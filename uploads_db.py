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
                bg REAL,
                ratio REAL,
                ct_bg_sum REAL,
                starred INTEGER DEFAULT 0 CHECK (starred IN (0, 1)),
                changed_field TEXT,
                changed_value TEXT,
                detail_json TEXT,
                date TEXT,
                time TEXT,
                timestamp TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS upload_meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()
    _ensure_schema_updates()
    _migrate_meta_json_if_needed()
    _migrate_to_dark_scale_if_needed()
    _migrate_detail_metrics_alignment_v2_if_needed()
    _migrate_precision_v3_if_needed()
    _migrate_bg_v4_if_needed()


def _ensure_schema_updates():
    conn = _get_conn()
    try:
        cols = conn.execute("PRAGMA table_info(upload_records)").fetchall()
        col_names = {row["name"] for row in cols}
        if "ct_bg_sum" not in col_names:
            conn.execute("ALTER TABLE upload_records ADD COLUMN ct_bg_sum REAL")
            conn.commit()
        if "bg" not in col_names:
            conn.execute("ALTER TABLE upload_records ADD COLUMN bg REAL")
            conn.commit()
        if "starred" not in col_names:
            conn.execute("ALTER TABLE upload_records ADD COLUMN starred INTEGER DEFAULT 0 CHECK (starred IN (0, 1))")
            conn.commit()
        if "changed_field" not in col_names:
            conn.execute("ALTER TABLE upload_records ADD COLUMN changed_field TEXT")
            conn.commit()
        if "changed_value" not in col_names:
            conn.execute("ALTER TABLE upload_records ADD COLUMN changed_value TEXT")
            conn.commit()
    finally:
        conn.close()


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


def _to_dark_value(v):
    if v is None:
        return None
    return float(255.0 - float(v))


def _r4(v):
    if v is None:
        return None
    return round(float(v), 4)


def _transform_detail_json_to_dark_scale(detail_json):
    if not detail_json:
        return detail_json
    try:
        detail = json.loads(detail_json)
    except Exception:
        return detail_json
    if not isinstance(detail, dict):
        return detail_json

    metrics = detail.get('metrics')
    if isinstance(metrics, dict):
        c_val = metrics.get('c')
        t_val = metrics.get('t')
        if c_val is not None:
            metrics['c'] = _r4(_to_dark_value(c_val))
        if t_val is not None:
            metrics['t'] = _r4(_to_dark_value(t_val))
        detail['metrics'] = metrics

    table_rows = detail.get('table_rows')
    if isinstance(table_rows, list):
        for row in table_rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get('name', '')).lower()
            if name in ('c', 't', 'background', 'line_1', 'line_2', 'line_3'):
                if row.get('gray_mean') is not None:
                    row['gray_mean'] = _r4(_to_dark_value(row.get('gray_mean')))
        detail['table_rows'] = table_rows

    return json.dumps(detail, ensure_ascii=False)


def _migrate_to_dark_scale_if_needed():
    conn = _get_conn()
    try:
        done_row = conn.execute(
            "SELECT value FROM upload_meta WHERE key = 'dark_scale_migrated_v1'"
        ).fetchone()
        if done_row and str(done_row['value']) == '1':
            return

        rows = conn.execute(
            "SELECT id, c, t, ct_bg_sum, detail_json FROM upload_records"
        ).fetchall()
        for row in rows:
            c_old = row['c']
            t_old = row['t']
            c_new = _r4(_to_dark_value(c_old)) if c_old is not None else None
            t_new = _r4(_to_dark_value(t_old)) if t_old is not None else None

            ct_bg_sum_new = row['ct_bg_sum']
            if ct_bg_sum_new is not None:
                ct_bg_sum_new = _r4(float(-1.0 * float(ct_bg_sum_new)))

            detail_json_new = _transform_detail_json_to_dark_scale(row['detail_json'])

            conn.execute(
                """
                UPDATE upload_records
                SET c = ?, t = ?, ct_bg_sum = ?, detail_json = ?
                WHERE id = ?
                """,
                (c_new, t_new, ct_bg_sum_new, detail_json_new, row['id']),
            )

        conn.execute(
            """
            INSERT INTO upload_meta (key, value)
            VALUES ('dark_scale_migrated_v1', '1')
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """
        )
        conn.commit()
    finally:
        conn.close()


def _migrate_detail_metrics_alignment_v2_if_needed():
    conn = _get_conn()
    try:
        done_row = conn.execute(
            "SELECT value FROM upload_meta WHERE key = 'detail_metrics_alignment_v2'"
        ).fetchone()
        if done_row and str(done_row['value']) == '1':
            return

        rows = conn.execute(
            "SELECT id, c, t, ratio, ct_bg_sum, detail_json FROM upload_records"
        ).fetchall()
        for row in rows:
            detail_json = row['detail_json']
            if not detail_json:
                continue
            try:
                detail = json.loads(detail_json)
            except Exception:
                continue
            if not isinstance(detail, dict):
                continue

            metrics = detail.get('metrics')
            if not isinstance(metrics, dict):
                continue

            metrics['c'] = _r4(row['c']) if row['c'] is not None else None
            metrics['t'] = _r4(row['t']) if row['t'] is not None else None
            metrics['ratio'] = _r4(row['ratio']) if row['ratio'] is not None else None
            metrics['ct_bg_sum'] = _r4(row['ct_bg_sum']) if row['ct_bg_sum'] is not None else None
            detail['metrics'] = metrics

            conn.execute(
                "UPDATE upload_records SET detail_json = ? WHERE id = ?",
                (json.dumps(detail, ensure_ascii=False), row['id']),
            )

        conn.execute(
            """
            INSERT INTO upload_meta (key, value)
            VALUES ('detail_metrics_alignment_v2', '1')
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """
        )
        conn.commit()
    finally:
        conn.close()


