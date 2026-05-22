from pathlib import Path

import numpy as np
import streamlit as st
from PIL import Image, ImageDraw, ImageEnhance
import json
from datetime import datetime

from image_processing import process_image_to_grayscale


def _detect_full_height_vertical_dark_regions(gray_pil):
    arr = np.array(gray_pil)
    if arr.ndim == 3:
        arr = np.mean(arr, axis=2)

    col_profile = np.mean(arr, axis=0)
    thr = min(float(np.mean(col_profile) * 0.90),
              float(np.mean(col_profile) - 0.3 * np.std(col_profile)))
    dark_cols = col_profile < thr

    regions = []
    run_start = None
    for i, is_dark in enumerate(dark_cols):
        if is_dark and run_start is None:
            run_start = i
        elif (not is_dark) and run_start is not None:
            run_end = i
            if run_end - run_start >= 2:
                regions.append((run_start, run_end))
            run_start = None

    if run_start is not None:
        run_end = len(dark_cols)
        if run_end - run_start >= 2:
            regions.append((run_start, run_end))

    return regions


def _build_ten_boxes_by_rightmost_rule(regions, image_width):
    """
    Build exactly 10 full-height boxes:
    - width uses the rightmost detected region width
    - spacing uses nearby detected region center distances
    - anchor starts from rightmost detected region center
    """
    if not regions:
        return []

    regions_sorted = sorted(regions, key=lambda r: r[0])
    centers = [((s + e) / 2.0) for s, e in regions_sorted]
    right_s, right_e = regions_sorted[-1]
    box_w = max(2.0, float(right_e - right_s))
    right_center = centers[-1]

    # Standard spacing: maximum gap among the rightmost three detected boxes.
    if len(centers) >= 3:
        gap1 = float(centers[-1] - centers[-2])
        gap2 = float(centers[-2] - centers[-3])
        spacing = max(2.0, max(gap1, gap2))
    elif len(centers) >= 2:
        spacing = max(2.0, float(centers[-1] - centers[-2]))
    else:
        spacing = box_w * 1.5

    boxes = []
    half_w = box_w / 2.0
    for i in range(10):
        c = right_center - i * spacing
        x0 = int(round(c - half_w))
        x1 = x0 + int(round(box_w))

        # Keep constant width: shift into image bounds instead of clipping width.
        if x0 < 0:
            shift = -x0
            x0 += shift
            x1 += shift
        if x1 > image_width:
            shift = x1 - image_width
            x0 -= shift
            x1 -= shift

        x0 = max(0, x0)
        x1 = min(image_width, x1)
        if x1 - x0 >= 2:
            boxes.append((x0, x1))

    return boxes


def _estimate_vertical_span(gray_pil, x0, x1):
    """Estimate dark-line y span within a given x-range."""
    arr = np.array(gray_pil)
    if arr.ndim == 3:
        arr = np.mean(arr, axis=2)

    x0 = max(0, int(x0))
    x1 = min(arr.shape[1], int(x1))
    if x1 <= x0:
        return 0, arr.shape[0] - 1

    band = arr[:, x0:x1]
    row_profile = np.mean(band, axis=1)
    thr = min(
        float(np.mean(row_profile) * 0.92),
        float(np.mean(row_profile) - 0.25 * np.std(row_profile)),
    )
    dark_rows = row_profile < thr

    runs = []
    run_start = None
    for i, is_dark in enumerate(dark_rows):
        if is_dark and run_start is None:
            run_start = i
        elif (not is_dark) and run_start is not None:
            run_end = i
            if run_end - run_start >= 2:
                runs.append((run_start, run_end))
            run_start = None

    if run_start is not None:
        run_end = len(dark_rows)
        if run_end - run_start >= 2:
            runs.append((run_start, run_end))

    if not runs:
        return 0, arr.shape[0] - 1

    y0, y1 = max(runs, key=lambda r: r[1] - r[0])
    return int(y0), int(y1)


