"""Reloop competition MVP: local accounts, durable demo data and indoor routing."""
from __future__ import annotations

import base64
import copy
import hashlib
import heapq
import hmac
import json
import math
import os
import random
import secrets
import sqlite3
import threading
import time
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any, Literal, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .sample_layout import (CIVIC_CORES, CIVIC_CORRIDOR, CIVIC_FILL_PATTERN, CIVIC_FLOORS, CIVIC_LINKS,
                            CIVIC_POINTS, CIVIC_ROOM_NAMES, CIVIC_ROOMS, civic_bin_at, LARGE_BINS, ROUND_CENTRES, ROUND_CORES,
                            ROUND_FILL_PATTERN, ROUND_FLOORS, ROUND_INNER_U, ROUND_M_PER_PX, ROUND_OUTER_U,
                            ROUND_POINTS, ROUND_RADIALS, ROUND_RADII, ROUND_ROOM_NAMES, ROUND_ROOMS, round_at, round_bin_at,
                            round_door, round_nearest, round_px, LARGE_CORES, LARGE_CORRIDOR_X, LARGE_CORRIDORS, LARGE_DEPOT, LARGE_FILLS,
                            LARGE_FLOORS, LARGE_OFFICE, LARGE_ROOMS, LIBRARY_CORES, LIBRARY_FLOORS, LIBRARY_POINTS,
                            LIBRARY_RING, LIBRARY_ROOM_NAMES, LIBRARY_ROOMS, large_room_label, library_fill)

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("RELOOP_DATA_DIR", str(ROOT / "data")))
DB_PATH = DATA_DIR / "reloop.sqlite3"
MAP_DIR = DATA_DIR / "maps"
LOCK = threading.RLock()
COOKIE = "reloop_session"
DEMO_EMAIL = "demo@reloop.local"
DEMO_PASSWORD = "Demo1234!"
ROUTE_COLORS = ["#3976db", "#9266ce", "#1d9caa", "#bf648f", "#6073a3", "#9b7946"]
# Route presets. fastest: the earliest time by which every collection is done; lean: the fewest
# workers, then the least total working time. Both keep within the cart capacity and the per-person
# working-time cap, and end each trip at the drop-off point (분리수거장, or the office if none is set).
RouteMode = Literal["fastest", "lean"]
# Travel-time defaults are assumptions to be replaced by on-site measurements.
ROUTE_DEFAULTS = {"route_mode": "fastest", "stairs_up_seconds": 20, "stairs_down_seconds": 14,
                  "elevator_wait_seconds": 40, "elevator_floor_seconds": 4, "use_cart": False,
                  "cart_capacity": 4, "depot_node": "", "unload_seconds": 60, "max_work_minutes": 20,
                  "compartment_seconds": 15}
# One location holds four compartments, as the device sorts them: 캔, PET, 유리, 일반. Each has its own
# sensor value; the location's fill (and so its status) is its fullest compartment.
COMPARTMENTS = ("CAN", "PET", "GLASS", "OTHER")
Compartment = Literal["CAN", "PET", "GLASS", "OTHER"]
Percent = Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]
OLD_CATEGORY = {"PET": "PET", "캔": "CAN", "유리": "GLASS", "일반": "OTHER", "혼합": "OTHER"}
CART_SPEED_RATIO = 0.85  # walking speed with a loaded cart
# The map draws its 0-100 units on a 900 x 460 pixel plan, so a unit down is shorter than a unit across.
# Distances are measured as drawn; meters_per_unit is the scale across.
MAP_Y_SCALE = 460 / 900


def map_distance(a: dict, b: dict, meters_per_unit: float) -> float:
    return math.hypot(a["x"] - b["x"], (a["y"] - b["y"]) * MAP_Y_SCALE) * meters_per_unit
