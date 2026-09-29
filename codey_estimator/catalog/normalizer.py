import re
from collections.abc import Callable
from fractions import Fraction
from typing import Final

from codey_estimator.catalog.schema import (
    Attr,
    AttrKind,
    AttrValue,
    Category,
    Measure,
    NormalizedAttributes,
    get_schema,
    make_attributes,
    normalize_brand,
)
from codey_estimator.catalog.text import (
    COLOR,
    DRYWALL_SUBTYPE,
    FASTENER_MATERIAL,
    FASTENER_SUBTYPE,
    FASTENER_TYPE,
    LUMBER_MATERIAL,
    LUMBER_TREATMENT,
    NUM,
    PAINT_FINISH,
    PAINT_SUBTYPE,
    PAINT_TYPE,
    PIPE_MATERIAL,
    PIPE_PRODUCT_TYPE,
    PIPE_SUBTYPE,
    find_first,
    find_gauge,
    find_measures,
    find_pack_count,
    format_measure_value,
    parse_fraction,
    preprocess,
)

Span = tuple[int, int]

_BARE_SIZE_RE: Final[re.Pattern[str]] = re.compile(
    r"(?<![\d/.#])(?P<num>" + NUM + r")(?![\d/]|\.\d)"
)

_DRYWALL_PAIR_RE: Final[re.Pattern[str]] = re.compile(
    r"(?<![\d/.#])(?P<a>" + NUM + r")\s*(?:ft\.?|feet|foot)?\s*x\s*"
    r"(?P<b>" + NUM + r")\s*(?:ft\.?|feet|foot)?"
    r"(?!\s*-?\s*(?:inches|inch|in\b))"
)

_LUMBER_TRIPLE_RE: Final[re.Pattern[str]] = re.compile(
    r"(?<![\d/.#])(?P<a>" + NUM + r")\s*(?:inches|inch|in\.?)?\s*x\s*"
    r"(?P<b>" + NUM + r")\s*(?:inches|inch|in\.?)?\s*x\s*"
    r"(?P<c>" + NUM + r")\s*-?\s*"
    r"(?P<cu>feet|foot|ft\.?|inches|inch|in\.?)?(?![a-z0-9])"
)

_LUMBER_PAIR_RE: Final[re.Pattern[str]] = re.compile(
    r"(?<![\d/.#])(?P<a>" + NUM + r")\s*(?:inches|inch|in\.?)?\s*x\s*"
    r"(?P<b>" + NUM + r")\s*(?:inches|inch|in\.?)?"
    r"(?!\s*-?\s*(?:feet|foot|ft\b)|\s*x)"
)

_GALLON_RE: Final[re.Pattern[str]] = re.compile(r"\bgallon\b")
_QUART_RE: Final[re.Pattern[str]] = re.compile(r"\bquart\b")


def _overlaps(a: Span, b: Span) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def _bare_size(pre: str, exclude: list[Span]) -> Fraction | None:
    for m in _BARE_SIZE_RE.finditer(pre):
        span = m.span()
        if any(_overlaps(span, e) for e in exclude):
            continue
        token = m.group("num")
        if "/" in token or "." in token:
            return parse_fraction(token)
    return None


def _extract_pipe(pre: str) -> dict[Attr, AttrValue]:
    values: dict[Attr, AttrValue] = {}
    measures = find_measures(pre)
    in_measures = [m for m, _ in measures if m.unit == "IN"]
    ft_measures = [m for m, _ in measures if m.unit == "FT"]
    exclude = [s for _, s in measures]
    if in_measures:
        values[Attr.NOMINAL_SIZE] = in_measures[0]
    else:
        bare = _bare_size(pre, exclude)
        if bare is not None:
            values[Attr.NOMINAL_SIZE] = Measure(bare, "IN")
    if ft_measures:
        values[Attr.LENGTH] = ft_measures[0]
    material = find_first(PIPE_MATERIAL, pre)
    if material is not None:
        values[Attr.MATERIAL] = material
    subtype = find_first(PIPE_SUBTYPE, pre)
    if subtype is not None:
        values[Attr.SUBTYPE] = subtype
    product_type = find_first(PIPE_PRODUCT_TYPE, pre)
    if product_type is not None:
        values[Attr.PRODUCT_TYPE] = product_type
    color = find_first(COLOR, pre)
    if color is not None:
        values[Attr.COLOR] = color
    count = find_pack_count(pre)
    if count is not None:
        values[Attr.PACKAGE_COUNT] = count
    return values


def _extract_drywall(pre: str) -> dict[Attr, AttrValue]:
    values: dict[Attr, AttrValue] = {}
    measures = find_measures(pre)
    exclude: list[Span] = [s for _, s in measures]

    pair_match = _DRYWALL_PAIR_RE.search(pre)
    pair_span: Span | None = None
    if pair_match is not None:
        a = parse_fraction(pair_match.group("a"))
        b = parse_fraction(pair_match.group("b"))
        lo, hi = sorted((a, b))
        values[Attr.WIDTH] = Measure(lo, "FT")
        values[Attr.LENGTH] = Measure(hi, "FT")
        pair_span = pair_match.span()
        exclude.append(pair_span)
    else:
        ft_measures = [m for m, _ in measures if m.unit == "FT"]
        if len(ft_measures) >= 2:
            lo, hi = sorted((ft_measures[0].value, ft_measures[1].value))
            values[Attr.WIDTH] = Measure(lo, "FT")
            values[Attr.LENGTH] = Measure(hi, "FT")

    in_measures = [
        (m, s)
        for m, s in measures
        if m.unit == "IN" and not (pair_span and _overlaps(s, pair_span))
    ]
    if in_measures:
        values[Attr.THICKNESS] = in_measures[0][0]
    else:
        bare = _bare_size(pre, exclude)
        if bare is not None:
            values[Attr.THICKNESS] = Measure(bare, "IN")

    subtype = find_first(DRYWALL_SUBTYPE, pre)
    if subtype is not None:
        values[Attr.SUBTYPE] = subtype
    count = find_pack_count(pre)
    if count is not None:
        values[Attr.PACKAGE_COUNT] = count
    return values


