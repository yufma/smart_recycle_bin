import copy
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
    assert len(both["routes"]) == 3
    assert all(r["path"][0]["id"] == r["path"][-1]["id"] == "OFFICE" for r in both["routes"])


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
