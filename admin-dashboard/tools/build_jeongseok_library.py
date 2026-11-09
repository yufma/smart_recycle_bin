"""Make a local-only import from the user's six photographs, without changing the originals.

Points are manually read from the photographs in a 1400x1050 reference frame. This is a
collection demo, not a surveyed building model or an evacuation guide. No bin/staff positions
are inferred from the photographs. Run from admin-dashboard with --photos and --output.
"""
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

PHOTOS = {
    -1: 'KakaoTalk_20261105_184705044.jpg',
    1: 'KakaoTalk_20261105_184705044_01.jpg',
    2: 'KakaoTalk_20261105_132603662_04.jpg',
    3: 'KakaoTalk_20261105_132603662_02.jpg',
    4: 'KakaoTalk_20261105_132603662_01.jpg',
    5: 'KakaoTalk_20261105_132603662.jpg',
}
NOTE = ('직접 촬영한 도면에서 복도·계단·승강기 지점을 수작업으로 배치했습니다. '
        '실제 쓰레기통·관리자실·분리수거장 위치는 직접 지정해 주세요. '
        '축척과 층간 운행은 현장 확인 전 가정이며 거리·시간은 시연용 예상치입니다.')

# Consecutive points within a line are joined; shared coordinates become one junction.
# Branches terminate at visible doors/landings. No line crosses the central OPEN atrium.
PATHS = {
    -1: [
        [(225, 352), (300, 352), (420, 354), (525, 356), (590, 358), (640, 360), (710, 362), (810, 363), (880, 365), (970, 367), (1120, 370)],
        [(590, 358), (590, 306)], [(640, 360), (640, 334)],
        [(710, 362), (710, 334)], [(880, 365), (880, 304)],
        [(300, 352), (300, 336)], [(525, 356), (510, 342)],
        [(590, 358), (590, 385)], [(810, 363), (810, 390)],
        [(970, 367), (970, 392)],
    ],
    1: [
        [(580, 353), (580, 410), (650, 430), (710, 430), (770, 450), (870, 450), (870, 400), (945, 400), (945, 352)],
        [(650, 430), (665, 407)], [(710, 430), (755, 407)],
        [(770, 450), (770, 520), (770, 610), (770, 720), (770, 780), (770, 846)],
        [(770, 720), (650, 720), (535, 745), (420, 745), (365, 745)],
        [(365, 745), (344, 745)],
        [(580, 410), (540, 410)], [(945, 400), (985, 400)],
        [(770, 520), (875, 520)],
    ],
    2: [
        [(548, 298), (548, 373), (590, 373), (640, 373), (680, 373), (779, 373), (779, 322), (858, 322), (858, 294)],
        [(590, 373), (590, 347)], [(680, 373), (680, 347)],
        [(640, 373), (640, 402), (640, 458)],
        [(170, 458), (300, 458), (420, 458), (640, 458), (915, 458), (1040, 458), (1190, 458)],
        [(170, 458), (170, 550), (170, 592), (170, 750), (170, 830)],
        [(170, 592), (265, 592), (265, 622)],
        [(1190, 458), (1190, 550), (1190, 580), (1190, 750), (1190, 810)],
        [(1190, 580), (1125, 580), (1125, 610)],
    ],
    3: [
        [(548, 286), (548, 367), (595, 367), (641, 367), (681, 367), (786, 367), (786, 316), (880, 316), (880, 289)],
        [(595, 367), (595, 341)], [(681, 367), (681, 341)],
        [(641, 367), (641, 400), (641, 461)],
        [(166, 461), (300, 461), (420, 461), (641, 461), (950, 461), (1090, 461), (1230, 461)],
        [(166, 461), (166, 555), (166, 595), (166, 750), (166, 840)],
        [(166, 595), (260, 595), (260, 635)],
        [(1230, 461), (1230, 550), (1230, 585), (1230, 750), (1230, 815)],
        [(1230, 585), (1145, 585), (1145, 615)],
    ],
    4: [
        [(530, 332), (530, 418), (574, 418), (620, 418), (659, 418), (760, 418), (760, 371), (844, 371), (844, 335)],
        [(574, 418), (574, 390)], [(659, 418), (659, 390)],
        [(620, 418), (620, 450), (620, 500)],
        [(150, 500), (285, 500), (400, 500), (620, 500), (900, 500), (1030, 500), (1160, 500)],
        [(150, 500), (150, 580), (150, 620), (150, 780), (150, 850)],
        [(150, 620), (242, 620), (242, 654)],
        [(1160, 500), (1160, 570), (1160, 610), (1160, 760), (1160, 830)],
        [(1160, 610), (1080, 610), (1080, 652)],
    ],
    5: [
        [(531, 330), (531, 412), (580, 412), (635, 412), (683, 412), (780, 412), (780, 371), (893, 371), (943, 371), (1165, 351)],
        [(580, 412), (580, 388)], [(683, 412), (683, 388)],
        [(893, 371), (893, 320)],
        [(531, 412), (470, 412), (430, 412), (320, 412), (230, 412), (230, 550), (230, 630), (230, 675), (215, 675), (215, 699)],
        [(1165, 351), (1175, 470), (1175, 580), (1175, 637), (1175, 675), (1180, 705)],
        [(230, 630), (330, 630), (330, 675)],
    ],
}

