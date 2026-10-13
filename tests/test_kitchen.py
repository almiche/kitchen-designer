from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from kitchen_designer.catalog import load_catalog, panel_rip_in, side_cover
from kitchen_designer.packet import render_packet
from kitchen_designer.colors import parse_hex, sample_image
from kitchen_designer.rehydrate import parse_inches, rehydrate_catalog
from kitchen_designer.room import normalize_preferences, normalize_room
from kitchen_designer.service import design_kitchen, export_model, export_stl
from kitchen_designer.usdz import write_usdz
from kitchen_designer.view import HFOV, _camera_point, _open_floor, render_rgb, shot_list
from kitchen_designer.solve import buy_boards, buy_cover_rips, design_room, pack


STRAIGHT = {
    "name": "Straight 12 ft",
    "shape": "straight",
    "ceiling_height_in": 96,
    "walls": [{
        "id": "back",
        "length_in": 144,
        "openings": [{"kind": "window", "offset_in": 48, "width_in": 36, "sill_in": 42, "height_in": 36}],
    }],
    "photo_observations": "One window on the only wall.",
}


def floor_items(design, wall_id=None):
    kinds = {"base", "sink_base", "filler", "fridge", "range", "dishwasher"}
    rows = [item for item in design["items"] if item["kind"] in kinds]
    if wall_id:
        rows = [item for item in rows if item["wall_id"] == wall_id]
    return sorted(rows, key=lambda item: item["offset_in"])