def _migrate_precision_v3_if_needed():
    conn = _get_conn()
    try:
        done_row = conn.execute(
            "SELECT value FROM upload_meta WHERE key = 'precision_4dp_v3'"
        ).fetchone()
        if done_row and str(done_row['value']) == '1':
            return

        rows = conn.execute(
            "SELECT id, c, t, ratio, ct_bg_sum, detail_json FROM upload_records"
        ).fetchall()
        for row in rows:
            c_new = _r4(row['c']) if row['c'] is not None else None
            t_new = _r4(row['t']) if row['t'] is not None else None
            ratio_new = _r4(row['ratio']) if row['ratio'] is not None else None
            ct_bg_sum_new = _r4(row['ct_bg_sum']) if row['ct_bg_sum'] is not None else None

            detail_json_new = row['detail_json']
            if detail_json_new:
                try:
                    detail = json.loads(detail_json_new)
                    if isinstance(detail, dict):
                        metrics = detail.get('metrics')
                        if isinstance(metrics, dict):
                            for k in ('c', 't', 'bg', 'ratio', 'ct_bg_sum'):
                                if metrics.get(k) is not None:
                                    metrics[k] = _r4(metrics[k])
                            detail['metrics'] = metrics
                        table_rows = detail.get('table_rows')
                        if isinstance(table_rows, list):
                            for tr in table_rows:
                                if isinstance(tr, dict) and tr.get('gray_mean') is not None:
                                    tr['gray_mean'] = _r4(tr['gray_mean'])
                            detail['table_rows'] = table_rows
                        detail_json_new = json.dumps(detail, ensure_ascii=False)
                except Exception:
                    pass

            conn.execute(
                """
                UPDATE upload_records
                SET c = ?, t = ?, ratio = ?, ct_bg_sum = ?, detail_json = ?
                WHERE id = ?
                """,
                (c_new, t_new, ratio_new, ct_bg_sum_new, detail_json_new, row['id']),
            )

        conn.execute(
            """
            INSERT INTO upload_meta (key, value)
            VALUES ('precision_4dp_v3', '1')
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """
        )
        conn.commit()
    finally:
        conn.close()


def _migrate_bg_v4_if_needed():
    conn = _get_conn()
    try:
        done_row = conn.execute(
            "SELECT value FROM upload_meta WHERE key = 'bg_backfill_v4'"
        ).fetchone()
        if done_row and str(done_row['value']) == '1':
            return

        rows = conn.execute(
            "SELECT id, bg, detail_json FROM upload_records"
        ).fetchall()
        for row in rows:
            if row['bg'] is not None:
                continue
            detail_json = row['detail_json']
            if not detail_json:
                continue
            try:
                detail = json.loads(detail_json)
            except Exception:
                continue
            if not isinstance(detail, dict):
                continue
            metrics = detail.get('metrics')
            if not isinstance(metrics, dict):
                continue
            bg_val = metrics.get('bg')
            if bg_val is None:
                continue
            conn.execute(
                "UPDATE upload_records SET bg = ? WHERE id = ?",
                (_r4(bg_val), row['id']),
            )

        conn.execute(
            """
            INSERT INTO upload_meta (key, value)
            VALUES ('bg_backfill_v4', '1')
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """
        )
        conn.commit()
    finally:
        conn.close()


def upsert_upload_record(entry):
    conn = _get_conn()
    try:
        conn.execute(
            """
            INSERT INTO upload_records (
                id, original_name, original_path, gray_path, cropped_name,
                cropped_path, dark_regions_path, c, t, bg, ratio, ct_bg_sum, starred, changed_field, changed_value, detail_json,
                date, time, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, 0), ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                original_name=excluded.original_name,
                original_path=excluded.original_path,
                gray_path=excluded.gray_path,
                cropped_name=excluded.cropped_name,
                cropped_path=excluded.cropped_path,
                dark_regions_path=excluded.dark_regions_path,
                c=excluded.c,
                t=excluded.t,
                bg=excluded.bg,
                ratio=excluded.ratio,
                ct_bg_sum=excluded.ct_bg_sum,
                starred=CASE
                    WHEN excluded.starred IS NULL THEN upload_records.starred
                    ELSE excluded.starred
                END,
                changed_field=excluded.changed_field,
                changed_value=excluded.changed_value,
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
                _r4(entry.get('c')) if entry.get('c') is not None else None,
                _r4(entry.get('t')) if entry.get('t') is not None else None,
                _r4(entry.get('bg')) if entry.get('bg') is not None else None,
                _r4(entry.get('ratio')) if entry.get('ratio') is not None else None,
                _r4(entry.get('ct_bg_sum')) if entry.get('ct_bg_sum') is not None else None,
                entry.get('starred'),
                entry.get('changed_field'),
                entry.get('changed_value'),
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
            SELECT id, c, t, bg, ratio, ct_bg_sum, date, time, starred, changed_field
            FROM upload_records
            ORDER BY date DESC, time DESC, id DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_starred_status(record_id):
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT starred FROM upload_records WHERE id = ?",
            (str(record_id),),
        ).fetchone()
        if row is None:
            return False
        return bool(row["starred"])
    finally:
        conn.close()


def set_starred_status(record_id, starred):
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE upload_records SET starred = ? WHERE id = ?",
            (1 if starred else 0, str(record_id)),
        )
        conn.commit()
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
