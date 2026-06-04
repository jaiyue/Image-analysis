# library.py — Library page with center‑based closest bars cropping

import streamlit as st
import pandas as pd
import base64
import sqlite3
import re
from image_processing import (
    process_image_to_grayscale,
    build_enhanced_detection_image,
    build_black_white_image,
    analyze_library_image,
)
from pathlib import Path
from datetime import datetime, date
from database import sync_experiment_db
from uploads_db import (
    init_uploads_db,
    upsert_upload_record,
    get_starred_status,
    set_starred_status,
)

try:
    from PIL import Image, ImageOps, UnidentifiedImageError
except Exception:
    Image = None
    UnidentifiedImageError = Exception


ASSETS_DIR = Path(__file__).parent / 'assets'
STAR_ICON_PATH = ASSETS_DIR / 'star.png'
YELLOW_STAR_ICON_PATH = ASSETS_DIR / 'yellow_star.png'
REMOVE_ICON_PATH = ASSETS_DIR / 'remove.png'
EXPERIMENT_DB_PATH = Path(__file__).parent / 'experiment_data.db'
ANALYSIS_CACHE_VERSION = 'v2'
PREPROCESS_CACHE_VERSION = 'v2'

CHANGED_FIELD_NAMES = [
    'sample_equivalent_mg_ml',
    'nitrocellulose_material',
    'cassette',
    'sample_pad_material',
    'sample_pad_pretreatment_lot',
    'conjugate_pad_material',
    'conjugate_pad_pretreatment_lot',
    'absorbent_pad_material',
    'running_buffer_lot',
    'glide_buffer_lot',
    'reconstitution_buffer_lot',
    'test_line_reagent',
    'test_line_concentration_mg_ml',
    'reference_line_reagent',
    'reference_line_concentration_mg_ml',
    'glide_volume_ul_per_cm',
    'conjugate_batch_name',
    'gnp_lot',
    'conjugate_loading_ul_per_cm',
    'stability_timepoint',
    'experiment_notes',
]

EXPERIMENT_DEFAULT_VALUES = {
    'operator': 'A.Li',
    'conjugate_pad_material': 'NGF66',
    'test_line_reagent': 'Bovine IgG',
    'reference_line_reagent': 'Chicken IgY',
    'reference_line_concentration_mg_ml': '0.2',
    'test_line_concentration_mg_ml': '0.45',
    'glide_volume_ul_per_cm': '2.5',
    'conjugate_loading_ul_per_cm': '80',
}

EXPERIMENT_FIELD_SPECS = [
    {'ui': 'nitrocellulose_material', 'db': 'nitrocellulose_material', 'kind': 'pad_select'},
    {'ui': 'cassette', 'db': 'cassette', 'kind': 'pad_select'},
    {'ui': 'sample_pad_material', 'db': 'sample_pad_material', 'kind': 'pad_select'},
    {'ui': 'sample_pad_pretreatment_lot', 'db': 'sample_pad_pretreatment_lot', 'kind': 'lot_select'},
    {'ui': 'conjugate_pad_material', 'db': 'conjugate_pad_material', 'kind': 'pad_select'},
    {'ui': 'conjugate_pad_pretreatment_lot', 'db': 'conjugate_pad_pretreatment_lot', 'kind': 'lot_select'},
    {'ui': 'absorbent_pad_material', 'db': 'absorbent_pad_material', 'kind': 'pad_select'},
    {'ui': 'running_buffer_lot', 'db': 'running_buffer_lot', 'kind': 'lot_select'},
    {'ui': 'glide_buffer_lot', 'db': 'glide_buffer_lot', 'kind': 'lot_select'},
    {'ui': 'reconstitution_buffer_lot', 'db': 'reconstitution_buffer_lot', 'kind': 'lot_select'},
    {'ui': 'test_line_reagent', 'db': 'test_line_reagent', 'kind': 'text'},
    {'ui': 'test_line_concentration_mg_ml', 'db': 'test_line_concentration_mg_ml', 'kind': 'number'},
    {'ui': 'reference_line_reagent', 'db': 'reference_line_reagent', 'kind': 'text'},
    {'ui': 'reference_line_concentration_mg_ml', 'db': 'reference_line_concentration_mg_ml', 'kind': 'number'},
    {'ui': 'glide_volume_ul_per_cm', 'db': 'glide_volume_ul_per_cm', 'kind': 'number'},
    {'ui': 'conjugate_batch_name', 'db': 'conjugate_batch_name', 'kind': 'conjugate_batch_select'},
    {'ui': 'gnp_lot', 'db': 'gnp_lot', 'kind': 'lot_select'},
    {'ui': 'conjugate_loading_ul_per_cm', 'db': 'conjugate_loading_ul_per_cm', 'kind': 'number'},
    {'ui': 'drying_time', 'db': 'drying_time', 'kind': 'text'},
    {'ui': 'storage_condition', 'db': 'storage_condition', 'kind': 'text'},
    {'ui': 'stability_timepoint', 'db': 'stability_timepoint', 'kind': 'text'},
    {'ui': 'experiment_notes', 'db': 'experiment_notes', 'kind': 'text'},
]


def _should_auto_star(analysis):
    return int(analysis.get('recrop_results_count', 0) or 0) != 2


def _normalize_cell_value(v):
    try:
        if pd.isna(v):
            return None
    except Exception:
        pass
    return v


def _update_experiment_row(conn, row_dict):
    if not row_dict or 'experiment_id' not in row_dict:
        return
    pk_value = row_dict.get('experiment_id')
    set_cols = [c for c in row_dict.keys() if c != 'experiment_id']
    if not set_cols:
        return
    set_sql = ', '.join([f'"{c}" = ?' for c in set_cols])
    values = [_normalize_cell_value(row_dict.get(c)) for c in set_cols]
    values.append(pk_value)
    conn.execute(
        f'UPDATE "experiments" SET {set_sql} WHERE "experiment_id" = ?',
        values,
    )

OPTIONAL_EXPERIMENT_FIELDS = {
    'stability_timepoint',
    'experiment_notes',
}

LOT_LINKED_TYPES = {
    'sample_pad_pretreatment_lot',
    'conjugate_pad_pretreatment_lot',
    'running_buffer_lot',
    'glide_buffer_lot',
    'reconstitution_buffer_lot',
    'gnp_lot',
}

PAD_LINKED_TYPES = {
    'nitrocellulose_material',
    'cassette',
    'sample_pad_material',
    'conjugate_pad_material',
    'absorbent_pad_material',
}


def _display_label(text):
    return str(text).replace('_', ' ')


def _is_missing_value(v):
    if v is None:
        return True
    try:
        if pd.isna(v):
            return True
    except Exception:
        pass
    return str(v).strip() == ''


def _suggest_changed_field_from_experiment_row(row_dict, changed_fields=None, experiment_specs=None):
    if not isinstance(row_dict, dict) or not row_dict:
        return None
    changed_fields = list(changed_fields or CHANGED_FIELD_NAMES)
    experiment_specs = list(experiment_specs or EXPERIMENT_FIELD_SPECS)
    changed_set = set(changed_fields)

    condition_val = str(row_dict.get('condition') or '').strip()
    if condition_val in changed_set:
        return condition_val
    condition_norm = condition_val.replace(' ', '_')
    if condition_norm in changed_set:
        return condition_norm

    ordered_fields = [spec['db'] for spec in experiment_specs if spec['db'] in changed_set]
    primary_fields = [f for f in ordered_fields if f not in OPTIONAL_EXPERIMENT_FIELDS]
    optional_fields = [f for f in ordered_fields if f in OPTIONAL_EXPERIMENT_FIELDS]

    for field in primary_fields:
        if _is_missing_value(row_dict.get(field)):
            return field

    for field in optional_fields:
        if _is_missing_value(row_dict.get(field)):
            return field

    return None


