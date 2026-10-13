from __future__ import annotations

from .gltf import box, oriented_box, world
from .labels import describe_corner, describe_item, describe_panel, describe_worktop, tag_node


def money(value: float | None) -> str:
    if value is None:
        return ""
    return f"${value:,.0f}"


def _paint(node: dict, rgb, metallic: float = 0.0, roughness: float = 0.55) -> dict:
    if not rgb:
        return node
    node["color"] = [float(channel) for channel in rgb]
    node["metallic"] = float(metallic)
    node["roughness"] = float(roughness)
    return node


def _metal(item: dict) -> tuple[float, float]:
    finish = item.get("finish")
    if finish == "stainless":
        return 0.9, 0.18
    if finish == "black":
        return 0.55, 0.25
    return 0.06, 0.4


def _shade(rgb, factor: float) -> list[float]:
    return [max(0.02, min(1.0, float(channel) * factor)) for channel in rgb]


def _detail(nodes, name, frame, along, into, width, depth, y, height, color, metal, rough, text, article, surface):
    if width <= 0.08 or depth <= 0.08 or height <= 0.08:
        return
    node = oriented_box(name, 1, frame, along, into, width, depth, y, height)
    _paint(node, color, metal, rough)
    node["surface"] = surface
    nodes.append(tag_node(node, text, article))


def _dress(node: dict, front: dict) -> dict:
    """Paint a door from the chosen front. AXSTAD white keeps the shared white material."""
    node["surface"] = front.get("surface") or "paint"
    node["metallic"] = 0.02 if front.get("metal") is None else float(front.get("metal"))
    node["roughness"] = 0.34 if front.get("rough") is None else float(front.get("rough"))
    color = front.get("color")
    if color:
        _paint(node, color, node["metallic"], node["roughness"])
    return node


def _luminance(rgb) -> float:
    if not rgb:
        return 1.0
    red, green, blue = (float(channel) for channel in list(rgb)[:3])
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _knob_metal(front: dict) -> tuple[list[float], float, float]:
    """Brass on a dark front, nickel on a light one. Both are schematic hardware."""
    if _luminance(front.get("color")) < 0.45:
        return [0.76, 0.58, 0.26], 0.9, 0.18
    return [0.78, 0.79, 0.81], 0.88, 0.16


def _door_detail(nodes, item, frame, text, article, along, into, door_w, door_y, door_h, index, count, front):
    """Raised panel on shaker fronts, and a small knob on every door."""
    look = front.get("look") or "shaker"
    if look in ("shaker", "wood-shaker"):
        if front.get("color"):
            panel_color = [min(1.0, float(channel) * 1.04) for channel in front["color"]]
            surface = front.get("surface") or "paint"
            metal = 0.02 if front.get("metal") is None else float(front.get("metal"))
            rough = 0.34 if front.get("rough") is None else float(front.get("rough"))
        else:
            panel_color = [0.97, 0.97, 0.95]
            surface = "paint"
            metal, rough = 0.03, 0.32
        rail = 1.45
        _detail(
            nodes, f"{item['id']}-panel-{index + 1}", frame,
            along + rail, into, door_w - rail * 2, 0.16, door_y + rail, door_h - rail * 2,
            panel_color, metal, rough, text, article, surface,
        )
    color, metal, rough = _knob_metal(front)
    if count == 1 or index == 0:
        knob_along = along + door_w - 1.15
    else:
        knob_along = along + 0.2
    center = door_y + door_h * 0.5
    _detail(
        nodes, f"{item['id']}-pull-{index + 1}", frame,
        knob_along, into, 0.95, 0.16, center - 0.47, 0.95,
        color, metal, rough, text, article, "metal",
    )
    _detail(
        nodes, f"{item['id']}-knob-{index + 1}", frame,
        knob_along + 0.12, into + 0.16, 0.7, 0.4, center - 0.35, 0.7,
        color, min(1.0, metal + 0.04), max(0.12, rough - 0.04), text, article, "metal",
    )


