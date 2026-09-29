from decimal import Decimal, localcontext
from fractions import Fraction
from typing import Final, TypedDict

from codey_estimator.dto import (
    DiscountKind,
    EstimateInput,
    EstimateResult,
    LaborRateType,
    LineInput,
    LineResult,
    LineType,
    TaxMethod,
)
from codey_estimator.errors import (
    EstimateValidationError,
    IncompatibleUnitsError,
    UnknownUnitError,
)
from codey_estimator.money import (
    allocate_pro_rata,
    apply_markup,
    percent_of,
    ratio_bp,
    round_half_up,
)
from codey_estimator.units import convert_quantity, normalize_unit, packages_needed

CALC_ENGINE_VERSION: Final[int] = 1


class _LineRaw(TypedDict):
    """Internal shape returned by `_compute_line`, before it's spread into a
    `LineResult`. Not part of the public API."""

    qty_with_waste: Decimal | None
    packages_needed: int | None
    material_cost_cents: int
    material_sell_cents: int
    labor_cost_cents: int
    labor_sell_cents: int
    equipment_cost_cents: int
    equipment_sell_cents: int
    sub_cost_cents: int
    sub_sell_cents: int
    cost_total_cents: int
    components_sell_cents: int
    sell_before_discount_cents: int
    price_override_applied: bool
    sell_total_cents: int


def _require_money(value: object, field_name: str, line_key: str | None) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int cents, got {type(value)!r}")


def _require_qty(value: object, field_name: str, line_key: str | None) -> None:
    if isinstance(value, bool) or not isinstance(value, (Decimal, int)):
        raise TypeError(f"{field_name} must be Decimal or int, got {type(value)!r}")
    if isinstance(value, Decimal) and not value.is_finite():
        raise ValueError(f"{field_name} must be finite, got {value}")


def _require_bp(value: object, field_name: str, line_key: str | None) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int basis points, got {type(value)!r}")


def _fraction_to_decimal(frac: Fraction) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = 60
        return Decimal(frac.numerator) / Decimal(frac.denominator)