def _write_png(path, width, height, pixel):
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            raw.extend(pixel(x, y, width, height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"")
    path.write_bytes(png)


def assert_tiled(test, items, start, end):
    cursor = start
    for item in items:
        test.assertAlmostEqual(item["offset_in"], cursor, places=2)
        cursor += item["width_in"]
    test.assertAlmostEqual(cursor, end, places=2)


class SolveTests(unittest.TestCase):
    def setUp(self):
        self.catalog = load_catalog()

    def test_pack_prefers_full_coverage(self):
        chosen, leftover = pack(72, [12, 15, 18, 24, 30, 36])
        self.assertEqual(sum(chosen), 72)
        self.assertEqual(leftover, 0)
        self.assertLessEqual(len(chosen), 3)

    def test_boards_cover_with_least_waste(self):
        self.assertEqual(buy_boards(78), [(98, 1)])
        self.assertEqual(buy_boards(74), [(74, 1)])
        self.assertEqual(sum(length * count for length, count in buy_boards(200)), 222)

    def test_straight_run_tiles_and_puts_sink_under_window(self):
        design = design_room(normalize_room(STRAIGHT), normalize_preferences({}), self.catalog)
        items = floor_items(design, "back")
        assert_tiled(self, items, 0, 144)
        kinds = [(item["kind"], item["width_in"]) for item in items]
        self.assertEqual(kinds, [
            ("filler", 4),
            ("fridge", 36),
            ("filler", 8),
            ("sink_base", 36),
            ("dishwasher", 24),
            ("range", 30),
            ("filler", 6),
        ])
        sink = next(item for item in items if item["kind"] == "sink_base")
        self.assertEqual(sink["offset_in"], 48)
        self.assertEqual(sink["article_no"], "802.653.98")
        fridge = next(item for item in items if item["kind"] == "fridge")
        self.assertEqual(fridge["offset_in"], 4)
        self.assertEqual(items[0]["reason"], "fridge-wall")
        work = design["worktops"]
        self.assertEqual(len(work), 1)
        self.assertAlmostEqual(work[0]["width_in"], 68)
        boards = [line for line in design["bom"] if line["article"] == "106.090.35"]
        self.assertEqual(boards[0]["qty"], 1)
        covers = [line for line in design["bom"] if line["article"] == "304.177.52"]
        self.assertEqual(covers[0]["qty"], 3)
        self.assertGreater(design["total_price_cad"], 0)
        self.assertAlmostEqual(
            design["total_price_cad"],
            sum(line["line_total_cad"] or 0 for line in design["bom"]),
        )
        wall = [item for item in design["items"] if item["kind"] == "wall"]
        self.assertEqual(sorted(item["width_in"] for item in wall), [24])
        over = [item for item in design["items"] if item["kind"] == "over_fridge"]
        self.assertEqual(over[0]["article_no"], "302.654.71")
        self.assertEqual(fridge["model_id"], "fridge-french-36")
        self.assertEqual(fridge["finish"], "stainless")
        hoods = [item for item in design["items"] if item["kind"] == "hood"]
        self.assertEqual([(item["width_in"], item["model_id"]) for item in hoods], [(30, "hood-30")])
        faucets = [item for item in design["items"] if item["kind"] == "faucet"]
        self.assertEqual(len(faucets), 1)
        self.assertEqual(faucets[0]["model_id"], "faucet-pull-down")
        self.assertEqual([item for item in design["items"] if item["kind"] == "microwave"], [])
        self.assertTrue(any(row["id"] == "microwave-counter" and row["placed"] is False for row in design["appliances"]))
        self.assertTrue(all(line.get("article") for line in design["bom"]))
        self.assertEqual(self.catalog["constants"]["fridge_width_in"], 36)
        self.assertEqual(self.catalog["constants"]["range_width_in"], 30)
        self.assertEqual(design["preferences"]["front_style"], "axstad-white")
        self.assertEqual(design["total_price_cad"], 975)
        self.assertTrue(any(line["article"] == "004.260.55" for line in design["bom"]))
        self.assertIn("802.653.98", next(line for line in design["buy"]["cabinets"] if line.startswith("Sink base")))
        self.assertIn("transferred", design["buy"]["sentence"])

    def test_a_front_transfers_and_names_what_to_buy(self):
        with self.assertRaises(ValueError):
            normalize_preferences({"front_style": "not-a-front"})
        design = design_room(
            normalize_room(STRAIGHT),
            normalize_preferences({"front_style": "voxtorp-matt-white"}),
            self.catalog,
        )
        articles = {line["article"] for line in design["bom"]}
        self.assertIn("802.733.22", articles)
        self.assertNotIn("004.260.55", articles)
        self.assertEqual(design["total_price_cad"], 975)
        packet = render_packet(design)
        self.assertIn("## What to buy", packet)
        self.assertIn("transferred", packet)
        self.assertIn("Sink base, 36 in", packet)
        self.assertNotIn("## Not a stocked article", packet)
        sink = next(line for line in design["buy"]["cabinets"] if line.startswith("Sink base"))
        self.assertIn("802.653.98", sink)
        self.assertIn("2 doors 802.733.22", sink)

    def test_filler_strips_come_from_cover_panels(self):
        self.assertEqual(side_cover(self.catalog, 24, 34.5)["article"], "304.177.52")
        wide, notes = buy_cover_rips(self.catalog, [
            {"width_in": 4, "height_in": 34.5},
            {"width_in": 8, "height_in": 34.5},
            {"width_in": 6, "height_in": 34.5},
        ])
        self.assertEqual(notes, [])
        self.assertEqual([(panel["article"], count) for panel, count in wide], [("304.177.52", 1)])
        self.assertGreaterEqual(panel_rip_in(wide[0][0], 34.5), 18)
        narrow, _notes = buy_cover_rips(self.catalog, [{"width_in": 4, "height_in": 34.5}])
        self.assertEqual(narrow[0][0]["article"], "905.678.33")
        self.assertEqual(narrow[0][1], 1)

    def test_l_shape_keeps_the_corner_clear(self):
        room = normalize_room({
            "name": "L",
            "shape": "L",
            "ceiling_height_in": 96,
            "walls": [
                {"id": "left", "length_in": 96, "openings": []},
                {"id": "back", "length_in": 132, "openings": [
                    {"kind": "window", "offset_in": 70, "width_in": 36, "sill_in": 42, "height_in": 36},
                ]},
            ],
        })
        design = design_room(room, normalize_preferences({"appliance_wall": "back"}), self.catalog)
        self.assertTrue(any(corner["kind"] == "corner_base" for corner in design["corners"]))
        for item in floor_items(design, "left"):
            self.assertLessEqual(item["offset_in"] + item["width_in"], 96 - 38 + 0.1)
        for item in floor_items(design, "back"):
            self.assertGreaterEqual(item["offset_in"], 38 - 0.1)
        corner_lines = [line for line in design["bom"] if line.get("article") == "705.967.56"]
        self.assertEqual(corner_lines[0]["qty"], 1)

    def test_other_appliance_sizes_and_finishes(self):
        with self.assertRaises(ValueError):
            normalize_preferences({"range_width_in": 29})
        wide = design_room(normalize_room(STRAIGHT), normalize_preferences({"range_width_in": 36, "finish": "black"}), self.catalog)
        items = floor_items(wide, "back")
        assert_tiled(self, items, 0, 144)
        stove = next(item for item in items if item["kind"] == "range")
        self.assertEqual(stove["width_in"], 36)
        self.assertEqual(stove["model_id"], "range-36")
        self.assertEqual(stove["finish"], "black")
        self.assertEqual(stove["offset_in"] + stove["width_in"], 144)
        self.assertEqual(next(item["model_id"] for item in wide["items"] if item["kind"] == "hood"), "hood-36")
        self.assertEqual(self.catalog["constants"]["fridge_width_in"], 36)
        self.assertEqual(self.catalog["constants"]["range_width_in"], 30)

        top = design_room(
            normalize_room(STRAIGHT),
            normalize_preferences({"fridge_style": "top-freezer", "fridge_width_in": 30, "finish": "white"}),
            self.catalog,
        )
        top_items = floor_items(top, "back")
        assert_tiled(self, top_items, 0, 144)
        fridge = next(item for item in top_items if item["kind"] == "fridge")
        self.assertEqual(fridge["width_in"], 30)
        self.assertEqual(fridge["height_in"], 67)
        self.assertEqual(fridge["model_id"], "fridge-top-30")
        self.assertEqual(fridge["finish_rgb"], [0.94, 0.94, 0.93])
        over = [item for item in top["items"] if item["kind"] == "over_fridge"]
        self.assertEqual(over[0]["width_in"], 30)

        otr = design_room(normalize_room(STRAIGHT), normalize_preferences({"vent": "otr", "faucet": "bridge"}), self.catalog)
        self.assertFalse(any(item["kind"] == "hood" for item in otr["items"]))
        micros = [item for item in otr["items"] if item["kind"] == "microwave"]
        self.assertEqual([(item["mount"], item["model_id"]) for item in micros], [("otr", "microwave-otr-30")])
        self.assertEqual(next(item["model_id"] for item in otr["items"] if item["kind"] == "faucet"), "faucet-bridge")
        self.assertFalse(any("open counter" in warning for warning in otr["warnings"]))
        narrow = design_room(normalize_room(STRAIGHT), normalize_preferences({"range_width_in": 28, "fridge_style": "top-freezer", "fridge_width_in": 28}), self.catalog)
        narrow_range = next(item for item in narrow["items"] if item["kind"] == "range")
        narrow_fridge = next(item for item in narrow["items"] if item["kind"] == "fridge")
        self.assertEqual((narrow_range["model_id"], narrow_range["width_in"]), ("range-28", 28))
        self.assertEqual((narrow_fridge["model_id"], narrow_fridge["width_in"], narrow_fridge["height_in"]), ("fridge-top-28", 28, 66))


class OutputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["KITCHEN_DESIGNER_HOME"] = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop("KITCHEN_DESIGNER_HOME", None)

    def test_design_writes_a_glb_and_packet(self):
        design = design_kitchen({"room": STRAIGHT})
        model = Path(design["files"]["model"])
        data = model.read_bytes()
        self.assertEqual(data[:4], b"glTF")
        length = struct.unpack_from("<I", data, 8)[0]
        self.assertEqual(length, len(data))
        json_len = struct.unpack_from("<I", data, 12)[0]
        self.assertEqual(data[16:20], b"JSON")
        document = json.loads(data[20:20 + json_len])
        self.assertEqual(document["asset"]["version"], "2.0")
        self.assertGreater(len(document["nodes"]), 5)
        for node in document["nodes"]:
            self.assertTrue(all(value > 0 for value in node["scale"]))
        packet = Path(design["files"]["packet"]).read_text()
        self.assertIn("| 802.653.98 |", packet)
        self.assertIn("| 304.177.52 |", packet)
        self.assertIn("Filler strips add up to 18.0 inches", packet)
        self.assertNotIn("## Not a stocked article", packet)
        self.assertIn("## What to buy", packet)
        self.assertIn("transferred", packet)
        self.assertIn("Priced subtotal", packet)
        bom = json.loads(Path(design["files"]["bom"]).read_text())
        self.assertTrue(all(line.get("article") for line in bom["lines"]))
        again = export_model(design["id"])
        self.assertTrue(Path(again["path"]).is_file())
        self.assertTrue(Path(again["stl"]).is_file())
        walk = Path(design["files"]["walk"])
        self.assertTrue(walk.is_file())
        page = walk.read_text()
        self.assertIn("WASD", page)
        self.assertIn("views/facing.png", page)
        facing = Path(design["views"]["images"][0]["path"])
        png = facing.read_bytes()
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        packet = Path(design["files"]["packet"]).read_text()
        self.assertIn("## First person", packet)
        self.assertIn("walk.html", packet)
        self.assertIn("views/facing.png", packet)
        self.assertIn("Filler strips add up to 18.0 inches", packet)
        self.assertIn("kitchen.usdz", packet)
        self.assertIn("AirDrop", packet)
        self.assertIn("Sink base, 36 in", packet)
        self.assertIn("36 x 24 x 30 in", packet)
        self.assertIn("from 48 to 84 in", packet)
        self.assertIn("802.653.98", page)
        self.assertIn('"measures"', page)
        self.assertIn("144 in", page)
        self.assertIn("Ceiling height 96 in", page)
        self.assertIn("Products in this design", page)
        self.assertIn("What to buy", page)
        self.assertIn("transferred", page)
        sink = next(node for node in document["nodes"] if "802.653.98" in node.get("name", ""))
        self.assertIn("Sink base", sink["extras"]["product"])
        self.assertIn("36 x 24 x 30 in", sink["extras"]["product"])
        self.assertIn("from 48 to 84 in", sink["extras"]["product"])
        self.assertIn("802.653.98", " ".join(document["asset"]["extras"]["products"]))
        self.assertIn("Ceiling height 96 in", " ".join(document["asset"]["extras"]["products"]))
        products = Path(design["files"]["stl"]).parent / "print" / "products.txt"
        self.assertIn("802.653.98", products.read_text())
        self.assertIn("Sink base", products.read_text())
        self.assertIn("36 x 24 x 30 in", products.read_text())
        self.assertIn("Counter height", products.read_text())
        png_h = struct.unpack(">I", png[20:24])[0]
        self.assertGreater(png_h, 288)
        usdz = Path(design["files"]["usdz"])
        self.assertEqual(usdz.read_bytes()[:2], b"PK")
        self.assertIn('rel="ar"', Path(design["files"]["ar"]).read_text())
        self.assertIn("802.653.98", Path(design["files"]["ar"]).read_text())
        import zipfile
        usda = zipfile.ZipFile(usdz).read("kitchen.usda").decode()
        self.assertIn("802.653.98", usda)
        self.assertIn("Sink base", usda)

    def test_first_person_center_sees_the_box(self):
        boxes = [{
            "name": "block",
            "x": 0, "y": 0, "z": 0,
            "sx": 40, "sy": 40, "sz": 20,
            "color": [0.85, 0.05, 0.05],
        }]
        seen = render_rgb(
            boxes,
            {"eye": [20, 20, 80], "yaw": 0, "pitch": 0},
            80, 48,
            background=(0.05, 0.08, 0.3),
        )
        center = (24 * 80 + 40) * 3
        red, green, blue = seen[center], seen[center + 1], seen[center + 2]
        self.assertGreater(red, 80)
        self.assertGreater(red, green * 3)
        corner = seen[0], seen[1], seen[2]
        self.assertGreater(corner[2], corner[0])

    def test_yaw_zero_looks_toward_negative_z(self):
        import math

        eye = [10.0, 62.0, 80.0]
        ahead = _camera_point(10, 62, 70, eye, 0.0, 0.0)
        right = _camera_point(20, 62, 80, eye, 0.0, 0.0)
        self.assertGreater(ahead[2], 5)
        self.assertLess(abs(ahead[0]), 0.01)
        self.assertGreater(right[0], 5)
        self.assertLess(abs(right[2]), 0.01)
        yaw = math.pi / 2
        self.assertAlmostEqual(math.sin(yaw), 1.0)
        self.assertAlmostEqual(-math.cos(yaw), 0.0)
        front = _camera_point(20, 62, 80, eye, yaw, 0.0)
        self.assertGreater(front[2], 5)
        page = (ROOT / "src/kitchen_designer/view.py").read_text()
        self.assertIn("const fx = Math.sin(yaw), fz = -Math.cos(yaw);", page)
        self.assertIn("const rx = Math.cos(yaw), rz = Math.sin(yaw);", page)
        self.assertIn("const camX = dx * cosY + dz * sinY;", page)
        self.assertIn("const camZ = dx * sinY - dz * cosY;", page)

    def test_facing_shot_stands_in_front_of_the_run(self):
        import math

        design = design_room(normalize_room(STRAIGHT), normalize_preferences({}), load_catalog())
        boxes = [{
            "name": "floor", "x": -30.0, "y": -0.4, "z": -30.0,
            "sx": 204.0, "sy": 0.4, "sz": 84.0, "color": [0.5, 0.5, 0.5],
        }]
        _open_floor(boxes, design)
        shots = shot_list(design, boxes)
        facing, along, detail = shots
        floor = boxes[0]
        self.assertEqual(facing["name"], "facing")
        self.assertAlmostEqual(facing["eye"][1], 62.0)
        self.assertGreater(facing["eye"][2], 80)
        self.assertAlmostEqual(facing["yaw"], 0.0, places=2)
        self.assertGreaterEqual(facing["eye"][0], floor["x"] + 6)
        self.assertLessEqual(facing["eye"][0], floor["x"] + floor["sx"] - 6)
        self.assertGreaterEqual(facing["eye"][2], floor["z"] + 6)
        self.assertLessEqual(facing["eye"][2], floor["z"] + floor["sz"] - 6)
        limit = math.tan(HFOV / 2)
        for x in (4.0, 140.0):
            cam = _camera_point(x, 45, 24, facing["eye"], facing["yaw"], facing["pitch"])
            self.assertGreater(cam[2], 1)
            self.assertLess(abs(cam[0] / cam[2]), limit)
        aim = _camera_point(100, 42, 12, along["eye"], along["yaw"], along["pitch"])
        self.assertGreater(aim[2], 1)
        self.assertEqual(detail["name"], "sink")
        self.assertLess(detail["pitch"], 0)

    def test_usdz_sits_on_the_ground_at_real_size(self):
        import io
        import zipfile

        path = Path(self.tmp.name) / "kitchen.usdz"
        write_usdz(path, [
            {
                "name": "floor",
                "material": 6,
                "translation": [0.0, -0.01016, 0.0],
                "scale": [3.6576, 0.01016, 1.0],
                "color": [0.2, 0.4, 0.6],
            },
            {
                "name": "cabinet",
                "material": 0,
                "translation": [0.0, 0.0, 0.0],
                "scale": [0.6096, 0.762, 0.6096],
            },
        ])
        data = path.read_bytes()
        self.assertEqual(data[:2], b"PK")
        name_len, extra_len = struct.unpack_from("<HH", data, 26)
        self.assertEqual((30 + name_len + extra_len) % 64, 0)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            usda = archive.read("kitchen.usda").decode()
        self.assertIn("metersPerUnit = 1", usda)
        self.assertIn('upAxis = "Y"', usda)
        self.assertIn("UsdPreviewSurface", usda)
        self.assertIn('subdivisionScheme = "none"', usda)
        self.assertIn("(0, 0, 0)", usda)
        self.assertIn("3.6576", usda)
        page = Path(self.tmp.name, "ar.html").read_text()
        self.assertIn('rel="ar" href="kitchen.usdz"', page)

    def test_photo_colors_and_printable_stl(self):
        room = dict(STRAIGHT)
        room["floor_color"] = "#336699"
        room["wall_color"] = "#d9d4cc"
        room["surround_color"] = "#1c3a5f"
        design = design_kitchen({
            "room": room,
            "preferences": {"finish": "white", "print_scale": 20},
        })
        model = Path(design["files"]["model"]).read_bytes()
        json_len = struct.unpack_from("<I", model, 12)[0]
        document = json.loads(model[20:20 + json_len])
        def material_of(node):
            primitive = document["meshes"][node["mesh"]]["primitives"][0]
            return document["materials"][primitive["material"]]

        floor = next(node for node in document["nodes"] if node["name"] == "floor")
        factor = material_of(floor)["pbrMetallicRoughness"]["baseColorFactor"]
        self.assertGreater(factor[2], factor[1])
        self.assertGreater(factor[1], factor[0])
        self.assertIn("baseColorTexture", material_of(floor)["pbrMetallicRoughness"])
        surround = next(node for node in document["nodes"] if node["name"].startswith("surround-"))
        surround_color = material_of(surround)["pbrMetallicRoughness"]["baseColorFactor"]
        self.assertGreater(surround_color[2], surround_color[0])
        fridge = next(node for node in document["nodes"] if "French-door" in node["name"])
        fridge_color = material_of(fridge)["pbrMetallicRoughness"]["baseColorFactor"]
        self.assertGreater(fridge_color[0], 0.9)
        for node in document["nodes"]:
            self.assertTrue(all(value > 0 for value in node["scale"]))
        full = Path(design["files"]["stl"]).read_bytes()
        cabinets = Path(design["files"]["cabinets"]).read_bytes()
        rest = Path(design["files"]["without_cabinets"]).read_bytes()
        self.assertTrue(full.startswith(b"kitchen-designer schematic print"))
        full_tris = struct.unpack_from("<I", full, 80)[0]
        cab_tris = struct.unpack_from("<I", cabinets, 80)[0]
        rest_tris = struct.unpack_from("<I", rest, 80)[0]
        self.assertGreater(cab_tris, 0)
        self.assertGreater(rest_tris, 0)
        self.assertEqual(full_tris, cab_tris + rest_tris)
        self.assertNotEqual(full, cabinets)
        packet = Path(design["files"]["packet"]).read_text()
        self.assertIn("## Appliances", packet)
        self.assertIn("## Print", packet)
        self.assertIn("1:20", packet)
        self.assertIn("print/cabinets.stl", packet)
        self.assertIn("#336699", packet)
        self.assertIn("Filler strips add up to 18.0 inches", packet)
        self.assertNotIn("## Not a stocked article", packet)
        bom = json.loads(Path(design["files"]["bom"]).read_text())
        self.assertTrue(any(row["id"] == "range-30" and row["finish"] == "white" for row in bom["appliances"]))
        self.assertNotIn("Range, 30", " ".join(line["name"] for line in bom["lines"]))
        exported = export_stl(design["id"])
        self.assertIn("kitchen.stl", exported["summary"])

    def test_photo_sampler_reads_floor_and_surround(self):
        self.assertEqual(parse_hex("#369"), parse_hex("#336699"))
        path = Path(self.tmp.name) / "bands.png"

        def pixel(x, y, width, height):
            if y < height / 5:
                return (10, 20, 200)
            if height / 3 <= y < height * 2 / 3:
                return (150, 148, 146)
            if y >= height * 3 / 4:
                return (140, 70, 30)
            return (240, 240, 240)

        _write_png(path, 80, 60, pixel)
        colors = sample_image(str(path))
        floor = parse_hex(colors["floor"])
        wall = parse_hex(colors["wall"])
        surround = parse_hex(colors["surround"])
        self.assertGreater(floor[0], floor[2])
        self.assertGreater(surround[2], surround[0])
        self.assertLess(abs(wall[0] - wall[1]), 0.08)


class McpTests(unittest.TestCase):
    def test_stdio_round_trip(self):
        tmp = tempfile.TemporaryDirectory()
        env = os.environ.copy()
        env["KITCHEN_DESIGNER_HOME"] = tmp.name
        env["PYTHONPATH"] = str(ROOT / "src")
        proc = subprocess.Popen(
            [sys.executable, "-m", "kitchen_designer"],
            cwd=str(ROOT),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        def send(payload):
            raw = json.dumps(payload).encode()
            proc.stdin.write(f"Content-Length: {len(raw)}\r\n\r\n".encode() + raw)
            proc.stdin.flush()

        def read():
            headers = {}
            while True:
                line = proc.stdout.readline()
                if not line:
                    raise RuntimeError(proc.stderr.read().decode())
                if line in (b"\r\n", b"\n"):
                    break
                key, value = line.decode().split(":", 1)
                headers[key.strip().lower()] = value.strip()
            body = proc.stdout.read(int(headers["content-length"]))
            return json.loads(body)

        try:
            send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}}})
            init = read()
            self.assertEqual(init["result"]["serverInfo"]["name"], "kitchen-designer")
            send({"jsonrpc": "2.0", "method": "notifications/initialized"})
            send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            listed = read()
            names = [tool["name"] for tool in listed["result"]["tools"]]
            self.assertEqual(names, ["ingest_room", "design_kitchen", "export_model", "export_packet", "rehydrate_catalog", "export_stl", "export_view"])
            send({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "design_kitchen", "arguments": {"room": STRAIGHT}}})
            called = read()
            self.assertFalse(called["result"]["isError"])
            self.assertIn("Design design-", called["result"]["content"][0]["text"])
        finally:
            proc.stdin.close()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)
            proc.stdout.close()
            proc.stderr.close()
            tmp.cleanup()


