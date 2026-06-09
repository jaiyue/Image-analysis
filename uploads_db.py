import json
import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent
EXPERIMENT_DB_PATH = PROJECT_ROOT / 'experiment_data.db'
UPLOAD_RECORD_BASE_COLUMNS = [
    'id',
    'original_name',
    'original_path',
    'gray_path',
    'cropped_name',
    'cropped_path',
    'dark_regions_path',
    'starred',
    'detail_json',
]


def _get_conn():
    conn = sqlite3.connect(EXPERIMENT_DB_PATH)
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
                starred INTEGER DEFAULT 0 CHECK (starred IN (0, 1)),
                detail_json TEXT
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
    _migrate_upload_records_schema_v2()
    _ensure_schema_updates()
    _migrate_meta_json_if_needed()
    _migrate_to_dark_scale_if_needed()
    _migrate_detail_metrics_alignment_v2_if_needed()
    _migrate_precision_v3_if_needed()
    _migrate_bg_v4_if_needed()
    backfill_existing_detection_states()


def _migrate_upload_records_schema_v2():
    conn = _get_conn()
    conn.row_factory = sqlite3.Row
    try:
        cols = conn.execute('PRAGMA table_info("upload_records")').fetchall()
        col_names = [row['name'] for row in cols]
        legacy_data_cols = {
            'c', 't', 'bg', 'ratio', 'ct_bg_sum',
            'changed_field', 'changed_value', 'date', 'time', 'timestamp',
        }
        if not any(name in legacy_data_cols for name in col_names):
            return

        from database import ensure_core_schema

        ensure_core_schema(conn)
        rows = conn.execute('SELECT * FROM upload_records').fetchall()
        for row in rows:
            data = dict(row)
            strip_id = str(data.get('id') or '').strip()
            if strip_id == '':
                continue

            timestamp = data.get('timestamp')
            if not timestamp:
                raw_date = data.get('date')
                raw_time = data.get('time')
                timestamp = f'{raw_date}T{raw_time}' if raw_date and raw_time else None

            reference_raw = data.get('c')
            test_raw = data.get('t')
            bg = data.get('bg')
            ratio = data.get('ratio')
            ct_bg_sum = data.get('ct_bg_sum')
            reference_corrected = (reference_raw - bg) if (reference_raw is not None and bg is not None) else None
            test_corrected = (test_raw - bg) if (test_raw is not None and bg is not None) else None
            reference_test_ratio = None
            if ratio is not None:
                try:
                    ratio_val = float(ratio)
                    if abs(ratio_val) > 1e-12:
                        reference_test_ratio = 1.0 / ratio_val
                except Exception:
                    reference_test_ratio = None

            detail = {}
            try:
                detail = json.loads(data.get('detail_json') or '{}')
            except Exception:
                detail = {}
            vertical_crop_reason = detail.get('vertical_crop_reason') if isinstance(detail, dict) else None
            line_detection_status = detail.get('line_detection_status') if isinstance(detail, dict) else None
            confidence_score = detail.get('confidence_score') if isinstance(detail, dict) else None
            detail_quality_flags = detail.get('quality_flags') if isinstance(detail, dict) else []
            if not isinstance(detail_quality_flags, list):
                detail_quality_flags = []
            valid_strip = 1 if (
                test_corrected is not None
                and reference_corrected is not None
                and line_detection_status != 'failed'
            ) else 0
            failure_reason = None
            if not valid_strip:
                failure_reason = line_detection_status or vertical_crop_reason or 'line_detection_incomplete'
            elif vertical_crop_reason and vertical_crop_reason not in ('ok', 'single_line_cropped'):
                failure_reason = vertical_crop_reason

            quality_flags = []
            if vertical_crop_reason and vertical_crop_reason != 'ok':
                quality_flags.append(vertical_crop_reason)
            if bg is None:
                quality_flags.append('missing_background')
            if ratio is None:
                quality_flags.append('missing_test_reference_ratio')
            if line_detection_status and line_detection_status != 'good':
                quality_flags.append(line_detection_status)
            if confidence_score is not None:
                try:
                    if float(confidence_score) < 0.70:
                        quality_flags.append('low_detection_confidence')
                except Exception:
                    pass
            quality_flags.extend(detail_quality_flags)
            quality_flags_text = ','.join(sorted(set(quality_flags))) if quality_flags else None

            conn.execute(
                """
                INSERT INTO strip_results (
                    strip_id,
                    changed_field,
                    condition_value,
                    test_line_raw_intensity,
                    reference_line_raw_intensity,
                    test_line_corrected_intensity,
                    reference_line_corrected_intensity,
                    test_reference_ratio,
                    reference_test_ratio,
                    overall_membrane_background,
                    ct_bg_sum,
                    valid_strip,
                    failure_reason,
                    quality_flags,
                    image_filename,
                    image_upload_datetime
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(strip_id) DO UPDATE SET
                    changed_field = COALESCE(excluded.changed_field, strip_results.changed_field),
                    condition_value = COALESCE(excluded.condition_value, strip_results.condition_value),
                    test_line_raw_intensity = COALESCE(strip_results.test_line_raw_intensity, excluded.test_line_raw_intensity),
                    reference_line_raw_intensity = COALESCE(strip_results.reference_line_raw_intensity, excluded.reference_line_raw_intensity),
                    test_line_corrected_intensity = COALESCE(strip_results.test_line_corrected_intensity, excluded.test_line_corrected_intensity),
                    reference_line_corrected_intensity = COALESCE(strip_results.reference_line_corrected_intensity, excluded.reference_line_corrected_intensity),
                    test_reference_ratio = COALESCE(strip_results.test_reference_ratio, excluded.test_reference_ratio),
                    reference_test_ratio = COALESCE(strip_results.reference_test_ratio, excluded.reference_test_ratio),
                    overall_membrane_background = COALESCE(strip_results.overall_membrane_background, excluded.overall_membrane_background),
                    ct_bg_sum = COALESCE(strip_results.ct_bg_sum, excluded.ct_bg_sum),
                    valid_strip = COALESCE(strip_results.valid_strip, excluded.valid_strip),
                    failure_reason = COALESCE(strip_results.failure_reason, excluded.failure_reason),
                    quality_flags = COALESCE(strip_results.quality_flags, excluded.quality_flags),
                    image_filename = COALESCE(strip_results.image_filename, excluded.image_filename),
                    image_upload_datetime = COALESCE(strip_results.image_upload_datetime, excluded.image_upload_datetime)
                """,
                (
                    strip_id,
                    data.get('changed_field'),
                    data.get('changed_value'),
                    test_raw,
                    reference_raw,
                    test_corrected,
                    reference_corrected,
                    ratio,
                    reference_test_ratio,
                    bg,
                    ct_bg_sum,
                    valid_strip,
                    failure_reason,
                    quality_flags_text,
                    data.get('original_name'),
                    timestamp,
                ),
            )

        conn.execute('ALTER TABLE upload_records RENAME TO upload_records_old')
        conn.execute(
            """
            CREATE TABLE upload_records (
                id TEXT PRIMARY KEY,
                original_name TEXT,
                original_path TEXT,
                gray_path TEXT,
                cropped_name TEXT,
                cropped_path TEXT,
                dark_regions_path TEXT,
                starred INTEGER DEFAULT 0 CHECK (starred IN (0, 1)),
                detail_json TEXT
            )
            """
        )
        common = [name for name in UPLOAD_RECORD_BASE_COLUMNS if name in col_names]
        if common:
            cols_sql = ', '.join([f'"{name}"' for name in common])
            conn.execute(
                f'''
                INSERT INTO upload_records ({cols_sql})
                SELECT {cols_sql}
                FROM upload_records_old
                '''
            )
        conn.execute('DROP TABLE upload_records_old')
        conn.commit()
    finally:
        conn.close()


