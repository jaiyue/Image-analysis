from pathlib import Path
import sqlite3

import streamlit as st
import pandas as pd
from PIL import Image, ImageOps
from database import DB_PATH, sync_experiment_db
from uploads_db import get_upload_detail_by_id, init_uploads_db


IMAGE_ANALYSIS_FIELDS = [
    'test_line_raw_intensity',
    'reference_line_raw_intensity',
    'test_line_corrected_intensity',
    'reference_line_corrected_intensity',
    'test_reference_ratio',
    'reference_test_ratio',
    'overall_membrane_background',
    'ct_bg_sum',
    'valid_strip',
    'failure_reason',
    'quality_flags',
]

STRIP_RESULTS_META_FIELDS = [
    'changed_field',
    'image_filename',
    'sample_equivalent_mg_ml',
    'dilution_equivalent',
    'image_upload_datetime',
    'read_time_minutes',
    'anomaly_flag',
]

STRIP_RESULTS_DISPLAY_FIELDS = [
    'strip_id',
    'experiment_id',
    'condition_value',
    *IMAGE_ANALYSIS_FIELDS,
    *STRIP_RESULTS_META_FIELDS,
]


def _resize_to_height(img, target_h=260):
    if img.height <= 0 or target_h <= 0:
        return img
    if img.height == target_h:
        return img
    new_w = max(1, int(round(img.width * (target_h / float(img.height)))))
    return img.resize((new_w, target_h))


def _to_uniform_canvas(img, target_w=260, target_h=260, bg=245):
    base = Image.new('RGB', (target_w, target_h), (bg, bg, bg))
    src = img.convert('RGB')
    src = ImageOps.contain(src, (target_w, target_h))
    x = (target_w - src.width) // 2
    y = (target_h - src.height) // 2
    base.paste(src, (x, y))
    return base


def _r4(v):
    if v is None:
        return None
    try:
        return round(float(v), 4)
    except Exception:
        return v


def _fetch_one(conn, table_name, key_name, key_value):
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        f'SELECT * FROM "{table_name}" WHERE "{key_name}" = ? LIMIT 1',
        (key_value,),
    ).fetchone()
    if row is None:
        return None
    return dict(row)


def _normalize_cell_value(v):
    try:
        if pd.isna(v):
            return None
    except Exception:
        pass
    return v


def _row_dict_from_df(df):
    if df is None or df.empty:
        return None
    row = df.iloc[0].to_dict()
    return {k: _normalize_cell_value(v) for k, v in row.items()}


def _apply_strip_override_to_experiment_row(experiment_row, strip_row):
    if not isinstance(experiment_row, dict) or not isinstance(strip_row, dict):
        return experiment_row

    condition_label = experiment_row.get('condition')
    changed_value = strip_row.get('condition_value')
    if condition_label is None:
        return dict(experiment_row)

    key_candidates = []
    label = str(condition_label).strip()
    if label:
        key_candidates.append(label)
        key_candidates.append(label.replace(' ', '_'))

    if changed_value is None:
        return dict(experiment_row)
    changed_text = str(changed_value).strip()
    if changed_text == '':
        return dict(experiment_row)

    merged = dict(experiment_row)
    for k in key_candidates:
        if k in merged:
            merged[k] = changed_value
            break
    return merged


def _update_row(conn, table_name, pk_name, row_dict):
    if not row_dict or pk_name not in row_dict:
        return
    pk_value = row_dict.get(pk_name)
    set_cols = [c for c in row_dict.keys() if c != pk_name]
    if not set_cols:
        return
    set_sql = ', '.join([f'"{c}" = ?' for c in set_cols])
    values = [_normalize_cell_value(row_dict.get(c)) for c in set_cols]
    values.append(pk_value)
    conn.execute(
        f'UPDATE "{table_name}" SET {set_sql} WHERE "{pk_name}" = ?',
        values,
    )


def _project_row_fields(row_dict, ordered_fields):
    if not isinstance(row_dict, dict):
        return {}
    out = {}
    for field in ordered_fields:
        if field in row_dict:
            out[field] = row_dict.get(field)
    for key, value in row_dict.items():
        if key in out:
            continue
        out[key] = value
    return out


def _render_table_editor(row_dict, edit_mode, key_prefix, width='stretch', hide_cols=None):
    if not row_dict:
        return None
    render_row = dict(row_dict)
    for c in (hide_cols or []):
        render_row.pop(c, None)
    return st.data_editor(
        pd.DataFrame([render_row]),
        hide_index=True,
        key=key_prefix,
        width=width,
        disabled=(not edit_mode),
    ).copy()


