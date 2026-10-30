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
import secrets
import sqlite3
import threading
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("RELOOP_DATA_DIR", str(ROOT / "data")))
DB_PATH = DATA_DIR / "reloop.sqlite3"
MAP_DIR = DATA_DIR / "maps"
LOCK = threading.RLock()
COOKIE = "reloop_session"
DEMO_EMAIL = "demo@reloop.local"
DEMO_PASSWORD = "Demo1234!"
ROUTE_COLORS = ["#3976db", "#9266ce", "#1d9caa", "#bf648f", "#6073a3", "#9b7946"]


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
                         "category": ["PET", "캔", "일반", "혼합"][index],
                         "fill": levels[floor-1][index], "device_type": "real" if number == 1 else "demo",
                         "reading_source": "unconnected" if number == 1 else "demo",
                         "measured_at": None if number == 1 else stamp,
                         "received_at": None if number == 1 else stamp,
                         "awaiting_confirmation": False})
    return {
        "building": {"name": "인하대학교 · 미래관", "floors": 3,
                     "total_staff": 3, "available_staff": 2, "include_orange": False,
                     "office_floor": 1, "office_x": 10, "office_y": 78,
                     "office_access_node": "F1-N0", "meters_per_unit": 0.6,
                     "speed_mps": 1.0, "service_seconds": 45,
                     "warning_threshold": 80, "critical_threshold": 90,
                     "stale_minutes": 5},
        "bins": bins, "graph": {"nodes": nodes, "edges": edges},
        "map_images": {}, "logs": [], "readings": [], "last_plan": None,
        "device_key_hint": None, "revision": 1, "updated_at": stamp,
    }


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
    return json.loads(row[0])


def save_workspace(db, user_id: int, state: dict):
    state["revision"] = state.get("revision", 0) + 1
    state["updated_at"] = now()
    db.execute("UPDATE workspaces SET state_json=? WHERE user_id=?",
               (json.dumps(state, ensure_ascii=False, allow_nan=False), user_id))


def bin_status(bin: dict, config: dict) -> str:
    if bin["fill"] is None:
        return "offline"
    if bin.get("awaiting_confirmation"):
        return "pending"
    if bin["reading_source"] == "actual":
        measured = parse_time(bin["measured_at"])
        if datetime.now(timezone.utc) - measured > timedelta(minutes=config["stale_minutes"]):
            return "offline"
    if bin["fill"] >= config["critical_threshold"]:
        return "critical"
    if bin["fill"] >= config["warning_threshold"]:
        return "warning"
    return "normal"


def route_signature(state: dict) -> str:
    inputs = {"building": state["building"], "graph": state["graph"],
              "bins": [{k: b.get(k) for k in ["id", "floor", "x", "y", "access_node"]} |
                       {"status": bin_status(b, state["building"])} for b in state["bins"]]}
    return hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()


def public_workspace(state: dict, user: dict) -> dict:
    result = copy.deepcopy(state)
    for bin in result["bins"]:
        bin["status"] = bin_status(bin, result["building"])
    if result.get("last_plan"):
        result["last_plan"]["outdated"] = result["last_plan"]["signature"] != route_signature(state)
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
    office_floor: Optional[int] = Field(default=None, ge=1, le=10)
    office_x: Optional[float] = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    office_y: Optional[float] = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    office_access_node: Optional[str] = Field(default=None, max_length=50)
    meters_per_unit: Optional[float] = Field(default=None, ge=0.05, le=10, allow_inf_nan=False)
    speed_mps: Optional[float] = Field(default=None, ge=0.2, le=3, allow_inf_nan=False)
    service_seconds: Optional[int] = Field(default=None, ge=0, le=600)
    warning_threshold: Optional[int] = Field(default=None, ge=1, le=99)
    critical_threshold: Optional[int] = Field(default=None, ge=2, le=100)
    stale_minutes: Optional[int] = Field(default=None, ge=1, le=120)


def validate_config(state: dict):
    cfg = state["building"]
    if cfg["available_staff"] > cfg["total_staff"]:
        raise HTTPException(422, "수거 가능 인원은 전체 관리자 수를 넘을 수 없습니다.")
    if cfg["warning_threshold"] >= cfg["critical_threshold"]:
        raise HTTPException(422, "주의 기준은 수거 필요 기준보다 작아야 합니다.")
    if cfg["office_floor"] > cfg["floors"] or any(b["floor"] > cfg["floors"] for b in state["bins"]):
        raise HTTPException(422, "등록된 쓰레기통과 관리자실의 층을 먼저 변경해 주세요.")
    if any(n["floor"] > cfg["floors"] for n in state["graph"]["nodes"]):
        raise HTTPException(422, "해당 층의 통로를 먼저 삭제해 주세요.")
    node = next((n for n in state["graph"]["nodes"] if n["id"] == cfg["office_access_node"]), None)
    if node and node["floor"] != cfg["office_floor"]:
        raise HTTPException(422, "관리자실과 연결 통로는 같은 층이어야 합니다.")


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
    category: str = Field(default="혼합", min_length=1, max_length=20)
    device_type: Literal["demo", "real"] = "demo"
    fill: Optional[float] = Field(default=0, ge=0, le=100, allow_inf_nan=False)


