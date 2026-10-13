from __future__ import annotations

import json
import sys
import traceback

from . import __version__
from .catalog import front_ids
from .service import design_kitchen, export_model, export_packet, export_stl, export_view, ingest_room, refresh_catalog

_ROOM = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "shape": {"type": "string", "enum": ["straight", "L", "U", "galley"]},
        "ceiling_height_in": {"type": "number"},
        "room_depth_in": {"type": "number", "description": "Galley only: inches between the two parallel walls."},
        "photo_observations": {"type": "string", "description": "What you can see in the kitchen photo: windows, doors, obstacles, existing appliances."},
        "floor_color": {"type": "string", "description": "Hex color of the floor, such as #8A6A4A. Wins over image_path."},
        "wall_color": {"type": "string", "description": "Hex color of the walls."},
        "surround_color": {"type": "string", "description": "Hex color of the background around the kitchen."},
        "image_path": {"type": "string", "description": "Local photo path. This Mac samples floor, wall, and surround colors from it. Image bytes are not sent."},
        "notes": {"type": "string"},
        "walls": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "length_in": {"type": "number"},
                    "openings": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "kind": {"type": "string", "enum": ["window", "door"]},
                                "offset_in": {"type": "number"},
                                "width_in": {"type": "number"},
                                "sill_in": {"type": "number"},
                                "height_in": {"type": "number"},
                            },
                            "required": ["kind", "offset_in", "width_in"],
                        },
                    },
                },
                "required": ["length_in"],
            },
        },
    },
    "required": ["shape", "walls"],
}

_PREFS = {
    "type": "object",
    "properties": {
        "wall_height_in": {"type": "integer", "enum": [20, 30, 40]},
        "fridge": {"type": "boolean"},
        "range": {"type": "boolean"},
        "sink": {"type": "boolean"},
        "dishwasher": {"type": "boolean"},
        "appliance_wall": {"type": "string"},
        "front_style": {
            "type": "string",
            "enum": front_ids(),
            "description": "Door front transferred onto every cabinet frame. Default is axstad-white.",
        },
        "fridge_style": {"type": "string", "enum": ["french-door", "top-freezer"], "description": "French door, or a freezer above the fridge."},
        "fridge_width_in": {"type": "integer", "description": "French door: 36 or 30. Top freezer: 30 or 28. Default is 36 for French door and 30 for top freezer."},
        "range_width_in": {"type": "integer", "enum": [28, 30, 36]},
        "finish": {"type": "string", "enum": ["stainless", "white", "black"]},
        "vent": {"type": "string", "enum": ["hood", "otr", "none"], "description": "Hood over the range, or a microwave mounted in place of the hood."},
        "faucet": {"type": "string", "enum": ["pull-down", "bridge", "single", "none"]},
        "microwave": {"type": "string", "enum": ["auto", "counter", "none"], "description": "Countertop microwave when a clear counter span exists. Skipped when vent is otr."},
        "print_scale": {"type": "integer", "description": "1:N print scale from 8 to 40. Default 20."},
    },
}

TOOLS = [
    {
        "name": "ingest_room",
        "description": "Save a measured kitchen. Look at the photo yourself and put openings in photo_observations. Pass floor_color, wall_color, and surround_color, or a local image_path so this Mac can sample those bands. Image bytes are not an argument. All sizes are inches.",
        "inputSchema": _ROOM,
    },
    {
        "name": "design_kitchen",
        "description": "Place a Canada SEKTION run from a saved room_id or an inline room. preferences.front_style transfers one door front onto every cabinet and prices those doors. Writes a schematic GLB, a real-size USDZ for iPhone AR, a 1:20 STL set with the cabinets in their own file, a first-person walkthrough, stills from eye height, a cabinet-by-cabinet buy list, and a design packet. Each file names the product and its width, depth, height, and position. Appliance bodies are schematic size classes, not IKEA articles. Prices come from the saved IKEA.ca snapshot. This does not call IKEA.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "room_id": {"type": "string"},
                "room": _ROOM,
                "preferences": _PREFS,
            },
        },
    },
    {
        "name": "export_model",
        "description": "Rewrite the schematic GLB and the printable STL set for a saved design. Boxes are original geometry at SEKTION module sizes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "design_id": {"type": "string"},
                "path": {"type": "string"},
            },
            "required": ["design_id"],
        },
    },
    {
        "name": "export_packet",
        "description": "Rewrite the markdown design packet and purchase list for a saved design.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "design_id": {"type": "string"},
                "path": {"type": "string"},
            },
            "required": ["design_id"],
        },
    },
    {
        "name": "rehydrate_catalog",
        "description": "Refresh prices of the known Canada SEKTION articles from IKEA.ca and write a new as_of date on the saved catalog. Does not add articles. Planning keeps using the saved file until you run this.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dry_run": {"type": "boolean", "description": "Report price changes and leave the saved file as it is."},
            },
        },
    },
    {
        "name": "export_stl",
        "description": "Rewrite the printable STL set for a saved design: the whole kitchen, the cabinets alone, and the kitchen with the cabinets taken out.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "design_id": {"type": "string"},
                "path": {"type": "string", "description": "Directory for the STL files. Defaults to the design folder."},
            },
            "required": ["design_id"],
        },
    },
    {
        "name": "export_view",
        "description": "Rewrite the first-person walkthrough and the eye-height stills for a saved design. Open walk.html in a browser.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "design_id": {"type": "string"},
                "path": {"type": "string", "description": "Directory for walk.html and the views folder. Defaults to the design folder."},
            },
            "required": ["design_id"],
        },
    },
]


