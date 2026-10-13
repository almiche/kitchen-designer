"""Schematic appliance bodies. Dimensions follow published opening sizes."""

from __future__ import annotations

import json
from pathlib import Path

_PATH = Path(__file__).resolve().parents[2] / "data" / "appliances.json"

FINISH_RGB = {
    "stainless": (0.74, 0.75, 0.77),
    "white": (0.94, 0.94, 0.93),
    "black": (0.13, 0.13, 0.14),
}


def load_appliances() -> dict:
    return json.loads(_PATH.read_text())


def _models(role: str) -> list[dict]:
    return [item for item in load_appliances()["models"] if item["role"] == role]


def _finish(prefs: dict) -> str:
    finish = prefs.get("finish") or "stainless"
    if finish not in FINISH_RGB:
        raise ValueError("finish must be stainless, white, or black")
    return finish


def pick_fridge(prefs: dict) -> dict:
    style = prefs.get("fridge_style") or "french-door"
    if style not in ("french-door", "top-freezer"):
        raise ValueError("fridge_style must be french-door or top-freezer")
    width = prefs.get("fridge_width_in")
    if width is None:
        width = 36 if style == "french-door" else 30
    width = int(width)
    rows = [item for item in _models("fridge") if item["style"] == style and int(item["width_in"]) == width]
    if not rows:
        choices = ", ".join(f"{item['style']} {item['width_in']:g}" for item in _models("fridge"))
        raise ValueError(f"no {style} fridge at {width} inches. Choices: {choices}")
    return rows[0]


def pick_range(prefs: dict) -> dict:
    width = int(prefs.get("range_width_in") or 30)
    rows = [item for item in _models("range") if int(item["width_in"]) == width]
    if not rows:
        raise ValueError("range_width_in must be 28, 30, or 36")
    return rows[0]


def pick_role(role: str, **match) -> dict:
    for item in _models(role):
        if all(item.get(key) == value for key, value in match.items()):
            return item
    raise KeyError(role)


def sized_catalog(catalog: dict, prefs: dict) -> dict:
    """Copy the catalog constants so the chosen fridge and range widths drive the layout."""
    local = dict(catalog)
    const = dict(catalog["constants"])
    fridge = pick_fridge(prefs)
    stove = pick_range(prefs)
    const["fridge_width_in"] = fridge["width_in"]
    const["fridge_height_in"] = fridge["height_in"]
    const["fridge_depth_in"] = fridge["depth_in"]
    const["range_width_in"] = stove["width_in"]
    const["range_height_in"] = stove["height_in"]
    const["range_depth_in"] = stove["depth_in"]
    local["constants"] = const
    return local


def _tagged(model: dict, finish: str, **extra) -> dict:
    row = {
        "model_id": model["id"],
        "name": model["name"],
        "finish": finish,
        "finish_rgb": list(FINISH_RGB[finish]),
        "examples": model.get("examples") or "",
    }
    row.update(extra)
    return row


