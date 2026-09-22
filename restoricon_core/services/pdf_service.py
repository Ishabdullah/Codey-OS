"""
PDF rendering service for Restoricon Core (B8.6d-a).

Structured template + signature-anchor model: callers pass a `DocumentSpec`
(title, an ordered list of label/value fields, a free-text body, and a list
of signature anchors) and get back PDF bytes. Deliberately NOT HTML-to-PDF
-- reportlab has no HTML rendering path, so the input is this structured
spec, not a template string.

Uses `reportlab.pdfgen.canvas` (direct x/y coordinate control) rather than
`reportlab.platypus` (flowable/paragraph-based). The signature-anchor design
needs named x/y coordinates per anchor; canvas gives that directly, while
platypus's flowable model is a better fit for pure prose and would fight
the anchor model rather than match it.

This sub-phase (B8.6d-a) renders exactly ONE signature anchor -- the
existing single Contract.customer_signed_at/customer_signature_data pair.
Multi-party signer tracking is B8.6d-b, out of scope here; `DocumentSpec`
already carries a *list* of anchors so that later phase does not need a
data-model change, but `render_pdf` below only draws the first one.
"""

from __future__ import annotations

import base64
import binascii
import io
import re
from dataclasses import dataclass, field
from typing import List, Optional

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfgen import canvas as rl_canvas

PDF_MAGIC = b"%PDF-"

# Matches a genuine base64-encoded image data URL (the HTML5-canvas
# e-signature shape sign_contract's portal caller sends). Deliberately
# narrow -- only data:image/...;base64,... counts as "an image"; every
# other signature_data shape (the internal staff countersignature sentinel
# 'portal_countersignature', the routes.py fallback default
# 'digital_signature_token', or any other opaque token) falls through to
# the typed-text stamp branch below.
_DATA_URL_RE = re.compile(r"^data:image/[a-zA-Z0-9.+-]+;base64,", re.IGNORECASE)

_PAGE_WIDTH, _PAGE_HEIGHT = LETTER
_MARGIN = 54.0  # 0.75in
_LINE_HEIGHT = 14.0
_BOTTOM_GUARD = _MARGIN + _LINE_HEIGHT * 4


@dataclass
class SignatureAnchor:
    party_role: str
    page: int
    x: float
    y: float
    label: str


@dataclass
class DocumentField:
    label: str
    value: str


@dataclass
class DocumentSpec:
    title: str
    fields: List[DocumentField] = field(default_factory=list)
    signature_anchors: List[SignatureAnchor] = field(default_factory=list)
    # Free-text body (e.g. Contract.content), rendered below `fields` and
    # above the signature anchor. Kept separate from `fields` because
    # contract content is a single prose blob, not a label/value pair.
    body: str = ""


def is_data_url_image(signature_data: Optional[str]) -> bool:
    """True only for a genuine base64 image data URL. See _DATA_URL_RE."""
    if not signature_data or not isinstance(signature_data, str):
        return False
    return bool(_DATA_URL_RE.match(signature_data))


def _decode_data_url_image(data_url: str) -> bytes:
    _, _, encoded = data_url.partition(",")
    return base64.b64decode(encoded, validate=True)


def render_pdf(spec: DocumentSpec, signature_data: Optional[str], signer_label: str) -> bytes:
    """Render a DocumentSpec to PDF bytes.

    `signature_data` is the raw value from the one supported anchor for
    this sub-phase (single-signer only). `signer_label` is the
    human-readable text drawn for the typed-text stamp branch (used both
    when signature_data isn't an image, and as a fallback if an
    image-shaped signature_data fails to decode).
    """
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=LETTER)

    y = _PAGE_HEIGHT - _MARGIN
    c.setFont("Helvetica-Bold", 16)
    c.drawString(_MARGIN, y, spec.title)
    y -= _LINE_HEIGHT * 2

    for f in spec.fields:
        if y < _BOTTOM_GUARD:
            c.showPage()
            y = _PAGE_HEIGHT - _MARGIN
        c.setFont("Helvetica-Bold", 10)
        c.drawString(_MARGIN, y, f"{f.label}:")
        c.setFont("Helvetica", 10)
        c.drawString(_MARGIN + 130, y, str(f.value))
        y -= _LINE_HEIGHT

    if spec.body:
        y -= _LINE_HEIGHT
        max_width = _PAGE_WIDTH - 2 * _MARGIN
        for raw_line in (spec.body.splitlines() or [""]):
            wrapped = simpleSplit(raw_line, "Helvetica", 9, max_width) or [""]
            for line in wrapped:
                if y < _BOTTOM_GUARD:
                    c.showPage()
                    y = _PAGE_HEIGHT - _MARGIN
                c.setFont("Helvetica", 9)
                c.drawString(_MARGIN, y, line)
                y -= _LINE_HEIGHT

    # Signature anchor -- this sub-phase draws only the first entry
    # (single-signer, B8.6d-a). Always starts on a fresh page so the
    # anchor's own x/y (measured from that page's origin) never collides
    # with wrapped body text above; `anchor.page` isn't otherwise used to
    # route content this round since there is exactly one anchor and one
    # signature section.
    if spec.signature_anchors:
        anchor = spec.signature_anchors[0]
        c.showPage()
        c.setFont("Helvetica", 9)
        c.drawString(anchor.x, anchor.y + 16, f"{anchor.label} ({anchor.party_role}):")

        drew_image = False
        if is_data_url_image(signature_data):
            try:
                image_bytes = _decode_data_url_image(signature_data)
                reader = ImageReader(io.BytesIO(image_bytes))
                c.drawImage(
                    reader, anchor.x, anchor.y, width=180, height=60,
                    preserveAspectRatio=True, anchor="sw", mask="auto",
                )
                drew_image = True
            except (binascii.Error, ValueError, OSError):
                # Malformed base64/image payload inside an otherwise
                # image-shaped data URL -- fall through to the typed-text
                # stamp rather than raising; a broken signature image must
                # not abort PDF generation for an already-committed sign.
                drew_image = False

        if not drew_image:
            c.setFont("Helvetica-Oblique", 10)
            c.drawString(anchor.x, anchor.y, signer_label)

    c.showPage()
    c.save()
    return buf.getvalue()


def render_contract_pdf(contract, signer_label: str) -> bytes:
    """Build a DocumentSpec from an already-signed Contract's existing
    fields and render it. `signer_label` is the typed-text stamp used when
    contract.customer_signature_data isn't an image (see render_pdf)."""
    spec = DocumentSpec(
        title=contract.title or f"Contract {contract.contract_number}",
        fields=[
            DocumentField("Contract Number", contract.contract_number or ""),
            DocumentField("Status", contract.status or ""),
            DocumentField("Signed At", contract.customer_signed_at or ""),
        ],
        body=contract.content or "",
        signature_anchors=[
            SignatureAnchor(
                party_role="customer",
                page=1,
                x=_MARGIN,
                y=120.0,
                label="Signature",
            ),
        ],
    )
    return render_pdf(spec, contract.customer_signature_data, signer_label)
