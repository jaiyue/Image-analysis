# library.py — Library page with center‑based closest bars cropping

import streamlit as st
import pandas as pd
import base64
import sqlite3
import re
import tempfile
from io import BytesIO
from image_processing import (
    process_image_to_grayscale,
    build_enhanced_detection_image,
    build_black_white_image,
    analyze_library_image,
)
from pathlib import Path
from datetime import datetime, date
from database import sync_experiment_db
from ui_labels import display_label, label_with_required
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

try:
    import rawpy
except Exception:
    rawpy = None

try:
    import exifread
except Exception:
    exifread = None


ASSETS_DIR = Path(__file__).parent / 'assets'
STAR_ICON_PATH = ASSETS_DIR / 'star.png'
YELLOW_STAR_ICON_PATH = ASSETS_DIR / 'yellow_star.png'
BLACK_STAR_ICON_PATH = ASSETS_DIR / 'black_star.png'
REMOVE_ICON_PATH = ASSETS_DIR / 'remove.png'
EXPERIMENT_DB_PATH = Path(__file__).parent / 'experiment_data.db'
ANALYSIS_CACHE_VERSION = 'v2'
PREPROCESS_CACHE_VERSION = 'v3'
DNG_EXTENSIONS = {'.dng'}
DEFAULT_OPERATOR = 'A.Li'
DRYING_UNITS = ('nights', 'days')
STORAGE_UNITS = ('°C', '°F')

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
    'line_gliding_date',
    'line_storage_condition',
    'line_drying_time',
    'glide_volume_ul_per_cm',
    'conjugate_batch_name',
    'gnp_lot',
    'conjugate_loading_ul_per_cm',
    'stability_timepoint',
    'experiment_notes',
]

EXPERIMENT_DEFAULT_VALUES = {
    'operator': DEFAULT_OPERATOR,
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
    {'ui': 'line_gliding_date', 'db': 'line_gliding_date', 'kind': 'text'},
    {'ui': 'line_storage_condition', 'db': 'line_storage_condition', 'kind': 'text'},
    {'ui': 'line_drying_time', 'db': 'line_drying_time', 'kind': 'text'},
    {'ui': 'glide_volume_ul_per_cm', 'db': 'glide_volume_ul_per_cm', 'kind': 'number'},
    {'ui': 'conjugate_batch_name', 'db': 'conjugate_batch_name', 'kind': 'conjugate_batch_select'},
    {'ui': 'gnp_lot', 'db': 'gnp_lot', 'kind': 'lot_select'},
    {'ui': 'conjugate_loading_ul_per_cm', 'db': 'conjugate_loading_ul_per_cm', 'kind': 'number'},
    {'ui': 'drying_time', 'db': 'drying_time', 'kind': 'text'},
    {'ui': 'storage_condition', 'db': 'storage_condition', 'kind': 'text'},
    {'ui': 'stability_timepoint', 'db': 'stability_timepoint', 'kind': 'text'},
    {'ui': 'experiment_notes', 'db': 'experiment_notes', 'kind': 'text'},
]

EXPERIMENT_FIELD_GROUPS = [
    (
        'Materials',
        [
            'nitrocellulose_material',
            'cassette',
            'sample_pad_material',
            'conjugate_pad_material',
            'absorbent_pad_material',
        ],
    ),
    (
        'Pretreatment & buffers',
        [
            'sample_pad_pretreatment_lot',
            'conjugate_pad_pretreatment_lot',
            'running_buffer_lot',
            'glide_buffer_lot',
            'reconstitution_buffer_lot',
            'gnp_lot',
        ],
    ),
    (
        'Line reagents',
        [
            'test_line_reagent',
            'test_line_concentration_mg_ml',
            'reference_line_reagent',
            'reference_line_concentration_mg_ml',
            'line_gliding_date',
            'line_storage_condition',
            'line_drying_time',
        ],
    ),
    (
        'Conjugate & run conditions',
        [
            'conjugate_batch_name',
            'glide_volume_ul_per_cm',
            'conjugate_loading_ul_per_cm',
            'drying_time',
            'storage_condition',
            'stability_timepoint',
        ],
    ),
    (
        'Notes',
        [
            'experiment_notes',
        ],
    ),
]

PER_STRIP_CHANGED_FIELD = 'sample_equivalent_mg_ml'

EXPERIMENT_TITLE_CODES = {
    'nitrocellulose_material': 'NC',
    'cassette': 'CAS',
    'sample_pad_material': 'SAMPAD',
    'sample_pad_pretreatment_lot': 'SAMPBUFF',
    'conjugate_pad_material': 'CONPAD',
    'conjugate_pad_pretreatment_lot': 'CONBUFF',
    'absorbent_pad_material': 'ABS',
    'running_buffer_lot': 'RUNBUF',
    'glide_buffer_lot': 'GLIBUF',
    'reconstitution_buffer_lot': 'REBUF',
    'test_line_reagent': 'TEST',
    'test_line_concentration_mg_ml': 'TESTCONC',
    'reference_line_reagent': 'REF',
    'reference_line_concentration_mg_ml': 'REFCONC',
    'line_gliding_date': 'LINEGLIDE',
    'line_storage_condition': 'LINESTORE',
    'line_drying_time': 'LINEDRY',
    'glide_volume_ul_per_cm': 'GLIDEVOL',
    'conjugate_batch_name': 'CONBATCH',
    'gnp_lot': 'GNP',
    'conjugate_loading_ul_per_cm': 'CONLOAD',
    'drying_time': 'DRY',
    'storage_condition': 'STORE',
    'stability_timepoint': 'STAB',
    'experiment_notes': 'NOTE',
}