def stamp_and_place(items: list[dict], frames: list[dict], prefs: dict, const: dict, work_corners: list[dict]) -> tuple[list[dict], list[dict], list[str]]:
    """Label the fridge, range, and dishwasher, then add the hood, faucet, and microwave."""
    finish = _finish(prefs)
    fridge = pick_fridge(prefs)
    stove = pick_range(prefs)
    dishwasher = pick_role("dishwasher")
    notes: list[str] = []
    schedule: list[dict] = []

    def remember(model: dict, placed: bool) -> None:
        schedule.append({
            "id": model["id"],
            "role": model["role"],
            "name": model["name"],
            "finish": finish,
            "width_in": model["width_in"],
            "height_in": model["height_in"],
            "depth_in": model["depth_in"],
            "examples": model.get("examples") or "",
            "placed": placed,
        })

    for item in items:
        if item["kind"] == "fridge":
            item.update(_tagged(fridge, finish))
        elif item["kind"] == "range":
            item.update(_tagged(stove, finish))
        elif item["kind"] == "dishwasher":
            item.update(_tagged(dishwasher, finish))
    if any(item["kind"] == "fridge" for item in items):
        remember(fridge, True)
    elif prefs.get("fridge", True):
        remember(fridge, False)
    if any(item["kind"] == "range" for item in items):
        remember(stove, True)
    elif prefs.get("range", True):
        remember(stove, False)
    if any(item["kind"] == "dishwasher" for item in items):
        remember(dishwasher, True)
    elif prefs.get("dishwasher", True):
        remember(dishwasher, False)

    extras: list[dict] = []
    counter = const["leg_height_in"] + const["base_frame_height_in"] + const["counter_thickness_in"]
    vent = prefs.get("vent") or "hood"
    if vent not in ("hood", "otr", "none"):
        raise ValueError("vent must be hood, otr, or none")
    ranges = [item for item in items if item["kind"] == "range"]
    if ranges and vent == "hood":
        hood = min(_models("hood"), key=lambda row: abs(row["width_in"] - stove["width_in"]))
        host = ranges[0]
        extras.append({
            "kind": "hood",
            "wall_id": host["wall_id"],
            "offset_in": host["offset_in"],
            "width_in": host["width_in"],
            "depth_in": hood["depth_in"],
            "height_in": hood["height_in"],
            "y_in": counter + 22,
            "into_in": 0,
            **_tagged(hood, finish),
        })
        remember(hood, True)
    elif ranges and vent == "otr":
        micro = pick_role("microwave", mount="otr")
        host = ranges[0]
        width = min(micro["width_in"], host["width_in"])
        extras.append({
            "kind": "microwave",
            "mount": "otr",
            "wall_id": host["wall_id"],
            "offset_in": host["offset_in"] + (host["width_in"] - width) / 2,
            "width_in": width,
            "depth_in": micro["depth_in"],
            "height_in": micro["height_in"],
            "y_in": counter + 16,
            "into_in": 0,
            **_tagged(micro, finish),
        })
        remember(micro, True)

    faucet_style = prefs.get("faucet") or "pull-down"
    if faucet_style not in ("pull-down", "bridge", "single", "none"):
        raise ValueError("faucet must be pull-down, bridge, single, or none")
    sinks = [item for item in items if item["kind"] == "sink_base"]
    if sinks and faucet_style != "none":
        faucet = pick_role("faucet", style=faucet_style)
        host = sinks[0]
        extras.append({
            "kind": "faucet",
            "style": faucet_style,
            "wall_id": host["wall_id"],
            "offset_in": host["offset_in"] + host["width_in"] / 2 - faucet["width_in"] / 2,
            "width_in": faucet["width_in"],
            "depth_in": faucet["depth_in"],
            "height_in": faucet["height_in"],
            "y_in": counter,
            "into_in": 3,
            **_tagged(faucet, finish),
        })
        remember(faucet, True)
    elif faucet_style != "none" and prefs.get("sink", True):
        remember(pick_role("faucet", style=faucet_style), False)

    microwave_mode = prefs.get("microwave") or "auto"
    if microwave_mode not in ("auto", "counter", "none"):
        raise ValueError("microwave must be auto, counter, or none")
    if microwave_mode != "none" and vent != "otr":
        micro = pick_role("microwave", mount="counter")
        spot = _counter_spot(items, frames, work_corners, const, micro["width_in"])
        if spot is None:
            remember(micro, False)
            notes.append("Countertop microwave is on the appliance list. This run has no open counter long enough for it.")
        else:
            wall_id, offset = spot
            extras.append({
                "kind": "microwave",
                "mount": "counter",
                "wall_id": wall_id,
                "offset_in": offset,
                "width_in": micro["width_in"],
                "depth_in": micro["depth_in"],
                "height_in": micro["height_in"],
                "y_in": counter,
                "into_in": 4,
                **_tagged(micro, finish),
            })
            remember(micro, True)
    return extras, schedule, notes


def _counter_spot(items, frames, corners, const, need: float):
    from .solve import _absorb_fillers

    for frame in frames:
        spans = [
            (item["offset_in"], item["offset_in"] + item["width_in"])
            for item in items
            if item.get("wall_id") == frame["id"] and item["kind"] in ("base", "sink_base", "dishwasher")
        ]
        fillers = [
            (item["offset_in"], item["offset_in"] + item["width_in"])
            for item in items
            if item.get("wall_id") == frame["id"] and item["kind"] == "filler"
        ]
        for corner in corners:
            end = corner["ends"].get(frame["id"])
            if end == "start":
                spans.append((0.0, corner["span_in"]))
            elif end == "end":
                spans.append((frame["length_in"] - corner["span_in"], frame["length_in"]))
        blocked = [
            (item["offset_in"], item["offset_in"] + item["width_in"])
            for item in items
            if item.get("wall_id") == frame["id"] and item["kind"] in ("sink_base", "dishwasher", "range", "fridge")
        ]
        clear = _subtract(list(_absorb_fillers(spans, fillers)), blocked)
        for start, end in clear:
            if end - start >= need:
                return frame["id"], start
    return None


def _subtract(spans, holes):
    from .solve import subtract

    rows = [(row[0], row[1]) for row in spans]
    return subtract(rows, holes)
