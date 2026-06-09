from pathlib import Path, PureWindowsPath
import sqlite3
from datetime import date

import streamlit as st
import pandas as pd
from PIL import Image, ImageOps
from image_processing import process_image_to_grayscale, analyze_library_image
from database import DB_PATH, sync_experiment_db
from uploads_db import get_upload_detail_by_id, init_uploads_db, update_upload_detail, upsert_upload_record
from ui_labels import display_label


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


def _should_auto_star(analysis):
    status = str(analysis.get('line_detection_status') or '').strip()
    if status:
        return status == 'failed'
    return int(analysis.get('recrop_results_count', 0) or 0) != 2


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


def _resolve_existing_image_path(path_str):
    raw_path = str(path_str or '').strip()
    if raw_path == '':
        return None

    direct_path = Path(raw_path)
    if direct_path.exists():
        return direct_path

    posix_name = Path(raw_path.replace('\\', '/')).name
    windows_name = PureWindowsPath(raw_path).name
    for filename in (posix_name, windows_name):
        filename = str(filename or '').strip()
        if filename == '':
            continue
        fallback_path = Path(__file__).parent / 'uploads' / filename
        if fallback_path.exists():
            return fallback_path

    return None


def _is_experiment_older_than_two_days(experiment_row):
    if not isinstance(experiment_row, dict):
        return False
    raw_date = str(experiment_row.get('experiment_date') or '').strip()
    if raw_date == '':
        return False
    try:
        exp_date = date.fromisoformat(raw_date)
    except ValueError:
        return False
    return abs((date.today() - exp_date).days) > 2


def _is_experiment_older_than_three_days(experiment_row):
    if not isinstance(experiment_row, dict):
        return False
    raw_date = str(experiment_row.get('experiment_date') or '').strip()
    if raw_date == '':
        return False
    try:
        exp_date = date.fromisoformat(raw_date)
    except ValueError:
        return False
    return abs((date.today() - exp_date).days) > 3


def _prune_hidden_detail_images(detail_id, detail_entry, experiment_row):
    if not _is_experiment_older_than_three_days(experiment_row):
        return False

    detail = dict(detail_entry.get('detail', {}) or {})
    images = dict(detail.get('images', {}) or {})

    delete_keys = [
        'gray_path',
        'cropped_path',
        'cropped_trimmed_path',
        'vertical_crop_path',
        'recrop_path',
    ]

    changed = False
    for key in delete_keys:
        path_str = str(images.get(key) or '').strip()
        if path_str:
            try:
                Path(path_str).unlink(missing_ok=True)
            except Exception:
                pass
            images[key] = ''
            changed = True

    updated_detail = dict(detail)
    updated_detail['images'] = images

    if not changed:
        return False

    update_upload_detail(detail_id, updated_detail)
    upsert_upload_record({
        'id': detail_id,
        'original_name': detail_entry.get('original_name'),
        'original_path': detail_entry.get('original_path'),
        'gray_path': '',
        'cropped_name': detail_entry.get('cropped_name'),
        'cropped_path': '',
        'dark_regions_path': images.get('dark_regions_path', detail_entry.get('dark_regions_path', '')),
        'starred': detail_entry.get('starred'),
        'detail': updated_detail,
    })
    return True


