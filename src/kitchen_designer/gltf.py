from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path

INCH = 0.0254

# Shared unit cube. Nodes scale it. Viewers transform normals with the node scale.
_FACES = (
    ((0, 0, 1), ((0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1))),
    ((0, 0, -1), ((1, 0, 0), (0, 0, 0), (0, 1, 0), (1, 1, 0))),
    ((0, 1, 0), ((0, 1, 1), (1, 1, 1), (1, 1, 0), (0, 1, 0))),
    ((0, -1, 0), ((0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1))),
    ((1, 0, 0), ((1, 0, 1), (1, 0, 0), (1, 1, 0), (1, 1, 1))),
    ((-1, 0, 0), ((0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0))),
)


def _pack(values: list[float]) -> bytes:
    return struct.pack("<" + "f" * len(values), *values)


def _cube_buffers() -> tuple[bytes, bytes, bytes, bytes]:
    positions: list[float] = []
    normals: list[float] = []
    uvs: list[float] = []
    indices: list[int] = []
    for normal, corners in _FACES:
        base = len(positions) // 3
        for index, corner in enumerate(corners):
            positions.extend(corner)
            normals.extend(normal)
            uvs.extend(((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))[index])
        indices.extend((base, base + 1, base + 2, base, base + 2, base + 3))
    idx = struct.pack("<" + "H" * len(indices), *indices)
    return _pack(positions), _pack(normals), _pack(uvs), idx


def _grid_floor(div_x: int, div_z: int) -> tuple[bytes, bytes, bytes, bytes]:
    """Unit box whose top is a tile grid. UVs repeat once per tile."""
    positions: list[float] = []
    normals: list[float] = []
    uvs: list[float] = []
    indices: list[int] = []

    def vert(x: float, y: float, z: float, nx: float, ny: float, nz: float, u: float, v: float) -> int:
        positions.extend((x, y, z))
        normals.extend((nx, ny, nz))
        uvs.extend((u, v))
        return len(positions) // 3 - 1

    def quad(a: int, b: int, c: int, d: int) -> None:
        indices.extend((a, b, c, a, c, d))

    for j in range(div_z):
        for i in range(div_x):
            x0, x1 = i / div_x, (i + 1) / div_x
            z0, z1 = j / div_z, (j + 1) / div_z
            a = vert(x0, 1, z0, 0, 1, 0, float(i), float(j))
            b = vert(x1, 1, z0, 0, 1, 0, float(i + 1), float(j))
            c = vert(x1, 1, z1, 0, 1, 0, float(i + 1), float(j + 1))
            d = vert(x0, 1, z1, 0, 1, 0, float(i), float(j + 1))
            quad(a, b, c, d)
    # Sides and bottom stay coarse. They still add faces the top grid does not have.
    rings = (
        ((0, 0, -1), ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0))),
        ((0, 0, 1), ((1, 0, 1), (0, 0, 1), (0, 1, 1), (1, 1, 1))),
        ((1, 0, 0), ((1, 0, 1), (1, 0, 0), (1, 1, 0), (1, 1, 1))),
        ((-1, 0, 0), ((0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0))),
        ((0, -1, 0), ((0, 0, 1), (1, 0, 1), (1, 0, 0), (0, 0, 0))),
    )
    for normal, corners in rings:
        ids = [vert(c[0], c[1], c[2], normal[0], normal[1], normal[2], uv[0], uv[1]) for c, uv in zip(corners, ((0, 0), (1, 0), (1, 1), (0, 1)))]
        quad(*ids)
    return _pack(positions), _pack(normals), _pack(uvs), struct.pack("<" + "H" * len(indices), *indices)


def _png(width: int, height: int, rgb: bytes) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw = bytearray()
    stride = width * 3
    for y in range(height):
        raw.append(0)
        raw.extend(rgb[y * stride:(y + 1) * stride])
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(bytes(raw), 6)) + chunk(b"IEND", b"")


def _tex_paint() -> bytes:
    size = 64
    raw = bytearray(size * size * 3)
    for y in range(size):
        for x in range(size):
            grain = 238 + ((x * 13 + y * 7) % 17)
            index = (y * size + x) * 3
            raw[index:index + 3] = bytes((grain, grain - 1, grain - 2))
    return _png(size, size, bytes(raw))


def _tex_marble() -> bytes:
    size = 64
    raw = bytearray(size * size * 3)
    for y in range(size):
        for x in range(size):
            vein = abs(((x * 3 + y) % 31) - 8)
            shade = 246 - min(28, vein if vein < 3 else 0)
            if (x + y * 2) % 19 == 0:
                shade -= 18
            index = (y * size + x) * 3
            raw[index:index + 3] = bytes((shade, shade, shade - 2))
    return _png(size, size, bytes(raw))


