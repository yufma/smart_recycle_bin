"""Package an isolated browser demo from source and synthetic seed data, never a live database."""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

from server import app as backend
from tools.build_inha_campus import build_workspaces, campus_data
from tools.build_jeongseok_library import PHOTOS, build_workspace

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / 'public' / 'public-demo'


def populate_demo(state):
    """Fictional collection sites on actual mapped walkways, visibly labelled as demo data."""
    corridors = [n for n in state['graph']['nodes'] if n['kind'] == 'corridor']
    floors = sorted({n['floor'] for n in corridors})
    sites = []
    for floor in floors:
        points = [n for n in corridors if n['floor'] == floor]
        slots = 12 if len(floors) == 1 else 2
        sites.extend(points[round(i * (len(points) - 1) / (slots - 1))] for i in range(slots))
    stamp = backend.now()
    state['bins'] = []
    for i, point in enumerate(sites):
        label = f'지하 {-point["floor"]}층' if point['floor'] < 0 else f'{point["floor"]}층'
        level = [94, 84, 35, 97, 58, 91, 86, 42, 96, 65, 92, 81][i % 12]
        state['bins'].append(backend.set_fills({
            'id': f'B-{i + 1:03}', 'name': f'시연 · {label} 수거 지점 {i + 1}',
            'floor': point['floor'], 'x': point['x'], 'y': point['y'], 'access_node': point['id'],
            'device_type': 'real' if i == 0 else 'demo', 'reading_source': 'simulated' if i == 0 else 'demo',
            'measured_at': stamp, 'received_at': stamp, 'awaiting_confirmation': False,
        }, backend.demo_fills(level, i)))
    ground = [n for n in corridors if n['floor'] == 1]
    for kind, anchor, code, label in [('office', ground[0], 'PUBOF', '시연 관리자실'),
                                       ('depot', ground[-1], 'PUBDP', '시연 집하장')]:
        existing = next((n for n in state['graph']['nodes'] if n['kind'] == kind), None)
        if existing:
            existing.update(floor=1, x=anchor['x'], y=anchor['y'], label=label)
            point = existing
        else:
            point = dict(anchor, id=f'F1-{code}', kind=kind, label=label)
            state['graph']['nodes'].append(point)
        state['graph']['edges'].append({'id': f'PUBLIC-{code}', 'from': anchor['id'], 'to': point['id'], 'distance_m': 1})
    state['building']['layout_note'] = (state['building'].get('layout_note', '') +
        ' 공개 체험판의 쓰레기통·관리자실·집하장 위치와 적재율은 시연용 가정이며 실제 설치 정보가 아닙니다.')
    state['graph_version'] = 2
    return state


def seed_workspaces():
    dummy = backend.new_workspace()
    dummy['building']['name'] = '인하대학교 · 더미관'
    campus = populate_demo(build_workspaces(campus_data())[0])
    campus['building']['name'] = '인하대학교 · 용현캠퍼스'
    campus['map_images'] = {'1': 'seed-inha.png'}
    library = populate_demo(build_workspace())
    library['map_images'] = {str(f): f'seed-jeongseok-{f}.jpg' for f in PHOTOS}
    for state in [dummy, campus, library]:
        state.update(last_plan=None, logs=[], readings=[], device_key_hint=None)
        state['building'].setdefault('basement_floors', 0)
        state['building'].setdefault('layout_note', '')
        backend.validate_config(state)
        backend.validate_graph(state['graph'], state['building']['floors'], state['building']['basement_floors'])
        for bin in state['bins']:
            backend.validate_bin(state, bin)
    return [dummy, campus, library]


def package(photos=None):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    archive = OUTPUT / 'backend.zip'
    retained = {}
    if archive.exists():
        with zipfile.ZipFile(archive) as previous:
            retained = {name: previous.read(name) for name in previous.namelist() if name.startswith('demo-assets/seed-jeongseok-')}
    files = {}
    for path in (ROOT / 'server').glob('*.py'):
        files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    for path in (ROOT / 'server' / 'samples').glob('*.png'):
        files[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    for name in ['build_inha_campus.py', 'build_jeongseok_library.py']:
        files['tools/' + name] = (ROOT / 'tools' / name).read_bytes()
    files['datasets/inha-campus/osm-snapshot.json'] = (ROOT / 'datasets/inha-campus/osm-snapshot.json').read_bytes()
    files['demo-assets/seed-inha.png'] = (ROOT / 'server/samples/inha-floor-1.png').read_bytes()
    for floor, filename in PHOTOS.items():
        name = f'demo-assets/seed-jeongseok-{floor}.jpg'
        if photos:
            files[name] = (photos / filename).read_bytes()
        elif name in retained:
            files[name] = retained[name]
        else:
            raise ValueError('최초 빌드에는 --photos 폴더가 필요합니다.')
    files['demo-assets/seeds.json'] = json.dumps(seed_workspaces(), ensure_ascii=False, allow_nan=False).encode()
    files['browser_runtime.py'] = (ROOT / 'browser/runtime.py').read_bytes()
    # Allow-list above deliberately excludes local accounts, SQLite files, logs, keys and settings.
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as packed:
        for name, raw in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            packed.writestr(info, raw)
    manifest = {'format': 'inloop-public-demo-v1', 'archive': 'backend.zip',
                'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(), 'files': len(files),
                'pyodide': '314.0.7', 'data': 'synthetic collection sites; no local database or credentials'}
    (OUTPUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUTPUT / 'ATTRIBUTION.txt').write_text(
        'Campus map: © OpenStreetMap contributors, ODbL 1.0. https://www.openstreetmap.org/copyright\n'
        'Jeongseok floor plans: photographs provided by the project owner for this competition demo.\n'
        'Bin positions, fill levels and operational sites are fictional demo data.\n', encoding='utf-8')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--photos', type=Path)
    args = parser.parse_args()
    print(json.dumps(package(args.photos), ensure_ascii=False))