def _build_runtime_experiment_specs(db_col_names, reagent_lot_values, pad_material_values):
    specs = list(EXPERIMENT_FIELD_SPECS)
    existing = {s['db'] for s in specs}

    for lot_type in sorted(reagent_lot_values.keys()):
        t = str(lot_type).strip()
        if not t or t in existing or t not in db_col_names:
            continue
        specs.append({'ui': t, 'db': t, 'kind': 'lot_select'})
        existing.add(t)

    for material_type in sorted(pad_material_values.keys()):
        t = str(material_type).strip()
        if not t or t in existing or t not in db_col_names:
            continue
        specs.append({'ui': t, 'db': t, 'kind': 'pad_select'})
        existing.add(t)

    return specs


def _build_runtime_changed_fields(specs):
    changed = list(CHANGED_FIELD_NAMES)
    seen = set(changed)
    for spec in specs:
        ui = spec.get('ui')
        kind = spec.get('kind')
        if not ui or ui in seen:
            continue
        if kind in ('lot_select', 'pad_select'):
            changed.append(ui)
            seen.add(ui)
    return changed


@st.cache_data(show_spinner=False)
def _read_icon_base64(path_str):
    p = Path(path_str)
    if not p.exists():
        return ''
    return base64.b64encode(p.read_bytes()).decode('ascii')


def _build_star_button_label(starred):
    icon_path = YELLOW_STAR_ICON_PATH if starred else STAR_ICON_PATH
    icon_b64 = _read_icon_base64(str(icon_path))
    if not icon_b64:
        return '⭐' if starred else '☆'
    return f"![star](data:image/png;base64,{icon_b64})"


def _build_remove_button_label():
    icon_b64 = _read_icon_base64(str(REMOVE_ICON_PATH))
    if not icon_b64:
        return 'Delete'
    return f"![remove](data:image/png;base64,{icon_b64})"


@st.dialog('Confirm remove')
def _confirm_delete_experiments_dialog(experiment_ids):
    experiment_ids = [int(x) for x in experiment_ids if x is not None]
    if not experiment_ids:
        st.info('No experiment selected for removal.')
        return

    st.write('These experiment records will be deleted:')
    st.write(', '.join([str(x) for x in experiment_ids]))

    confirm_col, cancel_col = st.columns(2)
    with confirm_col:
        if st.button('Confirm', key='library_confirm_delete_experiments', width='stretch'):
            deleted = 0
            failed = []
            for rid in experiment_ids:
                try:
                    _delete_experiment(rid)
                    if st.session_state.get('library_selected_experiment_id') == rid:
                        st.session_state['library_selected_experiment_id'] = None
                    deleted += 1
                except Exception as e:
                    failed.append(str(e))
            st.session_state['library_pending_remove_experiment_ids'] = []
            st.session_state['library_existing_experiment_editor_nonce'] = (
                int(st.session_state.get('library_existing_experiment_editor_nonce', 0)) + 1
            )
            if deleted > 0:
                st.success(f'Deleted {deleted} experiment(s).')
            if failed:
                st.error('Failed to delete some rows: ' + '; '.join(failed))
            st.rerun()
    with cancel_col:
        if st.button('Cancel', key='library_cancel_delete_experiments', width='stretch'):
            st.session_state['library_pending_remove_experiment_ids'] = []
            st.session_state['library_existing_experiment_editor_nonce'] = (
                int(st.session_state.get('library_existing_experiment_editor_nonce', 0)) + 1
            )
            st.rerun()


def _extract_image_datetime(pil_img):
    try:
        exif = pil_img.getexif()
        for tag in (36867, 36868, 306):  # DateTimeOriginal, DateTimeDigitized, DateTime
            raw = exif.get(tag)
            if raw:
                return datetime.strptime(str(raw), '%Y:%m:%d %H:%M:%S')
    except Exception:
        pass
    try:
        info = getattr(pil_img, 'info', {}) or {}
        for key in ('date:create', 'date:modify', 'creation_time', 'timestamp'):
            raw = info.get(key)
            if not raw:
                continue
            text = str(raw).strip()
            for fmt in (
                '%Y-%m-%dT%H:%M:%S',
                '%Y-%m-%d %H:%M:%S',
                '%Y:%m:%d %H:%M:%S',
            ):
                try:
                    return datetime.strptime(text[:19], fmt)
                except Exception:
                    continue
    except Exception:
        pass
    return None


def _extract_datetime_from_filename(name):
    if not name:
        return None
    patterns = [
        (r'(\d{8})[_-](\d{6})', '%Y%m%d%H%M%S'),
        (r'(\d{8})(\d{6})', '%Y%m%d%H%M%S'),
        (r'(\d{4})[-_](\d{2})[-_](\d{2})[_-](\d{2})[-_](\d{2})[-_](\d{2})', None),
    ]
    for pattern, fmt in patterns:
        m = re.search(pattern, str(name))
        if not m:
            continue
        try:
            if fmt:
                return datetime.strptime(''.join(m.groups()), fmt)
            y, mo, d, hh, mm, ss = [int(x) for x in m.groups()]
            return datetime(y, mo, d, hh, mm, ss)
        except Exception:
            continue
    return None


def _get_latest_upload_date():
    if not EXPERIMENT_DB_PATH.exists():
        return date.today().isoformat()
    conn = None
    try:
        conn = sqlite3.connect(EXPERIMENT_DB_PATH)
        row = conn.execute(
            """
            SELECT SUBSTR(image_upload_datetime, 1, 10)
            FROM strip_results
            WHERE image_upload_datetime IS NOT NULL
              AND TRIM(image_upload_datetime) != ''
            ORDER BY image_upload_datetime DESC
            LIMIT 1
            """
        ).fetchone()
        if row and row[0]:
            return str(row[0])
    except Exception:
        pass
    finally:
        if conn is not None:
            conn.close()
    return date.today().isoformat()


def _load_existing_image_ids():
    ids = set()

    if EXPERIMENT_DB_PATH.exists():
        conn = sqlite3.connect(EXPERIMENT_DB_PATH)
        try:
            rows = conn.execute(
                """
                SELECT id
                FROM upload_records
                WHERE id IS NOT NULL AND TRIM(CAST(id AS TEXT)) != ''
                """
            ).fetchall()
            for r in rows:
                ids.add(str(r[0]).strip())
        except Exception:
            pass
        finally:
            conn.close()

    if EXPERIMENT_DB_PATH.exists():
        conn = sqlite3.connect(EXPERIMENT_DB_PATH)
        try:
            rows = conn.execute(
                """
                SELECT strip_id
                FROM strip_results
                WHERE strip_id IS NOT NULL AND TRIM(CAST(strip_id AS TEXT)) != ''
                """
            ).fetchall()
            for r in rows:
                ids.add(str(r[0]).strip())
        except Exception:
            pass
        finally:
            conn.close()

    return ids


def _load_existing_image_names():
    names = set()

    if not EXPERIMENT_DB_PATH.exists():
        return names

    conn = sqlite3.connect(EXPERIMENT_DB_PATH)
    try:
        rows = conn.execute(
            """
            SELECT original_name
            FROM upload_records
            WHERE original_name IS NOT NULL
              AND TRIM(original_name) != ''
            """
        ).fetchall()
        for r in rows:
            names.add(str(r[0]).strip())

        rows = conn.execute(
            """
            SELECT image_filename
            FROM strip_results
            WHERE image_filename IS NOT NULL
              AND TRIM(image_filename) != ''
            """
        ).fetchall()
        for r in rows:
            names.add(str(r[0]).strip())
    except Exception:
        pass
    finally:
        conn.close()

    return names


def _next_image_id(existing_ids):
    normalized_ids = set()
    for sid in existing_ids:
        s = str(sid).strip()
        if s.isdigit():
            normalized_ids.add(f'{int(s):05d}')
    candidate = 1
    while f'{candidate:05d}' in normalized_ids:
        candidate += 1
    return f'{candidate:05d}'


def _get_experiment_columns():
    if not EXPERIMENT_DB_PATH.exists():
        return []
    conn = sqlite3.connect(EXPERIMENT_DB_PATH)
    try:
        rows = conn.execute('PRAGMA table_info("experiments")').fetchall()
        return [
            {
                'name': r[1],
                'type': (r[2] or '').upper(),
                'not_null': bool(r[3]),
                'is_pk': bool(r[5]),
            }
            for r in rows
        ]
    finally:
        conn.close()


