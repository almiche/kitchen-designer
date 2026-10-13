from __future__ import annotations

import math

from .appliances import sized_catalog, stamp_and_place
from .catalog import display_name, find_articles, front_by_id, hinge, one, panel_rip_in, side_cover, widths

UNDER_COUNTER = {"base", "sink_base", "dishwasher"}
CABINET = {"base", "sink_base"}


def subtract(spans: list[tuple[float, float]], holes: list[tuple[float, float]]) -> list[tuple[float, float]]:
    current = spans
    for hole_a, hole_b in holes:
        nxt: list[tuple[float, float]] = []
        for start, end in current:
            if hole_b <= start or hole_a >= end:
                nxt.append((start, end))
                continue
            if hole_a > start:
                nxt.append((start, hole_a))
            if hole_b < end:
                nxt.append((hole_b, end))
        current = nxt
    return [(a, b) for a, b in current if b - a > 0.25]


def pack(length_in: float, module_widths: list[int]) -> tuple[list[int], float]:
    """Fill length with module widths. Leftover is smaller than the smallest module."""
    if length_in <= 0 or not module_widths:
        return [], max(length_in, 0)
    whole = int(math.floor(length_in + 1e-6))
    fraction = length_in - whole
    options = sorted({int(w) for w in module_widths if w > 0}, reverse=True)
    best: list[list[int] | None] = [None] * (whole + 1)
    best[0] = []
    for used in range(whole + 1):
        chosen = best[used]
        if chosen is None:
            continue
        for width in options:
            nxt = used + width
            if nxt > whole:
                continue
            candidate = chosen + [width]
            current = best[nxt]
            if current is None or len(candidate) < len(current):
                best[nxt] = candidate
    for used in range(whole, -1, -1):
        if best[used] is not None:
            return list(best[used] or []), (whole - used) + fraction
    return [], length_in


def buy_boards(length_in: float, sizes: tuple[int, ...] = (74, 98)) -> list[tuple[int, int]]:
    """Return (board_length, count) pairs that cover length with the least waste."""
    if length_in <= 0.5:
        return []
    target = int(math.ceil(length_in - 1e-6))
    smallest = min(sizes)
    limit = int(math.ceil(target / smallest)) + 1
    best: tuple[int, int, tuple[int, ...]] | None = None
    counts = [0] * len(sizes)
    # sizes are only 74 and 98, so a pair of loops stays obvious.
    for count_a in range(limit + 1):
        for count_b in range(limit + 1):
            counts = (count_a, count_b)
            total = sizes[0] * count_a + sizes[1] * count_b
            pieces = count_a + count_b
            if pieces == 0 or total < target or total > target + max(sizes):
                continue
            cand = (total - target, pieces, counts)
            if best is None or cand < best:
                best = cand
    if best is None:
        return []
    return [(sizes[i], best[2][i]) for i in range(len(sizes)) if best[2][i]]


def buy_cover_rips(catalog: dict, rips: list[dict]) -> tuple[list[tuple[dict, int]], list[str]]:
    """Buy whole cover panels that can be ripped into these filler strips.

    A side panel is not part of this stock. Each strip has to come out of one
    panel, with the panel's long side covering the filler height.
    """
    panels = [
        item for item in catalog["articles"]
        if item.get("role") == "cover_panel" and item.get("width_in") and item.get("height_in")
    ]
    notes: list[str] = []
    pieces: list[dict] = []
    for rip in rips:
        width = float(rip["width_in"])
        height = float(rip["height_in"])
        cap = max((panel_rip_in(panel, height) for panel in panels), default=0.0)
        if cap <= 0.05:
            notes.append(f"No cover panel in the catalog covers a {height:.1f} inch filler.")
            continue
        if width > cap + 0.05:
            notes.append(
                f"A {width:.1f} inch filler is wider than the widest cover panel that covers {height:.1f} inches. "
                "It is cut from more than one panel."
            )
            while width > 0.2:
                pieces.append({"width_in": min(width, cap), "height_in": height})
                width -= cap
        else:
            pieces.append({"width_in": width, "height_in": height})
    if not pieces:
        return [], notes
    if len(pieces) > 16:
        bought = _greedy_rips(panels, pieces)
    else:
        bought = _dp_rips(panels, pieces)
    counts: dict[str, int] = {}
    chosen: dict[str, dict] = {}
    for panel in bought:
        counts[panel["article"]] = counts.get(panel["article"], 0) + 1
        chosen[panel["article"]] = panel
    rows = [(chosen[article], counts[article]) for article in sorted(counts)]
    return rows, notes


def _dp_rips(panels: list[dict], pieces: list[dict]) -> list[dict]:
    count = len(pieces)
    singles: dict[int, tuple[float, dict]] = {}
    for mask in range(1, 1 << count):
        widths = []
        height = 0.0
        for index in range(count):
            if mask & (1 << index):
                widths.append(pieces[index]["width_in"])
                height = max(height, pieces[index]["height_in"])
        need = sum(widths)
        best: tuple[float, str, dict] | None = None
        for panel in panels:
            cap = panel_rip_in(panel, height)
            if cap + 0.05 < need:
                continue
            key = (float(panel["price_cad"]), panel["article"], panel)
            if best is None or key < best:
                best = key
        if best is not None:
            singles[mask] = (best[0], best[2])
    inf = 10 ** 9
    cost = [inf] * (1 << count)
    parent: list[tuple[int, dict] | None] = [None] * (1 << count)
    cost[0] = 0
    for mask in range(1 << count):
        if cost[mask] >= inf:
            continue
        for sub, (extra, panel) in singles.items():
            if mask & sub:
                continue
            nxt = mask | sub
            cand = cost[mask] + extra
            if cand < cost[nxt]:
                cost[nxt] = cand
                parent[nxt] = (mask, panel)
    full = (1 << count) - 1
    if cost[full] >= inf or parent[full] is None:
        return _greedy_rips(panels, pieces)
    bought = []
    mask = full
    guard = 0
    while mask:
        step = parent[mask]
        if step is None:
            return _greedy_rips(panels, pieces)
        prev, panel = step
        bought.append(panel)
        mask = prev
        guard += 1
        if guard > count + 2:
            return _greedy_rips(panels, pieces)
    return bought


