"""First-person stills and a browser walkthrough at a 62 inch eye height."""

from __future__ import annotations

import array
import json
import math
import struct
import zlib
from pathlib import Path

from .gltf import INCH, world
from .labels import callouts, dimension_lines, paint_dimensions, paint_labels, product_lines, still_legend

EYE_IN = 62.0
HFOV = math.radians(70)
STILL_WIDTH = 512
STILL_HEIGHT = 288

_SURFACES = ("paint", "marble", "metal", "tile", "wood", "gloss", "flat")

# Same order as the GLB materials.
_FALLBACK = (
    (0.93, 0.93, 0.91),
    (0.97, 0.97, 0.96),
    (0.86, 0.86, 0.84),
    (0.42, 0.44, 0.47),
    (0.78, 0.78, 0.76),
    (0.88, 0.87, 0.84),
    (0.55, 0.52, 0.48),
    (0.90, 0.90, 0.88),
)

# Box corners, then the six faces as corner indexes and an outward normal.
_CORNERS = (
    (0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
    (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1),
)
_FACE_INDEX = (
    ((4, 5, 6, 7), (0, 0, 1)),
    ((1, 0, 3, 2), (0, 0, -1)),
    ((3, 2, 6, 7), (0, 1, 0)),
    ((0, 1, 5, 4), (0, -1, 0)),
    ((1, 2, 6, 5), (1, 0, 0)),
    ((4, 0, 3, 7), (-1, 0, 0)),
)


def _yaw_toward(dx: float, dz: float) -> float:
    """Yaw whose forward vector is (dx, dz). Yaw 0 looks toward -Z."""
    return math.atan2(dx, -dz)


def _unit(x: float, y: float, z: float) -> tuple[float, float, float]:
    length = math.sqrt(x * x + y * y + z * z) or 1.0
    return x / length, y / length, z / length


def _shade(color, normal, metal: float = 0.0, rough: float = 0.85, view=(0.0, 0.0, 1.0), surface: str = "") -> tuple[int, int, int]:
    """Key light, a fill, and a little sky. Sheen stays off matte paint."""
    key = _unit(0.35, 0.92, 0.42)
    fill = _unit(-0.55, 0.35, 0.25)
    key_facing = max(0.0, normal[0] * key[0] + normal[1] * key[1] + normal[2] * key[2])
    fill_facing = max(0.0, normal[0] * fill[0] + normal[1] * fill[1] + normal[2] * fill[2])
    sky = max(0.0, normal[1]) * 0.07
    gain = 0.34 + 0.62 * key_facing + 0.16 * fill_facing + sky
    rgb = [channel * gain for channel in color]
    if metal > 0.15 or rough < 0.45:
        vx, vy, vz = view
        vlen = math.sqrt(vx * vx + vy * vy + vz * vz) or 1.0
        vx, vy, vz = vx / vlen, vy / vlen, vz / vlen
        hx, hy, hz = key[0] + vx, key[1] + vy, key[2] + vz
        hlen = math.sqrt(hx * hx + hy * hy + hz * hz) or 1.0
        spec = max(0.0, (normal[0] * hx + normal[1] * hy + normal[2] * hz) / hlen)
        shine = 10.0 + (1.0 - rough) * 70.0
        amount = (spec ** shine) * (0.2 + 0.8 * metal) * (1.0 - min(rough, 0.95))
        rgb = [min(1.0, channel + amount) for channel in rgb]
        if surface == "gloss" or rough < 0.2:
            power, broad = 4.0, 0.42
        elif surface == "metal":
            power, broad = 6.0, 0.35
        elif surface in ("marble", "tile"):
            power, broad = 7.0, 0.26
        else:
            power, broad = 0.0, 0.0
        if broad:
            soft = spec ** power
            rgb = [min(1.0, channel + soft * broad) for channel in rgb]
        if surface in ("gloss", "marble", "metal", "tile") or rough < 0.22:
            facing_eye = max(0.0, normal[0] * vx + normal[1] * vy + normal[2] * vz)
            fres = (1.0 - facing_eye) ** 0.65
            lift = fres * (0.22 + 0.45 * metal) * (1.2 - rough)
            rgb = [min(1.0, channel + lift) for channel in rgb]
    return tuple(max(0, min(255, int(channel * 255 + 0.5))) for channel in rgb)


def boxes_from_nodes(nodes: list[dict]) -> list[dict]:
    """Inch-space boxes. Node translation is the minimum corner, in meters."""
    boxes = []
    for node in nodes:
        tx, ty, tz = node["translation"]
        sx, sy, sz = node["scale"]
        if sx <= 0 or sy <= 0 or sz <= 0:
            continue
        color = node.get("color")
        if not color:
            material = int(node.get("material") or 0)
            color = _FALLBACK[material if 0 <= material < len(_FALLBACK) else 0]
        box = {
            "name": node.get("name") or "box",
            "x": tx / INCH,
            "y": ty / INCH,
            "z": tz / INCH,
            "sx": sx / INCH,
            "sy": sy / INCH,
            "sz": sz / INCH,
            "color": [float(channel) for channel in list(color)[:3]],
            "metal": float(node.get("metallic") or 0.0),
            "rough": float(node["roughness"]) if node.get("roughness") is not None else 0.85,
        }
        if node.get("surface") in _SURFACES:
            box["surface"] = node["surface"]
        boxes.append(box)
    return boxes


def _room_color(room: dict, key: str, fallback: tuple[float, float, float]) -> tuple[float, float, float]:
    value = (room.get("colors") or {}).get(key)
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        return (float(value[0]), float(value[1]), float(value[2]))
    return fallback


def _add_ceiling(boxes: list[dict], room: dict) -> None:
    floor = next((box for box in boxes if box["name"] == "floor"), None)
    if floor is None:
        return
    wall = _room_color(room, "wall", (0.90, 0.90, 0.88))
    boxes.append({
        "name": "ceiling",
        "x": floor["x"],
        "y": float(room.get("ceiling_height_in") or 96),
        "z": floor["z"],
        "sx": floor["sx"],
        "sy": 0.6,
        "sz": floor["sz"],
        "color": [min(1.0, channel + 0.04) for channel in wall],
    })


def _occupied(x: float, z: float, boxes: list[dict]) -> bool:
    for box in boxes:
        if box["name"] in ("floor", "ceiling") or box["sy"] < 8:
            continue
        if box["y"] > EYE_IN or box["y"] + box["sy"] < 18:
            continue
        if box["x"] <= x <= box["x"] + box["sx"] and box["z"] <= z <= box["z"] + box["sz"]:
            return True
    return False


def _clear_spot(eye: list[float], boxes: list[dict], inward: tuple[float, float]) -> list[float]:
    ix, iz = inward
    spot = [eye[0], eye[1], eye[2]]
    for _step in range(30):
        if not _occupied(spot[0], spot[2], boxes):
            return spot
        spot[0] += ix * 6
        spot[2] += iz * 6
    return spot


def _stand(frame: dict, along: float, into: float) -> list[float]:
    x, z = world(frame["origin"], frame["direction"], frame["inward"], along, into)
    return [x, EYE_IN, z]


def _look_at(eye: list[float], target: list[float]) -> tuple[float, float]:
    """Yaw and pitch that point the eye at target. Yaw 0 looks toward -Z."""
    dx = target[0] - eye[0]
    dy = target[1] - eye[1]
    dz = target[2] - eye[2]
    flat = math.hypot(dx, dz)
    return _yaw_toward(dx, dz), math.atan2(dy, flat if flat > 1e-6 else 1.0)


def _max_clear_into(frame: dict, boxes: list[dict], along: float) -> float:
    """Inches inward from the wall before another cabinet blocks the aisle."""
    origin = frame["origin"]
    direction = frame["direction"]
    inward = frame["inward"]
    into = 36.0
    x, z = world(origin, direction, inward, along, into)
    if _occupied(x, z, boxes):
        while into > 18:
            x, z = world(origin, direction, inward, along, into)
            if not _occupied(x, z, boxes):
                break
            into -= 4
        return into
    while into < 420:
        nxt = into + 6
        x, z = world(origin, direction, inward, along, nxt)
        if _occupied(x, z, boxes):
            return into
        into = nxt
    return into


def _facing_into(frame: dict, boxes: list[dict], along: float, length: float) -> float:
    """Stand far enough back to fit the run, and stay in the open aisle."""
    ideal = 24.0 + (length * 0.5 + 18.0) / math.tan(HFOV / 2)
    clear = _max_clear_into(frame, boxes, along)
    stand = min(ideal, clear - 16.0)
    if stand < 40:
        stand = max(32.0, min(clear - 6.0, ideal))
    return stand


def _open_floor(boxes: list[dict], design: dict) -> None:
    """Extend the walk floor inward so the camera can stand back and see the run.

    The GLB and the STL keep the short pad. This slab is only for the walkthrough.
    """
    floor = next((box for box in boxes if box["name"] == "floor"), None)
    frames = design.get("frames") or []
    if floor is None or not frames:
        return
    xs = [floor["x"], floor["x"] + floor["sx"]]
    zs = [floor["z"], floor["z"] + floor["sz"]]
    for frame in frames:
        length = float(frame["length_in"])
        stand = _facing_into(frame, boxes, length / 2, length)
        far = stand + 48.0
        for along in (-36.0, 0.0, length, length + 36.0):
            for into in (0.0, far):
                x, z = world(frame["origin"], frame["direction"], frame["inward"], along, into)
                xs.append(x)
                zs.append(z)
    floor["x"] = min(xs)
    floor["z"] = min(zs)
    floor["sx"] = max(xs) - floor["x"]
    floor["sz"] = max(zs) - floor["z"]


def _pin_ground(boxes: list[dict]) -> None:
    """Replace the single floor slab with world-locked planks.

    One big quad clips against the near plane, and that clipped edge stays
    glued to the camera. Planks are separate boxes on a fixed inch grid, so
    the ground stays put while the camera moves. They stay plain so the walk
    does not subdivide them.
    """
    floor = next((box for box in boxes if box["name"] == "floor"), None)
    if floor is None:
        return
    origin_x, origin_z = floor["x"], floor["z"]
    origin_sx, origin_sz = floor["sx"], floor["sz"]
    margin = 240.0
    floor["x"] -= margin
    floor["z"] -= margin
    floor["sx"] += margin * 2
    floor["sz"] += margin * 2
    floor["skip"] = True
    color = floor.get("color") or [0.55, 0.52, 0.48]
    length = 120.0
    board = 8.0
    seam_w = 0.45
    pad = 36.0
    footprints = []
    for box in boxes:
        name = box.get("name") or ""
        if name in ("floor", "ceiling") or name.startswith(("shell", "surround", "measure")):
            continue
        if "-door" in name or "-panel" in name or "-pull" in name or "-knob" in name or "-gap" in name or "-toe" in name or "-under" in name:
            continue
        if box.get("y", 0) > 8 or box.get("sy", 0) < 12:
            continue
        footprints.append((box["x"], box["z"], box["x"] + box["sx"], box["z"] + box["sz"]))
    x_start = math.floor((origin_x - pad) / length) * length
    z_start = math.floor((origin_z - pad) / board) * board
    end_x = origin_x + origin_sx + pad
    end_z = origin_z + origin_sz + pad
    groove = [min(1.0, channel * 0.4) for channel in color]
    z = z_start
    row = 0
    while z < end_z - 0.1:
        tone = 0.88 if row % 2 else 1.0
        if row % 4 == 0:
            tone *= 0.95
        x = x_start
        while x < end_x - 0.1:
            boxes.append({
                "name": "floor-tile",
                "x": x,
                "y": 0.0,
                "z": z,
                "sx": length,
                "sy": 0.2,
                "sz": board,
                "color": [min(1.0, channel * tone) for channel in color],
                "metal": 0.1,
                "rough": 0.28,
                "surface": "tile",
                "top": True,
                "plain": True,
            })
            boxes.append({
                "name": "floor-tile",
                "x": x,
                "y": 0.05,
                "z": z + board - seam_w,
                "sx": length,
                "sy": 0.18,
                "sz": seam_w,
                "color": groove,
                "metal": 0.02,
                "rough": 0.6,
                "surface": "paint",
                "top": True,
                "plain": True,
            })
            x += length
        z += board
        row += 1
    for index, (left, near, right, far) in enumerate(footprints):
        expand = 10.0
        boxes.append({
            "name": "floor-tile",
            "x": left - expand,
            "y": 0.24 + (index % 4) * 0.01,
            "z": near - expand,
            "sx": (right - left) + expand * 2,
            "sy": 0.05,
            "sz": (far - near) + expand * 2,
            "color": [min(1.0, channel * 0.72) for channel in color],
            "metal": 0.02,
            "rough": 0.7,
            "surface": "paint",
            "top": True,
            "plain": True,
        })


def _frame_point(frame: dict, along: float, into: float, y: float) -> list[float]:
    x, z = world(frame["origin"], frame["direction"], frame["inward"], along, into)
    return [x, y, z]


def shot_list(design: dict, boxes: list[dict]) -> list[dict]:
    """Three standing views: the whole run, down the run, and at the sink or range."""
    frames = design.get("frames") or []
    if not frames:
        return [{
            "name": "facing",
            "label": "Standing in the kitchen",
            "eye": [0.0, EYE_IN, 72.0],
            "yaw": 0.0,
            "pitch": -0.12,
        }]
    host = max(frames, key=lambda frame: frame["length_in"])
    inward = (float(host["inward"][0]), float(host["inward"][1]))
    length = float(host["length_in"])
    mid = length / 2
    stand_into = _facing_into(host, boxes, mid, length)
    facing_eye = _clear_spot(_stand(host, mid, stand_into), boxes, inward)
    facing_yaw, facing_pitch = _look_at(facing_eye, _frame_point(host, mid, 12.0, 46.0))
    start_along = min(36.0, length * 0.22)
    aisle = min(stand_into, 70.0)
    along_eye = _clear_spot(_stand(host, start_along, aisle), boxes, inward)
    aim_along = min(length - 8.0, start_along + max(48.0, length * 0.55))
    along_yaw, along_pitch = _look_at(along_eye, _frame_point(host, aim_along, 12.0, 42.0))
    shots = [
        {
            "name": "facing",
            "label": "Standing in front of the run, looking at the cabinets",
            "eye": facing_eye,
            "yaw": facing_yaw,
            "pitch": facing_pitch,
        },
        {
            "name": "along",
            "label": "Looking down the run",
            "eye": along_eye,
            "yaw": along_yaw,
            "pitch": along_pitch,
        },
    ]
    target = next((item for item in design.get("items") or [] if item["kind"] == "sink_base"), None)
    kind = "sink"
    label = "At the sink"
    if target is None:
        target = next((item for item in design.get("items") or [] if item["kind"] == "range"), None)
        kind = "range"
        label = "At the range"
    if target is None:
        detail = dict(shots[0])
        detail["name"] = "detail"
        detail["label"] = "At the counter"
        shots.append(detail)
        return shots
    frame = next(row for row in frames if row["id"] == target["wall_id"])
    frame_in = (float(frame["inward"][0]), float(frame["inward"][1]))
    at = float(target["offset_in"]) + float(target["width_in"]) / 2
    detail_into = min(64.0, _facing_into(frame, boxes, at, float(frame["length_in"])))
    eye = _clear_spot(_stand(frame, at, detail_into), boxes, frame_in)
    yaw, pitch = _look_at(eye, _frame_point(frame, at, 24.0, 36.0))
    shots.append({
        "name": kind,
        "label": label,
        "eye": eye,
        "yaw": yaw,
        "pitch": pitch,
    })
    return shots


def _project_shot(point, shot: dict, width: int, height: int):
    cam_x, cam_y, cam_z = _camera_point(point[0], point[1], point[2], shot["eye"], shot["yaw"], shot["pitch"])
    if cam_z < 0.3:
        return None
    focal = (width / 2) / math.tan(HFOV / 2)
    return (width / 2 + cam_x / cam_z * focal, height / 2 - cam_y / cam_z * focal)


def _camera_point(px: float, py: float, pz: float, eye, yaw: float, pitch: float):
    dx = px - eye[0]
    dy = py - eye[1]
    dz = pz - eye[2]
    cos_y = math.cos(yaw)
    sin_y = math.sin(yaw)
    cam_x = dx * cos_y + dz * sin_y
    cam_z = dx * sin_y - dz * cos_y
    cam_y = dy
    cos_p = math.cos(pitch)
    sin_p = math.sin(pitch)
    return cam_x, cam_y * cos_p - cam_z * sin_p, cam_y * sin_p + cam_z * cos_p


def _clip_near(points, near: float = 0.12):
    if not points:
        return []
    output = []
    previous = points[-1]
    for current in points:
        if previous[2] >= near and current[2] >= near:
            output.append(current)
        elif previous[2] >= near and current[2] < near:
            output.append(_split_near(previous, current, near))
        elif previous[2] < near and current[2] >= near:
            output.append(_split_near(previous, current, near))
            output.append(current)
        previous = current
    return output


def _split_near(start, end, near: float):
    dz = end[2] - start[2]
    t = 0.0 if dz == 0 else (near - start[2]) / dz
    return (
        start[0] + t * (end[0] - start[0]),
        start[1] + t * (end[1] - start[1]),
        near,
    )


def _raster(tri, color, rgb: bytearray, zbuf, width: int, height: int) -> None:
    pts = sorted(tri, key=lambda point: point[1])
    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = pts
    if cy - ay < 0.5:
        return
    y0 = max(int(ay), 0)
    y1 = min(int(cy) + 1, height)
    if y1 <= y0:
        return
    red, green, blue = color

    def edge(y, y_start, y_end, x_start, x_end, z_start, z_end):
        if y_end == y_start:
            return x_start, z_start
        t = (y - y_start) / (y_end - y_start)
        return x_start + t * (x_end - x_start), z_start + t * (z_end - z_start)

    for y in range(y0, y1):
        sample_y = y + 0.5
        if sample_y < ay or sample_y > cy:
            continue
        left_x, left_z = edge(sample_y, ay, cy, ax, cx, az, cz)
        if sample_y < by:
            right_x, right_z = edge(sample_y, ay, by, ax, bx, az, bz)
        else:
            right_x, right_z = edge(sample_y, by, cy, bx, cx, bz, cz)
        if left_x > right_x:
            left_x, right_x = right_x, left_x
            left_z, right_z = right_z, left_z
        span = right_x - left_x
        x0 = max(int(left_x), 0)
        x1 = min(int(right_x) + 1, width)
        if x1 <= x0:
            continue
        inv_span = 0.0 if span == 0 else 1.0 / span
        row = y * width
        for x in range(x0, x1):
            iz = left_z + ((x + 0.5) - left_x) * inv_span * (right_z - left_z)
            index = row + x
            if iz > zbuf[index]:
                zbuf[index] = iz
                offset = index * 3
                rgb[offset] = red
                rgb[offset + 1] = green
                rgb[offset + 2] = blue


def _mix(a, b, t: float):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def _surface_of(box: dict) -> str:
    surface = box.get("surface")
    if surface in _SURFACES:
        return surface
    if box.get("name") == "floor-tile":
        return "tile"
    if float(box.get("metal") or 0.0) >= 0.45:
        return "metal"
    rough = 0.85 if box.get("rough") is None else float(box["rough"])
    if rough <= 0.22:
        return "marble"
    return "paint"


def _tex_gain(surface: str, x: float, y: float, z: float) -> float:
    """World-inch texture. The pattern stays on the cabinet when the camera moves."""
    if surface == "metal":
        return 0.68 if int(math.floor(y / 4.0)) % 2 == 0 else 1.0
    if surface == "marble":
        band = abs((int(math.floor(x + z * 0.6)) % 16) - 3)
        return 0.72 if band < 1 else 1.0
    if surface == "tile":
        fx = x % 12.0
        fz = z % 12.0
        if fx < 0:
            fx += 12.0
        if fz < 0:
            fz += 12.0
        if fx < 0.5 or fz < 0.5:
            return 0.55
        return 1.0
    if surface == "wood":
        streak = int(math.floor(x * 0.7 + y * 0.05)) % 7
        if streak == 0:
            return 0.72
        if streak == 3:
            return 0.88
        return 1.0
    if surface == "gloss":
        return 1.15 if int(math.floor(y / 6.0)) % 5 == 0 else 0.92
    if surface == "flat":
        return 0.96 + ((int(math.floor(x)) + int(math.floor(y)) * 2) % 3) * 0.02
    grain = (int(math.floor(x * 2.0)) + int(math.floor(y * 2.0)) * 3) % 5
    return 0.9 + grain * 0.025


def _face_span(corners) -> float:
    span = 0.0
    origin = corners[0]
    for corner in corners[1:]:
        span = max(span, abs(corner[0] - origin[0]), abs(corner[1] - origin[1]), abs(corner[2] - origin[2]))
    return span


def _face_quads(corners, div: int):
    """Split one face into a grid so a world-space texture has somewhere to land."""
    if div <= 1:
        yield corners
        return

    def at(u, v):
        return _mix(_mix(corners[0], corners[1], u), _mix(corners[3], corners[2], u), v)

    for j in range(div):
        for i in range(div):
            u0, u1 = i / div, (i + 1) / div
            v0, v1 = j / div, (j + 1) / div
            yield (at(u0, v0), at(u1, v0), at(u1, v1), at(u0, v1))


def render_rgb(boxes: list[dict], camera: dict, width: int = STILL_WIDTH, height: int = STILL_HEIGHT, background=(0.58, 0.64, 0.70)) -> bytes:
    """Draw the boxes from one eye. Returns packed RGB bytes."""
    back = tuple(max(0, min(255, int(channel * 255 + 0.5))) for channel in background)
    rgb = bytearray(bytes(back) * (width * height))
    zbuf = array.array("f", [0.0]) * (width * height)
    eye = camera["eye"]
    yaw = float(camera["yaw"])
    pitch = float(camera["pitch"])
    focal = (width / 2) / math.tan(HFOV / 2)
    faces = _FACE_INDEX
    for box in boxes:
        if box.get("skip"):
            continue
        x0, y0, z0 = box["x"], box["y"], box["z"]
        sx, sy, sz = box["sx"], box["sy"], box["sz"]
        metal = float(box.get("metal") or 0.0)
        rough = 0.85 if box.get("rough") is None else float(box["rough"])
        surface = _surface_of(box)
        textured = (not box.get("plain")) and (
            box.get("surface") in _SURFACES
            or box.get("name") == "floor-tile"
            or metal > 0.15
            or rough < 0.5
        )
        corners = [(x0 + ox * sx, y0 + oy * sy, z0 + oz * sz) for ox, oy, oz in _CORNERS]
        selected = (faces[2],) if box.get("top") else faces
        for indexes, normal in selected:
            world_corners = [corners[index] for index in indexes]
            if textured:
                div = max(2, min(8, int(round(_face_span(world_corners) / 4.0)) or 2))
            else:
                div = 1
            for quad in _face_quads(world_corners, div):
                face = (
                    (quad[0][0] + quad[2][0]) * 0.5,
                    (quad[0][1] + quad[2][1]) * 0.5,
                    (quad[0][2] + quad[2][2]) * 0.5,
                )
                gain = _tex_gain(surface, face[0], face[1], face[2]) if div > 1 else 1.0
                if normal[0] * (eye[0] - face[0]) + normal[1] * (eye[1] - face[1]) + normal[2] * (eye[2] - face[2]) <= 0:
                    continue
                view = (eye[0] - face[0], eye[1] - face[1], eye[2] - face[2])
                shaded = _shade([channel * gain for channel in box["color"]], normal, metal, rough, view, surface)
                cam = [_camera_point(point[0], point[1], point[2], eye, yaw, pitch) for point in quad]
                clipped = _clip_near(cam)
                if len(clipped) < 3:
                    continue
                projected = []
                for cx, cy, cz in clipped:
                    inv = 1.0 / cz
                    projected.append((width / 2 + cx * inv * focal, height / 2 - cy * inv * focal, inv))
                for index in range(1, len(projected) - 1):
                    _raster((projected[0], projected[index], projected[index + 1]), shaded, rgb, zbuf, width, height)
    return bytes(rgb)


def _png(rgb: bytes, width: int, height: int) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw = bytearray()
    stride = width * 3
    for y in range(height):
        raw.append(0)
        raw.extend(rgb[y * stride:(y + 1) * stride])
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(bytes(raw), 6)) + chunk(b"IEND", b"")