def _should_auto_star(analysis):
    status = str(analysis.get('line_detection_status') or '').strip()
    if status:
        return status == 'failed'
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
    'line_gliding_date',
    'line_storage_condition',
    'line_drying_time',
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
    return display_label(text)


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
    for condition_part in _split_changed_fields(condition_val):
        if condition_part in changed_set:
            return condition_part
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
    changed = [name for name in CHANGED_FIELD_NAMES if name != PER_STRIP_CHANGED_FIELD]
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


def _build_star_button_label(starred, line_detection_status=None):
    status = str(line_detection_status or '').strip().lower()
    if status == 'good':
        icon_path = YELLOW_STAR_ICON_PATH
    elif status == 'needs_review':
        icon_path = STAR_ICON_PATH
    elif status == 'failed':
        icon_path = BLACK_STAR_ICON_PATH
    else:
        icon_path = YELLOW_STAR_ICON_PATH if starred else STAR_ICON_PATH
    icon_b64 = _read_icon_base64(str(icon_path))
    if not icon_b64:
        if status == 'good':
            return '⭐'
        if status == 'needs_review':
            return '☆'
        if status == 'failed':
            return '✦'
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


def _parse_image_datetime_text(raw):
    if raw is None:
        return None
    text = str(raw).strip().strip('\x00')
    if not text:
        return None

    text = text.replace('Z', '')
    for fmt in (
        '%Y:%m:%d %H:%M:%S',
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%d %H:%M:%S',
        '%Y/%m/%d %H:%M:%S',
    ):
        try:
            return datetime.strptime(text[:19], fmt)
        except Exception:
            continue
    return None


def _is_dng_upload(name):
    return Path(str(name or '')).suffix.lower() in DNG_EXTENSIONS


def _extract_dng_datetime_from_bytes(file_bytes):
    if not file_bytes:
        return None

    if exifread is not None:
        try:
            tags = exifread.process_file(BytesIO(file_bytes), details=False)
            for key in (
                'EXIF DateTimeOriginal',
                'EXIF DateTimeDigitized',
                'Image DateTime',
            ):
                parsed = _parse_image_datetime_text(tags.get(key))
                if parsed is not None:
                    return parsed
        except Exception:
            pass

    # Fallback for DNG/TIFF metadata when exifread is unavailable. The date
    # strings are commonly embedded as ASCII even though the container is binary.
    try:
        text = file_bytes[:1024 * 1024].decode('latin-1', errors='ignore')
        m = re.search(r'(\d{4}:\d{2}:\d{2} \d{2}:\d{2}:\d{2})', text)
        if m:
            return _parse_image_datetime_text(m.group(1))
    except Exception:
        pass

    return None


def _open_largest_embedded_jpeg(file_bytes):
    if not file_bytes:
        return None

    candidates = []
    start = 0
    while True:
        soi = file_bytes.find(b'\xff\xd8\xff', start)
        if soi < 0:
            break
        eoi = file_bytes.find(b'\xff\xd9', soi + 3)
        if eoi < 0:
            break
        eoi += 2
        candidates.append(file_bytes[soi:eoi])
        start = eoi

    for jpeg_bytes in sorted(candidates, key=len, reverse=True):
        try:
            img = Image.open(BytesIO(jpeg_bytes))
            img.load()
            return ImageOps.exif_transpose(img).convert('RGB')
        except Exception:
            continue

    return None


def _convert_dng_bytes_to_rgb(file_bytes, name):
    raw_error = None
    tmp_path = None
    if rawpy is not None:
        try:
            suffix = Path(str(name or '')).suffix or '.dng'
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(file_bytes)
                tmp_path = Path(tmp.name)

            with rawpy.imread(str(tmp_path)) as raw:
                rgb = raw.postprocess(
                    use_camera_wb=True,
                    output_bps=8,
                    no_auto_bright=False,
                )
            return Image.fromarray(rgb).convert('RGB'), 'dng-raw'
        except Exception as e:
            raw_error = e
        finally:
            if tmp_path is not None:
                try:
                    tmp_path.unlink(missing_ok=True)
                except Exception:
                    pass

    preview_img = _open_largest_embedded_jpeg(file_bytes)
    if preview_img is not None:
        return preview_img, 'dng-preview'

    if rawpy is None:
        raise RuntimeError(
            'DNG support requires rawpy. Install requirements.txt, then restart Streamlit.'
        )
    raise RuntimeError(f'DNG could not be decoded and no embedded preview was found: {raw_error}')


def _load_uploaded_image(uploaded, name):
    if _is_dng_upload(name):
        file_bytes = uploaded.getvalue()
        image_dt = _extract_dng_datetime_from_bytes(file_bytes)
        if image_dt is None:
            image_dt = _extract_datetime_from_filename(name)
        img, file_kind = _convert_dng_bytes_to_rgb(file_bytes, name)
        return img, image_dt, file_kind

    src_img = Image.open(uploaded)
    image_dt = _extract_image_datetime(src_img)
    src_img = ImageOps.exif_transpose(src_img)
    if image_dt is None:
        image_dt = _extract_image_datetime(src_img)
    if image_dt is None:
        image_dt = _extract_datetime_from_filename(name)
    return src_img.convert('RGB'), image_dt, 'image'


