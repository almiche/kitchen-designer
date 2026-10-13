"""Refresh the saved IKEA.ca snapshot. Planning stays on the file."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

from .catalog import _CATALOG_PATH

_SEARCH = "https://sik.search.blue.cdtapps.com/ca/en/search-result-page"
_DIMS = {
    "base_frame": ("width_in", "depth_in", "height_in"),
    "wall_frame": ("width_in", "depth_in", "height_in"),
    "corner_base_frame": ("width_in", "depth_in", "height_in"),
    "corner_wall_frame": ("width_in", "depth_in", "height_in"),
    "door": ("width_in", "height_in"),
    "corner_door": ("width_in", "height_in"),
    "cover_panel": ("width_in", "height_in"),
    "leg": ("height_in",),
    "suspension_rail": ("length_in",),
    "toe_kick": ("length_in", "height_in"),
    "worktop": ("length_in", "thickness_in"),
}


def item_digits(value: str) -> str:
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return digits.zfill(8)


def parse_inches(text: str) -> list[float]:
    """Read the imperial sizes IKEA prints in parentheses, such as 15x40 1/2."""
    if not text:
        return []
    match = re.search(r"\(([^)]*)\)", text)
    raw = match.group(1) if match else text
    raw = raw.replace('"', "").replace("″", "").strip()
    if not raw:
        return []
    values = []
    for part in re.split(r"\s*x\s*", raw):
        part = part.strip()
        found = re.fullmatch(r"(\d+)(?:\s+(\d+)/(\d+))?", part)
        if not found:
            return []
        value = float(found.group(1))
        if found.group(2):
            value += float(found.group(2)) / float(found.group(3))
        values.append(value)
    return values


def _whole(value: float) -> float:
    value = float(value)
    if abs(value - round(value)) < 0.001:
        return int(round(value))
    return round(value, 2)


def normalize_product(product: dict) -> dict:
    price = product.get("salesPrice") or {}
    numeral = price.get("numeral")
    if numeral is None and product.get("price_cad") is not None:
        numeral = product["price_cad"]
    return {
        "item_no": item_digits(product.get("itemNo") or product.get("item_no") or ""),
        "price_cad": None if numeral is None else float(numeral),
        "measure": product.get("itemMeasureReferenceText") or product.get("measure") or "",
        "name": product.get("name") or "",
        "type_name": product.get("typeName") or product.get("type_name") or "",
    }


def apply_live(row: dict, product: dict) -> tuple[list[str], list[str]]:
    """Update price. Report a size disagreement and keep the stored size."""
    live = normalize_product(product)
    price_changes = []
    notes = []
    if live["price_cad"] is not None and abs(live["price_cad"] - float(row["price_cad"])) > 0.001:
        previous = row["price_cad"]
        row["price_cad"] = _whole(live["price_cad"])
        price_changes.append(f"{row['article']} {previous} -> {row['price_cad']}")
    keys = _DIMS.get(row.get("role") or "")
    dims = parse_inches(live["measure"])
    if keys and len(dims) == len(keys):
        for key, value in zip(keys, dims):
            old = row.get(key)
            if old is not None and abs(float(old) - value) > 0.3:
                notes.append(f"{row['article']} {key} stays {old:g}; IKEA measure says {value:g}")
    return price_changes, notes


def _iter_products(payload: dict):
    main = ((payload.get("searchResultPage") or {}).get("products") or {}).get("main") or {}
    for hit in main.get("items") or []:
        product = hit.get("product")
        if not product:
            continue
        yield product
        variants = (product.get("gprDescription") or {}).get("variants") or []
        for variant in variants:
            yield variant


def fetch_product(article: str) -> dict | None:
    digits = item_digits(article)
    url = _SEARCH + "?q=" + urllib.parse.quote(digits) + "&size=8"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode())
    for product in _iter_products(payload):
        if item_digits(product.get("itemNo") or "") == digits:
            return normalize_product(product)
    return None


def rehydrate_catalog(path: Path | None = None, fetch=None, dry_run: bool = False, today: str | None = None) -> dict:
    """Refresh prices for known articles and stamp as_of. Does not add new articles."""
    if fetch is None and os.environ.get("KITCHEN_DESIGNER_OFFLINE") == "1":
        raise RuntimeError("KITCHEN_DESIGNER_OFFLINE=1, so the catalog was not refreshed from IKEA.ca.")
    target = path or _CATALOG_PATH
    raw = json.loads(target.read_text())
    live_fetch = fetch or fetch_product
    pause = fetch is None
    as_of = today or date.today().isoformat()
    updated: list[str] = []
    kept: list[str] = []
    missing: list[str] = []
    for index, row in enumerate(raw["articles"]):
        if pause and index:
            time.sleep(0.15)
        try:
            product = live_fetch(row["article"])
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            missing.append(f"{row['article']} ({exc.__class__.__name__})")
            continue
        if not product:
            missing.append(row["article"])
            continue
        price_changes, notes = apply_live(row, product)
        updated.extend(price_changes)
        kept.extend(notes)
    if len(missing) == len(raw["articles"]):
        raise RuntimeError("IKEA search returned none of the catalog articles. The saved file was not changed.")
    raw["as_of"] = as_of
    prefix = "Prices and article numbers were read from ikea.com/ca on "
    for index, note in enumerate(raw.get("notes") or []):
        if isinstance(note, str) and note.startswith(prefix):
            raw["notes"][index] = prefix + as_of + ". They change."
            break
    if not dry_run:
        target.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n")
    lines = [f"Catalog {as_of}. Checked {len(raw['articles'])} articles."]
    if dry_run:
        lines.append("Dry run. The file was not written.")
    if updated:
        lines.append("Price changes:")
        lines.extend(f"- {row}" for row in updated)
    else:
        lines.append("Prices unchanged.")
    if kept:
        lines.append("Stored sizes kept:")
        lines.extend(f"- {row}" for row in kept)
    if missing:
        lines.append("Not returned, previous price kept:")
        lines.extend(f"- {row}" for row in missing)
    return {
        "as_of": as_of,
        "checked": len(raw["articles"]),
        "updated": updated,
        "kept": kept,
        "missing": missing,
        "dry_run": dry_run,
        "path": str(target),
        "summary": "\n".join(lines),
    }
