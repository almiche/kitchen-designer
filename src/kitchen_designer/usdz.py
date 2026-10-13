"""Real-size USDZ for iPhone AR Quick Look. Schematic boxes, same geometry as the GLB."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

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

# Unit-box corners. Faces are reordered so the geometric normal points outward.
_CORNERS = (
    (0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
    (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1),
)
_FACES = (
    ((4, 5, 6, 7), (0.0, 0.0, 1.0)),
    ((1, 0, 3, 2), (0.0, 0.0, -1.0)),
    ((3, 2, 6, 7), (0.0, 1.0, 0.0)),
    ((0, 1, 5, 4), (0.0, -1.0, 0.0)),
    ((1, 2, 6, 5), (1.0, 0.0, 0.0)),
    ((4, 0, 3, 7), (-1.0, 0.0, 0.0)),
)

_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kitchen in AR</title>
<style>
  body { margin: 0; padding: 28px 20px 48px; background: #f4f1ea; color: #1b1d1c;
    font: 17px/1.45 "Iowan Old Style", Palatino, Georgia, serif; }
  main { max-width: 420px; margin: 0 auto; }
  a { color: inherit; }
  img { display: block; width: 100%; height: auto; border-radius: 8px; background: #d9d4cc; }
  p { margin: 0 0 16px; }
</style>
</head>
<body>
<main>
<p>On an iPhone, AirDrop <code>__USDZ__</code> and tap it. Then tap AR and set the kitchen on the floor. It is real size. Pinch to scale it. No extra app.</p>
<p><a rel="ar" href="__USDZ__"><img src="views/facing.png" alt="View the kitchen in AR"></a></p>
<p>Safari shows the AR button on that picture when this page is served over HTTPS. AirDrop, Messages, and Mail open the file directly.</p>
__PRODUCTS__
</main>
</body>
</html>
"""


def _outward(indexes, normal):
    a, b, c = (_CORNERS[indexes[0]], _CORNERS[indexes[1]], _CORNERS[indexes[2]])
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx = uy * vz - uz * vy
    ny = uz * vx - ux * vz
    nz = ux * vy - uy * vx
    if nx * normal[0] + ny * normal[1] + nz * normal[2] < 0:
        return tuple(reversed(indexes))
    return indexes


def _color(node: dict) -> tuple[float, float, float]:
    color = node.get("color")
    if color and len(color) >= 3:
        return (float(color[0]), float(color[1]), float(color[2]))
    material = int(node.get("material") or 0)
    return _FALLBACK[material if 0 <= material < len(_FALLBACK) else 0]


def _prim(name: str, index: int) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in (name or "box"))
    if not cleaned or cleaned[0].isdigit():
        cleaned = "n_" + cleaned
    return f"{cleaned}_{index}"


def _fmt(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".") or "0"


def _triple(value) -> str:
    return "(" + ", ".join(_fmt(channel) for channel in value) + ")"


