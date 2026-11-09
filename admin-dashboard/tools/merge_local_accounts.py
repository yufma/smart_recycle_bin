"""Back up and explicitly consolidate two accounts in the same local SQLite server.

Run after stopping the server. A preview is the default; --apply makes the named change.
Only explicitly listed duplicate buildings leave the active list; their layouts remain recoverable.
"""
import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from server import account_store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--from-email', required=True)
    parser.add_argument('--into-email', required=True)
    parser.add_argument('--archive-building-id', type=int, action='append', default=[])
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    data_dir = args.data_dir.resolve()
    db = sqlite3.connect(f'file:{(data_dir / "reloop.sqlite3").as_posix()}?mode=rw', uri=True)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    try:
        source = db.execute('SELECT id,name,email FROM users WHERE email=?', (args.from_email.strip().lower(),)).fetchone()
        target = db.execute('SELECT id,name,email FROM users WHERE email=?', (args.into_email.strip().lower(),)).fetchone()
        if not source or not target or source['id'] == target['id']:
            raise ValueError('서로 다른 기존 계정 두 곳을 지정해 주세요.')
        preview = {'source': dict(source), 'target': dict(target), 'archive_building_ids': args.archive_building_id,
                   'buildings': [{'id': row['id'], 'owner': row['user_id'],
                                  'name': json.loads(row['state_json'])['building']['name'],
                                  'archived': bool(row['deleted_at'])}
                                 for row in db.execute('SELECT id,user_id,state_json,deleted_at FROM buildings '
                                                       'WHERE user_id IN (?,?) ORDER BY id', (source['id'], target['id']))]}
        if not args.apply:
            print(json.dumps(preview, ensure_ascii=False, indent=2))
            return
        stamp = datetime.now(timezone.utc)
        recovery = data_dir.parent / 'recovery-accounts'
        recovery.mkdir(exist_ok=True)
        backup = recovery / ('before-account-merge-' + stamp.strftime('%Y%m%d-%H%M%S-%f') + '.sqlite3')
        with sqlite3.connect(backup) as snapshot:
            db.backup(snapshot)
        account_store.install(db)
        db.commit()
        with db:
            db.execute('BEGIN IMMEDIATE')
            result = account_store.merge(db, source['id'], target['id'], stamp.isoformat(),
                                         archive_ids=args.archive_building_id)
        report = {'backup': str(backup), **preview, 'result': result}
        backup.with_suffix('.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'backup': str(backup), **result}, ensure_ascii=False))
    finally:
        db.close()


if __name__ == '__main__':
    main()