class BinPatch(StrictModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=40)
    floor: Optional[int] = Field(default=None, ge=1, le=10)
    x: Optional[float] = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    y: Optional[float] = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    access_node: Optional[str] = Field(default=None, max_length=50)
    category: Optional[str] = Field(default=None, min_length=1, max_length=20)
    fill: Optional[float] = Field(default=None, ge=0, le=100, allow_inf_nan=False)


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
        if body.device_type == "real":
            bin.update(fill=None, reading_source="unconnected", measured_at=None, received_at=None)
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
        if "fill" in patch and bin["device_type"] == "real":
            raise HTTPException(422, "실물 장치는 센서 수신 또는 실물 시뮬레이션을 사용해 주세요.")
        bin.update(patch)
        if "fill" in patch:
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
    kind: Literal["corridor", "stairs", "elevator"] = "corridor"
    label: str = Field(default="통로", max_length=40)


class GraphEdge(StrictModel):
    id: str = Field(min_length=1, max_length=80)
    from_: str = Field(alias="from", max_length=50)
    to: str = Field(max_length=50)
    distance_m: Optional[float] = Field(default=None, gt=0, le=10000, allow_inf_nan=False)


class Graph(StrictModel):
    nodes: list[GraphNode] = Field(max_length=200)
    edges: list[GraphEdge] = Field(max_length=600)


def validate_graph(graph: dict, floors: int):
    nodes = {n["id"]: n for n in graph["nodes"]}
    if len(nodes) != len(graph["nodes"]):
        raise HTTPException(422, "통로 지점 번호가 중복됩니다.")
    if any(key == "OFFICE" or key.startswith("B-") for key in nodes):
        raise HTTPException(422, "통로 번호는 쓰레기통 또는 관리자실 번호와 달라야 합니다.")
    if any(n["floor"] > floors for n in nodes.values()):
        raise HTTPException(422, "건물에 없는 층의 통로입니다.")
    ids, pairs = set(), set()
    for edge in graph["edges"]:
        a, b = nodes.get(edge["from"]), nodes.get(edge["to"])
        if not a or not b or a["id"] == b["id"]:
            raise HTTPException(422, "연결할 통로 지점을 확인해 주세요.")
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
            distance = math.hypot(a["x"] - b["x"], a["y"] - b["y"]) * config["meters_per_unit"]
        else:
            distance = abs(a["floor"] - b["floor"]) * 12.0
        connect(a["id"], b["id"], max(distance, 0.01))
    points = [{"id": "OFFICE", "floor": config["office_floor"], "x": config["office_x"],
               "y": config["office_y"], "access_node": config["office_access_node"], "kind": "office"}] + state["bins"]
    for point in points:
        nodes[point["id"]] = dict(point)
        adjacency[point["id"]] = []
        access = nodes.get(point["access_node"])
        if access and access["floor"] == point["floor"]:
            distance = math.hypot(point["x"] - access["x"], point["y"] - access["y"]) * config["meters_per_unit"]
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


