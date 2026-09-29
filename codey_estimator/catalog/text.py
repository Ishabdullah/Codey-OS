import re
from decimal import Decimal, localcontext
from fractions import Fraction
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from codey_estimator.catalog.schema import Measure

NUM: Final[str] = r"(?:\d+[\s-]+\d+/\d+|\d+/\d+|\d+\.\d+|\.\d+|\d+)"

NUM_RE: Final[re.Pattern[str]] = re.compile(NUM)
_MIXED_RE: Final[re.Pattern[str]] = re.compile(r"(\d+)[\s-]+(\d+)/(\d+)")
_FRAC_RE: Final[re.Pattern[str]] = re.compile(r"(\d+)/(\d+)")
_DEC_RE: Final[re.Pattern[str]] = re.compile(r"\d*\.\d+")
_INT_RE: Final[re.Pattern[str]] = re.compile(r"\d+")

_VULGAR_MAP: Final[dict[str, str]] = {
    "½": "1/2",
    "¼": "1/4",
    "¾": "3/4",
    "⅛": "1/8",
    "⅜": "3/8",
    "⅝": "5/8",
    "⅞": "7/8",
}
_VULGAR_RE: Final[re.Pattern[str]] = re.compile(
    r"(\d)?([½¼¾⅛⅜⅝⅞])"
)
_COMMA_RE: Final[re.Pattern[str]] = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")
_INCH_MARK_RE: Final[re.Pattern[str]] = re.compile(
    r"(?<=\d)\s*(?:''|\"|″|“|”)"
)
_FOOT_MARK_RE: Final[re.Pattern[str]] = re.compile(r"(?<=\d)\s*(?:'|′|’)")
_WS_RE: Final[re.Pattern[str]] = re.compile(r"\s+")

MEASURE_RE: Final[re.Pattern[str]] = re.compile(
    r"(?<![\d/.#])(?P<num>" + NUM + r")\s*-?\s*"
    r"(?P<unit>inches|inch|in\.?|feet|foot|ft\.?|gallons|gallon|gal\.?|quarts|quart|qt\.?)"
    r"(?![a-z0-9])"
)

_UNIT_WORDS: Final[dict[str, str]] = {
    "inches": "IN",
    "inch": "IN",
    "in": "IN",
    "feet": "FT",
    "foot": "FT",
    "ft": "FT",
    "gallons": "GAL",
    "gallon": "GAL",
    "gal": "GAL",
    "quarts": "QT",
    "quart": "QT",
    "qt": "QT",
}


def _sub_vulgar(m: re.Match[str]) -> str:
    frac = _VULGAR_MAP[m.group(2)]
    if m.group(1):
        return m.group(1) + "-" + frac
    return frac


