from __future__ import annotations

import json
import sys
from pathlib import Path

from .service import design_kitchen, export_model, export_packet, export_stl, export_view, refresh_catalog


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help"):
        print("usage: python3 -m kitchen_designer.cli design room.json")
        print("       python3 -m kitchen_designer.cli packet DESIGN_ID")
        print("       python3 -m kitchen_designer.cli model DESIGN_ID")
        print("       python3 -m kitchen_designer.cli stl DESIGN_ID")
        print("       python3 -m kitchen_designer.cli view DESIGN_ID")
        print("       python3 -m kitchen_designer.cli rehydrate [--dry-run]")
        return 0
    command = args[0]
    if command == "design":
        payload = json.loads(Path(args[1]).read_text())
        design = design_kitchen({"room": payload, "preferences": payload.get("preferences")})
        print(design["summary"])
        return 0
    if command == "packet":
        print(export_packet(args[1])["path"])
        return 0
    if command == "model":
        print(export_model(args[1])["summary"])
        return 0
    if command == "stl":
        print(export_stl(args[1])["summary"])
        return 0
    if command == "view":
        print(export_view(args[1])["summary"])
        return 0
    if command == "rehydrate":
        result = refresh_catalog("--dry-run" in args[1:])
        print(result["summary"])
        return 0
    print(f"unknown command {command}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
