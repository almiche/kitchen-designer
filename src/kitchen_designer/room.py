from __future__ import annotations

from .catalog import front_ids
from .colors import attach_colors

SHAPES = {
    "straight": 1,
    "L": 2,
    "U": 3,
    "galley": 2,
}


def normalize_room(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("room must be an object")
    shape = payload.get("shape", "straight")
    if shape not in SHAPES:
        raise ValueError("shape must be straight, L, U, or galley")
    walls_in = payload.get("walls")
    if not isinstance(walls_in, list) or len(walls_in) != SHAPES[shape]:
        raise ValueError(f"{shape} needs {SHAPES[shape]} wall(s)")
    walls = []
    for index, wall in enumerate(walls_in):
        if not isinstance(wall, dict):
            raise ValueError("each wall must be an object")
        length = float(wall.get("length_in") or wall.get("length") or 0)
        if length < 24:
            raise ValueError("each wall needs a length_in of at least 24 inches")
        wall_id = str(wall.get("id") or f"wall-{index + 1}")
        openings = []
        for opening in wall.get("openings") or []:
            kind = opening.get("kind")
            if kind not in ("window", "door"):
                raise ValueError("opening kind must be window or door")
            offset = float(opening.get("offset_in") or opening.get("offset") or 0)
            width = float(opening.get("width_in") or opening.get("width") or 0)
            if width <= 0 or offset < 0 or offset + width > length + 0.1:
                raise ValueError(f"opening on {wall_id} falls outside the wall")
            openings.append({
                "kind": kind,
                "offset_in": offset,
                "width_in": width,
                "sill_in": float(opening.get("sill_in") or 0),
                "height_in": float(opening.get("height_in") or (80 if kind == "door" else 36)),
            })
        walls.append({"id": wall_id, "length_in": length, "openings": openings})
    ceiling = float(payload.get("ceiling_height_in") or 96)
    if ceiling < 78:
        raise ValueError("ceiling_height_in looks too low for a SEKTION kitchen")
    room = {
        "name": str(payload.get("name") or "Kitchen"),
        "shape": shape,
        "units": "in",
        "ceiling_height_in": ceiling,
        "walls": walls,
        "photo_observations": str(payload.get("photo_observations") or ""),
        "notes": str(payload.get("notes") or ""),
    }
    if shape == "galley":
        room["room_depth_in"] = float(payload.get("room_depth_in") or 120)
    elif payload.get("room_depth_in"):
        room["room_depth_in"] = float(payload["room_depth_in"])
    warning = attach_colors(room, payload)
    if warning:
        room["color_warning"] = warning
    return room


def normalize_preferences(payload: dict | None) -> dict:
    raw = payload or {}
    height = int(raw.get("wall_height_in") or 30)
    if height not in (20, 30, 40):
        raise ValueError("wall_height_in must be 20, 30, or 40")
    style = raw.get("fridge_style") or "french-door"
    if style not in ("french-door", "top-freezer"):
        raise ValueError("fridge_style must be french-door or top-freezer")
    fridge_width = raw.get("fridge_width_in")
    if fridge_width is not None and fridge_width != "":
        fridge_width = int(fridge_width)
    else:
        fridge_width = None
    range_width = int(raw.get("range_width_in") or 30)
    if range_width not in (28, 30, 36):
        raise ValueError("range_width_in must be 28, 30, or 36")
    finish = raw.get("finish") or "stainless"
    if finish not in ("stainless", "white", "black"):
        raise ValueError("finish must be stainless, white, or black")
    vent = raw.get("vent") or "hood"
    if vent not in ("hood", "otr", "none"):
        raise ValueError("vent must be hood, otr, or none")
    faucet = raw.get("faucet") or "pull-down"
    if faucet not in ("pull-down", "bridge", "single", "none"):
        raise ValueError("faucet must be pull-down, bridge, single, or none")
    microwave = raw.get("microwave") or "auto"
    if microwave not in ("auto", "counter", "none"):
        raise ValueError("microwave must be auto, counter, or none")
    scale = int(raw.get("print_scale") or 20)
    if scale < 8 or scale > 40:
        raise ValueError("print_scale must be from 8 to 40")
    front = raw.get("front_style") or "axstad-white"
    choices = front_ids()
    if front not in choices:
        raise ValueError("front_style must be one of: " + ", ".join(choices))
    return {
        "wall_height_in": height,
        "fridge": bool(raw.get("fridge", True)),
        "range": bool(raw.get("range", True)),
        "sink": bool(raw.get("sink", True)),
        "dishwasher": bool(raw.get("dishwasher", True)),
        "appliance_wall": raw.get("appliance_wall") or None,
        "front_style": front,
        "fridge_style": style,
        "fridge_width_in": fridge_width,
        "range_width_in": range_width,
        "finish": finish,
        "vent": vent,
        "faucet": faucet,
        "microwave": microwave,
        "print_scale": scale,
    }
