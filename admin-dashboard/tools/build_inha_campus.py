"""Build editable campus backups from a cached OSM extract; never change a running workspace.

Run from admin-dashboard: python tools/build_inha_campus.py --output <directory>
Map data is ODbL, © OpenStreetMap contributors. Bin sites and operational roles are not surveyed.
"""
from __future__ import annotations

import argparse
import base64
import copy
import csv
import hashlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from server.app import COMPARTMENTS, new_workspace, sample_fills  # noqa: E402

SOURCE = ROOT / 'datasets' / 'inha-campus' / 'osm-snapshot.json'
WALK_TYPES = {'footway', 'pedestrian', 'path', 'steps', 'service', 'residential', 'living_street', 'unclassified'}
RADIUS = 6_371_008.8
Y_RATIO = 460 / 900
# These sites exist only in the separate algorithm-check fixture, not the editable manual backup.
EXAMPLE_SITES = [
    (217958071, 94), (218189298, 86), (218038027, 96), (218081857, 91),
    (217950511, 84), (218037242, 42), (218188831, 93), (218188169, 88),
    (568420969, 97), (568420968, 64), (568420970, 90), (218265217, 83),
]


def metres(a: dict, b: dict) -> float:
    lat1, lat2 = map(math.radians, (a['lat'], b['lat']))
    delta_lat, delta_lon = lat2 - lat1, math.radians(b['lon'] - a['lon'])
    h = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    return 2 * RADIUS * math.asin(math.sqrt(min(1, h)))


def inside(point: dict, polygon: list[dict]) -> bool:
    x, y, hit = point['lon'], point['lat'], False
    for a, b in zip(polygon, polygon[1:]):
        if (a['lat'] > y) != (b['lat'] > y) and x < (b['lon'] - a['lon']) * (y - a['lat']) / (b['lat'] - a['lat']) + a['lon']:
            hit = not hit
    return hit


def campus_data(path: Path = SOURCE) -> dict:
    snapshot = json.loads(path.read_text(encoding='utf8'))
    nodes = {e['id']: e for e in snapshot['elements'] if e['type'] == 'node'}
    ways = {e['id']: e for e in snapshot['elements'] if e['type'] == 'way'}
    boundary = [nodes[i] for i in ways[472447787]['nodes']]
    links, adjacency = {}, defaultdict(set)
    for way in ways.values():
        tags = way.get('tags', {})
        if (tags.get('highway') not in WALK_TYPES or tags.get('access') in {'private', 'no'}
                or tags.get('foot') in {'private', 'no'} or tags.get('oneway:foot') in {'yes', '-1'}
                or tags.get('area') == 'yes' or tags.get('indoor') == 'yes'):
            continue
        for a, b in zip(way['nodes'], way['nodes'][1:]):
            mid = {k: (nodes[a][k] + nodes[b][k]) / 2 for k in ('lat', 'lon')}
            if a == b or not all(inside(p, boundary) for p in (nodes[a], mid, nodes[b])):
                continue
            pair = tuple(sorted((a, b)))
            links.setdefault(pair, []).append(way['id'])
            adjacency[a].add(b)
            adjacency[b].add(a)
    unseen, components = set(adjacency), []
    while unseen:
        connected = {min(unseen)}
        todo = list(connected)
        for node in todo:
            for other in adjacency[node] - connected:
                connected.add(other)
                todo.append(other)
        unseen -= connected
        components.append(connected)
    if not components:
        raise ValueError('No connected walk network in the cached source.')
    connected = max(components, key=len)
    links = {pair: ids for pair, ids in links.items() if set(pair) <= connected}
    buildings = []
    for way in ways.values():
        if 'building' not in way.get('tags', {}):
            continue
        points = [nodes[i] for i in way['nodes'][:-1]]
        centre = {k: sum(p[k] for p in points) / len(points) for k in ('lat', 'lon')}
        if inside(centre, boundary):
            buildings.append(way | {'centre': centre})
    return {'snapshot': snapshot, 'nodes': nodes, 'ways': ways, 'boundary': boundary,
            'links': links, 'connected': connected, 'buildings': buildings,
            'excluded_components': sorted((len(c) for c in components if c is not connected), reverse=True)}


def projection(data: dict):
    points = data['boundary']
    centre_lat = (min(p['lat'] for p in points) + max(p['lat'] for p in points)) / 2
    centre_lon = (min(p['lon'] for p in points) + max(p['lon'] for p in points)) / 2
    x_scale = math.pi * RADIUS / 180 * math.cos(math.radians(centre_lat))
    y_scale = math.pi * RADIUS / 180
    width = (max(p['lon'] for p in points) - min(p['lon'] for p in points)) * x_scale
    height = (max(p['lat'] for p in points) - min(p['lat'] for p in points)) * y_scale
    # Leave room for the source notice. Preserve physical aspect ratio, including the app's 900:460 map.
    units = math.ceil(max(width / 88, height / (76 * Y_RATIO)) * 20) / 20
    if units > 20:
        raise ValueError('The map is larger than the supported campus scale.')

    def locate(point):
        return {'x': round(50 + (point['lon'] - centre_lon) * x_scale / units, 6),
                'y': round(52 - (point['lat'] - centre_lat) * y_scale / (units * Y_RATIO), 6)}
    return locate, units


