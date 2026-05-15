#!/usr/bin/env python3
"""Copy template.html to index.html (data is now external in data/ folder)."""
import shutil, pathlib
ROOT = pathlib.Path(__file__).parent
shutil.copy(ROOT / "template.html", ROOT / "index.html")
print("Wrote index.html")