def _file_kind_notice(file_kind):
    if file_kind == 'dng-preview':
        return 'DNG RAW decode failed. Using embedded preview converted to PNG for analysis and saving.'
    return ''


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
            SELECT ur.original_name
            FROM upload_records ur
            LEFT JOIN strip_results sr
              ON sr.strip_id = ur.id
            WHERE ur.original_name IS NOT NULL
              AND TRIM(ur.original_name) != ''
              AND (sr.strip_id IS NULL OR sr.experiment_id IS NOT NULL)
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
              AND experiment_id IS NOT NULL
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
    line_detection_status=None,
    confidence_score=None,
    quality_flags=None,
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

        line_detection_status = (line_detection_status or '').strip() or None
        quality_flags = list(quality_flags or [])
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

        combined_quality_flags = []
        if vertical_crop_reason and vertical_crop_reason != 'ok':
            combined_quality_flags.append(vertical_crop_reason)
        if bg is None:
            combined_quality_flags.append('missing_background')
        if ratio is None:
            combined_quality_flags.append('missing_test_reference_ratio')
        if line_detection_status and line_detection_status != 'good':
            combined_quality_flags.append(line_detection_status)
        if confidence_score is not None:
            try:
                if float(confidence_score) < 0.70:
                    combined_quality_flags.append('low_detection_confidence')
            except Exception:
                pass
        combined_quality_flags.extend(quality_flags)
        quality_flags_text = ','.join(sorted(set(combined_quality_flags))) if combined_quality_flags else None

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
            SELECT experiment_title
            FROM experiments
            WHERE experiment_title IS NOT NULL
              AND TRIM(experiment_title) != ''
            GROUP BY experiment_title
            ORDER BY MAX(experiment_id) DESC
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


def _split_changed_fields(value):
    if value is None:
        return []
    parts = re.split(r'[,;/]+', str(value))
    out = []
    seen = set()
    for raw in parts:
        text = raw.strip()
        if not text or text in seen or text == PER_STRIP_CHANGED_FIELD:
            continue
        seen.add(text)
        out.append(text)
    return out


def _join_changed_fields(values):
    cleaned = []
    seen = set()
    for raw in values or []:
        text = str(raw or '').strip()
        if not text or text in seen or text == PER_STRIP_CHANGED_FIELD:
            continue
        seen.add(text)
        cleaned.append(text)
    return ','.join(cleaned)


def _title_code_for_changed_fields(changed_fields):
    codes = []
    seen = set()
    for field in changed_fields or []:
        code = EXPERIMENT_TITLE_CODES.get(field)
        if not code:
            code = ''.join(part[:3].upper() for part in str(field).split('_') if part)[:12]
        if code and code not in seen:
            seen.add(code)
            codes.append(code)
    return '-'.join(codes) if codes else 'EXP'


def _changed_fields_from_title(title, changed_options=None):
    text = str(title or '').strip()
    if not text:
        return []
    m = re.match(r'^(.+?)(\d{6})-\d+$', text)
    if not m:
        return []
    reverse_codes = {v: k for k, v in EXPERIMENT_TITLE_CODES.items()}
    allowed = set(changed_options or [])
    values = []
    for code in m.group(1).split('-'):
        field = reverse_codes.get(code.strip().upper())
        if field and (not allowed or field in allowed):
            values.append(field)
    return values


def _next_experiment_set_number(prefix):
    if not prefix or not EXPERIMENT_DB_PATH.exists():
        return 1
    conn = sqlite3.connect(EXPERIMENT_DB_PATH)
    try:
        rows = conn.execute(
            """
            SELECT experiment_title
            FROM experiments
            WHERE experiment_title LIKE ?
            """,
            (f'{prefix}-%',),
        ).fetchall()
    finally:
        conn.close()

    max_n = 0
    pattern = re.compile(rf'^{re.escape(prefix)}-(\d+)$')
    for (title,) in rows:
        m = pattern.match(str(title or '').strip())
        if not m:
            continue
        try:
            max_n = max(max_n, int(m.group(1)))
        except Exception:
            continue
    return max_n + 1


def _build_experiment_title(changed_fields, experiment_date):
    if isinstance(experiment_date, date):
        date_part = experiment_date.strftime('%d%m%y')
    else:
        dt = pd.to_datetime(experiment_date, errors='coerce')
        date_part = date.today().strftime('%d%m%y') if pd.isna(dt) else dt.strftime('%d%m%y')
    prefix = f'{_title_code_for_changed_fields(changed_fields)}{date_part}'
    return f'{prefix}-{_next_experiment_set_number(prefix)}'


