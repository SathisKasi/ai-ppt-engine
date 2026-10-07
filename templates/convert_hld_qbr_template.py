"""
templates/convert_hld_qbr_template.py — One-time conversion: HLD QBR Template
PFv3.potx (PowerPoint Template content type) -> templates/hld_qbr_template.pptx
(standard Presentation content type), so python-pptx can load it directly.

No slide content is modified here — guidance-box/decorative-icon/highlight
stripping happens per-slide at build time in core/builders/hld_qbr_builder.py.
Run this again only if the source .potx is replaced with a newer export.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import zipfile

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(PROJECT_ROOT, "HLD QBR Template PFv3.potx")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hld_qbr_template.pptx")


def convert(src: str = SRC, out: str = OUT) -> str:
    tmpdir = tempfile.mkdtemp()
    with zipfile.ZipFile(src, "r") as z:
        z.extractall(tmpdir)

    ct_path = os.path.join(tmpdir, "[Content_Types].xml")
    with open(ct_path, "r", encoding="utf-8") as f:
        content = f.read()
    content = content.replace(
        "presentationml.template.main+xml",
        "presentationml.presentation.main+xml",
    )
    with open(ct_path, "w", encoding="utf-8") as f:
        f.write(content)

    if os.path.exists(out):
        os.remove(out)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(tmpdir):
            for file in files:
                full = os.path.join(root, file)
                rel = os.path.relpath(full, tmpdir)
                zf.write(full, rel)

    shutil.rmtree(tmpdir, ignore_errors=True)
    return out


if __name__ == "__main__":
    result = convert()
    print("HLD QBR working template written to:", result)