def _ensure_experiment_columns_for_dynamic_types():
    if not EXPERIMENT_DB_PATH.exists():
        return
    conn = sqlite3.connect(EXPERIMENT_DB_PATH)
    try:
        exp_cols = {r[1] for r in conn.execute('PRAGMA table_info("experiments")').fetchall()}
        if not exp_cols:
            return
        type_values = set()
        try:
            rows = conn.execute(
                """
                SELECT DISTINCT reagent_type
                FROM reagent_lots
                WHERE reagent_type IS NOT NULL
                  AND TRIM(reagent_type) != ''
                """
            ).fetchall()
            type_values.update([str(r[0]).strip() for r in rows if r and str(r[0]).strip()])
        except Exception:
            pass
        try:
            rows = conn.execute(
                """
                SELECT DISTINCT type
                FROM pad_material
                WHERE type IS NOT NULL
                  AND TRIM(type) != ''
                """
            ).fetchall()
            type_values.update([str(r[0]).strip() for r in rows if r and str(r[0]).strip()])
        except Exception:
            pass

        for col_name in sorted(type_values):
            if col_name in exp_cols:
                continue
            conn.execute(f'ALTER TABLE experiments ADD COLUMN "{col_name}" TEXT')
        conn.commit()
    finally:
        conn.close()


def _migrate_experiment_loading_column():
    # Experiments schema is centrally maintained in database.sync_experiment_db.
    return


def _migrate_experiment_fields_for_changed_form():
    # Experiments schema is centrally maintained in database.sync_experiment_db.
    return


def _insert_experiment(payload):
    conn = sqlite3.connect(EXPERIMENT_DB_PATH)
    try:
        cols = list(payload.keys())
        placeholders = ', '.join(['?'] * len(cols))
        cols_sql = ', '.join([f'"{c}"' for c in cols])
        query = f'INSERT INTO "experiments" ({cols_sql}) VALUES ({placeholders})'
        cur = conn.execute(query, [payload[c] for c in cols])
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _delete_experiment(experiment_id):
    conn = sqlite3.connect(EXPERIMENT_DB_PATH)
    try:
        conn.execute('PRAGMA foreign_keys = ON')
        conn.execute('DELETE FROM experiments WHERE experiment_id = ?', (int(experiment_id),))
        conn.commit()
    finally:
        conn.close()


def _link_saved_image_to_experiment(
    strip_id,
    experiment_id,
    changed_field,
    changed_value,
    sample_equivalent_mg_ml=None,
):
    conn = sqlite3.connect(EXPERIMENT_DB_PATH)
    try:
        exp_row = conn.execute(
            'SELECT 1 FROM experiments WHERE experiment_id = ?',
            (int(experiment_id),),
        ).fetchone()
        if not exp_row:
            return False, 'Selected experiment was not found in DB.'
        conn.execute(
            'UPDATE experiments SET condition = ? WHERE experiment_id = ?',
            (changed_field, int(experiment_id)),
        )
        if sample_equivalent_mg_ml is None:
            conn.execute(
                """
                UPDATE strip_results
                SET experiment_id = ?, changed_field = ?, condition_value = ?
                WHERE strip_id = ?
                """,
                (int(experiment_id), changed_field, changed_value, str(strip_id)),
            )
        else:
            conn.execute(
                """
                UPDATE strip_results
                SET experiment_id = ?, changed_field = ?, condition_value = ?, sample_equivalent_mg_ml = ?
                WHERE strip_id = ?
                """,
                (int(experiment_id), changed_field, changed_value, float(sample_equivalent_mg_ml), str(strip_id)),
            )
        conn.commit()
        return True, None
    finally:
        conn.close()


def _upsert_strip_results_snapshot(
    strip_id,
    image_filename,
    image_dt,
    changed_field,
    changed_value,
    c_val,
    t_val,
    bg_val,
    ratio_val,
    ct_bg_sum_val,
    vertical_crop_reason,
):
    conn = sqlite3.connect(EXPERIMENT_DB_PATH)
    try:
        timestamp = image_dt.isoformat(timespec='seconds') if image_dt else None
        reference_raw = float(c_val) if c_val is not None else None
        test_raw = float(t_val) if t_val is not None else None
        bg = float(bg_val) if bg_val is not None else None
        ratio = float(ratio_val) if ratio_val is not None else None
        ct_bg_sum = float(ct_bg_sum_val) if ct_bg_sum_val is not None else None
        reference_corrected = (reference_raw - bg) if (reference_raw is not None and bg is not None) else None
        test_corrected = (test_raw - bg) if (test_raw is not None and bg is not None) else None
        reference_test_ratio = None
        if ratio is not None and abs(ratio) > 1e-12:
            reference_test_ratio = 1.0 / ratio

        valid_strip = 1 if (test_corrected is not None and reference_corrected is not None) else 0
        failure_reason = None
        if not valid_strip:
            failure_reason = vertical_crop_reason or 'line_detection_incomplete'
        elif vertical_crop_reason and vertical_crop_reason not in ('ok', 'single_line_cropped'):
            failure_reason = vertical_crop_reason

        quality_flags = []
        if vertical_crop_reason and vertical_crop_reason != 'ok':
            quality_flags.append(vertical_crop_reason)
        if bg is None:
            quality_flags.append('missing_background')
        if ratio is None:
            quality_flags.append('missing_test_reference_ratio')
        quality_flags_text = ','.join(quality_flags) if quality_flags else None

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
                image_upload_datetime,
                anomaly_flag
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(strip_id) DO UPDATE SET
                changed_field = COALESCE(excluded.changed_field, strip_results.changed_field),
                condition_value = COALESCE(excluded.condition_value, strip_results.condition_value),
                test_line_raw_intensity = excluded.test_line_raw_intensity,
                reference_line_raw_intensity = excluded.reference_line_raw_intensity,
                test_line_corrected_intensity = excluded.test_line_corrected_intensity,
                reference_line_corrected_intensity = excluded.reference_line_corrected_intensity,
                test_reference_ratio = excluded.test_reference_ratio,
                reference_test_ratio = excluded.reference_test_ratio,
                overall_membrane_background = excluded.overall_membrane_background,
                ct_bg_sum = excluded.ct_bg_sum,
                valid_strip = excluded.valid_strip,
                failure_reason = excluded.failure_reason,
                quality_flags = excluded.quality_flags,
                image_filename = COALESCE(strip_results.image_filename, excluded.image_filename),
                image_upload_datetime = COALESCE(strip_results.image_upload_datetime, excluded.image_upload_datetime),
                anomaly_flag = COALESCE(strip_results.anomaly_flag, excluded.anomaly_flag)
            """,
            (
                str(strip_id),
                changed_field,
                (changed_value or '').strip() or None,
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
                image_filename,
                timestamp,
                0,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _load_experiments_df():
    if not EXPERIMENT_DB_PATH.exists():
        return pd.DataFrame()
    conn = sqlite3.connect(EXPERIMENT_DB_PATH)
    try:
        return pd.read_sql_query(
            'SELECT * FROM experiments ORDER BY experiment_id DESC',
            conn
        )
    finally:
        conn.close()


def _load_latest_experiment_row():
    if not EXPERIMENT_DB_PATH.exists():
        return {}
    conn = sqlite3.connect(EXPERIMENT_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT *
            FROM experiments
            ORDER BY experiment_id DESC
            LIMIT 1
            """
        ).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


def _load_experiment_title_options():
    if not EXPERIMENT_DB_PATH.exists():
        return []
    conn = sqlite3.connect(EXPERIMENT_DB_PATH)
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT experiment_title
            FROM experiments
            WHERE experiment_title IS NOT NULL
              AND TRIM(experiment_title) != ''
            ORDER BY experiment_title
            """
        ).fetchall()
        return [str(r[0]).strip() for r in rows if r and str(r[0]).strip()]
    finally:
        conn.close()


def _load_experiment_date_options():
    if not EXPERIMENT_DB_PATH.exists():
        return []
    conn = sqlite3.connect(EXPERIMENT_DB_PATH)
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT experiment_date
            FROM experiments
            WHERE experiment_date IS NOT NULL
              AND TRIM(experiment_date) != ''
            ORDER BY experiment_date DESC
            """
        ).fetchall()
        return [str(r[0]).strip() for r in rows if r and str(r[0]).strip()]
    finally:
        conn.close()


