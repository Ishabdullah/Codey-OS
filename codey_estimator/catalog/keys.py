from codey_estimator.catalog.schema import Measure, NormalizedAttributes, get_schema
from codey_estimator.errors import CatalogValidationError


def canonical_key(attrs: NormalizedAttributes) -> str:
    schema = get_schema(attrs.category)
    for attr in schema.required:
        if attrs.get(attr) is None:
            raise CatalogValidationError(
                "MISSING_REQUIRED_ATTRIBUTE",
                f"missing required attribute: {attr}",
                attr=attr.value,
            )
    segments: list[str] = []
    for attr in schema.key_attrs:
        value = attrs.get(attr)
        if value is None:
            segments.append("*")
        elif isinstance(value, Measure):
            segments.append(value.key_text())
        else:
            segments.append(str(value))
    return f"{attrs.category.value}:" + "|".join(segments)