CORES = {
    -1: {'ST1': (590, 306), 'ST2': (880, 304), 'EL1': (640, 334), 'EL2': (710, 334)},
    1: {'ST1': (580, 353), 'ST2': (945, 352), 'EL1': (665, 407), 'EL2': (755, 407), 'ST3': (344, 745)},
    2: {'ST1': (548, 298), 'ST2': (858, 294), 'EL1': (590, 347), 'EL2': (680, 347), 'ST3': (265, 622), 'ST4': (1125, 610)},
    3: {'ST1': (548, 286), 'ST2': (880, 289), 'EL1': (595, 341), 'EL2': (681, 341), 'ST3': (260, 635), 'ST4': (1145, 615)},
    4: {'ST1': (530, 332), 'ST2': (844, 335), 'EL1': (574, 390), 'EL2': (659, 390), 'ST3': (242, 654), 'ST4': (1080, 652)},
    5: {'ST1': (531, 330), 'ST2': (893, 320), 'EL1': (580, 388), 'EL2': (683, 388), 'ST3': (215, 699), 'ST4': (1180, 705)},
}
NAMES = {'ST1': '후면 서측 계단', 'ST2': '후면 동측 계단', 'ST3': '전면 서측 계단',
         'ST4': '전면 동측 계단', 'EL1': '중앙 서측 승강기', 'EL2': '중앙 동측 승강기'}


def photo_point(x: float, y: float) -> dict:
    # MapView fits a 4:3 photo into 900x460 at (50,45), with horizontal letterboxing.
    width, height = 460 * 4 / 3, 460
    return {'x': round(((900 - width) / 2 + x / 1400 * width) / 9, 3),
            'y': round(y / 1050 * height / 4.6, 3)}


def build_graph() -> dict:
    nodes, edges, pair_ids = [], [], set()
    shafts = {}
    for floor, paths in PATHS.items():
        cores = {at: code for code, at in CORES[floor].items()}
        points = {}
        for line in paths:
            for at in line:
                if at in points:
                    continue
                code = cores.get(at)
                node_id = f'F{floor}-{code or len(points) + 1}'
                kind = 'stairs' if code and code.startswith('ST') else 'elevator' if code else 'corridor'
                nodes.append({'id': node_id, 'floor': floor, **photo_point(*at), 'kind': kind,
                              'label': NAMES[code] if code else f'복도 {len(points) + 1}'})
                points[at] = node_id
                if code:
                    shafts.setdefault(code, []).append(node_id)
            for a, b in zip(line, line[1:]):
                pair = tuple(sorted([points[a], points[b]]))
                if pair not in pair_ids:
                    edges.append({'id': f'J-{len(edges) + 1}', 'from': points[a], 'to': points[b], 'distance_m': None})
                    pair_ids.add(pair)
    for stops in shafts.values():
        for a, b in zip(stops, stops[1:]):
            edges.append({'id': f'J-{len(edges) + 1}', 'from': a, 'to': b, 'distance_m': None})
    return {'nodes': nodes, 'edges': edges}


def build_workspace() -> dict:
    from server.app import new_workspace
    state = new_workspace()
    state['building'].update(name='인하대학교 · 정석학술정보관', floors=5, basement_floors=1,
                             layout_note=NOTE, meters_per_unit=1.0, office_access_node='', depot_node='')
    state.update(graph=build_graph(), graph_version=2, map_images={}, last_plan=None, logs=[], readings=[])
    real = next(b for b in state['bins'] if b['device_type'] == 'real')
    real.update(name='위치 지정 전 실물 장치', floor=1, x=6, y=8, access_node='F1-ST1')
    state['bins'] = [real]
    return state


def make_backup(photos: Path) -> dict:
    from server.app import now
    state = build_workspace()
    images = {}
    for floor, filename in PHOTOS.items():
        raw = (photos / filename).read_bytes()
        if not raw.startswith(b'\xff\xd8\xff') or len(raw) > 4_000_000:
            raise ValueError(f'{filename}: expected a JPEG under 4MB')
        images[str(floor)] = base64.b64encode(raw).decode('ascii')
    return {'format': 'reloop-backup-v1', 'created_at': now(), 'workspace': state, 'images': images}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--photos', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    backup = make_backup(args.photos)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'jeongseok-library-backup.json').write_text(json.dumps(backup, ensure_ascii=False), encoding='utf-8')
    manifest = {'floors': PHOTOS, 'note': NOTE, 'coordinate_frame': [1400, 1050],
                'bin_locations': 'not supplied; one unplaced real-device slot only',
                'admin_and_dropoff_locations': 'not supplied; user must place them',
                'walkways': 'photo interpretation; open reading areas and door access require on-site confirmation',
                'scale': '1 metre per map x unit is an uncalibrated demo assumption'}
    (args.output / 'photo-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'floors': list(PHOTOS), 'nodes': len(backup['workspace']['graph']['nodes']),
                      'edges': len(backup['workspace']['graph']['edges']), 'photos': len(backup['images'])}))


if __name__ == '__main__':
    main()