def _load_experiment_row_by_title(experiment_title):
    title = str(experiment_title or '').strip()
    if title == '' or not EXPERIMENT_DB_PATH.exists():
        return {}
    conn = sqlite3.connect(EXPERIMENT_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT *
            FROM experiments
            WHERE experiment_title = ?
            ORDER BY experiment_id DESC
            LIMIT 1
            """,
            (title,),
        ).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


def _apply_previous_experiment_to_form(
    baseline_row,
    experiment_specs,
    changed_options,
):
    baseline_row = dict(baseline_row or {})
    st.session_state['library_exp_experiment_title'] = ''
    if baseline_row.get('condition') in changed_options:
        st.session_state['library_exp_changed_selector'] = baseline_row.get('condition')
        st.session_state['library_changed_field'] = baseline_row.get('condition')
    for spec in experiment_specs:
        db_name = spec['db']
        raw_val = baseline_row.get(db_name)
        default_val = '' if raw_val is None else str(raw_val)
        if default_val == '':
            default_val = EXPERIMENT_DEFAULT_VALUES.get(db_name, '')

        if spec.get('kind') in ('lot_select', 'pad_select', 'conjugate_batch_select'):
            st.session_state[f'library_exp_{db_name}_select'] = default_val
        elif db_name == 'drying_time':
            m = re.match(r'^\s*([0-9]*\.?[0-9]+)\s*(nights?|days?)?\s*$', default_val, flags=re.IGNORECASE)
            st.session_state[f'library_exp_{db_name}_num'] = m.group(1) if m else ''
            unit = (m.group(2) or 'nights') if m else 'nights'
            unit = unit.lower()
            if unit not in ('nights', 'days'):
                unit = 'nights'
            st.session_state[f'library_exp_{db_name}_unit'] = unit
        elif db_name == 'storage_condition':
            m = re.match(r'^\s*([0-9]*\.?[0-9]+)\s*(°?\s*[cCfF]|o[cC])?\s*$', default_val)
            st.session_state[f'library_exp_{db_name}_num'] = m.group(1) if m else ''
            default_unit_raw = (m.group(2) or '').strip().lower() if m else ''
            st.session_state[f'library_exp_{db_name}_unit'] = '°F' if default_unit_raw in ('f', '°f') else '°C'
        else:
            st.session_state[f'library_exp_{db_name}'] = default_val


def _selectbox_with_state(container, label, options, key, default_index=0, format_func=None, label_visibility='visible'):
    kwargs = {
        'label': label,
        'options': options,
        'key': key,
        'label_visibility': label_visibility,
    }
    if format_func is not None:
        kwargs['format_func'] = format_func
    if key not in st.session_state:
        kwargs['index'] = default_index
    return container.selectbox(**kwargs)


def _multiselect_with_state(container, label, options, key, default_values=None, placeholder=None, label_visibility='visible'):
    kwargs = {
        'label': label,
        'options': options,
        'key': key,
        'label_visibility': label_visibility,
    }
    if placeholder is not None:
        kwargs['placeholder'] = placeholder
    if key not in st.session_state:
        kwargs['default'] = list(default_values or [])
    return container.multiselect(**kwargs)


def _text_input_with_state(container, label, key, default_value='', placeholder=''):
    kwargs = {
        'label': label,
        'key': key,
        'placeholder': placeholder,
    }
    if key not in st.session_state:
        kwargs['value'] = default_value
    return container.text_input(**kwargs)


def _date_input_with_state(container, label, key, default_value):
    kwargs = {
        'label': label,
        'key': key,
    }
    if key not in st.session_state:
        kwargs['value'] = default_value
    return container.date_input(**kwargs)


def _load_reagent_lot_values_by_type():
    out = {k: [] for k in LOT_LINKED_TYPES}
    if not EXPERIMENT_DB_PATH.exists():
        return out
    conn = sqlite3.connect(EXPERIMENT_DB_PATH)
    try:
        rows = conn.execute(
            """
            SELECT lot_name, reagent_type
            FROM reagent_lots
            WHERE lot_name IS NOT NULL
              AND TRIM(lot_name) != ''
              AND reagent_type IS NOT NULL
              AND TRIM(reagent_type) != ''
            ORDER BY lot_name
            """
        ).fetchall()
        for lot_name, reagent_type in rows:
            rt = str(reagent_type).strip()
            if rt == '':
                continue
            out.setdefault(rt, []).append(str(lot_name).strip())
    finally:
        conn.close()
    for k in out:
        # keep order but remove duplicates
        seen = set()
        deduped = []
        for v in out[k]:
            if v in seen:
                continue
            seen.add(v)
            deduped.append(v)
        out[k] = deduped
    return out


def _load_pad_material_values_by_type():
    out = {k: [] for k in PAD_LINKED_TYPES}
    if not EXPERIMENT_DB_PATH.exists():
        return out
    conn = sqlite3.connect(EXPERIMENT_DB_PATH)
    try:
        rows = conn.execute(
            """
            SELECT pad_name, type
            FROM pad_material
            WHERE pad_name IS NOT NULL
              AND TRIM(pad_name) != ''
              AND type IS NOT NULL
              AND TRIM(type) != ''
            ORDER BY pad_name
            """
        ).fetchall()
        for pad_name, pad_type in rows:
            t = str(pad_type).strip()
            if t == '':
                continue
            out.setdefault(t, []).append(str(pad_name).strip())
    finally:
        conn.close()
    for k in out:
        seen = set()
        deduped = []
        for v in out[k]:
            if v in seen:
                continue
            seen.add(v)
            deduped.append(v)
        out[k] = deduped
    return out


def _load_conjugate_batch_names():
    if not EXPERIMENT_DB_PATH.exists():
        return []
    conn = sqlite3.connect(EXPERIMENT_DB_PATH)
    try:
        rows = conn.execute(
            """
            SELECT conjugate_batch_name
            FROM conjugate_batch
            WHERE conjugate_batch_name IS NOT NULL
              AND TRIM(conjugate_batch_name) != ''
            ORDER BY conjugate_batch_name
            """
        ).fetchall()
        values = [str(r[0]).strip() for r in rows if r and str(r[0]).strip()]
    finally:
        conn.close()
    seen = set()
    deduped = []
    for v in values:
        if v in seen:
            continue
        seen.add(v)
        deduped.append(v)
    return deduped


def _render_experiment_selector():
    mode_row = st.columns([2.4, 2.2])
    with mode_row[0]:
        mode = st.radio(
            'Experiment mode',
            options=['New experiment', 'Exist experiment'],
            horizontal=True,
            key='library_experiment_mode',
            label_visibility='collapsed',
        )

    if mode == 'New experiment':
        cols = _get_experiment_columns()
        if not cols:
            st.warning('experiments table not found in experiment_data.db.')
            return

        db_cols = {c['name']: c for c in cols}
        reagent_lot_values = _load_reagent_lot_values_by_type()
        pad_material_values = _load_pad_material_values_by_type()
        experiment_specs = _build_runtime_experiment_specs(
            db_col_names=set(db_cols.keys()),
            reagent_lot_values=reagent_lot_values,
            pad_material_values=pad_material_values,
        )
        changed_options = _build_runtime_changed_fields(experiment_specs)
        st.session_state['library_changed_field_options'] = changed_options

        required_db_fields = ['experiment_title', 'operator', 'experiment_date', 'condition'] + [f['db'] for f in experiment_specs]
        missing_db_fields = [name for name in required_db_fields if name not in db_cols]
        if missing_db_fields:
            st.error(
                'Missing experiments columns: '
                + ', '.join([_display_label(x) for x in missing_db_fields])
            )
            return

        latest_row = _load_latest_experiment_row()
        has_baseline = bool(latest_row)
        conjugate_batch_names = _load_conjugate_batch_names()
        previous_experiment_titles = _load_experiment_title_options()

        if not has_baseline:
            st.info('No baseline experiment found. Please fill all fields once.')

        previous_none_label = 'previous experiment:None'
        previous_options = [previous_none_label] + previous_experiment_titles
        with mode_row[1]:
            previous_title = _selectbox_with_state(
                st,
                'previous experiment',
                previous_options,
                key='library_previous_experiment_title',
                default_index=0,
                label_visibility='collapsed',
            )
        previous_title_value = '' if previous_title == previous_none_label else previous_title
        previous_row = _load_experiment_row_by_title(previous_title_value) if previous_title_value else {}
        baseline_row = previous_row if previous_row else latest_row

        previous_applied_key = 'library_previous_experiment_applied_title'
        prev_applied_title = st.session_state.get(previous_applied_key, None)
        current_apply_title = previous_title_value if previous_title_value else '__latest__'
        if prev_applied_title != current_apply_title:
            _apply_previous_experiment_to_form(
                baseline_row=baseline_row,
                experiment_specs=experiment_specs,
                changed_options=changed_options,
            )
            st.session_state[previous_applied_key] = current_apply_title

        form_values = {}
        title_col, changed_col, date_col = st.columns(3)
        form_values['experiment_title'] = _text_input_with_state(
            title_col,
            'experiment title *',
            key='library_exp_experiment_title',
            default_value='',
            placeholder='not empty',
        )

        changed_default = st.session_state.get('library_exp_changed_selector', st.session_state.get('library_changed_field', changed_options[0]))
        if changed_default not in changed_options:
            changed_default = changed_options[0]
        changed_ui = _selectbox_with_state(
            changed_col,
            'changed',
            changed_options,
            key='library_exp_changed_selector',
            default_index=changed_options.index(changed_default),
            format_func=_display_label,
        )
        st.session_state['library_changed_field'] = changed_ui
        form_values['experiment_date'] = _date_input_with_state(
            date_col,
            'experiment date *',
            key='library_exp_experiment_date',
            default_value=date.today(),
        )

        show_specs = [s for s in experiment_specs if s['ui'] != changed_ui]

        for i in range(0, len(show_specs), 3):
            row_cols = st.columns(3)
            for j, spec in enumerate(show_specs[i:i + 3]):
                ui_label = spec['ui']
                db_name = spec['db']
                latest_val = baseline_row.get(db_name)
                default_val = '' if latest_val is None else str(latest_val)
                if default_val == '':
                    default_val = EXPERIMENT_DEFAULT_VALUES.get(db_name, '')
                field_required = db_name not in OPTIONAL_EXPERIMENT_FIELDS
                display_name = _display_label(ui_label)
                label = f'{display_name} *' if field_required else display_name
                placeholder = 'not empty' if field_required else 'optional'

                if spec.get('kind') == 'lot_select':
                    options = list(reagent_lot_values.get(ui_label, []))
                    if default_val and default_val not in options:
                        options.append(default_val)
                    if not options:
                        options = ['']
                    default_idx = options.index(default_val) if default_val in options else 0
                    form_values[db_name] = _selectbox_with_state(
                        row_cols[j],
                        label,
                        options,
                        key=f'library_exp_{db_name}_select',
                        default_index=default_idx,
                    )
                elif spec.get('kind') == 'pad_select':
                    options = list(pad_material_values.get(ui_label, []))
                    if default_val and default_val not in options:
                        options.append(default_val)
                    if not options:
                        options = ['']
                    default_idx = options.index(default_val) if default_val in options else 0
                    form_values[db_name] = _selectbox_with_state(
                        row_cols[j],
                        label,
                        options,
                        key=f'library_exp_{db_name}_select',
                        default_index=default_idx,
                    )
                elif spec.get('kind') == 'conjugate_batch_select':
                    options = list(conjugate_batch_names)
                    if default_val and default_val not in options:
                        options.append(default_val)
                    if not options:
                        options = ['']
                    default_idx = options.index(default_val) if default_val in options else 0
                    form_values[db_name] = _selectbox_with_state(
                        row_cols[j],
                        label,
                        options,
                        key=f'library_exp_{db_name}_select',
                        default_index=default_idx,
                    )
                elif db_name == 'drying_time':
                    m = re.match(r'^\s*([0-9]*\.?[0-9]+)\s*(nights?|days?)?\s*$', default_val, flags=re.IGNORECASE)
                    default_num = m.group(1) if m else ''
                    default_unit = (m.group(2) or 'nights') if m else 'nights'
                    default_unit = default_unit.lower()
                    if default_unit not in ('nights', 'days'):
                        default_unit = 'nights'
                    dt_num_col, dt_unit_col = row_cols[j].columns([2, 2])
                    drying_num = _text_input_with_state(
                        dt_num_col,
                        label,
                        key=f'library_exp_{db_name}_num',
                        default_value=default_num,
                        placeholder=placeholder,
                    )
                    drying_unit = _selectbox_with_state(
                        dt_unit_col,
                        'unit',
                        ['nights', 'days'],
                        key=f'library_exp_{db_name}_unit',
                        default_index=0 if default_unit == 'nights' else 1,
                    )
                    form_values[db_name] = (f'{drying_num.strip()} {drying_unit}' if (drying_num or '').strip() else '')
                elif db_name == 'storage_condition':
                    m = re.match(r'^\s*([0-9]*\.?[0-9]+)\s*(°?\s*[cCfF]|o[cC])?\s*$', default_val)
                    default_num = m.group(1) if m else ''
                    default_unit_raw = (m.group(2) or '').strip().lower() if m else ''
                    if default_unit_raw in ('f', '°f'):
                        default_unit = '°F'
                    else:
                        default_unit = '°C'
                    sc_num_col, sc_unit_col = row_cols[j].columns([2, 1])
                    storage_num = _text_input_with_state(
                        sc_num_col,
                        label,
                        key=f'library_exp_{db_name}_num',
                        default_value=default_num,
                        placeholder=placeholder,
                    )
                    storage_unit = _selectbox_with_state(
                        sc_unit_col,
                        'unit',
                        ['°C', '°F'],
                        key=f'library_exp_{db_name}_unit',
                        default_index=0 if default_unit == '°C' else 1,
                    )
                    form_values[db_name] = (f'{storage_num.strip()} {storage_unit}' if (storage_num or '').strip() else '')
                else:
                    form_values[db_name] = _text_input_with_state(
                        row_cols[j],
                        label,
                        key=f'library_exp_{db_name}',
                        default_value=default_val,
                        placeholder=placeholder,
                    )

        save_clicked = st.button('Save experiment', key='library_save_experiment', width='content')

        if save_clicked:
            title = (form_values.get('experiment_title') or '').strip()
            if title == '':
                st.error('Not empty required: experiment_title')
                return

            payload = {'experiment_date': form_values['experiment_date'].isoformat()}
            payload['experiment_title'] = title
            payload['condition'] = changed_ui
            payload['operator'] = (baseline_row.get('operator') or latest_row.get('operator') or 'A.Li')

            # Start from baseline to avoid refilling unchanged items.
            if has_baseline:
                for spec in experiment_specs:
                    db_name = spec['db']
                    if db_name in baseline_row:
                        payload[db_name] = baseline_row.get(db_name)

            if changed_ui in payload:
                payload[changed_ui] = None

            missing = []
            convert_errors = []
            target_specs = [s for s in experiment_specs if s['ui'] != changed_ui]

            for spec in target_specs:
                ui_label = spec['ui']
                db_name = spec['db']
                raw = form_values.get(db_name)
                raw_text = (raw or '').strip()
                field_required = db_name not in OPTIONAL_EXPERIMENT_FIELDS
                if raw_text == '' and field_required:
                    missing.append(ui_label)
                    continue
                if raw_text == '' and not field_required:
                    payload[db_name] = None
                    continue

                if db_name == 'drying_time':
                    m = re.match(r'^\s*([0-9]*\.?[0-9]+)\s+(nights|days)\s*$', raw_text, flags=re.IGNORECASE)
                    if not m:
                        convert_errors.append(f'{ui_label} expects number + nights/days.')
                    else:
                        payload[db_name] = f"{m.group(1)} {m.group(2).lower()}"
                elif db_name == 'storage_condition':
                    m = re.match(r'^\s*([0-9]*\.?[0-9]+)\s+(°[cCfF]|[cCfF]|oc)\s*$', raw_text, flags=re.IGNORECASE)
                    if not m:
                        convert_errors.append(f'{ui_label} expects number + °C/°F.')
                    else:
                        unit_raw = m.group(2).lower()
                        unit = '°F' if unit_raw in ('f', '°f') else '°C'
                        payload[db_name] = f"{m.group(1)} {unit}"
                elif spec['kind'] == 'number':
                    try:
                        payload[db_name] = float(raw_text)
                    except ValueError:
                        convert_errors.append(f'{ui_label} expects a numeric value.')
                else:
                    payload[db_name] = raw_text

            if missing:
                st.error(f'Not empty required: {", ".join(missing)}')
            elif convert_errors:
                st.error('; '.join(convert_errors))
            else:
                try:
                    inserted_id = _insert_experiment(payload)
                    if inserted_id:
                        st.session_state['library_selected_experiment_id'] = int(inserted_id)
                    st.success('Experiment saved.')
                    st.rerun()
                except Exception as e:
                    st.error(f'Failed to save experiment: {e}')
    else:
        date_options = _load_experiment_date_options()
        title_options = _load_experiment_title_options()
        date_placeholder = 'Choose date(Optional)'
        today_text = date.today().isoformat()
        existing_date_options = [date_placeholder] + date_options
        default_date_index = existing_date_options.index(today_text) if today_text in existing_date_options else 0
        with mode_row[1]:
            filter_cols = st.columns([1, 1.2])
            selected_date = _selectbox_with_state(
                filter_cols[0],
                'experiment date filter',
                existing_date_options,
                key='library_existing_experiment_date_filter',
                default_index=default_date_index,
                label_visibility='collapsed',
            )
            selected_titles = _multiselect_with_state(
                filter_cols[1],
                'experiment title filter',
                title_options,
                key='library_existing_experiment_title_filter',
                default_values=[],
                placeholder='Experiment title',
                label_visibility='collapsed',
            )

        cols = _get_experiment_columns()
        db_col_names = {c['name'] for c in cols} if cols else set()
        reagent_lot_values = _load_reagent_lot_values_by_type()
        pad_material_values = _load_pad_material_values_by_type()
        experiment_specs = _build_runtime_experiment_specs(
            db_col_names=db_col_names,
            reagent_lot_values=reagent_lot_values,
            pad_material_values=pad_material_values,
        )
        changed_options = _build_runtime_changed_fields(experiment_specs)
        st.session_state['library_changed_field_options'] = changed_options

        exp_df = _load_experiments_df()
        if exp_df.empty:
            st.info('No experiments found.')
            return
        if selected_date != date_placeholder and 'experiment_date' in exp_df.columns:
            exp_df = exp_df[exp_df['experiment_date'].astype(str) == selected_date]
            if exp_df.empty:
                st.info('No experiments matched the selected date.')
                return
        if selected_titles and 'experiment_title' in exp_df.columns:
            selected_title_set = {str(v).strip() for v in selected_titles if str(v).strip()}
            exp_df = exp_df[exp_df['experiment_title'].astype(str).isin(selected_title_set)]
            if exp_df.empty:
                st.info('No experiments matched the selected title filter.')
                return

        existing_selected_id = st.session_state.get('library_selected_experiment_id')
        if existing_selected_id is not None:
            try:
                sid = int(existing_selected_id)
                hit = exp_df[exp_df['experiment_id'] == sid]
                if not hit.empty:
                    suggested_changed = _suggest_changed_field_from_experiment_row(
                        hit.iloc[0].to_dict(),
                        changed_fields=changed_options,
                        experiment_specs=experiment_specs,
                    )
                    if suggested_changed:
                        st.session_state['library_changed_field'] = suggested_changed
            except Exception:
                pass

        selected_id = st.session_state.get('library_selected_experiment_id')
        display_df = exp_df.copy()
        # Keep column order synced with current experiments table schema.
        schema_order = [c['name'] for c in cols if c['name'] in display_df.columns]
        if schema_order:
            display_df = display_df[schema_order]
        display_df.insert(0, 'remove', False)
        display_df.insert(0, 'select', display_df['experiment_id'] == selected_id)

        editor_nonce = int(st.session_state.get('library_existing_experiment_editor_nonce', 0))
        edit_key = 'library_existing_experiment_edit_mode'
        prev_edit_key = 'library_existing_experiment_prev_edit_mode'
        cache_key = 'library_existing_experiment_editor_cache'
        prev_edit_mode = bool(st.session_state.get(prev_edit_key, False))
        header_cols = st.columns([1.15, 0.85, 6])
        header_cols[0].write('Exist experiment')
        edit_mode = header_cols[1].toggle('Edit table', key=edit_key)
        st.session_state[prev_edit_key] = bool(edit_mode)
        pending_remove_ids = st.session_state.get('library_pending_remove_experiment_ids', [])
        if pending_remove_ids:
            _confirm_delete_experiments_dialog(pending_remove_ids)

        if prev_edit_mode and not edit_mode:
            edited_cache_df = st.session_state.get(cache_key)
            if edited_cache_df is not None and not edited_cache_df.empty:
                try:
                    conn = sqlite3.connect(EXPERIMENT_DB_PATH)
                    for _, row in edited_cache_df.iterrows():
                        row_dict = {
                            k: _normalize_cell_value(v)
                            for k, v in row.to_dict().items()
                            if k not in ('select', 'remove')
                        }
                        _update_experiment_row(conn, row_dict)
                    conn.commit()
                    st.success('Experiment table changes saved.')
                    exp_df = _load_experiments_df()
                    if selected_date != date_placeholder and 'experiment_date' in exp_df.columns:
                        exp_df = exp_df[exp_df['experiment_date'].astype(str) == selected_date]
                    if selected_titles and 'experiment_title' in exp_df.columns:
                        selected_title_set = {str(v).strip() for v in selected_titles if str(v).strip()}
                        exp_df = exp_df[exp_df['experiment_title'].astype(str).isin(selected_title_set)]
                    display_df = exp_df.copy()
                    if schema_order:
                        display_df = display_df[schema_order]
                    display_df.insert(0, 'remove', False)
                    display_df.insert(0, 'select', display_df['experiment_id'] == selected_id)
                    editor_nonce += 1
                    st.session_state['library_existing_experiment_editor_nonce'] = editor_nonce
                except Exception as e:
                    st.error(f'Failed to save experiment table changes: {e}')
                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass

        col_config = {
            'select': st.column_config.CheckboxColumn('select', width='small'),
            'remove': st.column_config.CheckboxColumn('remove', width='small'),
        }
        for col in display_df.columns:
            if col in ('select', 'remove'):
                continue
            col_config[col] = st.column_config.Column(_display_label(col))

        edited = st.data_editor(
            display_df,
            hide_index=True,
            width='stretch',
            key=f'library_existing_experiment_editor_{editor_nonce}',
            column_config=col_config,
            disabled=(
                ['experiment_id']
                if edit_mode
                else [c for c in display_df.columns if c not in ('select', 'remove')]
            ),
        )
        if edit_mode:
            st.session_state[cache_key] = edited.copy()

        remove_rows = edited[edited['remove'] == True]  # noqa: E712
        if not remove_rows.empty:
            st.session_state['library_pending_remove_experiment_ids'] = [
                int(r['experiment_id']) for _, r in remove_rows.iterrows()
            ]
            _confirm_delete_experiments_dialog(st.session_state['library_pending_remove_experiment_ids'])

        selected_rows = edited[edited['select'] == True]  # noqa: E712
        prev_selected = st.session_state.get('library_selected_experiment_id')
        if len(selected_rows) > 1:
            selected_candidates = [int(x) for x in selected_rows['experiment_id'].tolist()]
            if prev_selected in selected_candidates and len(selected_candidates) > 1:
                fallback = [x for x in selected_candidates if x != prev_selected]
                new_selected = fallback[0] if fallback else selected_candidates[0]
            else:
                new_selected = selected_candidates[0]
            st.session_state['library_selected_experiment_id'] = new_selected
            st.session_state['library_existing_experiment_editor_nonce'] = editor_nonce + 1
            st.rerun()
        elif len(selected_rows) == 1:
            new_selected = int(selected_rows.iloc[0]['experiment_id'])
            st.session_state['library_selected_experiment_id'] = new_selected
            if prev_selected != new_selected:
                st.session_state['library_existing_experiment_editor_nonce'] = editor_nonce + 1
                st.rerun()

            exp_row_dict = None
            try:
                hit = exp_df[exp_df['experiment_id'] == new_selected]
                if not hit.empty:
                    exp_row_dict = hit.iloc[0].to_dict()
            except Exception:
                exp_row_dict = None
            suggested_changed = _suggest_changed_field_from_experiment_row(
                exp_row_dict,
                changed_fields=changed_options,
                experiment_specs=experiment_specs,
            )
            if suggested_changed:
                st.session_state['library_changed_field'] = suggested_changed

            st.caption(f'Selected experiment id: {new_selected}')
        else:
            if prev_selected is not None:
                st.caption(f'Selected experiment id: {prev_selected}')
            else:
                st.caption('No experiment selected.')


def render_library_page():
    st.subheader('Library')
    st.markdown(
        """
        <style>
        div[data-testid="stButton"] button:has(img[alt="star"]) {
            border: none !important;
            background: transparent !important;
            box-shadow: none !important;
            padding: 0 !important;
            min-height: auto !important;
            line-height: 1 !important;
        }
        div[data-testid="stButton"] button:has(img[alt="star"]):hover {
            background: transparent !important;
        }
        div[data-testid="stButton"] button:has(img[alt="star"]) img {
            width: 20px !important;
            height: 20px !important;
            display: block !important;
        }
        div[data-testid="stButton"] button:has(img[alt="remove"]) {
            border: none !important;
            background: transparent !important;
            box-shadow: none !important;
            padding: 0 !important;
            min-height: auto !important;
            line-height: 1 !important;
        }
        div[data-testid="stButton"] button:has(img[alt="remove"]):hover {
            background: transparent !important;
        }
        div[data-testid="stButton"] button:has(img[alt="remove"]) img {
            width: 16px !important;
            height: 16px !important;
            display: block !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    uploads_dir = Path(__file__).parent / 'uploads'
    uploads_dir.mkdir(exist_ok=True)
    init_uploads_db()
    sync_experiment_db()
    _ensure_experiment_columns_for_dynamic_types()
    _migrate_experiment_loading_column()
    _migrate_experiment_fields_for_changed_form()
    _render_experiment_selector()
    st.divider()

    uploaded_files = st.file_uploader(
        'Upload images or CSV files',
        accept_multiple_files=True,
        type=['png', 'jpg', 'jpeg', 'gif', 'tif', 'tiff', 'csv']
    )

    if 'library_id_counter' not in st.session_state:
        st.session_state['library_id_counter'] = 0
    if 'library_file_ids' not in st.session_state:
        st.session_state['library_file_ids'] = {}
    if 'library_preprocess_cache' not in st.session_state:
        st.session_state['library_preprocess_cache'] = {}
    if st.session_state.get('library_preprocess_cache_version') != PREPROCESS_CACHE_VERSION:
        st.session_state['library_preprocess_cache'] = {}
        st.session_state['library_preprocess_cache_version'] = PREPROCESS_CACHE_VERSION
    if 'library_analysis_cache' not in st.session_state:
        st.session_state['library_analysis_cache'] = {}
    if 'library_written_files' not in st.session_state:
        st.session_state['library_written_files'] = set()

    if not uploaded_files:
        st.info('No files uploaded yet. Use the uploader to add images or CSVs.')
        return

    current_file_sigs = {
        f"{uploaded.name}::{getattr(uploaded, 'size', None)}"
        for uploaded in uploaded_files
        if not (uploaded.name.lower().endswith('.csv') or uploaded.type == 'text/csv')
    }
    st.session_state['library_file_ids'] = {
        sig: image_id
        for sig, image_id in st.session_state['library_file_ids'].items()
        if sig in current_file_sigs
    }

    images = []
    tables = []
    existing_image_names = _load_existing_image_names()
    batch_seen_names = set()
    reserved_ids = _load_existing_image_ids().union(set(st.session_state['library_file_ids'].values()))

    for uploaded in uploaded_files:
        name = uploaded.name
        if name.lower().endswith('.csv') or uploaded.type == 'text/csv':
            try:
                df = pd.read_csv(uploaded)
                tables.append((name, df))
            except Exception as e:
                st.warning(f'Could not read CSV {name}: {e}')
        else:
            clean_name = str(name).strip()
            if clean_name in batch_seen_names:
                st.warning(f'Image name already exists in current upload: {clean_name}')
                continue
            if clean_name in existing_image_names:
                st.warning(f'Image name already exists: {clean_name}')
                continue
            batch_seen_names.add(clean_name)
            if Image is None:
                st.warning('Pillow is not available: cannot display images.')
                break
            try:
                file_size = getattr(uploaded, 'size', None)
                file_sig = f"{name}::{file_size}"
                if file_sig not in st.session_state['library_file_ids']:
                    next_id = _next_image_id(reserved_ids)
                    st.session_state['library_file_ids'][file_sig] = next_id
                    reserved_ids.add(next_id)
                img_id = st.session_state['library_file_ids'][file_sig]
                prep_cache = st.session_state['library_preprocess_cache']
                if file_sig in prep_cache:
                    cached = prep_cache[file_sig]
                    img = cached['img']
                    gray = cached['gray']
                    enhanced = cached['enhanced']
                    black_white = cached['black_white']
                    image_dt = cached['image_dt']
                else:
                    src_img = Image.open(uploaded)
                    image_dt = _extract_image_datetime(src_img)
                    src_img = ImageOps.exif_transpose(src_img)
                    if image_dt is None:
                        image_dt = _extract_image_datetime(src_img)
                    if image_dt is None:
                        image_dt = _extract_datetime_from_filename(name)
                    img = src_img.convert('RGB')
                    gray = process_image_to_grayscale(img.copy())
                    enhanced = build_enhanced_detection_image(gray)
                    black_white = build_black_white_image(enhanced)
                    prep_cache[file_sig] = {
                        'img': img,
                        'gray': gray,
                        'enhanced': enhanced,
                        'black_white': black_white,
                        'image_dt': image_dt,
                    }

                images.append((img_id, name, img, gray, enhanced, black_white, image_dt, file_sig))
            except UnidentifiedImageError:
                st.warning(f'File {name} is not a recognized image.')
            except Exception as e:
                st.warning(f'Failed to open {name}: {e}')

    if images:
        st.subheader('Images')
        changed_options = st.session_state.get('library_changed_field_options', CHANGED_FIELD_NAMES)
        if not changed_options:
            changed_options = list(CHANGED_FIELD_NAMES)
        selected_changed_field = st.session_state.get('library_changed_field', changed_options[0])
        if selected_changed_field not in changed_options:
            selected_changed_field = changed_options[0]
        st.session_state['library_changed_field'] = selected_changed_field

        for row_idx, (img_id, name, img, gray, enhanced, black_white, image_dt, file_sig) in enumerate(images):
            row_key = f'{img_id}_{row_idx}'
            cropped_overlay = None
            recrop_overlay = None
            c_val = None
            t_val = None
            bg_val = None
            ratio_val = None
            ct_bg_sum_val = None
            analysis_key = f'{ANALYSIS_CACHE_VERSION}::{file_sig}'
            analysis_cache = st.session_state['library_analysis_cache']
            if analysis_key in analysis_cache:
                analysis = analysis_cache[analysis_key]
            else:
                analysis = analyze_library_image(gray)
                analysis_cache[analysis_key] = analysis
            cropped = analysis["cropped"]
            vertical_overlay = analysis["vertical_overlay"]
            cropped_between = analysis["cropped_between"]
            analysis_img_trimmed = analysis["analysis_img_trimmed"]
            cropped_overlay = analysis["cropped_overlay"]
            recrop_overlay = analysis["recrop_overlay"]
            table_rows = analysis["table_rows"]
            c_val = analysis["c"]
            t_val = analysis["t"]
            bg_val = analysis.get("bg")
            ratio_val = analysis["ratio"]
            ct_bg_sum_val = analysis.get("ct_bg_sum")
            vertical_crop_reason = analysis["vertical_crop_reason"]
            trim_percent_used = analysis.get("trim_percent_used", 20)
            auto_starred = _should_auto_star(analysis)
            stored_starred = get_starred_status(img_id)
            effective_starred = bool(stored_starred or auto_starred)

            cols = st.columns([1, 2, 4])
            with cols[0]:
                mark_col, id_col = st.columns([1, 3])
                with mark_col:
                    if st.button(
                        _build_star_button_label(effective_starred),
                        key=f'lib_star_{row_key}',
                        width='content',
                        type='tertiary',
                    ):
                        stored_starred = not effective_starred
                        set_starred_status(img_id, stored_starred)
                        effective_starred = bool(stored_starred or auto_starred)
                with id_col:
                    st.markdown(f"ID\n\n`{img_id}`")

            if recrop_overlay is not None:
                with cols[1]:
                    st.image(
                        recrop_overlay,
                        caption=f"Dark Line Regions Re-Crop — {name}",
                        width=240
                    )
                with cols[2]:
                    table_df = pd.DataFrame(table_rows)
                    if {'name', 'gray_mean'}.issubset(table_df.columns):
                        mean_only_df = table_df[['name', 'gray_mean']].rename(
                            columns={'gray_mean': 'dark value'}
                        )
                        st.dataframe(mean_only_df, width='stretch')
                    else:
                        st.info('No dark value table available.')
            else:
                with cols[1]:
                    st.info(f"No dark line regions detected: {name}")
                with cols[2]:
                    st.empty()

            image_changed_value = cols[2].text_input(
                f'{_display_label(selected_changed_field)} *',
                key=f'library_img_changed_value_{selected_changed_field}_{row_key}',
                placeholder='not empty',
            )
            save_image_clicked = cols[2].button(
                'Save',
                key=f'library_save_image_{row_key}',
                width='content',
            )

            # Persist metadata
            try:
                original_filename = f'{img_id}_original.png'
                gray_filename = f'{img_id}_gray.png'
                cropped_filename = f'{img_id}_cropped.png'
                cropped_vertical_filename = f'{img_id}_cropped_vertical.png'
                cropped_trimmed_filename = f'{img_id}_cropped_trimmed.png'
                dark_filename = f'{img_id}_dark_regions.png'
                recrop_filename = f'{img_id}_recrop.png'
                vertical_crop_filename = f'{img_id}_vertical_crop.png'
                original_path = uploads_dir / original_filename
                gray_path = uploads_dir / gray_filename
                cropped_path = uploads_dir / cropped_filename
                cropped_vertical_path = uploads_dir / cropped_vertical_filename
                cropped_trimmed_path = uploads_dir / cropped_trimmed_filename
                dark_path = uploads_dir / dark_filename
                recrop_path = uploads_dir / recrop_filename
                vertical_crop_path = uploads_dir / vertical_crop_filename
                needs_file_write = file_sig not in st.session_state['library_written_files']
                if needs_file_write:
                    img.save(original_path)
                    gray.save(gray_path)
                    cropped.save(cropped_path)
                    vertical_overlay.save(cropped_vertical_path)
                    analysis_img_trimmed.save(cropped_trimmed_path)
                    if cropped_between is not None:
                        cropped_between.save(vertical_crop_path)
                    if cropped_overlay is not None:
                        cropped_overlay.save(dark_path)
                    if recrop_overlay is not None:
                        recrop_overlay.save(recrop_path)
                    st.session_state['library_written_files'].add(file_sig)

                now = image_dt
                detail_payload = {
                    'images': {
                        'original_path': str(original_path),
                        'gray_path': str(gray_path),
                        'cropped_path': str(cropped_path),
                        'cropped_vertical_path': str(cropped_vertical_path) if cropped_vertical_path.exists() else '',
                        'cropped_trimmed_path': str(cropped_trimmed_path) if cropped_trimmed_path.exists() else '',
                        'vertical_crop_path': str(vertical_crop_path) if vertical_crop_path.exists() else '',
                        'dark_regions_path': str(dark_path) if cropped_overlay is not None else '',
                        'recrop_path': str(recrop_path) if recrop_path.exists() else '',
                    },
                    'vertical_crop_reason': vertical_crop_reason,
                    'trim_percent_used': trim_percent_used,
                    'recrop_results_count': int(analysis.get('recrop_results_count', 0) or 0),
                }
                entry = {
                    'id': img_id,
                    'original_name': name,
                    'original_path': str(original_path),
                    'gray_path': str(gray_path),
                    'cropped_name': cropped_filename,
                    'cropped_path': str(cropped_path),
                    'dark_regions_path': str(dark_path) if cropped_overlay is not None else '',
                    'starred': 1 if effective_starred else 0,
                    'detail': detail_payload,
                }
                upsert_upload_record(entry)
                _upsert_strip_results_snapshot(
                    strip_id=img_id,
                    image_filename=name,
                    image_dt=now,
                    changed_field=selected_changed_field,
                    changed_value=image_changed_value,
                    c_val=(round(float(c_val), 4) if c_val is not None else None),
                    t_val=(round(float(t_val), 4) if t_val is not None else None),
                    bg_val=(round(float(bg_val), 4) if bg_val is not None else None),
                    ratio_val=(round(float(ratio_val), 4) if ratio_val is not None else None),
                    ct_bg_sum_val=(round(float(ct_bg_sum_val), 4) if ct_bg_sum_val is not None else None),
                    vertical_crop_reason=vertical_crop_reason,
                )

                if save_image_clicked:
                    selected_exp_id = st.session_state.get('library_selected_experiment_id')
                    if selected_exp_id is None:
                        cols[2].error('Please save/select an experiment first.')
                    elif (image_changed_value or '').strip() == '':
                        cols[2].error(f'Not empty required: {selected_changed_field}')
                    else:
                        try:
                            selected_exp_id = int(selected_exp_id)
                            sample_equivalent_value = None
                            if selected_changed_field == 'sample_equivalent_mg_ml':
                                sample_equivalent_value = float((image_changed_value or '').strip())
                            sync_experiment_db(default_experiment_id=selected_exp_id)
                            linked_ok = _link_saved_image_to_experiment(
                                strip_id=img_id,
                                experiment_id=selected_exp_id,
                                changed_field=selected_changed_field,
                                changed_value=image_changed_value.strip(),
                                sample_equivalent_mg_ml=sample_equivalent_value,
                            )
                            if linked_ok[0]:
                                cols[2].success(f'Saved to DB: image {img_id} -> experiment {selected_exp_id}')
                            else:
                                cols[2].error(linked_ok[1] or 'Failed to save to DB.')
                        except ValueError:
                            if selected_changed_field == 'sample_equivalent_mg_ml':
                                cols[2].error('sample equivalent mg ml must be a number.')
                            else:
                                cols[2].error(f'Invalid value: {selected_changed_field}')
                        except Exception as e:
                            cols[2].error(f'Failed to save to experiment_data.db: {e}')
            except Exception:
                st.warning('Failed to save cropped image or write to upload_records')

    if tables:
        st.subheader('Datasets')
        for name, df in tables:
            st.write(f'Preview — {name}')
            st.dataframe(df.head(50))