def _extract_lumber(pre: str) -> dict[Attr, AttrValue]:
    values: dict[Attr, AttrValue] = {}
    triple = _LUMBER_TRIPLE_RE.search(pre)
    if triple is not None:
        a = parse_fraction(triple.group("a"))
        b = parse_fraction(triple.group("b"))
        c = parse_fraction(triple.group("c"))
        cu = triple.group("cu")
        if cu is not None:
            cu_clean = cu.rstrip(".")
            if cu_clean in ("feet", "foot", "ft"):
                length = Measure(c, "FT")
            else:
                length = Measure(c / 12, "FT")
        elif c <= 24:
            length = Measure(c, "FT")
        else:
            length = Measure(c / 12, "FT")
        lo, hi = sorted((a, b))
        values[Attr.DIMENSION] = f"{format_measure_value(lo)}x{format_measure_value(hi)}"
        values[Attr.LENGTH] = length
    else:
        pair = _LUMBER_PAIR_RE.search(pre)
        if pair is not None:
            a = parse_fraction(pair.group("a"))
            b = parse_fraction(pair.group("b"))
            lo, hi = sorted((a, b))
            values[Attr.DIMENSION] = f"{format_measure_value(lo)}x{format_measure_value(hi)}"
            ft_measures = [m for m, _ in find_measures(pre) if m.unit == "FT"]
            if ft_measures:
                values[Attr.LENGTH] = ft_measures[0]

    treatment = find_first(LUMBER_TREATMENT, pre)
    if treatment is not None:
        values[Attr.TREATMENT] = treatment
    material = find_first(LUMBER_MATERIAL, pre)
    if material is not None:
        values[Attr.MATERIAL] = material
    count = find_pack_count(pre)
    if count is not None:
        values[Attr.PACKAGE_COUNT] = count
    return values


def _extract_fastener(pre: str) -> dict[Attr, AttrValue]:
    values: dict[Attr, AttrValue] = {}
    product_type = find_first(FASTENER_TYPE, pre)
    if product_type is not None:
        values[Attr.PRODUCT_TYPE] = product_type
    gauge = find_gauge(pre)
    if gauge is not None:
        values[Attr.GAUGE] = gauge
    subtype = find_first(FASTENER_SUBTYPE, pre)
    if subtype is not None:
        values[Attr.SUBTYPE] = subtype
    material = find_first(FASTENER_MATERIAL, pre)
    if material is not None:
        values[Attr.MATERIAL] = material
    in_measures = [m for m, _ in find_measures(pre) if m.unit == "IN"]
    if in_measures:
        values[Attr.LENGTH] = in_measures[0]
    count = find_pack_count(pre)
    if count is not None:
        values[Attr.PACKAGE_COUNT] = count
    return values


def _extract_paint(pre: str) -> dict[Attr, AttrValue]:
    values: dict[Attr, AttrValue] = {}
    product_type = find_first(PAINT_TYPE, pre)
    if product_type is not None:
        values[Attr.PRODUCT_TYPE] = product_type
    finish = find_first(PAINT_FINISH, pre)
    if finish is not None:
        values[Attr.FINISH] = finish
    subtype = find_first(PAINT_SUBTYPE, pre)
    if subtype is not None:
        values[Attr.SUBTYPE] = subtype
    color = find_first(COLOR, pre)
    if color is not None:
        values[Attr.COLOR] = color

    gal_qt = [m for m, _ in find_measures(pre) if m.unit in ("GAL", "QT")]
    volume: Fraction | None = None
    if gal_qt:
        m0 = gal_qt[0]
        volume = m0.value if m0.unit == "GAL" else m0.value / 4
    elif _GALLON_RE.search(pre):
        volume = Fraction(1)
    elif _QUART_RE.search(pre):
        volume = Fraction(1, 4)
    if volume is not None:
        values[Attr.VOLUME] = Measure(volume, "GAL")

    count = find_pack_count(pre)
    if count is not None:
        values[Attr.PACKAGE_COUNT] = count
    return values


_EXTRACTORS: Final[dict[Category, Callable[[str], dict[Attr, AttrValue]]]] = {
    Category.PLUMBING_PIPE: _extract_pipe,
    Category.DRYWALL_SHEET: _extract_drywall,
    Category.LUMBER: _extract_lumber,
    Category.FASTENER: _extract_fastener,
    Category.PAINT: _extract_paint,
}


def normalize_product(
    text: str, category: "Category | str", *, brand: str | None = None
) -> NormalizedAttributes:
    if not isinstance(text, str):
        raise TypeError(f"normalize_product requires a str, got {type(text)!r}")
    schema = get_schema(category)
    pre = preprocess(text)
    values = _EXTRACTORS[schema.category](pre)

    for spec in schema.specs:
        if spec.kind is AttrKind.TEXT and spec.default is not None and spec.attr not in values:
            values[spec.attr] = spec.default

    if brand is not None:
        normalized_brand = normalize_brand(brand)
        if normalized_brand is not None:
            values[Attr.BRAND] = normalized_brand

    return make_attributes(schema.category, values)