def cleanup_old_detail_images_on_startup():
    today_key = date.today().isoformat()
    if st.session_state.get('startup_old_detail_cleanup_day') == today_key:
        return

    init_uploads_db()
    sync_experiment_db()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT
                ur.id AS detail_id,
                sr.experiment_id AS experiment_id
            FROM upload_records ur
            LEFT JOIN strip_results sr
              ON sr.strip_id = ur.id
            ORDER BY
                CASE
                    WHEN ur.id GLOB '[0-9]*' THEN CAST(ur.id AS INTEGER)
                    ELSE NULL
                END ASC,
                ur.id ASC
            """
        ).fetchall()
    finally:
        conn.close()

    for row in rows:
        detail_id = str(row['detail_id'])
        detail_entry = get_upload_detail_by_id(detail_id)
        if detail_entry is None:
            continue

        experiment_row = None
        experiment_id = row['experiment_id']
        if experiment_id is not None:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            try:
                experiment_data = conn.execute(
                    'SELECT * FROM experiments WHERE experiment_id = ? LIMIT 1',
                    (experiment_id,),
                ).fetchone()
                experiment_row = dict(experiment_data) if experiment_data else None
            finally:
                conn.close()

        _prune_hidden_detail_images(detail_id, detail_entry, experiment_row)

    st.session_state['startup_old_detail_cleanup_day'] = today_key


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
        column_config={col: st.column_config.Column(display_label(col)) for col in render_row.keys()},
    ).copy()


def _save_optional_image(img, path_str):
    if img is None or not path_str:
        return
    path = Path(path_str)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def _normalize_detail_output_path(path_value, default_path, uploads_dir):
    path_text = str(path_value or '').strip()
    if not path_text:
        return str(default_path)
    candidate = Path(path_text)
    # Old records may still point to a different checkout; rewrite generated
    # output files into the current project's uploads directory.
    if candidate.parent != uploads_dir:
        return str(default_path)
    return str(candidate)


def _detail_output_paths(detail_id, detail_entry, images):
    uploads_dir = Path(__file__).parent / 'uploads'
    uploads_dir.mkdir(parents=True, exist_ok=True)
    return {
        'gray_path': _normalize_detail_output_path(
            images.get('gray_path') or detail_entry.get('gray_path'),
            uploads_dir / f'{detail_id}_gray.png',
            uploads_dir,
        ),
        'cropped_path': _normalize_detail_output_path(
            images.get('cropped_path') or detail_entry.get('cropped_path'),
            uploads_dir / f'{detail_id}_cropped.png',
            uploads_dir,
        ),
        'cropped_vertical_path': _normalize_detail_output_path(
            images.get('cropped_vertical_path'),
            uploads_dir / f'{detail_id}_cropped_vertical.png',
            uploads_dir,
        ),
        'cropped_trimmed_path': _normalize_detail_output_path(
            images.get('cropped_trimmed_path'),
            uploads_dir / f'{detail_id}_cropped_trimmed.png',
            uploads_dir,
        ),
        'vertical_crop_path': _normalize_detail_output_path(
            images.get('vertical_crop_path'),
            uploads_dir / f'{detail_id}_vertical_crop.png',
            uploads_dir,
        ),
        'dark_regions_path': _normalize_detail_output_path(
            images.get('dark_regions_path') or detail_entry.get('dark_regions_path'),
            uploads_dir / f'{detail_id}_dark_regions.png',
            uploads_dir,
        ),
        'recrop_path': _normalize_detail_output_path(
            images.get('recrop_path'),
            uploads_dir / f'{detail_id}_recrop.png',
            uploads_dir,
        ),
    }


def _update_strip_results_analysis(
    strip_id,
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
    conn = sqlite3.connect(DB_PATH)
    try:
        test_raw = float(t_val) if t_val is not None else None
        reference_raw = float(c_val) if c_val is not None else None
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
            UPDATE strip_results
            SET
                test_line_raw_intensity = ?,
                reference_line_raw_intensity = ?,
                test_line_corrected_intensity = ?,
                reference_line_corrected_intensity = ?,
                test_reference_ratio = ?,
                reference_test_ratio = ?,
                overall_membrane_background = ?,
                ct_bg_sum = ?,
                valid_strip = ?,
                failure_reason = ?,
                quality_flags = ?
            WHERE strip_id = ?
            """,
            (
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
                str(strip_id),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _delete_strip_result(strip_id):
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            'DELETE FROM strip_results WHERE strip_id = ?',
            (str(strip_id),),
        )
        conn.commit()
    finally:
        conn.close()


def _delete_upload_record_and_files(record_id):
    record_id = str(record_id)
    upload_entry = get_upload_detail_by_id(record_id)
    file_candidates = []
    if upload_entry:
        for path_value in (
            upload_entry.get('original_path'),
            upload_entry.get('gray_path'),
            upload_entry.get('cropped_path'),
            upload_entry.get('dark_regions_path'),
        ):
            if path_value:
                file_candidates.append(Path(path_value))
        detail = dict(upload_entry.get('detail', {}) or {})
        images = dict(detail.get('images', {}) or {})
        for path_value in images.values():
            if path_value:
                file_candidates.append(Path(str(path_value)))

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            'DELETE FROM upload_records WHERE id = ?',
            (record_id,),
        )
        conn.commit()
    finally:
        conn.close()

    uploads_dir = Path(__file__).parent / 'uploads'
    file_candidates.extend(uploads_dir.glob(f'{record_id}_*'))
    seen_paths = set()
    for path_obj in file_candidates:
        try:
            resolved = path_obj.resolve()
        except Exception:
            resolved = path_obj
        if resolved in seen_paths:
            continue
        seen_paths.add(resolved)
        try:
            if path_obj.exists() and path_obj.is_file():
                path_obj.unlink()
        except Exception:
            pass


