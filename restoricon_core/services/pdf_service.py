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

B8.6d-a rendered exactly ONE signature anchor -- the single
Contract.customer_signed_at/customer_signature_data pair. B8.6d-b (this
round) draws every anchor in `spec.signature_anchors`, each with its own
optional per-anchor `signature_data`/`signer_label` (falling back to the
single positional `signature_data`/`signer_label` args passed to
`render_pdf` for any anchor that doesn't carry its own -- this keeps the
single-signer call shape from B8.6d-a working unchanged).
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
    # B8.6d-b: per-anchor override for render_pdf's positional
    # signature_data/signer_label args. None means "not signed yet" (for
    # signature_data) or "use render_pdf's fallback label" (for
    # signer_label) -- a multi-party PDF draws each anchor with its own
    # signer's data, not the same signature repeated at every anchor.
    signature_data: Optional[str] = None
    signer_label: Optional[str] = None


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

    # Signature anchors -- ALL anchors in spec.signature_anchors are drawn
    # (B8.6d-b; B8.6d-a drew only anchors[0], single-signer). All anchors
    # share one fresh signature page so their own x/y (measured from that
    # page's origin) land at distinct on-page positions rather than each
    # starting a new page and only ever landing at the same spot --
    # `anchor.page` isn't otherwise used to route content this round since
    # every current caller places all anchors on the same signature page.
    if spec.signature_anchors:
        c.showPage()
        for anchor in spec.signature_anchors:
            # Per-anchor signature_data/signer_label (B8.6d-b multi-party)
            # falls back to render_pdf's positional args (B8.6d-a
            # single-signer shape) when the anchor doesn't carry its own.
            anchor_signature_data = anchor.signature_data if anchor.signature_data is not None else signature_data
            anchor_signer_label = anchor.signer_label if anchor.signer_label is not None else signer_label

            c.setFont("Helvetica", 9)
            c.drawString(anchor.x, anchor.y + 16, f"{anchor.label} ({anchor.party_role}):")

            if not anchor_signature_data:
                # Required signer who hasn't signed yet (multi-party,
                # partially-signed contract) -- label the anchor but draw
                # no signature/stamp content.
                c.setFont("Helvetica-Oblique", 9)
                c.drawString(anchor.x, anchor.y, "(pending signature)")
                continue

            drew_image = False
            if is_data_url_image(anchor_signature_data):
                try:
                    image_bytes = _decode_data_url_image(anchor_signature_data)
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
                c.drawString(anchor.x, anchor.y, anchor_signer_label)

    c.showPage()
    c.save()
    return buf.getvalue()


_MULTI_SIGNER_Y_START = 200.0
_MULTI_SIGNER_Y_STEP = 80.0  # >= image height (60) + label gap (16), keeps anchors from overlapping


def render_contract_pdf_multi(contract, signer_rows) -> bytes:
    """Build a DocumentSpec from a multi-party contract's ContractSigner
    rows (B8.6d-b) -- one signature anchor per row, each at its own
    on-page position, each carrying that signer's own signature_data so
    render_pdf draws every completed signature (and labels any still-
    pending one) rather than stacking them all at one spot.

    `signer_rows` must be non-empty (callers should use render_contract_pdf
    instead for the single-signer/no-ContractSigner-rows case).
    """
    # NEW-617: the "Signed At" field below resolves to
    # MAX(signer.signed_at) ONLY once every row in `signer_rows` has
    # signed -- same "all_signed" gate sign_contract itself uses to flip
    # contracts.status to 'signed' (see crm_service.py's sign_contract),
    # and the same rule CRMService._resolve_signed_at_value applies for a
    # fully-signed contract (Contract.customer_signed_at is never written
    # once a contract has contract_signers rows, since the last required
    # signer to complete may not be the customer). This function is also
    # called on every regenerate-on-each-signature side effect for a
    # still-partially-signed contract (see this function's docstring
    # above) -- deliberately None in that case, not the latest partial
    # signer's own timestamp, so this legal document's "Signed At" field
    # can never show a date before every party has actually signed. No DB
    # access needed here: `signer_rows` already carries every signer's own
    # signed_at.
    resolved_signed_at = (
        max(s.signed_at for s in signer_rows)
        if signer_rows and all(s.signed_at for s in signer_rows)
        else None
    )
    anchors = []
    for i, signer in enumerate(signer_rows):
        y = _MULTI_SIGNER_Y_START - i * _MULTI_SIGNER_Y_STEP
        label = signer.anchor_label or signer.signer_name or signer.party_role.title()
        stamp_label = (
            f"Signed by {signer.signer_name or signer.party_role} on {signer.signed_at}"
            if signer.signed_at
            else ""
        )
        anchors.append(
            SignatureAnchor(
                party_role=signer.party_role,
                page=1,
                x=_MARGIN,
                y=y,
                label=label,
                signature_data=signer.signature_data,
                signer_label=stamp_label,
            )
        )

    spec = DocumentSpec(
        title=contract.title or f"Contract {contract.contract_number}",
        fields=[
            DocumentField("Contract Number", contract.contract_number or ""),
            DocumentField("Status", contract.status or ""),
            DocumentField("Signed At", resolved_signed_at or ""),
        ],
        body=contract.content or "",
        signature_anchors=anchors,
    )
    # Positional signature_data/signer_label are unused here -- every
    # anchor above carries its own via SignatureAnchor.signature_data/
    # signer_label, which render_pdf always prefers over these fallbacks.
    return render_pdf(spec, None, "")


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