def _validate_line(line: LineInput, seen_keys: set[str]) -> None:
    if not line.line_key or not line.line_key.strip():
        raise EstimateValidationError("BLANK_LINE_KEY", "line_key is blank", line.line_key)
    if line.line_key in seen_keys:
        raise EstimateValidationError(
            "DUPLICATE_LINE_KEY", f"duplicate line_key {line.line_key!r}", line.line_key
        )
    seen_keys.add(line.line_key)

    has_material = line.material is not None
    has_labor = line.labor is not None
    has_equipment = line.equipment is not None
    has_sub = line.subcontractor is not None
    group_count = sum((has_material, has_labor, has_equipment, has_sub))

    if line.line_type == LineType.MATERIAL:
        ok = has_material and group_count == 1
    elif line.line_type == LineType.LABOR:
        ok = has_labor and group_count == 1
    elif line.line_type == LineType.EQUIPMENT:
        ok = has_equipment and group_count == 1
    elif line.line_type == LineType.SUBCONTRACTOR:
        ok = has_sub and group_count == 1
    elif line.line_type == LineType.COMBINED:
        ok = group_count >= 2
    elif line.line_type in (LineType.ALLOWANCE, LineType.FEE):
        ok = True
        if group_count == 0 and line.price_override_cents is None:
            raise EstimateValidationError(
                "ALLOWANCE_FEE_REQUIRES_OVERRIDE",
                f"{line.line_type} line with no components requires price_override_cents",
                line.line_key,
            )
    else:
        ok = False
    if not ok:
        raise EstimateValidationError(
            "LINE_TYPE_MISMATCH",
            f"line_type {line.line_type} does not match the components present",
            line.line_key,
        )

    if line.material is not None:
        m = line.material
        _require_qty(m.quantity, "material.quantity", line.line_key)
        if m.quantity < 0:
            raise EstimateValidationError(
                "NEGATIVE_QUANTITY", "material.quantity is negative", line.line_key
            )
        _require_qty(m.package_qty, "material.package_qty", line.line_key)
        if m.package_qty < 1:
            raise EstimateValidationError(
                "INVALID_PACKAGE_QTY", "material.package_qty must be >= 1", line.line_key
            )
        _require_money(m.unit_cost_cents, "material.unit_cost_cents", line.line_key)
        if m.unit_cost_cents < 0:
            raise EstimateValidationError(
                "NEGATIVE_AMOUNT", "material.unit_cost_cents is negative", line.line_key
            )
        _require_bp(m.waste_pct_bp, "material.waste_pct_bp", line.line_key)
        if not (0 <= m.waste_pct_bp <= 10_000):
            raise EstimateValidationError(
                "INVALID_BP", "material.waste_pct_bp out of range", line.line_key
            )
        _require_bp(m.material_markup_bp, "material.material_markup_bp", line.line_key)
        if m.material_markup_bp < 0:
            raise EstimateValidationError(
                "INVALID_BP", "material.material_markup_bp is negative", line.line_key
            )
        try:
            normalize_unit(m.unit)
            normalize_unit(m.package_unit or m.unit)
        except UnknownUnitError as exc:
            raise EstimateValidationError("UNKNOWN_UNIT", str(exc), line.line_key) from exc
        try:
            convert_quantity(Fraction(1), m.unit, m.package_unit or m.unit)
        except IncompatibleUnitsError as exc:
            raise EstimateValidationError("INCOMPATIBLE_UNITS", str(exc), line.line_key) from exc

    if line.labor is not None:
        lb = line.labor
        _require_qty(lb.labor_qty, "labor.labor_qty", line.line_key)
        if lb.labor_qty < 0:
            raise EstimateValidationError(
                "NEGATIVE_QUANTITY", "labor.labor_qty is negative", line.line_key
            )
        _require_money(lb.labor_cost_rate_cents, "labor.labor_cost_rate_cents", line.line_key)
        if lb.labor_cost_rate_cents < 0:
            raise EstimateValidationError(
                "NEGATIVE_AMOUNT", "labor.labor_cost_rate_cents is negative", line.line_key
            )
        _require_money(lb.labor_bill_rate_cents, "labor.labor_bill_rate_cents", line.line_key)
        if lb.labor_bill_rate_cents < 0:
            raise EstimateValidationError(
                "NEGATIVE_AMOUNT", "labor.labor_bill_rate_cents is negative", line.line_key
            )
        try:
            unit_code = normalize_unit(lb.labor_unit)
        except UnknownUnitError as exc:
            raise EstimateValidationError("UNKNOWN_UNIT", str(exc), line.line_key) from exc
        if lb.rate_type == LaborRateType.HOURLY and unit_code != "HR":
            raise EstimateValidationError(
                "LABOR_UNIT_MISMATCH", "HOURLY labor must use HR unit", line.line_key
            )
        if lb.rate_type == LaborRateType.FIXED_PER_UNIT and unit_code == "HR":
            raise EstimateValidationError(
                "LABOR_UNIT_MISMATCH", "FIXED_PER_UNIT labor must not use HR unit", line.line_key
            )

    if line.equipment is not None:
        eq = line.equipment
        _require_money(eq.equipment_cost_cents, "equipment.equipment_cost_cents", line.line_key)
        if eq.equipment_cost_cents < 0:
            raise EstimateValidationError(
                "NEGATIVE_AMOUNT", "equipment.equipment_cost_cents is negative", line.line_key
            )
        _require_bp(eq.equipment_markup_bp, "equipment.equipment_markup_bp", line.line_key)
        if eq.equipment_markup_bp < 0:
            raise EstimateValidationError(
                "INVALID_BP", "equipment.equipment_markup_bp is negative", line.line_key
            )

    if line.subcontractor is not None:
        sub = line.subcontractor
        _require_money(sub.sub_cost_cents, "subcontractor.sub_cost_cents", line.line_key)
        if sub.sub_cost_cents < 0:
            raise EstimateValidationError(
                "NEGATIVE_AMOUNT", "subcontractor.sub_cost_cents is negative", line.line_key
            )
        _require_bp(sub.sub_markup_bp, "subcontractor.sub_markup_bp", line.line_key)
        if sub.sub_markup_bp < 0:
            raise EstimateValidationError(
                "INVALID_BP", "subcontractor.sub_markup_bp is negative", line.line_key
            )

    _require_money(line.line_discount_cents, "line_discount_cents", line.line_key)
    if line.line_discount_cents < 0:
        raise EstimateValidationError(
            "NEGATIVE_AMOUNT", "line_discount_cents is negative", line.line_key
        )

    if line.price_override_cents is not None:
        _require_money(line.price_override_cents, "price_override_cents", line.line_key)
        if line.price_override_cents < 0:
            raise EstimateValidationError(
                "NEGATIVE_AMOUNT", "price_override_cents is negative", line.line_key
            )
        if not line.override_reason or not line.override_reason.strip():
            raise EstimateValidationError(
                "OVERRIDE_REASON_REQUIRED",
                "price_override_cents requires a non-blank override_reason",
                line.line_key,
            )


