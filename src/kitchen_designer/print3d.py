"""1:N STL export. Cabinets are a separate file so a print can leave them out."""

from __future__ import annotations

import struct
from pathlib import Path

from .gltf import world
from .labels import product_lines

_CABINET = {"base", "sink_base", "wall", "over_fridge", "filler", "wall_filler"}


def _aabb(frame, along, into, width, depth, y, height):
    x0, z0 = world(frame["origin"], frame["direction"], frame["inward"], along, into)
    x1, z1 = world(frame["origin"], frame["direction"], frame["inward"], along + width, into + depth)
    return (min(x0, x1), y, min(z0, z1), abs(x1 - x0), height, abs(z1 - z0))


def _box(x, y, z, sx, sy, sz) -> list[tuple]:
    if sx <= 0 or sy <= 0 or sz <= 0:
        return []
    x1, y1, z1 = x + sx, y + sy, z + sz
    faces = (
        ((0, -1, 0), (x, y, z1), (x1, y, z1), (x1, y, z), (x, y, z)),
        ((0, 1, 0), (x, y1, z), (x1, y1, z), (x1, y1, z1), (x, y1, z1)),
        ((0, 0, -1), (x1, y, z), (x, y, z), (x, y1, z), (x1, y1, z)),
        ((0, 0, 1), (x, y, z1), (x1, y, z1), (x1, y1, z1), (x, y1, z1)),
        ((-1, 0, 0), (x, y, z), (x, y, z1), (x, y1, z1), (x, y1, z)),
        ((1, 0, 0), (x1, y, z1), (x1, y, z), (x1, y1, z), (x1, y1, z1)),
    )
    tris = []
    for normal, a, b, c, d in faces:
        tris.append((normal, a, b, c))
        tris.append((normal, a, c, d))
    return tris


def _shell_boxes(frame, along, into, width, depth, y, height, thick):
    """Five slabs that meet at the edges. The front, at the room side, stays open."""
    if min(width, depth, height) <= thick * 2.4:
        return [_aabb(frame, along, into, width, depth, y, height)]
    inner_h = height - 2 * thick
    inner_w = width - 2 * thick
    slabs = [
        (along, into, width, depth, y, thick),
        (along, into, width, depth, y + height - thick, thick),
        (along, into, thick, depth, y + thick, inner_h),
        (along + width - thick, into, thick, depth, y + thick, inner_h),
        (along + thick, into, inner_w, thick, y + thick, inner_h),
    ]
    boxes = []
    for a, i, w, d, yy, h in slabs:
        boxes.append(_aabb(frame, a, i, w, d, yy, h))
    return boxes


def _inches_to_mm(box, scale: float, floor_mm: float) -> tuple:
    x, y, z, sx, sy, sz = box
    factor = 25.4 / scale
    return (
        x * factor,
        y * factor,
        z * factor,
        max(sx * factor, floor_mm),
        max(sy * factor, floor_mm),
        max(sz * factor, floor_mm),
    )


def collect_boxes(design: dict) -> dict[str, list]:
    """Inch-space boxes split into cabinets and everything else."""
    frames = {frame["id"]: frame for frame in design["frames"]}
    cabinets = []
    rest = []
    scale = float(design.get("preferences", {}).get("print_scale") or design.get("print_scale") or 20)
    thick = 1.6 * scale / 25.4
    for frame in design["frames"]:
        rest.append(_aabb(frame, 0, -4, frame["length_in"], 4, 0, design["room"]["ceiling_height_in"]))
    xs = []
    zs = []
    for frame in design["frames"]:
        for along in (0, frame["length_in"]):
            for into in (0, 24):
                x, z = world(frame["origin"], frame["direction"], frame["inward"], along, into)
                xs.append(x)
                zs.append(z)
    if xs:
        pad = 30
        rest.append((min(xs) - pad, -0.4, min(zs) - pad, max(xs) - min(xs) + pad * 2, 0.4, max(zs) - min(zs) + pad * 2))
    for item in design["items"]:
        frame = frames[item["wall_id"]]
        box = (
            frame,
            item["offset_in"],
            item.get("into_in", 0),
            item["width_in"],
            item.get("depth_in", 24),
            item.get("y_in", 0),
            item.get("height_in", 30),
        )
        if item["kind"] in _CABINET or item["kind"] == "corner":
            cabinets.extend(_shell_boxes(*box, thick))
        else:
            rest.append(_aabb(*box))
    for corner in design["corners"]:
        for wall_id, end in corner["ends"].items():
            frame = frames[wall_id]
            offset = 0 if end == "start" else frame["length_in"] - corner["span_in"]
            cabinets.extend(_shell_boxes(
                frame, offset, 0, corner["span_in"], corner["depth_in"], corner["y_in"], corner["height_in"], thick,
            ))
    for piece in design["worktops"]:
        frame = frames[piece["wall_id"]]
        rest.append(_aabb(frame, piece["offset_in"], 0, piece["width_in"], piece["depth_in"], piece["y_in"], piece["height_in"]))
    for panel in design["panels"]:
        frame = frames[panel["wall_id"]]
        along = panel["offset_in"] - 0.75 if panel["side"] == "start" else panel["offset_in"]
        host = panel["host"]
        cabinets.append(_aabb(frame, along, 0, 0.75, host.get("depth_in", 24), 0, host.get("y_in", 4.5) + host.get("height_in", 30)))
    return {"cabinets": cabinets, "rest": rest, "scale": scale}


def _triangles(boxes, scale: float) -> list:
    tris = []
    for box in boxes:
        x, y, z, sx, sy, sz = _inches_to_mm(box, scale, 1.6)
        tris.extend(_box(x, y, z, sx, sy, sz))
    return tris


def write_stl(path: Path, triangles: list) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = b"kitchen-designer schematic print. See print/products.txt"
    header = header[:80].ljust(80, b"\0")
    out = bytearray(header)
    out += struct.pack("<I", len(triangles))
    for normal, a, b, c in triangles:
        out += struct.pack("<12fH", *normal, *a, *b, *c, 0)
    path.write_bytes(out)
    return {"path": str(path), "triangles": len(triangles), "bytes": len(out)}


def write_print_set(design: dict, folder: Path) -> dict:
    """Write the full kitchen, the cabinets alone, and the kitchen with cabinets removed."""
    parts = collect_boxes(design)
    scale = parts["scale"]
    cabinets = _triangles(parts["cabinets"], scale)
    rest = _triangles(parts["rest"], scale)
    folder = Path(folder)
    full = write_stl(folder / "kitchen.stl", cabinets + rest)
    cab = write_stl(folder / "print" / "cabinets.stl", cabinets)
    shell = write_stl(folder / "print" / "kitchen-without-cabinets.stl", rest)
    notes = folder / "print" / "products.txt"
    notes.parent.mkdir(parents=True, exist_ok=True)
    notes.write_text("\n".join(product_lines(design)) + "\n")
    return {
        "stl": full["path"],
        "cabinets": cab["path"],
        "without_cabinets": shell["path"],
        "scale": scale,
        "triangles": full["triangles"],
    }
