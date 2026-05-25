# library.py — Library page with center‑based closest bars cropping

import streamlit as st
import pandas as pd
from image_processing import (
    process_image_to_grayscale,
    build_enhanced_detection_image,
    build_black_white_image,
    analyze_library_image,
)
from pathlib import Path
from datetime import datetime
from uploads_db import init_uploads_db, upsert_upload_record

try:
    from PIL import Image, ImageOps, UnidentifiedImageError
except Exception:
    Image = None
    UnidentifiedImageError = Exception


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


def render_library_page():
    st.title('Library')
    st.write(
        'Upload images or CSV datasets. Images show as thumbnails; CSVs show a preview.')

    uploads_dir = Path(__file__).parent / 'uploads'
    uploads_dir.mkdir(exist_ok=True)
    init_uploads_db()

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
        for img_id, name, img, gray, enhanced, black_white, image_dt in images:
            cropped_overlay = None
            recrop_overlay = None
            c_val = None
            t_val = None
            ratio_val = None
            cols = st.columns([1, 2, 4])
            with cols[0]:
                st.markdown(f"**ID**\n\n`{img_id}`")

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
            ratio_val = analysis["ratio"]
            vertical_crop_reason = analysis["vertical_crop_reason"]

            if recrop_overlay is not None:
                with cols[1]:
                    st.image(
                        recrop_overlay,
                        caption=f"Dark Line Regions Re-Crop — {name}",
                        width='stretch'
                    )
                with cols[2]:
                    mean_only_df = pd.DataFrame(table_rows)[['name', 'gray_mean']]
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
                        'ratio': round(float(ratio_val), 6) if ratio_val is not None else None,
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
                    'ratio': round(float(ratio_val), 6) if ratio_val is not None else None,
                    'detail': detail_payload,
                    'date': now.strftime('%Y-%m-%d'),
                    'time': now.strftime('%H:%M:%S'),
                    'timestamp': now.isoformat(timespec='seconds')
                }
                upsert_upload_record(entry)
            except Exception:
                st.warning('Failed to save cropped image or write to uploads.db')

    if tables:
        st.subheader('Datasets')
        for name, df in tables:
            st.write(f'Preview — {name}')
            st.dataframe(df.head(50))