def _redo_detail_processing(detail_id, detail_entry):
    detail = dict(detail_entry.get('detail', {}) or {})
    images = dict(detail.get('images', {}) or {})
    original_path = str(images.get('manual_crop_path') or images.get('original_path') or detail_entry.get('original_path') or '').strip()
    if not original_path:
        raise ValueError('Original image path not found.')
    source_path = _resolve_existing_image_path(original_path)
    if source_path is None:
        raise ValueError('Original image file does not exist.')

    with Image.open(source_path) as src_img:
        original_img = src_img.convert('RGB')

    gray = process_image_to_grayscale(original_img.copy())
    analysis = analyze_library_image(gray)

    output_paths = _detail_output_paths(detail_id, detail_entry, images)
    gray_path = output_paths['gray_path']
    cropped_path = output_paths['cropped_path']
    cropped_vertical_path = output_paths['cropped_vertical_path']
    cropped_trimmed_path = output_paths['cropped_trimmed_path']
    vertical_crop_path = output_paths['vertical_crop_path']
    dark_regions_path = output_paths['dark_regions_path']
    recrop_path = output_paths['recrop_path']

    _save_optional_image(gray, gray_path)
    _save_optional_image(analysis.get('cropped'), cropped_path)
    _save_optional_image(analysis.get('vertical_overlay'), cropped_vertical_path)
    _save_optional_image(analysis.get('analysis_img_trimmed'), cropped_trimmed_path)
    _save_optional_image(analysis.get('cropped_between'), vertical_crop_path)
    _save_optional_image(analysis.get('cropped_overlay'), dark_regions_path)
    _save_optional_image(analysis.get('recrop_overlay'), recrop_path)

    images['gray_path'] = gray_path
    images['cropped_path'] = cropped_path
    images['cropped_vertical_path'] = cropped_vertical_path if Path(cropped_vertical_path).exists() else ''
    images['cropped_trimmed_path'] = cropped_trimmed_path if Path(cropped_trimmed_path).exists() else ''
    images['vertical_crop_path'] = vertical_crop_path if vertical_crop_path and Path(vertical_crop_path).exists() else ''
    images['dark_regions_path'] = dark_regions_path if dark_regions_path and Path(dark_regions_path).exists() else ''
    images['recrop_path'] = recrop_path if recrop_path and Path(recrop_path).exists() else ''
    detail['images'] = images
    detail['vertical_crop_reason'] = analysis.get('vertical_crop_reason', '')
    detail['line_detection_status'] = analysis.get('line_detection_status', '')
    detail['confidence_score'] = analysis.get('confidence_score', 0.0)
    detail['quality_flags'] = list(analysis.get('quality_flags', []) or [])
    detail['line_candidates'] = list(analysis.get('line_candidates', []) or [])
    detail['selected_line_count'] = int(analysis.get('selected_line_count', 0) or 0)
    detail['trim_percent_used'] = int(analysis.get('trim_percent_used', 20) or 20)
    detail['recrop_results_count'] = int(analysis.get('recrop_results_count', 0) or 0)
    update_upload_detail(detail_id, detail)

    # Redo should refresh the star state to match the latest detection result.
    effective_starred = bool(_should_auto_star(analysis))

    upsert_upload_record({
        'id': detail_id,
        'original_name': detail_entry.get('original_name'),
        'original_path': detail_entry.get('original_path'),
        'gray_path': gray_path,
        'cropped_name': detail_entry.get('cropped_name'),
        'cropped_path': cropped_path,
        'dark_regions_path': dark_regions_path if dark_regions_path and Path(dark_regions_path).exists() else '',
        'starred': 1 if effective_starred else 0,
        'detail': detail,
    })

    _update_strip_results_analysis(
        detail_id,
        analysis.get('c'),
        analysis.get('t'),
        analysis.get('bg'),
        analysis.get('ratio'),
        analysis.get('ct_bg_sum'),
        analysis.get('vertical_crop_reason', ''),
        analysis.get('line_detection_status', ''),
        analysis.get('confidence_score', 0.0),
        analysis.get('quality_flags', []),
    )


