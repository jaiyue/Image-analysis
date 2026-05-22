import json
from pathlib import Path

import streamlit as st
from PIL import Image


def _load_meta():
    meta_path = Path(__file__).parent / 'uploads' / 'meta.json'
    if not meta_path.exists():
        return []
    try:
        with meta_path.open('r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except Exception:
        return []
    return []


def render_insight_detail_page(detail_id):
    st.subheader(f'Insight Detail - ID {detail_id}')
    if st.button('Back to Insights', key='back_to_insights'):
        st.query_params.clear()
        st.rerun()

    meta = _load_meta()
    detail_entry = next((m for m in reversed(meta) if str(m.get('id')) == str(detail_id)), None)
    if detail_entry is None:
        st.warning('Detail record not found in meta.json.')
        return

    st.write(f"Original file: {detail_entry.get('original_name', '-')}")
    st.write(
        f"Date/Time: {detail_entry.get('date', '-')}"
        f" {detail_entry.get('time', '-')}"
    )

    detail = detail_entry.get('detail', {})
    images = detail.get('images', {})
    metrics = detail.get('metrics', {})
    if not metrics:
        metrics = {
            'c': detail_entry.get('c'),
            't': detail_entry.get('t'),
            'ratio': detail_entry.get('ratio'),
        }
    st.table([{
        'id': detail_entry.get('id'),
        'c': metrics.get('c'),
        't': metrics.get('t'),
        'ratio': metrics.get('ratio'),
    }])

    show_paths = [
        ('Original', images.get('original_path', detail_entry.get('original_path', ''))),
        ('Grayscale', images.get('gray_path', detail_entry.get('gray_path', ''))),
        ('Cropped', images.get('cropped_path', detail_entry.get('cropped_path', ''))),
        ('Re-Crop Overlay', images.get('recrop_path', '')),
    ]
    cols = st.columns(3)
    col_idx = 0
    for caption, img_path in show_paths:
        if not img_path:
            continue
        p = Path(img_path)
        if not p.exists():
            continue
        with cols[col_idx % 3]:
            st.image(Image.open(p), caption=caption, width='stretch')
        col_idx += 1
