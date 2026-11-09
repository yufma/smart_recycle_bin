"""Verify the public artifact contains demo assets, never the owner's saved database."""
import ast
import hashlib
import hmac
import json
from pathlib import Path
import zipfile

import pytest

from tools.build_public_demo import FLOORPLANS, package


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def built_demo(tmp_path_factory):
    folder = tmp_path_factory.mktemp('public-demo')
    package(output=folder)
    return folder


def test_public_archive_is_allowlisted_and_has_three_fictional_workspaces(built_demo):
    folder = built_demo
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    archive = folder / manifest['archive']
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == manifest['sha256']
    with zipfile.ZipFile(archive) as packed:
        names = packed.namelist()
        assert len(names) == manifest['files']
        for name in names:
            assert not name.startswith(('/', '../')) and '..' not in Path(name).parts
            assert not name.endswith(('.sqlite3', '.db', '.log', '.env'))
            assert name.startswith(('server/', 'tools/', 'demo-assets/', 'datasets/inha-campus/')) or name == 'browser_runtime.py'
        seeds = json.loads(packed.read('demo-assets/seeds.json'))
        assert [s['building']['name'].split('·')[-1].strip() for s in seeds] == ['더미관', '용현캠퍼스', '정석학술정보관']
        for state in seeds:
            assert state['last_plan'] is None and state['logs'] == [] and state['readings'] == []
            assert state['device_key_hint'] is None and len(state['bins']) >= 12
            for filename in state['map_images'].values():
                assert 'demo-assets/' + filename in names
        library = seeds[2]
        assert sorted(map(int, library['map_images'])) == [-1, 1, 2, 3, 4, 5]
        for floor, filename in library['map_images'].items():
            original = ('B1' if floor == '-1' else f'{floor}F') + '.jpg'
            assert packed.read('demo-assets/' + filename) == (FLOORPLANS / original).read_bytes()
        for state in seeds[1:]:
            assert '시연용 가정' in state['building']['layout_note']


def test_browser_password_hash_matches_local_pbkdf2_algorithm():
    # Extract the portable function without booting the browser runtime or touching local files.
    tree = ast.parse((ROOT / 'browser/runtime.py').read_text(encoding='utf-8'))
    function = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == 'portable_pbkdf2')
    namespace = {'hmac': hmac}
    exec(compile(ast.Module(body=[function], type_ignores=[]), '<portable-pbkdf2>', 'exec'), namespace)
    for rounds, length in [(1, 32), (20, 32), (20, 48)]:
        args = ('sha256', '시연-password'.encode(), b'fixed-test-salt', rounds, length)
        assert namespace['portable_pbkdf2'](*args) == hashlib.pbkdf2_hmac(*args)