def _greedy_rips(panels: list[dict], pieces: list[dict]) -> list[dict]:
    remaining = list(pieces)
    bought = []
    guard = 0
    while remaining and guard < len(pieces) + 2:
        guard += 1
        height = max(piece["height_in"] for piece in remaining)
        options = []
        for panel in panels:
            cap = panel_rip_in(panel, height)
            if cap > 0:
                options.append((float(panel["price_cad"]), -cap, panel["article"], panel, cap))
        if not options:
            break
        options.sort()
        _price, _span, _article, panel, cap = options[0]
        used = 0.0
        nxt = []
        for piece in sorted(remaining, key=lambda row: -row["width_in"]):
            if piece["height_in"] <= height + 0.05 and used + piece["width_in"] <= cap + 0.05:
                used += piece["width_in"]
            else:
                nxt.append(piece)
        if used <= 0:
            break
        bought.append(panel)
        remaining = nxt
    return bought


def _frame(wall: dict, origin, direction, inward, corner_start: float, corner_end: float) -> dict:
    return {
        "id": wall["id"],
        "length_in": wall["length_in"],
        "openings": wall["openings"],
        "origin": origin,
        "direction": direction,
        "inward": inward,
        "corner_start": corner_start,
        "corner_end": corner_end,
    }


def wall_frames(room: dict, corner_span: float) -> list[dict]:
    walls = room["walls"]
    shape = room["shape"]
    if shape == "straight":
        return [_frame(walls[0], (0.0, 0.0), (1.0, 0.0), (0.0, 1.0), 0, 0)]
    if shape == "L":
        left, back = walls
        return [
            _frame(left, (0.0, 0.0), (0.0, 1.0), (1.0, 0.0), 0, corner_span),
            _frame(back, (0.0, left["length_in"]), (1.0, 0.0), (0.0, -1.0), corner_span, 0),
        ]
    if shape == "U":
        left, back, right = walls
        return [
            _frame(left, (0.0, 0.0), (0.0, 1.0), (1.0, 0.0), 0, corner_span),
            _frame(back, (0.0, left["length_in"]), (1.0, 0.0), (0.0, -1.0), corner_span, corner_span),
            _frame(right, (back["length_in"], left["length_in"]), (0.0, -1.0), (-1.0, 0.0), corner_span, 0),
        ]
    depth = float(room.get("room_depth_in") or 120)
    return [
        _frame(walls[0], (0.0, 0.0), (1.0, 0.0), (0.0, 1.0), 0, 0),
        _frame(walls[1], (0.0, depth), (1.0, 0.0), (0.0, -1.0), 0, 0),
    ]


def _segments(frame: dict) -> list[tuple[float, float]]:
    start = frame["corner_start"]
    end = frame["length_in"] - frame["corner_end"]
    if end - start < 12:
        return []
    holes = [
        (op["offset_in"], op["offset_in"] + op["width_in"])
        for op in frame["openings"]
        if op["kind"] == "door"
    ]
    return subtract([(start, end)], holes)


def _windows(frame: dict) -> list[dict]:
    return [op for op in frame["openings"] if op["kind"] == "window"]


def _place_range(gap: tuple[float, float], sink_on_right: bool, width: float = 30.0) -> tuple[float, float]:
    start, end = gap
    room = (end - start) - width
    best: tuple[float, float] | None = None
    steps = max(int(math.floor(room)) + 1, 1)
    for step in range(steps):
        left = float(step)
        right = room - left
        if (1 <= left <= 11) or (1 <= right <= 11):
            score = -1000 + left + right
        else:
            landing = right if sink_on_right else left
            other = left if sink_on_right else right
            score = landing * 10 + other
        if best is None or score > best[0]:
            best = (score, start + left)
    assert best is not None
    return best[1], best[1] + width


def _is_wall_end(frame: dict, segment: tuple[float, float], side: str) -> bool:
    start, end = segment
    if side == "start":
        return frame["corner_start"] == 0 and abs(start) < 0.2
    return frame["corner_end"] == 0 and abs(end - frame["length_in"]) < 0.2


def _preferred_fridge_side(frame: dict) -> str:
    if frame["corner_end"] > 0 and frame["corner_start"] == 0:
        return "start"
    return "end"


def _base_filler(frame: dict, offset: float, width: float, const: dict, reason: str) -> dict:
    thick = float(const.get("filler_thickness_in") or 0.75)
    depth = float(const["base_frame_depth_in"])
    return {
        "kind": "filler",
        "reason": reason,
        "wall_id": frame["id"],
        "offset_in": offset,
        "width_in": width,
        "depth_in": thick,
        "into_in": depth - thick,
        "height_in": float(const["leg_height_in"]) + float(const["base_frame_height_in"]),
        "y_in": 0,
    }