def preprocess(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError("preprocess requires a str")
    result = text.lower()
    result = _VULGAR_RE.sub(_sub_vulgar, result)
    result = result.replace("⁄", "/").replace("×", "x")
    result = _COMMA_RE.sub("", result)
    result = _INCH_MARK_RE.sub(" in ", result)
    result = _FOOT_MARK_RE.sub(" ft ", result)
    result = _WS_RE.sub(" ", result).strip()
    return result


def _num_to_fraction(text: str) -> Fraction:
    m = _MIXED_RE.fullmatch(text)
    if m:
        whole, num, den = m.groups()
        d = int(den)
        if d == 0:
            raise ValueError(f"zero denominator: {text!r}")
        return Fraction(int(whole)) + Fraction(int(num), d)
    m = _FRAC_RE.fullmatch(text)
    if m:
        num, den = m.groups()
        d = int(den)
        if d == 0:
            raise ValueError(f"zero denominator: {text!r}")
        return Fraction(int(num), d)
    if _DEC_RE.fullmatch(text):
        return Fraction(text)
    if _INT_RE.fullmatch(text):
        return Fraction(int(text))
    raise ValueError(f"not a number: {text!r}")


def parse_fraction(token: str) -> Fraction:
    text = preprocess(token)
    if not NUM_RE.fullmatch(text):
        raise ValueError(f"not a number: {token!r}")
    return _num_to_fraction(text)


def find_measures(text: str) -> tuple[tuple["Measure", tuple[int, int]], ...]:
    from codey_estimator.catalog.schema import Measure

    pre = preprocess(text)
    results: list[tuple[Measure, tuple[int, int]]] = []
    for m in MEASURE_RE.finditer(pre):
        num_text = m.group("num")
        unit_text = m.group("unit").rstrip(".")
        try:
            value = _num_to_fraction(num_text)
        except ValueError:
            continue
        if value == 0:
            continue
        unit = _UNIT_WORDS[unit_text]
        results.append((Measure(value, unit), m.span()))
    return tuple(results)


def format_measure_value(value: Fraction) -> str:
    n, d = value.numerator, value.denominator
    remainder = d
    while remainder % 2 == 0:
        remainder //= 2
    while remainder % 5 == 0:
        remainder //= 5
    if remainder == 1:
        with localcontext() as ctx:
            ctx.prec = 60
            dec = Decimal(n) / Decimal(d)
        return format(dec.normalize(), "f")
    return f"{n}/{d}"


def _compile_all(*patterns: str) -> re.Pattern[str]:
    return re.compile("|".join(patterns))


COLOR: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    (re.compile(r"\bred\b"), "red"),
    (re.compile(r"\bblue\b"), "blue"),
    (re.compile(r"\bwhite\b"), "white"),
    (re.compile(r"\bblack\b"), "black"),
    (re.compile(r"\bgr[ae]y\b"), "gray"),
    (re.compile(r"\borange\b"), "orange"),
    (re.compile(r"\bgreen\b"), "green"),
    (re.compile(r"\byellow\b"), "yellow"),
    (re.compile(r"\bbrown\b"), "brown"),
    (re.compile(r"\bbeige\b"), "beige"),
    (re.compile(r"\bclear\b"), "clear"),
)

PIPE_MATERIAL: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    (re.compile(r"\bpex\b"), "PEX"),
    (re.compile(r"\bcpvc\b"), "CPVC"),
    (re.compile(r"\bpvc\b"), "PVC"),
    (re.compile(r"\bcopper\b"), "COPPER"),
    (re.compile(r"\babs\b"), "ABS"),
)

PIPE_SUBTYPE: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    (re.compile(r"\bpex[\s-]?a\b"), "PEX-A"),
    (re.compile(r"\bpex[\s-]?b\b"), "PEX-B"),
    (re.compile(r"\btype[\s-]?k\b"), "TYPE-K"),
    (re.compile(r"\btype[\s-]?l\b"), "TYPE-L"),
    (re.compile(r"\btype[\s-]?m\b"), "TYPE-M"),
    (re.compile(r"\b(?:sch|schedule)\.?[\s-]?40\b"), "SCH40"),
    (re.compile(r"\b(?:sch|schedule)\.?[\s-]?80\b"), "SCH80"),
)

PIPE_PRODUCT_TYPE: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    (re.compile(r"\b(?:pipes?|tubing|tubes?)\b"), "pipe"),
)

DRYWALL_SUBTYPE: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    (re.compile(r"\btype[\s-]?x\b|fire[\s-]?(?:resistant|rated)|firecode"), "TYPE-X"),
    (re.compile(r"\bmold\b"), "MOLD-RESISTANT"),
    (re.compile(r"moisture[\s-]resistant"), "MOISTURE-RESISTANT"),
)

LUMBER_TREATMENT: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    (
        re.compile(r"pressure[\s-]?treated|\bpt\b|ground[\s-]contact|above[\s-]ground"),
        "PT",
    ),
)