def _tex_metal() -> bytes:
    size = 64
    raw = bytearray(size * size * 3)
    for y in range(size):
        band = 228 + (y % 4) * 6
        for x in range(size):
            shade = min(255, band + (x % 5))
            index = (y * size + x) * 3
            raw[index:index + 3] = bytes((shade, shade, shade + 1 if shade < 255 else 255))
    return _png(size, size, bytes(raw))


def _tex_wood() -> bytes:
    size = 64
    raw = bytearray(size * size * 3)
    for y in range(size):
        for x in range(size):
            shade = 214 + ((x * 3) % 11) * 2
            if (y // 3) % 7 == 0:
                shade -= 48
            shade = max(150, min(244, shade))
            index = (y * size + x) * 3
            raw[index:index + 3] = bytes((shade, max(0, shade - 6), max(0, shade - 14)))
    return _png(size, size, bytes(raw))


def _tex_gloss() -> bytes:
    size = 64
    raw = bytearray(size * size * 3)
    for y in range(size):
        for x in range(size):
            band = abs((x + y) % 32 - 3)
            shade = 255 if band < 2 else 248
            index = (y * size + x) * 3
            raw[index:index + 3] = bytes((shade, shade, shade))
    return _png(size, size, bytes(raw))


def _tex_flat() -> bytes:
    size = 64
    raw = bytearray(size * size * 3)
    for y in range(size):
        for x in range(size):
            shade = 244 + ((x * 5 + y * 3) % 3)
            index = (y * size + x) * 3
            raw[index:index + 3] = bytes((shade, shade, shade))
    return _png(size, size, bytes(raw))


def _tex_tile() -> bytes:
    size = 64
    raw = bytearray(size * size * 3)
    for y in range(size):
        for x in range(size):
            grout = x < 3 or y < 3 or x > 60 or y > 60
            shade = 176 if grout else 236 + ((x * y) % 5)
            index = (y * size + x) * 3
            raw[index:index + 3] = bytes((shade, shade - 2, shade - 6))
    return _png(size, size, bytes(raw))


_TEXTURES = (
    ("paint", _tex_paint),
    ("marble", _tex_marble),
    ("metal", _tex_metal),
    ("tile", _tex_tile),
    ("wood", _tex_wood),
    ("gloss", _tex_gloss),
    ("flat", _tex_flat),
)


def _pad(data: bytes, fill: bytes) -> bytes:
    return data + fill * ((4 - len(data) % 4) % 4)


def _material(name: str, color: list[float], metallic: float, roughness: float, texture: int | None) -> dict:
    pbr = {
        "baseColorFactor": [color[0], color[1], color[2], 1],
        "metallicFactor": metallic,
        "roughnessFactor": roughness,
    }
    if texture is not None:
        pbr["baseColorTexture"] = {"index": texture}
    return {"name": name, "pbrMetallicRoughness": pbr}


def _surface_for(name: str, metallic: float, roughness: float, explicit: str | None) -> str:
    if explicit in ("paint", "marble", "metal", "tile", "wood", "gloss", "flat"):
        return explicit
    if name == "worktop":
        return "marble"
    if name == "floor":
        return "tile"
    if metallic >= 0.45 or name == "appliance":
        return "metal"
    if roughness <= 0.2:
        return "marble"
    return "paint"


def write_glb(path: Path, nodes: list[dict], products: list[str] | None = None) -> dict:
    """Write a GLB. Cabinets are textured cubes. The floor is a tiled grid."""
    pos, norm, uv, idx = _cube_buffers()
    floor_node = next((node for node in nodes if node.get("name") == "floor"), None)
    floor_bytes = b""
    floor_counts = (0, 0, 0, 0)
    if floor_node is not None:
        div_x = max(2, min(24, int(round(float(floor_node["scale"][0]) / (12 * INCH))) or 2))
        div_z = max(2, min(24, int(round(float(floor_node["scale"][2]) / (12 * INCH))) or 2))
        floor_bytes = _grid_floor(div_x, div_z)
        floor_counts = (len(floor_bytes[0]) // 12, len(floor_bytes[1]) // 12, len(floor_bytes[2]) // 8, len(floor_bytes[3]) // 2)
    images = [builder() for _name, builder in _TEXTURES]
    image_index = {name: index for index, (name, _builder) in enumerate(_TEXTURES)}
    chunks = [pos, norm, uv, idx]
    if floor_node is not None:
        chunks.extend(floor_bytes)
    chunks.extend(images)
    blob = b""
    offsets = []
    for chunk in chunks:
        blob = _pad(blob, b"\x00")
        offsets.append(len(blob))
        blob += chunk
    views = []
    for index, chunk in enumerate(chunks):
        view = {"buffer": 0, "byteOffset": offsets[index], "byteLength": len(chunk)}
        if index < (8 if floor_node is not None else 4):
            view["target"] = 34963 if chunk[:2] != b"\x89P" and index in (3, 7) else 34962
        views.append(view)
    # Index views are the ones whose bytes are not floats and not PNG.
    views[3]["target"] = 34963
    if floor_node is not None:
        views[7]["target"] = 34963
    for index in range(len(chunks) - len(images), len(chunks)):
        views[index].pop("target", None)
    cube_uv_count = len(uv) // 8
    accessors = [
        {"bufferView": 0, "componentType": 5126, "count": len(pos) // 12, "type": "VEC3", "min": [0, 0, 0], "max": [1, 1, 1]},
        {"bufferView": 1, "componentType": 5126, "count": len(norm) // 12, "type": "VEC3", "min": [-1, -1, -1], "max": [1, 1, 1]},
        {"bufferView": 3, "componentType": 5126, "count": cube_uv_count, "type": "VEC2", "min": [0, 0], "max": [1, 1]},
        {"bufferView": 2, "componentType": 5123, "count": len(idx) // 2, "type": "SCALAR"},
    ]
    # POSITION 0, NORMAL 1, TEXCOORD 2, INDICES 3 for the cube.
    # I packed uv before idx in `chunks` but the accessor order above uses bufferView 3 for uv
    # and bufferView 2 for indices. chunks order is pos, norm, uv, idx so:
    # view 0 pos, 1 norm, 2 uv, 3 idx. Fix the accessors to match.
    accessors = [
        {"bufferView": 0, "componentType": 5126, "count": len(pos) // 12, "type": "VEC3", "min": [0, 0, 0], "max": [1, 1, 1]},
        {"bufferView": 1, "componentType": 5126, "count": len(norm) // 12, "type": "VEC3", "min": [-1, -1, -1], "max": [1, 1, 1]},
        {"bufferView": 2, "componentType": 5126, "count": len(uv) // 8, "type": "VEC2", "min": [0, 0], "max": [1, 1]},
        {"bufferView": 3, "componentType": 5123, "count": len(idx) // 2, "type": "SCALAR"},
    ]
    views[2].pop("target", None)
    views[2]["target"] = 34962
    views[3]["target"] = 34963
    floor_accessor = None
    if floor_node is not None:
        floor_accessor = len(accessors)
        accessors.extend([
            {"bufferView": 4, "componentType": 5126, "count": floor_counts[0], "type": "VEC3", "min": [0, 0, 0], "max": [1, 1, 1]},
            {"bufferView": 5, "componentType": 5126, "count": floor_counts[1], "type": "VEC3", "min": [-1, -1, -1], "max": [1, 1, 1]},
            {"bufferView": 6, "componentType": 5126, "count": floor_counts[2], "type": "VEC2"},
            {"bufferView": 7, "componentType": 5123, "count": floor_counts[3], "type": "SCALAR"},
        ])
        views[4]["target"] = 34962
        views[5]["target"] = 34962
        views[6]["target"] = 34962
        views[7]["target"] = 34963
    image_views = list(range(len(views) - len(images), len(views)))
    document = {
        "asset": {"version": "2.0", "generator": "kitchen-designer", "extras": {"products": [line for line in (products or []) if line]}},
        "scene": 0,
        "scenes": [{"nodes": list(range(len(nodes)))}],
        "nodes": nodes,
        "materials": [
            _material("cabinet", [0.93, 0.93, 0.91], 0.0, 0.42, image_index["paint"]),
            _material("door", [0.97, 0.97, 0.96], 0.02, 0.34, image_index["paint"]),
            _material("worktop", [0.90, 0.89, 0.86], 0.08, 0.16, image_index["marble"]),
            _material("appliance", [0.74, 0.75, 0.77], 0.88, 0.2, image_index["metal"]),
            _material("filler", [0.78, 0.78, 0.76], 0.0, 0.55, image_index["paint"]),
            _material("wall", [0.88, 0.87, 0.84], 0.0, 0.86, image_index["paint"]),
            _material("floor", [0.55, 0.52, 0.48], 0.04, 0.38, image_index["tile"]),
            _material("panel", [0.9, 0.9, 0.88], 0.02, 0.4, image_index["paint"]),
        ],
        "buffers": [{"byteLength": len(blob)}],
        "bufferViews": views,
        "accessors": accessors,
        "samplers": [{"wrapS": 10497, "wrapT": 10497, "magFilter": 9729, "minFilter": 9987}],
        "images": [{"bufferView": view, "mimeType": "image/png"} for view in image_views],
        "textures": [{"sampler": 0, "source": index} for index in range(len(images))],
    }
    extras = {}
    prepared = []
    for node in nodes:
        material = int(node.pop("material"))
        color = node.pop("color", None)
        surface = node.pop("surface", None)
        if color:
            metallic = 0.0 if node.get("metallic") is None else float(node.get("metallic"))
            roughness = 0.55 if node.get("roughness") is None else float(node.get("roughness"))
            kind = _surface_for(node.get("name") or "", metallic, roughness, surface)
            key = (
                round(float(color[0]), 4),
                round(float(color[1]), 4),
                round(float(color[2]), 4),
                round(metallic, 3),
                round(roughness, 3),
                kind,
            )
            if key not in extras:
                extras[key] = len(document["materials"])
                document["materials"].append(_material(
                    f"color-{len(extras)}",
                    [key[0], key[1], key[2]],
                    key[3],
                    key[4],
                    image_index[kind],
                ))
            material = extras[key]
        node.pop("metallic", None)
        node.pop("roughness", None)
        prepared.append((node, material))
    meshes = []
    for material in document["materials"]:
        meshes.append({
            "name": material["name"],
            "primitives": [{
                "attributes": {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2},
                "indices": 3,
                "material": len(meshes),
            }],
        })
    floor_mesh = None
    if floor_accessor is not None:
        floor_mesh = len(meshes)
        floor_material = next(material for node, material in prepared if node.get("name") == "floor")
        meshes.append({
            "name": "floor-grid",
            "primitives": [{
                "attributes": {
                    "POSITION": floor_accessor,
                    "NORMAL": floor_accessor + 1,
                    "TEXCOORD_0": floor_accessor + 2,
                },
                "indices": floor_accessor + 3,
                "material": floor_material,
            }],
        })
    document["meshes"] = meshes
    cleaned = []
    for node, material in prepared:
        entry = {
            "name": node["name"],
            "mesh": floor_mesh if node.get("name") == "floor" and floor_mesh is not None else material,
            "translation": [round(v, 5) for v in node["translation"]],
            "scale": [round(v, 5) for v in node["scale"]],
        }
        if node.get("extras"):
            entry["extras"] = {"product": node["extras"].get("product") or "", "article": node["extras"].get("article") or ""}
        cleaned.append(entry)
    document["nodes"] = cleaned
    document["scenes"][0]["nodes"] = list(range(len(cleaned)))
    json_chunk = _pad(json.dumps(document, separators=(",", ":")).encode(), b" ")
    total = 12 + 8 + len(json_chunk) + 8 + len(blob)
    header = struct.pack("<4sII", b"glTF", 2, total)
    out = bytearray(header)
    out += struct.pack("<I4s", len(json_chunk), b"JSON")
    out += json_chunk
    out += struct.pack("<I4s", len(blob), b"BIN\x00")
    out += blob
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(out)
    return {"path": str(path), "bytes": len(out), "nodes": len(cleaned)}


def box(name: str, material: int, x: float, y: float, z: float, sx: float, sy: float, sz: float) -> dict:
    """Axis-aligned box in inches, converted to meters. Zero thickness is skipped by the caller."""
    return {
        "name": name,
        "material": material,
        "translation": [x * INCH, y * INCH, z * INCH],
        "scale": [sx * INCH, sy * INCH, sz * INCH],
    }


def world(origin: tuple[float, float], direction: tuple[float, float], inward: tuple[float, float], along: float, into: float) -> tuple[float, float]:
    return (
        origin[0] + direction[0] * along + inward[0] * into,
        origin[1] + direction[1] * along + inward[1] * into,
    )


def oriented_box(name: str, material: int, frame: dict, along: float, into: float, width: float, depth: float, y: float, height: float) -> dict:
    x0, z0 = world(frame["origin"], frame["direction"], frame["inward"], along, into)
    x1, z1 = world(frame["origin"], frame["direction"], frame["inward"], along + width, into + depth)
    xmin, xmax = min(x0, x1), max(x0, x1)
    zmin, zmax = min(z0, z1), max(z0, z1)
    return box(name, material, xmin, y, zmin, max(xmax - xmin, 0.05), height, max(zmax - zmin, 0.05))