def _peel_door_fillers(frame: dict, segment: tuple[float, float], gaps: list[tuple[float, float]], width: float, min_module: float):
    """Hold back a door-swing filler where a cabinet still fits behind it."""
    start, end = segment
    need = width + min_module - 0.05
    peeled = []
    kept = []
    for gap_start, gap_end in gaps:
        if _is_wall_end(frame, segment, "start") and abs(gap_start - start) < 0.2 and gap_end - gap_start >= need:
            peeled.append((gap_start, width))
            gap_start += width
        if _is_wall_end(frame, segment, "end") and abs(gap_end - end) < 0.2 and gap_end - gap_start >= need:
            peeled.append((gap_end - width, width))
            gap_end -= width
        if gap_end - gap_start > 0.25:
            kept.append((gap_start, gap_end))
    return kept, peeled


def _layout_once(frame: dict, segment: tuple[float, float], appliances: bool, catalog: dict, prefs: dict, fridge_side: str | None):
    const = catalog["constants"]
    start, end = segment
    gaps = [(start, end)]
    placed: list[dict] = []
    warns: list[str] = []
    under_window = False

    def occupy(offset: float, width: float, kind: str, **extra) -> None:
        nonlocal gaps
        gaps = subtract(gaps, [(offset, offset + width)])
        item = {
            "kind": kind,
            "wall_id": frame["id"],
            "offset_in": offset,
            "width_in": width,
        }
        item.update(extra)
        placed.append(item)

    def reserve_filler(offset: float, width: float, reason: str) -> None:
        nonlocal gaps
        gaps = subtract(gaps, [(offset, offset + width)])
        placed.append(_base_filler(frame, offset, width, const, reason))

    if appliances and prefs["fridge"] and fridge_side:
        width = const["fridge_width_in"]
        # IKEA: 4 inches between a refrigerator door and a wall. A corner frame is not that wall.
        clearance = float(const.get("filler_fridge_in") or 4) if _is_wall_end(frame, segment, fridge_side) else 0.0
        if end - start + 0.1 >= width + clearance:
            if fridge_side == "start":
                if clearance:
                    reserve_filler(start, clearance, "fridge-wall")
                occupy(start + clearance, width, "fridge", depth_in=const["fridge_depth_in"], height_in=const["fridge_height_in"], y_in=0)
            else:
                if clearance:
                    reserve_filler(end - clearance, clearance, "fridge-wall")
                occupy(end - clearance - width, width, "fridge", depth_in=const["fridge_depth_in"], height_in=const["fridge_height_in"], y_in=0)
        else:
            warns.append(f"{frame['id']}: no room for a {width:.0f} inch fridge")
    elif appliances and prefs["fridge"]:
        warns.append(f"{frame['id']}: no room for a {const['fridge_width_in']:.0f} inch fridge beside the sink, dishwasher, and range")

    sink_box = None
    if appliances and prefs["sink"]:
        sink_width = 36 if one(catalog, "base_frame", width_in=36, height_in=30) else 30
        window = None
        for opening in _windows(frame):
            overlap = min(end, opening["offset_in"] + opening["width_in"]) - max(start, opening["offset_in"])
            if overlap > 0 and (window is None or opening["width_in"] > window["width_in"]):
                window = opening
        target = None
        from_window = False
        if window:
            center = window["offset_in"] + window["width_in"] / 2
            candidate = center - sink_width / 2
            for gap_start, gap_end in gaps:
                if candidate >= gap_start - 0.1 and candidate + sink_width <= gap_end + 0.1:
                    target = max(gap_start, min(candidate, gap_end - sink_width))
                    from_window = True
                    break
            if target is None:
                warns.append(f"{frame['id']}: sink does not fit under the window")
        if target is None:
            gap = max(gaps, key=lambda span: span[1] - span[0], default=None)
            if gap and gap[1] - gap[0] >= sink_width:
                target = gap[0] + (gap[1] - gap[0] - sink_width) / 2
        if target is None:
            warns.append(f"{frame['id']}: no room for a {sink_width:.0f} inch sink cabinet")
        else:
            article = one(catalog, "base_frame", width_in=sink_width, height_in=30)
            occupy(target, sink_width, "sink_base", depth_in=24, height_in=30, y_in=const["leg_height_in"], article=article)
            sink_box = (target, target + sink_width)
            under_window = from_window
            if appliances and prefs["dishwasher"]:
                dw = const["dishwasher_width_in"]
                right = target + sink_width
                left = target - dw
                placed_dw = False
                for gap_start, gap_end in gaps:
                    if gap_start <= right + 0.1 and gap_end >= right + dw - 0.1:
                        occupy(right, dw, "dishwasher", depth_in=24, height_in=const["leg_height_in"] + 30, y_in=0)
                        placed_dw = True
                        break
                if not placed_dw:
                    for gap_start, gap_end in list(gaps):
                        if gap_end >= left - 0.1 and gap_start <= left + 0.1 and gap_end - gap_start >= dw:
                            occupy(target - dw, dw, "dishwasher", depth_in=24, height_in=const["leg_height_in"] + 30, y_in=0)
                            placed_dw = True
                            break
                if not placed_dw:
                    warns.append(f"{frame['id']}: no room for a dishwasher beside the sink")

    if appliances and prefs["range"]:
        range_width = float(const.get("range_width_in") or 30)
        gap = max(gaps, key=lambda span: span[1] - span[0], default=None)
        if gap and gap[1] - gap[0] >= range_width:
            sink_right = True if sink_box is None else sink_box[0] >= gap[1]
            offset, _ = _place_range(gap, sink_right, range_width)
            occupy(offset, range_width, "range", depth_in=const["range_depth_in"], height_in=const["range_height_in"], y_in=0)
        else:
            warns.append(f"{frame['id']}: no room for a {range_width:.0f} inch range")

    # 2 inches where a door cabinet meets a wall. Range and dishwasher can sit flush.
    door_clear = float(const.get("filler_door_in") or 2)
    module_widths = widths(catalog, "base_frame", 30)
    min_module = min(module_widths) if module_widths else 12
    gaps, peeled = _peel_door_fillers(frame, segment, gaps, door_clear, min_module)
    for offset, width in peeled:
        placed.append(_base_filler(frame, offset, width, const, "door-wall"))

    for gap_start, gap_end in gaps:
        chosen, leftover = pack(gap_end - gap_start, module_widths)
        cursor = gap_start
        for width in chosen:
            article = one(catalog, "base_frame", width_in=width, height_in=30)
            placed.append({
                "kind": "base",
                "wall_id": frame["id"],
                "offset_in": cursor,
                "width_in": width,
                "depth_in": 24,
                "height_in": 30,
                "y_in": const["leg_height_in"],
                "article": article,
            })
            cursor += width
        if leftover >= 0.5:
            placed.append(_base_filler(frame, cursor, leftover, const, "leftover"))
            if leftover >= const["filler_warn_in"]:
                warns.append(
                    f"{frame['id']}: {leftover:.1f} inch filler at {cursor:.0f} inches. "
                    "A SEKTION frame will not fit there. The strip is cut from a cover panel."
                )
    placed.sort(key=lambda item: item["offset_in"])
    return placed, warns, under_window


