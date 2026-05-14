#!/usr/bin/env python3
"""Build index.html with cards.json inlined."""
import json, pathlib, html

ROOT = pathlib.Path(__file__).parent
cards_data = json.loads((ROOT / "cards.json").read_text())
template = (ROOT / "template.html").read_text()

# Inline data — escape </script> defensively.
data_str = json.dumps(cards_data, separators=(",", ":"))
data_str = data_str.replace("</", "<\\/")

out = template.replace("/*__DATA__*/", data_str)
(ROOT / "index.html").write_text(out)
print(f"Wrote index.html ({len(out):,} bytes)")