def _load_recent_changed_field(changed_options=None):
    if not EXPERIMENT_DB_PATH.exists():
        return None
    allowed = set(changed_options or [])
    conn = sqlite3.connect(EXPERIMENT_DB_PATH)
    try:
        rows = conn.execute(
            """
            SELECT changed_field AS value
            FROM strip_results
            WHERE changed_field IS NOT NULL
              AND TRIM(changed_field) != ''
            ORDER BY
                CASE
                    WHEN image_upload_datetime IS NOT NULL AND TRIM(image_upload_datetime) != ''
                    THEN image_upload_datetime
                    ELSE ''
                END DESC,
                CASE
                    WHEN strip_id GLOB '[0-9]*' THEN CAST(strip_id AS INTEGER)
                    ELSE NULL
                END DESC,
                strip_id DESC
            LIMIT 20
            """
        ).fetchall()
        for row in rows:
            values = _split_changed_fields(row[0])
            value = values[0] if values else str(row[0] or '').strip()
            if value and value != PER_STRIP_CHANGED_FIELD and (not allowed or value in allowed):
                return value

        rows = conn.execute(
            """
            SELECT condition AS value, experiment_title
            FROM experiments
            WHERE condition IS NOT NULL
               AND TRIM(condition) != ''
            ORDER BY experiment_id DESC
            LIMIT 20
            """
        ).fetchall()
        for row in rows:
            values = _split_changed_fields(row[0])
            if not values:
                values = _changed_fields_from_title(row[1], changed_options)
            value = values[0] if values else str(row[0] or '').strip()
            if value and value != PER_STRIP_CHANGED_FIELD and (not allowed or value in allowed):
                return value
    except Exception:
        return None
    finally:
        conn.close()
    return None


def _load_recent_changed_fields(changed_options=None):
    allowed = set(changed_options or [])
    if EXPERIMENT_DB_PATH.exists():
        conn = sqlite3.connect(EXPERIMENT_DB_PATH)
        try:
            rows = conn.execute(
                """
                SELECT condition, experiment_title
                FROM experiments
                WHERE condition IS NOT NULL
                  AND TRIM(condition) != ''
                ORDER BY experiment_id DESC
                LIMIT 20
                """
            ).fetchall()
        except Exception:
            rows = []
        finally:
            conn.close()
        for row in rows:
            values = [
                value
                for value in (_split_changed_fields(row[0]) or _changed_fields_from_title(row[1], changed_options))
                if value != PER_STRIP_CHANGED_FIELD and (not allowed or value in allowed)
            ]
            if values:
                return values

    first = _load_recent_changed_field(changed_options)
    if first and first != PER_STRIP_CHANGED_FIELD:
        return [first]
    return []


def _apply_previous_experiment_to_form(
    baseline_row,
    experiment_specs,
    changed_options,
    preferred_changed=None,
):
    baseline_row = dict(baseline_row or {})
    st.session_state['library_exp_experiment_title'] = ''
    changed_values = []
    if isinstance(preferred_changed, (list, tuple, set)):
        changed_values = [v for v in preferred_changed if v in changed_options]
    elif preferred_changed in changed_options:
        changed_values = [preferred_changed]
    if not changed_values:
        changed_values = [v for v in _split_changed_fields(baseline_row.get('condition')) if v in changed_options]
    if not changed_values:
        changed_values = _changed_fields_from_title(baseline_row.get('experiment_title'), changed_options)
    if changed_values:
        st.session_state['library_exp_changed_selector'] = changed_values[0]
        st.session_state['library_exp_changed_multiselect'] = changed_values
        st.session_state['library_changed_field'] = changed_values[0]
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
            if unit not in DRYING_UNITS:
                unit = 'nights'
            st.session_state[f'library_exp_{db_name}_unit'] = unit
        elif db_name in ('storage_condition', 'line_storage_condition'):
            m = re.match(r'^\s*([0-9]*\.?[0-9]+)\s*(?:°?\s*)?([cCfF]|o[cC]|o[fF])?\s*$', default_val)
            st.session_state[f'library_exp_{db_name}_num'] = m.group(1) if m else ''
            default_unit_raw = (m.group(2) or '').strip().lower() if m else ''
            st.session_state[f'library_exp_{db_name}_unit'] = STORAGE_UNITS[1] if default_unit_raw in ('f', 'of') else STORAGE_UNITS[0]
        else:
            st.session_state[f'library_exp_{db_name}'] = default_val


def _selectbox_with_state(container, label, options, key, default_index=0, format_func=None, label_visibility='visible'):
    if key in st.session_state and st.session_state[key] not in options:
        del st.session_state[key]
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


def _multiselect_with_state(container, label, options, key, default_values=None, placeholder=None, label_visibility='visible', format_func=None):
    kwargs = {
        'label': label,
        'options': options,
        'key': key,
        'label_visibility': label_visibility,
    }
    if placeholder is not None:
        kwargs['placeholder'] = placeholder
    if format_func is not None:
        kwargs['format_func'] = format_func
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