def _layout_segment(frame: dict, segment: tuple[float, float], appliances: bool, catalog: dict, prefs: dict, warnings: list[str]) -> list[dict]:
    if not (appliances and prefs["fridge"]):
        placed, warns, _under = _layout_once(frame, segment, appliances, catalog, prefs, None)
        warnings.extend(warns)
        return placed
    ranked = []
    # Also try leaving the fridge out. A wall that can take the sink, dishwasher, and range
    # beats a wall that takes the fridge and drops the others.
    for side in ("start", "end", None):
        placed, warns, under = _layout_once(frame, segment, appliances, catalog, prefs, side)
        ranked.append((side, placed, warns, under))

    def rank(row):
        side, placed, _warns, under = row
        kinds = {item["kind"] for item in placed}
        got = sum(kind in kinds for kind in ("fridge", "sink_base", "dishwasher", "range"))
        filler_in = round(sum(item["width_in"] for item in placed if item["kind"] == "filler"), 3)
        preferred = 1 if side == _preferred_fridge_side(frame) else 0
        return (got, int(under), -filler_in, preferred)

    _side, placed, warns, _under = max(ranked, key=rank)
    warnings.extend(warns)
    return placed


def _wall_run(frame: dict, base_items: list[dict], catalog: dict, height: float, warnings: list[str]) -> list[dict]:
    const = catalog["constants"]
    bottom = const["leg_height_in"] + const["base_frame_height_in"] + const["counter_thickness_in"] + const["wall_gap_above_counter_in"]
    blocked: list[tuple[float, float]] = []
    for item in base_items:
        if item["kind"] in ("range", "fridge", "sink_base"):
            blocked.append((item["offset_in"], item["offset_in"] + item["width_in"]))
    for opening in _windows(frame):
        head = opening["sill_in"] + opening["height_in"]
        if opening["sill_in"] < bottom + height and head > bottom:
            blocked.append((opening["offset_in"], opening["offset_in"] + opening["width_in"]))
    candidates = []
    for item in base_items:
        if item["kind"] in ("base", "dishwasher"):
            candidates.append((item["offset_in"], item["offset_in"] + item["width_in"]))
    clear = subtract(candidates, blocked)
    module_widths = widths(catalog, "wall_frame", height)
    placed = []
    depth = const["wall_frame_depth_in"]
    for gap_start, gap_end in clear:
        chosen, leftover = pack(gap_end - gap_start, module_widths)
        cursor = gap_start
        for width in chosen:
            article = one(catalog, "wall_frame", width_in=width, height_in=height)
            if article is None:
                continue
            placed.append({
                "kind": "wall",
                "wall_id": frame["id"],
                "offset_in": cursor,
                "width_in": width,
                "depth_in": depth,
                "height_in": height,
                "y_in": bottom,
                "article": article,
            })
            cursor += width
        if leftover >= 0.5:
            thick = float(const.get("filler_thickness_in") or 0.75)
            placed.append({
                "kind": "wall_filler",
                "reason": "leftover",
                "wall_id": frame["id"],
                "offset_in": cursor,
                "width_in": leftover,
                "depth_in": thick,
                "into_in": depth - thick,
                "height_in": height,
                "y_in": bottom,
            })
            if leftover >= const["filler_warn_in"]:
                warnings.append(
                    f"{frame['id']}: {leftover:.1f} inch filler in the wall-cabinet run. "
                    "The strip is cut from a cover panel."
                )
    for item in base_items:
        if item["kind"] != "fridge":
            continue
        article = one(catalog, "wall_frame", width_in=item["width_in"], height_in=20)
        top = item["height_in"] + 20
        if article and top <= frame.get("ceiling", 96) + 0.1:
            placed.append({
                "kind": "over_fridge",
                "wall_id": frame["id"],
                "offset_in": item["offset_in"],
                "width_in": item["width_in"],
                "depth_in": depth,
                "height_in": 20,
                "y_in": item["height_in"],
                "article": article,
            })
        elif article is None:
            warnings.append(f"{frame['id']}: no {item['width_in']:.0f}x20 inch cabinet over the fridge")
    return placed