CAR = "~car"  # suffix of the car twin of each lift node
# Search effort per preset: up to SEARCH_RESTARTS runs of base rounds plus rounds per stop, within a
# time budget in seconds.
SEARCH_ROUNDS, SEARCH_ROUNDS_PER_STOP, SEARCH_SECONDS, SEARCH_RESTARTS = 600, 20, 0.6, 4
SEARCH_HEAT = 0.01  # starting annealing temperature as a share of the first plan's time


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_time(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError("timezone required")
        return result.astimezone(timezone.utc)
    except (ValueError, TypeError):
        raise HTTPException(422, "측정 시각은 시간대가 포함된 ISO 8601 형식이어야 합니다.")


@contextmanager
def database():
    connection = sqlite3.connect(DB_PATH, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def password_hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 310_000).hex()


def set_fills(bin: dict, fills: dict) -> dict:
    """Update some compartments (None = no value yet); the location's fill is its fullest compartment."""
    current = dict.fromkeys(COMPARTMENTS) | (bin.get("compartments") or {})
    current.update({c: None if v is None else round(float(v), 1) for c, v in fills.items()})
    bin["compartments"] = {c: current[c] for c in COMPARTMENTS}
    known = [v for v in bin["compartments"].values() if v is not None]
    bin["fill"] = max(known) if known else None
    return bin


def demo_fills(level: float, index: int) -> dict:
    """Demo values: the fullest compartment keeps the given level, so the location's status matches it;
    the others trail behind, and which compartment is fullest rotates from location to location."""
    drops = (0, 12, 35, 55)
    return {c: max(3.0, level - drops[(k - index) % 4]) for k, c in enumerate(COMPARTMENTS)}


def sample_fills(level, index: int) -> dict:
    # a real device has no values until it reports
    return set_fills({}, dict.fromkeys(COMPARTMENTS) if level is None else demo_fills(level, index))


def current_fills(bin: dict, config: dict, at: datetime | None = None) -> dict:
    """Operational values only. Keep raw readings in storage, but never refresh one compartment
    with another's timestamp. Older single-timestamp workspaces use their original measurement time."""
    values = dict.fromkeys(COMPARTMENTS) | (bin.get("compartments") or {})
    if bin["reading_source"] != "actual":
        return values
    cutoff = (at or datetime.now(timezone.utc)) - timedelta(minutes=config["stale_minutes"])
    times = bin.get("compartment_measured_at")
    for compartment, value in values.items():
        stamp = times.get(compartment) if times is not None else bin.get("measured_at")
        if value is not None and (not stamp or parse_time(stamp) < cutoff):
            values[compartment] = None
    return values


def to_empty(bin: dict, config: dict, at: datetime | None = None) -> dict:
    """Compartments emptied on a visit: every one at the warning level or above (all of them if none is)."""
    known = {c: v for c, v in current_fills(bin, config, at).items() if v is not None}
    return {c: v for c, v in known.items() if v >= config["warning_threshold"]} or known


def new_workspace() -> dict:
    nodes, edges, bins = [], [], []
    levels = [(None, 94, 43, 84), (97, 65, 88, 35), (76, 92, 58, 81)]
    names = ["서쪽 복도", "라운지 앞", "강의실 앞", "동쪽 계단"]
    stamp = now()
    for floor in range(1, 4):
        for index, x in enumerate([10, 20, 40, 62, 82, 92]):
            node_id = f"F{floor}-N{index}"
            nodes.append({"id": node_id, "floor": floor, "x": x, "y": 50,
                          "kind": "stairs" if index == 5 else "corridor",
                          "label": "동쪽 계단" if index == 5 else f"복도 {index + 1}"})
            if index:
                edges.append({"id": f"E{floor}-{index}", "from": f"F{floor}-N{index-1}",
                              "to": node_id, "distance_m": None})
        if floor > 1:
            edges.append({"id": f"STAIR-{floor}", "from": f"F{floor-1}-N5",
                          "to": f"F{floor}-N5", "distance_m": 12.0})
        for index, x in enumerate([20, 40, 62, 82]):
            number = (floor - 1) * 4 + index + 1
            bins.append({"id": f"B-{number:03}", "name": names[index], "floor": floor,
                         "x": x, "y": 29 if index % 2 == 0 else 72,
                         "access_node": f"F{floor}-N{index+1}",
                         **sample_fills(None if number == 1 else levels[floor-1][index], number),
                         "device_type": "real" if number == 1 else "demo",
                         "reading_source": "unconnected" if number == 1 else "demo",
                         "measured_at": None if number == 1 else stamp,
                         "received_at": None if number == 1 else stamp,
                         "awaiting_confirmation": False})
    return {
        "building": {"name": "인하대학교 · 미래관", "floors": 3,
                     "total_staff": 3, "available_staff": 2, "include_orange": False, **ROUTE_DEFAULTS,
                     "office_floor": 1, "office_x": 10, "office_y": 78,
                     "office_access_node": "F1-N0", "meters_per_unit": 0.6,
                     "speed_mps": 1.0, "service_seconds": 45,
                     "warning_threshold": 80, "critical_threshold": 90,
                     "stale_minutes": 5},
        "bins": bins, "graph": {"nodes": nodes + [
            {"id": "F1-OF1", "floor": 1, "x": 10, "y": 78, "kind": "office", "label": "관리자실"},
            {"id": "F1-DP1", "floor": 1, "x": 90, "y": 88, "kind": "depot", "label": "분리수거장"}],
            "edges": edges + [{"id": "E-F1-N0-F1-OF1", "from": "F1-N0", "to": "F1-OF1", "distance_m": None},
                              {"id": "E-F1-N4-F1-DP1", "from": "F1-N4", "to": "F1-DP1", "distance_m": None}]},
        "graph_version": 2, "map_images": {}, "logs": [], "readings": [], "last_plan": None,
        "device_key_hint": None, "revision": 1, "updated_at": stamp,
    }


# Floor plans drawn by tools/make_large_floorplans.py for the large sample building.
SAMPLE_DIR = ROOT / "server" / "samples"


def large_workspace() -> dict:
    state = new_workspace()
    nodes, edges, bins = [], [], []
    stamp = state["updated_at"]
    for floor in range(1, LARGE_FLOORS + 1):
        for side, y, name in LARGE_CORRIDORS:
            for index, x in enumerate(LARGE_CORRIDOR_X):
                nodes.append({"id": f"F{floor}-{side}{index}", "floor": floor, "x": x, "y": y,
                              "kind": "corridor", "label": f"{name} 복도 {index + 1}"})
                if index:
                    edges.append({"id": f"E{floor}-{side}{index}", "from": f"F{floor}-{side}{index-1}",
                                  "to": f"F{floor}-{side}{index}", "distance_m": None})
        for core, x, kind, label, rise in LARGE_CORES:
            node_id = f"F{floor}-{core}"
            index = LARGE_CORRIDOR_X.index(x)
            nodes.append({"id": node_id, "floor": floor, "x": x, "y": 50, "kind": kind, "label": label})
            edges += [{"id": f"E{floor}-{core}-N", "from": f"F{floor}-N{index}", "to": node_id, "distance_m": None},
                      {"id": f"E{floor}-{core}-S", "from": node_id, "to": f"F{floor}-S{index}", "distance_m": None}]
            if floor > 1:
                edges.append({"id": f"{core}-{floor}", "from": f"F{floor-1}-{core}", "to": node_id, "distance_m": rise})
        for index, (x, y, access, room) in enumerate(LARGE_BINS):
            number = (floor - 1) * len(LARGE_BINS) + index + 1
            bins.append({"id": f"B-{number:03}", "name": f"{large_room_label(LARGE_ROOMS[room], floor)} 앞",
                         "floor": floor, "x": x, "y": y, "access_node": f"F{floor}-{access}",
                         **sample_fills(None if number == 1 else LARGE_FILLS[floor-1][index], number),
                         "device_type": "real" if number == 1 else "demo",
                         "reading_source": "unconnected" if number == 1 else "demo",
                         "measured_at": None if number == 1 else stamp,
                         "received_at": None if number == 1 else stamp, "awaiting_confirmation": False})
    for kind, (x, y, access), label in (("office", LARGE_OFFICE, "관리자실"), ("depot", LARGE_DEPOT, "분리수거장")):
        node_id = f"F1-{'OF' if kind == 'office' else 'DP'}1"
        nodes.append({"id": node_id, "floor": 1, "x": x, "y": y, "kind": kind, "label": label})
        edges.append({"id": f"E-F1-{access}-{node_id}", "from": f"F1-{access}", "to": node_id, "distance_m": None})
    office_x, office_y, office_access = LARGE_OFFICE
    state["building"].update(name="예시 캠퍼스 · 종합관", floors=LARGE_FLOORS, total_staff=5, available_staff=3,
                             office_x=office_x, office_y=office_y, office_access_node=f"F1-{office_access}",
                             meters_per_unit=0.8)
    state.update(bins=bins, graph={"nodes": nodes, "edges": edges})
    return state


def library_workspace() -> dict:
    state = new_workspace()
    nodes, edges, bins = [], [], []
    stamp = state["updated_at"]
    ring = [point for point, _, _ in LIBRARY_RING]
    taken = {(floor, room) for floor, room, *_ in LIBRARY_POINTS}
    for floor in range(1, LIBRARY_FLOORS + 1):
        for index, (point, x, y) in enumerate(LIBRARY_RING):
            side = {"N": "북쪽 복도", "S": "남쪽 복도", "W": "서쪽 복도", "E": "동쪽 복도"}[point[0]]
            nodes.append({"id": f"F{floor}-{point}", "floor": floor, "x": x, "y": y, "kind": "corridor",
                          "label": f"{side} {int(point[1:]) + 1}" if point[0] in "NS" else side})
            after = ring[(index + 1) % len(ring)]
            edges.append({"id": f"E{floor}-{point}-{after}", "from": f"F{floor}-{point}", "to": f"F{floor}-{after}", "distance_m": None})
        for code, x, y, kind, label, door, rise in LIBRARY_CORES:
            node_id = f"F{floor}-{code}"
            nodes.append({"id": node_id, "floor": floor, "x": x, "y": y, "kind": kind, "label": label})
            edges.append({"id": f"E-F{floor}-{door}-{node_id}", "from": f"F{floor}-{door}", "to": node_id, "distance_m": None})
            if floor > 1:
                edges.append({"id": f"V-F{floor-1}-{code}-{node_id}", "from": f"F{floor-1}-{code}", "to": node_id, "distance_m": rise})
        for room, (_, door, (x, y)) in enumerate(LIBRARY_ROOMS):
            if (floor, room) in taken:
                continue
            number = len(bins) + 1
            bins.append({"id": f"B-{number:03}", "name": f"{LIBRARY_ROOM_NAMES[floor][room]} 앞",
                         "floor": floor, "x": x, "y": y, "access_node": f"F{floor}-{door}",
                         **sample_fills(None if number == 1 else library_fill(floor, room), number),
                         "device_type": "real" if number == 1 else "demo",
                         "reading_source": "unconnected" if number == 1 else "demo",
                         "measured_at": None if number == 1 else stamp,
                         "received_at": None if number == 1 else stamp, "awaiting_confirmation": False})
    counts = {"office": 0, "depot": 0}
    for floor, room, kind, (x, y), label in LIBRARY_POINTS:
        counts[kind] += 1
        node_id = f"F{floor}-{'OF' if kind == 'office' else 'DP'}{counts[kind]}"
        door = f"F{floor}-{LIBRARY_ROOMS[room][1]}"
        nodes.append({"id": node_id, "floor": floor, "x": x, "y": y, "kind": kind, "label": label})
        edges.append({"id": f"E-{door}-{node_id}", "from": door, "to": node_id, "distance_m": None})
    state["building"].update(name="예시 · 시립 중앙도서관", floors=LIBRARY_FLOORS, total_staff=6, available_staff=4,
                             meters_per_unit=1.0)
    state.update(bins=bins, graph={"nodes": nodes, "edges": edges})
    return state


def civic_workspace() -> dict:
    state = new_workspace()
    nodes, edges, bins = [], [], []
    stamp = state["updated_at"]
    taken = {(floor, room) for floor, room, *_ in CIVIC_POINTS}
    for floor in range(1, CIVIC_FLOORS + 1):
        here = {point for point, *_, top in CIVIC_CORRIDOR if floor <= top}
        for point, x, y, label, top in CIVIC_CORRIDOR:
            if point in here:
                nodes.append({"id": f"F{floor}-{point}", "floor": floor, "x": x, "y": y, "kind": "corridor", "label": label})
        for a, b in CIVIC_LINKS:
            if a in here and b in here:
                edges.append({"id": f"E{floor}-{a}-{b}", "from": f"F{floor}-{a}", "to": f"F{floor}-{b}", "distance_m": None})
        for room, (rect, door, top, every_floor) in enumerate(CIVIC_ROOMS):
            if floor > top or (floor, room) in taken or not (every_floor or floor == 1):
                continue
            number = len(bins) + 1
            x, y = civic_bin_at(CIVIC_ROOMS[room])
            bins.append({"id": f"B-{number:03}", "name": f"{CIVIC_ROOM_NAMES[floor][room]} 앞",
                         "floor": floor, "x": x, "y": y, "access_node": f"F{floor}-{door}",
                         **sample_fills(None if number == 1 else CIVIC_FILL_PATTERN[number % len(CIVIC_FILL_PATTERN)], number),
                         "device_type": "real" if number == 1 else "demo",
                         "reading_source": "unconnected" if number == 1 else "demo",
                         "measured_at": None if number == 1 else stamp,
                         "received_at": None if number == 1 else stamp, "awaiting_confirmation": False})
    for code, x, y, kind, label, door, rise, top, closed in CIVIC_CORES:
        # open stops are linked floor to floor; an out-of-service stop is skipped
        below = None
        for floor in range(1, top + 1):
            node_id = f"F{floor}-{code}"
            nodes.append({"id": node_id, "floor": floor, "x": x, "y": y, "kind": kind, "label": label, "closed": floor in closed})
            edges.append({"id": f"E-F{floor}-{door}-{node_id}", "from": f"F{floor}-{door}", "to": node_id, "distance_m": None})
            if floor in closed:
                continue
            if below:
                edges.append({"id": f"V-{below}-{node_id}", "from": below, "to": node_id,
                              "distance_m": rise * (floor - int(below[1:below.index('-')]))})
            below = node_id
    counts = {"office": 0, "depot": 0}
    for floor, room, kind, (x, y), label in CIVIC_POINTS:
        counts[kind] += 1
        node_id = f"F{floor}-{'OF' if kind == 'office' else 'DP'}{counts[kind]}"
        door = f"F{floor}-{CIVIC_ROOMS[room][1]}"
        nodes.append({"id": node_id, "floor": floor, "x": x, "y": y, "kind": kind, "label": label})
        edges.append({"id": f"E-{door}-{node_id}", "from": door, "to": node_id, "distance_m": None})
    state["building"].update(name="예시 · 시민 복합청사", floors=CIVIC_FLOORS, total_staff=8, available_staff=5,
                             meters_per_unit=1.2)
    state.update(bins=bins, graph={"nodes": nodes, "edges": edges})
    return state


def round_workspace() -> dict:
    state = new_workspace()
    nodes, edges, bins = [], [], []
    stamp = state["updated_at"]
    taken = {(floor, room) for floor, room, *_ in ROUND_POINTS}
    places = {}  # node id -> plan pixels, to measure the links on the curved geometry

    def link(edge_id, a, b):
        (ax, ay), (bx, by) = places[a], places[b]
        edges.append({"id": edge_id, "from": a, "to": b, "distance_m": max(0.1, round(math.hypot(ax - bx, ay - by) * ROUND_M_PER_PX, 1))})

    def point(node_id, floor, u, radius, kind, label):
        x, y = round_at(u, radius)
        places[node_id] = round_px(u, radius)
        nodes.append({"id": node_id, "floor": floor, "x": x, "y": y, "kind": kind, "label": label})

    for floor in range(1, ROUND_FLOORS + 1):
        # the curved corridors: closely spaced points joined in a ring
        for ring, spots, radius, name in (("OR", ROUND_OUTER_U, ROUND_RADII["outer_corridor"], "바깥 곡선 복도"),
                                          ("IR", ROUND_INNER_U, ROUND_RADII["inner_corridor"], "안쪽 곡선 복도")):
            for k, u in enumerate(spots):
                point(f"F{floor}-{ring}{k}", floor, u, radius, "corridor", f"{name} {k + 1}")
            for k in range(len(spots)):
                link(f"E{floor}-{ring}{k}", f"F{floor}-{ring}{k}", f"F{floor}-{ring}{(k + 1) % len(spots)}")
        for u in ROUND_RADIALS:
            link(f"E{floor}-RAD{ROUND_OUTER_U.index(u)}", f"F{floor}-IR{ROUND_INNER_U.index(u)}", f"F{floor}-OR{ROUND_OUTER_U.index(u)}")
        for code, u, radius, kind, label in ROUND_CORES:
            node_id = f"F{floor}-{code}"
            point(node_id, floor, u, radius, kind, label)
            link(f"E-F{floor}-{code}", f"F{floor}-OR{round_nearest(ROUND_OUTER_U, u)}", node_id)
            if floor > 1:
                edges.append({"id": f"V-F{floor-1}-{code}-{node_id}", "from": f"F{floor-1}-{code}", "to": node_id,
                              "distance_m": 15.0 if kind == "elevator" else 12.0})
        for room, spec in enumerate(ROUND_ROOMS):
            if (floor, room) in taken:
                continue
            number = len(bins) + 1
            x, y = round_bin_at(spec)
            bins.append({"id": f"B-{number:03}", "name": f"{ROUND_ROOM_NAMES[floor][room]} 앞",
                         "floor": floor, "x": x, "y": y, "access_node": f"F{floor}-{round_door(spec)}",
                         **sample_fills(None if number == 1 else ROUND_FILL_PATTERN[number % len(ROUND_FILL_PATTERN)], number),
                         "device_type": "real" if number == 1 else "demo",
                         "reading_source": "unconnected" if number == 1 else "demo",
                         "measured_at": None if number == 1 else stamp,
                         "received_at": None if number == 1 else stamp, "awaiting_confirmation": False})
    counts = {"office": 0, "depot": 0}
    for floor, room, kind, u, radius, label in ROUND_POINTS:
        counts[kind] += 1
        node_id = f"F{floor}-{'OF' if kind == 'office' else 'DP'}{counts[kind]}"
        point(node_id, floor, u, radius, kind, label)
        door = f"F{floor}-{round_door(ROUND_ROOMS[room])}"
        link(f"E-{door}-{node_id}", door, node_id)
    # one map unit is 9 plan pixels across; bins and new links are measured with it
    state["building"].update(name="예시 · 시립 곡선형 컨벤션센터", floors=ROUND_FLOORS, total_staff=8, available_staff=5,
                             meters_per_unit=round(9 * ROUND_M_PER_PX, 2))
    state.update(bins=bins, graph={"nodes": nodes, "edges": edges})
    return state


def sample_floorplans(template: str) -> dict:
    floors = {"large": LARGE_FLOORS, "library": LIBRARY_FLOORS, "civic": CIVIC_FLOORS, "round": ROUND_FLOORS}.get(template)
    if not floors:
        return {}
    images = {}
    for floor in range(1, floors + 1):
        source = SAMPLE_DIR / f"{template}-floor-{floor}.png"
        if source.is_file():
            name = f"sample-{template}-{floor}.png"
            (MAP_DIR / name).write_bytes(source.read_bytes())
            images[str(floor)] = name
    return images


def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MAP_DIR.mkdir(parents=True, exist_ok=True)
    with LOCK, database() as db:
        db.execute("PRAGMA journal_mode = WAL")
        db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
                salt TEXT NOT NULL, password_hash TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
                expires_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS workspaces (
                user_id INTEGER PRIMARY KEY REFERENCES users(id), state_json TEXT NOT NULL,
                device_key_hash TEXT UNIQUE
            );
        """)
        if not db.execute("SELECT id FROM users WHERE email = ?", (DEMO_EMAIL,)).fetchone():
            salt = secrets.token_hex(16)
            cursor = db.execute("INSERT INTO users(email, name, salt, password_hash, created_at) VALUES(?,?,?,?,?)",
                                (DEMO_EMAIL, "시연 관리자", salt, password_hash(DEMO_PASSWORD, salt), now()))
            db.execute("INSERT INTO workspaces(user_id, state_json) VALUES(?,?)",
                       (cursor.lastrowid, json.dumps(new_workspace(), ensure_ascii=False)))
        db.execute("DELETE FROM sessions WHERE expires_at < ?", (now(),))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Reloop Local MVP", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def basic_headers(request: Request, call_next):
    origin = request.headers.get("origin")
    if request.method not in {"GET", "HEAD", "OPTIONS"} and origin:
        allowed = {str(request.base_url).rstrip("/"), "http://127.0.0.1:5173", "http://localhost:5173"}
        if origin.rstrip("/") not in allowed:
            return JSONResponse({"detail": "허용되지 않은 요청 출처입니다."}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
    return response


def current_user(request: Request) -> dict:
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "로그인이 필요합니다.")
    hashed = hashlib.sha256(token.encode()).hexdigest()
    with database() as db:
        row = db.execute("SELECT u.id,u.email,u.name FROM sessions s JOIN users u ON u.id=s.user_id "
                         "WHERE s.token_hash=? AND s.expires_at>?", (hashed, now())).fetchone()
    if not row:
        raise HTTPException(401, "로그인이 만료되었습니다. 다시 로그인해 주세요.")
    return dict(row)


def read_workspace(db, user_id: int) -> dict:
    row = db.execute("SELECT state_json FROM workspaces WHERE user_id=?", (user_id,)).fetchone()
    if not row:
        raise HTTPException(404, "건물 정보를 찾을 수 없습니다.")
    state = json.loads(row[0])
    building = state["building"]
    # Workspaces saved before the travel-time model get its defaults; retired route modes fall back.
    building.pop("route_slack_percent", None)
    for key, value in ROUTE_DEFAULTS.items():
        building.setdefault(key, value)
    if building["route_mode"] not in ("fastest", "lean"):
        building["route_mode"] = ROUTE_DEFAULTS["route_mode"]
    return upgrade_points(upgrade_bins(state))


def upgrade_bins(state: dict) -> dict:
    """Bins saved with one category and one fill get four compartments: the old fill goes to its
    category's compartment and the others start empty (no value yet on a real device)."""
    for bin in state["bins"]:
        if "compartments" not in bin:
            category = OLD_CATEGORY.get(bin.pop("category", ""), "OTHER")
            fills = dict.fromkeys(COMPARTMENTS, None if bin["device_type"] == "real" else 0.0)
            fills[category] = bin.get("fill")
            set_fills(bin, fills)
        if bin["reading_source"] == "actual" and "compartment_measured_at" not in bin:
            bin["compartment_measured_at"] = {c: bin["measured_at"] for c, v in bin["compartments"].items()
                                               if v is not None and bin.get("measured_at")}
    return state


def upgrade_points(state: dict) -> dict:
    """Before version 2 a workspace kept one office in the building settings and named one corridor
    point as the drop-off. Both become graph points (kinds office and depot), joined to the same
    corridor points as before, so existing buildings keep their connections."""
    if state.get("graph_version", 1) >= 2:
        return state
    b, graph = state["building"], state["graph"]
    nodes = {n["id"]: n for n in graph["nodes"]}

    def add(base, floor, x, y, kind, label, access):
        k = 1
        while f"{base}{k}" in nodes:
            k += 1
        node = {"id": f"{base}{k}", "floor": floor, "x": x, "y": y, "kind": kind, "label": label}
        nodes[node["id"]] = node
        graph["nodes"].append(node)
        if access in nodes and nodes[access]["floor"] == floor:
            graph["edges"].append({"id": f"E-{access}-{node['id']}", "from": access, "to": node["id"], "distance_m": None})

    if "office_x" in b and not any(n["kind"] == "office" for n in graph["nodes"]):
        add(f"F{b['office_floor']}-OF", b["office_floor"], b["office_x"], b["office_y"], "office", "관리자실", b.get("office_access_node"))
    depot = nodes.get(b.get("depot_node") or "")
    if depot and not any(n["kind"] == "depot" for n in graph["nodes"]):
        # set just off the corridor point it used to be, so both stay clickable on the map
        y = depot["y"] + 10 if depot["y"] <= 90 else depot["y"] - 10
        add(f"F{depot['floor']}-DP", depot["floor"], depot["x"], y, "depot", "분리수거장", depot["id"])
    b["depot_node"] = ""
    state["graph_version"] = 2
    return state


def save_workspace(db, user_id: int, state: dict):
    state["revision"] = state.get("revision", 0) + 1
    state["updated_at"] = now()
    db.execute("UPDATE workspaces SET state_json=? WHERE user_id=?",
               (json.dumps(state, ensure_ascii=False, allow_nan=False), user_id))


def bin_status(bin: dict, config: dict, at: datetime | None = None) -> str:
    fill = max((v for v in current_fills(bin, config, at).values() if v is not None), default=None)
    if fill is None:
        return "offline"
    if bin.get("awaiting_confirmation"):
        return "pending"
    if fill >= config["critical_threshold"]:
        return "critical"
    if fill >= config["warning_threshold"]:
        return "warning"
    return "normal"


def route_signature(state: dict, at: datetime | None = None) -> str:
    at = at or datetime.now(timezone.utc)
    inputs = {"route_version": 2, "building": state["building"], "graph": state["graph"],
              "bins": [{k: b.get(k) for k in ["id", "floor", "x", "y", "access_node"]} |
                       {"compartments": current_fills(b, state["building"], at),
                        "status": bin_status(b, state["building"], at)} for b in state["bins"]]}
    return hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()


def public_bin(bin: dict, config: dict, at: datetime | None = None) -> dict:
    at = at or datetime.now(timezone.utc)
    result = copy.deepcopy(bin)
    values = current_fills(bin, config, at)
    result.update(last_compartments=dict(bin["compartments"]), compartments=values,
                  fill=max((v for v in values.values() if v is not None), default=None),
                  stale_compartments=[c for c in COMPARTMENTS if bin["compartments"][c] is not None and values[c] is None],
                  partial_reading=bin["reading_source"] == "actual" and any(v is not None for v in values.values())
                                  and any(v is None for v in values.values()),
                  status=bin_status(bin, config, at))
    return result


def public_workspace(state: dict, user: dict) -> dict:
    result = copy.deepcopy(state)
    at = datetime.now(timezone.utc)
    result["bins"] = [public_bin(bin, state["building"], at) for bin in state["bins"]]
    if result.get("last_plan"):
        result["last_plan"]["outdated"] = result["last_plan"]["signature"] != route_signature(state, at)
    result["user"] = user
    return result


def result_for(db, user: dict, state: dict):
    save_workspace(db, user["id"], state)
    return public_workspace(state, user)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(StrictModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class Register(Login):
    name: str = Field(min_length=1, max_length=40)


def set_session(response: Response, db, user_id: int):
    token = secrets.token_urlsafe(32)
    db.execute("INSERT INTO sessions(token_hash,user_id,expires_at) VALUES(?,?,?)",
               (hashlib.sha256(token.encode()).hexdigest(), user_id,
                (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()))
    response.set_cookie(COOKIE, token, httponly=True, samesite="strict", max_age=604800, path="/")


@app.get("/api/health")
def health():
    return {"status": "ok", "application": "reloop", "storage": "local-sqlite"}


@app.post("/api/auth/login")
def login(body: Login, response: Response):
    with LOCK, database() as db:
        row = db.execute("SELECT * FROM users WHERE email=?", (body.email.strip().lower(),)).fetchone()
        if not row or not hmac.compare_digest(password_hash(body.password, row["salt"]), row["password_hash"]):
            raise HTTPException(401, "이메일 또는 비밀번호를 확인해 주세요.")
        set_session(response, db, row["id"])
        return {"id": row["id"], "email": row["email"], "name": row["name"]}


@app.post("/api/auth/register", status_code=201)
def register(body: Register, response: Response):
    email, name = body.email.strip().lower(), body.name.strip()
    if "@" not in email or "." not in email.split("@")[-1] or not name:
        raise HTTPException(422, "이름과 이메일 형식을 확인해 주세요.")
    if len(body.password) < 8:
        raise HTTPException(422, "비밀번호는 8자 이상 입력해 주세요.")
    with LOCK, database() as db:
        if db.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
            raise HTTPException(409, "이미 가입된 이메일입니다.")
        salt = secrets.token_hex(16)
        cursor = db.execute("INSERT INTO users(email,name,salt,password_hash,created_at) VALUES(?,?,?,?,?)",
                            (email, name, salt, password_hash(body.password, salt), now()))
        user = {"id": cursor.lastrowid, "email": email, "name": name}
        db.execute("INSERT INTO workspaces(user_id,state_json) VALUES(?,?)",
                   (user["id"], json.dumps(new_workspace(), ensure_ascii=False)))
        set_session(response, db, user["id"])
        return user


@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE, "")
    with LOCK, database() as db:
        db.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@app.get("/api/workspace")
def get_workspace(user=Depends(current_user)):
    with database() as db:
        return public_workspace(read_workspace(db, user["id"]), user)


class ConfigPatch(StrictModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    floors: Optional[int] = Field(default=None, ge=1, le=10)
    total_staff: Optional[int] = Field(default=None, ge=1, le=12)
    available_staff: Optional[int] = Field(default=None, ge=0, le=12)
    include_orange: Optional[bool] = None
    route_mode: Optional[RouteMode] = None
    stairs_up_seconds: Optional[float] = Field(default=None, ge=1, le=300, allow_inf_nan=False)
    stairs_down_seconds: Optional[float] = Field(default=None, ge=1, le=300, allow_inf_nan=False)
    elevator_wait_seconds: Optional[float] = Field(default=None, ge=0, le=600, allow_inf_nan=False)
    elevator_floor_seconds: Optional[float] = Field(default=None, ge=0.5, le=120, allow_inf_nan=False)
    use_cart: Optional[bool] = None
    cart_capacity: Optional[float] = Field(default=None, ge=0, le=50, allow_inf_nan=False)
    depot_node: Optional[str] = Field(default=None, max_length=50)  # version 1, read to upgrade old backups
    unload_seconds: Optional[int] = Field(default=None, ge=0, le=600)
    max_work_minutes: Optional[int] = Field(default=None, ge=0, le=480)
    # version 1 office fields: kept so older backups restore, offices are graph points now
    office_floor: Optional[int] = Field(default=None, ge=1, le=10)
    office_x: Optional[float] = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    office_y: Optional[float] = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    office_access_node: Optional[str] = Field(default=None, max_length=50)
    meters_per_unit: Optional[float] = Field(default=None, ge=0.05, le=10, allow_inf_nan=False)
    speed_mps: Optional[float] = Field(default=None, ge=0.2, le=3, allow_inf_nan=False)
    service_seconds: Optional[int] = Field(default=None, ge=0, le=600)
    compartment_seconds: Optional[int] = Field(default=None, ge=0, le=600)
    warning_threshold: Optional[int] = Field(default=None, ge=1, le=99)
    critical_threshold: Optional[int] = Field(default=None, ge=2, le=100)
    stale_minutes: Optional[int] = Field(default=None, ge=1, le=120)


def validate_config(state: dict):
    cfg = state["building"]
    if cfg["available_staff"] > cfg["total_staff"]:
        raise HTTPException(422, "수거 가능 인원은 전체 관리자 수를 넘을 수 없습니다.")
    if cfg["warning_threshold"] >= cfg["critical_threshold"]:
        raise HTTPException(422, "주의 기준은 수거 필요 기준보다 작아야 합니다.")
    if any(b["floor"] > cfg["floors"] for b in state["bins"]):
        raise HTTPException(422, "등록된 쓰레기통의 층을 먼저 변경해 주세요.")
    if any(n["floor"] > cfg["floors"] for n in state["graph"]["nodes"]):
        raise HTTPException(422, "해당 층의 지점을 먼저 삭제해 주세요.")
    if 0 < cfg["cart_capacity"] < 1:
        raise HTTPException(422, "한 번에 옮길 양은 0(제한 없음) 또는 가득 찬 통 1개 이상이어야 합니다.")


@app.patch("/api/config")
def update_config(body: ConfigPatch, user=Depends(current_user)):
    with LOCK, database() as db:
        state = read_workspace(db, user["id"])
        patch = body.model_dump(exclude_unset=True)
        if any(v is None for v in patch.values()):
            raise HTTPException(422, "설정값은 비워 둘 수 없습니다.")
        state["building"].update(patch)
        validate_config(state)
        return result_for(db, user, state)


class BinCreate(StrictModel):
    name: str = Field(min_length=1, max_length=40)
    floor: int = Field(ge=1, le=10)
    x: float = Field(ge=0, le=100, allow_inf_nan=False)
    y: float = Field(ge=0, le=100, allow_inf_nan=False)
    access_node: str = Field(max_length=50)
    device_type: Literal["demo", "real"] = "demo"
    fills: dict[Compartment, Percent] = Field(default_factory=dict)  # demo values; missing ones start empty


class BinPatch(StrictModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=40)
    floor: Optional[int] = Field(default=None, ge=1, le=10)
    x: Optional[float] = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    y: Optional[float] = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    access_node: Optional[str] = Field(default=None, max_length=50)
    fills: Optional[dict[Compartment, Percent]] = None  # demo values of some compartments


def find_bin(state: dict, bin_id: str) -> dict:
    bin = next((b for b in state["bins"] if b["id"] == bin_id), None)
    if not bin:
        raise HTTPException(404, "쓰레기통을 찾을 수 없습니다.")
    return bin


def validate_bin(state: dict, bin: dict):
    if bin["floor"] > state["building"]["floors"]:
        raise HTTPException(422, "건물에 없는 층입니다.")
    node = next((n for n in state["graph"]["nodes"] if n["id"] == bin["access_node"]), None)
    if not node or node["floor"] != bin["floor"]:
        raise HTTPException(422, "같은 층에 있는 연결 통로를 선택해 주세요.")


@app.post("/api/bins", status_code=201)
def create_bin(body: BinCreate, user=Depends(current_user)):
    with LOCK, database() as db:
        state = read_workspace(db, user["id"])
        if len(state["bins"]) >= 100:
            raise HTTPException(422, "MVP에서는 쓰레기통을 최대 100개 등록할 수 있습니다.")
        if body.device_type == "real" and any(b["device_type"] == "real" for b in state["bins"]):
            raise HTTPException(422, "대회용 실물 장치는 1대입니다. 시연 장치로 추가해 주세요.")
        existing = {b["id"] for b in state["bins"]}
        number = 1
        while f"B-{number:03}" in existing:
            number += 1
        bin = body.model_dump() | {"id": f"B-{number:03}", "reading_source": "demo", "measured_at": now(),
                                   "received_at": now(), "awaiting_confirmation": False}
        set_fills(bin, dict.fromkeys(COMPARTMENTS, 0.0) | bin.pop("fills"))
        if body.device_type == "real":
            set_fills(bin, dict.fromkeys(COMPARTMENTS))
            bin.update(reading_source="unconnected", measured_at=None, received_at=None)
        validate_bin(state, bin)
        state["bins"].append(bin)
        return result_for(db, user, state)


@app.patch("/api/bins/{bin_id}")
def update_bin(bin_id: str, body: BinPatch, user=Depends(current_user)):
    with LOCK, database() as db:
        state = read_workspace(db, user["id"])
        bin = find_bin(state, bin_id)
        patch = body.model_dump(exclude_unset=True)
        if any(v is None for v in patch.values()):
            raise HTTPException(422, "쓰레기통 정보는 비워 둘 수 없습니다.")
        if "fills" in patch and bin["device_type"] == "real":
            raise HTTPException(422, "실물 장치는 센서 수신 또는 실물 시뮬레이션을 사용해 주세요.")
        fills = patch.pop("fills", None)
        bin.update(patch)
        if fills is not None:
            set_fills(bin, fills)
            bin.update(measured_at=now(), received_at=now(), awaiting_confirmation=False)
        validate_bin(state, bin)
        return result_for(db, user, state)


@app.delete("/api/bins/{bin_id}")
def delete_bin(bin_id: str, user=Depends(current_user)):
    with LOCK, database() as db:
        state = read_workspace(db, user["id"])
        bin = find_bin(state, bin_id)
        if bin["device_type"] == "real":
            raise HTTPException(422, "실물 시연 장치는 유지해 주세요.")
        state["bins"] = [b for b in state["bins"] if b["id"] != bin_id]
        return result_for(db, user, state)


class GraphNode(StrictModel):
    id: str = Field(min_length=1, max_length=50, pattern=r"^[A-Za-z0-9_-]+$")
    floor: int = Field(ge=1, le=10)
    x: float = Field(ge=0, le=100, allow_inf_nan=False)
    y: float = Field(ge=0, le=100, allow_inf_nan=False)
    kind: Literal["corridor", "stairs", "elevator", "office", "depot"] = "corridor"
    label: str = Field(default="통로", max_length=40)
    closed: bool = False  # a stair or lift stop out of service: no floor-to-floor moves there


class GraphEdge(StrictModel):
    id: str = Field(min_length=1, max_length=80)
    from_: str = Field(alias="from", max_length=50)
    to: str = Field(max_length=50)
    distance_m: Optional[float] = Field(default=None, gt=0, le=10000, allow_inf_nan=False)


class Graph(StrictModel):
    nodes: list[GraphNode] = Field(max_length=400)
    edges: list[GraphEdge] = Field(max_length=1200)


def validate_graph(graph: dict, floors: int):
    nodes = {n["id"]: n for n in graph["nodes"]}
    if len(nodes) != len(graph["nodes"]):
        raise HTTPException(422, "지점 번호가 중복됩니다.")
    if any(key.startswith("B-") for key in nodes):
        raise HTTPException(422, "지점 번호는 쓰레기통 번호와 달라야 합니다.")
    if any(n["floor"] > floors for n in nodes.values()):
        raise HTTPException(422, "건물에 없는 층의 지점입니다.")
    ids, pairs = set(), set()
    for edge in graph["edges"]:
        a, b = nodes.get(edge["from"]), nodes.get(edge["to"])
        if not a or not b or a["id"] == b["id"]:
            raise HTTPException(422, "연결할 지점을 확인해 주세요.")
        pair = tuple(sorted([a["id"], b["id"]]))
        if edge["id"] in ids or pair in pairs:
            raise HTTPException(422, "통로 연결이 중복됩니다.")
        ids.add(edge["id"])
        pairs.add(pair)
        if a["floor"] != b["floor"] and (a["kind"] not in {"stairs", "elevator"} or a["kind"] != b["kind"]):
            raise HTTPException(422, "층 사이는 계단끼리 또는 엘리베이터끼리 연결해 주세요.")


@app.put("/api/graph")
def update_graph(body: Graph, user=Depends(current_user)):
    with LOCK, database() as db:
        state = read_workspace(db, user["id"])
        graph = body.model_dump(by_alias=True)
        validate_graph(graph, state["building"]["floors"])
        state["graph"] = graph
        return result_for(db, user, state)


def build_graph(state: dict):
    config = state["building"]
    nodes = {n["id"]: dict(n) for n in state["graph"]["nodes"]}
    adjacency = {key: [] for key in nodes}

    def connect(a, b, distance):
        adjacency[a].append((b, distance))
        adjacency[b].append((a, distance))

    for edge in state["graph"]["edges"]:
        a, b = nodes[edge["from"]], nodes[edge["to"]]
        if edge.get("distance_m") is not None:
            distance = edge["distance_m"]
        elif a["floor"] == b["floor"]:
            distance = map_distance(a, b, config["meters_per_unit"])
        else:
            distance = abs(a["floor"] - b["floor"]) * 12.0
        connect(a["id"], b["id"], max(distance, 0.01))
    for point in state["bins"]:
        nodes[point["id"]] = dict(point)
        adjacency[point["id"]] = []
        access = nodes.get(point["access_node"])
        if access and access["floor"] == point["floor"]:
            distance = map_distance(point, access, config["meters_per_unit"])
            connect(point["id"], access["id"], max(distance, 0.01))
    return nodes, adjacency


def dijkstra(adjacency: dict, start: str):
    distances, previous = {start: 0.0}, {}
    queue = [(0.0, start)]
    while queue:
        distance, node = heapq.heappop(queue)
        if distance > distances[node]:
            continue
        for target, weight in adjacency[node]:
            new_distance = distance + weight
            if new_distance < distances.get(target, math.inf):
                distances[target], previous[target] = new_distance, node
                heapq.heappush(queue, (new_distance, target))
    return distances, previous


def travel_graph(state: dict):
    """Directed travel times between points, in seconds, with the walking metres of each step.

    Corridors cost metres / walking speed. Stairs cost a time per floor that differs going up and
    down. A lift ride costs one boarding wait plus a time per floor: every lift node gets a twin car
    node, so walking past the lift door costs nothing and the wait is paid once per ride. With a
    cart the stairs are closed and walking is slower."""
    config = state["building"]
    nodes, adjacency = build_graph(state)
    cart = config["use_cart"]
    speed = config["speed_mps"] * (CART_SPEED_RATIO if cart else 1)
    arcs = {key: [] for key in nodes}
    for key, node in list(nodes.items()):
        if node.get("kind") == "elevator":
            nodes[key + CAR] = dict(node, id=key + CAR)
            arcs[key + CAR] = [(key, 0.0, 0.0)]
            arcs[key].append((key + CAR, config["elevator_wait_seconds"], 0.0))
    for a, links in adjacency.items():
        for b, metres in links:
            here, there = nodes[a], nodes[b]
            rise = there["floor"] - here["floor"]
            if not rise:
                arcs[a].append((b, metres / speed, metres))
            elif here.get("closed") or there.get("closed"):
                continue
            elif here.get("kind") == "elevator":
                arcs[a + CAR].append((b + CAR, abs(rise) * config["elevator_floor_seconds"], 0.0))
            elif not cart:
                seconds = rise * config["stairs_up_seconds"] if rise > 0 else -rise * config["stairs_down_seconds"]
                arcs[a].append((b, seconds, metres))
    return nodes, arcs


def fastest_paths(arcs: dict, start: str):
    seconds, metres, previous = {start: 0.0}, {start: 0.0}, {}
    queue = [(0.0, start)]
    while queue:
        elapsed, node = heapq.heappop(queue)
        if elapsed > seconds[node]:
            continue
        for target, cost, length in arcs[node]:
            value = elapsed + cost
            if value < seconds.get(target, math.inf) - 1e-9:
                seconds[target], metres[target], previous[target] = value, metres[node] + length, node
                heapq.heappush(queue, (value, target))
    return seconds, metres, previous


def calculate_plan(state: dict) -> dict:
    config = state["building"]
    at = datetime.now(timezone.utc)
    selected = [b for b in state["bins"] if bin_status(b, config, at) == "critical" or
                (config["include_orange"] and bin_status(b, config, at) == "warning")]
    nodes, arcs = travel_graph(state)
    points = state["graph"]["nodes"]
    offices = [n["id"] for n in points if n["kind"] == "office"]
    depots = [n["id"] for n in points if n["kind"] == "depot"]
    ends = depots or offices  # without a drop-off point the cart is emptied at an office
    label = {n["id"]: n["label"] for n in points}
    seconds, metres, previous = {}, {}, {}
    for source in dict.fromkeys(offices + ends + [b["id"] for b in selected]):
        seconds[source], metres[source], previous[source] = fastest_paths(arcs, source)

    def start_of(target):  # (seconds, office) of the office this stop is quickest to reach from
        options = [(seconds[o][target], o) for o in offices if target in seconds[o]]
        return min(options) if options else None

    unreachable = [b["id"] for b in selected if start_of(b["id"]) is None or not any(e in seconds[b["id"]] for e in ends)]
    targets = [b["id"] for b in selected if b["id"] not in unreachable]
    issues = []
    if not offices:
        issues.append("관리자실이 없습니다. 건물·배치도의 '지점 설정'에서 관리자실을 놓아 주세요.")
    lonely = [label[o] for o in offices if not arcs.get(o)]
    if lonely:
        issues.append(f"통로와 이어지지 않은 관리자실이 있습니다: {', '.join(lonely)}. '통로 연결' 도구로 이어 주세요.")
    cut_off = [label[d] for d in depots if not any(d in seconds[o] for o in offices)]
    if offices and cut_off:
        issues.append(f"관리자실에서 갈 수 없는 분리수거장이 있습니다: {', '.join(cut_off)}. '통로 연결' 도구로 이어 주세요.")
    if unreachable:
        issues.append(f"통로와 이어지지 않아 경로에서 빠진 쓰레기통이 있습니다: {', '.join(unreachable)}. 건물·배치도에서 통로 연결을 확인해 주세요.")
    empty = {b["id"]: to_empty(b, config, at) for b in selected}
    load = {t: sum(v.values()) / 100 for t, v in empty.items()}  # in full compartments
    workers = min(config["available_staff"], len(targets))
    mode = config.get("route_mode", ROUTE_DEFAULTS["route_mode"])
    capacity = config["cart_capacity"] or math.inf
    limit = config["max_work_minutes"] * 60 or math.inf
    unload = config["unload_seconds"]
    capacity_issues = [{"bin_id": t, "load": round(load[t], 3), "capacity": capacity}
                       for t in targets if load[t] > capacity + 1e-9]
    if capacity_issues:
        # The MVP collects a location in one visit. Do not produce an impossible route or silently
        # omit an oversized location. Leave the whole plan unassigned until the settings/data change.
        issues += [f"{p['bin_id']}: 수거량 {p['load']:g}칸 분량 / 운반 가능 {p['capacity']:g}칸 분량. "
                   "한 위치를 나눠 운반하는 기능은 아직 지원하지 않습니다. 실제 운반 용량과 수거 상태를 확인해 주세요."
                   for p in capacity_issues]
        return {"created_at": now(), "signature": route_signature(state, at), "include_orange": config["include_orange"],
                "available_staff": config["available_staff"], "mode": mode, "end": "DEPOT" if depots else "OFFICE",
                "issues": issues, "blocked_reason": "capacity", "capacity_issues": capacity_issues,
                "max_work_seconds": None if limit == math.inf else limit, "routes": [], "target_ids": targets,
                "unreachable": unreachable, "empty": {t: empty[t] for t in targets}, "unassigned": targets,
                "total_distance_m": 0.0, "makespan_seconds": 0, "total_seconds": 0,
                "method": "time-model-alns", "outdated": False}
    # time at a location: a base time plus a time per compartment emptied
    serve = {t: config["service_seconds"] + config["compartment_seconds"] * len(v) for t, v in empty.items()}
    cache: dict[tuple, tuple] = {}
    # Same inputs, same plan: the search is seeded from everything but the chosen preset and the
    # number of available staff (the worker count of each search is part of its own seed).
    seed = route_signature(dict(state, building={k: v for k, v in config.items() if k not in ("route_mode", "available_staff")}), at)

    def evaluate(route):
        # Seconds, walking metres, trips and start office for one visiting order. The route starts
        # at the office nearest its first stop. The cart is emptied whenever the next bins would not
        # fit, at whichever drop-off point (or office) suits; dynamic programming picks where to
        # break the order into trips and where each trip unloads.
        key = tuple(route)
        if key in cache:
            return cache[key]
        n = len(route)
        if not n:
            cache[key] = (0.0, 0.0, [], None)
            return cache[key]
        chain_t, chain_m, served = [0.0], [0.0], [0.0]
        for t in route:
            served.append(served[-1] + serve[t])
        for a, b in zip(route, route[1:]):
            chain_t.append(chain_t[-1] + seconds[a].get(b, math.inf))
            chain_m.append(chain_m[-1] + metres[a].get(b, 0.0))
        first = start_of(route[0])
        # best[j][e]: (seconds, metres, i, previous end) covering route[:j] with the last trip ending at e
        best: list[dict] = [{} for _ in range(n + 1)]
        for j in range(1, n + 1):
            carried = 0.0
            for i in range(j - 1, -1, -1):
                carried += load[route[i]]
                if carried > capacity + 1e-9:
                    break
                inner_t = chain_t[j - 1] - chain_t[i] + served[j] - served[i] + unload
                inner_m = chain_m[j - 1] - chain_m[i]
                if i == 0:
                    leads = [(0.0, 0.0, None, first[0], metres[first[1]][route[0]])] if first else []
                else:
                    leads = [(t, m, e, seconds[e].get(route[i], math.inf), metres[e].get(route[i], 0.0))
                             for e, (t, m, *_) in best[i].items()]
                for prev_t, prev_m, prev_end, lead_t, lead_m in leads:
                    for e in ends:
                        tail = seconds[route[j - 1]].get(e)
                        if tail is None:
                            continue
                        value = prev_t + lead_t + inner_t + tail
                        if value < best[j].get(e, (math.inf,))[0]:
                            best[j][e] = (value, prev_m + lead_m + inner_m + metres[route[j - 1]][e], i, prev_end)
        if not best[n] or not first:
            cache[key] = (math.inf, 0.0, [], None)
            return cache[key]
        e = min(best[n], key=lambda k: (best[n][k][0], k))
        total_t, total_m = best[n][e][:2]
        trips, j = [], n
        while j > 0:
            _, _, i, prev_end = best[j][e]
            trips.append((j, e))
            j, e = i, prev_end
        cache[key] = result = (total_t, total_m, sorted(trips), first[1])
        return result

    def value_of(span, total, used, preset):
        # fastest: finish time, then total time; the cap needs no term, because the earliest finish
        # keeps everyone under it whenever that is possible. lean: the worst overrun of the cap first,
        # then the number of workers, then finish time, then total time.
        if preset == "fastest":
            return span + 0.001 * total
        return 1e7 * max(0.0, span - limit) + 1e5 * used + span + 0.001 * total

    def score(routes, preset):
        times = [evaluate(r)[0] for r in routes if r]
        return value_of(max(times, default=0.0), sum(times), len(times), preset)

    def options(routes, target, preset):
        # Every place the target could go, cheapest first. Only the first empty route is tried.
        times = [evaluate(r)[0] for r in routes]
        total, used = sum(times), sum(1 for r in routes if r)
        found, tried_empty = [], False
        for r, route in enumerate(routes):
            if not route:
                if tried_empty:
                    continue
                tried_empty = True
            other_span = max(times[:r] + times[r + 1:], default=0.0)
            for p in range(len(route) + 1):
                new = evaluate(route[:p] + [target] + route[p:])[0]
                value = value_of(max(other_span, new), total - times[r] + new, used + (0 if route else 1), preset)
                found.append((value, r, p))
        found.sort()
        return found

    def repair(routes, removed, preset, regret):
        # Greedy: put each stop in its cheapest place. Regret-2: first place the stop that would lose
        # the most if its best place were taken.
        routes, left = [r[:] for r in routes], list(removed)
        while left:
            if regret:
                choice = None
                for t in left:
                    found = options(routes, t, preset)
                    gap = found[1][0] - found[0][0] if len(found) > 1 else math.inf
                    if choice is None or gap > choice[0]:
                        choice = (gap, t, found[0])
                _, t, (_, r, p) = choice
            else:
                t = left[0]
                _, r, p = options(routes, t, preset)[0]
            routes[r].insert(p, t)
            left.remove(t)
        return routes

    def destroy(routes, how, rng):
        stops = [t for r in routes for t in r]
        count = min(len(stops), rng.randint(1, max(1, min(5, len(stops) // 3 + 1))))
        if how == "random":
            removed = rng.sample(stops, count)
        elif how == "worst":
            savings = sorted(((evaluate(r)[0] - evaluate(r[:i] + r[i + 1:])[0], t) for r in routes for i, t in enumerate(r)), reverse=True)
            removed = [t for _, t in savings[:count]]
        elif how == "related":
            seed = rng.choice(stops)
            removed = sorted(stops, key=lambda t: (seconds[seed].get(t, math.inf) + seconds[t].get(seed, math.inf), t))[:count]
        else:
            removed = list(rng.choice([r for r in routes if r]))
        gone = set(removed)
        return [[t for t in r if t not in gone] for r in routes], removed

    def polish(route):
        # Reverse a section (2-opt) or move one stop, judged by the full route time with unloading.
        for _ in range(20):
            best, best_time = route, evaluate(route)[0]
            for i in range(len(route)):
                for j in range(i + 2, len(route) + 1):
                    trial = route[:i] + list(reversed(route[i:j])) + route[j:]
                    if evaluate(trial)[0] + 0.001 < best_time:
                        best, best_time = trial, evaluate(trial)[0]
                rest = route[:i] + route[i + 1:]
                for p in range(len(rest) + 1):
                    trial = rest[:p] + [route[i]] + rest[p:]
                    if evaluate(trial)[0] + 0.001 < best_time:
                        best, best_time = trial, evaluate(trial)[0]
            if best is route:
                return route
            route = best
        return route

    def search(preset, count):
        # Several independent runs with different random seeds, as long as the time budget allows;
        # the best plan for at most `count` workers wins. The first run always completes.
        if not count:
            return []
        began, best = time.perf_counter(), None
        for attempt in range(SEARCH_RESTARTS):
            if attempt and time.perf_counter() - began > SEARCH_SECONDS / 2:
                break
            found = settle(anneal(preset, count, random.Random(f"{seed}-{preset}-{count}-{attempt}"), began), preset, began)
            if best is None or score(found, preset) < score(best, preset) - 1e-6:
                best = found
        return best

    def anneal(preset, count, rng, began):
        # Adaptive large neighbourhood search: repeatedly remove a few stops and put them back,
        # accept by simulated annealing, and use more often the removal rules that pay off.
        start_routes = repair([[] for _ in range(count)], sorted(targets, key=lambda t: (-start_of(t)[0], t)), preset, False)
        current = best = start_routes
        current_score = best_score = score(best, preset)
        times = [evaluate(r)[0] for r in best if r]
        heat = max(0.5, SEARCH_HEAT * max(times))  # both presets now trade mainly in finish time
        rules, weights = ["random", "worst", "related", "route"], [1.0] * 4
        gained, used = [0.0] * 4, [0] * 4
        rounds = SEARCH_ROUNDS + SEARCH_ROUNDS_PER_STOP * len(targets) if len(targets) > 1 else 0
        for step in range(rounds):
            if time.perf_counter() - began > SEARCH_SECONDS:
                break
            k = rng.choices(range(4), weights)[0]
            partial, removed = destroy(current, rules[k], rng)
            candidate = repair(partial, removed, preset, regret=len(targets) <= 15 and rng.random() < 0.3)
            value = score(candidate, preset)
            temperature = heat * 0.001 ** (step / rounds)
            used[k] += 1
            if value < best_score - 1e-6:
                best, best_score, current, current_score = candidate, value, candidate, value
                gained[k] += 3
            elif value < current_score - 1e-6:
                current, current_score = candidate, value
                gained[k] += 2
            elif value - current_score < 30 * temperature and rng.random() < math.exp(-(value - current_score) / temperature):
                current, current_score = candidate, value
                gained[k] += 1
            if (step + 1) % 50 == 0:
                weights = [max(0.1, 0.7 * w + 0.3 * (g / u if u else 0)) for w, g, u in zip(weights, gained, used)]
                gained, used = [0.0] * 4, [0] * 4
        return best

    def settle(routes, preset, began):
        # Finish with plain local search between workers: move one stop to another worker or swap two
        # stops, taking the first change that helps, until none does or the time budget runs out.
        routes = [polish(r) for r in routes]
        improved = True
        while improved and time.perf_counter() - began < SEARCH_SECONDS * 1.5:
            improved = False
            current = score(routes, preset)
            times = [evaluate(r)[0] for r in routes]
            for i, a in enumerate(routes):
                for x, stop in enumerate(a):
                    rest = a[:x] + a[x + 1:]
                    for j, b in enumerate(routes):
                        if i == j or (not b and any(not r for r in routes[:j])):
                            continue
                        others = [t for k, t in enumerate(times) if k not in (i, j)]
                        trials = [(rest, b[:p] + [stop] + b[p:]) for p in range(len(b) + 1)]
                        if i < j:
                            trials += [(rest[:x] + [y] + rest[x:], b[:q] + [stop] + b[q + 1:]) for q, y in enumerate(b)]
                        for new_a, new_b in trials:
                            ta, tb = evaluate(new_a)[0], evaluate(new_b)[0]
                            moved = [t for t in (ta, tb) if t] + [t for t in others if t]
                            if value_of(max(moved, default=0.0), sum(moved), len(moved), preset) < current - 1e-6:
                                routes[i], routes[j] = polish(new_a), polish(new_b)
                                improved = True
                                break
                        if improved:
                            break
                    if improved:
                        break
                if improved:
                    break
        return routes

    def path(a, b):
        steps = [b]
        while steps[-1] != a:
            steps.append(previous[a][steps[-1]])
        out: list[str] = []
        for step in reversed(steps):
            step = step.removesuffix(CAR)
            if not out or out[-1] != step:
                out.append(step)
        return out

    def summary(assigned):
        used = [r for r in assigned if r]
        used = [r for r in used if evaluate(r)[0] < math.inf]
        times = [evaluate(r)[0] for r in used]
        return {"workers": len(used), "total_distance_m": round(sum(round(evaluate(r)[1], 1) for r in used), 1),
                "makespan_seconds": max((round(t) for t in times), default=0), "total_seconds": round(sum(times))}

    fastest = search("fastest", workers)
    # 인력 아끼기: first the fewest workers that keep everyone under the cap, then the fastest plan for
    # exactly that many. The second search is the same as '빨리 끝내기' with that many staff, so spare
    # staff never change the result.
    fewest = search("lean", workers)
    needed = sum(1 for r in fewest if r)
    lean = fastest if needed == workers else search("fastest", needed)
    if score(fewest, "lean") < score(lean, "lean") - 1e-6 and max((evaluate(r)[0] for r in lean if r), default=0.0) > limit:
        lean = fewest  # the second search missed the cap that the first one kept
    # '빨리 끝내기' never ends later than '인력 아끼기': it takes the lean plan if that one is faster.
    plans = {"fastest": min((fastest, lean), key=lambda routes: score(routes, "fastest")), "lean": lean}
    if mode not in plans:
        mode = ROUTE_DEFAULTS["route_mode"]
    routes, split = [], []
    for route in (r for r in plans[mode] if r):
        duration, walked, trips, start = evaluate(route)
        if duration == math.inf:  # parts with no corridor between them and too few workers to cover each
            split += route
            continue
        sequence, previous_cut = [], 0
        for cut, end_point in trips:
            sequence += route[previous_cut:cut] + [end_point]
            previous_cut = cut
        stops, path_ids = [start] + sequence, []
        for a, b in zip(stops, stops[1:]):
            leg = path(a, b)
            path_ids.extend(leg if not path_ids else leg[1:])
        index = len(routes)
        routes.append({"worker": index + 1, "color": ROUTE_COLORS[index % len(ROUTE_COLORS)],
                       "bin_ids": route, "start": start, "sequence": sequence, "drops": len(trips),
                       "distance_m": round(walked, 1), "duration_seconds": round(duration),
                       "over_limit": duration > limit + 0.5,
                       "path": [{"id": n, "floor": nodes[n]["floor"], "x": nodes[n]["x"], "y": nodes[n]["y"],
                                 "kind": nodes[n].get("kind", "bin")} for n in path_ids]})
    if split:
        issues.append(f"서로 오갈 수 없는 구역에 있어 경로에 넣지 못한 쓰레기통이 있습니다: {', '.join(split)}. "
                      "'통로 연결' 도구로 구역을 이어 주세요.")
        unreachable += split
        targets = [t for t in targets if t not in split]
    return {"created_at": now(), "signature": route_signature(state, at), "include_orange": config["include_orange"],
            "available_staff": config["available_staff"], "mode": mode, "end": "DEPOT" if depots else "OFFICE", "issues": issues,
            "max_work_seconds": None if limit == math.inf else limit, "routes": routes,
            "target_ids": targets, "unreachable": unreachable, "empty": {t: empty[t] for t in targets},
            "unassigned": targets if workers == 0 else [],
            "total_distance_m": round(sum(r["distance_m"] for r in routes), 1),
            "makespan_seconds": max((r["duration_seconds"] for r in routes), default=0),
            "total_seconds": sum(r["duration_seconds"] for r in routes),
            "comparison": {name: summary(assigned) for name, assigned in plans.items()},
            "method": "time-model-alns", "outdated": False}


class PlanRequest(StrictModel):
    available_staff: Optional[int] = Field(default=None, ge=0, le=12)
    include_orange: Optional[bool] = None
    route_mode: Optional[RouteMode] = None


@app.post("/api/plan")
def plan(body: PlanRequest, user=Depends(current_user)):
    with LOCK, database() as db:
        state = read_workspace(db, user["id"])
        state["building"].update({k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None})
        validate_config(state)
        state["last_plan"] = calculate_plan(state)
        return result_for(db, user, state)


class CollectRequest(StrictModel):
    worker: Optional[int] = Field(default=None, ge=1, le=12)


@app.post("/api/collect/{bin_id}")
def collect(bin_id: str, body: CollectRequest, user=Depends(current_user)):
    with LOCK, database() as db:
        state = read_workspace(db, user["id"])
        bin = find_bin(state, bin_id)
        at = datetime.now(timezone.utc)
        current = public_bin(bin, state["building"], at)
        if current["fill"] is None or bin.get("awaiting_confirmation"):
            raise HTTPException(422, "수거할 상태값이 없거나 센서 확인을 기다리고 있습니다.")
        if bin["reading_source"] == "actual" and current["status"] == "offline":
            raise HTTPException(422, "최신 센서값을 수신한 뒤 수거를 완료해 주세요.")
        emptied = to_empty(bin, state["building"], at)
        state["logs"].insert(0, {"id": secrets.token_hex(6), "bin_id": bin_id, "floor": bin["floor"],
                                 "name": bin["name"], "fill_before": current["fill"], "emptied": emptied, "worker": body.worker,
                                 "actor": user["name"], "source": bin["reading_source"], "completed_at": now()})
        state["logs"] = state["logs"][:1000]
        if bin["reading_source"] == "actual":
            # confirmed once the sensor has reported every emptied compartment again
            bin.update(awaiting_confirmation=True, collection_pending_at=now(), pending_compartments=sorted(emptied))
        else:
            set_fills(bin, dict.fromkeys(emptied, 0.0))
            bin.update(measured_at=now(), received_at=now())
        if state["last_plan"]:
            state["last_plan"] = calculate_plan(state)
        return result_for(db, user, state)


class Scenario(StrictModel):
    scenario: Literal["mixed", "rush", "calm"]


@app.post("/api/demo/scenario")
def scenario(body: Scenario, user=Depends(current_user)):
    values = {"mixed": [94, 43, 84, 97, 65, 88, 35, 76, 92, 58, 81],
              "rush": [98, 86, 92, 97, 91, 88, 83, 96, 95, 89, 93],
              "calm": [24, 43, 34, 17, 65, 28, 35, 46, 32, 58, 21]}
    with LOCK, database() as db:
        state = read_workspace(db, user["id"])
        index = 0
        for bin in state["bins"]:
            if bin["device_type"] == "demo":
                set_fills(bin, demo_fills(values[body.scenario][index % 11], index))
                bin.update(measured_at=now(), received_at=now(), awaiting_confirmation=False)
                index += 1
        if state["last_plan"]:
            state["last_plan"] = calculate_plan(state)
        return result_for(db, user, state)


class Simulation(StrictModel):
    fills: Optional[dict[Compartment, Percent]] = None  # None disconnects the simulation


@app.post("/api/demo/real-simulation")
def real_simulation(body: Simulation, user=Depends(current_user)):
    with LOCK, database() as db:
        state = read_workspace(db, user["id"])
        bin = next((b for b in state["bins"] if b["device_type"] == "real"), None)
        if not bin:
            raise HTTPException(404, "실물 장치가 없습니다.")
        if body.fills is None:
            set_fills(bin, dict.fromkeys(COMPARTMENTS))
            bin.update(reading_source="unconnected", measured_at=None, received_at=None, awaiting_confirmation=False)
        else:
            set_fills(bin, dict.fromkeys(COMPARTMENTS, 0.0) | body.fills)
            bin.update(reading_source="simulated", measured_at=now(), received_at=now(), awaiting_confirmation=False)
        bin["compartment_measured_at"] = {}
        state["readings"].insert(0, {"bin_id": bin["id"], "fill": bin["fill"], "fills": body.fills,
                                     "source": bin["reading_source"], "at": now()})
        state["readings"] = state["readings"][:200]
        return result_for(db, user, state)


class DemoReset(StrictModel):
    template: Literal["basic", "large", "library", "civic", "round"] = "basic"


@app.post("/api/demo/reset")
def reset_demo(body: DemoReset, user=Depends(current_user)):
    with LOCK, database() as db:
        old_state = read_workspace(db, user["id"])
        state = {"large": large_workspace, "library": library_workspace, "civic": civic_workspace,
                 "round": round_workspace}.get(body.template, new_workspace)()
        state["map_images"] = sample_floorplans(body.template)
        state["device_key_hint"] = old_state.get("device_key_hint")
        return result_for(db, user, state)


@app.post("/api/device/key")
def create_device_key(user=Depends(current_user)):
    key = "rl_" + secrets.token_urlsafe(32)
    with LOCK, database() as db:
        state = read_workspace(db, user["id"])
        state["device_key_hint"] = key[-6:]
        db.execute("UPDATE workspaces SET device_key_hash=? WHERE user_id=?",
                   (hashlib.sha256(key.encode()).hexdigest(), user["id"]))
        save_workspace(db, user["id"], state)
    return {"key": key, "hint": key[-6:]}


class DeviceReading(StrictModel):
    bin_id: str = Field(min_length=1, max_length=20)
    compartment: Optional[Compartment] = None  # one compartment with fill_percent ...
    fill_percent: Optional[float] = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    fills: Optional[dict[Compartment, Percent]] = None  # ... or several compartments at once
    measured_at: Optional[str] = Field(default=None, max_length=50)


@app.post("/api/device/readings")
def device_reading(body: DeviceReading, x_device_key: str = Header(default="", max_length=200)):
    if not x_device_key:
        raise HTTPException(401, "X-Device-Key 헤더가 필요합니다.")
    with LOCK, database() as db:
        row = db.execute("SELECT user_id FROM workspaces WHERE device_key_hash=?",
                         (hashlib.sha256(x_device_key.encode()).hexdigest(),)).fetchone()
        if not row:
            raise HTTPException(401, "장치 연결 키를 확인해 주세요.")
        state = read_workspace(db, row["user_id"])
        bin = find_bin(state, body.bin_id)
        if bin["device_type"] != "real":
            raise HTTPException(422, "실물로 등록된 쓰레기통만 센서값을 수신합니다.")
        if body.compartment and body.fill_percent is not None and body.fills is None:
            fills = {body.compartment: body.fill_percent}
        elif body.fills and body.compartment is None and body.fill_percent is None:
            fills = body.fills
        else:
            raise HTTPException(422, "칸별 적재율을 compartment와 fill_percent, 또는 fills로 보내 주세요.")
        measured = parse_time(body.measured_at) if body.measured_at else datetime.now(timezone.utc)
        if measured > datetime.now(timezone.utc) + timedelta(minutes=2):
            raise HTTPException(422, "측정 시각이 현재보다 너무 늦습니다.")
        times = bin.get("compartment_measured_at") or {}
        if bin["reading_source"] == "actual" and any(c in times and measured <= parse_time(times[c]) for c in fills):
            raise HTTPException(409, "이미 수신한 값보다 이전 측정값입니다.")
        if bin["reading_source"] != "actual":  # simulated values are not mixed with real ones
            set_fills(bin, dict.fromkeys(COMPARTMENTS))
            times = {}
        pending = set(bin.get("pending_compartments", COMPARTMENTS))
        if bin.get("collection_pending_at") and measured > parse_time(bin["collection_pending_at"]):
            pending -= set(fills)
        still_pending = bool(bin.get("awaiting_confirmation") and pending)
        set_fills(bin, fills)
        times.update(dict.fromkeys(fills, measured.isoformat()))
        latest = max([measured] + ([parse_time(bin["measured_at"])] if bin["reading_source"] == "actual" and bin["measured_at"] else []))
        bin.update(measured_at=latest.isoformat(), received_at=now(), reading_source="actual", compartment_measured_at=times,
                   awaiting_confirmation=still_pending, pending_compartments=sorted(pending) if still_pending else [])
        state["readings"].insert(0, {"bin_id": bin["id"], "fill": bin["fill"], "fills": fills, "source": "actual", "at": now()})
        state["readings"] = state["readings"][:200]
        save_workspace(db, row["user_id"], state)
    current = public_bin(bin, state["building"])
    return {"ok": True, "bin_id": body.bin_id, "compartments": current["compartments"], "fill_percent": current["fill"],
            "stale_compartments": current["stale_compartments"], "partial_reading": current["partial_reading"],
            "status": current["status"]}


class MapImage(StrictModel):
    data_url: Optional[str] = Field(default=None, max_length=5_600_000)


@app.put("/api/floorplan/{floor}")
def upload_floorplan(floor: int, body: MapImage, user=Depends(current_user)):
    with LOCK, database() as db:
        state = read_workspace(db, user["id"])
        if floor < 1 or floor > state["building"]["floors"]:
            raise HTTPException(422, "건물에 없는 층입니다.")
        if body.data_url is None:
            state["map_images"].pop(str(floor), None)
        else:
            try:
                header, encoded = body.data_url.split(",", 1)
                raw = base64.b64decode(encoded, validate=True)
            except (ValueError, TypeError):
                raise HTTPException(422, "이미지 파일을 확인해 주세요.")
            if raw.startswith(b"\x89PNG\r\n\x1a\n"):
                suffix = ".png"
            elif raw.startswith(b"\xff\xd8\xff"):
                suffix = ".jpg"
            elif raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
                suffix = ".webp"
            else:
                raise HTTPException(422, "PNG, JPG, WEBP 이미지를 사용해 주세요.")
            if len(raw) > 4_000_000:
                raise HTTPException(422, "도면 이미지는 4MB 이하여야 합니다.")
            name = secrets.token_hex(16) + suffix
            (MAP_DIR / name).write_bytes(raw)
            state["map_images"][str(floor)] = name
        return result_for(db, user, state)


@app.get("/api/floorplan/{floor}")
def get_floorplan(floor: int, user=Depends(current_user)):
    with database() as db:
        state = read_workspace(db, user["id"])
        name = state["map_images"].get(str(floor))
        if not name or Path(name).name != name or not (MAP_DIR / name).is_file():
            raise HTTPException(404, "등록한 도면이 없습니다.")
        return FileResponse(MAP_DIR / name)


@app.get("/api/backup")
def backup(user=Depends(current_user)):
    with database() as db:
        state = read_workspace(db, user["id"])
    state.pop("device_key_hint", None)
    state["last_plan"] = None
    images = {}
    for floor, name in state.get("map_images", {}).items():
        file = MAP_DIR / Path(name).name
        if file.is_file():
            images[floor] = base64.b64encode(file.read_bytes()).decode()
    return JSONResponse({"format": "reloop-backup-v1", "created_at": now(), "workspace": state, "images": images},
                        headers={"Content-Disposition": 'attachment; filename="reloop-backup.json"'})


class RestoreRequest(StrictModel):
    format: Literal["reloop-backup-v1"]
    created_at: str
    workspace: dict
    images: dict[str, str] = Field(default_factory=dict)


class SavedLog(StrictModel):
    id: str = Field(min_length=1, max_length=50)
    bin_id: str = Field(min_length=1, max_length=20)
    floor: int = Field(ge=1, le=10)
    name: str = Field(max_length=40)
    fill_before: float = Field(ge=0, le=100, allow_inf_nan=False)
    emptied: Optional[dict[Compartment, Percent]] = None
    worker: Optional[int] = Field(default=None, ge=1, le=12)
    actor: str = Field(min_length=1, max_length=40)
    source: Literal["actual", "simulated", "demo"]
    completed_at: str = Field(max_length=50)


class SavedReading(StrictModel):
    bin_id: str = Field(max_length=20)
    fill: Optional[float] = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    fills: Optional[dict[Compartment, Percent]] = None
    source: Literal["actual", "simulated", "demo", "unconnected"]
    at: str = Field(max_length=50)


@app.post("/api/restore")
def restore(body: RestoreRequest, user=Depends(current_user)):
    if len(json.dumps(body.model_dump())) > 35_000_000:
        raise HTTPException(422, "백업 파일은 35MB 이하로 선택해 주세요.")
    try:
        incoming = body.workspace
        config = ConfigPatch(**(ROUTE_DEFAULTS | incoming["building"])).model_dump()
        if any(v is None for v in config.values()):
            raise ValueError("incomplete configuration")
        graph = Graph(**incoming["graph"]).model_dump(by_alias=True)
        if not 1 <= len(incoming["bins"]) <= 100:
            raise ValueError("invalid bin count")
        bins = []
        ids = set()
        for item in incoming["bins"]:
            item = upgrade_bins({"bins": [dict(item)]})["bins"][0]  # older backups: one category and one fill
            known = {c: v for c, v in item["compartments"].items() if v is not None}
            clean = BinCreate(**{k: item[k] for k in BinCreate.model_fields if k != "fills"}, fills=known).model_dump()
            fills = clean.pop("fills")
            bin_id = item["id"]
            if not isinstance(bin_id, str) or not bin_id.startswith("B-") or not bin_id[2:].isdigit() or len(bin_id) > 12 or bin_id in ids:
                raise ValueError("invalid bin id")
            ids.add(bin_id)
            source = "demo" if clean["device_type"] == "demo" else "unconnected"
            bin = clean | {"id": bin_id, "reading_source": source, "measured_at": now() if source == "demo" else None,
                           "received_at": now() if source == "demo" else None, "awaiting_confirmation": False}
            bins.append(set_fills(bin, dict.fromkeys(COMPARTMENTS) if source == "unconnected" else dict.fromkeys(COMPARTMENTS, 0.0) | fills))
        if sum(b["device_type"] == "real" for b in bins) != 1:
            raise ValueError("one real device required")
        state = new_workspace()
        state.update(building=config, graph=graph, bins=bins, map_images={}, logs=[], readings=[], last_plan=None,
                     graph_version=2 if any(n["kind"] == "office" for n in graph["nodes"]) else 1)
        upgrade_points(state)
        if len(incoming.get("logs", [])) > 1000 or len(incoming.get("readings", [])) > 200:
            raise ValueError("too many records")
        state["logs"] = [SavedLog(**item).model_dump() for item in incoming.get("logs", [])]
        state["readings"] = [SavedReading(**item).model_dump() for item in incoming.get("readings", [])]
        for item in state["logs"]:
            parse_time(item["completed_at"])
        for item in state["readings"]:
            parse_time(item["at"])
        validate_graph(graph, config["floors"])
        validate_config(state)
        for bin in bins:
            validate_bin(state, bin)
    except (ValueError, KeyError, TypeError):
        raise HTTPException(422, "리루프에서 내보낸 백업 파일인지 확인해 주세요.")
    images_to_write = []
    for floor, encoded in body.images.items():
        if not floor.isdigit() or not 1 <= int(floor) <= config["floors"]:
            raise HTTPException(422, "도면의 층 정보를 확인해 주세요.")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError):
            raise HTTPException(422, "백업 도면이 손상되었습니다.")
        suffix = ".png" if raw.startswith(b"\x89PNG\r\n\x1a\n") else ".jpg" if raw.startswith(b"\xff\xd8\xff") else ".webp" if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP" else None
        if not suffix or len(raw) > 4_000_000:
            raise HTTPException(422, "백업 도면의 형식이나 크기를 확인해 주세요.")
        name = secrets.token_hex(16) + suffix
        state["map_images"][floor] = name
        images_to_write.append((name, raw))
    with LOCK, database() as db:
        old = read_workspace(db, user["id"])
        state["device_key_hint"] = old.get("device_key_hint")
        for name, raw in images_to_write:
            (MAP_DIR / name).write_bytes(raw)
        return result_for(db, user, state)


@app.get("/{path:path}")
def frontend(path: str):
    if path.startswith("api/"):
        raise HTTPException(404, "존재하지 않는 API입니다.")
    dist = (ROOT / "dist").resolve()
    candidate = (dist / path).resolve()
    if not candidate.is_relative_to(dist):
        raise HTTPException(404)
    if path and candidate.is_file():
        return FileResponse(candidate)
    if (dist / "index.html").is_file():
        return FileResponse(dist / "index.html")
    return JSONResponse({"message": "화면 빌드 후 start.ps1로 실행해 주세요."}, status_code=503)
