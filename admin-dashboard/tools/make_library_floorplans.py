"""Draw the library sample building's floor plans into server/samples/library-floor-N.png.

The server copies these into the map folder when the demo is reset to the library, where the dashboard
shows them like an uploaded floor plan. Needs Pillow and a Korean font. From the project root:
    python tools/make_library_floorplans.py [--font C:/Windows/Fonts/malgun.ttf]
"""
import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from server.sample_layout import (LIBRARY_ATRIUM, LIBRARY_CORES, LIBRARY_FLOORS, LIBRARY_POINTS,  # noqa: E402
                                  LIBRARY_RING, LIBRARY_ROOM_NAMES, LIBRARY_ROOMS)

WIDTH, HEIGHT = 1800, 920  # drawn over the 900 x 460 map area, so 2 image pixels per map pixel
FLOOR, HALL, WALL, CORE, CORE_LINE, LABEL = "#fcfdfb", "#edf1eb", "#c9d4cb", "#e3eadf", "#b2c0ad", "#4f5b54"
VOID, VOID_LINE = "#f1f4f0", "#d5ddd3"
RING_X = {point: x for point, x, _ in LIBRARY_RING}
ENTRANCE_X = 44  # map x of the main entrance, in the lobby's north wall


def at(x, y):
    return x * WIDTH / 100, y * HEIGHT / 100


def box(draw, x0, y0, x1, y1, **style):
    draw.rectangle([*at(x0, y0), *at(x1, y1)], **style)


def label_in(draw, font, text, area, avoid):
    # the corner of the area farthest from the markers drawn there (each marker has a name tag below it)
    x0, y0, x1, y1 = area
    w = draw.textlength(text, font=font) * 100 / WIDTH
    h = 40 * 100 / HEIGHT
    corners = [(x0 + 1.6, y0 + 2.4), (x1 - 1.6 - w, y0 + 2.4), (x0 + 1.6, y1 - 2.4 - h), (x1 - 1.6 - w, y1 - 2.4 - h)]
    spots = [(x, y + dy) for x, y in avoid for dy in (0, 8)]
    if spots:
        lx, ly = max(corners, key=lambda c: min((c[0] + w / 2 - x) ** 2 + ((c[1] + h / 2 - y) * 2) ** 2 for x, y in spots))
    else:
        lx, ly = (x0 + x1 - w) / 2, (y0 + y1 - h) / 2
    draw.text(at(lx, ly), text, font=font, fill=LABEL)


def draw_floor(floor: int, font: ImageFont.FreeTypeFont, small: ImageFont.FreeTypeFont) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), FLOOR)
    draw = ImageDraw.Draw(image)
    # the corridor ring: north and south halls, joined by the west and east halls
    box(draw, 0, 21, 100, 33, fill=HALL)
    box(draw, 0, 67, 100, 79, fill=HALL)
    box(draw, 0, 21, 12.5, 79, fill=HALL)  # the west hall with its stairs
    box(draw, 87.5, 21, 100, 79, fill=HALL)

    # the atrium: the lobby on the first floor, an open void with a railing above it
    ax0, ay0, ax1, ay1 = LIBRARY_ATRIUM
    if floor == 1:
        box(draw, ax0, ay0, ax1, ay1, fill=FLOOR, outline=WALL, width=3)
        atrium_label = "로비 아트리움"
    else:
        box(draw, ax0, ay0, ax1, ay1, fill=VOID)
        for k in range(-30, 80, 3):  # diagonal hatching inside the void
            x_start, x_end = ax0 + k, ax0 + k + (ay1 - ay0) * 0.5
            xa, ya, xb, yb = max(ax0, x_start), ay0 + (max(ax0, x_start) - x_start) * 2, min(ax1, x_end), ay0 + (min(ax1, x_end) - x_start) * 2
            if xa < xb:
                draw.line([*at(xa, ya), *at(xb, yb)], fill=VOID_LINE, width=2)
        box(draw, ax0, ay0, ax1, ay1, outline=CORE_LINE, width=4)
        box(draw, ax0 + 0.6, ay0 + 1.2, ax1 - 0.6, ay1 - 1.2, outline=VOID_LINE, width=2)
        atrium_label = "아트리움 (개방)"
    text_w = draw.textlength(atrium_label, font=font) * 100 / WIDTH
    draw.text(at((ax0 + ax1 - text_w) / 2, 46), atrium_label, font=font, fill=LABEL)

    # small rooms between the side halls and the atrium
    for area in ((13.5, 38, 21, 62), (79, 38, 86.5, 62)):
        box(draw, *area, fill=FLOOR, outline=WALL, width=4)
        label_in(draw, small, "화장실", area, [])

    # rooms on the north and south sides, each with a door onto its corridor point
    points = {(f, room): (x, y) for f, room, _, (x, y), _ in LIBRARY_POINTS}
    for room, ((x0, y0, x1, y1), door, (bx, by)) in enumerate(LIBRARY_ROOMS):
        box(draw, x0, y0, x1, y1, fill=FLOOR, outline=WALL, width=5)
        wall = y1 if y1 <= 50 else y0
        door_x = min(max(RING_X[door], x0 + 3.2), x1 - 3.2)
        box(draw, door_x - 2.6, wall - 0.9, door_x + 2.6, wall + 0.9, fill=FLOOR)
        avoid = [points.get((floor, room), (bx, by))]
        if floor == 1 and room == 1:
            avoid.append((ENTRANCE_X, 0))
        label_in(draw, font, LIBRARY_ROOM_NAMES[floor][room], (x0, y0, x1, y1), avoid)
    if floor == 1:  # the main entrance in the lobby's outer wall
        box(draw, ENTRANCE_X - 4, -1, ENTRANCE_X + 4, 1.2, fill=FLOOR)
        text_w = draw.textlength("주출입구 ▼", font=small) * 100 / WIDTH
        draw.text(at(ENTRANCE_X - text_w / 2, 2), "주출입구 ▼", font=small, fill=LABEL)

    # stairs to the west and east, glass lifts on the atrium edges
    for _, x, y, kind, *_ in LIBRARY_CORES:
        if kind == "stairs":
            box(draw, x - 3.2, y - 10, x + 3.2, y + 10, fill=CORE, outline=CORE_LINE, width=3)
            for step in range(1, 9):
                yy = y - 10 + step * 20 / 9
                box(draw, x - 3.2, yy, x + 3.2, yy, outline=CORE_LINE, width=2)
        else:
            box(draw, x - 2.6, y - 4.5, x + 2.6, y + 4.5, fill=CORE, outline=CORE_LINE, width=3)
            draw.line([*at(x - 2.6, y - 4.5), *at(x + 2.6, y + 4.5)], fill=CORE_LINE, width=3)
            draw.line([*at(x + 2.6, y - 4.5), *at(x - 2.6, y + 4.5)], fill=CORE_LINE, width=3)
    box(draw, 0, 0, 100, 100, outline=WALL, width=8)
    return image


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--font", default="C:/Windows/Fonts/malgun.ttf")
    args = parser.parse_args()
    font, small = ImageFont.truetype(args.font, 34), ImageFont.truetype(args.font, 28)
    out = ROOT / "server" / "samples"
    out.mkdir(parents=True, exist_ok=True)
    for floor in range(1, LIBRARY_FLOORS + 1):
        path = out / f"library-floor-{floor}.png"
        draw_floor(floor, font, small).save(path, optimize=True)
        print(path.relative_to(ROOT), path.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
