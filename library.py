# library.py — Library page with center‑based closest bars cropping

import streamlit as st
import pandas as pd
from image_processing import (
    process_image_to_grayscale,
    build_enhanced_detection_image,
    build_black_white_image,
    build_intensity_profile,
    detect_line_regions,
    measure_line_darkness,
)
from pathlib import Path
import json
import io
from datetime import datetime

try:
    from PIL import Image, UnidentifiedImageError
except Exception:
    Image = None
    UnidentifiedImageError = Exception


def render_library_page():
    st.title('Library')
    st.write(
        'Upload images or CSV datasets. Images show as thumbnails; CSVs show a preview.')

    uploads_dir = Path(__file__).parent / 'uploads'
    uploads_dir.mkdir(exist_ok=True)
    standard_ref_path = Path(__file__).parent / 'standard_reference.json'

    standard_ref_values = []
    try:
        if standard_ref_path.exists():
            with standard_ref_path.open('r', encoding='utf-8') as f:
                ref_payload = json.load(f)
            for row in ref_payload.get('values', []):
                cid = row.get('id')
                cga = row.get('corrected_gray_avg')
                if cid is None or cga is None:
                    continue
                try:
                    standard_ref_values.append((int(cid), float(cga)))
                except (TypeError, ValueError):
                    continue
            standard_ref_values.sort(key=lambda x: x[1], reverse=True)
    except Exception:
        standard_ref_values = []

    def get_standard_id_range(gray_value):
        if not standard_ref_values:
            return '-'
        try:
            value = float(gray_value)
        except (TypeError, ValueError):
            return '-'

        if value >= standard_ref_values[0][1]:
            edge_id = standard_ref_values[0][0]
            return f"{edge_id}~{edge_id}"
        if value <= standard_ref_values[-1][1]:
            edge_id = standard_ref_values[-1][0]
            return f"{edge_id}~{edge_id}"

        for i in range(len(standard_ref_values) - 1):
            id_hi, val_hi = standard_ref_values[i]
            id_lo, val_lo = standard_ref_values[i + 1]
            if val_hi >= value >= val_lo:
                return f"{id_hi}~{id_lo}"
        return '-'

    meta_path = uploads_dir / 'meta.json'
    try:
        if meta_path.exists():
            with meta_path.open('r', encoding='utf-8') as f:
                meta = json.load(f)
        else:
            meta = []
    except Exception:
        meta = []

    if 'library_id_counter' not in st.session_state:
        st.session_state['library_id_counter'] = 0
    if 'library_file_ids' not in st.session_state:
        st.session_state['library_file_ids'] = {}
    if 'library_cached_uploads' not in st.session_state:
        st.session_state['library_cached_uploads'] = []
    if 'library_cached_signatures' not in st.session_state:
        st.session_state['library_cached_signatures'] = []

    detail_id = st.query_params.get('detail_id')
    if detail_id:
        detail_entry = None
        for item in reversed(meta):
            if str(item.get('id')) == str(detail_id):
                detail_entry = item
                break
        header_cols = st.columns([6, 1])
        with header_cols[0]:
            st.subheader(f'Detail - ID {detail_id}')
        with header_cols[1]:
            if st.button('Back', key='library_detail_back'):
                st.query_params.clear()
                st.rerun()
        if detail_entry is None:
            st.warning('Detail record not found in meta.json.')
            return
        st.write(f"Original file: {detail_entry.get('original_name', '-')}")
        dcols = st.columns(3)
        with dcols[0]:
            orig_path = detail_entry.get('original_path', '')
            if orig_path and Path(orig_path).exists():
                st.image(Image.open(orig_path), caption='Original', width='stretch')
        with dcols[1]:
            gray_path = detail_entry.get('gray_path', '')
            if gray_path and Path(gray_path).exists():
                st.image(Image.open(gray_path), caption='Grayscale', width='stretch')
        with dcols[2]:
            dark_path = detail_entry.get('dark_regions_path', '')
            if dark_path and Path(dark_path).exists():
                st.image(Image.open(dark_path), caption='Dark Line Regions', width='stretch')
            else:
                st.info('No Dark Line Regions image found.')
        return

    uploaded_files = st.file_uploader(
        'Upload images or CSV files',
        accept_multiple_files=True,
        type=['png', 'jpg', 'jpeg', 'gif', 'tif', 'tiff', 'csv'],
        key='library_uploader'
    )

    if uploaded_files:
        current_sigs = [f"{f.name}::{getattr(f, 'size', None)}" for f in uploaded_files]
        if current_sigs != st.session_state['library_cached_signatures']:
            st.session_state['library_cached_uploads'] = [
                {
                    'name': uploaded.name,
                    'type': uploaded.type,
                    'size': getattr(uploaded, 'size', None),
                    'bytes': uploaded.getvalue(),
                }
                for uploaded in uploaded_files
            ]
            st.session_state['library_cached_signatures'] = current_sigs

    source_files = list(uploaded_files) if uploaded_files else []
    if (not source_files) and st.session_state['library_cached_uploads']:
        for item in st.session_state['library_cached_uploads']:
            bio = io.BytesIO(item['bytes'])
            bio.name = item['name']
            bio.type = item['type']
            bio.size = item['size']
            source_files.append(bio)

    if not source_files:
        st.info('No files uploaded yet. Use the uploader to add images or CSVs.')
        return

    images = []
    tables = []

    for uploaded in source_files:
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
                img = Image.open(uploaded).convert('RGB')
                file_size = getattr(uploaded, 'size', None)
                file_sig = f"{name}::{file_size}"
                if file_sig not in st.session_state['library_file_ids']:
                    st.session_state['library_id_counter'] += 1
                    st.session_state['library_file_ids'][file_sig] = f"{st.session_state['library_id_counter']:05d}"
                img_id = st.session_state['library_file_ids'][file_sig]

                # Original grayscale (no enhancement)
                gray = process_image_to_grayscale(img.copy())
                # Enhanced detection image
                enhanced = build_enhanced_detection_image(gray)
                # Binary image for bar detection
                black_white = build_black_white_image(enhanced)

                images.append((img_id, name, img.copy(),
                              gray, enhanced, black_white))
            except UnidentifiedImageError:
                st.warning(f'File {name} is not a recognized image.')
            except Exception as e:
                st.warning(f'Failed to open {name}: {e}')

    if images:
        st.subheader('Images')
        for img_id, name, img, gray, enhanced, black_white in images:
            cropped_overlay = None
            cols = st.columns([1, 2, 4])
            with cols[0]:
                st.markdown(f"**ID**\n\n`{img_id}`")
                st.link_button('Detail', f'?detail_id={img_id}', use_container_width=True)

            # Hard crop: fixed 0.3 x 0.3 centered region
            w_gray, h_gray = gray.size
            crop_w = max(1, int(w_gray * 0.25))
            crop_h = max(1, int(h_gray * 0.25))
            x0 = (w_gray - crop_w) // 2
            y0 = (h_gray - crop_h) // 2
            x1 = x0 + crop_w
            y1 = y0 + crop_h
            cropped = gray.crop((x0, y0, x1, y1))

            # Full-height vertical dark-line detection (column-wise)
            import numpy as np
            cropped_np = np.array(cropped)
            if cropped_np.ndim == 3:
                cropped_np = np.mean(cropped_np, axis=2)
            col_profile = np.mean(cropped_np, axis=0)
            col_thr = min(float(np.mean(col_profile) * 0.90),
                          float(np.mean(col_profile) - 0.3 * np.std(col_profile)))
            dark_cols = col_profile < col_thr

            v_regions = []
            run_start = None
            for i, is_dark in enumerate(dark_cols):
                if is_dark and run_start is None:
                    run_start = i
                elif (not is_dark) and run_start is not None:
                    run_end = i
                    if run_end - run_start >= 2:
                        v_regions.append((run_start, run_end))
                    run_start = None
            if run_start is not None:
                run_end = len(dark_cols)
                if run_end - run_start >= 2:
                    v_regions.append((run_start, run_end))

            from PIL import ImageDraw
            vertical_overlay = cropped.convert('RGB')
            draw_v = ImageDraw.Draw(vertical_overlay)
            w_crop, h_crop = vertical_overlay.size
            for xs, xe in v_regions:
                x0 = max(0, int(xs))
                x1 = min(w_crop - 1, int(xe))
                draw_v.rectangle((x0, 0, x1, h_crop - 1), outline=(0, 255, 255), width=2)

            # Re-crop by two full-height vertical dark lines: keep only middle area
            cropped_between = None
            if len(v_regions) >= 2:
                left_region = v_regions[0]
                right_region = v_regions[-1]
                pad_x = 5
                x_left = max(0, int(left_region[1]) - pad_x)
                x_right = min(w_crop, int(right_region[0]) + pad_x)
                if x_right - x_left >= 2:
                    cropped_between = cropped.crop((x_left, 0, x_right, h_crop))

            # post_cols = st.columns(2)
            # with post_cols[0]:
            #     # st.image(
            #     #     vertical_overlay,
            #     #     caption=f"Full-Height Vertical Dark Lines — {name}",
            #     #     width='stretch'
            #     # )
            #     st.caption(f"Vertical full-height dark-line regions (x_start, x_end): {v_regions}")
            # with post_cols[1]:
            #     if cropped_between is not None:
            #         # st.image(
            #         #     cropped_between,
            #         #     caption=f"Cropped Between Two Full-Height Dark Lines — {name}",
            #         #     width='stretch'
            #         # )
            #         st.caption(between_caption)

            analysis_img = cropped_between if cropped_between is not None else cropped

            # Dark-line detection on cropped image
            profile = build_intensity_profile(analysis_img)
            regions = detect_line_regions(profile, threshold_scale=0.85, min_region_height=2)
            darkness_results = measure_line_darkness(analysis_img, regions)

            if regions:
                from PIL import ImageDraw
                cropped_overlay = analysis_img.convert('RGB')
                draw = ImageDraw.Draw(cropped_overlay)
                w_crop, h_crop = cropped_overlay.size
                for row in darkness_results:
                    y0_r = max(0, int(row['start']))
                    y1_r = min(h_crop - 1, int(row['end']))
                    x0_r = max(0, int(row.get('x_start', 0)))
                    x1_r = min(w_crop - 1, int(row.get('x_end', w_crop)))
                    draw.rectangle((x0_r, y0_r, x1_r, y1_r), outline=(255, 0, 0), width=2)

                # Crop again around center-most detected dark-line regions with padding
                pad = 20
                n_regions = len(darkness_results)
                take_n = 3 if n_regions == 3 else min(2, n_regions)
                cy = h_crop / 2.0
                sorted_by_center = sorted(
                    darkness_results,
                    key=lambda r: abs(((r['start'] + r['end']) / 2.0) - cy)
                )
                selected = sorted_by_center[:take_n]

                x_min = min(int(r.get('x_start', 0)) for r in selected)
                x_max = max(int(r.get('x_end', w_crop)) for r in selected)
                y_min = min(int(r['start']) for r in selected)
                y_max = max(int(r['end']) for r in selected)

                cx_sel = (x_min + x_max) / 2.0
                cy_sel = (y_min + y_max) / 2.0
                half_w = max(cx_sel - x_min, x_max - cx_sel) + pad
                half_h = max(cy_sel - y_min, y_max - cy_sel) + pad

                x0_c = max(0, int(round(cx_sel - half_w)))
                x1_c = min(w_crop, int(round(cx_sel + half_w)))
                y0_c = max(0, int(round(cy_sel - half_h)))
                y1_c = min(h_crop, int(round(cy_sel + half_h)))

                refined_crop = analysis_img.crop((x0_c, y0_c, x1_c, y1_c))
                recrop_profile = build_intensity_profile(refined_crop)
                recrop_regions = detect_line_regions(
                    recrop_profile, threshold_scale=0.85, min_region_height=2
                )
                recrop_results = measure_line_darkness(refined_crop, recrop_regions)

                recrop_overlay = refined_crop.convert('RGB')
                draw_recrop = ImageDraw.Draw(recrop_overlay)
                w_ref, h_ref = recrop_overlay.size
                label_map = {1: 'c', 2: 't'}
                for idx, row in enumerate(recrop_results, start=1):
                    y0_rr = max(0, int(row['start']))
                    y1_rr = min(h_ref - 1, int(row['end']))
                    x0_rr = 0
                    x1_rr = w_ref - 1
                    draw_recrop.rectangle((x0_rr, y0_rr, x1_rr, y1_rr), outline=(255, 0, 0), width=2)
                    draw_recrop.text(
                        (x0_rr + 4, max(0, y0_rr - 14)),
                        label_map.get(idx, f"line_{idx}"),
                        fill=(255, 0, 0)
                    )

                with cols[1]:
                    st.image(
                        recrop_overlay,
                        caption=f"Dark Line Regions Re-Crop — {name}",
                        width='stretch'
                    )
                with cols[2]:
                    name_map = {1: 'c', 2: 't'}
                    table_rows = [{
                        'name': name_map.get(i, f"line_{i}"),
                        'gray_mean': float(r.get('line_mean', 0.0))
                    } for i, r in enumerate(recrop_results, start=1)]

                    if len(recrop_results) >= 2:
                        sorted_rows = sorted(
                            recrop_results,
                            key=lambda r: int(r.get('start', 0))
                        )
                        upper_end = int(sorted_rows[0].get('end', 0))
                        lower_start = int(sorted_rows[1].get('start', 0))
                        bg_y0 = max(0, upper_end + 1)
                        bg_y1 = min(h_ref, lower_start)
                        if bg_y1 > bg_y0:
                            refined_np = np.array(refined_crop)
                            if refined_np.ndim == 3:
                                refined_np = np.mean(refined_np, axis=2)
                            bg_region = refined_np[bg_y0:bg_y1, :]
                            if bg_region.size > 0:
                                bg_gray_mean = float(np.mean(bg_region))
                                table_rows.append({
                                    'name': 'background',
                                    'gray_mean': bg_gray_mean
                                })

                    c_val = next((r['gray_mean'] for r in table_rows if r.get('name') == 'c'), None)
                    t_val = next((r['gray_mean'] for r in table_rows if r.get('name') == 't'), None)
                    bg_val = next((r['gray_mean'] for r in table_rows if r.get('name') == 'background'), None)
                    if c_val is not None and t_val is not None and bg_val is not None:
                        denom = c_val - bg_val
                        if abs(denom) > 1e-12:
                            ratio_val = (t_val - bg_val) / denom
                            table_rows.append({
                                'name': 'ratio',
                                'gray_mean': float(ratio_val)
                            })

                    mean_only_df = pd.DataFrame(table_rows)[['name', 'gray_mean']]
                    mean_only_df['standard_id_range'] = mean_only_df['gray_mean'].apply(
                        get_standard_id_range
                    )
                    st.dataframe(mean_only_df[['name', 'gray_mean']], width='stretch')
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
                dark_filename = f'{img_id}_dark_regions.png'
                original_path = uploads_dir / original_filename
                gray_path = uploads_dir / gray_filename
                cropped_path = uploads_dir / cropped_filename
                dark_path = uploads_dir / dark_filename
                img.save(original_path)
                gray.save(gray_path)
                cropped.save(cropped_path)
                if cropped_overlay is not None:
                    cropped_overlay.save(dark_path)

                now = datetime.now()
                entry = {
                    'id': img_id,
                    'original_name': name,
                    'original_path': str(original_path),
                    'gray_path': str(gray_path),
                    'cropped_name': cropped_filename,
                    'cropped_path': str(cropped_path),
                    'dark_regions_path': str(dark_path) if cropped_overlay is not None else '',
                    'date': now.strftime('%Y-%m-%d'),
                    'time': now.strftime('%H:%M:%S'),
                    'timestamp': now.isoformat(timespec='seconds')
                }
                meta = [m for m in meta if str(m.get('id')) != str(img_id)]
                meta.append(entry)
                with meta_path.open('w', encoding='utf-8') as f:
                    json.dump(meta, f, ensure_ascii=False, indent=2)
            except Exception:
                st.warning('Failed to save cropped image or write meta.json')

    if tables:
        st.subheader('Datasets')
        for name, df in tables:
            st.write(f'Preview — {name}')
            st.dataframe(df.head(50))