def _html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _usd_quote(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', "'").replace("\n", " ")


def _usda(nodes: list[dict], notes: list[str] | None = None) -> str:
    usable = []
    for node in nodes:
        scale = node.get("scale") or (0, 0, 0)
        if len(scale) < 3 or scale[0] <= 0 or scale[1] <= 0 or scale[2] <= 0:
            continue
        usable.append(node)
    bottoms = [node["translation"][1] for node in usable]
    lift = -min(bottoms) if bottoms else 0.0

    materials = {}
    assigned = []
    for index, node in enumerate(usable):
        color = _color(node)
        metallic = float(node.get("metallic") or 0.0)
        roughness = node.get("roughness")
        roughness = 0.6 if roughness is None else float(roughness)
        key = (tuple(round(channel, 4) for channel in color), round(metallic, 3), round(roughness, 3))
        if key not in materials:
            materials[key] = f"Mat{len(materials)}"
        assigned.append((index, node, key))

    lines = [
        "#usda 1.0",
        "(",
        '    defaultPrim = "Kitchen"',
        "    metersPerUnit = 1",
        '    upAxis = "Y"',
        '    doc = "' + _usd_quote("Schematic kitchen at real size. " + " | ".join(line for line in (notes or []) if line)) + '"',
        ")",
        "",
        'def Xform "Kitchen" (',
        '    kind = "component"',
        ")",
        "{",
        '    def Scope "Materials"',
        "    {",
    ]
    for key, name in materials.items():
        color, metallic, roughness = key
        lines.extend([
            f'        def Material "{name}"',
            "        {",
            f"            token outputs:surface.connect = </Kitchen/Materials/{name}/Preview.outputs:surface>",
            '            def Shader "Preview"',
            "            {",
            '                uniform token info:id = "UsdPreviewSurface"',
            f"                color3f inputs:diffuseColor = {_triple(color)}",
            f"                float inputs:metallic = {_fmt(metallic)}",
            f"                float inputs:roughness = {_fmt(roughness)}",
            "                token outputs:surface",
            "            }",
            "        }",
        ])
    lines.extend(["    }", ""])

    for index, node, key in assigned:
        tx, ty, tz = node["translation"]
        sx, sy, sz = node["scale"]
        origin = (tx, ty + lift, tz)
        points = []
        for ox, oy, oz in _CORNERS:
            points.append((origin[0] + ox * sx, origin[1] + oy * sy, origin[2] + oz * sz))
        indices = []
        normals = []
        for corners, normal in _FACES:
            for corner in _outward(corners, normal):
                indices.append(str(corner))
                normals.append(_triple(normal))
        ys = [point[1] for point in points]
        xs = [point[0] for point in points]
        zs = [point[2] for point in points]
        extent = f"[{_triple((min(xs), min(ys), min(zs)))}, {_triple((max(xs), max(ys), max(zs)))}]"
        mat = materials[key]
        prim = _prim(node.get("name") or "box", index)
        product = ((node.get("extras") or {}).get("product") or "").strip()
        lines.append(f'    def Mesh "{prim}" (')
        if product:
            lines.append(f'        doc = "{_usd_quote(product)}"')
        lines.extend([
            '        prepend apiSchemas = ["MaterialBindingAPI"]',
            "    )",
            "    {",
            "        uniform bool doubleSided = 1",
            '        uniform token subdivisionScheme = "none"',
            f"        rel material:binding = </Kitchen/Materials/{mat}>",
            f"        float3[] extent = {extent}",
            "        int[] faceVertexCounts = [4, 4, 4, 4, 4, 4]",
            "        int[] faceVertexIndices = [" + ", ".join(indices) + "]",
            "        point3f[] points = [" + ", ".join(_triple(point) for point in points) + "]",
            "        normal3f[] normals = [" + ", ".join(normals) + "] (",
            '            interpolation = "faceVarying"',
            "        )",
            "    }",
        ])
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def _pack(files: list[tuple[str, bytes]]) -> bytes:
    """Uncompressed zip whose file bytes start on 64-byte boundaries. USDZ requires that."""
    locals_ = []
    central = []
    offset = 0
    for name, data in files:
        name_b = name.encode("utf-8")
        crc = zlib.crc32(data) & 0xFFFFFFFF
        base = offset + 30 + len(name_b)
        extra_len = (64 - (base % 64)) % 64
        extra = b"\x00" * extra_len
        header = struct.pack(
            "<IHHHHHIIIHH",
            0x04034B50,
            20,
            0,
            0,
            0,
            0,
            crc,
            len(data),
            len(data),
            len(name_b),
            extra_len,
        )
        locals_.append(header + name_b + extra + data)
        central.append(struct.pack(
            "<IHHHHHHIIIHHHHHII",
            0x02014B50,
            20,
            20,
            0,
            0,
            0,
            0,
            crc,
            len(data),
            len(data),
            len(name_b),
            extra_len,
            0,
            0,
            0,
            0,
            offset,
        ) + name_b + extra)
        offset += len(locals_[-1])
    central_blob = b"".join(central)
    end = struct.pack(
        "<IHHHHIIH",
        0x06054B50,
        0,
        0,
        len(files),
        len(files),
        len(central_blob),
        offset,
        0,
    )
    return b"".join(locals_) + central_blob + end


def write_usdz(path: Path, nodes: list[dict], notes: list[str] | None = None) -> dict:
    """Write a real-size kitchen.usdz and an ar.html link beside it.

    The floor bottom is lifted to y = 0 so Quick Look sets the kitchen on the detected ground.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    usda = _usda(nodes, notes).encode("utf-8")
    payload = _pack([("kitchen.usda", usda)])
    path.write_bytes(payload)
    items = ""
    if notes:
        rows = "".join(f"<li>{_html(line)}</li>" for line in notes if line)
        items = "<h2>Products in this design</h2><ul>" + rows + "</ul>"
    page = path.with_name("ar.html")
    page.write_text(_PAGE.replace("__USDZ__", path.name).replace("__PRODUCTS__", items))
    return {"path": str(path), "bytes": len(payload), "page": str(page)}
