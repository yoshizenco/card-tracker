#!/usr/bin/env python3
"""Copy template.html to index.html, substituting backend config.

Backend selection:
  1. If `gist-config.json` exists with { "gist_id": "...", "pat": "..." } → use GitHub Gist
  2. Else if `backend-url.txt` exists with a worker URL on line 1 → use Cloudflare Worker
  3. Else app runs in device-only mode (still functional, no cross-device sync)
"""
import json, shutil, pathlib

ROOT = pathlib.Path(__file__).parent
template = (ROOT / "template.html").read_text()

backend_url = ""
gist_id = ""
gist_pat = ""

gist_cfg = ROOT / "gist-config.json"
backend_cfg = ROOT / "backend-url.txt"

if gist_cfg.exists():
    cfg = json.loads(gist_cfg.read_text())
    gist_id = cfg.get("gist_id", "").strip()
    gist_pat = cfg.get("pat", "").strip()

if backend_cfg.exists():
    backend_url = backend_cfg.read_text().strip()

template = template.replace("__BACKEND_URL__", backend_url or "__BACKEND_URL__")
template = template.replace("__GIST_ID__", gist_id or "__GIST_ID__")
template = template.replace("__GIST_PAT__", gist_pat or "__GIST_PAT__")

if gist_id and gist_pat:
    print(f"Wrote index.html (GitHub Gist: {gist_id})")
elif backend_url:
    print(f"Wrote index.html (Cloudflare Worker: {backend_url})")
else:
    print("Wrote index.html (no backend configured — device-only storage)")

(ROOT / "index.html").write_text(template)