def render_insight_detail_page(detail_id):
    st.subheader(f'Insight Detail - ID {detail_id}')
    if st.button('Back to Insights', key='back_to_insights'):
        st.query_params.clear()
        st.rerun()

    init_uploads_db()
    detail_entry = get_upload_detail_by_id(detail_id)
    if detail_entry is None:
        st.warning('Detail record not found in experiment_data.db.')
        return

    detail = detail_entry.get('detail', {})
    images = detail.get('images', {})
    vertical_crop_reason = detail.get('vertical_crop_reason', '')

    show_paths = [
        ('1. Original', images.get('original_path', detail_entry.get('original_path', ''))),
        ('2. Grayscale', images.get('gray_path', detail_entry.get('gray_path', ''))),
        ('3. Cropped', images.get('cropped_path', detail_entry.get('cropped_path', ''))),
        ('4. Cropped Vertical Overlay', images.get('cropped_vertical_path', images.get('cropped_path', detail_entry.get('cropped_path', '')))),
        ('5. Vertical Crop (Length Limited)', images.get('vertical_crop_path', '')),
        ('6. Cropped (Top/Bottom 20% Removed)', images.get('cropped_trimmed_path', '')),
        ('7. Dark Regions Overlay', images.get('dark_regions_path', detail_entry.get('dark_regions_path', ''))),
        ('8. Re-Crop Overlay', images.get('recrop_path', '')),
    ]
    cols = st.columns(3)
    col_idx = 0
    for caption, img_path in show_paths:
        if not img_path:
            if caption.startswith('5. Vertical Crop'):
                reason_map = {
                    'only_one_vertical_line': 'Vertical crop not generated: only one vertical line detected.',
                    'no_vertical_lines': 'Vertical crop not generated: no vertical lines detected.',
                    'width_insufficient': 'Vertical crop not generated: width between two lines is insufficient.',
                    'single_line_width_insufficient': 'Vertical crop not generated: single detected line width is insufficient.',
                }
                if vertical_crop_reason in reason_map:
                    st.info(reason_map[vertical_crop_reason])
            continue
        p = Path(img_path)
        if not p.exists():
            continue
        with cols[col_idx % 3]:
            img = Image.open(p)
            st.write(caption)
            st.image(_to_uniform_canvas(img, 260, 260), width='stretch')
        col_idx += 1

    sync_experiment_db()
    strip_row = None
    experiment_row = None
    experiment_display_row = None
    if DB_PATH.exists():
        conn = sqlite3.connect(DB_PATH)
        try:
            strip_row = _fetch_one(conn, 'strip_results', 'strip_id', str(detail_id))
            if strip_row and strip_row.get('experiment_id') is not None:
                experiment_row = _fetch_one(conn, 'experiments', 'experiment_id', strip_row.get('experiment_id'))
                experiment_display_row = _apply_strip_override_to_experiment_row(experiment_row, strip_row)
        finally:
            conn.close()

    edit_key = f'detail_edit_mode_{detail_id}'
    prev_edit_key = f'detail_prev_edit_mode_{detail_id}'
    prev_edit_mode = bool(st.session_state.get(prev_edit_key, False))
    edit_mode = st.toggle('Edit tables', key=edit_key)
    st.session_state[prev_edit_key] = bool(edit_mode)

    strip_cache_key = f'detail_strip_cache_{detail_id}'
    exp_cache_key = f'detail_experiment_cache_{detail_id}'

    if prev_edit_mode and not edit_mode:
        conn = sqlite3.connect(DB_PATH)
        try:
            strip_df = st.session_state.get(strip_cache_key)
            exp_df = st.session_state.get(exp_cache_key)
            strip_data = _row_dict_from_df(strip_df)
            exp_data = _row_dict_from_df(exp_df)
            if strip_data:
                _update_row(conn, 'strip_results', 'strip_id', strip_data)
            if exp_data:
                _update_row(conn, 'experiments', 'experiment_id', exp_data)
            conn.commit()
            st.success('Table changes saved.')
            strip_row = _fetch_one(conn, 'strip_results', 'strip_id', str(detail_id))
            if strip_row and strip_row.get('experiment_id') is not None:
                experiment_row = _fetch_one(conn, 'experiments', 'experiment_id', strip_row.get('experiment_id'))
                experiment_display_row = _apply_strip_override_to_experiment_row(experiment_row, strip_row)
            else:
                experiment_row = None
                experiment_display_row = None
        except Exception as e:
            st.error(f'Failed to save table changes: {e}')
        finally:
            conn.close()

    st.write('strip_results')
    if strip_row:
        strip_display_row = _project_row_fields(strip_row, STRIP_RESULTS_DISPLAY_FIELDS)
        strip_df = _render_table_editor(
            strip_display_row,
            edit_mode=edit_mode,
            key_prefix=f'detail_strip_editor_{detail_id}_{"edit" if edit_mode else "view"}',
        )
        if edit_mode and strip_df is not None:
            st.session_state[strip_cache_key] = strip_df
    else:
        st.info('No strip_results record for this image.')

    st.write('experiments')
    if experiment_row:
        if edit_mode:
            st.caption('Edit mode updates base experiment row. Per-image override is shown in view mode.')
            exp_df = _render_table_editor(
                experiment_row,
                edit_mode=True,
                key_prefix=f'detail_experiment_editor_{detail_id}_edit',
            )
            if exp_df is not None:
                st.session_state[exp_cache_key] = exp_df
        else:
            _render_table_editor(
                experiment_display_row or experiment_row,
                edit_mode=False,
                key_prefix=f'detail_experiment_editor_{detail_id}_view',
            )
    else:
        st.info('No experiments record linked to this image.')