class CatalogTests(unittest.TestCase):
    def test_parse_ikea_inch_text(self):
        self.assertEqual(parse_inches('39x103 cm (15x40 1/2 ")'), [15.0, 40.5])
        self.assertEqual(parse_inches('11 cm (4 1/2 ")'), [4.5])
        self.assertEqual(parse_inches('91x61x76 cm (36x24x30 ")'), [36.0, 24.0, 30.0])

    def _copy(self, tmp):
        path = Path(tmp) / "ca_sektion.json"
        path.write_text((ROOT / "data" / "ca_sektion.json").read_text())
        return path

    def test_rehydrate_writes_prices_from_the_fetcher(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._copy(tmp)

            def fetch(article):
                return {"item_no": article.replace(".", ""), "price_cad": 19, "measure": '99x99x99 cm (99x99x99 ")'}

            result = rehydrate_catalog(path=path, fetch=fetch, today="2026-10-14")
            saved = json.loads(path.read_text())
            self.assertEqual(saved["as_of"], "2026-10-14")
            self.assertNotIn("by_article", saved)
            frame = next(item for item in saved["articles"] if item["article"] == "802.653.98")
            self.assertEqual(frame["price_cad"], 19)
            self.assertEqual(frame["width_in"], 36)
            self.assertTrue(any("802.653.98" in row and "stays" in row for row in result["kept"]))

    def test_dry_run_and_total_miss_leave_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._copy(tmp)
            before = path.read_text()
            rehydrate_catalog(path=path, fetch=lambda article: {"item_no": article.replace(".", ""), "price_cad": 19, "measure": ""}, dry_run=True, today="2026-10-14")
            self.assertEqual(path.read_text(), before)
            with self.assertRaises(RuntimeError):
                rehydrate_catalog(path=path, fetch=lambda article: None, today="2026-10-14")
            self.assertEqual(path.read_text(), before)

    def test_offline_refuses_without_a_fetcher(self):
        os.environ["KITCHEN_DESIGNER_OFFLINE"] = "1"
        try:
            with self.assertRaises(RuntimeError):
                rehydrate_catalog()
        finally:
            os.environ.pop("KITCHEN_DESIGNER_OFFLINE", None)


if __name__ == "__main__":
    unittest.main()
