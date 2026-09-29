from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Final

from codey_estimator.errors import CustomerViewError
from codey_estimator.units import get_unit


class LineType(StrEnum):
    MATERIAL = "material"
    LABOR = "labor"
    EQUIPMENT = "equipment"
    SUBCONTRACTOR = "subcontractor"
    COMBINED = "combined"
    ALLOWANCE = "allowance"
    FEE = "fee"


class LaborRateType(StrEnum):
    HOURLY = "hourly"
    FIXED_PER_UNIT = "fixed_per_unit"
    FIXED_FLAT = "fixed_flat"


class TaxMethod(StrEnum):
    NONE = "none"
    MATERIALS_ONLY = "materials_only"
    TAXABLE_LINES = "taxable_lines"


class DiscountKind(StrEnum):
    FIXED = "fixed"
    PERCENT = "percent"


@dataclass(frozen=True, slots=True)
class MaterialInput:
    quantity: Decimal
    unit: str
    unit_cost_cents: int
    package_qty: Decimal = Decimal(1)
    package_unit: str | None = None
    waste_pct_bp: int = 0
    material_markup_bp: int = 0
    price_book_item_id: int | None = None
    retailer_product_id: int | None = None
    price_observation_id: int | None = None
    retailer_code_snapshot: str | None = None
    product_title_snapshot: str | None = None


@dataclass(frozen=True, slots=True)
class LaborInput:
    rate_type: LaborRateType
    labor_qty: Decimal
    labor_unit: str
    labor_cost_rate_cents: int
    labor_bill_rate_cents: int
    labor_type: str = ""
    labor_rate_id: int | None = None


@dataclass(frozen=True, slots=True)
class EquipmentInput:
    equipment_cost_cents: int
    equipment_markup_bp: int = 0
    equipment_id: int | None = None


@dataclass(frozen=True, slots=True)
class SubcontractorInput:
    sub_cost_cents: int
    sub_markup_bp: int = 0
    subcontractor_id: int | None = None


@dataclass(frozen=True, slots=True)
class LineInput:
    line_key: str
    line_type: LineType
    description: str
    customer_description: str = ""
    visible_to_customer: bool = True
    sort_order: int = 0
    section: str = ""
    category: str = ""
    material: MaterialInput | None = None
    labor: LaborInput | None = None
    equipment: EquipmentInput | None = None
    subcontractor: SubcontractorInput | None = None
    taxable: bool = True
    line_discount_cents: int = 0
    price_override_cents: int | None = None
    override_reason: str | None = None
    internal_note: str = ""


@dataclass(frozen=True, slots=True)
class EstimateDiscount:
    kind: DiscountKind
    value: int


@dataclass(frozen=True, slots=True)
class EstimateInput:
    lines: tuple[LineInput, ...]
    tax_rate_bp: int
    tax_method: TaxMethod = TaxMethod.MATERIALS_ONLY
    estimate_discount: EstimateDiscount | None = None
    terms: str = ""
    customer_notes: str = ""
    margin_floor_bp: int | None = None


@dataclass(frozen=True, slots=True)
class LineResult:
    input: LineInput
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
    line_discount_cents: int
    sell_total_cents: int
    allocated_discount_cents: int
    net_sell_cents: int
    taxable_amount_cents: int
    tax_cents: int
    line_total_cents: int


@dataclass(frozen=True, slots=True)
class EstimateResult:
    calc_engine_version: int
    tax_method: TaxMethod
    tax_rate_bp: int
    lines: tuple[LineResult, ...]
    material_cost_cents: int
    labor_cost_cents: int
    equipment_cost_cents: int
    sub_cost_cents: int
    cost_total_cents: int
    subtotal_sell_cents: int
    discount_cents: int
    taxable_base_cents: int
    tax_cents: int
    total_cents: int
    gross_profit_cents: int
    gross_margin_bp: int
    markup_effective_bp: int | None
    warnings: tuple[str, ...]
    terms: str
    customer_notes: str


@dataclass(frozen=True, slots=True)
class CustomerLineView:
    description: str
    quantity: str | None
    unit: str | None
    price_cents: int


@dataclass(frozen=True, slots=True)
class CustomerEstimateView:
    lines: tuple[CustomerLineView, ...]
    subtotal_cents: int
    discount_cents: int
    tax_cents: int
    total_cents: int
    terms: str
    customer_notes: str

    def to_dict(self) -> dict[str, object]:
        return {
            "lines": [
                {
                    "description": line.description,
                    "quantity": line.quantity,
                    "unit": line.unit,
                    "price_cents": line.price_cents,
                }
                for line in self.lines
            ],
            "subtotal_cents": self.subtotal_cents,
            "discount_cents": self.discount_cents,
            "tax_cents": self.tax_cents,
            "total_cents": self.total_cents,
            "terms": self.terms,
            "customer_notes": self.customer_notes,
        }


CUSTOMER_VIEW_KEYS: Final[frozenset[str]] = frozenset(
    {
        "lines",
        "subtotal_cents",
        "discount_cents",
        "tax_cents",
        "total_cents",
        "terms",
        "customer_notes",
    }
)
CUSTOMER_LINE_KEYS: Final[frozenset[str]] = frozenset(
    {"description", "quantity", "unit", "price_cents"}
)


def _format_quantity(qty: Decimal | int) -> str:
    if isinstance(qty, int):
        qty = Decimal(qty)
    return format(qty.normalize(), "f")


def to_customer_view(result: EstimateResult) -> CustomerEstimateView:
    indexed = list(enumerate(result.lines))
    visible = [
        (idx, line_result)
        for idx, line_result in indexed
        if line_result.input.visible_to_customer
    ]
    visible.sort(key=lambda pair: (pair[1].input.sort_order, pair[0]))

    views: list[CustomerLineView] = []
    for _, line_result in visible:
        li = line_result.input
        if not li.customer_description.strip():
            raise CustomerViewError(
                "MISSING_CUSTOMER_DESCRIPTION",
                f"line {li.line_key!r} is visible to customer but has no customer_description",
                li.line_key,
            )
        quantity: str | None
        unit: str | None
        if li.material is not None:
            quantity = _format_quantity(li.material.quantity)
            unit = get_unit(li.material.unit).label
        elif li.labor is not None:
            quantity = _format_quantity(li.labor.labor_qty)
            unit = get_unit(li.labor.labor_unit).label
        else:
            quantity = None
            unit = None
        views.append(
            CustomerLineView(
                description=li.customer_description,
                quantity=quantity,
                unit=unit,
                price_cents=line_result.sell_total_cents,
            )
        )

    return CustomerEstimateView(
        lines=tuple(views),
        subtotal_cents=result.subtotal_sell_cents,
        discount_cents=result.discount_cents,
        tax_cents=result.tax_cents,
        total_cents=result.total_cents,
        terms=result.terms,
        customer_notes=result.customer_notes,
    )
