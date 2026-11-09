"""Explicit local account consolidation; unrelated accounts keep separate workspaces."""
import json

from fastapi import HTTPException

from . import building_store


def install(db):
    db.execute('''CREATE TABLE IF NOT EXISTS account_aliases (
        user_id INTEGER PRIMARY KEY REFERENCES users(id),
        primary_user_id INTEGER NOT NULL REFERENCES users(id),
        merged_at TEXT NOT NULL,
        CHECK(user_id != primary_user_id)
    )''')


def primary_user(db, user_id):
    seen = set()
    while user_id not in seen:
        seen.add(user_id)
        alias = db.execute('SELECT primary_user_id FROM account_aliases WHERE user_id=?', (user_id,)).fetchone()
        if not alias:
            row = db.execute('SELECT id,email,name FROM users WHERE id=?', (user_id,)).fetchone()
            if row:
                return dict(row)
            break
        user_id = alias['primary_user_id']
    raise HTTPException(401, '계정 연결을 확인할 수 없습니다. 다시 로그인해 주세요.')


def merge(db, source_id, target_id, stamp, *, archive_ids=()):
    """Caller backs up the DB and holds a transaction. Preserve building IDs, states and keys.

    Only explicitly named duplicate buildings are archived. No names or email patterns trigger
    a merge, and no API grants one account access to another account's data.
    """
    target = primary_user(db, target_id)
    if source_id == target['id']:
        raise ValueError('동일한 계정을 통합할 수 없습니다.')
    existing = db.execute('SELECT primary_user_id FROM account_aliases WHERE user_id=?', (source_id,)).fetchone()
    if existing:
        if primary_user(db, source_id)['id'] == target['id']:
            return {'already_merged': True, 'primary_user_id': target['id'], 'moved_building_ids': []}
        raise ValueError('이미 다른 계정으로 통합된 계정입니다.')
    if not db.execute('SELECT id FROM users WHERE id=?', (source_id,)).fetchone():
        raise ValueError('통합할 계정을 찾을 수 없습니다.')
    rows = db.execute('SELECT id,deleted_at FROM buildings WHERE user_id=? ORDER BY id', (source_id,)).fetchall()
    archive_ids = set(archive_ids)
    if not archive_ids.issubset({row['id'] for row in rows}):
        raise ValueError('보관할 건물이 통합 대상 계정에 속하지 않습니다.')
    count = len(building_store.summaries(db, target['id'])) + sum(
        row['deleted_at'] is None and row['id'] not in archive_ids for row in rows)
    if count > building_store.LIMIT:
        raise ValueError('통합 후 관리 가능한 건물 수를 초과합니다.')
    if archive_ids:
        # Archived keys cannot keep writing after a building leaves the active list.
        for building_id in archive_ids:
            row = db.execute('SELECT state_json FROM buildings WHERE id=?', (building_id,)).fetchone()
            state = json.loads(row['state_json'])
            state['device_key_hint'] = None
            db.execute('UPDATE buildings SET deleted_at=COALESCE(deleted_at,?),device_key_hash=NULL,state_json=? WHERE id=?',
                       (stamp, json.dumps(state, ensure_ascii=False, allow_nan=False), building_id))
    db.execute('UPDATE buildings SET user_id=? WHERE user_id=?', (target['id'], source_id))
    db.execute('DELETE FROM building_selection WHERE user_id=?', (source_id,))
    db.execute('UPDATE sessions SET user_id=? WHERE user_id=?', (target['id'], source_id))
    db.execute('INSERT INTO account_aliases(user_id,primary_user_id,merged_at) VALUES(?,?,?)',
               (source_id, target['id'], stamp))
    building_store.choose(db, target['id'], building_store.selected(db, target['id']))
    return {'already_merged': False, 'primary_user_id': target['id'],
            'moved_building_ids': [row['id'] for row in rows], 'archived_building_ids': sorted(archive_ids)}
