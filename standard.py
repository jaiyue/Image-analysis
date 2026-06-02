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

    # Column grayscale profile
    col_profile = np.mean(arr, axis=0)

    # Dark threshold
    thr = min(
        float(np.mean(col_profile) * 0.90),
        float(np.mean(col_profile) - 0.3 * np.std(col_profile))
    )

    dark_cols = col_profile < thr

    regions = []

    run_start = None

    for i, is_dark in enumerate(dark_cols):

        if is_dark and run_start is None:

            run_start = i

        elif (not is_dark) and run_start is not None:

            run_end = i

            if run_end - run_start >= 2:

                regions.append(
                    (run_start, run_end)
                )

            run_start = None

    if run_start is not None:

        run_end = len(dark_cols)

        if run_end - run_start >= 2:

            regions.append(
                (run_start, run_end)
            )

    return regions


def _build_ten_boxes_by_rightmost_rule(
    regions,
    image_width
):
    """
    Always build EXACTLY 10 boxes.

    Logic:
    - use detected spacing
    - use detected width
    - anchor from rightmost detection
    - generate fixed 10 positions
    """

    if not regions:
        return []

    # Sort left -> right
    regions_sorted = sorted(
        regions,
        key=lambda r: r[0]
    )

    # Centers
    centers = [
        (s + e) / 2.0
        for s, e in regions_sorted
    ]

    # Widths
    widths = [
        (e - s)
        for s, e in regions_sorted
    ]

    # Stable width
    box_w = int(
        max(
            2,
            np.median(widths)
        )
    )

    # Use detected spacing
    gaps = []

    for i in range(len(centers) - 1):

        gap = (
            centers[i + 1] -
            centers[i]
        )

        if gap > 2:
            gaps.append(gap)

    # Fallback spacing
    if len(gaps) == 0:

        spacing = box_w * 1.5

    else:

        spacing = float(
            np.median(gaps)
        )

    # RIGHTMOST anchor
    rightmost_center = centers[-1]

    # Build EXACTLY 10 boxes
    final_centers = []

    for i in range(10):

        c = (
            rightmost_center -
            spacing * (9 - i)
        )

        final_centers.append(c)

    boxes = []

    half_w = box_w / 2.0

    for c in final_centers:

        x0 = int(round(c - half_w))
        x1 = int(round(c + half_w))

        # Boundary protection
        x0 = max(0, x0)
        x1 = min(image_width, x1)

        if x1 - x0 >= 2:

            boxes.append(
                (x0, x1)
            )

    return boxes


def _estimate_vertical_span(
    gray_pil,
    x0,
    x1
):

    arr = np.array(gray_pil)

    if arr.ndim == 3:
        arr = np.mean(arr, axis=2)

    x0 = max(0, int(x0))
    x1 = min(arr.shape[1], int(x1))

    if x1 <= x0:
        return 0, arr.shape[0] - 1

    band = arr[:, x0:x1]

    row_profile = np.mean(
        band,
        axis=1
    )

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

                runs.append(
                    (run_start, run_end)
                )

            run_start = None

    if run_start is not None:

        run_end = len(dark_rows)

        if run_end - run_start >= 2:

            runs.append(
                (run_start, run_end)
            )

    if not runs:
        return 0, arr.shape[0] - 1

    y0, y1 = max(
        runs,
        key=lambda r: r[1] - r[0]
    )

    return int(y0), int(y1)


def estimate_missing_values(standard_rows):
    """
    Exponential + noise model

    Ideal model:

    y = a * exp(-b*x) + epsilon

    where:
    - exponential = global trend
    - epsilon = local residual noise
    """

    stable = [
        row for row in standard_rows
        if row["id"] >= 4
        and row["gray_avg"] is not None
    ]

    if len(stable) < 2:
        return standard_rows

    # x and y
    x = np.array([
        row["id"]
        for row in stable
    ])

    y = np.array([
        row["gray_avg"]
        for row in stable
    ])

    # Safety
    y = np.clip(y, 1e-6, None)

    # ===== EXPONENTIAL FIT =====

    log_y = np.log(y)

    coeffs = np.polyfit(
        x,
        log_y,
        1
    )

    b = coeffs[0]
    ln_a = coeffs[1]

    a = np.exp(ln_a)

    # ===== RESIDUAL NOISE =====

    fitted_y = a * np.exp(b * x)

    residuals = y - fitted_y

    # Estimate epsilon
    epsilon_std = np.std(residuals)

    corrected_rows = []

    for row in standard_rows:

        idx = row["id"]

        # Pure exponential prediction
        predicted = (
            a *
            np.exp(b * idx)
        )

        # Add epsilon noise
        epsilon = 0.0

        if idx >= 4:

            # Stable area:
            # keep real residual behavior
            nearest_idx = min(
                len(residuals) - 1,
                idx - 4
            )

            epsilon = residuals[
                nearest_idx
            ]

        else:

            # Weak unstable area:
            # use reduced synthetic noise
            epsilon = (
                np.random.normal(
                    0,
                    epsilon_std * 0.35
                )
            )

        predicted_with_noise = (
            predicted + epsilon
        )

        predicted_with_noise = round(
            float(predicted_with_noise),
            2
        )

        # ===== CORRECTION =====

        if idx >= 4:

            corrected = row["gray_avg"]

        else:

            real = row["gray_avg"]

            if real is None:

                corrected = predicted_with_noise

            else:

                # Blend:
                # 70% model
                # 30% measured
                corrected = (
                    real * 0.3 +
                    predicted_with_noise * 0.7
                )

        corrected = round(
            float(corrected),
            2
        )

        row["predicted_gray_avg"] = predicted_with_noise

        row["corrected_gray_avg"] = corrected

        # Optional debug values
        row["exp_component"] = round(
            float(predicted),
            2
        )

        row["epsilon"] = round(
            float(epsilon),
            2
        )

        corrected_rows.append(row)

    return corrected_rows


