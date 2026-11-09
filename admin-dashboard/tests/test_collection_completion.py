import json

import pytest
from fastapi.testclient import TestClient

from server import app as backend


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(backend, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(backend, 'DB_PATH', tmp_path / 'collection.sqlite3')
    monkeypatch.setattr(backend, 'MAP_DIR', tmp_path / 'maps')
    # These tests exercise completion/assignments, not optimizer quality.
    monkeypatch.setattr(backend, 'SEARCH_ROUNDS', 35)
    monkeypatch.setattr(backend, 'SEARCH_SECONDS', 0.05)
    monkeypatch.setattr(backend, 'SEARCH_RESTARTS', 1)
    with TestClient(backend.app) as c:
        c.post('/api/auth/login', json={'email': backend.DEMO_EMAIL, 'password': backend.DEMO_PASSWORD})
        assert c.patch('/api/config', json={'cart_capacity': 0, 'max_work_minutes': 0}).status_code == 200
        assert c.post('/api/demo/scenario', json={'scenario': 'rush'}).status_code == 200
        response = c.post('/api/plan', json={'available_staff': 2, 'include_orange': True})
        assert response.status_code == 200 and len(response.json()['last_plan']['routes']) == 2
        yield c


def state(client, **kwargs):
    return client.get('/api/workspace', **kwargs).json()


def by_id(s, bin_id):
    return next(b for b in s['bins'] if b['id'] == bin_id)


def finish_worker(client, plan, worker, **kwargs):
    response = client.post(f'/api/collect/worker/{worker}', json={'plan_id': plan['id']}, **kwargs)
    assert response.status_code == 200, response.text
    return response.json()


def test_worker_completion_only_changes_assigned_bins_and_keeps_other_routes(client):
    before = state(client)
    plan = before['last_plan']
    route = plan['routes'][0]
    after = finish_worker(client, plan, route['worker'])
    assigned = set(route['bin_ids'])
    assert set(after['last_plan']['completed_bin_ids']) == assigned
    assert after['last_plan']['routes'] == plan['routes'] and not after['last_plan']['outdated']
    assert [r['worker'] for r in after['last_plan']['completed_workers']] == [route['worker']]
    assert len(after['logs']) == len(assigned)
    assert {log['bin_id'] for log in after['logs']} == assigned
    assert all(log['worker'] == route['worker'] for log in after['logs'])
    for bin in before['bins']:
        result = by_id(after, bin['id'])
        if bin['id'] not in assigned:
            assert result == bin
        else:
            assert result['collection_done']
            for compartment, fill in bin['compartments'].items():
                assert result['compartments'][compartment] == (0 if compartment in plan['empty'][bin['id']] else fill)
    repeated = finish_worker(client, plan, route['worker'])
    assert repeated['logs'] == after['logs'] and repeated['revision'] == after['revision']
    assert state(client)['last_plan']['completed_bin_ids'] == after['last_plan']['completed_bin_ids']


def test_individual_then_worker_completion_does_not_reassign_or_collect_twice(client):
    before = state(client)
    plan = before['last_plan']
    route = max(plan['routes'], key=lambda r: len(r['bin_ids']))
    bin_id = route['bin_ids'][0]
    body = {'worker': route['worker'], 'plan_id': plan['id'], 'version': by_id(before, bin_id)['collection_version']}
    response = client.post('/api/collect/' + bin_id, json=body)
    assert response.status_code == 200, response.text
    first = response.json()
    assert first['last_plan']['routes'] == plan['routes']
    assert first['last_plan']['completed_bin_ids'] == [bin_id]
    assert first['logs'][0]['worker'] == route['worker']
    after = finish_worker(client, plan, route['worker'])
    assert len(after['logs']) == len(route['bin_ids'])
    assert len({log['bin_id'] for log in after['logs']}) == len(after['logs'])
    again = client.post('/api/collect/' + bin_id, json=body)
    assert again.status_code == 200 and again.json()['logs'] == after['logs']


def test_all_workers_complete_then_explicit_new_plan_starts_new_round(client):
    plan = state(client)['last_plan']
    for route in plan['routes']:
        after = finish_worker(client, plan, route['worker'])
    assert set(after['last_plan']['completed_bin_ids']) == set(plan['target_ids'])
    assert len(after['last_plan']['completed_workers']) == len(plan['routes'])
    assert len(after['logs']) == len(plan['target_ids'])
    assert not after['last_plan']['outdated']
    new = client.post('/api/plan', json={}).json()
    assert new['last_plan']['id'] != plan['id'] and not new['last_plan']['routes']
    assert new['last_plan']['completed_bin_ids'] == []
    assert client.post('/api/collect/worker/1', json={'plan_id': plan['id']}).status_code == 409
    assert state(client)['logs'] == after['logs']


def test_stale_worker_completion_is_atomic_and_keeps_all_other_bins_unchanged(client):
    before = state(client)
    plan = before['last_plan']
    bin_id = plan['routes'][0]['bin_ids'][-1]
    assert client.patch('/api/bins/' + bin_id, json={'fills': dict.fromkeys(backend.COMPARTMENTS, 0)}).status_code == 200
    changed = state(client)
    assert changed['last_plan']['outdated']
    response = client.post(f'/api/collect/worker/{plan["routes"][0]["worker"]}', json={'plan_id': plan['id']})
    assert response.status_code == 409
    after = state(client)
    assert after['bins'] == changed['bins'] and after['logs'] == []
    assert not after['last_plan'].get('completed_bin_ids')


def test_stale_individual_reading_cannot_be_completed_and_empty_bin_is_not_logged(client):
    before = state(client)
    bin_id = before['last_plan']['routes'][0]['bin_ids'][0]
    old_version = by_id(before, bin_id)['collection_version']
    client.patch('/api/bins/' + bin_id, json={'fills': dict.fromkeys(backend.COMPARTMENTS, 0)})
    assert client.post('/api/collect/' + bin_id, json={'version': old_version}).status_code == 409
    assert client.post('/api/collect/' + bin_id, json={}).status_code == 422
    assert state(client)['logs'] == []


def test_individual_completion_is_idempotent_and_allows_a_later_new_reading(client):
    bin_id = 'B-002'
    changed = client.patch('/api/bins/' + bin_id, json={'fills': {'CAN': 10, 'PET': 20, 'GLASS': 30, 'OTHER': 40}}).json()
    body = {'version': by_id(changed, bin_id)['collection_version']}
    first = client.post('/api/collect/' + bin_id, json=body).json()
    assert by_id(first, bin_id)['collection_done'] and len(first['logs']) == 1
    assert first['last_plan']['outdated']  # completing a bin does not silently revive an old plan
    assert client.post('/api/collect/' + bin_id, json=body).json()['logs'] == first['logs']
    changed = client.patch('/api/bins/' + bin_id, json={'fills': {'PET': 94}}).json()
    assert not by_id(changed, bin_id)['collection_done']
    second = client.post('/api/collect/' + bin_id, json={'version': by_id(changed, bin_id)['collection_version']}).json()
    assert len(second['logs']) == 2 and by_id(second, bin_id)['collection_done']


def test_actual_sensor_batch_keeps_readings_pending_and_confirmation_does_not_reshuffle(client):
    key = client.post('/api/device/key', json={}).json()['key']
    headers = {'X-Device-Key': key}
    client.post('/api/device/readings', headers=headers, json={'bin_id': 'B-001', 'fills': {'CAN': 95, 'PET': 10}})
    before = client.post('/api/plan', json={}).json()
    plan = before['last_plan']
    route = next(r for r in plan['routes'] if 'B-001' in r['bin_ids'])
    after = finish_worker(client, plan, route['worker'])
    real = by_id(after, 'B-001')
    assert real['awaiting_confirmation'] and real['compartments']['CAN'] == 95
    assert real['pending_compartments'] == ['CAN'] and real['status'] == 'pending'
    assert next(log for log in after['logs'] if log['bin_id'] == 'B-001')['worker'] == route['worker']
    assert client.post('/api/device/readings', headers=headers, json={'bin_id': 'B-001', 'compartment': 'CAN', 'fill_percent': 2}).status_code == 200
    confirmed = state(client)
    assert not by_id(confirmed, 'B-001')['awaiting_confirmation']
    assert not confirmed['last_plan']['outdated'] and confirmed['last_plan']['routes'] == plan['routes']
    assert finish_worker(client, plan, route['worker'])['logs'] == after['logs']


def test_worker_completion_is_scoped_to_building_and_account(client):
    before = state(client)
    plan = before['last_plan']
    other = client.post('/api/buildings', json={'name': '다른 건물', 'template': 'basic'}).json()
    assert client.post('/api/collect/worker/1', json={'plan_id': plan['id']}).status_code == 409
    assert other['workspace_id'] != before['workspace_id'] and state(client)['logs'] == []
    first_scope = {'X-Building-ID': str(before['workspace_id'])}
    assert state(client, headers=first_scope)['logs'] == []
    client.post('/api/auth/register', json={'email': 'other@reloop.local', 'password': 'Other1234!', 'name': '다른 관리자'})
    assert client.post('/api/collect/worker/1', headers=first_scope, json={'plan_id': plan['id']}).status_code == 404


def test_old_saved_plan_can_be_completed_with_a_stable_upgraded_id(client):
    with backend.database() as db:
        row = db.execute('SELECT id,state_json FROM buildings WHERE deleted_at IS NULL ORDER BY id LIMIT 1').fetchone()
        stored = json.loads(row['state_json'])
        for key in ['id', 'completed_bin_ids', 'completed_workers']:
            stored['last_plan'].pop(key, None)
        db.execute('UPDATE buildings SET state_json=? WHERE id=?', (json.dumps(stored), row['id']))
    before = state(client)
    assert state(client)['last_plan']['id'] == before['last_plan']['id']
    after = finish_worker(client, before['last_plan'], before['last_plan']['routes'][0]['worker'])
    assert after['last_plan']['id'] == before['last_plan']['id'] and not after['last_plan']['outdated']


def test_only_explicit_plan_request_recalculates_after_condition_or_scenario_changes(client):
    before = state(client)['last_plan']
    changed = client.patch('/api/config', json={'include_orange': False}).json()['last_plan']
    assert changed['id'] == before['id'] and changed['routes'] == before['routes'] and changed['outdated']
    changed = client.post('/api/demo/scenario', json={'scenario': 'calm'}).json()['last_plan']
    assert changed['id'] == before['id'] and changed['routes'] == before['routes'] and changed['outdated']
    recalculated = client.post('/api/plan', json={}).json()['last_plan']
    assert recalculated['id'] != before['id'] and recalculated['routes'] == []


@pytest.mark.parametrize('worker', [0, 12, 999])
def test_worker_without_assignment_is_rejected_without_any_records(client, worker):
    before = state(client)
    assert client.post(f'/api/collect/worker/{worker}', json={'plan_id': before['last_plan']['id']}).status_code == 422
    assert state(client)['logs'] == []
