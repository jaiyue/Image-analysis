# library.py — Library page with center‑based closest bars cropping

import streamlit as st
import pandas as pd
import base64
import sqlite3
from image_processing import (
    process_image_to_grayscale,
    build_enhanced_detection_image,
    build_black_white_image,
    analyze_library_image,
)
from pathlib import Path
from datetime import datetime, date
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
EXPERIMENT_DB_PATH = Path(__file__).parent / 'experiment_data.db'
UPLOADS_DB_PATH = Path(__file__).parent / 'uploads.db'

CHANGED_FIELD_NAMES = [
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
    'conjugate_batch_id',
    'gnp_lot',
    'conjugate_ratio',
    'reconstitution_volume_ul',
    'conjugate_loading_ul_per_cm',
]

EXPERIMENT_DEFAULT_VALUES = {
    'operator_name': 'A.Li',
    'test_line_reagent': 'Bovine IgG',
    'reference_line_reagent': 'Chicken IgY',
}

EXPERIMENT_FIELD_SPECS = [
    {'ui': 'nitrocellulose_material', 'db': 'nitrocellulose_material', 'kind': 'text'},
    {'ui': 'sample_pad_material', 'db': 'sample_pad_material', 'kind': 'text'},
    {'ui': 'sample_pad_pretreatment_lot', 'db': 'sample_pad_pretreatment_lot_id', 'kind': 'lot_select'},
    {'ui': 'conjugate_pad_material', 'db': 'conjugate_pad_material', 'kind': 'text'},
    {'ui': 'conjugate_pad_pretreatment_lot', 'db': 'conjugate_pad_pretreatment_lot_id', 'kind': 'lot_select'},
    {'ui': 'absorbent_pad_material', 'db': 'absorbent_pad_material', 'kind': 'text'},
    {'ui': 'running_buffer_lot', 'db': 'running_buffer_lot_id', 'kind': 'lot_select'},
    {'ui': 'glide_buffer_lot', 'db': 'glide_buffer_lot_id', 'kind': 'lot_select'},
    {'ui': 'test_line_reagent', 'db': 'test_line_reagent', 'kind': 'text'},
    {'ui': 'test_line_concentration_mg_ml', 'db': 'test_line_concentration', 'kind': 'number'},
    {'ui': 'reference_line_reagent', 'db': 'reference_line_reagent', 'kind': 'text'},
    {'ui': 'reference_line_concentration_mg_ml', 'db': 'reference_line_concentration', 'kind': 'number'},
    {'ui': 'glide_volume_ul_per_cm', 'db': 'glide_volume_ul_per_cm', 'kind': 'number'},
    {'ui': 'conjugate_batch_id', 'db': 'conjugate_batch_id', 'kind': 'text'},
    {'ui': 'gnp_lot', 'db': 'gnp_lot_id', 'kind': 'lot_select'},
    {'ui': 'conjugate_ratio', 'db': 'conjugate_ratio', 'kind': 'number'},
    {'ui': 'reconstitution_volume_ul', 'db': 'reconstitution_volume_ul', 'kind': 'number'},
    {'ui': 'conjugate_loading_ul_per_cm', 'db': 'conjugate_loading_ul_per_cm', 'kind': 'number'},
]


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


def _extract_image_datetime(pil_img):
    try:
        exif = pil_img.getexif()
        for tag in (36867, 36868, 306):  # DateTimeOriginal, DateTimeDigitized, DateTime
            raw = exif.get(tag)
            if raw:
                return datetime.strptime(str(raw), '%Y:%m:%d %H:%M:%S')
    except Exception:
        return None
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
    if not EXPERIMENT_DB_PATH.exists():
        return
    conn = sqlite3.connect(EXPERIMENT_DB_PATH)
    try:
        col_rows = conn.execute('PRAGMA table_info("experiments")').fetchall()
        col_names = {r[1] for r in col_rows}
        if 'loading_volume_ul' in col_names and 'conjugate_loading_ul_per_cm' not in col_names:
            conn.execute(
                """
                ALTER TABLE experiments
                RENAME COLUMN loading_volume_ul TO conjugate_loading_ul_per_cm
                """
            )
            conn.commit()
    finally:
        conn.close()


def _migrate_experiment_fields_for_changed_form():
    if not EXPERIMENT_DB_PATH.exists():
        return
    conn = sqlite3.connect(EXPERIMENT_DB_PATH)
    try:
        col_rows = conn.execute('PRAGMA table_info("experiments")').fetchall()
        col_names = {r[1] for r in col_rows}
        required_cols = [
            ('nitrocellulose_material', 'TEXT'),
            ('absorbent_pad_material', 'TEXT'),
            ('test_line_reagent', 'TEXT'),
            ('reference_line_reagent', 'TEXT'),
            ('glide_volume_ul_per_cm', 'REAL'),
            ('conjugate_batch_id', 'TEXT'),
            ('gnp_lot_id', 'INTEGER'),
            ('drying_time', 'TEXT'),
            ('stability_timepoint', 'TEXT'),
            ('changed_parameter', 'TEXT'),
        ]
        for col_name, col_type in required_cols:
            if col_name in col_names:
                continue
            conn.execute(f'ALTER TABLE experiments ADD COLUMN "{col_name}" {col_type}')
        conn.commit()
    finally:
        conn.close()