def _save_manual_crop(detail_id, detail, original_img, crop_box):
    uploads_dir = Path(__file__).parent / 'uploads'
    uploads_dir.mkdir(parents=True, exist_ok=True)
    output_path = uploads_dir / f'{detail_id}_manual_crop.png'
    cropped = original_img.crop(crop_box)
    cropped.save(output_path)

    updated_detail = dict(detail or {})
    images = dict(updated_detail.get('images', {}) or {})
    images['manual_crop_path'] = str(output_path)
    updated_detail['images'] = images
    updated_detail['manual_crop_box'] = {
        'left': int(crop_box[0]),
        'top': int(crop_box[1]),
        'right': int(crop_box[2]),
        'bottom': int(crop_box[3]),
    }
    update_upload_detail(detail_id, updated_detail)


def _clear_manual_crop(detail_id, detail):
    updated_detail = dict(detail or {})
    images = dict(updated_detail.get('images', {}) or {})
    manual_crop_path = str(images.get('manual_crop_path') or '').strip()
    if manual_crop_path:
        try:
            Path(manual_crop_path).unlink(missing_ok=True)
        except Exception:
            pass
    images['manual_crop_path'] = ''
    updated_detail['images'] = images
    updated_detail.pop('manual_crop_box', None)
    update_upload_detail(detail_id, updated_detail)


def _render_original_crop_editor(detail_id, detail, original_path):
    if not original_path:
        return
    p = _resolve_existing_image_path(original_path)
    if p is None:
        return

    with Image.open(p) as src_img:
        original_img = src_img.convert('RGB')

    width, height = original_img.size
    saved_box = dict(detail.get('manual_crop_box', {}) or {})

    st.write('Original crop editor')
    ctrl_cols = st.columns(4)
    left = ctrl_cols[0].slider(
        'left',
        min_value=0,
        max_value=max(0, width - 1),
        value=int(saved_box.get('left', 0)),
        key=f'detail_crop_left_{detail_id}',
    )
    top = ctrl_cols[1].slider(
        'top',
        min_value=0,
        max_value=max(0, height - 1),
        value=int(saved_box.get('top', 0)),
        key=f'detail_crop_top_{detail_id}',
    )
    right_min = min(width, max(left + 1, 1))
    right_default = int(saved_box.get('right', width))
    right_default = min(width, max(right_default, right_min))
    right = ctrl_cols[2].slider(
        'right',
        min_value=right_min,
        max_value=width,
        value=right_default,
        key=f'detail_crop_right_{detail_id}',
    )
    bottom_min = min(height, max(top + 1, 1))
    bottom_default = int(saved_box.get('bottom', height))
    bottom_default = min(height, max(bottom_default, bottom_min))
    bottom = ctrl_cols[3].slider(
        'bottom',
        min_value=bottom_min,
        max_value=height,
        value=bottom_default,
        key=f'detail_crop_bottom_{detail_id}',
    )

    crop_box = (int(left), int(top), int(right), int(bottom))
    crop_preview = original_img.crop(crop_box)

    preview_cols = st.columns([1.1, 1.1, 1.2])
    with preview_cols[0]:
        st.write('Original')
        st.image(_to_uniform_canvas(original_img, 260, 260), width='stretch')
    with preview_cols[1]:
        st.write('Crop preview')
        st.image(_to_uniform_canvas(crop_preview, 260, 260), width='stretch')
    with preview_cols[2]:
        st.write(f'Crop box: {crop_box}')
        save_clicked = st.button('Save crop', key=f'detail_save_crop_{detail_id}', width='content')
        clear_clicked = st.button('Clear crop', key=f'detail_clear_crop_{detail_id}', width='content')
        if save_clicked:
            try:
                _save_manual_crop(detail_id, detail, original_img, crop_box)
                st.success('Manual crop saved.')
                st.rerun()
            except Exception as e:
                st.error(f'Failed to save manual crop: {e}')
        if clear_clicked:
            try:
                _clear_manual_crop(detail_id, detail)
                st.success('Manual crop cleared.')
                st.rerun()
            except Exception as e:
                st.error(f'Failed to clear manual crop: {e}')


