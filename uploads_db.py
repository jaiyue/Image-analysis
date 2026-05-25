import json
import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent
UPLOADS_DB_PATH = PROJECT_ROOT / 'uploads.db'


def _get_conn():
    conn = sqlite3.connect(UPLOADS_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_uploads_db():
    conn = _get_conn()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS upload_records (
                id TEXT PRIMARY KEY,
                original_name TEXT,
                original_path TEXT,
                gray_path TEXT,
                cropped_name TEXT,
                cropped_path TEXT,
                dark_regions_path TEXT,
                c REAL,
                t REAL,
                ratio REAL,
                detail_json TEXT,
                date TEXT,
                time TEXT,
                timestamp TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()
    _migrate_meta_json_if_needed()


def _migrate_meta_json_if_needed():
    conn = _get_conn()
    try:
        count_row = conn.execute("SELECT COUNT(*) AS n FROM upload_records").fetchone()
        existing_count = int(count_row["n"]) if count_row else 0
    finally:
        conn.close()

    if existing_count > 0:
        return

    legacy_meta_path = PROJECT_ROOT / 'uploads' / 'meta.json'
    if not legacy_meta_path.exists():
        return

    try:
        with legacy_meta_path.open('r', encoding='utf-8') as f:
            legacy_rows = json.load(f)
        if not isinstance(legacy_rows, list):
            return
    except Exception:
        return

    for row in legacy_rows:
        if not isinstance(row, dict):
            continue
        upsert_upload_record(row)


def upsert_upload_record(entry):
    conn = _get_conn()
    try:
        conn.execute(
            """
            INSERT INTO upload_records (
                id, original_name, original_path, gray_path, cropped_name,
                cropped_path, dark_regions_path, c, t, ratio, detail_json,
                date, time, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                original_name=excluded.original_name,
                original_path=excluded.original_path,
                gray_path=excluded.gray_path,
                cropped_name=excluded.cropped_name,
                cropped_path=excluded.cropped_path,
                dark_regions_path=excluded.dark_regions_path,
                c=excluded.c,
                t=excluded.t,
                ratio=excluded.ratio,
                detail_json=excluded.detail_json,
                date=excluded.date,
                time=excluded.time,
                timestamp=excluded.timestamp
            """,
            (
                str(entry.get('id', '')),
                entry.get('original_name'),
                entry.get('original_path'),
                entry.get('gray_path'),
                entry.get('cropped_name'),
                entry.get('cropped_path'),
                entry.get('dark_regions_path'),
                entry.get('c'),
                entry.get('t'),
                entry.get('ratio'),
                json.dumps(entry.get('detail', {}), ensure_ascii=False),
                entry.get('date'),
                entry.get('time'),
                entry.get('timestamp'),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def list_insight_rows():
    conn = _get_conn()
    try:
        rows = conn.execute(
            """
            SELECT id, c, t, ratio, date, time
            FROM upload_records
            ORDER BY date DESC, time DESC, id DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_upload_detail_by_id(detail_id):
    conn = _get_conn()
    try:
        row = conn.execute(
            """
            SELECT *
            FROM upload_records
            WHERE id = ?
            """,
            (str(detail_id),),
        ).fetchone()
        if row is None:
            return None
        data = dict(row)
        detail_json = data.get('detail_json') or '{}'
        try:
            data['detail'] = json.loads(detail_json)
        except Exception:
            data['detail'] = {}
        return data
    finally:
        conn.close()