def _compute_line(line: LineInput) -> _LineRaw:
    qty_with_waste: Decimal | None = None
    packages: int | None = None
    material_cost = material_sell = 0
    if line.material is not None:
        m = line.material
        qty_frac = Fraction(m.quantity)
        waste_frac = qty_frac * Fraction(10_000 + m.waste_pct_bp, 10_000)
        qty_with_waste = _fraction_to_decimal(waste_frac)
        package_unit = m.package_unit or m.unit
        packages = packages_needed(waste_frac, m.unit, m.package_qty, package_unit)
        material_cost = packages * m.unit_cost_cents
        material_sell = apply_markup(material_cost, m.material_markup_bp)

    labor_cost = labor_sell = 0
    if line.labor is not None:
        lb = line.labor
        eff_qty = (
            Fraction(1) if lb.rate_type == LaborRateType.FIXED_FLAT else Fraction(lb.labor_qty)
        )
        labor_cost = round_half_up(eff_qty * lb.labor_cost_rate_cents)
        labor_sell = round_half_up(eff_qty * lb.labor_bill_rate_cents)

    equipment_cost = equipment_sell = 0
    if line.equipment is not None:
        eq = line.equipment
        equipment_cost = eq.equipment_cost_cents
        equipment_sell = apply_markup(equipment_cost, eq.equipment_markup_bp)

    sub_cost = sub_sell = 0
    if line.subcontractor is not None:
        sub = line.subcontractor
        sub_cost = sub.sub_cost_cents
        sub_sell = apply_markup(sub_cost, sub.sub_markup_bp)

    cost_total = material_cost + labor_cost + equipment_cost + sub_cost
    components_sell = material_sell + labor_sell + equipment_sell + sub_sell
    price_override_applied = line.price_override_cents is not None
    sell_before_discount = (
        line.price_override_cents
        if line.price_override_cents is not None
        else components_sell
    )
    sell_total = sell_before_discount - line.line_discount_cents
    if sell_total < 0:
        raise EstimateValidationError(
            "NEGATIVE_LINE_SELL",
            "line_discount_cents exceeds sell_before_discount",
            line.line_key,
        )

    return {
        "qty_with_waste": qty_with_waste,
        "packages_needed": packages,
        "material_cost_cents": material_cost,
        "material_sell_cents": material_sell,
        "labor_cost_cents": labor_cost,
        "labor_sell_cents": labor_sell,
        "equipment_cost_cents": equipment_cost,
        "equipment_sell_cents": equipment_sell,
        "sub_cost_cents": sub_cost,
        "sub_sell_cents": sub_sell,
        "cost_total_cents": cost_total,
        "components_sell_cents": components_sell,
        "sell_before_discount_cents": sell_before_discount,
        "price_override_applied": price_override_applied,
        "sell_total_cents": sell_total,
    }


