import base64
import copy

import pytest
from fastapi.testclient import TestClient

from server import app as backend
from tools.build_jeongseok_library import PHOTOS, build_graph, build_workspace

PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l6UAAAAASUVORK5CYII='


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(backend, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(backend, 'DB_PATH', tmp_path / 'library.sqlite3')
    monkeypatch.setattr(backend, 'MAP_DIR', tmp_path / 'maps')
    with TestClient(backend.app) as c:
        assert c.post('/api/auth/login', json={'email': backend.DEMO_EMAIL, 'password': backend.DEMO_PASSWORD}).status_code == 200
        yield c


def import_library(client):
    response = client.post('/api/buildings', json={'name': '정석학술정보관', 'template': 'empty', 'floors': 5, 'basement_floors': 1})
    assert response.status_code == 201
    response = client.post('/api/restore', json={'format': 'reloop-backup-v1', 'created_at': backend.now(),
                           'workspace': build_workspace(), 'images': {'-1': PNG}})
    assert response.status_code == 200, response.text
    return response.json()


def test_basement_map_restore_roundtrip_and_original_building_stays_separate(client):
    original = client.get('/api/workspace').json()
    state = import_library(client)
    assert state['building']['floors'] == 5 and state['building']['basement_floors'] == 1
    assert not any(n['kind'] in ('office', 'depot') for n in state['graph']['nodes'])
    assert set(n['floor'] for n in state['graph']['nodes']) == {-1, 1, 2, 3, 4, 5}
    assert client.get('/api/floorplan/-1').content == base64.b64decode(PNG)
    exported = client.get('/api/backup').json()
    assert exported['images'] == {'-1': PNG}
    assert client.post('/api/restore', json=exported).status_code == 200
    old = client.get('/api/workspace', headers={'X-Building-ID': str(original['workspace_id'])}).json()
    assert old['building'] == original['building'] and old['graph'] == original['graph']


def test_nonexistent_floors_and_removing_used_basement_are_rejected(client):
    state = import_library(client)
    for floor in [0, -2, 6]:
        assert client.put(f'/api/floorplan/{floor}', json={'data_url': 'data:image/png;base64,' + PNG}).status_code == 422
        graph = copy.deepcopy(state['graph'])
        graph['nodes'][0]['floor'] = floor
        assert client.put('/api/graph', json=graph).status_code == 422
    assert client.patch('/api/config', json={'basement_floors': 0}).status_code == 422
    assert client.get('/api/workspace').json()['building']['basement_floors'] == 1
    for key in ['0', '-2', '--1', '01']:
        backup = client.get('/api/backup').json()
        backup['images'] = {key: PNG}
        assert client.post('/api/restore', json=backup).status_code == 422


def test_basement_bins_can_be_named_without_changing_readings_or_identity(client):
    state = import_library(client)
    point = next(n for n in state['graph']['nodes'] if n['floor'] == -1 and n['kind'] == 'corridor')
    created = client.post('/api/bins', json={'name': '지하 테스트', 'floor': -1, 'x': point['x'], 'y': point['y'],
                          'access_node': point['id'], 'fills': {'PET': 94}, 'device_type': 'demo'})
    assert created.status_code == 201, created.text
    before = created.json()['bins'][-1]
    response = client.patch('/api/bins/' + before['id'], json={'name': '  지하 1층 서쪽 출입구  '})
    assert response.status_code == 200
    after = response.json()['bins'][-1]
    assert after['name'] == '지하 1층 서쪽 출입구'
    assert {k: v for k, v in after.items() if k != 'name'} == {k: v for k, v in before.items() if k != 'name'}
    assert client.patch('/api/bins/' + before['id'], json={'name': '   '}).status_code == 422
    assert client.patch('/api/bins/' + before['id'], json={'floor': 0}).status_code == 422


def test_library_graph_connected_by_stairs_and_by_lifts_without_inventing_real_locations():
    state = build_workspace()
    assert set(PHOTOS) == {-1, 1, 2, 3, 4, 5}
    assert len(state['bins']) == 1 and state['bins'][0]['fill'] is None
    assert not any(n['kind'] in ('office', 'depot') for n in state['graph']['nodes'])
    backend.validate_graph(build_graph(), 5, 1)
    for cart in [False, True]:
        state['building']['use_cart'] = cart
        nodes, arcs = backend.travel_graph(state)
        reached, _, _ = backend.fastest_paths(arcs, 'F-1-ST1')
        assert all(n['id'] in reached for n in state['graph']['nodes']), (cart, len(reached), len(nodes))


@pytest.mark.parametrize('lower,upper,storeys', [(-1, 1, 1), (-2, 1, 2), (-1, 5, 5), (1, 5, 4)])
def test_travel_time_skips_floor_zero(lower, upper, storeys):
    state = build_workspace()
    state['graph'] = {'nodes': [
        {'id': 'A', 'floor': lower, 'x': 50, 'y': 50, 'kind': 'stairs'},
        {'id': 'B', 'floor': upper, 'x': 50, 'y': 50, 'kind': 'stairs'},
    ], 'edges': [{'id': 'E', 'from': 'A', 'to': 'B', 'distance_m': None}]}
    _, arcs = backend.travel_graph(state)
    assert arcs['A'][0][1] == storeys * state['building']['stairs_up_seconds']
    assert arcs['B'][0][1] == storeys * state['building']['stairs_down_seconds']
    assert arcs['A'][0][2] == storeys * 12


def test_older_backup_still_imports_without_basement_or_note(client):
    backup = client.get('/api/backup').json()
    backup['workspace']['building'].pop('basement_floors', None)
    backup['workspace']['building'].pop('layout_note', None)
    response = client.post('/api/restore', json=backup)
    assert response.status_code == 200, response.text
    assert response.json()['building']['basement_floors'] == 0


def test_library_route_collects_all_six_floors_after_user_places_sites():
    state = build_workspace()
    state['building'].update(available_staff=1, use_cart=True, cart_capacity=0, max_work_minutes=0)
    anchor = next(n for n in state['graph']['nodes'] if n['floor'] == 1 and n['kind'] == 'corridor')
    for kind in ['office', 'depot']:
        point = dict(anchor, id='TEST-' + kind, kind=kind, label='테스트 위치')
        state['graph']['nodes'].append(point)
        state['graph']['edges'].append({'id': 'TEST-' + kind, 'from': anchor['id'], 'to': point['id'], 'distance_m': 1})
    expected = []
    for i, floor in enumerate(PHOTOS, 2):
        point = next(n for n in state['graph']['nodes'] if n['floor'] == floor and n['kind'] == 'corridor')
        bin_id = f'B-{i:03}'
        expected.append(bin_id)
        state['bins'].append(backend.set_fills(dict(state['bins'][0], id=bin_id, floor=floor, name='테스트 위치',
                              x=point['x'], y=point['y'], access_node=point['id'], device_type='demo',
                              reading_source='demo'), {'CAN': 0, 'PET': 95, 'GLASS': 0, 'OTHER': 0}))
    plan = backend.calculate_plan(state)
    assert not plan['unreachable'] and not plan['unassigned']
    assert sorted(plan['target_ids']) == expected
    assert sorted(b for r in plan['routes'] for b in r['bin_ids']) == expected
    assert set(p['floor'] for r in plan['routes'] for p in r['path']) == set(PHOTOS)