def build_workspaces(data: dict) -> tuple[dict, dict, dict]:
    locate, scale = projection(data)
    nodes = [{'id': f'OSM-{i}', 'floor': 1, **locate(data['nodes'][i]), 'kind': 'corridor',
              'label': f'교내 길 {n + 1}'} for n, i in enumerate(sorted(data['connected']))]
    edges = [{'id': f'OSM-{a}-{b}', 'from': f'OSM-{a}', 'to': f'OSM-{b}',
              'distance_m': round(metres(data['nodes'][a], data['nodes'][b]), 3)} for a, b in sorted(data['links'])]
    state = new_workspace()
    state.update(graph={'nodes': copy.deepcopy(nodes), 'edges': edges}, bins=[], graph_version=2, map_images={},
                 logs=[], readings=[], last_plan=None)
    # The three existing entry points are visibly unplaced; no real bin/office/depot positions are claimed.
    state['building'].update(name='인하대학교 · 용현캠퍼스(직접 배치용)', floors=1, meters_per_unit=scale,
                             total_staff=3, available_staff=2, include_orange=False, office_floor=1,
                             office_x=9, office_y=31, office_access_node='', depot_node='')
    state['graph']['nodes'] += [
        {'id': 'F1-OF1', 'floor': 1, 'x': 9, 'y': 31, 'kind': 'office', 'label': '위치 지정 전 관리자실'},
        {'id': 'F1-DP1', 'floor': 1, 'x': 9, 'y': 58, 'kind': 'depot', 'label': '위치 지정 전 집하장'},
    ]
    nearest = min(data['connected'], key=lambda i: data['nodes'][i]['lon'])
    state['bins'] = [{'id': 'B-001', 'name': '위치 지정 전 실물 장치', 'floor': 1, 'x': 9, 'y': 81,
                      'access_node': f'OSM-{nearest}', 'device_type': 'real', 'reading_source': 'unconnected',
                      'measured_at': None, 'received_at': None, 'awaiting_confirmation': False,
                      **sample_fills(None, 0)}]

    example = copy.deepcopy(state)
    example['building']['name'] = '인하대학교 · 용현캠퍼스(가상 수거지점 검증)'
    example['graph']['nodes'] = copy.deepcopy(nodes)
    used = set()
    audit = []
    for number, (building_id, fill) in enumerate(EXAMPLE_SITES, 2):
        building = next(b for b in data['buildings'] if b['id'] == building_id)
        point_id = min(data['connected'] - used, key=lambda i: metres(data['nodes'][i], building['centre']))
        used.add(point_id)
        xy = locate(data['nodes'][point_id])
        example['bins'].append({'id': f'B-{number:03}', 'name': '가상 · ' + building['tags']['name'], 'floor': 1,
                               **xy, 'access_node': f'OSM-{point_id}', 'device_type': 'demo', 'reading_source': 'demo',
                               'measured_at': state['updated_at'], 'received_at': state['updated_at'],
                               'awaiting_confirmation': False, **sample_fills(fill, number)})
        audit.append({'bin_id': f'B-{number:03}', 'building_osm_id': building_id,
                      'building_name': building['tags']['name'], 'road_node_osm_id': point_id,
                      'lat': data['nodes'][point_id]['lat'], 'lon': data['nodes'][point_id]['lon'],
                      'max_fill_percent': fill, 'evidence': 'synthetic_check_only'})
    # Even the optional example keeps the single hardware slot disconnected and off campus until placed.
    for kind, building_id in [('office', 217958071), ('depot', 1098539003)]:
        building = next(b for b in data['buildings'] if b['id'] == building_id)
        point_id = min(data['connected'] - used, key=lambda i: metres(data['nodes'][i], building['centre']))
        used.add(point_id)
        point = next(n for n in example['graph']['nodes'] if n['id'] == f'OSM-{point_id}')
        point.update(kind=kind, label='가상 관리자실' if kind == 'office' else '가상 집하장')
    manifest = {'source': data['snapshot']['source_url'], 'retrieved_on': data['snapshot']['retrieved_on'],
                'attribution': data['snapshot']['attribution'], 'license': data['snapshot']['license'],
                'road_nodes': len(data['connected']), 'road_edges': len(data['links']),
                'excluded_components': data['excluded_components'], 'building_footprints': len(data['buildings']),
                'real_bin_locations': 0, 'real_fill_readings': 0, 'scale_m_per_unit': scale,
                'example_sites': audit, 'map_note': '1F represents the campus ground surface; no indoor topology.'}
    return state, example, manifest