def _merge_spans(spans: list[tuple[float, float]]) -> list[list[float]]:
    merged: list[list[float]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1] + 0.6:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def _absorb_fillers(spans: list[tuple[float, float]], fillers: list[tuple[float, float]]) -> list[list[float]]:
    """Pull a filler into a counter run when it touches a base, sink, or dishwasher."""
    merged = _merge_spans(spans)
    pending = list(fillers)
    progressed = True
    while progressed:
        progressed = False
        still = []
        for start, end in pending:
            hit = None
            for index, row in enumerate(merged):
                if start <= row[1] + 0.6 and end >= row[0] - 0.6:
                    hit = index
                    break
            if hit is None:
                still.append((start, end))
                continue
            merged[hit][0] = min(merged[hit][0], start)
            merged[hit][1] = max(merged[hit][1], end)
            progressed = True
        pending = still
    return merged


def _worktops(frames: list[dict], items: list[dict], corners: list[dict]) -> list[dict]:
    pieces = []
    for frame in frames:
        spans = [
            (item["offset_in"], item["offset_in"] + item["width_in"])
            for item in items
            if item.get("wall_id") == frame["id"] and item["kind"] in UNDER_COUNTER
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
        for start, end in _absorb_fillers(spans, fillers):
            if end - start < 6:
                continue
            pieces.append({
                "kind": "worktop",
                "wall_id": frame["id"],
                "offset_in": start,
                "width_in": end - start,
                "depth_in": 25.625,
                "height_in": 1.125,
                "y_in": 4.5 + 30,
            })
    return pieces


def _exposed_sides(items: list[dict]) -> list[dict]:
    panels = []
    by_wall: dict[str, list[dict]] = {}
    for item in items:
        if item["kind"] in CABINET:
            by_wall.setdefault(item["wall_id"], []).append(item)
    for wall_id, row in by_wall.items():
        row.sort(key=lambda item: item["offset_in"])
        for index, item in enumerate(row):
            left = row[index - 1] if index else None
            right = row[index + 1] if index + 1 < len(row) else None
            if left is None or item["offset_in"] - (left["offset_in"] + left["width_in"]) > 0.6:
                panels.append({"wall_id": wall_id, "offset_in": item["offset_in"], "side": "start", "host": item})
            if right is None or right["offset_in"] - (item["offset_in"] + item["width_in"]) > 0.6:
                panels.append({"wall_id": wall_id, "offset_in": item["offset_in"] + item["width_in"], "side": "end", "host": item})
    return panels


def plan_doors(catalog: dict, width: float, height: float, style: str = "axstad-white") -> list[dict | None]:
    def find(w: float, h: float) -> dict | None:
        for item in find_articles(catalog, "door", width_in=w, height_in=h):
            if item.get("style") == style:
                return item
        return None

    found = find(width, height)
    if found:
        return [found]
    if width >= 27:
        half = find(width / 2, height)
        if half:
            return [half, half]
        return [None, None]
    return [None]


def corner_set(catalog: dict, style: str) -> dict | None:
    """One corner-door set for this front. A handed pair buys the left set once."""
    rows = [
        item for item in find_articles(catalog, "corner_door", width_in=13, height_in=30)
        if item.get("style") == style
    ]
    left = [item for item in rows if item.get("hand") == "left"]
    if left:
        return left[0]
    plain = [item for item in rows if not item.get("hand")]
    if plain:
        return plain[0]
    return rows[0] if rows else None


def _cad(value) -> str:
    if value is None:
        return ""
    return f"${float(value):,.0f}"


def _article_index(catalog: dict) -> dict:
    index = catalog.get("by_article")
    if index:
        return index
    return {item["article"]: item for item in catalog["articles"]}


def build_buy(catalog: dict, prefs: dict, frames: list[dict], items: list[dict], corners: list[dict], bom: list[dict], total: float) -> dict:
    """Cabinet-by-cabinet purchase lines. The flat article table stays beside this."""
    style = prefs.get("front_style") or "axstad-white"
    front = front_by_id(catalog, style) or {"id": style, "name": style}
    titles = {
        "base": "Base cabinet",
        "sink_base": "Sink base",
        "wall": "Wall cabinet",
        "over_fridge": "Cabinet over the fridge",
    }
    wall_order = {frame["id"]: index for index, frame in enumerate(frames)}

    def door_phrase(width: float, height: float) -> str:
        doors = plan_doors(catalog, width, height, style)
        count = len(doors)
        each_w = width / count if count > 1 else width
        groups: dict[str, dict] = {}
        missing = 0
        for door in doors:
            if not door:
                missing += 1
                continue
            row = groups.setdefault(door["article"], {"name": display_name(door), "qty": 0, "each": door.get("price_cad")})
            row["qty"] += 1
        parts = []
        for article, row in groups.items():
            noun = "door" if row["qty"] == 1 else "doors"
            parts.append(f"{row['qty']} {noun} {article} {row['name']} {_cad(row['each'])} each")
        if missing:
            noun = "door" if missing == 1 else "doors"
            parts.append(f"{missing} {noun}, {each_w:.0f}x{height:.0f} in, not stocked in this front")
        return " + ".join(parts)

    cabinets = []
    placed = [item for item in items if item["kind"] in titles]
    placed.sort(key=lambda item: (wall_order.get(item.get("wall_id"), 0), item["offset_in"]))
    for item in placed:
        height = 30 if item["kind"] in ("base", "sink_base") else float(item["height_in"])
        start = float(item["offset_in"])
        end = start + float(item["width_in"])
        record = item.get("article") if isinstance(item.get("article"), dict) else None
        frame_name = display_name(record) if record else (item.get("name") or "")
        frame = f"frame {item.get('article_no') or ''} {frame_name} {_cad(item.get('price_cad'))}".strip()
        doors = door_phrase(float(item["width_in"]), height)
        cabinets.append(
            f"{titles[item['kind']]}, {float(item['width_in']):.0f} in "
            f"({item.get('wall_id')}, {start:.0f}–{end:.0f} in): {frame} + {doors}"
        )
    for corner in corners:
        walls = " and ".join(corner.get("ends") or {})
        article = corner.get("article") if isinstance(corner.get("article"), dict) else {}
        article_no = corner.get("article_no") or article.get("article") or ""
        price = article.get("price_cad")
        frame_name = display_name(article) if article else (corner.get("name") or "")
        span = float(corner.get("span_in") or 0)
        if corner["kind"] == "corner_base":
            door = corner_set(catalog, style)
            if door:
                extra = f" + 1 corner door set {door['article']} {display_name(door)} {_cad(door.get('price_cad'))}"
                if door.get("alternate_article"):
                    extra += f". The other hand is {door['alternate_article']}"
            else:
                extra = " + corner door 13x30 in is not stocked in this front"
            title = "Corner base"
        else:
            extra = ". This catalog has no separate door for the corner wall cabinet"
            title = "Corner wall cabinet"
        cabinets.append(
            f"{title}, {span:.0f} in ({walls}): frame {article_no} {frame_name} {_cad(price)}{extra}".strip()
        )

    index = _article_index(catalog)
    skip = {"door", "corner_door", "base_frame", "wall_frame", "corner_base_frame", "corner_wall_frame"}
    buckets = {"hinge": "hardware", "leg": "hardware", "suspension_rail": "hardware", "toe_kick": "hardware", "cover_panel": "panels", "worktop": "worktops"}
    grouped = {"hardware": [], "panels": [], "worktops": []}
    unresolved = []
    for line in bom:
        if not line.get("article"):
            unresolved.append(line.get("name") or "Unresolved item")
            continue
        record = index.get(line["article"]) or {}
        role = record.get("role") or ""
        if role in skip:
            continue
        pack_qty = line.get("pack_qty") or record.get("pack_qty") or 1
        unit = "a pack" if pack_qty > 1 else "each"
        text = (
            f"{line.get('name')} · {line['article']} · {line.get('qty')} pieces, "
            f"{line.get('packs')} packs · {_cad(line.get('unit_price_cad'))} {unit} · {_cad(line.get('line_total_cad'))}"
        )
        grouped[buckets.get(role, "hardware")].append(text)
    if any(item["kind"] in ("filler", "wall_filler") for item in items) and grouped["panels"]:
        grouped["panels"].insert(0, "Filler strips are cut from the cover panels below.")
    return {
        "front_id": style,
        "front_name": front.get("name") or style,
        "sentence": "The front is transferred onto every cabinet frame.",
        "color_note": front.get("color_note") or "",
        "cabinets": cabinets,
        "hardware": grouped["hardware"],
        "panels": grouped["panels"],
        "worktops": grouped["worktops"],
        "unresolved": unresolved,
        "total": (
            f"Priced subtotal: {_cad(total)}. "
            "The subtotal leaves out appliances, the sink bowl, lighting, delivery, and tax."
        ),
    }


def _bom(catalog: dict, items: list[dict], corners: list[dict], panels: list[dict], worktop_pieces: list[dict], warnings: list[str], style: str = "axstad-white") -> list[dict]:
    lines: dict[tuple, dict] = {}

    def add(article: dict | None, qty: int, description: str) -> None:
        if qty <= 0:
            return
        if article is None:
            key = ("missing", description)
            row = lines.setdefault(key, {
                "article": None,
                "name": description,
                "qty": 0,
                "packs": None,
                "unit_price_cad": None,
                "line_total_cad": None,
                "url": None,
            })
            row["qty"] += qty
            warnings.append(description)
            return
        packs = int(math.ceil(qty / article["pack_qty"]))
        key = article["article"]
        row = lines.setdefault(key, {
            "article": article["article"],
            "name": display_name(article),
            "qty": 0,
            "pack_qty": article["pack_qty"],
            "packs": 0,
            "unit_price_cad": article["price_cad"],
            "line_total_cad": 0,
            "url": "https://www.ikea.com/ca/en/search/?q=" + article["article"].replace(".", ""),
        })
        row["qty"] += qty
        row["packs"] = int(math.ceil(row["qty"] / article["pack_qty"]))
        row["line_total_cad"] = row["packs"] * article["price_cad"]

    base_like = [item for item in items if item["kind"] in CABINET]
    for item in base_like:
        add(item.get("article"), 1, f"base frame {item['width_in']:.0f} in")
        for door in plan_doors(catalog, item["width_in"], 30, style):
            label = f"{style} door, {item['width_in']:.0f} by 30 inches, is not stocked in this front"
            add(door, 1, label)
    for item in items:
        if item["kind"] in ("wall", "over_fridge"):
            add(item.get("article"), 1, f"wall frame {item['width_in']:.0f}x{item['height_in']:.0f}")
            for door in plan_doors(catalog, item["width_in"], item["height_in"], style):
                add(door, 1, f"{style} door, {item['width_in']:.0f} by {item['height_in']:.0f} inches, is not stocked in this front")
    for corner in corners:
        add(corner["article"], 1, corner["name"])
        if corner["kind"] == "corner_base":
            door = corner_set(catalog, style)
            if door:
                add(door, 1, door["name"])
            else:
                add(None, 1, f"Corner door about 13 inches wide by 30 inches tall is not stocked for front {style}.")
            add(hinge(catalog, 153), 2, "153 degree hinge")

    door_count = 0
    corner_door_hinges = 0
    for item in base_like:
        door_count += len(plan_doors(catalog, item["width_in"], 30, style))
    for item in items:
        if item["kind"] in ("wall", "over_fridge"):
            door_count += len(plan_doors(catalog, item["width_in"], item["height_in"], style))
    for corner in corners:
        if corner["kind"] == "corner_wall":
            door_count += 1
        else:
            corner_door_hinges += 2
    regular_hinges = door_count * 2
    add(hinge(catalog, 110), regular_hinges, "110 degree hinge")

    leg = one(catalog, "leg", height_in=4.5)
    leg_count = 4 * (len(base_like) + sum(1 for corner in corners if corner["kind"] == "corner_base"))
    add(leg, leg_count, "leg")
    if any(corner["kind"] == "corner_base" for corner in corners):
        warnings.append("Corner base is counted with 4 legs. Check the assembly sheet; the larger footprint sometimes wants more.")

    rail = next(item for item in catalog["articles"] if item["role"] == "suspension_rail")
    toe = next(item for item in catalog["articles"] if item["role"] == "toe_kick")
    rail_inches: dict[str, float] = {}
    toe_spans: dict[str, list] = {}
    toe_fillers: dict[str, list] = {}
    for item in items:
        wall_id = item.get("wall_id")
        if not wall_id:
            continue
        if item["kind"] in ("wall", "over_fridge"):
            rail_inches[wall_id] = rail_inches.get(wall_id, 0) + item["width_in"]
        if item["kind"] in ("base", "sink_base", "dishwasher"):
            toe_spans.setdefault(wall_id, []).append((item["offset_in"], item["offset_in"] + item["width_in"]))
        if item["kind"] == "filler":
            toe_fillers.setdefault(wall_id, []).append((item["offset_in"], item["offset_in"] + item["width_in"]))
    toe_inches = 0.0
    for wall_id, spans in toe_spans.items():
        for start, end in _absorb_fillers(spans, toe_fillers.get(wall_id, [])):
            toe_inches += end - start
    for corner in corners:
        if corner["kind"] == "corner_wall":
            for wall_id in corner["ends"]:
                rail_inches[wall_id] = rail_inches.get(wall_id, 0) + corner["span_in"]
        else:
            toe_inches += corner["span_in"] * len(corner["ends"])
    rail_qty = sum(int(math.ceil(length / rail["length_in"])) for length in rail_inches.values() if length > 1)
    add(rail, rail_qty, "suspension rail")
    if toe_inches > 1:
        add(toe, int(math.ceil(toe_inches / toe["length_in"])), "toe kick")

    side_height = catalog["constants"]["leg_height_in"] + catalog["constants"]["base_frame_height_in"]
    panel = side_cover(catalog, catalog["constants"]["base_frame_depth_in"], side_height)
    if panels and panel is None:
        add(None, len(panels), "Exposed cabinet side needs a cover panel, and none in the catalog covers that side.")
    else:
        add(panel, len(panels), "cover panel")

    purchase = sum(piece["width_in"] for piece in worktop_pieces)
    for corner in corners:
        if corner["kind"] == "corner_base":
            purchase -= corner["span_in"]
    for length, count in buy_boards(max(purchase, 0)):
        article = one(catalog, "worktop", length_in=length)
        add(article, count, f"{length} inch worktop")

    rips = [
        {"width_in": item["width_in"], "height_in": item["height_in"]}
        for item in items
        if item["kind"] in ("filler", "wall_filler")
    ]
    bought, notes = buy_cover_rips(catalog, rips)
    for article, count in bought:
        add(article, count, "cover panel for filler")
    for note in notes:
        add(None, 1, note)

    return list(lines.values())


def _choose_wall_height(catalog: dict, requested: int, ceiling: float) -> tuple[int, list[str]]:
    const = catalog["constants"]
    bottom = const["leg_height_in"] + const["base_frame_height_in"] + const["counter_thickness_in"] + const["wall_gap_above_counter_in"]
    warnings = []
    for height in (requested, 30, 20):
        if height > requested:
            continue
        if bottom + height <= ceiling + 0.1 and widths(catalog, "wall_frame", height):
            if height != requested:
                warnings.append(f"Wall cabinets stepped down from {requested} to {height} inches so they fit under the ceiling.")
            return height, warnings
    warnings.append("No wall-cabinet height fits this ceiling. Base cabinets only.")
    return 0, warnings


def design_room(room: dict, prefs: dict, catalog: dict) -> dict:
    catalog = sized_catalog(catalog, prefs)
    const = catalog["constants"]
    warnings: list[str] = []
    if room.get("color_warning"):
        warnings.append(room["color_warning"])
    corner_span = const["corner_base_span_in"] if room["shape"] in ("L", "U") else 0
    frames = wall_frames(room, corner_span)
    for frame in frames:
        frame["ceiling"] = room["ceiling_height_in"]
    if room["shape"] == "galley":
        aisle = float(room.get("room_depth_in") or 120) - 2 * const["base_frame_depth_in"]
        if aisle < 42:
            warnings.append(f"Aisle is about {aisle:.0f} inches. 42 inches is a tight working clearance.")
        elif "room_depth_in" not in room:
            warnings.append("Galley wall-to-wall distance was not given. Assumed 120 inches.")

    segments = []
    for frame in frames:
        for segment in _segments(frame):
            segments.append((frame, segment, segment[1] - segment[0]))
        if frame["corner_start"] + frame["corner_end"] >= frame["length_in"]:
            warnings.append(f"{frame['id']} is shorter than the corner cabinets that meet there.")

    appliance_id = prefs.get("appliance_wall")
    primary = None
    if appliance_id:
        owned = [row for row in segments if row[0]["id"] == appliance_id]
        if owned:
            primary = max(owned, key=lambda row: row[2])
        else:
            warnings.append(f"No wall named {appliance_id}. Appliances went on the longest run.")
    if primary is None and segments:
        primary = max(segments, key=lambda row: row[2])

    items: list[dict] = []
    for frame, segment, _length in segments:
        use_appliances = primary is not None and frame is primary[0] and segment == primary[1]
        items.extend(_layout_segment(frame, segment, use_appliances, catalog, prefs, warnings))

    height, height_warnings = _choose_wall_height(catalog, prefs["wall_height_in"], room["ceiling_height_in"])
    warnings.extend(height_warnings)
    if height:
        for frame in frames:
            wall_bases = [item for item in items if item.get("wall_id") == frame["id"]]
            items.extend(_wall_run(frame, wall_bases, catalog, height, warnings))

    corners = []
    if room["shape"] in ("L", "U"):
        pairs = [("start-end", frames[0], frames[1])]
        if room["shape"] == "U":
            pairs.append(("end-start", frames[1], frames[2]))
        # frames already encode which end is the corner.
        joins = []
        if room["shape"] == "L":
            joins = [(frames[0], "end", frames[1], "start")]
        else:
            joins = [(frames[0], "end", frames[1], "start"), (frames[1], "end", frames[2], "start")]
        for left, left_end, right, right_end in joins:
            base = one(catalog, "corner_base_frame", height_in=30)
            corners.append({
                "kind": "corner_base",
                "name": base["name"] if base else "corner base",
                "article": base,
                "span_in": corner_span,
                "depth_in": 24,
                "height_in": 30,
                "y_in": const["leg_height_in"],
                "ends": {left["id"]: left_end, right["id"]: right_end},
            })
            if height:
                wall = one(catalog, "corner_wall_frame", height_in=height)
                if wall:
                    bottom = const["leg_height_in"] + 30 + const["counter_thickness_in"] + const["wall_gap_above_counter_in"]
                    corners.append({
                        "kind": "corner_wall",
                        "name": wall["name"],
                        "article": wall,
                        "span_in": wall["span_in"],
                        "depth_in": const["wall_frame_depth_in"],
                        "height_in": height,
                        "y_in": bottom,
                        "ends": {left["id"]: left_end, right["id"]: right_end},
                    })
                    extra = corner_span - wall["span_in"]
                    filler_frame = one(catalog, "wall_frame", width_in=extra, height_in=height)
                    if filler_frame and abs(extra - filler_frame["width_in"]) < 0.2:
                        for host, end_name in ((left, left_end), (right, right_end)):
                            offset =  wall["span_in"] if end_name == "start" else host["length_in"] - corner_span
                            items.append({
                                "kind": "wall",
                                "wall_id": host["id"],
                                "offset_in": offset,
                                "width_in": extra,
                                "depth_in": const["wall_frame_depth_in"],
                                "height_in": height,
                                "y_in": bottom,
                                "article": filler_frame,
                            })
                    elif extra >= 1:
                        warnings.append(
                            f"Corner leaves a {extra:.0f} inch strip beside the {wall['span_in']:.0f} inch corner wall cabinet, and no frame of that width is in the catalog."
                        )

    extras, schedule, notes = stamp_and_place(
        items,
        frames,
        prefs,
        const,
        [corner for corner in corners if corner["kind"] == "corner_base"],
    )
    items.extend(extras)
    warnings.extend(notes)

    for index, item in enumerate(items, start=1):
        item["id"] = f"item-{index}"
        if "article" in item and isinstance(item["article"], dict):
            item["article_no"] = item["article"]["article"]
            item["name"] = item["article"]["name"]
            item["price_cad"] = item["article"]["price_cad"]
    for index, corner in enumerate(corners, start=1):
        corner["id"] = f"corner-{index}"
        article = corner.get("article")
        if isinstance(article, dict):
            corner["article_no"] = article["article"]

    pieces = _worktops(frames, items, [corner for corner in corners if corner["kind"] == "corner_base"])
    panels = _exposed_sides(items)
    style = prefs.get("front_style") or "axstad-white"
    bom = _bom(catalog, items, corners, panels, pieces, warnings, style)
    # Warnings from missing articles were appended once per add() call. Collapse duplicates.
    deduped = []
    seen = set()
    for warning in warnings:
        if warning not in seen:
            seen.add(warning)
            deduped.append(warning)
    priced = sum(line["line_total_cad"] or 0 for line in bom)
    buy = build_buy(catalog, prefs, frames, items, corners, bom, priced)
    return {
        "room": room,
        "preferences": prefs,
        "frames": [
            {
                "id": frame["id"],
                "length_in": frame["length_in"],
                "origin": frame["origin"],
                "direction": frame["direction"],
                "inward": frame["inward"],
                "corner_start": frame["corner_start"],
                "corner_end": frame["corner_end"],
            }
            for frame in frames
        ],
        "items": items,
        "corners": corners,
        "worktops": pieces,
        "panels": panels,
        "appliances": schedule,
        "bom": bom,
        "buy": buy,
        "warnings": deduped,
        "total_price_cad": priced,
        "price_as_of": catalog["as_of"],
        "currency": catalog["currency"],
    }