def _door_gaps(nodes, item, frame, text, article, along, door_w, door_y, door_h, depth, index, count, seam):
    """A dark joint in the reveal so each front reads as its own door."""
    ink = [0.16, 0.15, 0.14]
    into = depth + 0.02

    def line(suffix, line_along, line_y, width, height):
        _detail(
            nodes, f"{item['id']}-gap-{suffix}", frame,
            line_along, into, width, 0.14, line_y, height,
            ink, 0.0, 0.78, text, article, "paint",
        )

    line(f"{index + 1}-top", along, door_y + door_h + 0.1, door_w, 0.12)
    line(f"{index + 1}-bottom", along, door_y - 0.22, door_w, 0.12)
    if index == 0:
        line(f"{index + 1}-side", along - 0.26, door_y, 0.12, door_h)
    if index == count - 1:
        line(f"{index + 1}-end", along + door_w + 0.14, door_y, 0.12, door_h)
    elif seam > 0.12:
        line(f"{index + 1}-seam", along + door_w + (seam - 0.1) / 2, door_y, 0.1, door_h)


def _toe_kick(nodes, name, frame, text, article, along, width, depth):
    _detail(
        nodes, name, frame,
        along + 0.55, depth - 4.8, width - 1.1, 2.2,
        0.12, 3.35,
        [0.07, 0.065, 0.06], 0.02, 0.7, text, article, "paint",
    )


def _under_line(nodes, name, frame, text, article, along, width, depth, y):
    """A thin contact shadow under a counter lip or a wall cabinet."""
    _detail(
        nodes, name, frame,
        along + 0.15, max(depth - 2.2, 0.1), max(width - 0.3, 0.2), min(2.0, depth),
        y - 0.2, 0.16,
        [0.05, 0.045, 0.04], 0.0, 0.92, text, article, "paint",
    )