def _insert_experiment(payload):
    conn = sqlite3.connect(EXPERIMENT_DB_PATH)
    try:
        cols = list(payload.keys())
        placeholders = ', '.join(['?'] * len(cols))
        cols_sql = ', '.join([f'"{c}"' for c in cols])
        query = f'INSERT INTO "experiments" ({cols_sql}) VALUES ({placeholders})'
        conn.execute(query, [payload[c] for c in cols])
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


def _load_reagent_lot_options():
    if not EXPERIMENT_DB_PATH.exists():
        return {}
    conn = sqlite3.connect(EXPERIMENT_DB_PATH)
    try:
        rows = conn.execute(
            """
            SELECT lot_id, lot_number
            FROM reagent_lots
            WHERE lot_number IS NOT NULL
              AND TRIM(lot_number) != ''
            ORDER BY lot_id
            """
        ).fetchall()
        return {int(r[0]): str(r[1]) for r in rows}
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
        required_db_fields = ['experiment_name', 'operator_name'] + [f['db'] for f in EXPERIMENT_FIELD_SPECS]
        missing_db_fields = [name for name in required_db_fields if name not in db_cols]
        if missing_db_fields:
            st.error(f'Missing experiments columns: {", ".join(missing_db_fields)}')
            return

        latest_row = _load_latest_experiment_row()
        has_baseline = bool(latest_row)
        lot_options = _load_reagent_lot_options()

        st.caption(f'Hidden autofill: experiment_date = {_get_latest_upload_date()}')
        if not has_baseline:
            st.info('No baseline experiment found. Please fill all fields once.')

        form_values = {}
        title_col, changed_col = st.columns(2)
        form_values['experiment_name'] = title_col.text_input(
            'experiment_title *',
            value='',
            placeholder='not empty',
            key='library_exp_experiment_name',
        )

        changed_default = st.session_state.get('library_changed_field', CHANGED_FIELD_NAMES[0])
        if changed_default not in CHANGED_FIELD_NAMES:
            changed_default = CHANGED_FIELD_NAMES[0]
        changed_ui = changed_col.selectbox(
            'changed',
            options=CHANGED_FIELD_NAMES,
            index=CHANGED_FIELD_NAMES.index(changed_default),
            key='library_exp_changed_selector',
        )
        st.session_state['library_changed_field'] = changed_ui

        show_specs = [s for s in EXPERIMENT_FIELD_SPECS if s['ui'] != changed_ui]

        for i in range(0, len(show_specs), 3):
            row_cols = st.columns(3)
            for j, spec in enumerate(show_specs[i:i + 3]):
                ui_label = spec['ui']
                db_name = spec['db']
                latest_val = latest_row.get(db_name)

                if spec['kind'] == 'lot_select':
                    option_values = [None] + sorted(lot_options.keys())
                    default_lot = None
                    if latest_val is not None:
                        try:
                            default_lot = int(latest_val)
                        except Exception:
                            default_lot = None
                    default_idx = option_values.index(default_lot) if default_lot in option_values else 0
                    form_values[db_name] = row_cols[j].selectbox(
                        f'{ui_label} *',
                        options=option_values,
                        index=default_idx,
                        format_func=lambda x, _m=lot_options: (
                            'Select lot'
                            if x is None
                            else _m.get(x, '')
                        ),
                        key=f'library_exp_{db_name}',
                    )
                else:
                    default_val = '' if latest_val is None else str(latest_val)
                    if default_val == '':
                        default_val = EXPERIMENT_DEFAULT_VALUES.get(db_name, '')
                    form_values[db_name] = row_cols[j].text_input(
                        f'{ui_label} *',
                        value=default_val,
                        placeholder='not empty',
                        key=f'library_exp_{db_name}',
                    )

        save_clicked = st.button('Save experiment', key='library_save_experiment', width='content')

        if save_clicked:
            title = (form_values.get('experiment_name') or '').strip()
            if title == '':
                st.error('Not empty required: experiment_title')
                return

            payload = {'experiment_date': _get_latest_upload_date()}
            payload['experiment_name'] = title
            payload['operator_name'] = (latest_row.get('operator_name') or 'A.Li')
            payload['changed_parameter'] = changed_ui

            # Start from baseline to avoid refilling unchanged items.
            if has_baseline:
                for spec in EXPERIMENT_FIELD_SPECS:
                    db_name = spec['db']
                    if db_name in latest_row:
                        payload[db_name] = latest_row.get(db_name)

            missing = []
            convert_errors = []
            target_specs = [s for s in EXPERIMENT_FIELD_SPECS if s['ui'] != changed_ui]

            for spec in target_specs:
                ui_label = spec['ui']
                db_name = spec['db']
                raw = form_values.get(db_name)

                if spec['kind'] == 'lot_select':
                    if raw is None:
                        missing.append(ui_label)
                        continue
                    payload[db_name] = int(raw)
                    continue

                raw_text = (raw or '').strip()
                if raw_text == '':
                    missing.append(ui_label)
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
                    _insert_experiment(payload)
                    st.success('Experiment saved.')
                    st.rerun()
                except Exception as e:
                    st.error(f'Failed to save experiment: {e}')
    else:
        exp_df = _load_experiments_df()
        if exp_df.empty:
            st.info('No experiments found.')
            return
        display_df = exp_df.copy()
        selected_id = st.session_state.get('library_selected_experiment_id')
        display_df.insert(0, 'select', display_df['experiment_id'] == selected_id)
        edited = st.data_editor(
            display_df,
            hide_index=True,
            width='stretch',
            key='library_existing_experiment_editor',
            column_config={
                'select': st.column_config.CheckboxColumn('select')
            },
        )
        selected_rows = edited[edited['select'] == True]  # noqa: E712
        if not selected_rows.empty:
            new_selected = int(selected_rows.iloc[0]['experiment_id'])
            st.session_state['library_selected_experiment_id'] = new_selected
            st.caption(f'Selected experiment_id: {new_selected}')
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
        </style>
        """,
        unsafe_allow_html=True,
    )

    uploads_dir = Path(__file__).parent / 'uploads'
    uploads_dir.mkdir(exist_ok=True)
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
                src_img = Image.open(uploaded)
                src_img = ImageOps.exif_transpose(src_img)
                image_dt = _extract_image_datetime(src_img)
                img = src_img.convert('RGB')
                file_size = getattr(uploaded, 'size', None)
                file_sig = f"{name}::{file_size}"
                if file_sig not in st.session_state['library_file_ids']:
                    st.session_state['library_id_counter'] += 1
                    st.session_state['library_file_ids'][
                        file_sig] = f"{st.session_state['library_id_counter']:05d}"
                img_id = st.session_state['library_file_ids'][file_sig]

                # Original grayscale (no enhancement)
                gray = process_image_to_grayscale(img.copy())
                # Enhanced detection image
                enhanced = build_enhanced_detection_image(gray)
                # Binary image for bar detection
                black_white = build_black_white_image(enhanced)

                images.append((img_id, name, img.copy(),
                              gray, enhanced, black_white, image_dt))
            except UnidentifiedImageError:
                st.warning(f'File {name} is not a recognized image.')
            except Exception as e:
                st.warning(f'Failed to open {name}: {e}')

    if images:
        st.subheader('Images')
        default_changed = st.session_state.get('library_changed_field', CHANGED_FIELD_NAMES[0])
        if default_changed not in CHANGED_FIELD_NAMES:
            default_changed = CHANGED_FIELD_NAMES[0]
        selected_changed_field = st.selectbox(
            'changed *',
            options=CHANGED_FIELD_NAMES,
            index=CHANGED_FIELD_NAMES.index(default_changed),
            key='library_images_changed_selector',
        )
        changed_value = st.text_input(
            f'{selected_changed_field} *',
            value=st.session_state.get('library_changed_value', ''),
            key='library_changed_value_input',
            placeholder='not empty',
        )
        st.session_state['library_changed_value'] = changed_value
        st.session_state['library_changed_field'] = selected_changed_field
        changed_value_required_missing = (changed_value or '').strip() == ''

        for img_id, name, img, gray, enhanced, black_white, image_dt in images:
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
                        st.rerun()
                with id_col:
                    st.markdown(f"ID\n\n`{img_id}`")

            analysis = analyze_library_image(gray)
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
                        columns={'gray_mean': 'dark_value'}
                    )
                    st.dataframe(mean_only_df, width='stretch')
            else:
                with cols[1]:
                    st.info(f"No dark line regions detected: {name}")
                with cols[2]:
                    st.empty()

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

                now = image_dt or datetime.now()
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
                    'ratio': round(float(ratio_val), 4) if ratio_val is not None else None,
                    'ct_bg_sum': round(float(ct_bg_sum_val), 4) if ct_bg_sum_val is not None else None,
                    'starred': 1 if is_starred else 0,
                    'changed_field': selected_changed_field,
                    'changed_value': changed_value.strip() if not changed_value_required_missing else None,
                    'detail': detail_payload,
                    'date': now.strftime('%Y-%m-%d'),
                    'time': now.strftime('%H:%M:%S'),
                    'timestamp': now.isoformat(timespec='seconds')
                }
                upsert_upload_record(entry)
            except Exception:
                st.warning('Failed to save cropped image or write to uploads.db')
        if changed_value_required_missing:
            st.warning('changed value is empty. Please fill it for this upload batch.')

    if tables:
        st.subheader('Datasets')
        for name, df in tables:
            st.write(f'Preview — {name}')
            st.dataframe(df.head(50))
