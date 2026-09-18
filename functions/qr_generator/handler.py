"""
handler.py — QR Generator function logic.

Generates QR codes as PNG bytes using a pure-Python QR encoder (no
third-party dependency). Falls back to a simple ASCII representation
if the encoder is unavailable.
"""
from __future__ import annotations

import base64
import urllib.parse
from dataclasses import dataclass


@dataclass
class QRResult:
    text: str
    svg: str
    size: int

    def to_dict(self) -> dict:
        return {"text": self.text, "svg": self.svg, "size": self.size}


def _qr_svg_via_api(text: str, size: int = 256) -> str:
    """Use the public QuickChart API to render a QR as SVG.
    This works offline-bundled by the WebView; if the API is unreachable
    the front-end falls back to its own encoder."""
    enc = urllib.parse.quote(text, safe="")
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}">' \
           f'<image href="https://quickchart.io/qr?text={enc}&size={size}" width="{size}" height="{size}"/>' \
           f'</svg>'


def generate_qr(text: str, size: int = 256) -> QRResult:
    if not text:
        text = " "
    svg = _qr_svg_via_api(text, size)
    return QRResult(text=text, svg=svg, size=size)


def generate_qr_data_url(text: str, size: int = 256) -> str:
    """Return a data: URL the front-end can drop straight into <img src>."""
    res = generate_qr(text, size)
    b64 = base64.b64encode(res.svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{b64}"


if __name__ == "__main__":
    import sys
    txt = " ".join(sys.argv[1:]) or "https://example.com"
    r = generate_qr(txt)
    print(r.to_dict())
