"""Draw the large sample building's floor plans into server/samples/large-floor-N.png.

The server copies these into the map folder when the demo is reset to the large building, where the
dashboard shows them like an uploaded floor plan. Needs Pillow and a Korean font. From the project root:
    python tools/make_large_floorplans.py [--font C:/Windows/Fonts/malgun.ttf]
"""
import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from server.sample_layout import (LARGE_BINS, LARGE_CORES, LARGE_CORRIDOR_X, LARGE_CORRIDORS,  # noqa: E402
                                  LARGE_FLOORS, LARGE_OFFICE, LARGE_ROOMS, large_room_label)

WIDTH, HEIGHT = 1800, 920  # drawn over the 900 x 460 map area, so 2 image pixels per map pixel
FLOOR, HALL, WALL, CORE, CORE_LINE, LABEL = "#fcfdfb", "#edf1eb", "#c9d4cb", "#e3eadf", "#b2c0ad", "#4f5b54"


def at(x, y):
    return x * WIDTH / 100, y * HEIGHT / 100


def box(draw, x0, y0, x1, y1, **style):
    draw.rectangle([*at(x0, y0), *at(x1, y1)], **style)


def draw_floor(floor: int, font: ImageFont.FreeTypeFont) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), FLOOR)
    draw = ImageDraw.Draw(image)
    for _, y, _ in LARGE_CORRIDORS:
        box(draw, 0, y - 5, 100, y + 5, fill=HALL)
    for x0, x1 in [(0, 12), (46, 54), (88, 100)]:  # stair and lift halls between the corridors
        box(draw, x0, 35, x1, 65, fill=HALL)
    for (x0, y0, x1, y1), *_ in LARGE_ROOMS:
        box(draw, x0, y0, x1, y1, fill=FLOOR, outline=WALL, width=5)

    # Doors face the corridor of each stop's access node; labels sit in the room corner farthest from the stops.
    stops = [(x, y, access, room) for x, y, access, room in LARGE_BINS]
    if floor == 1:
        room = next(i for i, ((x0, y0, x1, y1), *_) in enumerate(LARGE_ROOMS) if x0 <= LARGE_OFFICE[0] <= x1 and y0 <= LARGE_OFFICE[1] <= y1)
        stops.append((LARGE_OFFICE[0], LARGE_OFFICE[1], LARGE_OFFICE[2], room))
    corridor_y = {side: y for side, y, _ in LARGE_CORRIDORS}
    corridor_x = {f"{side}{i}": x for side, _, _ in LARGE_CORRIDORS for i, x in enumerate(LARGE_CORRIDOR_X)}
    for x, y, access, room in stops:
        (x0, y0, x1, y1) = LARGE_ROOMS[room][0]
        wall = y1 if corridor_y[access[0]] > y1 else y0
        door_x = corridor_x[access]
        box(draw, door_x - 2.6, wall - 0.9, door_x + 2.6, wall + 0.9, fill=FLOOR)
    for index, ((x0, y0, x1, y1), *_) in enumerate(LARGE_ROOMS):
        label = large_room_label(LARGE_ROOMS[index], floor)
        # each stop is drawn as a marker with its name tag just below it
        inside = [(x, y + dy) for x, y, _, room in stops if room == index for dy in (0, 8)]
        w = draw.textlength(label, font=font) * 100 / WIDTH
        h = 40 * 100 / HEIGHT
        corners = [(x0 + 1.6, y0 + 2.4), (x1 - 1.6 - w, y0 + 2.4), (x0 + 1.6, y1 - 2.4 - h), (x1 - 1.6 - w, y1 - 2.4 - h)]
        if inside:
            lx, ly = max(corners, key=lambda c: min(((c[0] + w / 2 - x) ** 2 + ((c[1] + h / 2 - y) * 2) ** 2) for x, y in inside))
        else:
            lx, ly = (x0 + x1 - w) / 2, (y0 + y1 - h) / 2
        draw.text(at(lx, ly), label, font=font, fill=LABEL)

    for _, x, kind, _, _ in LARGE_CORES:
        if kind == "stairs":
            box(draw, x - 4.2, 39, x + 4.2, 57, fill=CORE, outline=CORE_LINE, width=3)
            for step in range(1, 8):
                box(draw, x - 4.2, 39 + step * 2.25, x + 4.2, 39 + step * 2.25, outline=CORE_LINE, width=2)
        else:
            box(draw, x - 3.4, 40, x + 3.4, 56, fill=CORE, outline=CORE_LINE, width=3)
            draw.line([*at(x - 3.4, 40), *at(x + 3.4, 56)], fill=CORE_LINE, width=3)
            draw.line([*at(x + 3.4, 40), *at(x - 3.4, 56)], fill=CORE_LINE, width=3)
    box(draw, 0, 0, 100, 100, outline=WALL, width=8)
    return image


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--font", default="C:/Windows/Fonts/malgun.ttf")
    args = parser.parse_args()
    font = ImageFont.truetype(args.font, 34)
    out = ROOT / "server" / "samples"
    out.mkdir(parents=True, exist_ok=True)
    for floor in range(1, LARGE_FLOORS + 1):
        path = out / f"large-floor-{floor}.png"
        draw_floor(floor, font).save(path, optimize=True)
        print(path.relative_to(ROOT), path.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