def calculate_line(line: LineInput) -> LineResult:
    _validate_line(line, set())
    raw = _compute_line(line)
    return LineResult(
        input=line,
        qty_with_waste=raw["qty_with_waste"],
        packages_needed=raw["packages_needed"],
        material_cost_cents=raw["material_cost_cents"],
        material_sell_cents=raw["material_sell_cents"],
        labor_cost_cents=raw["labor_cost_cents"],
        labor_sell_cents=raw["labor_sell_cents"],
        equipment_cost_cents=raw["equipment_cost_cents"],
        equipment_sell_cents=raw["equipment_sell_cents"],
        sub_cost_cents=raw["sub_cost_cents"],
        sub_sell_cents=raw["sub_sell_cents"],
        cost_total_cents=raw["cost_total_cents"],
        components_sell_cents=raw["components_sell_cents"],
        sell_before_discount_cents=raw["sell_before_discount_cents"],
        price_override_applied=raw["price_override_applied"],
        line_discount_cents=line.line_discount_cents,
        sell_total_cents=raw["sell_total_cents"],
        allocated_discount_cents=0,
        net_sell_cents=raw["sell_total_cents"],
        taxable_amount_cents=0,
        tax_cents=0,
        line_total_cents=raw["sell_total_cents"],
    )


def calculate(estimate: EstimateInput) -> EstimateResult:
    _require_bp(estimate.tax_rate_bp, "tax_rate_bp", None)
    if not (0 <= estimate.tax_rate_bp <= 10_000):
        raise EstimateValidationError("INVALID_BP", "tax_rate_bp out of range", None)

    if estimate.margin_floor_bp is not None:
        _require_bp(estimate.margin_floor_bp, "margin_floor_bp", None)
        if not (-10_000 <= estimate.margin_floor_bp <= 10_000):
            raise EstimateValidationError("INVALID_BP", "margin_floor_bp out of range", None)

    if estimate.estimate_discount is not None:
        d = estimate.estimate_discount
        if d.kind == DiscountKind.PERCENT:
            _require_bp(d.value, "estimate_discount.value", None)
            if not (0 <= d.value <= 10_000):
                raise EstimateValidationError(
                    "INVALID_BP", "estimate_discount percent out of range", None
                )
        else:
            _require_money(d.value, "estimate_discount.value", None)
            if d.value < 0:
                raise EstimateValidationError(
                    "NEGATIVE_AMOUNT", "estimate_discount fixed value is negative", None
                )

    seen_keys: set[str] = set()
    raws: list[_LineRaw] = []
    for line in estimate.lines:
        _validate_line(line, seen_keys)
        raws.append(_compute_line(line))

    subtotal_sell = sum(r["sell_total_cents"] for r in raws)

    if estimate.estimate_discount is None:
        discount = 0
    elif estimate.estimate_discount.kind == DiscountKind.FIXED:
        discount = estimate.estimate_discount.value
        if discount > subtotal_sell:
            raise EstimateValidationError(
                "DISCOUNT_EXCEEDS_SUBTOTAL", "fixed discount exceeds subtotal", None
            )
    else:
        discount = percent_of(subtotal_sell, estimate.estimate_discount.value)

    weights = [r["sell_total_cents"] for r in raws]
    allocated = allocate_pro_rata(discount, weights)
    net_sells = [raws[i]["sell_total_cents"] - allocated[i] for i in range(len(raws))]

    taxable_amounts: list[int] = []
    for i, r in enumerate(raws):
        line = estimate.lines[i]
        if estimate.tax_method == TaxMethod.NONE:
            taxable = 0
        elif estimate.tax_method == TaxMethod.TAXABLE_LINES:
            taxable = net_sells[i] if line.taxable else 0
        else:
            if not line.taxable or r["components_sell_cents"] == 0:
                taxable = 0
            else:
                taxable = round_half_up(
                    Fraction(net_sells[i] * r["material_sell_cents"], r["components_sell_cents"])
                )
        taxable_amounts.append(taxable)

    taxable_base = sum(taxable_amounts)
    tax = percent_of(taxable_base, estimate.tax_rate_bp)
    tax_alloc = allocate_pro_rata(tax, taxable_amounts)

    line_results: list[LineResult] = []
    for i, r in enumerate(raws):
        line = estimate.lines[i]
        line_total = net_sells[i] + tax_alloc[i]
        line_results.append(
            LineResult(
                input=line,
                qty_with_waste=r["qty_with_waste"],
                packages_needed=r["packages_needed"],
                material_cost_cents=r["material_cost_cents"],
                material_sell_cents=r["material_sell_cents"],
                labor_cost_cents=r["labor_cost_cents"],
                labor_sell_cents=r["labor_sell_cents"],
                equipment_cost_cents=r["equipment_cost_cents"],
                equipment_sell_cents=r["equipment_sell_cents"],
                sub_cost_cents=r["sub_cost_cents"],
                sub_sell_cents=r["sub_sell_cents"],
                cost_total_cents=r["cost_total_cents"],
                components_sell_cents=r["components_sell_cents"],
                sell_before_discount_cents=r["sell_before_discount_cents"],
                price_override_applied=r["price_override_applied"],
                line_discount_cents=line.line_discount_cents,
                sell_total_cents=r["sell_total_cents"],
                allocated_discount_cents=allocated[i],
                net_sell_cents=net_sells[i],
                taxable_amount_cents=taxable_amounts[i],
                tax_cents=tax_alloc[i],
                line_total_cents=line_total,
            )
        )

    total = subtotal_sell - discount + tax
    material_cost_total = sum(r["material_cost_cents"] for r in raws)
    labor_cost_total = sum(r["labor_cost_cents"] for r in raws)
    equipment_cost_total = sum(r["equipment_cost_cents"] for r in raws)
    sub_cost_total = sum(r["sub_cost_cents"] for r in raws)
    cost_total = material_cost_total + labor_cost_total + equipment_cost_total + sub_cost_total
    net = subtotal_sell - discount
    gross_profit = net - cost_total
    gross_margin_bp = 0 if net == 0 else ratio_bp(gross_profit, net)
    markup_effective_bp = None if cost_total == 0 else ratio_bp(gross_profit, cost_total)

    if (
        estimate.margin_floor_bp is not None
        and net > 0
        and gross_margin_bp < estimate.margin_floor_bp
    ):
        warnings: tuple[str, ...] = ("MARGIN_BELOW_FLOOR",)
    else:
        warnings = ()

    return EstimateResult(
        calc_engine_version=CALC_ENGINE_VERSION,
        tax_method=estimate.tax_method,
        tax_rate_bp=estimate.tax_rate_bp,
        lines=tuple(line_results),
        material_cost_cents=material_cost_total,
        labor_cost_cents=labor_cost_total,
        equipment_cost_cents=equipment_cost_total,
        sub_cost_cents=sub_cost_total,
        cost_total_cents=cost_total,
        subtotal_sell_cents=subtotal_sell,
        discount_cents=discount,
        taxable_base_cents=taxable_base,
        tax_cents=tax,
        total_cents=total,
        gross_profit_cents=gross_profit,
        gross_margin_bp=gross_margin_bp,
        markup_effective_bp=markup_effective_bp,
        warnings=warnings,
        terms=estimate.terms,
        customer_notes=estimate.customer_notes,
    )
