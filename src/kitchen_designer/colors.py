"""Floor, wall, and surround colors taken from a kitchen photo."""

from __future__ import annotations

import struct
import subprocess
import tempfile
import zlib
from pathlib import Path


def parse_hex(value: str) -> list[float]:
    text = value.strip().lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6:
        raise ValueError(f"color {value} should look like #AABBCC")
    try:
        channels = [int(text[index:index + 2], 16) / 255.0 for index in (0, 2, 4)]
    except ValueError as exc:
        raise ValueError(f"color {value} should look like #AABBCC") from exc
    return channels


def _paeth(left: int, up: int, up_left: int) -> int:
    estimate = left + up - up_left
    dl = abs(estimate - left)
    du = abs(estimate - up)
    dul = abs(estimate - up_left)
    if dl <= du and dl <= dul:
        return left
    if du <= dul:
        return up
    return up_left


def _unfilter(filter_type: int, row: bytes, prev: bytes, bpp: int) -> bytearray:
    out = bytearray(len(row))
    for index, value in enumerate(row):
        left = out[index - bpp] if index >= bpp else 0
        up = prev[index] if index < len(prev) else 0
        up_left = prev[index - bpp] if index >= bpp else 0
        if filter_type == 0:
            sample = value
        elif filter_type == 1:
            sample = (value + left) & 255
        elif filter_type == 2:
            sample = (value + up) & 255
        elif filter_type == 3:
            sample = (value + ((left + up) // 2)) & 255
        elif filter_type == 4:
            sample = (value + _paeth(left, up, up_left)) & 255
        else:
            raise RuntimeError(f"png filter {filter_type} is not supported")
        out[index] = sample
    return out


def _png_header(data: bytes):
    if not data.startswith(b"\x89PNG\r\n\x1a\n") or data[12:16] != b"IHDR":
        return None
    return struct.unpack(">IIBBBBB", data[16:29])


def _png_supported(data: bytes) -> bool:
    header = _png_header(data)
    if header is None:
        return False
    _width, _height, bit_depth, color_type, _compression, _filter, interlace = header
    return interlace == 0 and bit_depth in (8, 16) and color_type in (0, 2, 3, 4, 6)


def _decode_png(data: bytes) -> tuple[int, int, bytes]:
    """Return width, height, and tightly packed RGB bytes. Y grows downward."""
    header = _png_header(data)
    if header is None or not _png_supported(data):
        raise RuntimeError("this png needs a sips conversion before it can be sampled")
    width, height, bit_depth, color_type, _compression, _filter, _interlace = header
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color_type]
    sample_bytes = 2 if bit_depth == 16 else 1
    idat = bytearray()
    palette = b""
    offset = 8
    while offset + 8 <= len(data):
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        chunk = data[offset + 8:offset + 8 + length]
        offset += 12 + length
        if kind == b"PLTE":
            palette = chunk
        elif kind == b"IDAT":
            idat.extend(chunk)
        elif kind == b"IEND":
            break
    raw = zlib.decompress(bytes(idat))
    stride = width * channels * sample_bytes
    expected = height * (stride + 1)
    if len(raw) < expected:
        raise RuntimeError("the png pixel data is shorter than its header")
    rgb = bytearray(width * height * 3)
    prev = bytearray(stride)
    cursor = 0
    for y in range(height):
        recon = _unfilter(raw[cursor], raw[cursor + 1:cursor + 1 + stride], prev, channels * sample_bytes)
        cursor += 1 + stride
        prev = recon
        for x in range(width):
            start = x * channels * sample_bytes
            if color_type == 3:
                index = recon[start]
                red, green, blue = palette[index * 3:index * 3 + 3]
            elif color_type == 0:
                red = green = blue = recon[start]
            elif color_type == 4:
                red = green = blue = recon[start]
            else:
                red, green, blue = recon[start], recon[start + sample_bytes], recon[start + 2 * sample_bytes]
            pixel = (y * width + x) * 3
            rgb[pixel] = red
            rgb[pixel + 1] = green
            rgb[pixel + 2] = blue
    return width, height, bytes(rgb)


def _png_bytes(path: Path) -> bytes:
    data = path.read_bytes()
    if _png_supported(data):
        header = _png_header(data)
        if header and header[0] * header[1] <= 1500 * 1500:
            return data
    dest = Path(tempfile.gettempdir()) / "kitchen-designer-sample.png"
    run = subprocess.run(
        ["sips", "-Z", "480", "-s", "format", "png", str(path), "--out", str(dest)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if run.returncode != 0 or not dest.is_file():
        detail = (run.stderr or run.stdout or "sips could not read the photo").strip()
        raise RuntimeError(detail.splitlines()[-1])
    return dest.read_bytes()


def _average(rgb: bytes, width: int, height: int, x0: int, y0: int, x1: int, y1: int) -> str:
    red = green = blue = count = 0
    step_x = max((x1 - x0) // 24, 1)
    step_y = max((y1 - y0) // 24, 1)
    y = max(y0, 0)
    y_stop = min(y1, height)
    x_stop = min(x1, width)
    while y < y_stop:
        x = max(x0, 0)
        while x < x_stop:
            pixel = (y * width + x) * 3
            red += rgb[pixel]
            green += rgb[pixel + 1]
            blue += rgb[pixel + 2]
            count += 1
            x += step_x
        y += step_y
    if count == 0:
        return "#000000"
    return f"#{red // count:02x}{green // count:02x}{blue // count:02x}"


def sample_image(path: str) -> dict[str, str]:
    """Return hex colors for the floor band, the wall band, and the top surround."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(path)
    width, height, rgb = _decode_png(_png_bytes(source))
    # Image y grows downward. The floor is the bottom band, the surround is the top band.
    return {
        "floor": _average(rgb, width, height, width // 4, height * 3 // 4, width * 3 // 4, height),
        "wall": _average(rgb, width, height, width // 4, height // 3, width * 3 // 4, height * 2 // 3),
        "surround": _average(rgb, width, height, 0, 0, width, height // 5),
    }


def attach_colors(room: dict, payload: dict) -> str | None:
    """Fill room colors from hex fields or from image_path. Returns a warning, if sampling failed."""
    hexes = {}
    warning = None
    image = payload.get("image_path")
    sampled = {}
    if image:
        room["image_path"] = str(image)
        try:
            sampled = sample_image(str(image))
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            warning = f"Could not read colors from {image}: {exc}"
    existing = payload.get("color_hex") if isinstance(payload.get("color_hex"), dict) else {}
    for key, field in (("floor", "floor_color"), ("wall", "wall_color"), ("surround", "surround_color")):
        if payload.get(field):
            hexes[key] = str(payload[field])
        elif key in sampled:
            hexes[key] = sampled[key]
        elif existing.get(key):
            hexes[key] = str(existing[key])
    if hexes:
        room["color_hex"] = hexes
        room["colors"] = {key: parse_hex(value) for key, value in hexes.items()}
    return warning
