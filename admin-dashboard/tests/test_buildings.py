import base64
import hashlib
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from server import app as backend

PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l6UAAAAASUVORK5CYII='


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(backend, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(backend, 'DB_PATH', tmp_path / 'buildings.sqlite3')
    monkeypatch.setattr(backend, 'MAP_DIR', tmp_path / 'maps')
    with TestClient(backend.app) as c:
        assert c.post('/api/auth/login', json={'email': backend.DEMO_EMAIL, 'password': backend.DEMO_PASSWORD}).status_code == 200
        yield c


def scope(building_id):
    return {'X-Building-ID': str(building_id)}


def add(client, name='다른 건물', template='basic', **extra):
    response = client.post('/api/buildings', json={'name': name, 'template': template, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def test_create_switch_and_rename_keep_independent_workspaces(client):
    first = client.get('/api/workspace').json()
    second = add(client)
    a, b = first['workspace_id'], second['workspace_id']
    assert a != b and len(second['buildings']) == 2
    assert client.patch('/api/config', json={'available_staff': 0}, headers=scope(a)).status_code == 200
    assert client.get('/api/workspace', headers=scope(a)).json()['building']['available_staff'] == 0
    assert client.get('/api/workspace', headers=scope(b)).json()['building']['available_staff'] == 2
    renamed = client.patch(f'/api/buildings/{a}', json={'name': '미래관 원본'}, headers=scope(b)).json()
    assert renamed['workspace_id'] == b and renamed['building']['name'] == '다른 건물'
    assert next(item for item in renamed['buildings'] if item['id'] == a)['name'] == '미래관 원본'
    selected = client.post(f'/api/buildings/{a}/select', json={}).json()
    assert selected['workspace_id'] == a
    assert client.get('/api/buildings').json()['active_id'] == a


def test_maps_backups_and_resets_are_scoped_to_the_requested_building(client):
    a = client.get('/api/workspace').json()['workspace_id']
    upload = client.put('/api/floorplan/1', json={'data_url': 'data:image/png;base64,' + PNG}, headers=scope(a))
    assert upload.status_code == 200
    b = add(client)['workspace_id']
    assert client.get(f'/api/floorplan/1?building_id={a}').content == base64.b64decode(PNG)
    assert client.get(f'/api/floorplan/1?building_id={b}').status_code == 404
    backup = client.get(f'/api/backup?building_id={a}').json()
    assert backup['images'] == {'1': PNG} and '_workspace_id' not in backup['workspace']
    assert client.get(f'/api/backup?building_id={b}').json()['images'] == {}
    assert client.post('/api/demo/reset', json={'template': 'basic'}, headers=scope(b)).status_code == 200
    assert client.get(f'/api/floorplan/1?building_id={a}').status_code == 200


def test_sensor_key_updates_its_building_even_after_switching(client):
    a = client.get('/api/workspace').json()['workspace_id']
    key = client.post('/api/device/key', json={}, headers=scope(a)).json()['key']
    b = add(client)['workspace_id']
    response = client.post('/api/device/readings', headers={'X-Device-Key': key},
                           json={'bin_id': 'B-001', 'compartment': 'PET', 'fill_percent': 94})
    assert response.status_code == 200
    assert client.get('/api/workspace', headers=scope(a)).json()['bins'][0]['fill'] == 94
    assert client.get('/api/workspace', headers=scope(b)).json()['bins'][0]['fill'] is None
    assert client.get('/api/workspace').json()['workspace_id'] == b


def test_collection_history_does_not_move_between_buildings(client):
    a = client.get('/api/workspace').json()['workspace_id']
    assert client.post('/api/collect/B-002', json={}, headers=scope(a)).status_code == 200
    b = add(client)['workspace_id']
    assert client.get('/api/workspace', headers=scope(a)).json()['logs'][0]['bin_id'] == 'B-002'
    assert client.get('/api/workspace', headers=scope(b)).json()['logs'] == []
    assert client.get('/api/workspace', headers=scope(a)).json()['bins'][1]['fill'] < 90
    assert client.get('/api/workspace', headers=scope(b)).json()['bins'][1]['fill'] == 94


def test_delete_inactive_and_restore_preserve_data_and_revoke_old_sensor_key(client):
    a = client.get('/api/workspace').json()['workspace_id']
    key = client.post('/api/device/key', json={}, headers=scope(a)).json()['key']
    client.post('/api/collect/B-002', json={}, headers=scope(a))
    b = add(client)['workspace_id']
    deleted = client.delete(f'/api/buildings/{a}', headers=scope(b)).json()
    assert deleted['workspace_id'] == b
    assert [item['id'] for item in deleted['buildings']] == [b]
    assert [item['id'] for item in deleted['deleted_buildings']] == [a]
    assert client.get('/api/workspace', headers=scope(a)).status_code == 404
    assert client.post(f'/api/buildings/{a}/select', json={}).status_code == 404
    assert client.post('/api/device/readings', headers={'X-Device-Key': key},
                       json={'bin_id': 'B-001', 'compartment': 'PET', 'fill_percent': 10}).status_code == 401
    restored = client.post(f'/api/buildings/{a}/restore', json={}).json()
    assert restored['workspace_id'] == a and len(restored['logs']) == 1
    assert restored['device_key_hint'] is None
    assert len(restored['buildings']) == 2


def test_deleting_the_last_building_keeps_an_empty_account_and_allows_recovery(client):
    a = client.get('/api/workspace').json()['workspace_id']
    empty = client.delete(f'/api/buildings/{a}').json()
    assert empty['workspace_id'] is None and empty['building'] is None and empty['buildings'] == []
    backend.init_db()  # Restart must not recreate a deleted default building.
    assert client.get('/api/workspace').json()['building'] is None
    assert client.patch('/api/config', json={'name': '덮어쓰기'}).status_code == 409
    restored = client.post(f'/api/buildings/{a}/restore', json={}).json()
    assert restored['workspace_id'] == a and len(restored['bins']) == 12


def test_empty_account_can_add_a_new_building(client):
    a = client.get('/api/workspace').json()['workspace_id']
    client.delete(f'/api/buildings/{a}')
    result = add(client, '새 정석학술정보관', 'empty', floors=6)
    assert result['building']['floors'] == 6 and len(result['bins']) == 1
    assert result['bins'][0]['fill'] is None
    assert result['deleted_buildings'][0]['id'] == a


def test_inha_template_adds_real_map_separately_from_miraegwan(client):
    a = client.get('/api/workspace').json()['workspace_id']
    campus = add(client, '인하대학교 용현캠퍼스', 'inha')
    b = campus['workspace_id']
    assert campus['building']['floors'] == 1 and len(campus['graph']['nodes']) == 164
    assert len(campus['bins']) == 1 and campus['bins'][0]['fill'] is None
    assert client.get(f'/api/floorplan/1?building_id={b}').status_code == 200
    original = client.get('/api/workspace', headers=scope(a)).json()
    assert original['building']['floors'] == 3 and len(original['bins']) == 12 and not original['map_images']


@pytest.mark.parametrize('operation', ['select', 'rename', 'delete', 'restore', 'workspace', 'map', 'backup'])
def test_other_accounts_cannot_read_or_change_a_building(client, operation):
    foreign_id = client.get('/api/workspace').json()['workspace_id']
    assert client.post('/api/auth/register', json={'email': 'other@reloop.local', 'password': 'Another123!', 'name': '다른 관리자'}).status_code == 201
    if operation == 'select':
        response = client.post(f'/api/buildings/{foreign_id}/select', json={})
    elif operation == 'rename':
        response = client.patch(f'/api/buildings/{foreign_id}', json={'name': '이름 탈취'})
    elif operation == 'delete':
        response = client.delete(f'/api/buildings/{foreign_id}')
    elif operation == 'restore':
        response = client.post(f'/api/buildings/{foreign_id}/restore', json={})
    elif operation == 'workspace':
        response = client.get('/api/workspace', headers=scope(foreign_id))
    else:
        response = client.get(f'/api/{"floorplan/1" if operation == "map" else "backup"}?building_id={foreign_id}')
    assert response.status_code == 404


def test_legacy_single_workspace_migrates_once_without_changing_state_or_key(tmp_path, monkeypatch):
    monkeypatch.setattr(backend, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(backend, 'DB_PATH', tmp_path / 'legacy.sqlite3')
    monkeypatch.setattr(backend, 'MAP_DIR', tmp_path / 'maps')
    state = backend.new_workspace()
    state['building']['name'] = '복구한 미래관'
    state['map_images'] = {'1': 'preserved.png'}
    (tmp_path / 'maps').mkdir()
    (tmp_path / 'maps' / 'preserved.png').write_bytes(base64.b64decode(PNG))
    serialized = json.dumps(state, ensure_ascii=False)
    salt = '00' * 16
    key_hash = hashlib.sha256(b'legacy-sensor-key').hexdigest()
    with sqlite3.connect(backend.DB_PATH) as db:
        db.executescript('CREATE TABLE users(id INTEGER PRIMARY KEY,email TEXT UNIQUE,name TEXT,salt TEXT,password_hash TEXT,created_at TEXT); '
                         'CREATE TABLE workspaces(user_id INTEGER PRIMARY KEY,state_json TEXT,device_key_hash TEXT UNIQUE);')
        db.execute('INSERT INTO users VALUES(1,?,?,?,?,?)', (backend.DEMO_EMAIL, '기존 관리자', salt, backend.password_hash(backend.DEMO_PASSWORD, salt), backend.now()))
        db.execute('INSERT INTO workspaces VALUES(1,?,?)', (serialized, key_hash))
    backend.init_db()
    backend.init_db()
    with backend.database() as db:
        rows = db.execute('SELECT * FROM buildings').fetchall()
        assert len(rows) == 1 and rows[0]['state_json'] == serialized and rows[0]['device_key_hash'] == key_hash
        assert db.execute('SELECT state_json FROM workspaces').fetchone()[0] == serialized
    with TestClient(backend.app) as c:
        c.post('/api/auth/login', json={'email': backend.DEMO_EMAIL, 'password': backend.DEMO_PASSWORD})
        result = c.get('/api/workspace').json()
        assert result['building']['name'] == '복구한 미래관'
        assert c.get('/api/floorplan/1').content == base64.b64decode(PNG)
        assert c.post('/api/device/readings', json={'bin_id': 'B-001', 'compartment': 'PET', 'fill_percent': 35},
                      headers={'X-Device-Key': 'legacy-sensor-key'}).status_code == 200