def calculate_plan(state: dict) -> dict:
    config = state["building"]
    selected = [b for b in state["bins"] if bin_status(b, config) == "critical" or
                (config["include_orange"] and bin_status(b, config) == "warning")]
    nodes, adjacency = build_graph(state)
    distances, predecessors = {}, {}
    for source in ["OFFICE"] + [b["id"] for b in selected]:
        distances[source], predecessors[source] = dijkstra(adjacency, source)
    unreachable = [b["id"] for b in selected if b["id"] not in distances["OFFICE"]]
    targets = [b["id"] for b in selected if b["id"] not in unreachable]
    workers = min(config["available_staff"], len(targets))
    assignments: list[list[str]] = [[] for _ in range(workers)]
    speed, service = config["speed_mps"], config["service_seconds"]

    def length(route):
        if not route:
            return 0.0
        sequence = ["OFFICE"] + route + ["OFFICE"]
        return sum(distances[a][b] for a, b in zip(sequence, sequence[1:]))

    def elapsed(route):
        return length(route) / speed + service * len(route)

    # Farthest-first insertion balances projected finishing time, including the return to the office.
    for target in sorted(targets, key=lambda t: (-distances["OFFICE"][t], t)) if workers else []:
        options = []
        for worker, route in enumerate(assignments):
            for position in range(len(route) + 1):
                candidate = route[:position] + [target] + route[position:]
                times = [elapsed(candidate) if i == worker else elapsed(r) for i, r in enumerate(assignments)]
                options.append((max(times), sum(times), worker, position))
        _, _, worker, position = min(options)
        assignments[worker].insert(position, target)

    # Route reversal (2-opt), followed by bounded cross-worker relocation.
    def improve(route):
        for _ in range(12):
            best, best_length = route, length(route)
            for i in range(len(route)):
                for j in range(i + 2, len(route) + 1):
                    candidate = route[:i] + list(reversed(route[i:j])) + route[j:]
                    candidate_length = length(candidate)
                    if candidate_length + 0.001 < best_length:
                        best, best_length = candidate, candidate_length
            if best is route:
                break
            route = best
        return route

    assignments = [improve(r) for r in assignments]
    for _ in range(10):
        old_score = (max((elapsed(r) for r in assignments), default=0), sum(elapsed(r) for r in assignments))
        best_score, best_assignment = old_score, None
        for i, route in enumerate(assignments):
            if len(route) < 2:
                continue
            for target in route:
                for j, other in enumerate(assignments):
                    if i == j:
                        continue
                    for position in range(len(other) + 1):
                        candidate = [r[:] for r in assignments]
                        candidate[i].remove(target)
                        candidate[j].insert(position, target)
                        score = (max(elapsed(r) for r in candidate), sum(elapsed(r) for r in candidate))
                        if score < best_score:
                            best_score, best_assignment = score, candidate
        if best_assignment is None:
            break
        assignments = [improve(r) for r in best_assignment]

    def path(a, b):
        route = [b]
        while route[-1] != a:
            route.append(predecessors[a][route[-1]])
        return list(reversed(route))

    routes = []
    for index, route in enumerate(assignments):
        if not route:
            continue
        sequence = ["OFFICE"] + route + ["OFFICE"]
        path_ids: list[str] = []
        for a, b in zip(sequence, sequence[1:]):
            leg = path(a, b)
            path_ids.extend(leg if not path_ids else leg[1:])
        routes.append({"worker": index + 1, "color": ROUTE_COLORS[index % len(ROUTE_COLORS)],
                       "bin_ids": route, "distance_m": round(length(route), 1),
                       "duration_seconds": round(elapsed(route)),
                       "path": [{"id": n, "floor": nodes[n]["floor"], "x": nodes[n]["x"], "y": nodes[n]["y"],
                                 "kind": nodes[n].get("kind", "bin")} for n in path_ids]})
    return {"created_at": now(), "signature": route_signature(state), "include_orange": config["include_orange"],
            "available_staff": config["available_staff"], "routes": routes,
            "target_ids": targets, "unreachable": unreachable,
            "unassigned": targets if workers == 0 else [],
            "total_distance_m": round(sum(r["distance_m"] for r in routes), 1),
            "makespan_seconds": max((r["duration_seconds"] for r in routes), default=0),
            "method": "dijkstra-balanced-insertion-2opt", "outdated": False}


class PlanRequest(StrictModel):
    available_staff: Optional[int] = Field(default=None, ge=0, le=12)
    include_orange: Optional[bool] = None


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
        if bin["fill"] is None or bin.get("awaiting_confirmation"):
            raise HTTPException(422, "수거할 상태값이 없거나 센서 확인을 기다리고 있습니다.")
        if bin["reading_source"] == "actual" and bin_status(bin, state["building"]) == "offline":
            raise HTTPException(422, "최신 센서값을 수신한 뒤 수거를 완료해 주세요.")
        state["logs"].insert(0, {"id": secrets.token_hex(6), "bin_id": bin_id, "floor": bin["floor"],
                                 "name": bin["name"], "fill_before": bin["fill"], "worker": body.worker,
                                 "actor": user["name"], "source": bin["reading_source"], "completed_at": now()})
        state["logs"] = state["logs"][:1000]
        if bin["reading_source"] == "actual":
            bin["awaiting_confirmation"] = True
            bin["collection_pending_at"] = now()
        else:
            bin.update(fill=0, measured_at=now(), received_at=now())
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
                bin.update(fill=values[body.scenario][index % 11], measured_at=now(), received_at=now(),
                           awaiting_confirmation=False)
                index += 1
        if state["last_plan"]:
            state["last_plan"] = calculate_plan(state)
        return result_for(db, user, state)