def _ensure_schema_updates():
    conn = _get_conn()
    try:
        cols = conn.execute("PRAGMA table_info(upload_records)").fetchall()
        col_names = {row["name"] for row in cols}
        if "starred" not in col_names:
            conn.execute("ALTER TABLE upload_records ADD COLUMN starred INTEGER DEFAULT 0 CHECK (starred IN (0, 1))")
            conn.commit()
        if "detail_json" not in col_names:
            conn.execute("ALTER TABLE upload_records ADD COLUMN detail_json TEXT")
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


def _get_upload_meta_value(conn, key):
    row = conn.execute(
        'SELECT value FROM upload_meta WHERE key = ?',
        (str(key),),
    ).fetchone()
    if row is None:
        return None
    return row['value']


def _set_upload_meta_value(conn, key, value):
    conn.execute(
        """
        INSERT INTO upload_meta (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (str(key), None if value is None else str(value)),
    )


def _resolve_existing_upload_image_path(record_id, original_path, original_name=None):
    candidates = []
    record_text = str(record_id or '').strip()
    if record_text:
        candidates.extend([
            PROJECT_ROOT / 'uploads' / f'{record_text}_original.png',
            PROJECT_ROOT / 'uploads' / f'{record_text}_original.jpg',
            PROJECT_ROOT / 'uploads' / f'{record_text}.png',
            PROJECT_ROOT / 'uploads' / f'{record_text}.jpg',
        ])
    for raw in (original_path, original_name):
        text = str(raw or '').strip()
        if text:
            candidates.append(Path(text))
            candidates.append(PROJECT_ROOT / 'uploads' / Path(text).name)
    seen = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except Exception:
            resolved = candidate
        if resolved in seen:
            continue
        seen.add(resolved)
        try:
            if candidate.exists() and candidate.is_file():
                return candidate
        except Exception:
            continue
    return None


def backfill_existing_detection_states(force=False):
    conn = _get_conn()
    conn.row_factory = sqlite3.Row
    try:
        if not force and _get_upload_meta_value(conn, 'detection_state_backfill_v1') == 'done':
            return 0

        rows = conn.execute(
            """
            SELECT id, original_name, original_path, detail_json, starred
            FROM upload_records
            ORDER BY CAST(id AS INTEGER), id
            """
        ).fetchall()

        if not rows:
            _set_upload_meta_value(conn, 'detection_state_backfill_v1', 'done')
            conn.commit()
            return 0

        from PIL import Image
        from image_processing import analyze_library_image, process_image_to_grayscale

        updated = 0
        for row in rows:
            record_id = str(row['id'] or '').strip()
            if not record_id:
                continue

            try:
                detail = json.loads(row['detail_json'] or '{}')
            except Exception:
                detail = {}
            if not isinstance(detail, dict):
                detail = {}

            current_status = str(detail.get('line_detection_status') or '').strip().lower()
            original_path = detail.get('images', {}).get('original_path') if isinstance(detail.get('images'), dict) else None
            image_path = _resolve_existing_upload_image_path(
                record_id,
                original_path or row['original_path'],
                row['original_name'],
            )

            analysis = None
            if (force or current_status not in {'good', 'needs_review', 'failed'}) and image_path is not None:
                try:
                    with Image.open(image_path) as src_img:
                        original_img = src_img.convert('RGB')
                    gray = process_image_to_grayscale(original_img.copy())
                    analysis = analyze_library_image(gray)
                    current_status = str(analysis.get('line_detection_status') or '').strip().lower()
                    detail['vertical_crop_reason'] = analysis.get('vertical_crop_reason', detail.get('vertical_crop_reason', ''))
                    detail['line_detection_status'] = analysis.get('line_detection_status', '')
                    detail['confidence_score'] = analysis.get('confidence_score', 0.0)
                    detail['quality_flags'] = list(analysis.get('quality_flags', []) or [])
                    detail['line_candidates'] = list(analysis.get('line_candidates', []) or [])
                    detail['selected_line_count'] = int(analysis.get('selected_line_count', 0) or 0)
                    detail['trim_percent_used'] = int(analysis.get('trim_percent_used', 20) or 20)
                    detail['recrop_results_count'] = int(analysis.get('recrop_results_count', 0) or 0)
                except Exception:
                    analysis = None
                    current_status = ''

            starred_value = 1 if current_status == 'failed' else 0
            existing_starred = int(row['starred'] or 0)
            detail_json_text = json.dumps(detail, ensure_ascii=False)

            if detail_json_text != (row['detail_json'] or '') or existing_starred != starred_value:
                conn.execute(
                    """
                    UPDATE upload_records
                    SET starred = ?, detail_json = ?
                    WHERE id = ?
                    """,
                    (starred_value, detail_json_text, record_id),
                )
                updated += 1

        _set_upload_meta_value(conn, 'detection_state_backfill_v1', 'done')
        conn.commit()
        return updated
    finally:
        conn.close()


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
    return


def _migrate_detail_metrics_alignment_v2_if_needed():
    return


def _migrate_precision_v3_if_needed():
    return


def _migrate_bg_v4_if_needed():
    return


def upsert_upload_record(entry):
    conn = _get_conn()
    try:
        conn.execute(
            """
            INSERT INTO upload_records (
                id, original_name, original_path, gray_path, cropped_name,
                cropped_path, dark_regions_path, starred, detail_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, COALESCE(?, 0), ?)
            ON CONFLICT(id) DO UPDATE SET
                original_name=excluded.original_name,
                original_path=excluded.original_path,
                gray_path=excluded.gray_path,
                cropped_name=excluded.cropped_name,
                cropped_path=excluded.cropped_path,
                dark_regions_path=excluded.dark_regions_path,
                starred=CASE
                    WHEN excluded.starred IS NULL THEN upload_records.starred
                    ELSE excluded.starred
                END,
                detail_json=excluded.detail_json
            """,
            (
                str(entry.get('id', '')),
                entry.get('original_name'),
                entry.get('original_path'),
                entry.get('gray_path'),
                entry.get('cropped_name'),
                entry.get('cropped_path'),
                entry.get('dark_regions_path'),
                entry.get('starred'),
                json.dumps(entry.get('detail', {}), ensure_ascii=False),
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
            SELECT
                sr.strip_id AS id,
                sr.experiment_id AS experiment_id,
                sr.reference_line_raw_intensity AS c,
                sr.test_line_raw_intensity AS t,
                sr.overall_membrane_background AS bg,
                sr.test_reference_ratio AS ratio,
                sr.ct_bg_sum AS ct_bg_sum,
                CASE WHEN sr.image_upload_datetime IS NOT NULL THEN SUBSTR(sr.image_upload_datetime, 1, 10) END AS date,
                CASE
                    WHEN sr.image_upload_datetime IS NOT NULL AND LENGTH(sr.image_upload_datetime) >= 19
                    THEN SUBSTR(sr.image_upload_datetime, 12, 8)
                END AS time,
                COALESCE(ur.starred, 0) AS starred,
                COALESCE(json_extract(ur.detail_json, '$.line_detection_status'), '') AS line_detection_status,
                exp.experiment_title AS experiment_title,
                exp.condition AS experiment_condition,
                sr.changed_field AS changed_field,
                sr.condition_value AS changed_value
            FROM strip_results sr
            LEFT JOIN upload_records ur
              ON ur.id = sr.strip_id
            LEFT JOIN experiments exp
              ON exp.experiment_id = sr.experiment_id
            ORDER BY
                CASE
                    WHEN sr.strip_id GLOB '[0-9]*' THEN CAST(sr.strip_id AS INTEGER)
                    ELSE NULL
                END DESC,
                sr.strip_id DESC
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


def update_upload_detail(record_id, detail):
    conn = _get_conn()
    try:
        conn.execute(
            """
            UPDATE upload_records
            SET detail_json = ?
            WHERE id = ?
            """,
            (json.dumps(detail or {}, ensure_ascii=False), str(record_id)),
        )
        conn.commit()
    finally:
        conn.close()