def draw_map(data: dict, target: Path, example: bool, font_path: Path):
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new('RGB', (1800, 920), '#fafcf9')
    draw = ImageDraw.Draw(image)
    locate, _ = projection(data)

    def pixels(point):
        xy = locate(point)
        return xy['x'] * 18, xy['y'] * 9.2

    small, regular, title = [ImageFont.truetype(str(font_path), n) for n in (21, 25, 32)]
    draw.polygon([pixels(p) for p in data['boundary']], fill='#edf3e8', outline='#c2d2bb', width=3)
    for way in data['ways'].values():
        if way.get('tags', {}).get('natural') == 'water':
            draw.polygon([pixels(data['nodes'][i]) for i in way['nodes']], fill='#cde5e8', outline='#a7cbd3', width=2)
    for building in data['buildings']:
        draw.polygon([pixels(data['nodes'][i]) for i in building['nodes']], fill='#dce4e3', outline='#acbbb8', width=2)
    for a, b in data['links']:
        draw.line([pixels(data['nodes'][a]), pixels(data['nodes'][b])], fill='#ffffff', width=14)
        draw.line([pixels(data['nodes'][a]), pixels(data['nodes'][b])], fill='#bac9c1', width=5)
    for building in data['buildings']:
        name = building.get('tags', {}).get('name:ko') or building.get('tags', {}).get('name')
        if name:
            x, y = pixels(building['centre'])
            draw.text((x, y), name, fill='#3c5651', font=regular, anchor='mm', stroke_width=2, stroke_fill='#fafcf9')
    draw.rectangle((0, 0, 1800, 100), fill='#fafcf9')
    draw.text((28, 13), '인하대학교 용현캠퍼스 · ' + ('가상 수거지점 검증' if example else '직접 배치용 실제 지도'), font=title, fill='#234b3d')
    draw.text((28, 58), '길·건물: OpenStreetMap 공개자료  |  쓰레기통·관리거점: 사용자 지정  |  1F = 캠퍼스 지상', font=small, fill='#556a60')
    if not example:
        for y in (240, 488, 700):
            draw.text((25, y), '배치 대기', font=regular, fill='#9a6a35')
        draw.text((26, 145), '표식을 실제 위치로 옮긴 뒤', font=small, fill='#6a756d')
        draw.text((26, 177), '교내 길과 연결하세요.', font=small, fill='#6a756d')
    draw.rectangle((0, 872, 1800, 920), fill='#fafcf9')
    draw.text((28, 885), '© OpenStreetMap contributors · ODbL 1.0 · openstreetmap.org/copyright · 2026-11-04', font=small, fill='#556a60')
    image.save(target, optimize=True)


def export(output: Path, font: Path) -> dict:
    data = campus_data()
    manual, example, manifest = build_workspaces(data)
    output.mkdir(parents=True, exist_ok=True)
    for suffix, state in [('manual', manual), ('example', example)]:
        image = output / f'inha-campus-{suffix}.png'
        draw_map(data, image, suffix == 'example', font)
        payload = {'format': 'reloop-backup-v1', 'created_at': state['updated_at'], 'workspace': state,
                   'images': {'1': base64.b64encode(image.read_bytes()).decode()}}
        (output / f'inha-campus-{suffix}.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    features = []
    for (a, b), way_ids in sorted(data['links'].items()):
        features.append({'type': 'Feature', 'properties': {'osm_way_ids': way_ids, 'from_node': a, 'to_node': b,
                         'distance_m': round(metres(data['nodes'][a], data['nodes'][b]), 3), 'source': 'OpenStreetMap'},
                         'geometry': {'type': 'LineString', 'coordinates': [[data['nodes'][i]['lon'], data['nodes'][i]['lat']] for i in (a, b)]}})
    (output / 'inha-walkways.geojson').write_text(json.dumps({'type': 'FeatureCollection', 'features': features}, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    with (output / 'example-sites.csv').open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=list(manifest['example_sites'][0]))
        writer.writeheader()
        writer.writerows(manifest['example_sites'])
    manifest['snapshot_sha256'] = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    (output / 'provenance.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'data' / 'inha-export')
    parser.add_argument('--font', type=Path, default=Path('C:/Windows/Fonts/malgun.ttf'))
    args = parser.parse_args()
    result = export(args.output, args.font)
    print(json.dumps({k: result[k] for k in ('road_nodes', 'road_edges', 'building_footprints', 'scale_m_per_unit')}))
    print(str(args.output.resolve()))
