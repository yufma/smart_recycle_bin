"""Draw the civic complex sample's floor plans into server/samples/civic-floor-N.png.

The server copies these into the map folder when the demo is reset to the civic complex, where the
dashboard shows them like an uploaded floor plan. Needs Pillow and a Korean font. From the project root:
    python tools/make_civic_floorplans.py [--font C:/Windows/Fonts/malgun.ttf]
"""
import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from server.sample_layout import (CIVIC_CORES, CIVIC_CORRIDOR, CIVIC_FLOORS, CIVIC_POINTS, CIVIC_ROOM_NAMES,  # noqa: E402
                                  CIVIC_ROOMS, civic_bin_at)

WIDTH, HEIGHT = 1800, 920  # drawn over the 900 x 460 map area, so 2 image pixels per map pixel
FLOOR, HALL, WALL, CORE, CORE_LINE, LABEL = "#fcfdfb", "#edf1eb", "#c9d4cb", "#e3eadf", "#b2c0ad", "#4f5b54"
OUTSIDE, ROOF, ROOF_LINE, MUTED = "#f4f6f2", "#e9f0e4", "#cfdcc8", "#7b877f"
CORRIDOR_X = {point: x for point, x, *_ in CIVIC_CORRIDOR}
A_WING, LINK, B_WING = (1, 8, 44, 92), (44, 26, 56, 74), (56, 8, 99, 92)


def at(x, y):
    return x * WIDTH / 100, y * HEIGHT / 100


def box(draw, x0, y0, x1, y1, **style):
    draw.rectangle([*at(x0, y0), *at(x1, y1)], **style)


def text_at(draw, font, text, x, y, center=False):
    w = draw.textlength(text, font=font) * 100 / WIDTH
    draw.text(at(x - w / 2 if center else x, y), text, font=font, fill=LABEL)


def label_in(draw, font, text, area, avoid):
    # the corner of the room farthest from the markers drawn there (each marker has a name tag below it)
    x0, y0, x1, y1 = area
    w = draw.textlength(text, font=font) * 100 / WIDTH
    h = 36 * 100 / HEIGHT
    corners = [(x0 + 1.2, y0 + 2), (x1 - 1.2 - w, y0 + 2), (x0 + 1.2, y1 - 2 - h), (x1 - 1.2 - w, y1 - 2 - h)]
    spots = [(x, y + dy) for x, y in avoid for dy in (0, 8)]
    if spots:
        lx, ly = max(corners, key=lambda c: min((c[0] + w / 2 - x) ** 2 + ((c[1] + h / 2 - y) * 2) ** 2 for x, y in spots))
    else:
        lx, ly = (x0 + x1 - w) / 2, (y0 + y1 - h) / 2
    draw.text(at(lx, ly), text, font=font, fill=LABEL)


def hatch(draw, area, color):
    x0, y0, x1, y1 = area
    for k in range(-60, 110, 3):
        xa, xb = max(x0, x0 + k), min(x1, x0 + k + (y1 - y0) * 0.5)
        if xa < xb:
            draw.line([*at(xa, y0 + (xa - x0 - k) * 2), *at(xb, y0 + (xb - x0 - k) * 2)], fill=color, width=2)


