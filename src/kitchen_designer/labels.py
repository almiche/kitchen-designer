"""Names for the cabinets and products in a design, shared by every output."""

from __future__ import annotations

import math

from .gltf import world

_KINDS = {
    "base": "Base cabinet",
    "sink_base": "Sink base",
    "wall": "Wall cabinet",
    "over_fridge": "Over-fridge cabinet",
    "filler": "Filler",
    "wall_filler": "Wall filler",
}
_APPLIANCE = {"fridge", "range", "dishwasher", "hood", "microwave", "faucet"}

# 5x7 glyphs, one row per string. Used to stamp stills without a font library.
_FONT = {
    " ": ["     "] * 7,
    "A": [" ### ", "#   #", "#   #", "#####", "#   #", "#   #", "#   #"],
    "B": ["#### ", "#   #", "#   #", "#### ", "#   #", "#   #", "#### "],
    "C": [" ### ", "#   #", "#    ", "#    ", "#    ", "#   #", " ### "],
    "D": ["#### ", "#   #", "#   #", "#   #", "#   #", "#   #", "#### "],
    "E": ["#####", "#    ", "#    ", "#### ", "#    ", "#    ", "#####"],
    "F": ["#####", "#    ", "#    ", "#### ", "#    ", "#    ", "#    "],
    "G": [" ### ", "#   #", "#    ", "#  ##", "#   #", "#   #", " ### "],
    "H": ["#   #", "#   #", "#   #", "#####", "#   #", "#   #", "#   #"],
    "I": ["#####", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "#####"],
    "J": ["  ###", "   # ", "   # ", "   # ", "#  # ", "#  # ", " ##  "],
    "K": ["#   #", "#  # ", "# #  ", "##   ", "# #  ", "#  # ", "#   #"],
    "L": ["#    ", "#    ", "#    ", "#    ", "#    ", "#    ", "#####"],
    "M": ["#   #", "## ##", "# # #", "# # #", "#   #", "#   #", "#   #"],
    "N": ["#   #", "##  #", "# # #", "#  ##", "#   #", "#   #", "#   #"],
    "O": [" ### ", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "],
    "P": ["#### ", "#   #", "#   #", "#### ", "#    ", "#    ", "#    "],
    "Q": [" ### ", "#   #", "#   #", "#   #", "# # #", "#  # ", " ## #"],
    "R": ["#### ", "#   #", "#   #", "#### ", "# #  ", "#  # ", "#   #"],
    "S": [" ####", "#    ", "#    ", " ### ", "    #", "    #", "#### "],
    "T": ["#####", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "  #  "],
    "U": ["#   #", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "],
    "V": ["#   #", "#   #", "#   #", "#   #", "#   #", " # # ", "  #  "],
    "W": ["#   #", "#   #", "#   #", "# # #", "# # #", "## ##", "#   #"],
    "X": ["#   #", "#   #", " # # ", "  #  ", " # # ", "#   #", "#   #"],
    "Y": ["#   #", "#   #", " # # ", "  #  ", "  #  ", "  #  ", "  #  "],
    "Z": ["#####", "    #", "   # ", "  #  ", " #   ", "#    ", "#####"],
    "0": [" ### ", "#   #", "#  ##", "# # #", "##  #", "#   #", " ### "],
    "1": ["  #  ", " ##  ", "  #  ", "  #  ", "  #  ", "  #  ", " ### "],
    "2": [" ### ", "#   #", "    #", "  ## ", " #   ", "#    ", "#####"],
    "3": ["#### ", "    #", "    #", " ### ", "    #", "    #", "#### "],
    "4": ["   # ", "  ## ", " # # ", "#  # ", "#####", "   # ", "   # "],
    "5": ["#####", "#    ", "#    ", "#### ", "    #", "#   #", " ### "],
    "6": [" ### ", "#    ", "#    ", "#### ", "#   #", "#   #", " ### "],
    "7": ["#####", "    #", "   # ", "  #  ", " #   ", " #   ", " #   "],
    "8": [" ### ", "#   #", "#   #", " ### ", "#   #", "#   #", " ### "],
    "9": [" ### ", "#   #", "#   #", " ####", "    #", "    #", " ### "],
    ".": ["     ", "     ", "     ", "     ", "     ", " ##  ", " ##  "],
    ",": ["     ", "     ", "     ", "     ", "  #  ", "  #  ", " #   "],
    "-": ["     ", "     ", "     ", " ### ", "     ", "     ", "     "],
    "|": ["  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "  #  "],
    "(": ["   # ", "  #  ", " #   ", " #   ", " #   ", "  #  ", "   # "],
    ")": [" #   ", "  #  ", "   # ", "   # ", "   # ", "  #  ", " #   "],
    "/": ["    #", "   # ", "   # ", "  #  ", " #   ", " #   ", "#    "],
}


def _cover(design: dict | None) -> tuple[str, str]:
    for line in (design or {}).get("bom") or []:
        name = line.get("name") or ""
        if line.get("article") and "cover panel" in name.lower():
            return line["article"], name
    return "", ""


def _boards(design: dict | None) -> list[dict]:
    found = []
    for line in (design or {}).get("bom") or []:
        name = (line.get("name") or "").lower()
        if line.get("article") and ("countertop" in name or "worktop" in name):
            found.append(line)
    return found


def _num(value) -> str:
    number = float(value)
    if abs(number - round(number)) < 0.05:
        return str(int(round(number)))
    return f"{number:.3f}".rstrip("0").rstrip(".")


def _size_phrase(width, depth, height, offset=None, bottom=None) -> str:
    """Width x depth x height, the run it occupies, and the height of its bottom."""
    bits = []
    dims = [_num(value) for value in (width, depth, height) if value is not None]
    if len(dims) == 3:
        bits.append(f"{dims[0]} x {dims[1]} x {dims[2]} in")
    elif width is not None and height is not None:
        bits.append(f"{_num(width)} in wide, {_num(height)} in high")
    if offset is not None and width is not None:
        bits.append(f"from {_num(offset)} to {_num(float(offset) + float(width))} in")
    if bottom is not None:
        bits.append(f"bottom at {_num(bottom)} in")
    return " · ".join(bits)


def describe_item(item: dict, design: dict | None = None) -> tuple[str, str, str]:
    """Full label, short label, and article number for one placed piece."""
    kind = item.get("kind") or ""
    article = item.get("article_no") or ""
    name = item.get("name") or ""
    width = item.get("width_in")
    size = f", {float(width):.0f} in" if width else ""
    phrase = _size_phrase(width, item.get("depth_in"), item.get("height_in"), item.get("offset_in"), item.get("y_in"))
    if kind in _APPLIANCE:
        text = name or kind.replace("_", " ")
        finish = item.get("finish") or ""
        if finish and finish.lower() not in text.lower():
            text = f"{text}, {finish}"
        short = text
        if phrase:
            text = f"{text}, {phrase}"
        return f"{text} (schematic, not an IKEA article)", short, ""
    if kind in ("filler", "wall_filler"):
        cover_no, cover_name = _cover(design)
        text = f"Filler{size}"
        if cover_no:
            text += f", cut from {cover_name} · {cover_no}"
        if phrase:
            text += f" · {phrase}"
        return text, f"Filler {cover_no}".strip(), cover_no
    role = _KINDS.get(kind, kind.replace("_", " ") or "Cabinet")
    text = f"{role}{size}"
    if name:
        text += f" · {name}"
    if article:
        text += f" · {article}"
    if phrase:
        text += f" · {phrase}"
    return text, f"{role} {article}".strip(), article


def describe_worktop(piece: dict, design: dict | None = None) -> tuple[str, str, str]:
    boards = _boards(design)
    text = f"Worktop, {float(piece['width_in']):.0f} in run"
    article = ""
    if boards:
        article = boards[0].get("article") or ""
        bits = [f"{board.get('name') or 'Worktop'} · {board.get('article')}" for board in boards]
        text += ", cut from " + "; ".join(bits)
    phrase = _size_phrase(piece.get("width_in"), piece.get("depth_in"), piece.get("height_in"), piece.get("offset_in"), piece.get("y_in"))
    if phrase:
        text += f" · {phrase}"
    short = f"Worktop {article}".strip()
    return text, short, article


def describe_corner(corner: dict) -> tuple[str, str, str]:
    article = corner.get("article_no") or ""
    name = corner.get("name") or corner.get("kind") or "Corner"
    text = f"{name}, {float(corner.get('span_in') or 0):.0f} in"
    if article:
        text += f" · {article}"
    phrase = _size_phrase(
        corner.get("span_in"), corner.get("depth_in"), corner.get("height_in"), None, corner.get("y_in"),
    )
    if phrase:
        text += f" · {phrase}"
    return text, f"Corner {article}".strip(), article


def describe_panel(panel: dict, design: dict | None = None) -> tuple[str, str, str]:
    cover_no, cover_name = _cover(design)
    text = "Side cover panel"
    if cover_name:
        text += f" · {cover_name}"
    if cover_no:
        text += f" · {cover_no}"
    host = panel.get("host") or {}
    height = float(host.get("y_in") or 0) + float(host.get("height_in") or 0)
    phrase = _size_phrase(0.75, host.get("depth_in"), height or None, panel.get("offset_in"), 0)
    if phrase:
        text += f" · {phrase}"
    return text, f"Cover panel {cover_no}".strip(), cover_no


def tag_node(node: dict, text: str, article: str = "") -> dict:
    node["extras"] = {"product": text, "article": article or ""}
    return node


def _anchor(frame: dict, along: float, into: float) -> tuple[float, float]:
    return world(frame["origin"], frame["direction"], frame["inward"], along, into)


def callouts(design: dict) -> list[dict]:
    """One label per cabinet, appliance, worktop, corner, and side panel."""
    frames = {frame["id"]: frame for frame in design.get("frames") or []}
    rows = []

    def add(kind, text, short, article, wall_id, along, into, y):
        frame = frames.get(wall_id)
        if frame is None:
            return
        x, z = _anchor(frame, along, into)
        rows.append({
            "kind": kind,
            "text": text,
            "short": short,
            "article": article,
            "x": x,
            "y": y,
            "z": z,
        })

    for item in design.get("items") or []:
        text, short, article = describe_item(item, design)
        depth = float(item.get("depth_in") or 24)
        into = float(item.get("into_in") or 0) + depth
        y = float(item.get("y_in") or 0) + float(item.get("height_in") or 30) * 0.5
        along = float(item["offset_in"]) + float(item["width_in"]) * 0.5
        add(item.get("kind") or "", text, short, article, item.get("wall_id"), along, into, y)
    for piece in design.get("worktops") or []:
        text, short, article = describe_worktop(piece, design)
        along = float(piece["offset_in"]) + float(piece["width_in"]) * 0.5
        y = float(piece["y_in"]) + float(piece["height_in"])
        add("worktop", text, short, article, piece.get("wall_id"), along, float(piece["depth_in"]), y)
    for corner in design.get("corners") or []:
        text, short, article = describe_corner(corner)
        wall_id, end = next(iter((corner.get("ends") or {}).items()), (None, None))
        frame = frames.get(wall_id)
        if frame is None:
            continue
        offset = 0.0 if end == "start" else float(frame["length_in"]) - float(corner["span_in"])
        along = offset + float(corner["span_in"]) * 0.5
        y = float(corner.get("y_in") or 0) + float(corner.get("height_in") or 30) * 0.5
        add(corner.get("kind") or "corner", text, short, article, wall_id, along, float(corner.get("depth_in") or 24), y)
    for panel in design.get("panels") or []:
        text, short, article = describe_panel(panel, design)
        along = float(panel["offset_in"])
        host = panel.get("host") or {}
        height = float(host.get("y_in") or 4.5) + float(host.get("height_in") or 30)
        add("panel", text, short, article, panel.get("wall_id"), along, float(host.get("depth_in") or 24), height * 0.5)
    return rows


_RUN_KINDS = {"base", "sink_base", "filler", "fridge", "range", "dishwasher"}


def _counter_top(design: dict, wall_id: str):
    tops = []
    for piece in design.get("worktops") or []:
        if piece.get("wall_id") == wall_id and piece.get("y_in") is not None and piece.get("height_in") is not None:
            tops.append(float(piece["y_in"]) + float(piece["height_in"]))
    if tops:
        return max(tops)
    return None


def dimension_lines(design: dict) -> list[dict]:
    """World-space dimension lines: wall length, module widths, ceiling, counter, openings."""
    rows = []

    def add(frame, along0, into0, y0, along1, into1, y1, text):
        if abs(along0 - along1) < 0.2 and abs(y0 - y1) < 0.2:
            return
        x0, z0 = world(frame["origin"], frame["direction"], frame["inward"], along0, into0)
        x1, z1 = world(frame["origin"], frame["direction"], frame["inward"], along1, into1)
        rows.append({"text": text, "a": [x0, y0, z0], "b": [x1, y1, z1]})

    room = design.get("room") or {}
    ceiling = float(room.get("ceiling_height_in") or 96)
    for frame in design.get("frames") or []:
        length = float(frame["length_in"])
        items = [item for item in design.get("items") or [] if item.get("wall_id") == frame["id"]]
        counter = _counter_top(design, frame["id"])
        band = counter if counter is not None else 35.625
        add(frame, 0, 1.5, band + 13, length, 1.5, band + 13, f"{_num(length)} in")
        for item in items:
            if item.get("kind") not in _RUN_KINDS:
                continue
            width = float(item.get("width_in") or 0)
            start = float(item.get("offset_in") or 0)
            if width < 0.5:
                continue
            label = f"{_num(width)} in" if width >= 10 else ""
            add(frame, start, 1.5, band + 4, start + width, 1.5, band + 4, label)
        add(frame, -10, 18, 0, -10, 18, ceiling, f"{_num(ceiling)} in")
        if counter is not None:
            add(frame, length + 10, 18, 0, length + 10, 18, counter, f"{_num(counter)} in")
        for wall in room.get("walls") or []:
            if wall.get("id") != frame["id"]:
                continue
            for opening in wall.get("openings") or []:
                width = float(opening.get("width_in") or 0)
                if width < 1:
                    continue
                start = float(opening.get("offset_in") or 0)
                head = float(opening.get("sill_in") or 42) + float(opening.get("height_in") or 36)
                add(frame, start, 1.5, head, start + width, 1.5, head, f"{_num(width)} in")
    return rows


def _measurement_lines(design: dict) -> list[str]:
    room = design.get("room") or {}
    lines = ["Measurements", "Sizes are width x depth x height."]
    ceiling = room.get("ceiling_height_in")
    if ceiling:
        lines.append(f"Ceiling height {_num(ceiling)} in")
    for frame in design.get("frames") or []:
        lines.append(f"Wall {frame['id']} length {_num(frame['length_in'])} in")
    seen = set()
    for piece in design.get("worktops") or []:
        wall_id = piece.get("wall_id")
        if wall_id in seen:
            continue
        seen.add(wall_id)
        top = _counter_top(design, wall_id)
        if top is not None:
            lines.append(f"Counter height on {wall_id} {_num(top)} in")
    for wall in room.get("walls") or []:
        for opening in wall.get("openings") or []:
            kind = opening.get("kind") or "opening"
            bits = [f"{kind} on {wall.get('id')}"]
            if opening.get("width_in") is not None:
                bits.append(f"{_num(opening['width_in'])} in wide")
            if opening.get("height_in") is not None:
                bits.append(f"{_num(opening['height_in'])} in high")
            if opening.get("sill_in") is not None:
                bits.append(f"sill {_num(opening['sill_in'])} in")
            if opening.get("offset_in") is not None and opening.get("width_in") is not None:
                start = float(opening["offset_in"])
                bits.append(f"from {_num(start)} to {_num(start + float(opening['width_in']))} in")
            lines.append(", ".join(bits))
    return lines


def still_legend(design: dict) -> list[str]:
    """Room sizes under a still. Product names stay on the cabinets."""
    return _measurement_lines(design)


def product_lines(design: dict) -> list[str]:
    """Every cabinet and product, in the same words on every asset."""
    lines = _measurement_lines(design)
    lines.append("")
    lines.append("Placed in the model")
    for row in callouts(design):
        lines.append(row["text"])
    lines.append("")
    lines.append("Purchase list")
    for line in design.get("bom") or []:
        name = line.get("name") or "Unresolved item"
        article = line.get("article") or ""
        qty = line.get("qty")
        text = name
        if article:
            text += f" · {article}"
        if qty:
            text += f" · qty {qty}"
        lines.append(text)
    appliances = design.get("appliances") or []
    if appliances:
        lines.append("")
        lines.append("Appliances, schematic")
        for row in appliances:
            state = "placed" if row.get("placed") else "listed, not placed in this run"
            name = row.get("name") or "Appliance"
            finish = row.get("finish") or ""
            text = name
            if finish:
                text += f", {finish}"
            phrase = _size_phrase(row.get("width_in"), row.get("depth_in"), row.get("height_in"))
            if phrase:
                text += f", {phrase}"
            lines.append(f"{text}, {state}. Not an IKEA article.")
    return lines


def _fold(text: str) -> str:
    folded = (
        text.upper()
        .replace("·", "|")
        .replace("—", "-")
        .replace("Ö", "O")
        .replace("Ä", "A")
        .replace("Å", "A")
    )
    return "".join(ch if ch in _FONT else " " for ch in folded)


def _wrap(text: str, limit: int) -> list[str]:
    words = text.split(" ")
    rows: list[str] = []
    current = ""
    for word in words:
        trial = word if not current else current + " " + word
        if len(trial) <= limit:
            current = trial
        else:
            if current:
                rows.append(current)
            current = word
    if current:
        rows.append(current)
    return rows or [""]


def _blit(buffer: bytearray, width: int, height: int, x: int, y: int, text: str, scale: int, color: tuple[int, int, int]) -> None:
    cursor = x
    for ch in _fold(text):
        glyph = _FONT.get(ch, _FONT[" "])
        for row, bits in enumerate(glyph):
            for col, bit in enumerate(bits):
                if bit != "#":
                    continue
                for dy in range(scale):
                    py = y + row * scale + dy
                    if py < 0 or py >= height:
                        continue
                    for dx in range(scale):
                        px = cursor + col * scale + dx
                        if px < 0 or px >= width:
                            continue
                        index = (py * width + px) * 3
                        buffer[index:index + 3] = bytes(color)
        cursor += 6 * scale


def _stroke(buffer: bytearray, width: int, height: int, x0: float, y0: float, x1: float, y1: float, color: tuple[int, int, int]) -> None:
    if max(abs(x0), abs(y0), abs(x1), abs(y1)) > 8000:
        return
    ix0, iy0, ix1, iy1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
    dx = abs(ix1 - ix0)
    dy = abs(iy1 - iy0)
    sx = 1 if ix0 < ix1 else -1
    sy = 1 if iy0 < iy1 else -1
    err = dx - dy
    guard = dx + dy + 4
    ink = bytes(color)
    while guard > 0:
        guard -= 1
        if 0 <= ix0 < width and 0 <= iy0 < height:
            index = (iy0 * width + ix0) * 3
            buffer[index:index + 3] = ink
        if ix0 == ix1 and iy0 == iy1:
            break
        doubled = 2 * err
        if doubled > -dy:
            err -= dy
            ix0 += sx
        if doubled < dx:
            err += dx
            iy0 += sy


def paint_dimensions(rgb: bytes, width: int, height: int, segments: list[tuple]) -> bytes:
    """Draw dimension lines on a still. Each segment is x0, y0, x1, y1, text in pixels."""
    photo = bytearray(rgb)
    placed = []
    ink = (28, 26, 22)
    for x0, y0, x1, y1, text in segments:
        span = math.hypot(x1 - x0, y1 - y0)
        if span < 8:
            continue
        horizontal = abs(x1 - x0) >= abs(y1 - y0)
        label = _fold(text or "")
        tw = len(label) * 6 + 4
        if not label.strip():
            label = ""
        elif horizontal and abs(x1 - x0) < tw + 4:
            label = ""
        elif not horizontal and abs(y1 - y0) < 16:
            label = ""
        _stroke(photo, width, height, x0, y0, x1, y1, ink)
        tick = 6
        if horizontal:
            _stroke(photo, width, height, x0, y0 - tick, x0, y0 + tick, ink)
            _stroke(photo, width, height, x1, y1 - tick, x1, y1 + tick, ink)
        else:
            _stroke(photo, width, height, x0 - tick, y0, x0 + tick, y0, ink)
            _stroke(photo, width, height, x1 - tick, y1, x1 + tick, y1, ink)
        if not label:
            continue
        left = int((x0 + x1) / 2 - tw / 2)
        top = int((y0 + y1) / 2 - 5)
        if left < 2 or top < 2 or left + tw >= width - 2 or top + 12 >= height - 2:
            continue
        if any(abs(left - box[0]) < tw and abs(top - box[1]) < 14 for box in placed):
            continue
        placed.append((left, top))
        for py in range(top - 1, top + 11):
            for px in range(left - 1, left + tw):
                if 0 <= px < width and 0 <= py < height:
                    index = (py * width + px) * 3
                    photo[index:index + 3] = b"\x14\x16\x15"
        _blit(photo, width, height, left + 2, top + 1, label, 1, (244, 241, 234))
    return bytes(photo)


def paint_labels(rgb: bytes, width: int, height: int, spots: list[tuple[float, float, str]], lines: list[str], side: list[str] | None = None) -> tuple[bytes, int, int]:
    """Draw the aimed-at name on the picture, the rest of that view in a side list, and room sizes below."""
    photo = bytearray(rgb)
    placed = []
    for x, y, text in spots:
        label = _fold(text)
        if not label.strip():
            continue
        tw = len(label) * 6 + 4
        left = int(x - tw / 2)
        top = int(y - 12)
        if left < 2 or top < 2 or left + tw >= width - 2 or top + 12 >= height - 2:
            continue
        if any(abs(left - box[0]) < tw and abs(top - box[1]) < 14 for box in placed):
            continue
        placed.append((left, top))
        for py in range(top - 1, top + 11):
            for px in range(left - 1, left + tw):
                if 0 <= px < width and 0 <= py < height:
                    index = (py * width + px) * 3
                    photo[index:index + 3] = b"\x14\x16\x15"
        _blit(photo, width, height, left + 2, top + 1, label, 1, (244, 241, 234))

    side_rows: list[str] = []
    if side:
        side_rows.append("In this view")
        side_rows.append("")
        for line in side:
            side_rows.extend(_wrap(line, 28))
            side_rows.append("")
        while side_rows and not side_rows[-1]:
            side_rows.pop()
    side_w = 28 * 6 + 16 if side_rows else 0
    scale = 1
    out_w = width + side_w
    limit = max(12, (out_w - 16) // (6 * scale))
    wrapped = []
    for line in lines:
        if not line:
            wrapped.append("")
            continue
        wrapped.extend(_wrap(line, limit))
    row_h = 8 * scale
    legend_h = 12 + len(wrapped) * row_h + 8
    out_h = height + legend_h
    out = bytearray(out_w * out_h * 3)
    for index in range(0, len(out), 3):
        out[index:index + 3] = b"\x1b\x1d\x1c"
    for row in range(height):
        src = row * width * 3
        dst = row * out_w * 3
        out[dst:dst + width * 3] = photo[src:src + width * 3]
    if side_w:
        y = 8
        for line in side_rows:
            if y + 8 >= height:
                break
            if line:
                _blit(out, out_w, out_h, width + 8, y, line, 1, (244, 241, 234))
            y += row_h
    y = height + 8
    for line in wrapped:
        if line:
            _blit(out, out_w, out_h, 8, y, line, scale, (244, 241, 234))
        y += row_h
    return bytes(out), out_w, out_h
