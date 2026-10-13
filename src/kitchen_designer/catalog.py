from __future__ import annotations

import json
from pathlib import Path

_CATALOG_PATH = Path(__file__).resolve().parents[2] / "data" / "ca_sektion.json"


def load_catalog(path: Path | None = None) -> dict:
    raw = json.loads((path or _CATALOG_PATH).read_text())
    raw["by_article"] = {item["article"]: item for item in raw["articles"]}
    return raw


def article_url(article: str) -> str:
    return "https://www.ikea.com/ca/en/search/?q=" + article.replace(".", "")


def front_ids(catalog: dict | None = None) -> list[str]:
    data = catalog if catalog is not None else load_catalog()
    return [str(front["id"]) for front in data.get("fronts") or []]


def front_by_id(catalog: dict, style: str) -> dict | None:
    for front in catalog.get("fronts") or []:
        if front.get("id") == style:
            return front
    return None


def display_name(item: dict) -> str:
    name = item["name"]
    role = item.get("role")
    if role in ("base_frame", "wall_frame", "corner_base_frame", "corner_wall_frame", "door", "corner_door", "cover_panel"):
        width = item.get("width_in")
        height = item.get("height_in")
        depth = item.get("depth_in")
        if width and height and depth and role != "door":
            return f"{name}, {width:g}x{depth:g}x{height:g} in"
        if width and height:
            return f"{name}, {width:g}x{height:g} in"
    if role == "leg" and item.get("height_in"):
        return f"{name}, {item['height_in']:g} in"
    if item.get("length_in") and role in ("suspension_rail", "toe_kick", "worktop"):
        return f"{name}, {item['length_in']:g} in"
    return name


def find_articles(catalog: dict, role: str, **match: float) -> list[dict]:
    found = []
    for item in catalog["articles"]:
        if item["role"] != role:
            continue
        ok = True
        for key, expected in match.items():
            if key not in item or abs(float(item[key]) - float(expected)) > 0.2:
                ok = False
                break
        if ok:
            found.append(item)
    return found


def one(catalog: dict, role: str, **match: float) -> dict | None:
    rows = find_articles(catalog, role, **match)
    return rows[0] if rows else None


def widths(catalog: dict, role: str, height_in: float) -> list[int]:
    values = {
        int(item["width_in"])
        for item in catalog["articles"]
        if item["role"] == role and abs(float(item["height_in"]) - height_in) < 0.2
    }
    return sorted(values)


def hinge(catalog: dict, angle: int) -> dict:
    for item in catalog["articles"]:
        if item["role"] == "hinge" and int(item["angle"]) == angle:
            return item
    raise KeyError(angle)


def panel_rip_in(panel: dict, min_height: float) -> float:
    """Inches of filler strips one cover panel can yield at this height.

    Either published side can be the height. The other side is the rip.
    """
    width = float(panel["width_in"])
    height = float(panel["height_in"])
    best = 0.0
    if width + 0.05 >= min_height:
        best = max(best, height)
    if height + 0.05 >= min_height:
        best = max(best, width)
    return best


def side_cover(catalog: dict, depth_in: float, height_in: float) -> dict | None:
    """Cheapest cover panel that can face an exposed cabinet side whole."""
    best = None
    best_key = None
    for panel in catalog["articles"]:
        if panel.get("role") != "cover_panel":
            continue
        width = float(panel["width_in"])
        height = float(panel["height_in"])
        fits = (width + 0.05 >= depth_in and height + 0.05 >= height_in) or (
            height + 0.05 >= depth_in and width + 0.05 >= height_in
        )
        if not fits:
            continue
        key = (panel["price_cad"], width * height, panel["article"])
        if best_key is None or key < best_key:
            best = panel
            best_key = key
    return best