LUMBER_MATERIAL: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    (re.compile(r"\bspf\b"), "SPF"),
    (re.compile(r"\bdouglas[\s-]?fir\b|\bdoug[\s-]?fir\b|\bdf\b"), "DF"),
    (re.compile(r"\bsouthern[\s-]yellow[\s-]pine\b|\bsyp\b"), "SYP"),
    (re.compile(r"\bhem[\s-]?fir\b"), "HEM-FIR"),
    (re.compile(r"\bcedar\b"), "CEDAR"),
)

FASTENER_TYPE: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    (re.compile(r"\bscrews?\b"), "screw"),
    (re.compile(r"\bnails?\b"), "nail"),
)

_FASTENER_GAUGE_PATTERNS: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    (re.compile(r"#\s*(\d+)\b"), "#{}"),
    (re.compile(r"\bno\.?\s*(\d+)\b"), "#{}"),
    (re.compile(r"\b(\d+)d\b"), "{}d"),
    (re.compile(r"\b(\d+)[\s-]penny\b"), "{}d"),
)

FASTENER_SUBTYPE: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    (re.compile(r"\bdrywall\b"), "DRYWALL"),
    (re.compile(r"\bdeck(?:ing)?\b"), "DECK"),
    (re.compile(r"\broofing\b"), "ROOFING"),
    (re.compile(r"\bframing\b"), "FRAMING"),
    (re.compile(r"\bfinish(?:ing)?\b"), "FINISH"),
    (re.compile(r"\bwood\b"), "WOOD"),
)

FASTENER_MATERIAL: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    (re.compile(r"\bstainless\b"), "STAINLESS"),
    (re.compile(r"\bgalvanized\b|\bhot[\s-]dip(?:ped)?\b"), "GALVANIZED"),
    (re.compile(r"\bbrass\b"), "BRASS"),
    (re.compile(r"\bsteel\b"), "STEEL"),
)

PAINT_TYPE: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    (re.compile(r"paint\s*(?:and|&|\+)\s*primer"), "paint"),
    (re.compile(r"\bprimer\b"), "primer"),
    (re.compile(r"\bpaint\b"), "paint"),
)

PAINT_FINISH: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    (re.compile(r"\bsemi[\s-]?gloss\b"), "semi-gloss"),
    (re.compile(r"\beggshell\b"), "eggshell"),
    (re.compile(r"\bsatin\b"), "satin"),
    (re.compile(r"\bmatte\b"), "matte"),
    (re.compile(r"\bflat\b"), "flat"),
    (re.compile(r"\b(?:high[\s-])?gloss\b"), "gloss"),
)

PAINT_SUBTYPE: Final[tuple[tuple[re.Pattern[str], str], ...]] = (
    (re.compile(r"\binterior\s*(?:/|&|and|-)?\s*exterior\b"), "INTERIOR-EXTERIOR"),
    (re.compile(r"\binterior\b"), "INTERIOR"),
    (re.compile(r"\bexterior\b"), "EXTERIOR"),
)

_PACK_RE_1: Final[re.Pattern[str]] = re.compile(
    r"\b(\d+)[\s-]*(?:pack|pk|count|ct|pcs|pc|pieces|piece)\b"
)
_PACK_RE_2: Final[re.Pattern[str]] = re.compile(
    r"\b(?:box|bag|case|pack|carton|pail|bucket)\s+of\s+(\d+)\b"
)


def find_first(vocab: tuple[tuple[re.Pattern[str], str], ...], text: str) -> str | None:
    for pattern, value in vocab:
        if pattern.search(text):
            return value
    return None


def find_gauge(text: str) -> str | None:
    for pattern, template in _FASTENER_GAUGE_PATTERNS:
        m = pattern.search(text)
        if m:
            return template.format(str(int(m.group(1))))
    return None


def find_pack_count(text: str) -> int | None:
    for pattern in (_PACK_RE_1, _PACK_RE_2):
        m = pattern.search(text)
        if m:
            n = int(m.group(1))
            if n != 0:
                return n
    return None