def _render_experiment_field(
    container,
    spec,
    baseline_row,
    reagent_lot_values,
    pad_material_values,
    pad_material_labels,
    conjugate_batch_names,
    form_values,
):
    ui_label = spec['ui']
    db_name = spec['db']
    latest_val = baseline_row.get(db_name)
    default_val = '' if latest_val is None else str(latest_val)
    if default_val == '':
        default_val = EXPERIMENT_DEFAULT_VALUES.get(db_name, '')
    field_required = db_name not in OPTIONAL_EXPERIMENT_FIELDS
    label = label_with_required(ui_label, required=field_required)
    placeholder = 'Required' if field_required else 'Optional'

    if spec.get('kind') == 'lot_select':
        options = list(reagent_lot_values.get(ui_label, []))
        if not options:
            options = ['']
        default_idx = options.index(default_val) if default_val in options else 0
        form_values[db_name] = _selectbox_with_state(
            container,
            label,
            options,
            key=f'library_exp_{db_name}_select',
            default_index=default_idx,
        )
    elif spec.get('kind') == 'pad_select':
        options = list(pad_material_values.get(ui_label, []))
        if not options:
            options = ['']
        default_idx = options.index(default_val) if default_val in options else 0
        labels = pad_material_labels.get(ui_label, {})
        form_values[db_name] = _selectbox_with_state(
            container,
            label,
            options,
            key=f'library_exp_{db_name}_select',
            default_index=default_idx,
            format_func=lambda value, label_map=labels: label_map.get(value, value),
        )
    elif spec.get('kind') == 'conjugate_batch_select':
        options = list(conjugate_batch_names)
        if not options:
            options = ['']
        default_idx = options.index(default_val) if default_val in options else 0
        form_values[db_name] = _selectbox_with_state(
            container,
            label,
            options,
            key=f'library_exp_{db_name}_select',
            default_index=default_idx,
        )
    elif db_name in ('drying_time', 'line_drying_time'):
        m = re.match(r'^\s*([0-9]*\.?[0-9]+)\s*(nights?|days?)?\s*$', default_val, flags=re.IGNORECASE)
        default_num = m.group(1) if m else ''
        default_unit = (m.group(2) or 'nights') if m else 'nights'
        default_unit = default_unit.lower()
        if default_unit not in DRYING_UNITS:
            default_unit = 'nights'
        dt_num_col, dt_unit_col = container.columns([2, 2])
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
            list(DRYING_UNITS),
            key=f'library_exp_{db_name}_unit',
            default_index=0 if default_unit == 'nights' else 1,
        )
        form_values[db_name] = (f'{drying_num.strip()} {drying_unit}' if (drying_num or '').strip() else '')
    elif db_name in ('storage_condition', 'line_storage_condition'):
        m = re.match(r'^\s*([0-9]*\.?[0-9]+)\s*(?:°?\s*)?([cCfF]|o[cC]|o[fF])?\s*$', default_val)
        default_num = m.group(1) if m else ''
        default_unit_raw = (m.group(2) or '').strip().lower() if m else ''
        if default_unit_raw in ('f', 'of'):
            default_unit = STORAGE_UNITS[1]
        else:
            default_unit = STORAGE_UNITS[0]
        sc_num_col, sc_unit_col = container.columns([2, 1])
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
            list(STORAGE_UNITS),
            key=f'library_exp_{db_name}_unit',
            default_index=0 if default_unit == STORAGE_UNITS[0] else 1,
        )
        form_values[db_name] = (f'{storage_num.strip()} {storage_unit}' if (storage_num or '').strip() else '')
    else:
        form_values[db_name] = _text_input_with_state(
            container,
            label,
            key=f'library_exp_{db_name}',
            default_value=default_val,
            placeholder=placeholder,
        )


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
              AND COALESCE(active, 1) = 1
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
    labels = {k: {} for k in PAD_LINKED_TYPES}
    if not EXPERIMENT_DB_PATH.exists():
        return out, labels
    conn = sqlite3.connect(EXPERIMENT_DB_PATH)
    try:
        rows = conn.execute(
            """
            SELECT pad_name, type, composition_details
            FROM pad_material
            WHERE pad_name IS NOT NULL
              AND TRIM(pad_name) != ''
              AND type IS NOT NULL
              AND TRIM(type) != ''
              AND COALESCE(active, 1) = 1
            ORDER BY pad_name
            """
        ).fetchall()
        for pad_name, pad_type, composition_details in rows:
            t = str(pad_type).strip()
            if t == '':
                continue
            pad_value = str(pad_name).strip()
            out.setdefault(t, []).append(pad_value)
            labels.setdefault(t, {})
            description = str(composition_details or '').strip()
            if description and pad_value not in labels[t]:
                labels[t][pad_value] = f'{pad_value} - {description}'
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
    return out, labels


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
              AND COALESCE(active, 1) = 1
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
    if st.session_state.get('library_experiment_mode') == 'Exist experiment':
        st.session_state['library_experiment_mode'] = 'Existing experiment'

    mode_row = st.columns([2.4, 2.2])
    with mode_row[0]:
        mode = st.radio(
            'Experiment mode',
            options=['New experiment', 'Existing experiment'],
            horizontal=True,
            key='library_experiment_mode',
        )

    if mode == 'New experiment':
        cols = _get_experiment_columns()
        if not cols:
            st.warning('experiments table not found in experiment_data.db.')
            return

        db_cols = {c['name']: c for c in cols}
        reagent_lot_values = _load_reagent_lot_values_by_type()
        pad_material_values, pad_material_labels = _load_pad_material_values_by_type()
        experiment_specs = _build_runtime_experiment_specs(
            db_col_names=set(db_cols.keys()),
            reagent_lot_values=reagent_lot_values,
            pad_material_values=pad_material_values,
        )
        changed_options = _build_runtime_changed_fields(experiment_specs)
        st.session_state['library_changed_field_options'] = changed_options
        recent_changed = _load_recent_changed_field(changed_options)
        recent_changed_values = _load_recent_changed_fields(changed_options)

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

        previous_none_label = 'No previous experiment'
        previous_options = [previous_none_label] + previous_experiment_titles
        with mode_row[1]:
            previous_title = _selectbox_with_state(
                st,
                'Previous experiment',
                previous_options,
                key='library_previous_experiment_title',
                default_index=0,
                label_visibility='visible',
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
                preferred_changed=(None if previous_row else recent_changed_values),
            )
            st.session_state[previous_applied_key] = current_apply_title

        form_values = {}
        default_changed_values = st.session_state.get('library_exp_changed_multiselect')
        if not default_changed_values:
            default_changed_values = recent_changed_values
        if not default_changed_values and recent_changed in changed_options:
            default_changed_values = [recent_changed]
        default_changed_values = [v for v in default_changed_values or [] if v in changed_options]

        changed_values = _multiselect_with_state(
            st,
            label_with_required('changed', required=True),
            changed_options,
            key='library_exp_changed_multiselect',
            default_values=default_changed_values,
            placeholder='Select one or more experiment variables',
            format_func=_display_label,
        )
        changed_values = [v for v in changed_values if v in changed_options]
        changed_ui = _join_changed_fields(changed_values)
        primary_changed = changed_values[0] if changed_values else ''
        if primary_changed:
            st.session_state['library_changed_field'] = primary_changed
            st.session_state['library_exp_changed_selector'] = primary_changed

        top_form_cols = st.columns([1, 1.8, 0.9])
        form_values['experiment_date'] = _date_input_with_state(
            top_form_cols[0],
            label_with_required('experiment_date', required=True),
            key='library_exp_experiment_date',
            default_value=date.today(),
        )
        generated_title = _build_experiment_title(changed_values, form_values['experiment_date'])
        previous_auto_title = st.session_state.get('library_exp_title_auto_value')
        current_title = st.session_state.get('library_exp_experiment_title', '')
        if 'library_exp_auto_title_enabled' not in st.session_state:
            st.session_state['library_exp_auto_title_enabled'] = True
        top_form_cols[2].markdown(
            "<div style='height: 0.8rem;'></div>",
            unsafe_allow_html=True,
        )
        auto_title_enabled = top_form_cols[2].checkbox(
            'Auto title',
            key='library_exp_auto_title_enabled',
        )
        if auto_title_enabled and (current_title == '' or current_title == previous_auto_title):
            st.session_state['library_exp_experiment_title'] = generated_title
        st.session_state['library_exp_title_auto_value'] = generated_title
        form_values['experiment_title'] = _text_input_with_state(
            top_form_cols[1],
            label_with_required('experiment_title', required=True),
            key='library_exp_experiment_title',
            default_value=generated_title,
            placeholder='Auto-generated',
        )
        suggested_text = f'Suggested: {generated_title}' if not auto_title_enabled else '&nbsp;'
        top_form_cols[2].markdown(
            (
                "<div style='min-height: 1.1rem; margin-top: -0.15rem; "
                "font-size: 0.875rem; color: rgba(49, 51, 63, 0.6);'>"
                f"{suggested_text}</div>"
            ),
            unsafe_allow_html=True,
        )

        show_specs = [s for s in experiment_specs if s['ui'] not in set(changed_values)]
        specs_by_ui = {s['ui']: s for s in show_specs}
        rendered = set()

        for group_title, group_fields in EXPERIMENT_FIELD_GROUPS:
            group_specs = [specs_by_ui[name] for name in group_fields if name in specs_by_ui]
            if not group_specs:
                continue
            st.markdown(f'**{group_title}**')
            for group_i in range(0, len(group_specs), 3):
                row_cols = st.columns(3)
                for j, spec in enumerate(group_specs[group_i:group_i + 3]):
                    _render_experiment_field(
                        row_cols[j],
                        spec,
                        baseline_row,
                        reagent_lot_values,
                        pad_material_values,
                        pad_material_labels,
                        conjugate_batch_names,
                        form_values,
                    )
                    rendered.add(spec['ui'])

        remaining_specs = [spec for spec in show_specs if spec['ui'] not in rendered]
        if remaining_specs:
            st.markdown('**Additional variables**')
            for group_i in range(0, len(remaining_specs), 3):
                row_cols = st.columns(3)
                for j, spec in enumerate(remaining_specs[group_i:group_i + 3]):
                    _render_experiment_field(
                        row_cols[j],
                        spec,
                        baseline_row,
                        reagent_lot_values,
                        pad_material_values,
                        pad_material_labels,
                        conjugate_batch_names,
                        form_values,
                    )

        save_clicked = st.button('Save experiment', key='library_save_experiment', width='content')

        if save_clicked:
            title = (form_values.get('experiment_title') or '').strip()
            if title == '':
                st.error('Experiment title is required.')
                return
            if not changed_values:
                st.error('Select at least one changed variable.')
                return

            payload = {'experiment_date': form_values['experiment_date'].isoformat()}
            payload['experiment_title'] = title
            payload['condition'] = changed_ui
            payload['operator'] = (baseline_row.get('operator') or latest_row.get('operator') or DEFAULT_OPERATOR)

            # Start from baseline to avoid refilling unchanged items.
            if has_baseline:
                for spec in experiment_specs:
                    db_name = spec['db']
                    if db_name in baseline_row:
                        payload[db_name] = baseline_row.get(db_name)

            for changed_name in changed_values:
                if changed_name in payload:
                    payload[changed_name] = None

            missing = []
            convert_errors = []
            target_specs = [s for s in experiment_specs if s['ui'] not in set(changed_values)]

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

                if db_name in ('drying_time', 'line_drying_time'):
                    m = re.match(r'^\s*([0-9]*\.?[0-9]+)\s+(nights|days)\s*$', raw_text, flags=re.IGNORECASE)
                    if not m:
                        convert_errors.append(f'{ui_label} expects number + nights/days.')
                    else:
                        payload[db_name] = f"{m.group(1)} {m.group(2).lower()}"
                elif db_name in ('storage_condition', 'line_storage_condition'):
                    m = re.match(r'^\s*([0-9]*\.?[0-9]+)\s+(?:°?\s*)?([cCfF]|o[cC]|o[fF])\s*$', raw_text, flags=re.IGNORECASE)
                    if not m:
                        convert_errors.append(f'{ui_label} expects number + °C/°F.')
                    else:
                        unit_raw = m.group(2).lower()
                        unit = STORAGE_UNITS[1] if unit_raw in ('f', 'of') else STORAGE_UNITS[0]
                        payload[db_name] = f"{m.group(1)} {unit}"
                elif spec['kind'] == 'number':
                    try:
                        payload[db_name] = float(raw_text)
                    except ValueError:
                        convert_errors.append(f'{ui_label} expects a numeric value.')
                else:
                    payload[db_name] = raw_text

            if missing:
                st.error('Required fields are missing: ' + ', '.join([_display_label(x) for x in missing]))
            elif convert_errors:
                st.error('; '.join(convert_errors))
            else:
                try:
                    inserted_id = _insert_experiment(payload)
                    if inserted_id:
                        st.session_state['library_selected_experiment_id'] = int(inserted_id)
                    st.session_state['library_changed_field'] = primary_changed
                    st.session_state['library_exp_changed_selector'] = primary_changed
                    st.success('Experiment saved.')
                    st.rerun()
                except Exception as e:
                    st.error(f'Failed to save experiment: {e}')
    else:
        date_options = _load_experiment_date_options()
        title_options = _load_experiment_title_options()
        date_placeholder = 'Choose date(Optional)'
        existing_date_options = [date_placeholder] + date_options
        default_date_index = 1 if date_options else 0
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
        pad_material_values, pad_material_labels = _load_pad_material_values_by_type()
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
        display_df.insert(0, 'Remove', False)
        display_df.insert(0, 'Select', display_df['experiment_id'] == selected_id)

        editor_nonce = int(st.session_state.get('library_existing_experiment_editor_nonce', 0))
        edit_key = 'library_existing_experiment_edit_mode'
        prev_edit_key = 'library_existing_experiment_prev_edit_mode'
        cache_key = 'library_existing_experiment_editor_cache'
        prev_edit_mode = bool(st.session_state.get(prev_edit_key, False))
        header_cols = st.columns([1.15, 0.85, 6])
        header_cols[0].write('Existing experiments')
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
                            if k not in ('Select', 'Remove')
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
                    display_df.insert(0, 'Remove', False)
                    display_df.insert(0, 'Select', display_df['experiment_id'] == selected_id)
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
            'Select': st.column_config.CheckboxColumn('Select', width='small'),
            'Remove': st.column_config.CheckboxColumn('Remove', width='small'),
        }
        for col in display_df.columns:
            if col in ('Select', 'Remove'):
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
                else [c for c in display_df.columns if c not in ('Select', 'Remove')]
            ),
        )
        if edit_mode:
            st.session_state[cache_key] = edited.copy()

        remove_rows = edited[edited['Remove'] == True]  # noqa: E712
        if not remove_rows.empty:
            st.session_state['library_pending_remove_experiment_ids'] = [
                int(r['experiment_id']) for _, r in remove_rows.iterrows()
            ]
            _confirm_delete_experiments_dialog(st.session_state['library_pending_remove_experiment_ids'])

        selected_rows = edited[edited['Select'] == True]  # noqa: E712
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

            st.caption(f'Selected experiment: {new_selected}')
        else:
            if prev_selected is not None:
                st.caption(f'Selected experiment: {prev_selected}')
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
        'Upload images, DNG files, or CSV files',
        accept_multiple_files=True,
        type=['png', 'jpg', 'jpeg', 'gif', 'tif', 'tiff', 'dng', 'csv']
    )
    st.caption('DNG files are converted inside the app. If RAW decoding is unavailable for a phone model, the largest embedded preview is converted to PNG and used, while the original DNG capture time is still read when present.')

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

    image_upload_count = sum(
        1
        for uploaded in uploaded_files
        if not (uploaded.name.lower().endswith('.csv') or uploaded.type == 'text/csv')
    )
    csv_upload_count = len(uploaded_files) - image_upload_count
    st.caption(f'Queued: {image_upload_count} image file(s), {csv_upload_count} CSV file(s).')

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
                    file_kind = cached.get('file_kind', 'image')
                else:
                    img, image_dt, file_kind = _load_uploaded_image(uploaded, name)
                    gray = process_image_to_grayscale(img.copy())
                    enhanced = build_enhanced_detection_image(gray)
                    black_white = build_black_white_image(enhanced)
                    prep_cache[file_sig] = {
                        'img': img,
                        'gray': gray,
                        'enhanced': enhanced,
                        'black_white': black_white,
                        'image_dt': image_dt,
                        'file_kind': file_kind,
                    }

                images.append((img_id, name, img, gray, enhanced, black_white, image_dt, file_sig, file_kind))
            except UnidentifiedImageError:
                st.warning(f'File {name} is not a recognized image.')
            except Exception as e:
                st.warning(f'Failed to open {name}: {e}')

    if images:
        st.subheader('Images')
        selected_changed_field = PER_STRIP_CHANGED_FIELD

        for row_idx, (img_id, name, img, gray, enhanced, black_white, image_dt, file_sig, file_kind) in enumerate(images):
            row_key = str(img_id)
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
            line_detection_status = analysis.get("line_detection_status", "failed")
            confidence_score = analysis.get("confidence_score", 0.0)
            quality_flags = list(analysis.get("quality_flags", []) or [])
            trim_percent_used = analysis.get("trim_percent_used", 20)
            file_kind_notice = _file_kind_notice(file_kind)
            auto_starred = _should_auto_star(analysis)
            stored_starred = get_starred_status(img_id)
            effective_starred = bool(stored_starred or auto_starred)

            cols = st.columns([1, 2, 4])
            with cols[0]:
                mark_col, id_col = st.columns([1, 3])
                with mark_col:
                    if st.button(
                        _build_star_button_label(effective_starred, line_detection_status),
                        key=f'lib_star_{row_key}',
                        width='content',
                        type='tertiary',
                    ):
                        stored_starred = not effective_starred
                        set_starred_status(img_id, stored_starred)
                        effective_starred = bool(stored_starred or auto_starred)
                with id_col:
                    st.markdown(f"ID\n\n`{img_id}`")
                    if file_kind == 'dng-preview':
                        st.caption('DNG preview → PNG')
                    elif file_kind == 'dng-raw':
                        st.caption('DNG RAW')
                    elif file_kind == 'dng':
                        st.caption('DNG')

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
                    if file_kind_notice:
                        st.warning(file_kind_notice)
                    status_text = str(line_detection_status or 'failed').replace('_', ' ').title()
                    confidence_text = f'{float(confidence_score or 0.0):.2f}'
                    if line_detection_status == 'good':
                        cols[2].success(f'Detection: {status_text} ({confidence_text})')
                    elif line_detection_status == 'needs_review':
                        cols[2].warning(f'Detection: {status_text} ({confidence_text})')
                    elif line_detection_status and line_detection_status != 'good':
                        cols[2].error(f'Detection: {status_text} ({confidence_text})')
                    if quality_flags:
                        cols[2].caption('Review flags: ' + ', '.join(str(flag).replace('_', ' ') for flag in quality_flags))
            else:
                with cols[1]:
                    st.info(f"No dark line regions detected: {name}")
                with cols[2]:
                    if file_kind_notice:
                        st.warning(file_kind_notice)
                    st.error('Detection: Failed (0.00)')

            manual_dt_text = ''
            capture_datetime_invalid = False
            with cols[2]:
                with st.form(key=f'library_save_image_form_{row_key}', clear_on_submit=False):
                    image_changed_value = st.text_input(
                        label_with_required(selected_changed_field, required=True),
                        key=f'library_img_changed_value_{selected_changed_field}_{row_key}',
                        placeholder='Required',
                    )
                    if image_dt is None:
                        st.warning('Capture date/time was not found. Enter it before saving if this image needs a timestamp.')
                        manual_dt_text = st.text_input(
                            'capture datetime',
                            key=f'library_img_capture_datetime_{row_key}',
                            placeholder='YYYY-MM-DD HH:MM:SS',
                        )
                        parsed_manual_dt = _parse_image_datetime_text(manual_dt_text)
                        if manual_dt_text.strip() and parsed_manual_dt is None:
                            capture_datetime_invalid = True
                            st.error('Use capture datetime format: YYYY-MM-DD HH:MM:SS')
                        elif parsed_manual_dt is not None:
                            image_dt = parsed_manual_dt
                    else:
                        st.caption(f'Capture: {image_dt.isoformat(sep=" ", timespec="seconds")}')

                    save_image_clicked = st.form_submit_button('Save')

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
                    'line_detection_status': line_detection_status,
                    'confidence_score': confidence_score,
                    'quality_flags': quality_flags,
                    'line_candidates': analysis.get('line_candidates', []),
                    'selected_line_count': int(analysis.get('selected_line_count', 0) or 0),
                    'trim_percent_used': trim_percent_used,
                    'recrop_results_count': int(analysis.get('recrop_results_count', 0) or 0),
                    'source_file_kind': file_kind,
                    'source_conversion_notice': _file_kind_notice(file_kind) or None,
                    'capture_datetime': image_dt.isoformat(timespec='seconds') if image_dt else None,
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
                    line_detection_status=line_detection_status,
                    confidence_score=confidence_score,
                    quality_flags=quality_flags,
                )

                if save_image_clicked:
                    selected_exp_id = st.session_state.get('library_selected_experiment_id')
                    if capture_datetime_invalid:
                        cols[2].error('Fix capture datetime before saving.')
                    elif selected_exp_id is None:
                        cols[2].error('Please save/select an experiment first.')
                    elif (image_changed_value or '').strip() == '':
                        cols[2].error(f'{_display_label(selected_changed_field)} is required.')
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
                                cols[2].error('Sample equivalent must be a number.')
                            else:
                                cols[2].error(f'Invalid value for {_display_label(selected_changed_field)}.')
                        except Exception as e:
                            cols[2].error(f'Failed to save to experiment_data.db: {e}')
            except Exception:
                st.warning('Failed to save cropped image or write to upload_records')

    if tables:
        st.subheader('Datasets')
        for name, df in tables:
            st.write(f'Preview — {name}')
            st.dataframe(df.head(50))
