#!/usr/bin/env python3
"""Fetch all Pokemon (TCGdex) + MTG (Scryfall) sets released since 2024-05-15.

Saves:
  data/manifest.json       — combined set metadata
  data/pokemon/{id}.json   — per-set card data
  data/mtg/{code}.json     — per-set card data

Resumable: skips already-fetched per-set files.
"""
import json, os, sys, time, urllib.request, urllib.parse
import concurrent.futures
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data"
(DATA / "pokemon").mkdir(parents=True, exist_ok=True)
(DATA / "mtg").mkdir(parents=True, exist_ok=True)

CUTOFF = "2024-05-15"
UA = {
    "User-Agent": "CardTracker/1.0 (https://yoshizenco.github.io/card-tracker)",
    "Accept": "application/json,*/*",
}

def get(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())

# ───────── POKEMON ──────────────────────────────────────────
def fetch_pokemon():
    print("[POKEMON] listing sets...")
    sets = get("https://api.tcgdex.net/v2/en/sets")
    # Fetch all set details in parallel to get releaseDate
    def detail(s):
        try: return get(f"https://api.tcgdex.net/v2/en/sets/{s['id']}", timeout=15)
        except Exception as e: return {"id": s['id'], "_err": str(e)}
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
        details = list(ex.map(detail, sets))
    recent = sorted(
        [s for s in details if s.get("releaseDate", "") >= CUTOFF],
        key=lambda s: s.get("releaseDate", ""),
        reverse=True
    )
    print(f"[POKEMON] {len(recent)} sets since {CUTOFF}")

    manifest = []
    for idx, s in enumerate(recent, 1):
        sid = s["id"]
        out = DATA / "pokemon" / f"{sid}.json"
        if out.exists():
            existing = json.load(out.open())
            # Use cached set metadata (may have logo_alt added by enrich_pokemon.py)
            merged_set = {**s, **existing.get("set", {})}
            manifest.append(meta_from_pkm(merged_set, existing["cards"]))
            print(f"  [{idx:>2}/{len(recent)}] {sid:>8} — cached ({len(existing['cards'])} cards)")
            continue

        card_ids = [c["id"] for c in s.get("cards", [])]
        if not card_ids:
            continue
        t0 = time.time()

        def fetch_card(cid):
            for _ in range(3):
                try: return get(f"https://api.tcgdex.net/v2/en/cards/{cid}", timeout=15)
                except Exception: time.sleep(0.5)
            return {"id": cid, "_err": "failed"}

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
            cards = list(ex.map(fetch_card, card_ids))

        # Slim down + sort
        slim = [slim_pkm(c) for c in cards if "_err" not in c]
        try: slim.sort(key=lambda c: int("".join(ch for ch in (c.get("localId") or "0") if ch.isdigit()) or 0))
        except: pass

        json.dump({
            "set": {
                "id": sid, "name": s.get("name"),
                "releaseDate": s.get("releaseDate"),
                "logo": s.get("logo"), "symbol": s.get("symbol"),
                "cardCount": s.get("cardCount"),
                "serie": s.get("serie"),
            },
            "cards": slim,
            "fetchedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }, out.open("w"))
        manifest.append(meta_from_pkm(s, slim))
        print(f"  [{idx:>2}/{len(recent)}] {sid:>8}  {len(slim):>4}c  {time.time()-t0:5.1f}s  {s.get('name')}")
    return manifest

def slim_pkm(c):
    pricing = c.get("pricing") or {}
    cm = pricing.get("cardmarket") if isinstance(pricing.get("cardmarket"), dict) else {}
    cm = cm or {}
    return {
        "id": c.get("id"), "localId": c.get("localId"), "name": c.get("name"),
        "image": c.get("image"),
        "rarity": c.get("rarity"), "category": c.get("category"),
        "illustrator": c.get("illustrator"),
        "variants": c.get("variants") or {},
        # Cardmarket fields — avg/low/trend track the "base" print (non-foil for cards with a normal print, the holo for cards with only a holo print).
        # avg-holo/low-holo/trend-holo track the holographic / reverse-holo variant when one exists.
        "cm_avg": cm.get("avg"), "cm_low": cm.get("low"), "cm_trend": cm.get("trend"),
        "cm_avg_holo": cm.get("avg-holo"), "cm_low_holo": cm.get("low-holo"), "cm_trend_holo": cm.get("trend-holo"),
    }

EUR_TO_USD = 1.08
PKM_VARIANT_ORDER = ["normal", "holo", "reverse", "firstEdition", "wPromo"]

def pkm_variant_count(c):
    v = c.get("variants") or {}
    return sum(1 for k in PKM_VARIANT_ORDER if v.get(k))

def pkm_variant_price_usd(c, variant):
    """USD price for a specific Pokemon variant.

    Precedence: per-variant TCGplayer USD (when pokemontcg.io covers the set) →
    TCGdex Cardmarket EUR→USD per variant.
    """
    # 1. Per-variant USD from pokemontcg.io (enrich_pokemon.py output)
    usd_prices = c.get("usd_prices") or {}
    PKMTCG_KEYS = {
        "normal": ["normal"],
        "holo": ["holofoil", "unlimitedHolofoil"],
        "reverse": ["reverseHolofoil"],
        "firstEdition": ["1stEditionHolofoil", "1stEditionNormal"],
        "wPromo": [],
    }
    for key in PKMTCG_KEYS.get(variant, []):
        if usd_prices.get(key) is not None:
            return float(usd_prices[key])

    # 2. TCGdex Cardmarket: avg = non-holo (= normal); avg-holo = holo variant (= reverse for low-rarity, or the only holo print)
    if variant in ("normal", "firstEdition", "wPromo"):
        if c.get("cm_avg") is not None: return c["cm_avg"] * EUR_TO_USD
    elif variant == "reverse":
        if c.get("cm_avg_holo") is not None: return c["cm_avg_holo"] * EUR_TO_USD
        # fall back to base price if no holo data
        if c.get("cm_avg") is not None: return c["cm_avg"] * EUR_TO_USD
    elif variant == "holo":
        # Cards with only a holo variant store the holo price in cm_avg, not cm_avg_holo
        v = c.get("variants") or {}
        if not v.get("normal") and not v.get("reverse"):
            if c.get("cm_avg") is not None: return c["cm_avg"] * EUR_TO_USD
        if c.get("cm_avg_holo") is not None: return c["cm_avg_holo"] * EUR_TO_USD
        if c.get("cm_avg") is not None: return c["cm_avg"] * EUR_TO_USD

    # 3. Last-resort fallback: legacy single price
    if c.get("usd_market") is not None: return c["usd_market"]
    return 0

def pkm_card_total_value(c):
    """Sum of every priced variant — master-set value for one card."""
    v = c.get("variants") or {}
    return sum(pkm_variant_price_usd(c, k) for k in PKM_VARIANT_ORDER if v.get(k))

def meta_from_pkm(s, cards):
    total_value = sum(pkm_card_total_value(c) for c in cards)
    variant_count = sum(pkm_variant_count(c) for c in cards)
    return {
        "game": "pokemon",
        "id": s["id"],
        "name": s.get("name"),
        "series": s.get("serie", {}).get("name") if isinstance(s.get("serie"), dict) else s.get("serie"),
        "releaseDate": s.get("releaseDate"),
        "cardCount": s.get("cardCount", {}).get("total") if isinstance(s.get("cardCount"), dict) else None,
        "loadedCount": len(cards),
        "variantCount": variant_count,
        "totalValue": round(total_value, 2),
        "logo": s.get("logo"),
        "logo_alt": s.get("logo_alt"),
        "symbol": s.get("symbol"),
        "file": f"data/pokemon/{s['id']}.json",
    }

# ───────── MTG ──────────────────────────────────────────────
def fetch_mtg():
    print("[MTG] listing sets...")
    sets_all = get("https://api.scryfall.com/sets")["data"]
    valid = {"expansion","core","masters","draft_innovation","commander","starter","funny"}
    recent = sorted(
        [s for s in sets_all if s.get("released_at","") >= CUTOFF
         and s.get("set_type") in valid and not s.get("digital") and s.get("card_count",0) > 0],
        key=lambda s: s.get("released_at",""), reverse=True
    )
    print(f"[MTG] {len(recent)} sets since {CUTOFF}")

    manifest = []
    for idx, s in enumerate(recent, 1):
        code = s["code"]
        out = DATA / "mtg" / f"{code}.json"
        if out.exists():
            existing = json.load(out.open())
            manifest.append(meta_from_mtg(s, existing["cards"]))
            print(f"  [{idx:>2}/{len(recent)}] {code:>6} — cached ({len(existing['cards'])} cards)")
            continue

        cards = []
        url = f"https://api.scryfall.com/cards/search?q=e%3A{urllib.parse.quote(code)}&unique=prints&order=set&include_extras=false"
        t0 = time.time()
        while url:
            try:
                page = get(url)
            except Exception as e:
                print(f"    error fetching {code}: {e}")
                break
            cards.extend(page.get("data", []))
            url = page.get("next_page") if page.get("has_more") else None
            time.sleep(0.1)  # Scryfall asks for 50-100ms between requests

        slim = [slim_mtg(c) for c in cards]
        json.dump({
            "set": {
                "code": code, "name": s.get("name"),
                "released_at": s.get("released_at"),
                "set_type": s.get("set_type"),
                "card_count": s.get("card_count"),
                "icon_svg_uri": s.get("icon_svg_uri"),
            },
            "cards": slim,
            "fetchedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }, out.open("w"))
        manifest.append(meta_from_mtg(s, slim))
        print(f"  [{idx:>2}/{len(recent)}] {code:>6}  {len(slim):>4}c  {time.time()-t0:5.1f}s  {s.get('name')}")
    return manifest

def slim_mtg(c):
    img = (c.get("image_uris") or {}).get("normal") if not c.get("card_faces") else None
    if not img and c.get("card_faces"):
        faces = c["card_faces"]
        if isinstance(faces, list) and faces:
            img = (faces[0].get("image_uris") or {}).get("normal")
    prices = c.get("prices") or {}
    def p(k):
        v = prices.get(k)
        try: return float(v) if v else None
        except: return None
    return {
        "id": c.get("id"),
        "collector_number": c.get("collector_number"),
        "name": c.get("name"),
        "image": img,
        "rarity": c.get("rarity"),
        "type_line": c.get("type_line"),
        "mana_cost": c.get("mana_cost"),
        "artist": c.get("artist"),
        "scryfall_uri": c.get("scryfall_uri"),
        "set_name": c.get("set_name"),
        "set_code": c.get("set"),
        "finishes": c.get("finishes") or [],
        "frame_effects": c.get("frame_effects") or [],
        "promo_types": c.get("promo_types") or [],
        "border_color": c.get("border_color"),
        "lang": c.get("lang"),
        "p_usd": p("usd"),
        "p_usd_foil": p("usd_foil"),
        "p_usd_etched": p("usd_etched"),
        "p_eur": p("eur"),
    }

def mtg_card_total_value(c):
    """Sum of every priced finish for a card — value of a complete master set entry.
    EUR nonfoil converts at 1.08 if USD missing. Foil/etched are USD-only on Scryfall.
    """
    total = 0
    finishes = c.get("finishes") or []
    if "nonfoil" in finishes:
        if c.get("p_usd") is not None:
            total += c["p_usd"]
        elif c.get("p_eur") is not None:
            total += c["p_eur"] * EUR_TO_USD
    if "foil" in finishes and c.get("p_usd_foil") is not None:
        total += c["p_usd_foil"]
    if "etched" in finishes and c.get("p_usd_etched") is not None:
        total += c["p_usd_etched"]
    return total

def meta_from_mtg(s, cards):
    total_value = sum(mtg_card_total_value(c) for c in cards)
    variant_count = sum(len(c.get("finishes") or []) for c in cards)
    return {
        "game": "mtg",
        "id": s["code"],
        "name": s.get("name"),
        "series": s.get("set_type"),
        "releaseDate": s.get("released_at"),
        "cardCount": s.get("card_count"),
        "loadedCount": len(cards),
        "variantCount": variant_count,
        "totalValue": round(total_value, 2),
        "logo": s.get("icon_svg_uri"),
        "symbol": s.get("icon_svg_uri"),
        "file": f"data/mtg/{s['code']}.json",
    }

if __name__ == "__main__":
    games = sys.argv[1:] if len(sys.argv) > 1 else ["pokemon", "mtg"]
    manifest = []
    if "pokemon" in games:
        manifest.extend(fetch_pokemon())
    if "mtg" in games:
        manifest.extend(fetch_mtg())

    # Merge with existing manifest if partial run
    mfp = DATA / "manifest.json"
    if mfp.exists() and len(games) < 2:
        existing = json.load(mfp.open())
        ids_new = {(m["game"], m["id"]) for m in manifest}
        for m in existing.get("sets", []):
            if (m["game"], m["id"]) not in ids_new:
                manifest.append(m)

    # Sort manifest by date desc
    manifest.sort(key=lambda m: (m["game"], -ord(m["releaseDate"][0]) if m.get("releaseDate") else 0, m.get("releaseDate","")), reverse=False)
    # Actually just sort by date desc within each game
    manifest.sort(key=lambda m: (m["game"], m.get("releaseDate","")), reverse=True)

    json.dump({"sets": manifest, "fetchedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
              mfp.open("w"), indent=1)
    print(f"\nWrote {mfp} ({len(manifest)} sets)")