def render_standard_page():

    st.title('Standard')

    st.write(
        'Use `image.png` as the standard rule image.'
    )

    image_path = (
        Path(__file__).parent /
        'image.png'
    )

    if not image_path.exists():

        st.error(
            f'Standard image not found: {image_path}'
        )

        return

    try:

        original = Image.open(
            image_path
        ).convert('RGB')

    except Exception as exc:

        st.error(
            f'Failed to open standard image: {exc}'
        )

        return

    # Grayscale
    gray = process_image_to_grayscale(
        original
    )

    # Detection enhancement
    enhanced_for_detection = ImageEnhance.Contrast(
        gray
    ).enhance(1.8)

    # Detect dark regions
    regions = _detect_full_height_vertical_dark_regions(
        enhanced_for_detection
    )

    # Build boxes
    constrained_boxes = _build_ten_boxes_by_rightmost_rule(
        regions,
        gray.size[0]
    )

    # Overlay
    vertical_overlay = gray.convert('RGB')

    draw = ImageDraw.Draw(
        vertical_overlay
    )

    w_img, h_img = vertical_overlay.size

    template_y0, template_y1 = 0, h_img - 1

    if constrained_boxes:

        tx0, tx1 = constrained_boxes[0]

        template_y0, template_y1 = _estimate_vertical_span(
            enhanced_for_detection,
            tx0,
            tx1
        )

    draw_boxes = []

    for xs, xe in constrained_boxes:

        x0 = max(0, int(xs))
        x1 = min(w_img - 1, int(xe))

        if x1 <= x0:
            continue

        half_start = int(
            round(
                template_y0 +
                (template_y1 - template_y0) * 0.5
            )
        )

        draw.rectangle(
            (
                x0,
                half_start,
                x1,
                template_y1
            ),
            outline=(0, 255, 255),
            width=2
        )

        draw_boxes.append((x0, x1))

    # Numeric extraction
    gray_arr = np.array(gray)

    if gray_arr.ndim == 3:
        gray_arr = np.mean(gray_arr, axis=2)

    boxes_left_to_right = sorted(
        draw_boxes,
        key=lambda b: b[0]
    )

    standard_rows = []

    for idx, (x0, x1) in enumerate(
        boxes_left_to_right,
        start=1
    ):

        y0 = max(
            0,
            int(
                round(
                    template_y0 +
                    (template_y1 - template_y0) * 0.5
                )
            )
        )

        y1 = min(
            h_img - 1,
            int(template_y1)
        )

        if x1 <= x0 or y1 <= y0:

            gray_avg = None
            gray_mean = None
            gray_max = None

        else:

            region = gray_arr[
                y0:y1 + 1,
                x0:x1 + 1
            ]

            gray_avg = float(np.mean(region))
            gray_mean = float(np.median(region))
            gray_max = float(
                np.percentile(region, 75)
            )

            gray_avg = round(gray_avg, 2)
            gray_mean = round(gray_mean, 2)
            gray_max = round(gray_max, 2)

        standard_rows.append({

            'id': idx,

            'x_start': x0,
            'x_end': x1,

            'gray_avg': gray_avg,


        })

    # Exponential correction
    standard_rows = estimate_missing_values(
        standard_rows
    )

    # Save JSON


    standard_path = (
        Path(__file__).parent /
        'standard_reference.json'
    )

    payload = {

        'source_image': str(image_path),

        'saved_at': datetime.now().isoformat(
            timespec='seconds'
        ),

        'box_count': len(standard_rows),

        'values': standard_rows,
    }

    try:

        with standard_path.open(
            'w',
            encoding='utf-8'
        ) as f:

            json.dump(
                payload,
                f,
                ensure_ascii=False,
                indent=2
            )

    except Exception as exc:

        st.warning(
            f'Failed to save standard reference: {exc}'
        )

    # Display
    cols = st.columns(4)

    with cols[0]:

        st.image(
            original,
            caption='Original',
            width='stretch'
        )

    with cols[1]:

        st.image(
            gray,
            caption='Grayscale',
            width='stretch'
        )

    with cols[2]:

        st.image(
            enhanced_for_detection,
            caption='Enhanced',
            width='stretch'
        )

    with cols[3]:

        st.image(
            vertical_overlay,
            caption='Detected Boxes',
            width='stretch'
        )

    st.caption(
        f'Raw detected regions: {regions}'
    )

    st.caption(
        f'Constrained boxes: {constrained_boxes}'
    )

    st.dataframe(
        standard_rows,
        width='stretch'
    )

    st.caption(
        f'Saved to: {standard_path}'
    )
