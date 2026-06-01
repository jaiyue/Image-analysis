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
UPLOADS_DB_PATH = Path(__file__).parent / 'uploads.db'
ANALYSIS_CACHE_VERSION = 'v2'
PREPROCESS_CACHE_VERSION = 'v2'

CHANGED_FIELD_NAMES = [
    'sample_equivalent_mg_ml',
    'nitrocellulose_material',
    'sample_pad_material',
    'sample_pad_pretreatment_lot',
    'conjugate_pad_material',
    'conjugate_pad_pretreatment_lot',
    'absorbent_pad_material',
    'running_buffer_lot',
    'glide_buffer_lot',
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
    'test_line_reagent': 'Bovine IgG',
    'reference_line_reagent': 'Chicken IgY',
}

EXPERIMENT_FIELD_SPECS = [
    {'ui': 'nitrocellulose_material', 'db': 'nitrocellulose_material', 'kind': 'pad_select'},
    {'ui': 'sample_pad_material', 'db': 'sample_pad_material', 'kind': 'pad_select'},
    {'ui': 'sample_pad_pretreatment_lot', 'db': 'sample_pad_pretreatment_lot', 'kind': 'lot_select'},
    {'ui': 'conjugate_pad_material', 'db': 'conjugate_pad_material', 'kind': 'pad_select'},
    {'ui': 'conjugate_pad_pretreatment_lot', 'db': 'conjugate_pad_pretreatment_lot', 'kind': 'lot_select'},
    {'ui': 'absorbent_pad_material', 'db': 'absorbent_pad_material', 'kind': 'pad_select'},
    {'ui': 'running_buffer_lot', 'db': 'running_buffer_lot', 'kind': 'lot_select'},
    {'ui': 'glide_buffer_lot', 'db': 'glide_buffer_lot', 'kind': 'lot_select'},
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

OPTIONAL_EXPERIMENT_FIELDS = {
    'stability_timepoint',
    'experiment_notes',
}

LOT_LINKED_TYPES = {
    'sample_pad_pretreatment_lot',
    'conjugate_pad_pretreatment_lot',
    'running_buffer_lot',
    'glide_buffer_lot',
    'gnp_lot',
}

PAD_LINKED_TYPES = {
    'nitrocellulose_material',
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


def _suggest_changed_field_from_experiment_row(row_dict):
    if not isinstance(row_dict, dict) or not row_dict:
        return None

    condition_val = str(row_dict.get('condition') or '').strip()
    if condition_val in CHANGED_FIELD_NAMES:
        return condition_val
    condition_norm = condition_val.replace(' ', '_')
    if condition_norm in CHANGED_FIELD_NAMES:
        return condition_norm

    ordered_fields = [spec['db'] for spec in EXPERIMENT_FIELD_SPECS if spec['db'] in CHANGED_FIELD_NAMES]
    primary_fields = [f for f in ordered_fields if f not in OPTIONAL_EXPERIMENT_FIELDS]
    optional_fields = [f for f in ordered_fields if f in OPTIONAL_EXPERIMENT_FIELDS]

    for field in primary_fields:
        if _is_missing_value(row_dict.get(field)):
            return field

    for field in optional_fields:
        if _is_missing_value(row_dict.get(field)):
            return field

    return None


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
    if not UPLOADS_DB_PATH.exists():
        return date.today().isoformat()
    conn = None
    try:
        conn = sqlite3.connect(UPLOADS_DB_PATH)
        row = conn.execute(
            """
            SELECT date
            FROM upload_records
            WHERE date IS NOT NULL
              AND TRIM(date) != ''
            ORDER BY date DESC, time DESC
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
                SET experiment_id = ?, condition_value = ?
                WHERE strip_id = ?
                """,
                (int(experiment_id), changed_value, str(strip_id)),
            )
        else:
            conn.execute(
                """
                UPDATE strip_results
                SET experiment_id = ?, condition_value = ?, sample_equivalent_mg_ml = ?
                WHERE strip_id = ?
                """,
                (int(experiment_id), changed_value, float(sample_equivalent_mg_ml), str(strip_id)),
            )
        conn.commit()
        return True, None
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
            if rt in out:
                out[rt].append(str(lot_name).strip())
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
            if t in out:
                out[t].append(str(pad_name).strip())
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
    st.subheader('Experiment')
    mode = st.radio(
        'Experiment mode',
        options=['New experiment', 'Exist experiment'],
        horizontal=True,
        key='library_experiment_mode',
    )

    if mode == 'New experiment':
        cols = _get_experiment_columns()
        if not cols:
            st.warning('experiments table not found in experiment_data.db.')
            return

        db_cols = {c['name']: c for c in cols}
        required_db_fields = ['experiment_title', 'operator', 'experiment_date', 'condition'] + [f['db'] for f in EXPERIMENT_FIELD_SPECS]
        missing_db_fields = [name for name in required_db_fields if name not in db_cols]
        if missing_db_fields:
            st.error(
                'Missing experiments columns: '
                + ', '.join([_display_label(x) for x in missing_db_fields])
            )
            return

        latest_row = _load_latest_experiment_row()
        has_baseline = bool(latest_row)
        reagent_lot_values = _load_reagent_lot_values_by_type()
        pad_material_values = _load_pad_material_values_by_type()
        conjugate_batch_names = _load_conjugate_batch_names()

        st.caption(f'Hidden autofill: experiment date = {_get_latest_upload_date()}')
        if not has_baseline:
            st.info('No baseline experiment found. Please fill all fields once.')

        form_values = {}
        title_col, changed_col = st.columns(2)
        form_values['experiment_title'] = title_col.text_input(
            'experiment title *',
            value='',
            placeholder='not empty',
            key='library_exp_experiment_title',
        )

        changed_default = st.session_state.get('library_changed_field', CHANGED_FIELD_NAMES[0])
        if changed_default not in CHANGED_FIELD_NAMES:
            changed_default = CHANGED_FIELD_NAMES[0]
        changed_ui = changed_col.selectbox(
            'changed',
            options=CHANGED_FIELD_NAMES,
            index=CHANGED_FIELD_NAMES.index(changed_default),
            key='library_exp_changed_selector',
            format_func=_display_label,
        )
        st.session_state['library_changed_field'] = changed_ui

        show_specs = [s for s in EXPERIMENT_FIELD_SPECS if s['ui'] != changed_ui]

        for i in range(0, len(show_specs), 3):
            row_cols = st.columns(3)
            for j, spec in enumerate(show_specs[i:i + 3]):
                ui_label = spec['ui']
                db_name = spec['db']
                latest_val = latest_row.get(db_name)
                default_val = '' if latest_val is None else str(latest_val)
                if default_val == '':
                    default_val = EXPERIMENT_DEFAULT_VALUES.get(db_name, '')
                field_required = db_name not in OPTIONAL_EXPERIMENT_FIELDS
                display_name = _display_label(ui_label)
                label = f'{display_name} *' if field_required else display_name
                placeholder = 'not empty' if field_required else 'optional'

                if spec.get('kind') == 'lot_select' and ui_label in LOT_LINKED_TYPES:
                    options = list(reagent_lot_values.get(ui_label, []))
                    if default_val and default_val not in options:
                        options.append(default_val)
                    if not options:
                        options = ['']
                    default_idx = options.index(default_val) if default_val in options else 0
                    form_values[db_name] = row_cols[j].selectbox(
                        label,
                        options=options,
                        index=default_idx,
                        key=f'library_exp_{db_name}_select',
                    )
                elif spec.get('kind') == 'pad_select' and ui_label in PAD_LINKED_TYPES:
                    options = list(pad_material_values.get(ui_label, []))
                    if default_val and default_val not in options:
                        options.append(default_val)
                    if not options:
                        options = ['']
                    default_idx = options.index(default_val) if default_val in options else 0
                    form_values[db_name] = row_cols[j].selectbox(
                        label,
                        options=options,
                        index=default_idx,
                        key=f'library_exp_{db_name}_select',
                    )
                elif spec.get('kind') == 'conjugate_batch_select':
                    options = list(conjugate_batch_names)
                    if default_val and default_val not in options:
                        options.append(default_val)
                    if not options:
                        options = ['']
                    default_idx = options.index(default_val) if default_val in options else 0
                    form_values[db_name] = row_cols[j].selectbox(
                        label,
                        options=options,
                        index=default_idx,
                        key=f'library_exp_{db_name}_select',
                    )
                else:
                    form_values[db_name] = row_cols[j].text_input(
                        label,
                        value=default_val,
                        placeholder=placeholder,
                        key=f'library_exp_{db_name}',
                    )

        save_clicked = st.button('Save experiment', key='library_save_experiment', width='content')

        if save_clicked:
            title = (form_values.get('experiment_title') or '').strip()
            if title == '':
                st.error('Not empty required: experiment_title')
                return

            payload = {'experiment_date': _get_latest_upload_date()}
            payload['experiment_title'] = title
            payload['condition'] = changed_ui
            payload['operator'] = (latest_row.get('operator') or 'A.Li')

            # Start from baseline to avoid refilling unchanged items.
            if has_baseline:
                for spec in EXPERIMENT_FIELD_SPECS:
                    db_name = spec['db']
                    if db_name in latest_row:
                        payload[db_name] = latest_row.get(db_name)

            if changed_ui in payload:
                payload[changed_ui] = None

            missing = []
            convert_errors = []
            target_specs = [s for s in EXPERIMENT_FIELD_SPECS if s['ui'] != changed_ui]

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

                if spec['kind'] == 'number':
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
        exp_df = _load_experiments_df()
        if exp_df.empty:
            st.info('No experiments found.')
            return

        existing_selected_id = st.session_state.get('library_selected_experiment_id')
        if existing_selected_id is not None:
            try:
                sid = int(existing_selected_id)
                hit = exp_df[exp_df['experiment_id'] == sid]
                if not hit.empty:
                    suggested_changed = _suggest_changed_field_from_experiment_row(hit.iloc[0].to_dict())
                    if suggested_changed:
                        st.session_state['library_changed_field'] = suggested_changed
            except Exception:
                pass

        selected_id = st.session_state.get('library_selected_experiment_id')
        display_df = exp_df.copy()
        display_df.insert(0, 'remove', False)
        display_df.insert(0, 'select', display_df['experiment_id'] == selected_id)

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
            key='library_existing_experiment_editor',
            column_config=col_config,
            disabled=[c for c in display_df.columns if c not in ('select', 'remove')],
        )

        remove_rows = edited[edited['remove'] == True]  # noqa: E712
        if not remove_rows.empty:
            deleted = 0
            failed = []
            for _, r in remove_rows.iterrows():
                try:
                    rid = int(r['experiment_id'])
                    _delete_experiment(rid)
                    if st.session_state.get('library_selected_experiment_id') == rid:
                        st.session_state['library_selected_experiment_id'] = None
                    deleted += 1
                except Exception as e:
                    failed.append(str(e))
            if deleted > 0:
                st.success(f'Deleted {deleted} experiment(s).')
            if failed:
                st.error('Failed to delete some rows: ' + '; '.join(failed))
            st.rerun()

        selected_rows = edited[edited['select'] == True]  # noqa: E712
        if not selected_rows.empty:
            new_selected = int(selected_rows.iloc[0]['experiment_id'])
            st.session_state['library_selected_experiment_id'] = new_selected

            exp_row_dict = None
            try:
                hit = exp_df[exp_df['experiment_id'] == new_selected]
                if not hit.empty:
                    exp_row_dict = hit.iloc[0].to_dict()
            except Exception:
                exp_row_dict = None
            suggested_changed = _suggest_changed_field_from_experiment_row(exp_row_dict)
            if suggested_changed:
                st.session_state['library_changed_field'] = suggested_changed

            st.caption(f'Selected experiment id: {new_selected}')
        else:
            st.caption('No experiment selected.')


def render_library_page():
    st.title('Library')
    st.write(
        'Upload images or CSV datasets. Images show as thumbnails; CSVs show a preview.')
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
    sync_experiment_db()
    init_uploads_db()
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

    images = []
    tables = []

    for uploaded in uploaded_files:
        name = uploaded.name
        if name.lower().endswith('.csv') or uploaded.type == 'text/csv':
            try:
                df = pd.read_csv(uploaded)
                tables.append((name, df))
            except Exception as e:
                st.warning(f'Could not read CSV {name}: {e}')
        else:
            if Image is None:
                st.warning('Pillow is not available: cannot display images.')
                break
            try:
                file_size = getattr(uploaded, 'size', None)
                file_sig = f"{name}::{file_size}"
                if file_sig not in st.session_state['library_file_ids']:
                    st.session_state['library_id_counter'] += 1
                    st.session_state['library_file_ids'][
                        file_sig] = f"{st.session_state['library_id_counter']:05d}"
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
        selected_changed_field = st.session_state.get('library_changed_field', CHANGED_FIELD_NAMES[0])
        if selected_changed_field not in CHANGED_FIELD_NAMES:
            selected_changed_field = CHANGED_FIELD_NAMES[0]
        st.session_state['library_changed_field'] = selected_changed_field

        for img_id, name, img, gray, enhanced, black_white, image_dt, file_sig in images:
            cropped_overlay = None
            recrop_overlay = None
            c_val = None
            t_val = None
            bg_val = None
            ratio_val = None
            ct_bg_sum_val = None
            cols = st.columns([1, 2, 4])
            with cols[0]:
                is_starred = get_starred_status(img_id)
                mark_col, id_col = st.columns([1, 3])
                with mark_col:
                    if st.button(
                        _build_star_button_label(is_starred),
                        key=f'lib_star_{img_id}',
                        width='content',
                        type='tertiary',
                    ):
                        set_starred_status(img_id, not is_starred)
                with id_col:
                    st.markdown(f"ID\n\n`{img_id}`")

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

            if recrop_overlay is not None:
                with cols[1]:
                    st.image(
                        recrop_overlay,
                        caption=f"Dark Line Regions Re-Crop — {name}",
                        width=240
                    )
                with cols[2]:
                    mean_only_df = pd.DataFrame(table_rows)[['name', 'gray_mean']].rename(
                        columns={'gray_mean': 'dark value'}
                    )
                    st.dataframe(mean_only_df, width='stretch')
            else:
                with cols[1]:
                    st.info(f"No dark line regions detected: {name}")
                with cols[2]:
                    st.empty()

            image_changed_value = cols[2].text_input(
                f'{_display_label(selected_changed_field)} *',
                key=f'library_img_changed_value_{selected_changed_field}_{img_id}',
                placeholder='not empty',
            )
            save_image_clicked = cols[2].button(
                'Save',
                key=f'library_save_image_{img_id}',
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
                    'metrics': {
                        'c': round(float(c_val), 4) if c_val is not None else None,
                        't': round(float(t_val), 4) if t_val is not None else None,
                        'bg': round(float(bg_val), 4) if bg_val is not None else None,
                        'ratio': round(float(ratio_val), 4) if ratio_val is not None else None,
                        'ct_bg_sum': round(float(ct_bg_sum_val), 4) if ct_bg_sum_val is not None else None,
                    },
                    'vertical_crop_reason': vertical_crop_reason
                }
                entry = {
                    'id': img_id,
                    'original_name': name,
                    'original_path': str(original_path),
                    'gray_path': str(gray_path),
                    'cropped_name': cropped_filename,
                    'cropped_path': str(cropped_path),
                    'dark_regions_path': str(dark_path) if cropped_overlay is not None else '',
                    'c': round(float(c_val), 4) if c_val is not None else None,
                    't': round(float(t_val), 4) if t_val is not None else None,
                    'bg': round(float(bg_val), 4) if bg_val is not None else None,
                    'ratio': round(float(ratio_val), 4) if ratio_val is not None else None,
                    'ct_bg_sum': round(float(ct_bg_sum_val), 4) if ct_bg_sum_val is not None else None,
                    'starred': 1 if is_starred else 0,
                    'changed_field': selected_changed_field,
                    'changed_value': (image_changed_value or '').strip() or None,
                    'detail': detail_payload,
                    'date': now.strftime('%Y-%m-%d') if now else None,
                    'time': now.strftime('%H:%M:%S') if now else None,
                    'timestamp': now.isoformat(timespec='seconds') if now else None
                }
                upsert_upload_record(entry)

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
                st.warning('Failed to save cropped image or write to uploads.db')

    if tables:
        st.subheader('Datasets')
        for name, df in tables:
            st.write(f'Preview — {name}')
            st.dataframe(df.head(50))