def draw_floor(floor: int, font: ImageFont.FreeTypeFont, small: ImageFont.FreeTypeFont) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), OUTSIDE)
    draw = ImageDraw.Draw(image)
    has_b = floor <= 5
    wings = [A_WING, LINK] + ([B_WING] if has_b else [])
    for area in wings:
        box(draw, *area, fill=FLOOR)
    # corridor loops of each wing and the central link hall
    box(draw, 1, 29, 44, 35, fill=HALL)
    box(draw, 1, 65, 44, 71, fill=HALL)
    box(draw, 1, 29, 11, 71, fill=HALL)  # the west hall with its stairs
    box(draw, 37, 29, 44, 71, fill=HALL)
    box(draw, *LINK, fill=HALL)
    if has_b:
        box(draw, 56, 29, 99, 35, fill=HALL)
        box(draw, 56, 65, 99, 71, fill=HALL)
        box(draw, 56, 35, 63, 65, fill=HALL)
        box(draw, 85, 29, 99, 71, fill=HALL)
    elif floor == 6:
        box(draw, *B_WING, fill=ROOF)
        hatch(draw, B_WING, ROOF_LINE)
        text_at(draw, font, "B동 옥상정원 (5층 지붕)", 77.5, 47, center=True)
    else:
        text_at(draw, small, "B동은 5층까지", 77.5, 48, center=True)

    # rooms with a door onto their corridor point; room names keep clear of the markers
    marks = {}
    for room, spec in enumerate(CIVIC_ROOMS):
        marks[room] = [civic_bin_at(spec)]
    for f, room, _, (x, y), _ in CIVIC_POINTS:
        if f == floor:
            marks[room] = [(x, y)]
    for room, ((x0, y0, x1, y1), door, top, every_floor) in enumerate(CIVIC_ROOMS):
        if floor > top:
            continue
        box(draw, x0, y0, x1, y1, fill=FLOOR, outline=WALL, width=5)
        wall = y1 if y1 <= 30 else y0
        door_x = min(max(CORRIDOR_X[door], x0 + 3), x1 - 3)
        box(draw, door_x - 2.4, wall - 0.9, door_x + 2.4, wall + 0.9, fill=FLOOR)
        has_marker = every_floor or floor == 1 or any(f == floor and r == room for f, r, *_ in CIVIC_POINTS)
        label_in(draw, font, CIVIC_ROOM_NAMES[floor][room], (x0, y0, x1, y1), marks[room] if has_marker else [])

    # wing names above the building, the main entrance in the courtyard between the wings
    text_at(draw, small, "A동 · 행정동 (8층)", 1.5, 1.6)
    text_at(draw, small, "중앙 연결동", 50, 1.6, center=True)
    if has_b:
        text_at(draw, small, "B동 · 문화복지동 (5층)", 56.5, 1.6)
    if floor == 1:
        box(draw, 46, 73, 54, 75, fill=HALL)
        text_at(draw, small, "▲ 주출입구", 50, 78, center=True)

    for code, x, y, kind, _, _, _, top, closed in CIVIC_CORES:
        if floor > top:
            continue
        if kind == "stairs":
            box(draw, x - 2.4, y - 8, x + 2.4, y + 8, fill=CORE, outline=CORE_LINE, width=3)
            for step in range(1, 8):
                yy = y - 8 + step * 2
                box(draw, x - 2.4, yy, x + 2.4, yy, outline=CORE_LINE, width=2)
        else:
            box(draw, x - 2.2, y - 4, x + 2.2, y + 4, fill=CORE, outline=CORE_LINE, width=3)
            draw.line([*at(x - 2.2, y - 4), *at(x + 2.2, y + 4)], fill=CORE_LINE, width=3)
            draw.line([*at(x + 2.2, y - 4), *at(x - 2.2, y + 4)], fill=CORE_LINE, width=3)
            if floor in closed:  # out of service on this floor
                text_at(draw, small, "운영 중단", x, y + 4.8, center=True)
    for area in wings:
        box(draw, *area, outline=WALL, width=7)
    return image


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--font", default="C:/Windows/Fonts/malgun.ttf")
    args = parser.parse_args()
    font, small = ImageFont.truetype(args.font, 28), ImageFont.truetype(args.font, 24)
    out = ROOT / "server" / "samples"
    out.mkdir(parents=True, exist_ok=True)
    for floor in range(1, CIVIC_FLOORS + 1):
        path = out / f"civic-floor-{floor}.png"
        draw_floor(floor, font, small).save(path, optimize=True)
        print(path.relative_to(ROOT), path.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