def _read_message() -> dict | None:
    headers = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        if b":" in line:
            key, value = line.decode("utf-8", "replace").split(":", 1)
            headers[key.strip().lower()] = value.strip()
    length = int(headers.get("content-length", "0"))
    if length <= 0:
        return None
    body = sys.stdin.buffer.read(length)
    if not body:
        return None
    return json.loads(body)


def _write_message(payload: dict) -> None:
    data = json.dumps(payload).encode()
    sys.stdout.buffer.write(f"Content-Length: {len(data)}\r\n\r\n".encode() + data)
    sys.stdout.buffer.flush()


def _result(message_id, result: dict) -> None:
    _write_message({"jsonrpc": "2.0", "id": message_id, "result": result})


def _error(message_id, code: int, message: str) -> None:
    _write_message({"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}})


def _tool_text(payload: dict, is_error: bool = False) -> dict:
    return {"content": [{"type": "text", "text": payload if isinstance(payload, str) else json.dumps(payload, indent=2)}], "isError": is_error}


def _call(name: str, arguments: dict) -> dict:
    if name == "ingest_room":
        saved = ingest_room(arguments)
        return _tool_text(saved["summary"] + "\nroom_id: " + saved["room_id"])
    if name == "design_kitchen":
        design = design_kitchen(arguments)
        return _tool_text(design["summary"])
    if name == "export_model":
        return _tool_text(export_model(arguments["design_id"], arguments.get("path"))["summary"])
    if name == "export_packet":
        exported = export_packet(arguments["design_id"], arguments.get("path"))
        return _tool_text(exported["summary"])
    if name == "export_stl":
        return _tool_text(export_stl(arguments["design_id"], arguments.get("path"))["summary"])
    if name == "export_view":
        return _tool_text(export_view(arguments["design_id"], arguments.get("path"))["summary"])
    if name == "rehydrate_catalog":
        refreshed = refresh_catalog(arguments.get("dry_run"))
        return _tool_text(refreshed["summary"])
    raise ValueError(f"unknown tool {name}")


def main() -> None:
    while True:
        try:
            message = _read_message()
        except Exception:
            traceback.print_exc(file=sys.stderr)
            return
        if message is None:
            return
        method = message.get("method")
        message_id = message.get("id")
        if message_id is None:
            continue
        try:
            if method == "initialize":
                version = (message.get("params") or {}).get("protocolVersion") or "2024-11-05"
                _result(message_id, {
                    "protocolVersion": version,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "kitchen-designer", "version": __version__},
                })
            elif method == "ping":
                _result(message_id, {})
            elif method == "tools/list":
                _result(message_id, {"tools": TOOLS})
            elif method == "tools/call":
                params = message.get("params") or {}
                _result(message_id, _call(params.get("name"), params.get("arguments") or {}))
            else:
                _error(message_id, -32601, f"method not found: {method}")
        except Exception as exc:
            traceback.print_exc(file=sys.stderr)
            if method == "tools/call":
                _result(message_id, _tool_text(str(exc), True))
            else:
                _error(message_id, -32000, str(exc))
