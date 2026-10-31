"""Draw the curved sample's floor plans into server/samples/round-floor-N.png.

The building is shaped like a running track, set in plan pixels so its curves stay round on screen.
The server copies these plans into the map folder when the demo is reset to it. Needs Pillow and a
Korean font. From the project root:
    python tools/make_round_floorplans.py [--font C:/Windows/Fonts/malgun.ttf]
"""
import argparse
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from server.sample_layout import (ROUND_CORES, ROUND_FLOORS, ROUND_INNER_U, ROUND_OUTER_U, ROUND_POINTS,  # noqa: E402
                                  ROUND_RADIALS, ROUND_RADII, ROUND_ROOM_NAMES, ROUND_ROOMS, round_bin_px, round_door,
                                  round_px)

SCALE = 2  # image pixels per plan pixel (the plan is 900 x 460)
WIDTH, HEIGHT = 900 * SCALE, 460 * SCALE
FLOOR, HALL, WALL, CORE, CORE_LINE, LABEL = "#fcfdfb", "#edf1eb", "#c9d4cb", "#e3eadf", "#b2c0ad", "#4f5b54"
OUTSIDE, VOID, VOID_LINE = "#f4f6f2", "#f1f4f0", "#d5ddd3"
R = ROUND_RADII


def img(p):
    return p[0] * SCALE, p[1] * SCALE


def band(u0, u1, r0, r1, step=0.01):
    """Polygon of a stretch of the track between two distances from its centre line."""
    n = max(2, int(abs(u1 - u0) / step))
    outer = [img(round_px(u0 + (u1 - u0) * i / n, r1)) for i in range(n + 1)]
    inner = [img(round_px(u1 - (u1 - u0) * i / n, r0)) for i in range(n + 1)]
    return outer + inner


def loop(radius):
    return [img(round_px(4 * i / 400, radius)) for i in range(400)]


def tangent(u, radius):
    (ax, ay), (bx, by) = round_px(u - 0.001, radius), round_px(u + 0.001, radius)
    length = math.hypot(bx - ax, by - ay)
    return (bx - ax) / length, (by - ay) / length


def gap(draw, u, radius, half=12):
    # a door: wall removed for `half` plan pixels on each side of the place
    (cx, cy), (tx, ty) = round_px(u, radius), tangent(u, radius)
    nx, ny = -ty, tx
    corners = [(cx + tx * half + nx * 5, cy + ty * half + ny * 5), (cx - tx * half + nx * 5, cy - ty * half + ny * 5),
               (cx - tx * half - nx * 5, cy - ty * half - ny * 5), (cx + tx * half - nx * 5, cy + ty * half - ny * 5)]
    draw.polygon([img(c) for c in corners], fill=FLOOR)


def room_label(draw, font, text, room, marker):
    """Beside the room's marker along the corridor, on the side away from its name tag below it."""
    band_name, u0, u1 = room
    r0, r1 = (R["outer_rooms"], R["wall"]) if band_name == "outer" else (R["middle_in"], R["middle_out"])
    mid_r = (r0 + r1) / 2
    w, h = draw.textlength(text, font=font) / SCALE, 26 / SCALE
    mx, my = marker
    best = None
    for sign in (1, -1):
        for step in range(1, 200):
            u = (u0 + u1) / 2 + sign * step * 0.002
            if not u0 + 0.01 < u < u1 - 0.01:
                break
            x, y = round_px(u, mid_r)
            # clear of the marker (radius 21) and of the name tag under it (to 52 below)
            if abs(x - mx) > 21 + 6 + w / 2 or y + h / 2 < my - 27 or y - h / 2 > my + 56:
                inside = all(u0 < uu < u1 for uu in (u - 0.01, u + 0.01))
                score = (inside, -(y > my + 18))
                if best is None or score > best[0]:
                    best = (score, x, y)
                break
    if best is None:  # no room beside the marker: above it, by the outer wall
        x, y = round_px((u0 + u1) / 2, r1 - 14)
    else:
        _, x, y = best
    draw.text(img((x - w / 2, y - h / 2)), text, font=font, fill=LABEL)


