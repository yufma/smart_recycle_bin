"""Checks against the cached source geography, and real restore/plan APIs with isolated data."""
import json

import pytest
from fastapi.testclient import TestClient

from server import app as backend
from tools.build_inha_campus import build_workspaces, campus_data, metres, projection


@pytest.fixture(scope='module')
def dataset():
    data = campus_data()
    manual, example, manifest = build_workspaces(data)
    return data, manual, example, manifest


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(backend, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(backend, 'DB_PATH', tmp_path / 'inha-test.sqlite3')
    monkeypatch.setattr(backend, 'MAP_DIR', tmp_path / 'maps')
    with TestClient(backend.app) as c:
        assert c.post('/api/auth/login', json={'email': backend.DEMO_EMAIL, 'password': backend.DEMO_PASSWORD}).status_code == 200
        yield c


def restore(client, state):
    result = client.post('/api/restore', json={'format': 'reloop-backup-v1', 'created_at': state['updated_at'],
                                             'workspace': state, 'images': {}})
    assert result.status_code == 200, result.text
    return result.json()


def test_source_edges_are_osm_segments_and_use_geographic_distances(dataset):
    data, manual, _, manifest = dataset
    source_nodes = data['nodes']
    graph_nodes = {p['id']: p for p in manual['graph']['nodes']}
    assert manifest['real_bin_locations'] == manifest['real_fill_readings'] == 0
    for edge in manual['graph']['edges']:
        a, b = [int(edge[key].removeprefix('OSM-')) for key in ('from', 'to')]
        assert (min(a, b), max(a, b)) in data['links']
        assert edge['distance_m'] == pytest.approx(metres(source_nodes[a], source_nodes[b]), abs=0.001)
        assert backend.map_distance(graph_nodes[edge['from']], graph_nodes[edge['to']], manifest['scale_m_per_unit']) == pytest.approx(edge['distance_m'], abs=0.03)


def test_projection_keeps_north_up_and_matches_the_drawing_scale(dataset):
    data, _, _, _ = dataset
    locate, scale = projection(data)
    start = {'lat': 37.449, 'lon': 126.653}
    north, east = start | {'lat': 37.4491}, start | {'lon': 126.6531}
    assert locate(north)['y'] < locate(start)['y']
    assert locate(east)['x'] > locate(start)['x']
    assert 10 < scale <= 20
    assert all(0 <= value <= 100 for i in data['connected'] for value in locate(data['nodes'][i]).values())


def test_manual_import_waits_for_user_bin_and_operational_locations(client, dataset):
    _, manual, _, _ = dataset
    state = restore(client, manual)
    assert len(state['bins']) == 1
    assert state['bins'][0]['name'] == '위치 지정 전 실물 장치'
    assert state['bins'][0]['fill'] is None
    assert state['building']['meters_per_unit'] > 10
    assert not any(e['from'] in {'F1-OF1', 'F1-DP1'} or e['to'] in {'F1-OF1', 'F1-DP1'} for e in state['graph']['edges'])
    plan = client.post('/api/plan', json={}).json()['last_plan']
    assert plan['routes'] == [] and plan['target_ids'] == []
    assert any('통로와 이어지지 않은 관리자실' in issue for issue in plan['issues'])


@pytest.mark.parametrize('include_orange', [False, True])
def test_synthetic_check_routes_follow_source_roads_and_assign_each_target_once(client, dataset, include_orange):
    data, _, example, _ = dataset
    state = restore(client, example)
    plan = client.post('/api/plan', json={'include_orange': include_orange, 'available_staff': 2}).json()['last_plan']
    expected = {b['id'] for b in state['bins'] if b['fill'] is not None and b['fill'] >= (80 if include_orange else 90)}
    assigned = [bin_id for route in plan['routes'] for bin_id in route['bin_ids']]
    assert len(expected) == (10 if include_orange else 6)
    assert len(assigned) == len(set(assigned)) and set(assigned) == expected
    assert not plan['issues'] and not plan['unreachable'] and not plan['unassigned']
    nodes = {p['id']: p for p in state['graph']['nodes']}
    for route in plan['routes']:
        assert nodes[route['path'][0]['id']]['kind'] == 'office'
        assert nodes[route['path'][-1]['id']]['kind'] == 'depot'
        for a, b in zip(route['path'], route['path'][1:]):
            # Bin/access legs are synthetic, zero-distance attachments. All travel follows source edges.
            if a['id'].startswith('B-') or b['id'].startswith('B-'):
                assert a['x'] == b['x'] and a['y'] == b['y']
            else:
                pair = tuple(sorted(int(p['id'].removeprefix('OSM-')) for p in (a, b)))
                assert pair in data['links']


def test_user_can_place_and_connect_a_bin_on_the_imported_campus(client, dataset):
    _, manual, _, _ = dataset
    state = restore(client, manual)
    graph = json.loads(json.dumps(state['graph']))
    road = next(n for n in graph['nodes'] if n['kind'] == 'corridor')
    office = next(n for n in graph['nodes'] if n['kind'] == 'office')
    depot = next(n for n in graph['nodes'] if n['kind'] == 'depot')
    office.update(x=road['x'], y=road['y'], label='사용자 지정 관리자실')
    depot.update(x=road['x'], y=road['y'], label='사용자 지정 집하장')
    graph['edges'] += [{'id': f'USER-{p["id"]}', 'from': road['id'], 'to': p['id'], 'distance_m': 0.01} for p in (office, depot)]
    assert client.put('/api/graph', json=graph).status_code == 200
    response = client.post('/api/bins', json={'name': '사용자가 지정한 수거 위치', 'floor': 1,
                           'x': road['x'], 'y': road['y'], 'access_node': road['id'],
                           'device_type': 'demo', 'fills': {'PET': 95}})
    assert response.status_code == 201
    new_id = response.json()['bins'][-1]['id']
    plan = client.post('/api/plan', json={}).json()['last_plan']
    assert plan['target_ids'] == [new_id]
    assert plan['routes'][0]['bin_ids'] == [new_id]
    assert not plan['issues']
