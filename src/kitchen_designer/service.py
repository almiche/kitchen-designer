from __future__ import annotations

from pathlib import Path

from .catalog import load_catalog
from .gltf import write_glb
from .labels import product_lines
from .packet import build_nodes, render_packet
from .print3d import write_print_set
from .rehydrate import rehydrate_catalog
from .room import normalize_preferences, normalize_room
from .solve import design_room
from .store import design_dir, designs_dir, new_id, read_json, write_json
from .usdz import write_usdz
from .view import write_experience


def _strip_articles(value):
    """Drop nested catalog records. Keep article-number strings on purchase lines."""
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            if key == "article" and isinstance(item, dict):
                continue
            cleaned[key] = _strip_articles(item)
        return cleaned
    if isinstance(value, list):
        return [_strip_articles(item) for item in value]
    return value


def _summary(design: dict) -> str:
    room = design["room"]
    lines = [
        f"Design {design['id']} for {room['name']} ({room['shape']}).",
        f"Priced subtotal {design['total_price_cad']:.0f} {design['currency']} at {design['price_as_of']} IKEA.ca prices.",
        (
            f"Front: {(design.get('buy') or {}).get('front_name') or 'AXSTAD matt white'}. "
            "The front is transferred onto every cabinet frame."
        ),
        f"Files: {design['files']['model']}",
        f"Packet: {design['files']['packet']}",
        f"Purchase list: {design['files']['bom']}",
    ]
    if design["files"].get("stl"):
        scale = int((design.get("preferences") or {}).get("print_scale") or (design.get("print") or {}).get("scale") or 20)
        lines.append(f"Print 1:{scale}: {design['files']['stl']}")
        lines.append(f"Cabinets: {design['files'].get('cabinets')}")
        lines.append(f"Without cabinets: {design['files'].get('without_cabinets')}")
    if design["files"].get("walk"):
        lines.append(f"Walk through: {design['files']['walk']}")
        for image in (design.get("views") or {}).get("images") or []:
            lines.append(f"View: {image.get('path') or image.get('file')}")
    if design["files"].get("usdz"):
        lines.append(f"iPhone AR: {design['files']['usdz']}")
    if (design.get("print") or {}).get("products"):
        lines.append(f"Products: {(design.get('files') or {}).get('stl', '')}".rsplit("/", 1)[0] + "/print/products.txt")
    if design["warnings"]:
        lines.append("Checks:")
        lines.extend(f"- {warning}" for warning in design["warnings"])
    lines.append("Run:")
    for item in sorted(design["items"], key=lambda row: (row.get("wall_id", ""), row["offset_in"])):
        label = f" {item['article_no']}" if item.get("article_no") else ""
        lines.append(
            f"- {item.get('wall_id')} {item['offset_in']:.0f}-{item['offset_in'] + item['width_in']:.0f} in "
            f"{item['kind']}{label}"
        )
    return "\n".join(lines)


def ingest_room(payload: dict) -> dict:
    room = normalize_room(payload)
    room_id = new_id("room")
    path = designs_dir() / "rooms"
    path.mkdir(parents=True, exist_ok=True)
    write_json(path / f"{room_id}.json", room)
    return {
        "room_id": room_id,
        "room": room,
        "summary": f"Saved room {room_id}: {room['shape']}, {len(room['walls'])} wall(s), ceiling {room['ceiling_height_in']:.0f} in.",
    }


def _load_room(payload: dict) -> dict:
    if payload.get("room"):
        return normalize_room(payload["room"])
    room_id = payload.get("room_id")
    if not room_id:
        raise ValueError("pass room or room_id")
    path = designs_dir() / "rooms" / f"{room_id}.json"
    if not path.is_file():
        raise ValueError(f"unknown room {room_id}")
    return normalize_room(read_json(path))


def _bom_payload(design: dict) -> dict:
    return {
        "as_of": design["price_as_of"],
        "currency": design["currency"],
        "total_price_cad": design["total_price_cad"],
        "lines": design["bom"],
        "appliances": design.get("appliances") or [],
        "annotations": design.get("annotations") or product_lines(design),
    }


def _write_outputs(design: dict, catalog: dict, folder: Path) -> dict:
    model_path = folder / "kitchen.glb"
    packet_path = folder / "packet.md"
    bom_path = folder / "bom.json"
    printed = write_print_set(design, folder)
    design["print"] = {
        "scale": printed["scale"],
        "stl": "kitchen.stl",
        "cabinets": "print/cabinets.stl",
        "without_cabinets": "print/kitchen-without-cabinets.stl",
        "triangles": printed["triangles"],
        "products": "print/products.txt",
    }
    nodes = build_nodes(design, catalog)
    experience = write_experience(design, nodes, folder)
    design["views"] = experience["record"]
    # write_glb consumes node colors, so the USDZ is written from the same nodes first.
    notes = product_lines(design)
    design["annotations"] = notes
    ar = write_usdz(folder / "kitchen.usdz", nodes, notes)
    design["ar"] = {"usdz": "kitchen.usdz", "page": "ar.html"}
    model = write_glb(model_path, nodes, notes)
    packet_path.write_text(render_packet(design))
    write_json(bom_path, _bom_payload(design))
    return {
        "model": str(model_path),
        "packet": str(packet_path),
        "bom": str(bom_path),
        "stl": printed["stl"],
        "cabinets": printed["cabinets"],
        "without_cabinets": printed["without_cabinets"],
        "walk": experience["walk"],
        "usdz": ar["path"],
        "ar": ar["page"],
        "bytes": model["bytes"],
        "nodes": model["nodes"],
    }