def draw_floor(floor: int, font: ImageFont.FreeTypeFont, small: ImageFont.FreeTypeFont) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), OUTSIDE)
    draw = ImageDraw.Draw(image)
    draw.polygon(loop(R["wall"]), fill=FLOOR)
    draw.polygon(loop(R["outer_corridor"] + 12), fill=HALL)
    draw.polygon(loop(R["outer_corridor"] - 12), fill=FLOOR)
    draw.polygon(loop(R["inner_corridor"] + 10), fill=HALL)
    draw.polygon(loop(R["inner_corridor"] - 10), fill=FLOOR)
    for u in ROUND_RADIALS:  # passages between the two curved corridors
        a, b = round_px(u, R["inner_corridor"]), round_px(u, R["outer_corridor"])
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        nx, ny = -(b[1] - a[1]) / length * 9, (b[0] - a[0]) / length * 9
        draw.polygon([img((a[0] + nx, a[1] + ny)), img((b[0] + nx, b[1] + ny)), img((b[0] - nx, b[1] - ny)), img((a[0] - nx, a[1] - ny))], fill=HALL)
    for u0, u1 in ((1.4, 1.6), (3.4, 3.6)):  # stair halls at the curved ends
        draw.polygon(band(u0, u1, R["outer_rooms"], R["wall"]), fill=HALL)
    for u0, u1 in ((0.5, 1), (2.5, 3)):  # lift lobbies
        draw.polygon(band(u0, u1, R["middle_in"], R["middle_out"]), fill=HALL)

    # the central hall: the lobby on the first floor, an open void above it
    hall = loop(R["hall"])
    if floor == 1:
        draw.polygon(hall, fill=FLOOR, outline=WALL, width=4)
        hall_label = "중앙 홀"
    else:
        layer = Image.new("RGB", (WIDTH, HEIGHT), VOID)  # diagonal hatching, pasted through the hall's shape
        layer_draw = ImageDraw.Draw(layer)
        for k in range(-HEIGHT, WIDTH, 22):
            layer_draw.line([(k, 0), (k + HEIGHT // 2, HEIGHT)], fill=VOID_LINE, width=2)
        mask = Image.new("L", (WIDTH, HEIGHT), 0)
        ImageDraw.Draw(mask).polygon(hall, fill=255)
        image.paste(layer, (0, 0), mask)
        draw = ImageDraw.Draw(image)
        draw.polygon(hall, outline=CORE_LINE, width=4)
        hall_label = "중앙 보이드"
    w = draw.textlength(hall_label, font=font)
    draw.text((450 * SCALE - w / 2, 230 * SCALE - 14), hall_label, font=font, fill=LABEL)

    # rooms with a door onto their corridor
    marks = {room: [round_bin_px(spec)] for room, spec in enumerate(ROUND_ROOMS)}
    for f, room, _, u, radius, _ in ROUND_POINTS:
        if f == floor:
            marks[room] = [round_px(u, radius)]
    for room, spec in enumerate(ROUND_ROOMS):
        band_name, u0, u1 = spec
        r0, r1 = (R["outer_rooms"], R["wall"]) if band_name == "outer" else (R["middle_in"], R["middle_out"])
        draw.polygon(band(u0, u1, r0, r1), fill=FLOOR, outline=WALL, width=5)
        door = round_door(spec)
        u_door = (ROUND_OUTER_U if door.startswith("OR") else ROUND_INNER_U)[int(door[2:])]
        gap(draw, min(max(u_door, u0 + 0.04), u1 - 0.04), r0)
    for room, spec in enumerate(ROUND_ROOMS):
        room_label(draw, small if spec[0] == "middle" else font, ROUND_ROOM_NAMES[floor][room], spec, marks[room][0])
    if floor == 1:
        gap(draw, 2.5, R["wall"], half=22)  # the main entrance on the south side

    for code, u, radius, kind, _ in ROUND_CORES:
        x, y = round_px(u, radius)
        if kind == "stairs":
            draw.rectangle([img((x - 22, y - 34)), img((x + 22, y + 34))], fill=CORE, outline=CORE_LINE, width=3)
            for step in range(1, 9):
                yy = y - 34 + step * 68 / 9
                draw.line([img((x - 22, yy)), img((x + 22, yy))], fill=CORE_LINE, width=2)
        else:
            draw.rectangle([img((x - 18, y - 12)), img((x + 18, y + 12))], fill=CORE, outline=CORE_LINE, width=3)
            draw.line([img((x - 18, y - 12)), img((x + 18, y + 12))], fill=CORE_LINE, width=3)
            draw.line([img((x + 18, y - 12)), img((x - 18, y + 12))], fill=CORE_LINE, width=3)
    draw.polygon(loop(R["wall"]), outline=WALL, width=7)
    return image


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--font", default="C:/Windows/Fonts/malgun.ttf")
    args = parser.parse_args()
    font, small = ImageFont.truetype(args.font, 26), ImageFont.truetype(args.font, 22)
    out = ROOT / "server" / "samples"
    out.mkdir(parents=True, exist_ok=True)
    for floor in range(1, ROUND_FLOORS + 1):
        path = out / f"round-floor-{floor}.png"
        draw_floor(floor, font, small).save(path, optimize=True)
        print(path.relative_to(ROOT), path.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
