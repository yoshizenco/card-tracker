#!/usr/bin/env python3
"""Enrich Pokemon set data with USD prices from pokemontcg.io.

For sets pokemontcg.io covers (13/31), fetches TCGplayer USD market prices
and writes `usd_market` per card. Sets it doesn't cover keep cm_avg (EUR)
which is converted at display time.
"""
import json, os, sys, urllib.request, urllib.parse, concurrent.futures
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data" / "pokemon"

UA = {
    "User-Agent": "CardTracker/1.0 (https://yoshizenco.github.io/card-tracker)",
    "Accept": "application/json",
}

def get(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())

# Map TCGdex set name → likely pokemontcg.io set id (we'll resolve by name below)
def pkmtcg_id_for_name(name):
    """Find pokemontcg.io set ID for a given TCGdex set name."""
    return PKMTCG_BY_NAME.get(name.lower())

def market_usd(prices_obj):
    """Pick the highest-variant TCGplayer market USD from a card."""
    if not prices_obj: return None
    # Prefer holofoil > normal > others
    for v in ("holofoil","normal","reverseHolofoil","1stEditionHolofoil","1stEditionNormal","unlimitedHolofoil"):
        if prices_obj.get(v, {}).get("market") is not None:
            return prices_obj[v]["market"]
    # Fallback: any variant's market
    for v, p in prices_obj.items():
        if p.get("market") is not None: return p["market"]
    return None

print("Listing pokemontcg.io sets…")
all_sets = get("https://api.pokemontcg.io/v2/sets?pageSize=250")["data"]
PKMTCG_BY_NAME = { s["name"].lower(): s for s in all_sets }

local_files = sorted(DATA.glob("*.json"))
print(f"Local pokemon sets: {len(local_files)}\n")

enriched_sets = []
unmatched = []

for f in local_files:
    d = json.load(f.open())
    name = d["set"]["name"]
    match = PKMTCG_BY_NAME.get(name.lower())
    if not match:
        unmatched.append((f.stem, name))
        continue

    pid = match["id"]
    print(f"  [{f.stem:>8} ↔ {pid:>10}] {name}")

    # Fetch all cards for this pokemontcg.io set (only need id/number/tcgplayer/images)
    sel = urllib.parse.quote("id,number,name,tcgplayer,images")
    cards_pkmtcg = []
    page = 1
    while True:
        r = get(f"https://api.pokemontcg.io/v2/cards?q=set.id:{pid}&pageSize=250&page={page}&select={sel}")
        cards_pkmtcg.extend(r["data"])
        if len(r["data"]) < 250: break
        page += 1

    # Build {collector_number → market_usd, image_url} lookup
    by_num = {}
    for c in cards_pkmtcg:
        num = str(c.get("number","")).strip()
        usd = market_usd((c.get("tcgplayer") or {}).get("prices"))
        img_small = (c.get("images") or {}).get("small")
        by_num[num] = {"usd": usd, "image_small": img_small}

    enriched_count = 0
    img_filled = 0
    for card in d["cards"]:
        num = str(card.get("localId","")).strip().lstrip("0") or "0"
        # try with leading zeros stripped, and with the raw localId
        match_p = by_num.get(num) or by_num.get(card.get("localId",""))
        if not match_p: continue
        if match_p["usd"] is not None:
            card["usd_market"] = match_p["usd"]
            enriched_count += 1
        if not card.get("image") and match_p.get("image_small"):
            # Save pokemontcg.io image URL as alt
            card["image_alt"] = match_p["image_small"]
            img_filled += 1

    # Update set logo if it was missing
    pkmtcg_logo = (match.get("images") or {}).get("logo")
    if not d["set"].get("logo") and pkmtcg_logo:
        d["set"]["logo_alt"] = pkmtcg_logo

    json.dump(d, f.open("w"))
    enriched_sets.append((f.stem, name, enriched_count, len(d["cards"]), img_filled))

print(f"\n{'set':>8}  {'name':<35}  prices_usd  img_filled")
for sid, name, n, total, im in enriched_sets:
    print(f"  {sid:>8}  {name:<35}     {n:>3}/{total:<3}     {im:>3}")
print(f"\nUnmatched (will use EUR→USD conversion):")
for sid, name in unmatched:
    print(f"  {sid:>8}  {name}")
