"""Per-account buildings and the one-time migration from the original single workspace."""
import json

from fastapi import HTTPException

LIMIT = 20


def install(db, stamp):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS buildings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id),
            state_json TEXT NOT NULL, device_key_hash TEXT UNIQUE,
            created_at TEXT NOT NULL, deleted_at TEXT
        );
        CREATE INDEX IF NOT EXISTS buildings_user ON buildings(user_id, deleted_at);
        CREATE TABLE IF NOT EXISTS building_selection (
            user_id INTEGER PRIMARY KEY REFERENCES users(id),
            building_id INTEGER REFERENCES buildings(id)
        );
        CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY);
    ''')
    if not db.execute("SELECT 1 FROM schema_migrations WHERE name='multi-building-v1'").fetchone():
        legacy = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='workspaces'").fetchone()
        if legacy:
            for row in db.execute('SELECT user_id,state_json,device_key_hash FROM workspaces').fetchall():
                cursor = db.execute('INSERT INTO buildings(user_id,state_json,device_key_hash,created_at) VALUES(?,?,?,?)',
                                    (row['user_id'], row['state_json'], row['device_key_hash'], stamp))
                choose(db, row['user_id'], cursor.lastrowid)
        db.execute("INSERT INTO schema_migrations(name) VALUES('multi-building-v1')")


def owned(db, user_id, building_id, *, deleted=False):
    row = db.execute('SELECT * FROM buildings WHERE id=? AND user_id=? AND deleted_at IS ' +
                     ('NOT NULL' if deleted else 'NULL'), (building_id, user_id)).fetchone()
    if not row:
        raise HTTPException(404, '건물을 찾을 수 없습니다. 최신 건물 목록을 불러와 주세요.')
    return row


def selected(db, user_id):
    row = db.execute('SELECT b.id FROM building_selection s JOIN buildings b ON b.id=s.building_id '
                     'WHERE s.user_id=? AND b.user_id=? AND b.deleted_at IS NULL', (user_id, user_id)).fetchone()
    if row:
        return row['id']
    row = db.execute('SELECT id FROM buildings WHERE user_id=? AND deleted_at IS NULL ORDER BY id LIMIT 1',
                     (user_id,)).fetchone()
    return row['id'] if row else None


def choose(db, user_id, building_id):
    if building_id is not None:
        owned(db, user_id, building_id)
    db.execute('INSERT INTO building_selection(user_id,building_id) VALUES(?,?) '
               'ON CONFLICT(user_id) DO UPDATE SET building_id=excluded.building_id', (user_id, building_id))


def summaries(db, user_id, *, deleted=False):
    rows = db.execute('SELECT id,state_json,deleted_at FROM buildings WHERE user_id=? AND deleted_at IS ' +
                      ('NOT NULL' if deleted else 'NULL') + ' ORDER BY id', (user_id,)).fetchall()
    results = []
    for row in rows:
        state = json.loads(row['state_json'])
        results.append({'id': row['id'], 'name': state['building']['name'], 'floors': state['building']['floors'],
                        'basement_floors': state['building'].get('basement_floors', 0),
                        'bin_count': len(state['bins']), 'updated_at': state['updated_at'], 'deleted_at': row['deleted_at']})
    return results


def require_room(db, user_id):
    if db.execute('SELECT COUNT(*) FROM buildings WHERE user_id=? AND deleted_at IS NULL', (user_id,)).fetchone()[0] >= LIMIT:
        raise HTTPException(422, f'건물은 최대 {LIMIT}개까지 관리할 수 있습니다.')


def create(db, user_id, state, stamp):
    require_room(db, user_id)
    cursor = db.execute('INSERT INTO buildings(user_id,state_json,created_at) VALUES(?,?,?)',
                        (user_id, json.dumps(state, ensure_ascii=False, allow_nan=False), stamp))
    choose(db, user_id, cursor.lastrowid)
    return cursor.lastrowid
