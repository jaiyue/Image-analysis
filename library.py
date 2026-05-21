# library.py — Library page for Image-analysis standalone app
import streamlit as st
import pandas as pd
from image_processing import process_image_to_grayscale, detect_and_crop_red_bars
from pathlib import Path
import io
import json
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

    uploaded_files = st.file_uploader('Upload images or CSV files', accept_multiple_files=True,
                                      type=['png', 'jpg', 'jpeg', 'gif', 'tif', 'tiff', 'csv'])

    # ensure we have a persistent incremental counter for image IDs
    if 'library_id_counter' not in st.session_state:
        st.session_state['library_id_counter'] = 0

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
                img = Image.open(uploaded).convert('RGB')
                # perform red-bar detection and crop before grayscale
                try:
                    cropped = detect_and_crop_red_bars(img, padding_cm=1.0)
                except Exception:
                    cropped = img

                # generate an incremental 5-digit ID
                st.session_state['library_id_counter'] += 1
                img_id_int = st.session_state['library_id_counter']
                img_id = f"{img_id_int:05d}"
                # generate grayscale version (use cropped image)
                gray = process_image_to_grayscale(
                    cropped, resize_to=(1024, 1024))
                images.append((img_id, name, img.copy(), gray))
            except UnidentifiedImageError:
                st.warning(f'File {name} is not a recognized image.')
            except Exception as e:
                st.warning(f'Failed to open {name}: {e}')

    if images:
        st.subheader('Images')
        uploads_dir = Path(__file__).parent / 'uploads'
        uploads_dir.mkdir(exist_ok=True)
        meta_path = uploads_dir / 'meta.json'
        try:
            if meta_path.exists():
                with meta_path.open('r', encoding='utf-8') as f:
                    meta = json.load(f)
            else:
                meta = []
        except Exception:
            meta = []

        for img_id, name, img, gray in images:
            cols = st.columns([1, 3, 3])
            with cols[0]:
                st.markdown(f"**ID**\n\n`{img_id}`")
            with cols[1]:
                st.image(img, caption=f"Original — {name}", width='stretch')
            with cols[2]:
                st.image(gray, caption=f"Grayscale — {name}", width='stretch')

            # Persist files and metadata
            try:
                ext = Path(name).suffix.lower() or '.png'
                orig_filename = f"{img_id}_orig{ext}"
                gray_filename = f"{img_id}_gray.png"
                orig_path = uploads_dir / orig_filename
                gray_path = uploads_dir / gray_filename

                # save original
                try:
                    img.save(orig_path)
                except Exception:
                    buf = io.BytesIO()
                    img.save(buf, format='PNG')
                    buf.seek(0)
                    with orig_path.open('wb') as f:
                        f.write(buf.read())

                # save grayscale
                try:
                    gray.save(gray_path)
                except Exception:
                    buf = io.BytesIO()
                    gray.save(buf, format='PNG')
                    buf.seek(0)
                    with gray_path.open('wb') as f:
                        f.write(buf.read())

                entry = {
                    'id': img_id,
                    'original_name': name,
                    'original_path': str(orig_path.name),
                    'gray_path': str(gray_path.name),
                    'timestamp': datetime.utcnow().isoformat() + 'Z'
                }
                meta.append(entry)
                try:
                    with meta_path.open('w', encoding='utf-8') as f:
                        json.dump(meta, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass
            except Exception:
                st.warning('Failed to save files to disk')

            # Download buttons removed per user request (files are still saved to ./uploads/)

    if tables:
        st.subheader('Datasets')
        for name, df in tables:
            st.write(f'Preview — {name}')
            st.dataframe(df.head(50))