def design_kitchen(payload: dict) -> dict:
    room = _load_room(payload)
    prefs = normalize_preferences(payload.get("preferences"))
    catalog = load_catalog()
    design = design_room(room, prefs, catalog)
    design_id = new_id("design")
    design["id"] = design_id
    public = _strip_articles(design)
    public["id"] = design_id
    folder = designs_dir() / design_id
    folder.mkdir(parents=True, exist_ok=True)
    files = _write_outputs(public, catalog, folder)
    public["files"] = {key: files[key] for key in ("model", "packet", "bom", "stl", "cabinets", "without_cabinets", "walk", "usdz", "ar")}
    write_json(folder / "design.json", public)
    public["summary"] = _summary(public)
    return public


def _saved(design_id: str) -> tuple[dict, dict, Path]:
    folder = design_dir(design_id)
    design = read_json(folder / "design.json")
    return design, load_catalog(), folder


def export_model(design_id: str, path: str | None = None) -> dict:
    design, catalog, folder = _saved(design_id)
    target = Path(path) if path else folder / "kitchen.glb"
    nodes = build_nodes(design, catalog)
    experience = write_experience(design, nodes, target.parent)
    notes = product_lines(design)
    ar = write_usdz(target.with_suffix(".usdz"), nodes, notes)
    model = write_glb(target, nodes, notes)
    printed = write_print_set(design, target.parent)
    scale = int(printed["scale"])
    summary = (
        f"Wrote {target} ({model['bytes']} bytes, {model['nodes']} nodes). "
        f"Print 1:{scale}: {printed['stl']}. Cabinets: {printed['cabinets']}. "
        f"Walk through: {experience['walk']}. "
        f"iPhone AR: {ar['path']}."
    )
    return {
        "path": str(target),
        "bytes": model["bytes"],
        "nodes": model["nodes"],
        "stl": printed["stl"],
        "cabinets": printed["cabinets"],
        "without_cabinets": printed["without_cabinets"],
        "walk": experience["walk"],
        "usdz": ar["path"],
        "ar": ar["page"],
        "summary": summary,
    }


def export_view(design_id: str, path: str | None = None) -> dict:
    """Rewrite the first-person walkthrough and the stills for a saved design."""
    design, catalog, folder = _saved(design_id)
    target = Path(path) if path else folder
    if target.suffix.lower() in (".html", ".png"):
        target = target.parent
    experience = write_experience(design, build_nodes(design, catalog), target)
    names = ", ".join(image["path"] for image in experience["images"])
    summary = f"Wrote {experience['walk']}. Views: {names}."
    return {
        "walk": experience["walk"],
        "images": experience["images"],
        "summary": summary,
    }


def export_stl(design_id: str, path: str | None = None) -> dict:
    """Write the printable set. path is a directory, or an .stl whose folder is used."""
    design, _catalog, folder = _saved(design_id)
    target = Path(path) if path else folder
    if target.suffix.lower() == ".stl":
        target = target.parent
    printed = write_print_set(design, target)
    scale = int(printed["scale"])
    summary = (
        f"Wrote 1:{scale} {printed['stl']} ({printed['triangles']} triangles). "
        f"Cabinets: {printed['cabinets']}. Without cabinets: {printed['without_cabinets']}."
    )
    return {
        "stl": printed["stl"],
        "cabinets": printed["cabinets"],
        "without_cabinets": printed["without_cabinets"],
        "scale": printed["scale"],
        "triangles": printed["triangles"],
        "summary": summary,
    }


def _flag(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes")
    return bool(value)


def refresh_catalog(dry_run=False) -> dict:
    """Refresh known article prices from IKEA.ca and write the snapshot."""
    return rehydrate_catalog(dry_run=_flag(dry_run))


def export_packet(design_id: str, path: str | None = None) -> dict:
    design, _catalog, folder = _saved(design_id)
    target = Path(path) if path else folder / "packet.md"
    target.write_text(render_packet(design))
    bom_path = target.with_suffix(".bom.json") if path else folder / "bom.json"
    write_json(bom_path, _bom_payload(design))
    return {
        "path": str(target),
        "bom": str(bom_path),
        "total_price_cad": design["total_price_cad"],
        "summary": render_packet(design),
    }