def _backsplash(nodes, piece, frame, wall_rgb):
    color = _shade(wall_rgb, 0.9) if wall_rgb else [0.84, 0.82, 0.78]
    tile = 6.0
    width = float(piece["width_in"])
    columns = max(1, int(width // tile))
    cell = width / columns
    base = float(piece["y_in"]) + float(piece["height_in"])
    for row in range(3):
        for col in range(columns):
            shade = 0.94 if (row + col) % 2 else 1.0
            _detail(
                nodes, f"splash-{piece['wall_id']}-{col}-{row}", frame,
                float(piece["offset_in"]) + col * cell + 0.18, 0.12, cell - 0.36, 0.4,
                base + row * tile + 0.18, tile - 0.36,
                _shade(color, shade), 0.05, 0.34, "Backsplash tile", "", "tile",
            )


def _appliance_faces(item: dict, frame: dict, ceiling: float) -> list[dict]:
    """Raised panels so a French door, a top freezer, a cooktop, and a faucet read as those things."""
    kind = item["kind"]
    rgb = item.get("finish_rgb")
    if not rgb or kind not in ("fridge", "range", "dishwasher", "hood", "microwave", "faucet"):
        return []
    metallic, roughness = _metal(item)
    face = _shade(rgb, 0.86)
    dark = [0.12, 0.12, 0.13]
    width = float(item["width_in"])
    height = float(item.get("height_in") or 1)
    depth = float(item.get("depth_in") or 1)
    along0 = float(item["offset_in"])
    y0 = float(item.get("y_in") or 0)
    into0 = float(item.get("into_in") or 0)
    gap = 0.3
    proud = 0.4
    nodes = []

    def add(name, along, into, w, d, y, h, color, metal=None, rough=None):
        if w <= 0.05 or d <= 0.05 or h <= 0.05:
            return
        node = oriented_box(name, 3, frame, along, into, w, d, y, h)
        _paint(node, color, metallic if metal is None else metal, roughness if rough is None else rough)
        node["surface"] = "metal" if (metallic if metal is None else metal) >= 0.45 else "paint"
        nodes.append(node)

    if kind == "fridge" and "top" in (item.get("model_id") or ""):
        freezer = max(height * 0.32, 8)
        add(f"{item['id']}-freezer", along0 + gap, depth, width - gap * 2, proud, y0 + height - freezer + gap, freezer - gap * 2, face)
        add(f"{item['id']}-fridge-door", along0 + gap, depth, width - gap * 2, proud, y0 + gap, height - freezer - gap * 2, face)
    elif kind == "fridge":
        freezer = max(height * 0.22, 8)
        door_h = height - freezer - gap * 3
        door_w = (width - gap * 3) / 2
        for index in (0, 1):
            add(
                f"{item['id']}-door-{index + 1}",
                along0 + gap + index * (door_w + gap),
                depth,
                door_w,
                proud,
                y0 + freezer + gap * 2,
                door_h,
                face,
            )
        add(f"{item['id']}-freezer", along0 + gap, depth, width - gap * 2, proud, y0 + gap, freezer - gap, face)
        for index in (0, 1):
            handle_along = along0 + gap + door_w - 1.15 if index == 0 else along0 + gap + door_w + gap + 0.45
            add(
                f"{item['id']}-pull-{index + 1}",
                handle_along,
                depth + proud,
                0.5,
                0.4,
                y0 + freezer + door_h * 0.45,
                min(8.0, door_h * 0.28),
                _shade(rgb, 0.78),
                0.88,
                0.16,
            )
    elif kind == "range":
        add(f"{item['id']}-cooktop", along0 + 0.6, 0.8, width - 1.2, max(depth - 1.6, 1), y0 + height, 0.35, dark, 0.15, 0.4)
        burner = 4.2
        for col, row in ((0.27, 0.32), (0.73, 0.32), (0.27, 0.68), (0.73, 0.68)):
            add(
                f"{item['id']}-burner-{col:.2f}-{row:.2f}",
                along0 + width * col - burner / 2,
                depth * row - burner / 2,
                burner,
                burner,
                y0 + height + 0.35,
                0.35,
                _shade(rgb, 0.7),
            )
        add(f"{item['id']}-oven", along0 + gap, depth, width - gap * 2, proud, y0 + gap, height * 0.62, face)
    elif kind == "dishwasher":
        add(f"{item['id']}-front", along0 + gap, depth, width - gap * 2, proud, y0 + gap, height - gap * 2, face)
        handle_w = max(width * 0.35, 4)
        add(
            f"{item['id']}-handle",
            along0 + (width - handle_w) / 2,
            depth + proud,
            handle_w,
            0.35,
            y0 + height * 0.72,
            0.55,
            _shade(rgb, 0.7),
        )
    elif kind == "hood":
        chimney_w = min(12.0, max(width - 2, 4))
        chimney_h = min(16.0, ceiling - (y0 + height) - 1)
        add(
            f"{item['id']}-chimney",
            along0 + (width - chimney_w) / 2,
            0,
            chimney_w,
            min(12.0, depth),
            y0 + height,
            chimney_h,
            face,
        )
    elif kind == "microwave":
        add(
            f"{item['id']}-window",
            along0 + width * 0.12,
            into0 + depth,
            width * 0.5,
            proud,
            y0 + height * 0.22,
            height * 0.5,
            dark,
            0.1,
            0.25,
        )
    elif kind == "faucet":
        spout_w = min(1.4, width * 0.7)
        add(
            f"{item['id']}-spout",
            along0 + (width - spout_w) / 2,
            into0 + depth * 0.35,
            spout_w,
            max(depth * 0.7, 3),
            y0 + height * 0.62,
            max(height * 0.14, 0.8),
            face,
        )
    return nodes


def render_packet(design: dict) -> str:
    room = design["room"]
    lines = [
        f"# {room['name']}",
        "",
        "Schematic SEKTION layout for a Canada kitchen. Cabinet boxes in the GLB are original geometry at published module sizes.",
        f"Prices are IKEA.ca figures from {design['price_as_of']} in {design['currency']}. Check each article before buying.",
        "",
        "## Room",
        "",
        f"- Shape: {room['shape']}",
        f"- Ceiling: {room['ceiling_height_in']:.0f} inches",
    ]
    if room.get("room_depth_in"):
        lines.append(f"- Wall-to-wall depth: {room['room_depth_in']:.0f} inches")
    finish = (design.get("preferences") or {}).get("finish")
    if finish:
        lines.append(f"- Appliance finish: {finish}")
    for label, key in (("Floor", "floor"), ("Walls", "wall"), ("Surround", "surround")):
        hex_color = (room.get("color_hex") or {}).get(key)
        if hex_color:
            lines.append(f"- {label}: {hex_color}")
    for wall in room["walls"]:
        bits = [f"{op['kind']} at {op['offset_in']:.0f} inches, {op['width_in']:.0f} wide" for op in wall["openings"]]
        extra = "; ".join(bits) if bits else "no openings"
        lines.append(f"- Wall {wall['id']}: {wall['length_in']:.0f} inches ({extra})")
    if room.get("photo_observations"):
        lines.extend(["", "## From the photo", "", room["photo_observations"]])
    if room.get("notes"):
        lines.extend(["", "## Notes", "", room["notes"]])
    lines.extend(["", "## Layout", ""])
    frames = {frame["id"]: frame for frame in design["frames"]}
    for frame in design["frames"]:
        lines.append(f"### {frame['id']} ({frame['length_in']:.0f} inches)")
        lines.append("")
        rows = [item for item in design["items"] if item.get("wall_id") == frame["id"]]
        rows.sort(key=lambda item: item["offset_in"])
        if not rows:
            lines.append("No modules on this wall.")
        for item in rows:
            text, _short, _article = describe_item(item, design)
            lines.append(
                f"- {item['offset_in']:.0f}–{item['offset_in'] + item['width_in']:.0f} in: {text}"
            )
        lines.append("")
    if design["corners"]:
        lines.append("Corners use one frame per turn. The 38 inch base corner and the 26 inch wall corner are the Canada frames.")
        lines.append("")
    appliances = design.get("appliances") or []
    if appliances:
        lines.extend([
            "## Appliances",
            "",
            "Schematic bodies at published opening sizes. They are not on the IKEA purchase list and they are not manufacturer models.",
            "Sizes are width x depth x height.",
            "",
        ])
        for row in appliances:
            state = "placed" if row.get("placed") else "listed, not placed in this run"
            examples = f" {row['examples']}" if row.get("examples") else ""
            lines.append(
                f"- {row['name']}, {row['finish']}, "
                f"{row['width_in']:g} x {row['depth_in']:g} x {row['height_in']:g} in, {state}.{examples}"
            )
        lines.append("")
    buy = design.get("buy") or {}
    if buy:
        lines.extend(["## What to buy", ""])
        front_name = buy.get("front_name") or buy.get("front_id") or ""
        sentence = buy.get("sentence") or ""
        lines.append(f"Front: {front_name}. {sentence}".strip())
        if buy.get("color_note"):
            lines.append(buy["color_note"])
        lines.append("")

        def section(title: str, rows: list) -> None:
            if not rows:
                return
            lines.append(f"### {title}")
            lines.append("")
            for row in rows:
                lines.append(f"- {row}")
            lines.append("")

        section("Cabinets", buy.get("cabinets") or [])
        section("Hardware", buy.get("hardware") or [])
        section("Cover panels and fillers", buy.get("panels") or [])
        section("Countertops", buy.get("worktops") or [])
        section("Still to resolve", buy.get("unresolved") or [])
        if buy.get("total"):
            lines.append(buy["total"])
            lines.append("")
    lines.extend(["## Purchase list", ""])
    lines.append("| Article | Item | Qty | Packs to buy | Each | Line |")
    lines.append("| --- | --- | ---: | ---: | ---: | ---: |")
    unresolved = []
    for line in design["bom"]:
        if not line.get("article"):
            unresolved.append(line)
            continue
        lines.append(
            f"| {line['article']} | {line['name']} | {line['qty']} | {line['packs']} | "
            f"{money(line['unit_price_cad'])} | {money(line['line_total_cad'])} |"
        )
    lines.append("")
    filler_items = [item for item in design["items"] if item["kind"] in ("filler", "wall_filler")]
    if filler_items:
        inches = sum(item["width_in"] for item in filler_items)
        lines.append(
            f"Filler strips add up to {inches:.1f} inches. Cut them from the cover panels on this list. "
            "A side panel is a whole panel on an exposed cabinet end."
        )
    lines.append(f"Priced subtotal: {money(design['total_price_cad'])}.")
    lines.append("The subtotal leaves out appliances, the sink bowl, lighting, delivery, and tax.")
    if unresolved:
        lines.extend(["", "## Not a stocked article in this catalog", ""])
        for line in unresolved:
            lines.append(f"- {line['name']}")
    if design["warnings"]:
        lines.extend(["", "## Check these", ""])
        for warning in design["warnings"]:
            lines.append(f"- {warning}")
    printed = design.get("print") or {}
    if printed:
        scale = int(printed.get("scale") or (design.get("preferences") or {}).get("print_scale") or 20)
        lines.extend([
            "",
            "## Print",
            "",
            f"Scale is 1:{scale}. kitchen.stl is the whole kitchen. "
            "print/cabinets.stl is the cabinets, fillers, and side panels. "
            "print/kitchen-without-cabinets.stl is the kitchen with those cabinets taken out.",
            "The STL is one material. Floor, wall, and surround colors are on the GLB.",
            "print/products.txt names the cabinets and products in the print files.",
            "Thin parts are raised to about 1.6 mm so a desktop printer can make them.",
        ])
    views = design.get("views") or {}
    if views.get("images"):
        eye = int(views.get("eye_in") or 62)
        lines.extend([
            "",
            "## First person",
            "",
            f"Eye height is {eye} inches. Open walk.html in a browser, click the view, and walk with WASD. Look with the mouse.",
            "",
        ])
        for image in views["images"]:
            lines.append(f"![{image['label']}]({image['file']})")
            lines.append("")
    if design.get("ar"):
        lines.extend([
            "",
            "## On an iPhone",
            "",
            "AirDrop kitchen.usdz to the iPhone and tap it. Tap AR and place the kitchen on the floor. "
            "The model is real size. Pinch to scale it. No extra app is required.",
            "ar.html is the same file as a picture link. Safari shows the AR button when that page is served over HTTPS.",
            "",
        ])
    lines.extend([
        "",
        "## Drawing notes",
        "",
        "- Base frames are 30 inches high and 24 inches deep, on 4 1/2 inch legs.",
        "- The worktop in the model is 1 1/8 inches thick and 25 5/8 inches deep. Search listings used here print length and thickness; confirm the depth on the product page.",
        "- Wall cabinets sit 18 inches above the worktop.",
        "- A 36 inch sink opening is left without a wall cabinet. The range has no cabinet above it. A 20 inch cabinet sits on the fridge when that frame exists.",
        "- Worktop boards are full lengths. Cut them to the runs. Joints are not drawn.",
        "- Shelves, drawers, and the sink bowl are not expanded into articles. Appliance bodies in the model are schematic.",
        "- Filler strips are cut from cover panels. A door cabinet keeps 2 inches clear of a wall. A refrigerator keeps 4 inches clear of a wall.",
        "",
    ])
    return "\n".join(lines)


def build_nodes(design: dict, catalog: dict) -> list[dict]:
    from .catalog import front_by_id
    from .solve import corner_set, plan_doors

    nodes: list[dict] = []
    style = ((design.get("preferences") or {}).get("front_style")) or "axstad-white"
    front = front_by_id(catalog, style) or {
        "id": style,
        "look": "shaker",
        "surface": "paint",
        "metal": 0.02,
        "rough": 0.34,
    }
    corner_door = corner_set(catalog, style)
    frames = {frame["id"]: frame for frame in design["frames"]}
    ceiling = design["room"]["ceiling_height_in"]
    colors = design["room"].get("colors") or {}
    xs: list[float] = []
    zs: list[float] = []
    for frame in design["frames"]:
        shell = oriented_box(
            f"shell-{frame['id']}", 5, frame, 0, -4, frame["length_in"], 4, 0, ceiling,
        )
        nodes.append(_paint(shell, colors.get("wall"), 0.0, 0.9))
        if colors.get("surround"):
            backdrop = oriented_box(
                f"surround-{frame['id']}", 5, frame, 0, -8, frame["length_in"], 2, 0, ceiling,
            )
            nodes.append(_paint(backdrop, colors["surround"], 0.0, 0.95))
        for along in (0, frame["length_in"]):
            for into in (0, 24):
                x, z = world(frame["origin"], frame["direction"], frame["inward"], along, into)
                xs.append(x)
                zs.append(z)
    if xs:
        pad = 30
        floor = box(
            "floor", 6,
            min(xs) - pad, -0.4, min(zs) - pad,
            max(xs) - min(xs) + pad * 2, 0.4, max(zs) - min(zs) + pad * 2,
        )
        _paint(floor, colors.get("floor"), 0.1, 0.26)
        floor["surface"] = "tile"
        nodes.append(floor)
    for item in design["items"]:
        frame = frames[item["wall_id"]]
        appliance = item["kind"] in ("fridge", "range", "dishwasher", "hood", "microwave", "faucet")
        material = 4 if item["kind"] in ("filler", "wall_filler") else 3 if appliance else 0
        full, short, article = describe_item(item, design)
        body = oriented_box(
            f"{item['id']} {short}", material, frame,
            item["offset_in"], item.get("into_in", 0), item["width_in"], item.get("depth_in", 24),
            item.get("y_in", 0), item.get("height_in", 30),
        )
        tag_node(body, full, article)
        if appliance and item.get("finish_rgb"):
            metallic, roughness = _metal(item)
            _paint(body, item["finish_rgb"], metallic, roughness)
            body["surface"] = "metal"
        elif not appliance:
            body["surface"] = "paint"
            body["metallic"] = 0.0
            body["roughness"] = 0.42
        nodes.append(body)
        for face in _appliance_faces(item, frame, ceiling):
            tag_node(face, full, article)
            nodes.append(face)
        if item["kind"] in ("base", "sink_base", "wall", "over_fridge"):
            full_h = 30.0 if item["kind"] in ("base", "sink_base") else float(item["height_in"])
            base_y = float(item.get("y_in", 4.5 if item["kind"] in ("base", "sink_base") else 0))
            reveal = 0.4
            seam = 0.22
            doors = plan_doors(catalog, item["width_in"], full_h, style)
            count = max(len(doors), 1)
            door_w = (float(item["width_in"]) - reveal * 2 - seam * (count - 1)) / count
            door_h = full_h - reveal * 2
            door_y = base_y + reveal
            depth = float(item.get("depth_in", 24))
            for index in range(count):
                along = float(item["offset_in"]) + reveal + index * (door_w + seam)
                door = oriented_box(
                    f"{item['id']}-door-{index + 1} {short}", 1, frame,
                    along, depth - 0.08, door_w, 0.5, door_y, door_h,
                )
                _dress(door, front)
                door_article = (doors[index] or {}).get("article") if index < len(doors) and doors[index] else article
                nodes.append(tag_node(door, full, door_article))
                _door_detail(
                    nodes, item, frame, full, door_article,
                    along, depth + 0.42, door_w, door_y, door_h, index, count, front,
                )
                _door_gaps(
                    nodes, item, frame, full, door_article,
                    along, door_w, door_y, door_h, depth, index, count, seam,
                )
            if item["kind"] in ("base", "sink_base"):
                _toe_kick(nodes, f"{item['id']}-toe", frame, full, article, float(item["offset_in"]), float(item["width_in"]), depth)
            else:
                _under_line(nodes, f"{item['id']}-under", frame, full, article, float(item["offset_in"]), float(item["width_in"]), depth, base_y)
    for piece in design["worktops"]:
        frame = frames[piece["wall_id"]]
        full, short, article = describe_worktop(piece, design)
        worktop = oriented_box(
            f"worktop-{piece['wall_id']}-{piece['offset_in']:.0f} {short}", 2, frame,
            piece["offset_in"], 0, piece["width_in"], piece["depth_in"], piece["y_in"], piece["height_in"],
        )
        worktop["surface"] = "marble"
        worktop["metallic"] = 0.08
        worktop["roughness"] = 0.16
        nodes.append(tag_node(worktop, full, article))
        lip = oriented_box(
            f"worktop-{piece['wall_id']}-edge", 2, frame,
            piece["offset_in"], piece["depth_in"], piece["width_in"], 0.45, piece["y_in"], piece["height_in"],
        )
        _paint(lip, [0.94, 0.93, 0.9], 0.12, 0.12)
        lip["surface"] = "marble"
        nodes.append(tag_node(lip, full, article))
        _under_line(
            nodes, f"worktop-{piece['wall_id']}-shadow", frame, full, article,
            float(piece["offset_in"]), float(piece["width_in"]), float(piece["depth_in"]), float(piece["y_in"]),
        )
        _backsplash(nodes, piece, frame, colors.get("wall"))
    for corner in design["corners"]:
        material = 0
        for wall_id, end in corner["ends"].items():
            frame = frames[wall_id]
            offset = 0 if end == "start" else frame["length_in"] - corner["span_in"]
            full, short, article = describe_corner(corner)
            piece = oriented_box(
                f"{corner['id']}-{wall_id} {short}", material, frame,
                offset, 0, corner["span_in"], corner["depth_in"], corner["y_in"], corner["height_in"],
            )
            piece["surface"] = "paint"
            piece["metallic"] = 0.0
            piece["roughness"] = 0.42
            nodes.append(tag_node(piece, full, article))
            if corner["kind"] == "corner_base" and float(corner["span_in"]) >= 13:
                reveal = 0.4
                door_w = 13.0 - reveal * 2
                door_along = offset + float(corner["span_in"]) - 13.0 + reveal if end == "start" else offset + reveal
                door_y = float(corner["y_in"]) + reveal
                door_h = float(corner["height_in"]) - reveal * 2
                depth = float(corner["depth_in"])
                door_article = (corner_door or {}).get("article") or article
                slab = oriented_box(
                    f"{corner['id']}-door-{wall_id}", 1, frame,
                    door_along, depth - 0.08, door_w, 0.5, door_y, door_h,
                )
                _dress(slab, front)
                nodes.append(tag_node(slab, full, door_article))
                _door_detail(
                    nodes, corner, frame, full, door_article,
                    door_along, depth + 0.42, door_w, door_y, door_h, 0, 1, front,
                )
                _door_gaps(
                    nodes, {"id": f"{corner['id']}-{wall_id}"}, frame, full, door_article,
                    door_along, door_w, door_y, door_h, depth, 0, 1, 0.0,
                )
                _toe_kick(
                    nodes, f"{corner['id']}-toe-{wall_id}", frame, full, article,
                    offset, float(corner["span_in"]), depth,
                )
            elif corner["kind"] == "corner_wall":
                _under_line(
                    nodes, f"{corner['id']}-under-{wall_id}", frame, full, article,
                    offset, float(corner["span_in"]), float(corner["depth_in"]), float(corner["y_in"]),
                )
    for index, panel in enumerate(design["panels"], start=1):
        frame = frames[panel["wall_id"]]
        along = panel["offset_in"] - 0.75 if panel["side"] == "start" else panel["offset_in"]
        host = panel["host"]
        full, short, article = describe_panel(panel, design)
        side = oriented_box(
            f"panel-{index} {short}", 7, frame,
            along, 0, 0.75, host.get("depth_in", 24), 0, host.get("y_in", 4.5) + host.get("height_in", 30),
        )
        side["surface"] = "paint"
        side["metallic"] = 0.02
        side["roughness"] = 0.4
        nodes.append(tag_node(side, full, article))
    return nodes
