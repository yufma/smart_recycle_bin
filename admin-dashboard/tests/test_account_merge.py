import base64

import pytest
from fastapi.testclient import TestClient

from server import account_store, app as backend

PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l6UAAAAASUVORK5CYII='
ALIAS_EMAIL, ALIAS_PASSWORD = 'map-test@reloop.local', 'MapTest1234!'


@pytest.fixture
def accounts(tmp_path, monkeypatch):
    monkeypatch.setattr(backend, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(backend, 'DB_PATH', tmp_path / 'accounts.sqlite3')
    monkeypatch.setattr(backend, 'MAP_DIR', tmp_path / 'maps')
    with TestClient(backend.app, base_url='http://localhost') as local, TestClient(backend.app, base_url='http://127.0.0.1') as ip:
        ip.post('/api/auth/login', json={'email': backend.DEMO_EMAIL, 'password': backend.DEMO_PASSWORD})
        primary = ip.get('/api/workspace').json()['user']['id']
        campus = ip.post('/api/buildings', json={'name': '용현캠퍼스', 'template': 'empty'}).json()['workspace_id']
        response = local.post('/api/auth/register', json={'email': ALIAS_EMAIL, 'password': ALIAS_PASSWORD, 'name': 'Map Test'})
        source = response.json()['id']
        library = local.get('/api/workspace').json()['workspace_id']
        assert local.patch(f'/api/buildings/{library}', json={'name': '정석학술정보관'}).status_code == 200
        assert local.put('/api/floorplan/1', json={'data_url': 'data:image/png;base64,' + PNG}).status_code == 200
        key = local.post('/api/device/key', json={}).json()['key']
        duplicate = local.post('/api/buildings', json={'name': '미배치 캠퍼스 이전본', 'template': 'empty'}).json()['workspace_id']
        duplicate_key = local.post('/api/device/key', json={}).json()['key']
        yield {'local': local, 'ip': ip, 'primary': primary, 'source': source, 'library': library,
               'campus': campus, 'duplicate': duplicate, 'key': key, 'duplicate_key': duplicate_key}


def merge(accounts):
    with backend.database() as db:
        return account_store.merge(db, accounts['source'], accounts['primary'], backend.now(), archive_ids=[accounts['duplicate']])


def test_old_sessions_on_localhost_and_ip_see_same_three_buildings(accounts):
    merge(accounts)
    local, ip = accounts['local'], accounts['ip']
    a, b = local.get('/api/workspace').json(), ip.get('/api/workspace').json()
    assert a['user'] == b['user'] and a['user']['id'] == accounts['primary']
    assert a['buildings'] == b['buildings'] and len(a['buildings']) == 3
    assert {item['name'] for item in a['buildings']} == {'인하대학교 · 미래관', '용현캠퍼스', '정석학술정보관'}
    assert local.get(f'/api/floorplan/1?building_id={accounts["library"]}').content == base64.b64decode(PNG)
    assert ip.get(f'/api/floorplan/1?building_id={accounts["library"]}').content == base64.b64decode(PNG)
    assert local.patch(f'/api/buildings/{accounts["library"]}', json={'name': '정석관 수정'}).status_code == 200
    assert any(item['name'] == '정석관 수정' for item in ip.get('/api/buildings').json()['items'])


def test_original_building_states_and_active_sensor_key_are_preserved(accounts):
    with backend.database() as db:
        rows = db.execute('SELECT id,state_json,device_key_hash FROM buildings WHERE deleted_at IS NULL').fetchall()
        before = {row['id']: (row['state_json'], row['device_key_hash']) for row in rows}
    merge(accounts)
    with backend.database() as db:
        for building_id, values in before.items():
            row = db.execute('SELECT state_json,device_key_hash FROM buildings WHERE id=?', (building_id,)).fetchone()
            if building_id != accounts['duplicate']:
                assert (row['state_json'], row['device_key_hash']) == values
    assert accounts['ip'].post('/api/device/readings', headers={'X-Device-Key': accounts['key']},
                                json={'bin_id': 'B-001', 'compartment': 'PET', 'fill_percent': 91}).status_code == 200
    response = accounts['local'].get('/api/workspace', headers={'X-Building-ID': str(accounts['library'])})
    assert response.json()['bins'][0]['fill'] == 91
    assert accounts['ip'].post('/api/device/readings', headers={'X-Device-Key': accounts['duplicate_key']},
                               json={'bin_id': 'B-001', 'compartment': 'PET', 'fill_percent': 12}).status_code == 401


def test_alias_login_still_checks_original_password_and_returns_primary_workspace(accounts):
    merge(accounts)
    local = accounts['local']
    assert local.post('/api/auth/login', json={'email': ALIAS_EMAIL, 'password': 'WrongPassword!'}).status_code == 401
    response = local.post('/api/auth/login', json={'email': ALIAS_EMAIL, 'password': ALIAS_PASSWORD})
    assert response.status_code == 200 and response.json()['id'] == accounts['primary']
    assert len(local.get('/api/buildings').json()['items']) == 3
    assert local.post('/api/auth/login', json={'email': backend.DEMO_EMAIL, 'password': backend.DEMO_PASSWORD}).status_code == 200


def test_duplicate_remains_recoverable_and_repeated_merge_does_not_copy_data(accounts):
    merge(accounts)
    response = accounts['local'].get('/api/buildings').json()
    assert [item['id'] for item in response['deleted_items']] == [accounts['duplicate']]
    assert merge(accounts)['already_merged']
    assert accounts['local'].get('/api/buildings').json() == response
    assert accounts['local'].post(f'/api/buildings/{accounts["duplicate"]}/restore', json={}).status_code == 200
    assert len(accounts['ip'].get('/api/buildings').json()['items']) == 4


def test_unrelated_accounts_keep_their_private_buildings(accounts):
    merge(accounts)
    local = accounts['local']
    response = local.post('/api/auth/register', json={'email': 'private@reloop.local', 'password': 'Private123!', 'name': 'Private'})
    assert response.status_code == 201
    assert len(local.get('/api/buildings').json()['items']) == 1
    assert local.get('/api/workspace', headers={'X-Building-ID': str(accounts['library'])}).status_code == 404
    assert len(accounts['ip'].get('/api/buildings').json()['items']) == 3


@pytest.mark.parametrize('invalid', ['self', 'foreign_archive'])
def test_invalid_merge_rolls_back_without_changing_accounts(accounts, invalid):
    with backend.database() as db:
        before = [tuple(r) for r in db.execute('SELECT * FROM buildings ORDER BY id')]
    with pytest.raises(ValueError), backend.database() as db:
        account_store.merge(db, accounts['source'], accounts['source'] if invalid == 'self' else accounts['primary'],
                            backend.now(), archive_ids=[accounts['campus']] if invalid == 'foreign_archive' else [])
    with backend.database() as db:
        assert [tuple(r) for r in db.execute('SELECT * FROM buildings ORDER BY id')] == before
        assert db.execute('SELECT COUNT(*) FROM account_aliases').fetchone()[0] == 0


def test_no_automatic_link_between_accounts_that_have_not_been_merged(accounts):
    a, b = accounts['local'].get('/api/buildings').json(), accounts['ip'].get('/api/buildings').json()
    assert len(a['items']) == 2 and len(b['items']) == 2
    assert {i['id'] for i in a['items']}.isdisjoint(i['id'] for i in b['items'])