def render_standard_page():
    st.title('Standard')
    st.write('Use `image.png` as the standard rule image.')

    image_path = Path(__file__).parent / 'image.png'
    if not image_path.exists():
        st.error(f'Standard image not found: {image_path}')
        return

    try:
        original = Image.open(image_path).convert('RGB')
    except Exception as exc:
        st.error(f'Failed to open standard image: {exc}')
        return

    gray = process_image_to_grayscale(original)
    enhanced_for_detection = ImageEnhance.Contrast(gray).enhance(1.8)
    regions = _detect_full_height_vertical_dark_regions(enhanced_for_detection)
    constrained_boxes = _build_ten_boxes_by_rightmost_rule(
        regions, gray.size[0])

    vertical_overlay = gray.convert('RGB')
    draw = ImageDraw.Draw(vertical_overlay)
    w_img, h_img = vertical_overlay.size
    # Use rightmost box as template for size and vertical position.
    template_y0, template_y1 = 0, h_img - 1
    if constrained_boxes:
        tx0, tx1 = constrained_boxes[0]
        template_y0, template_y1 = _estimate_vertical_span(
            enhanced_for_detection, tx0, tx1
        )
        template_y0 = max(0, min(h_img - 1, template_y0))
        template_y1 = max(0, min(h_img - 1, template_y1))
        if template_y1 <= template_y0:
            template_y0, template_y1 = 0, h_img - 1

    draw_boxes = []
    for xs, xe in constrained_boxes:
        x0_raw = max(0, int(xs))
        x1_raw = min(w_img - 1, int(xe) - 1)
        raw_w = x1_raw - x0_raw + 1
        if raw_w < 2:
            continue
        inset = min(1, max(0, (raw_w - 2) // 2))
        x0 = x0_raw + inset
        x1 = x1_raw - inset
        if x1 <= x0:
            continue
        half_start = int(
            round(template_y0 + (template_y1 - template_y0) * 0.5))
        draw.rectangle((x0, half_start, x1, template_y1),
                       outline=(0, 255, 255), width=2)
        draw_boxes.append((x0, x1))

    # Extract grayscale numeric values from each detection box.
    gray_arr = np.array(gray)
    if gray_arr.ndim == 3:
        gray_arr = np.mean(gray_arr, axis=2)

    boxes_left_to_right = sorted(draw_boxes, key=lambda b: b[0])
    standard_rows = []
    for idx, (x0, x1) in enumerate(boxes_left_to_right, start=1):
        y0 = max(0, int(round(template_y0 + (template_y1 - template_y0) * 0.5)))
        y1 = min(h_img - 1, int(template_y1))
        if x1 <= x0 or y1 <= y0:
            gray_avg = None
            gray_mean = None
            gray_max = None
        else:
            region = gray_arr[y0:y1 + 1, x0:x1 + 1]
            gray_avg = float(np.mean(region)) if region.size > 0 else None
            gray_mean = float(np.median(region)) if region.size > 0 else None
            # Use a robust bright-end metric instead of single-pixel max.
            gray_max = float(np.percentile(region, 75)
                             ) if region.size > 0 else None
            gray_avg = round(gray_avg, 2) if gray_avg is not None else None
            gray_mean = round(gray_mean, 2) if gray_mean is not None else None
            gray_max = round(gray_max, 2) if gray_max is not None else None

        standard_rows.append({
            'id': idx,  # leftmost=1 ... rightmost=10
            'x_start': x0,
            'x_end': x1,
            'gray_avg': gray_avg,
            'gray_max': gray_max,
            'gray_mean': gray_mean,
        })

    # Persist standard reference values on server for later comparison.
    uploads_dir = Path(__file__).parent / 'uploads'
    uploads_dir.mkdir(exist_ok=True)
    standard_path = uploads_dir / 'standard_reference.json'
    payload = {
        'source_image': str(image_path),
        'saved_at': datetime.now().isoformat(timespec='seconds'),
        'box_count': len(standard_rows),
        'values': standard_rows,
    }
    try:
        with standard_path.open('w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        st.warning(f'Failed to save standard reference: {exc}')

    cols = st.columns(4)
    with cols[0]:
        st.image(original, caption='Original (image.png)',
                 use_container_width=True)
    with cols[1]:
        st.image(gray, caption='Grayscale', use_container_width=True)
    with cols[2]:
        st.image(enhanced_for_detection,
                 caption='Contrast Enhanced (for detection)', use_container_width=True)
    with cols[3]:
        st.image(vertical_overlay, caption='Vertical Dark Lines',
                 use_container_width=True)

    st.caption(f'Raw detected regions: {regions}')
    st.caption(f'Constrained 10 boxes: {constrained_boxes}')
    st.write('Standard grayscale values (leftmost id=1, rightmost id=10):')
    st.dataframe(standard_rows, use_container_width=True)
    st.caption(f'Saved to: {standard_path}')