class Simulation(StrictModel):
    fill: Optional[float] = Field(default=None, ge=0, le=100, allow_inf_nan=False)


@app.post("/api/demo/real-simulation")
def real_simulation(body: Simulation, user=Depends(current_user)):
    with LOCK, database() as db:
        state = read_workspace(db, user["id"])
        bin = next((b for b in state["bins"] if b["device_type"] == "real"), None)
        if not bin:
            raise HTTPException(404, "실물 장치가 없습니다.")
        if body.fill is None:
            bin.update(fill=None, reading_source="unconnected", measured_at=None, received_at=None,
                       awaiting_confirmation=False)
        else:
            bin.update(fill=body.fill, reading_source="simulated", measured_at=now(), received_at=now(),
                       awaiting_confirmation=False)
        state["readings"].insert(0, {"bin_id": bin["id"], "fill": body.fill, "source": bin["reading_source"], "at": now()})
        state["readings"] = state["readings"][:200]
        return result_for(db, user, state)


@app.post("/api/demo/reset")
def reset_demo(user=Depends(current_user)):
    with LOCK, database() as db:
        old_state = read_workspace(db, user["id"])
        state = new_workspace()
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
    fill_percent: float = Field(ge=0, le=100, allow_inf_nan=False)
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
        measured = parse_time(body.measured_at) if body.measured_at else datetime.now(timezone.utc)
        if measured > datetime.now(timezone.utc) + timedelta(minutes=2):
            raise HTTPException(422, "측정 시각이 현재보다 너무 늦습니다.")
        if bin["reading_source"] == "actual" and bin["measured_at"] and measured <= parse_time(bin["measured_at"]):
            raise HTTPException(409, "이미 수신한 값보다 이전 측정값입니다.")
        still_pending = bool(bin.get("awaiting_confirmation") and bin.get("collection_pending_at") and
                             measured <= parse_time(bin["collection_pending_at"]))
        bin.update(fill=round(body.fill_percent, 1), measured_at=measured.isoformat(), received_at=now(),
                   reading_source="actual", awaiting_confirmation=still_pending)
        state["readings"].insert(0, {"bin_id": bin["id"], "fill": bin["fill"], "source": "actual", "at": now()})
        state["readings"] = state["readings"][:200]
        save_workspace(db, row["user_id"], state)
    return {"ok": True, "bin_id": body.bin_id, "fill_percent": bin["fill"], "status": bin_status(bin, state["building"])}


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
    worker: Optional[int] = Field(default=None, ge=1, le=12)
    actor: str = Field(min_length=1, max_length=40)
    source: Literal["actual", "simulated", "demo"]
    completed_at: str = Field(max_length=50)


class SavedReading(StrictModel):
    bin_id: str = Field(max_length=20)
    fill: Optional[float] = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    source: Literal["actual", "simulated", "demo", "unconnected"]
    at: str = Field(max_length=50)


@app.post("/api/restore")
def restore(body: RestoreRequest, user=Depends(current_user)):
    if len(json.dumps(body.model_dump())) > 35_000_000:
        raise HTTPException(422, "백업 파일은 35MB 이하로 선택해 주세요.")
    try:
        incoming = body.workspace
        config = ConfigPatch(**incoming["building"]).model_dump()
        if any(v is None for v in config.values()):
            raise ValueError("incomplete configuration")
        graph = Graph(**incoming["graph"]).model_dump(by_alias=True)
        if not 1 <= len(incoming["bins"]) <= 100:
            raise ValueError("invalid bin count")
        bins = []
        ids = set()
        for item in incoming["bins"]:
            clean = BinCreate(**{k: item[k] for k in BinCreate.model_fields}).model_dump()
            bin_id = item["id"]
            if not isinstance(bin_id, str) or not bin_id.startswith("B-") or not bin_id[2:].isdigit() or len(bin_id) > 12 or bin_id in ids:
                raise ValueError("invalid bin id")
            ids.add(bin_id)
            source = "demo" if clean["device_type"] == "demo" else "unconnected"
            if source == "unconnected":
                clean["fill"] = None
            bins.append(clean | {"id": bin_id, "reading_source": source,
                                 "measured_at": now() if source == "demo" else None,
                                 "received_at": now() if source == "demo" else None, "awaiting_confirmation": False})
        if sum(b["device_type"] == "real" for b in bins) != 1:
            raise ValueError("one real device required")
        state = new_workspace()
        state.update(building=config, graph=graph, bins=bins, map_images={}, logs=[], readings=[], last_plan=None)
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
