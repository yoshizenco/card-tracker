#!/usr/bin/env python3
"""Copy template.html to index.html, substituting the worker backend URL.

After the Cloudflare worker is deployed, paste its URL on a single line in
`backend-url.txt`. If the file is missing the app falls back to device-only
storage (still functional, just not cross-device synced).
"""
import shutil, pathlib

ROOT = pathlib.Path(__file__).parent
template = (ROOT / "template.html").read_text()

backend_url = ""
cfg = ROOT / "backend-url.txt"
if cfg.exists():
    backend_url = cfg.read_text().strip()

if backend_url:
    template = template.replace("__BACKEND_URL__", backend_url)
    print(f"Wrote index.html (backend: {backend_url})")
else:
    print("Wrote index.html (no backend configured — device-only storage)")

(ROOT / "index.html").write_text(template)
