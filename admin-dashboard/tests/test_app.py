import copy
import itertools
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from server import app as backend


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(backend, "DATA_DIR", tmp_path)
    monkeypatch.setattr(backend, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(backend, "MAP_DIR", tmp_path / "maps")
    with TestClient(backend.app) as c:
        response = c.post("/api/auth/login", json={"email": backend.DEMO_EMAIL, "password": backend.DEMO_PASSWORD})
        assert response.status_code == 200
        yield c


def workspace(client):
    response = client.get("/api/workspace")
    assert response.status_code == 200
    return response.json()


def bin_by_id(state, id):
    return next(b for b in state["bins"] if b["id"] == id)


def test_seed_has_one_unconnected_real_device_and_eleven_demo_bins(client):
    state = workspace(client)
    assert len(state["bins"]) == 12
    real = [b for b in state["bins"] if b["device_type"] == "real"]
    assert len(real) == 1
    assert real[0]["fill"] is None and real[0]["status"] == "offline"
    assert state["building"]["office_floor"] == 1


@pytest.mark.parametrize("fill,status", [(0, "normal"), (79.9, "normal"), (80, "warning"), (89.9, "warning"), (90, "critical"), (100, "critical")])
def test_status_boundaries(client, fill, status):
    result = client.patch("/api/bins/B-002", json={"fill": fill})
    assert result.status_code == 200
    assert bin_by_id(result.json(), "B-002")["status"] == status


def test_warning_option_changes_targets_and_assigns_each_exactly_once(client):
    red = client.post("/api/plan", json={"include_orange": False, "available_staff": 1}).json()["last_plan"]
    both = client.post("/api/plan", json={"include_orange": True, "available_staff": 3}).json()["last_plan"]
    assert set(red["target_ids"]) == {"B-002", "B-005", "B-010"}
    assert set(both["target_ids"]) == {"B-002", "B-004", "B-005", "B-007", "B-010", "B-012"}
    assigned = [id for r in both["routes"] for id in r["bin_ids"]]
    assert len(assigned) == len(set(assigned)) == 6
    assert set(assigned) == set(both["target_ids"])
    assert len(both["routes"]) == 3 and both["end"] == "DEPOT"
    assert all(r["path"][0]["id"] == "OFFICE" and r["path"][-1]["id"] == "DEPOT" for r in both["routes"])


def test_multi_floor_paths_follow_only_connected_edges(client):
    state = client.post("/api/plan", json={"include_orange": True}).json()
    nodes, adjacency = backend.build_graph(state)
    changes = 0
    for route in state["last_plan"]["routes"]:
        total = 0
        for a, b in zip(route["path"], route["path"][1:]):
            weights = dict(adjacency[a["id"]])
            assert b["id"] in weights
            total += weights[b["id"]]
            if a["floor"] != b["floor"]:
                assert a["kind"] == b["kind"] == "stairs"
                changes += 1
        assert round(total, 1) == route["distance_m"]
    assert changes > 0


def test_more_workers_reduce_finish_time_for_same_demo_targets(client):
    client.post("/api/demo/scenario", json={"scenario": "rush"})
    one = client.post("/api/plan", json={"include_orange": True, "available_staff": 1}).json()["last_plan"]
    three = client.post("/api/plan", json={"include_orange": True, "available_staff": 3}).json()["last_plan"]
    assert one["target_ids"] == three["target_ids"]
    assert three["makespan_seconds"] < one["makespan_seconds"]


def test_travel_times_price_stairs_by_direction_and_the_lift_wait_once(client):
    state = client.post("/api/demo/reset", json={"template": "large"}).json()
    b = state["building"]
    nodes, arcs = backend.travel_graph(state)
    assert backend.fastest_paths(arcs, "F1-WS")[0]["F3-WS"] == pytest.approx(2 * b["stairs_up_seconds"])
    assert backend.fastest_paths(arcs, "F3-WS")[0]["F1-WS"] == pytest.approx(2 * b["stairs_down_seconds"])
    ride = backend.fastest_paths(arcs, "F1-EL")[0]["F5-EL"]
    assert ride == pytest.approx(b["elevator_wait_seconds"] + 4 * b["elevator_floor_seconds"])
    # walking past the lift door (north corridor -> lift hall -> south corridor) costs walking only
    walk = backend.fastest_paths(arcs, "F1-N2")[0]["F1-S2"]
    assert walk == pytest.approx(40 * b["meters_per_unit"] / b["speed_mps"])
    # with a cart the stairs are closed: going up two floors means the lift
    client.patch("/api/config", json={"use_cart": True})
    nodes, arcs = backend.travel_graph(workspace(client))
    assert backend.fastest_paths(arcs, "F1-WS")[0]["F3-WS"] > 2 * b["elevator_wait_seconds"] / 2
    plan = client.post("/api/plan", json={"include_orange": True}).json()["last_plan"]
    assert not plan["unreachable"]
    assert all(p["kind"] != "stairs" or q["floor"] == p["floor"] for r in plan["routes"] for p, q in zip(r["path"], r["path"][1:]))


def test_cart_without_a_lift_cannot_reach_upper_floors(client):
    client.patch("/api/config", json={"use_cart": True})
    plan = client.post("/api/plan", json={}).json()["last_plan"]
    assert set(plan["unreachable"]) == {"B-005", "B-010"}
    assert [id for r in plan["routes"] for id in r["bin_ids"]] == ["B-002"]


def test_cart_capacity_adds_unloading_trips(client):
    one = client.post("/api/plan", json={"include_orange": True, "available_staff": 1}).json()["last_plan"]
    client.patch("/api/config", json={"cart_capacity": 1})
    tight = client.post("/api/plan", json={}).json()["last_plan"]
    route = tight["routes"][0]
    assert route["drops"] == len(route["bin_ids"]) == 6
    assert route["sequence"] == [x for id in route["bin_ids"] for x in (id, "DEPOT")]
    assert tight["makespan_seconds"] > one["makespan_seconds"]
    client.patch("/api/config", json={"cart_capacity": 0})
    free = client.post("/api/plan", json={}).json()["last_plan"]
    assert free["routes"][0]["drops"] == 1
    assert client.patch("/api/config", json={"cart_capacity": 0.5}).status_code == 422
    assert client.patch("/api/config", json={"depot_node": "NOPE"}).status_code == 422


def brute_force(state, targets, workers):
    """Both presets by exhaustive search: every split of the targets between workers, every visiting
    order and every choice of unloading stops, from the server's travel times."""
    b = state["building"]
    nodes, arcs = backend.travel_graph(state)
    end = "DEPOT" if "DEPOT" in nodes else "OFFICE"
    times = {s: backend.fastest_paths(arcs, s)[0] for s in ["OFFICE", end] + targets}
    load = {x["id"]: x["fill"] / 100 for x in state["bins"] if x["id"] in targets}
    capacity = b["cart_capacity"] or float("inf")

    def trip(start, stops):
        legs = [start] + list(stops) + [end]
        return sum(times[x][y] for x, y in zip(legs, legs[1:])) + b["service_seconds"] * len(stops) + b["unload_seconds"]

    best_route = {}
    for size in range(1, len(targets) + 1):
        for group in itertools.combinations(targets, size):
            options = []
            for order in itertools.permutations(group):
                for cuts in itertools.product([False, True], repeat=size - 1):
                    trips, current = [], [order[0]]
                    for stop, cut in zip(order[1:], cuts):
                        if cut:
                            trips.append(current)
                            current = []
                        current.append(stop)
                    trips.append(current)
                    if all(sum(load[t] for t in t_) <= capacity + 1e-9 for t_ in trips):
                        options.append(sum(trip("OFFICE" if i == 0 else end, t_) for i, t_ in enumerate(trips)))
            best_route[frozenset(group)] = min(options)
    limit = b["max_work_minutes"] * 60 or float("inf")
    fastest = lean = None
    for owner in itertools.product(range(workers), repeat=len(targets)):
        groups = [frozenset(t for t, o in zip(targets, owner) if o == w) for w in range(workers)]
        spans = [best_route[g] for g in groups if g]
        fast_value = (round(max(spans), 6), round(sum(spans), 6))
        lean_value = (round(max(0.0, max(spans) - limit), 6), len(spans), round(sum(spans), 6))
        fastest = fast_value if fastest is None or fast_value < fastest else fastest
        lean = lean_value if lean is None or lean_value < lean else lean
    return fastest, lean


def test_presets_match_exhaustive_search(client):
    state = client.post("/api/plan", json={"include_orange": True, "available_staff": 3, "route_mode": "fastest"}).json()
    fast = state["last_plan"]
    assert state["building"]["route_mode"] == fast["mode"] == "fastest"
    (span, total), (overrun, used, lean_total) = brute_force(state, fast["target_ids"], 3)
    assert fast["makespan_seconds"] == round(span)
    assert fast["total_seconds"] == pytest.approx(total, abs=len(fast["routes"]))
    lean = client.post("/api/plan", json={"route_mode": "lean"}).json()["last_plan"]
    assert lean["mode"] == "lean" and overrun == 0
    assert len(lean["routes"]) == used and lean["total_seconds"] == pytest.approx(lean_total, abs=used)
    assert all(not r["over_limit"] and r["duration_seconds"] <= 20 * 60 for r in lean["routes"])
    assert fast["comparison"] == lean["comparison"]
    assert fast["makespan_seconds"] <= lean["makespan_seconds"] and len(lean["routes"]) <= len(fast["routes"])
    for plan in (fast, lean):
        assigned = [id for r in plan["routes"] for id in r["bin_ids"]]
        assert sorted(assigned) == sorted(plan["target_ids"])


def test_many_stops_and_input_validation(client):
    client.post("/api/demo/reset", json={"template": "large"})
    client.post("/api/demo/scenario", json={"scenario": "rush"})
    plan = client.post("/api/plan", json={"include_orange": True, "available_staff": 5, "route_mode": "fastest"}).json()["last_plan"]
    assert len(plan["target_ids"]) == 29
    fast, lean = plan["comparison"]["fastest"], plan["comparison"]["lean"]
    assert fast["makespan_seconds"] <= lean["makespan_seconds"] and lean["workers"] <= fast["workers"]
    assigned = [id for r in plan["routes"] for id in r["bin_ids"]]
    assert sorted(assigned) == sorted(plan["target_ids"])
    assert client.post("/api/plan", json={"route_mode": "balanced"}).status_code == 422
    # workspaces saved with retired route modes read back with the default preset
    with backend.database() as db:
        user_id = db.execute("SELECT id FROM users WHERE email=?", (backend.DEMO_EMAIL,)).fetchone()[0]
        state = backend.read_workspace(db, user_id)
        state["building"].update(route_mode="shortest", route_slack_percent=10)
        del state["building"]["stairs_up_seconds"]
        backend.save_workspace(db, user_id, state)
    building = workspace(client)["building"]
    assert building["route_mode"] == "fastest" and "route_slack_percent" not in building
    assert building["stairs_up_seconds"] == backend.ROUTE_DEFAULTS["stairs_up_seconds"]
    assert client.post("/api/restore", json=client.get("/api/backup").json()).status_code == 200


def test_large_sample_building_has_floor_plans_several_cores_and_both_presets(client):
    state = client.post("/api/demo/reset", json={"template": "large"}).json()
    assert state["building"]["floors"] == 5 and len(state["bins"]) == 30
    assert sum(b["device_type"] == "real" for b in state["bins"]) == 1
    backend.validate_graph(state["graph"], 5)
    for b in state["bins"]:
        backend.validate_bin(state, b)
    assert sorted(state["map_images"]) == ["1", "2", "3", "4", "5"]
    assert client.get("/api/floorplan/3").status_code == 200
    fast = client.post("/api/plan", json={"include_orange": True, "route_mode": "fastest"}).json()["last_plan"]
    lean = client.post("/api/plan", json={"route_mode": "lean"}).json()["last_plan"]
    assert not fast["unreachable"] and len(fast["target_ids"]) == 13 and fast["end"] == "DEPOT"
    assert 1 <= len(lean["routes"]) <= len(fast["routes"]) <= 3
    cores = {p["id"].split("-")[1] for r in fast["routes"] + lean["routes"] for p in r["path"]
             if p["kind"] in ("stairs", "elevator")}
    assert len(cores) >= 2
    graph = workspace(client)["graph"]
    graph["nodes"] = [n for n in graph["nodes"] if n["id"] != "F1-S4"]
    graph["edges"] = [e for e in graph["edges"] if "F1-S4" not in (e["from"], e["to"])]
    assert client.put("/api/graph", json=graph).json()["building"]["depot_node"] == ""
    saved = client.get("/api/backup").json()
    assert len(saved["images"]) == 5
    assert client.post("/api/restore", json=saved).status_code == 200
    assert client.post("/api/demo/reset", json={}).json()["building"]["floors"] == 3


def test_zero_staff_no_targets_and_unreachable_are_explicit(client):
    zero = client.post("/api/plan", json={"available_staff": 0}).json()["last_plan"]
    assert not zero["routes"] and len(zero["unassigned"]) == 3
    graph = workspace(client)["graph"]
    graph["edges"] = [e for e in graph["edges"] if e["id"] != "STAIR-3"]
    assert client.put("/api/graph", json=graph).status_code == 200
    plan = client.post("/api/plan", json={"available_staff": 2}).json()["last_plan"]
    assert plan["unreachable"] == ["B-010"]
    assert "B-010" not in [id for r in plan["routes"] for id in r["bin_ids"]]
    client.post("/api/demo/scenario", json={"scenario": "calm"})
    empty = client.post("/api/plan", json={}).json()["last_plan"]
    assert not empty["routes"] and empty["makespan_seconds"] == 0


def test_data_survives_logout_new_session_and_db_reinitialization(client):
    client.patch("/api/config", json={"name": "지속성 테스트", "office_x": 15})
    client.post("/api/plan", json={"include_orange": True, "available_staff": 3})
    client.post("/api/auth/logout", json={})
    assert client.get("/api/workspace").status_code == 401
    backend.init_db()
    client.post("/api/auth/login", json={"email": backend.DEMO_EMAIL, "password": backend.DEMO_PASSWORD})
    state = workspace(client)
    assert state["building"]["name"] == "지속성 테스트"
    assert state["building"]["office_x"] == 15
    assert state["building"]["include_orange"] is True
    assert len(state["last_plan"]["routes"]) == 3


def test_registration_isolates_workspace_and_stores_no_plaintext_password(client):
    client.patch("/api/bins/B-002", json={"fill": 10})
    assert client.post("/api/auth/register", json={"name": "다른 관리자", "email": "other@example.com", "password": "NewPass123"}).status_code == 201
    assert bin_by_id(workspace(client), "B-002")["fill"] == 94
    assert client.post("/api/auth/register", json={"name": "중복", "email": "OTHER@example.com", "password": "NewPass123"}).status_code == 409
    with backend.database() as db:
        row = db.execute("SELECT password_hash FROM users WHERE email='other@example.com'").fetchone()
        assert row[0] != "NewPass123" and len(row[0]) == 64


def test_sensor_auth_validation_stale_values_and_collection_confirmation(client):
    assert client.post("/api/device/readings", json={"bin_id": "B-001", "fill_percent": 96}).status_code == 401
    key = client.post("/api/device/key", json={}).json()["key"]
    headers = {"X-Device-Key": key}
    assert client.post("/api/device/readings", headers=headers, json={"bin_id": "B-002", "fill_percent": 96}).status_code == 422
    assert client.post("/api/device/readings", headers=headers, json={"bin_id": "B-001", "fill_percent": 101}).status_code == 422
    old = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    assert client.post("/api/device/readings", headers=headers, json={"bin_id": "B-001", "fill_percent": 96, "measured_at": old}).status_code == 200
    assert bin_by_id(workspace(client), "B-001")["status"] == "offline"
    assert "B-001" not in client.post("/api/plan", json={}).json()["last_plan"]["target_ids"]
    assert client.post("/api/device/readings", headers=headers, json={"bin_id": "B-001", "fill_percent": 96}).status_code == 200
    assert client.post("/api/device/readings", headers=headers, json={"bin_id": "B-001", "fill_percent": 15, "measured_at": old}).status_code == 409
    result = client.post("/api/collect/B-001", json={"worker": 1}).json()
    assert bin_by_id(result, "B-001")["fill"] == 96
    assert bin_by_id(result, "B-001")["status"] == "pending"
    client.post("/api/device/readings", headers=headers, json={"bin_id": "B-001", "fill_percent": 5})
    assert bin_by_id(workspace(client), "B-001")["status"] == "normal"
    client.post("/api/device/key", json={})
    assert client.post("/api/device/readings", headers=headers, json={"bin_id": "B-001", "fill_percent": 10}).status_code == 401


def test_simulation_labeled_and_real_reading_replaces_it(client):
    sim = client.post("/api/demo/real-simulation", json={"fill": 94}).json()
    assert bin_by_id(sim, "B-001")["reading_source"] == "simulated"
    key = client.post("/api/device/key", json={}).json()["key"]
    client.post("/api/device/readings", headers={"X-Device-Key": key}, json={"bin_id": "B-001", "fill_percent": 85})
    assert bin_by_id(workspace(client), "B-001")["reading_source"] == "actual"


def test_backup_restore_includes_logs_and_validates_before_mutation(client):
    client.post("/api/collect/B-002", json={"worker": 1})
    client.patch("/api/config", json={"name": "백업 건물"})
    saved = client.get("/api/backup").json()
    assert "device_key_hint" not in saved["workspace"]
    client.post("/api/demo/reset", json={})
    result = client.post("/api/restore", json=saved)
    assert result.status_code == 200
    assert result.json()["building"]["name"] == "백업 건물"
    assert result.json()["logs"][0]["bin_id"] == "B-002"
    older = copy.deepcopy(saved)
    for key in ("route_mode", "cart_capacity", "depot_node", "max_work_minutes"):
        del older["workspace"]["building"][key]
    restored = client.post("/api/restore", json=older).json()["building"]
    assert restored["route_mode"] == "fastest" and restored["cart_capacity"] == 4 and restored["depot_node"] == ""
    invalid = copy.deepcopy(saved)
    invalid["workspace"]["building"]["critical_threshold"] = 10
    assert client.post("/api/restore", json=invalid).status_code == 422
    assert workspace(client)["building"]["critical_threshold"] == 90


def test_config_graph_validation_and_changed_inputs_mark_plan_outdated(client):
    assert client.patch("/api/config", json={"available_staff": 4}).status_code == 422
    assert client.patch("/api/config", json={"warning_threshold": 95}).status_code == 422
    client.post("/api/plan", json={})
    assert not workspace(client)["last_plan"]["outdated"]
    client.patch("/api/bins/B-003", json={"fill": 95})
    assert workspace(client)["last_plan"]["outdated"]
    graph = workspace(client)["graph"]
    graph["edges"].append({"id": "invalid-crossfloor", "from": "F1-N0", "to": "F3-N0", "distance_m": 1})
    assert client.put("/api/graph", json=graph).status_code == 422


def test_origin_protection(client):
    assert client.post("/api/plan", headers={"Origin": "https://untrusted.example"}, json={}).status_code == 403