def render_png(boxes, camera, width=STILL_WIDTH, height=STILL_HEIGHT, background=(0.58, 0.64, 0.70)) -> bytes:
    return _png(render_rgb(boxes, camera, width, height, background), width, height)


_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  html, body { margin: 0; height: 100%; background: #1b1d1c; color: #f4f1ea; font: 15px/1.4 "Iowan Old Style", Palatino, Georgia, serif; }
  canvas { display: block; width: 100%; height: 100%; cursor: crosshair; }
  #hud { position: fixed; left: 16px; top: 14px; right: 16px; display: flex; justify-content: space-between; gap: 16px; pointer-events: none; text-shadow: 0 1px 2px #000; }
  #help { pointer-events: none; opacity: 0.85; }
  #shots { position: fixed; left: 12px; right: 12px; bottom: 10px; display: flex; gap: 10px; align-items: end; }
  #products { position: fixed; top: 48px; right: 12px; width: min(300px, 42vw); max-height: 62vh; overflow: auto; background: rgba(20, 22, 21, 0.82); padding: 10px 12px; border-radius: 8px; font-size: 13px; pointer-events: auto; }
  #products h2 { margin: 0 0 6px; font-size: 15px; font-weight: normal; }
  #products h3 { margin: 8px 0 4px; font-size: 13px; font-weight: normal; }
  #products p { margin: 0 0 6px; }
  #products summary { cursor: pointer; margin: 10px 0 4px; }
  #products ul, #products ol { margin: 0 0 6px; padding-left: 18px; }
  #products li { margin: 0 0 6px; }
  #looking { list-style: none; padding: 0; }
  button { pointer-events: auto; background: rgba(20, 22, 21, 0.78); color: inherit; border: 1px solid rgba(255,255,255,0.25); border-radius: 6px; padding: 4px; font: inherit; cursor: pointer; }
  button img { display: block; width: 168px; height: 94px; object-fit: cover; border-radius: 4px; }
  button span { display: block; padding: 4px 4px 2px; font-size: 13px; }
  #cross { display: none; position: fixed; left: 50%; top: 50%; width: 12px; height: 12px; margin: -6px 0 0 -6px; pointer-events: none; }
  #cross:before, #cross:after { content: ""; position: absolute; background: #fff; }
  #cross:before { left: 5px; top: 0; width: 2px; height: 12px; }
  #cross:after { left: 0; top: 5px; width: 12px; height: 2px; }
</style>
</head>
<body>
<canvas id="view"></canvas>
<div id="cross"></div>
<div id="hud"><div id="where"></div><div id="help">Click to look. WASD walks. Esc releases the mouse.</div></div>
<aside id="products"><h2>In view</h2><p id="looking-empty">Look at a cabinet.</p><ol id="looking"></ol><details><summary>What to buy</summary><div id="buy">__BUY__</div></details><details><summary>Products in this design</summary><ol id="product-list"></ol></details></aside>
<div id="shots"></div>
<script>
const scene = __SCENE__;
const canvas = document.getElementById("view");
const ctx = canvas.getContext("2d");
const help = document.getElementById("help");
const cross = document.getElementById("cross");
const where = document.getElementById("where");
const EYE = scene.eye;
const hfov = scene.hfov * Math.PI / 180;
let yaw = scene.shots[0].yaw;
let pitch = scene.shots[0].pitch;
const cam = { x: scene.shots[0].eye[0], y: EYE, z: scene.shots[0].eye[2] };
const keys = {};
let locked = false;

function resize() {
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;
}
window.addEventListener("resize", resize);
resize();

function blocked(x, z) {
  for (const box of scene.boxes) {
    if (box.name === "floor" || box.name === "ceiling" || box.sy < 8) continue;
    if (box.y > EYE || box.y + box.sy < 18) continue;
    if (x > box.x - 8 && x < box.x + box.sx + 8 && z > box.z - 8 && z < box.z + box.sz + 8) return true;
  }
  return false;
}

function jump(shot) {
  cam.x = shot.eye[0];
  cam.y = EYE;
  cam.z = shot.eye[2];
  yaw = shot.yaw;
  pitch = shot.pitch;
}

const looking = document.getElementById("looking");
const lookingEmpty = document.getElementById("looking-empty");
let lookingKey = "";
function showLooking(rows) {
  const key = rows.map((row) => row.label.text || row.label.short).join("\n");
  if (key === lookingKey) return;
  lookingKey = key;
  looking.textContent = "";
  lookingEmpty.style.display = rows.length ? "none" : "block";
  for (const row of rows) {
    const item = document.createElement("li");
    item.textContent = row.label.text || row.label.short;
    looking.appendChild(item);
  }
}

const list = document.getElementById("product-list");
(scene.products || []).forEach((line) => {
  if (!line) {
    const gap = document.createElement("li");
    gap.textContent = "";
    return;
  }
  const item = document.createElement("li");
  item.textContent = line;
  list.appendChild(item);
});

const strip = document.getElementById("shots");
scene.shots.forEach((shot, index) => {
  const button = document.createElement("button");
  button.innerHTML = '<img alt="" src="' + shot.image + '"><span>' + (index + 1) + ". " + shot.label + "</span>";
  button.addEventListener("click", () => jump(shot));
  strip.appendChild(button);
});

canvas.addEventListener("click", () => canvas.requestPointerLock());
document.addEventListener("pointerlockchange", () => {
  locked = document.pointerLockElement === canvas;
  help.style.display = locked ? "none" : "block";
  cross.style.display = locked ? "block" : "none";
});
document.addEventListener("mousemove", (event) => {
  if (!locked) return;
  yaw += event.movementX * 0.0022;
  pitch -= event.movementY * 0.0022;
  pitch = Math.max(-1.15, Math.min(1.15, pitch));
});
document.addEventListener("keydown", (event) => {
  keys[event.code] = true;
  if (["KeyW", "KeyA", "KeyS", "KeyD", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Space"].includes(event.code)) event.preventDefault();
  const digit = { Digit1: 0, Digit2: 1, Digit3: 2 }[event.code];
  if (digit !== undefined && scene.shots[digit]) jump(scene.shots[digit]);
});
document.addEventListener("keyup", (event) => { keys[event.code] = false; });

const CORNERS = [[0,0,0],[1,0,0],[1,1,0],[0,1,0],[0,0,1],[1,0,1],[1,1,1],[0,1,1]];
const FACES = [
  [[4,5,6,7],[0,0,1]], [[1,0,3,2],[0,0,-1]], [[3,2,6,7],[0,1,0]],
  [[0,1,5,4],[0,-1,0]], [[1,2,6,5],[1,0,0]], [[4,0,3,7],[-1,0,0]]
];

function shade(color, normal, metal, rough, view, surface) {
  function unit(x, y, z) {
    const length = Math.hypot(x, y, z) || 1;
    return [x / length, y / length, z / length];
  }
  const key = unit(0.35, 0.92, 0.42);
  const fill = unit(-0.55, 0.35, 0.25);
  const keyFacing = Math.max(0, normal[0] * key[0] + normal[1] * key[1] + normal[2] * key[2]);
  const fillFacing = Math.max(0, normal[0] * fill[0] + normal[1] * fill[1] + normal[2] * fill[2]);
  const sky = Math.max(0, normal[1]) * 0.07;
  const gain = 0.34 + 0.62 * keyFacing + 0.16 * fillFacing + sky;
  const rgb = color.map((channel) => channel * gain);
  if (metal > 0.15 || rough < 0.45) {
    const vlen = Math.hypot(view[0], view[1], view[2]) || 1;
    const vx = view[0] / vlen, vy = view[1] / vlen, vz = view[2] / vlen;
    const hx = key[0] + vx, hy = key[1] + vy, hz = key[2] + vz;
    const hlen = Math.hypot(hx, hy, hz) || 1;
    const spec = Math.max(0, (normal[0] * hx + normal[1] * hy + normal[2] * hz) / hlen);
    const shine = 10 + (1 - rough) * 70;
    const amount = Math.pow(spec, shine) * (0.2 + 0.8 * metal) * (1 - Math.min(rough, 0.95));
    for (let i = 0; i < 3; i++) rgb[i] = Math.min(1, rgb[i] + amount);
    let power = 0, broad = 0;
    if (surface === "gloss" || rough < 0.2) { power = 4; broad = 0.42; }
    else if (surface === "metal") { power = 6; broad = 0.35; }
    else if (surface === "marble" || surface === "tile") { power = 7; broad = 0.26; }
    if (broad) {
      const soft = Math.pow(spec, power);
      for (let i = 0; i < 3; i++) rgb[i] = Math.min(1, rgb[i] + soft * broad);
    }
    if (surface === "gloss" || surface === "marble" || surface === "metal" || surface === "tile" || rough < 0.22) {
      const facingEye = Math.max(0, normal[0] * vx + normal[1] * vy + normal[2] * vz);
      const fres = Math.pow(1 - facingEye, 0.65);
      const lift = fres * (0.22 + 0.45 * metal) * (1.2 - rough);
      for (let i = 0; i < 3; i++) rgb[i] = Math.min(1, rgb[i] + lift);
    }
  }
  return "rgb(" + rgb.map((channel) => Math.max(0, Math.min(255, (channel * 255) | 0))).join(",") + ")";
}

function clipNear(points) {
  const near = 0.2;
  const output = [];
  let previous = points[points.length - 1];
  for (const current of points) {
    const pin = previous[2] >= near;
    const cin = current[2] >= near;
    if (pin && cin) output.push(current);
    else if (pin || cin) {
      const dz = current[2] - previous[2];
      const t = dz === 0 ? 0 : (near - previous[2]) / dz;
      output.push([
        previous[0] + t * (current[0] - previous[0]),
        previous[1] + t * (current[1] - previous[1]),
        near
      ]);
      if (cin) output.push(current);
    }
    previous = current;
  }
  return output;
}

function draw() {
  const width = canvas.width;
  const height = canvas.height;
  const focal = (width / 2) / Math.tan(hfov / 2);
  const cosY = Math.cos(yaw), sinY = Math.sin(yaw);
  const cosP = Math.cos(pitch), sinP = Math.sin(pitch);
  ctx.fillStyle = "rgb(" + scene.background.map((c) => (c * 255) | 0).join(",") + ")";
  ctx.fillRect(0, 0, width, height);
  const faces = [];
  function mix(a, b, t) {
    return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
  }
  function pushFace(world, normal, color, metal, rough, surface) {
    const face = [(world[0][0] + world[2][0]) / 2, (world[0][1] + world[2][1]) / 2, (world[0][2] + world[2][2]) / 2];
    if (normal[0] * (cam.x - face[0]) + normal[1] * (cam.y - face[1]) + normal[2] * (cam.z - face[2]) <= 0) return;
    const camPoints = world.map((point) => {
      const dx = point[0] - cam.x, dy = point[1] - cam.y, dz = point[2] - cam.z;
      const camX = dx * cosY + dz * sinY;
      const camZ = dx * sinY - dz * cosY;
      return [camX, dy * cosP - camZ * sinP, dy * sinP + camZ * cosP];
    });
    const clipped = clipNear(camPoints);
    if (clipped.length < 3) return;
    let depth = 0;
    const screen = clipped.map(([cx, cy, cz]) => {
      depth += cz;
      const inv = 1 / cz;
      return [width / 2 + cx * inv * focal, height / 2 - cy * inv * focal];
    });
    faces.push({
      depth: depth / clipped.length,
      screen,
      color: shade(color, normal, metal, rough, [cam.x - face[0], cam.y - face[1], cam.z - face[2]], surface)
    });
  }
  for (const box of scene.boxes) {
    if (box.skip) continue;
    const corners = CORNERS.map(([ox, oy, oz]) => [box.x + ox * box.sx, box.y + oy * box.sy, box.z + oz * box.sz]);
    const metal = box.metal || 0;
    const rough = box.rough == null ? 0.85 : box.rough;
    const surface = box.surface || (box.name === "floor-tile" ? "tile" : (metal >= 0.45 ? "metal" : (rough <= 0.22 ? "marble" : "paint")));
    const textured = !box.plain && (box.surface === "paint" || box.surface === "marble" || box.surface === "metal" || box.surface === "tile" || box.surface === "wood" || box.surface === "gloss" || box.surface === "flat" || box.name === "floor-tile" || metal > 0.15 || rough < 0.5);
    const selected = box.top ? [FACES[2]] : FACES;
    for (const [indexes, normal] of selected) {
      const world = indexes.map((index) => corners[index]);
      let span = 0;
      for (let k = 1; k < world.length; k++) {
        span = Math.max(span, Math.abs(world[k][0] - world[0][0]), Math.abs(world[k][1] - world[0][1]), Math.abs(world[k][2] - world[0][2]));
      }
      const div = textured ? Math.max(2, Math.min(4, Math.round(span / 6) || 2)) : 1;
      for (let j = 0; j < div; j++) {
        for (let i = 0; i < div; i++) {
          const u0 = i / div, u1 = (i + 1) / div, v0 = j / div, v1 = (j + 1) / div;
          const at = (u, v) => mix(mix(world[0], world[1], u), mix(world[3], world[2], u), v);
          const quad = [at(u0, v0), at(u1, v0), at(u1, v1), at(u0, v1)];
          const cx = (quad[0][0] + quad[2][0]) / 2, cy = (quad[0][1] + quad[2][1]) / 2, cz = (quad[0][2] + quad[2][2]) / 2;
          let gain = 1;
          if (div > 1) {
            if (surface === "metal") gain = (Math.floor(cy / 4) % 2) ? 1 : 0.68;
            else if (surface === "marble") gain = Math.abs((Math.floor(cx + cz * 0.6) % 16) - 3) < 1 ? 0.72 : 1;
            else if (surface === "tile") {
              const fx = ((cx % 12) + 12) % 12, fz = ((cz % 12) + 12) % 12;
              gain = (fx < 0.5 || fz < 0.5) ? 0.55 : 1;
            } else if (surface === "wood") {
              const streak = Math.floor(cx * 0.7 + cy * 0.05) % 7;
              gain = streak === 0 ? 0.72 : (streak === 3 ? 0.88 : 1);
            } else if (surface === "gloss") gain = (Math.floor(cy / 6) % 5) === 0 ? 1.15 : 0.92;
            else if (surface === "flat") gain = 0.96 + ((Math.floor(cx) + Math.floor(cy) * 2) % 3) * 0.02;
            else gain = 0.9 + ((Math.floor(cx * 2) + Math.floor(cy * 2) * 3) % 5) * 0.025;
          }
          pushFace(quad, normal, box.color.map((channel) => channel * gain), metal, rough, surface);
        }
      }
    }
  }
  faces.sort((a, b) => b.depth - a.depth);
  for (const face of faces) {
    ctx.beginPath();
    ctx.moveTo(face.screen[0][0], face.screen[0][1]);
    for (let i = 1; i < face.screen.length; i++) ctx.lineTo(face.screen[i][0], face.screen[i][1]);
    ctx.closePath();
    ctx.fillStyle = face.color;
    ctx.fill();
  }
  ctx.lineWidth = 2;
  ctx.strokeStyle = "#1c1a17";
  ctx.font = "13px Palatino, Georgia, serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  function projectPoint(pt) {
    const dx = pt[0] - cam.x, dy = pt[1] - cam.y, dz = pt[2] - cam.z;
    const camX = dx * cosY + dz * sinY;
    const camZ = dx * sinY - dz * cosY;
    const cy = dy * cosP - camZ * sinP;
    const cz = dy * sinP + camZ * cosP;
    if (cz < 0.3) return null;
    const inv = 1 / cz;
    return [width / 2 + camX * inv * focal, height / 2 - cy * inv * focal];
  }
  const measureHits = [];
  for (const mark of scene.measures || []) {
    if (!mark.text) continue;
    const mid = [(mark.a[0] + mark.b[0]) / 2, (mark.a[1] + mark.b[1]) / 2, (mark.a[2] + mark.b[2]) / 2];
    const at = projectPoint(mid);
    if (!at) continue;
    const off = Math.hypot((at[0] - width / 2) / (width / 2), (at[1] - height / 2) / (height / 2));
    if (off > 0.42) continue;
    measureHits.push({ mark, text: mark.text, at, off });
  }
  measureHits.sort((a, b) => a.off - b.off);
  for (const hit of measureHits.slice(0, 1)) {
    const a = projectPoint(hit.mark.a);
    const b = projectPoint(hit.mark.b);
    if (a && b) {
      ctx.strokeStyle = "#1c1a17";
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(a[0], a[1]);
      ctx.lineTo(b[0], b[1]);
      ctx.stroke();
    }
    const tw = ctx.measureText(hit.text).width + 8;
    ctx.fillStyle = "rgba(20,22,21,0.82)";
    ctx.fillRect(hit.at[0] - tw / 2, hit.at[1] - 8, tw, 16);
    ctx.fillStyle = "#f4f1ea";
    ctx.fillText(hit.text, hit.at[0], hit.at[1]);
  }
  const aimed = [];
  for (const label of scene.labels || []) {
    const dx = label.x - cam.x, dy = label.y - cam.y, dz = label.z - cam.z;
    const camX = dx * cosY + dz * sinY;
    const camZ = dx * sinY - dz * cosY;
    const cy = dy * cosP - camZ * sinP;
    const cz = dy * sinP + camZ * cosP;
    if (cz < 0.3) continue;
    const inv = 1 / cz;
    const sx = width / 2 + camX * inv * focal;
    const sy = height / 2 - cy * inv * focal;
    if (sx < 8 || sy < 8 || sx > width - 8 || sy > height - 8) continue;
    const off = Math.hypot((sx - width / 2) / (width / 2), (sy - height / 2) / (height / 2));
    if (off > 0.55) continue;
    aimed.push({ label, off, cz, sx, sy });
  }
  aimed.sort((a, b) => a.off - b.off || a.cz - b.cz);
  showLooking(aimed.slice(0, 4));
}

let last = performance.now();
function frame(now) {
  const dt = Math.min(0.05, (now - last) / 1000);
  last = now;
  let forward = (keys.KeyW || keys.ArrowUp ? 1 : 0) - (keys.KeyS || keys.ArrowDown ? 1 : 0);
  let strafe = (keys.KeyD || keys.ArrowRight ? 1 : 0) - (keys.KeyA || keys.ArrowLeft ? 1 : 0);
  const fx = Math.sin(yaw), fz = -Math.cos(yaw);
  const rx = Math.cos(yaw), rz = Math.sin(yaw);
  const speed = keys.ShiftLeft || keys.ShiftRight ? 110 : 56;
  const dx = (fx * forward + rx * strafe) * speed * dt;
  const dz = (fz * forward + rz * strafe) * speed * dt;
  if (!blocked(cam.x + dx, cam.z)) cam.x += dx;
  if (!blocked(cam.x, cam.z + dz)) cam.z += dz;
  const floor = scene.boxes.find((box) => box.name === "floor");
  if (floor) {
    cam.x = Math.max(floor.x + 6, Math.min(floor.x + floor.sx - 6, cam.x));
    cam.z = Math.max(floor.z + 6, Math.min(floor.z + floor.sz - 6, cam.z));
  }
  where.textContent = Math.round(cam.x) + " in, " + Math.round(cam.z) + " in";
  draw();
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
</script>
</body>
</html>
"""


def _esc(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _buy_html(design: dict) -> str:
    buy = design.get("buy") or {}
    if not buy:
        return ""
    parts = ["<h2>What to buy</h2>"]
    front = buy.get("front_name") or buy.get("front_id") or ""
    sentence = buy.get("sentence") or ""
    parts.append("<p>" + _esc(f"Front: {front}. {sentence}".strip()) + "</p>")
    if buy.get("color_note"):
        parts.append("<p>" + _esc(buy["color_note"]) + "</p>")

    def section(title: str, rows: list) -> None:
        if not rows:
            return
        parts.append("<h3>" + _esc(title) + "</h3><ul>")
        for row in rows:
            parts.append("<li>" + _esc(row) + "</li>")
        parts.append("</ul>")

    section("Cabinets", buy.get("cabinets") or [])
    section("Hardware", buy.get("hardware") or [])
    section("Cover panels and fillers", buy.get("panels") or [])
    section("Countertops", buy.get("worktops") or [])
    section("Still to resolve", buy.get("unresolved") or [])
    if buy.get("total"):
        parts.append("<p>" + _esc(buy["total"]) + "</p>")
    return "".join(parts)


def _page(design: dict, boxes: list[dict], shots: list[dict], background, measures: list[dict]) -> str:
    payload = {
        "eye": EYE_IN,
        "hfov": 70,
        "background": list(background),
        "boxes": boxes,
        "labels": [
            {
                "short": row["short"],
                "text": row["text"],
                "x": round(row["x"], 2),
                "y": round(row["y"], 2),
                "z": round(row["z"], 2),
            }
            for row in callouts(design)
        ],
        "measures": [
            {
                "text": row["text"],
                "a": [round(value, 2) for value in row["a"]],
                "b": [round(value, 2) for value in row["b"]],
            }
            for row in measures
        ],
        "products": product_lines(design),
        "shots": [
            {
                "name": shot["name"],
                "label": shot["label"],
                "eye": [round(value, 2) for value in shot["eye"]],
                "yaw": shot["yaw"],
                "pitch": shot["pitch"],
                "image": f"views/{shot['name']}.png",
            }
            for shot in shots
        ],
    }
    scene = json.dumps(payload, separators=(",", ":")).replace("<", "\\u003c")
    title = design.get("room", {}).get("name") or "Kitchen"
    return (
        _PAGE.replace("__TITLE__", str(title).replace("<", ""))
        .replace("__BUY__", _buy_html(design))
        .replace("__SCENE__", scene)
    )


def _aimed_measure_segments(marks: list[dict], camera: dict, width: int, height: int, cone: float = 0.42, limit: int = 1) -> list[tuple]:
    """One thin dimension line near the middle of the frame. The bars are not part of the model."""
    eye = camera["eye"]
    yaw = float(camera["yaw"])
    pitch = float(camera["pitch"])
    focal = (width / 2) / math.tan(HFOV / 2)
    ranked = []
    for mark in marks:
        if not mark.get("text"):
            continue
        ax, ay, az = mark["a"]
        bx, by, bz = mark["b"]
        cax, cay, caz = _camera_point(ax, ay, az, eye, yaw, pitch)
        cbx, cby, cbz = _camera_point(bx, by, bz, eye, yaw, pitch)
        if caz < 0.3 or cbz < 0.3:
            continue
        sax = width / 2 + cax / caz * focal
        say = height / 2 - cay / caz * focal
        sbx = width / 2 + cbx / cbz * focal
        sby = height / 2 - cby / cbz * focal
        mx = (sax + sbx) / 2
        my = (say + sby) / 2
        off = math.hypot((mx - width / 2) / (width / 2), (my - height / 2) / (height / 2))
        if off > cone:
            continue
        ranked.append((off, (sax, say, sbx, sby, mark["text"])))
    ranked.sort(key=lambda item: item[0])
    return [segment for _off, segment in ranked[:limit]]


def _labels_in_view(notes: list[dict], camera: dict, width: int, height: int, cone: float = 0.55, limit: int = 4) -> list[tuple]:
    """Callouts near the middle of the frame, nearest to the aim first."""
    eye = camera["eye"]
    yaw = float(camera["yaw"])
    pitch = float(camera["pitch"])
    focal = (width / 2) / math.tan(HFOV / 2)
    ranked = []
    for row in notes:
        cam_x, cam_y, cam_z = _camera_point(row["x"], row["y"], row["z"], eye, yaw, pitch)
        if cam_z < 0.3:
            continue
        sx = width / 2 + cam_x / cam_z * focal
        sy = height / 2 - cam_y / cam_z * focal
        if sx < 8 or sy < 8 or sx > width - 8 or sy > height - 8:
            continue
        off = math.hypot((sx - width / 2) / (width / 2), (sy - height / 2) / (height / 2))
        if off > cone:
            continue
        ranked.append((off, cam_z, sx, sy, row))
    ranked.sort(key=lambda item: (item[0], item[1]))
    return ranked[:limit]


def write_experience(design: dict, nodes: list[dict], folder: Path, width: int = STILL_WIDTH, height: int = STILL_HEIGHT) -> dict:
    """Write walk.html and the first-person stills next to the other design files."""
    folder = Path(folder)
    room = design.get("room") or {}
    boxes = boxes_from_nodes(nodes)
    _open_floor(boxes, design)
    _add_ceiling(boxes, room)
    _pin_ground(boxes)
    background = _room_color(room, "surround", (0.58, 0.64, 0.70))
    shots = shot_list(design, boxes)
    view_dir = folder / "views"
    view_dir.mkdir(parents=True, exist_ok=True)
    notes = callouts(design)
    lines = still_legend(design)
    measures = dimension_lines(design)
    images = []
    for shot in shots:
        path = view_dir / f"{shot['name']}.png"
        rgb = render_rgb(boxes, shot, width, height, background)
        segments = _aimed_measure_segments(measures, shot, width, height)
        if segments:
            rgb = paint_dimensions(rgb, width, height, segments)
        aimed = _labels_in_view(notes, shot, width, height)
        side = [row["text"] for _off, _depth, _sx, _sy, row in aimed]
        painted, out_w, out_h = paint_labels(rgb, width, height, [], lines, side)
        path.write_bytes(_png(painted, out_w, out_h))
        images.append({
            "name": shot["name"],
            "file": f"views/{shot['name']}.png",
            "path": str(path),
            "label": shot["label"],
        })
    html_path = folder / "walk.html"
    html_path.write_text(_page(design, boxes, shots, background, measures))
    return {
        "walk": str(html_path),
        "images": images,
        "record": {"walk": "walk.html", "eye_in": EYE_IN, "images": images},
    }