def render_insight_detail_page(detail_id):
    st.subheader(f'Result Detail - ID {detail_id}')
    if st.button('Back to Results', key='back_to_insights'):
        st.query_params.clear()
        st.rerun()

    init_uploads_db()
    detail_entry = get_upload_detail_by_id(detail_id)
    if detail_entry is None:
        st.warning('Detail record not found in experiment_data.db.')
        return

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

    if _prune_hidden_detail_images(detail_id, detail_entry, experiment_row):
        detail_entry = get_upload_detail_by_id(detail_id)

    detail = detail_entry.get('detail', {})
    images = detail.get('images', {})
    vertical_crop_reason = detail.get('vertical_crop_reason', '')
    line_detection_status = detail.get('line_detection_status', '')
    confidence_score = detail.get('confidence_score', None)
    quality_flags = list(detail.get('quality_flags', []) or [])
    trim_percent_used = int(detail.get('trim_percent_used', 20) or 20)
    original_path = images.get('original_path', detail_entry.get('original_path', ''))

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

    action_cols = st.columns([1, 1, 1, 3])
    with action_cols[0]:
        if st.button('Redo', key=f'detail_redo_{detail_id}', width='content'):
            try:
                _redo_detail_processing(detail_id, detail_entry)
                st.success('Image analysis redone.')
                st.rerun()
            except Exception as e:
                st.error(f'Failed to redo image analysis: {e}')
    with action_cols[1]:
        if st.button('Delete', key=f'detail_delete_{detail_id}', width='content'):
            try:
                _delete_strip_result(detail_id)
                _delete_upload_record_and_files(detail_id)
                st.query_params.clear()
                st.rerun()
            except Exception as e:
                st.error(f'Failed to delete strip result: {e}')

    if line_detection_status:
        status_text = str(line_detection_status).replace('_', ' ').title()
        confidence_text = ''
        if confidence_score is not None:
            try:
                confidence_text = f' ({float(confidence_score):.2f})'
            except Exception:
                confidence_text = ''
        if line_detection_status == 'good':
            st.success(f'Detection: {status_text}{confidence_text}')
        elif line_detection_status == 'needs_review':
            st.warning(f'Detection: {status_text}{confidence_text}')
        elif line_detection_status and line_detection_status != 'good':
            st.error(f'Detection: {status_text}{confidence_text}')
        if quality_flags:
            st.caption('Review flags: ' + ', '.join(str(flag).replace('_', ' ') for flag in quality_flags))

    _render_original_crop_editor(detail_id, detail, original_path)

    default_show_paths = [
        ('1. Original', original_path),
        ('1b. Manual Crop', images.get('manual_crop_path', '')),
        ('2. Grayscale', images.get('gray_path', detail_entry.get('gray_path', ''))),
        ('3. Cropped', images.get('cropped_path', detail_entry.get('cropped_path', ''))),
        ('4. Cropped Vertical Overlay', images.get('cropped_vertical_path', images.get('cropped_path', detail_entry.get('cropped_path', '')))),
        ('5. Vertical Crop (Length Limited)', images.get('vertical_crop_path', '')),
        (f'6. Cropped (Top/Bottom {trim_percent_used}% Removed)', images.get('cropped_trimmed_path', '')),
        ('7. Dark Regions Overlay', images.get('dark_regions_path', detail_entry.get('dark_regions_path', ''))),
        ('8. Re-Crop Overlay', images.get('recrop_path', '')),
    ]
    if _is_experiment_older_than_two_days(experiment_row):
        primary_caption = '1b. Manual Crop' if images.get('manual_crop_path', '') else '1. Original'
        primary_path = images.get('manual_crop_path', '') or original_path
        show_paths = [
            (primary_caption, primary_path),
            ('4. Cropped Vertical Overlay', images.get('cropped_vertical_path', images.get('cropped_path', detail_entry.get('cropped_path', '')))),
            ('7. Dark Regions Overlay', images.get('dark_regions_path', detail_entry.get('dark_regions_path', ''))),
        ]
    else:
        show_paths = default_show_paths
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
        p = _resolve_existing_image_path(img_path)
        if p is None:
            continue
        with cols[col_idx % 3]:
            img = Image.open(p)
            st.write(caption)
            st.image(_to_uniform_canvas(img, 260, 260), width='stretch')
        col_idx += 1
