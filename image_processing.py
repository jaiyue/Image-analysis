# image_processing.py

from PIL import Image, ImageOps
import streamlit as st
import numpy as np

try:
    import cv2
except Exception:
    cv2 = None


def process_image_to_grayscale(pil_image, resize_to=None):
    """Convert PIL image to grayscale."""
    if pil_image.mode == "RGBA":
        pil_image = pil_image.convert("RGB")
    img = pil_image.copy()
    if resize_to:
        img = img.resize(resize_to)
    return ImageOps.grayscale(img)


def build_enhanced_detection_image(gray_pil):
    """Build enhanced grayscale image for detection (denoise, CLAHE, etc.)."""
    gray = np.array(gray_pil.copy())
    if cv2 is None:
        return gray_pil

    denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
    blurred = cv2.GaussianBlur(denoised, (5, 5), 0)
    stretched = cv2.normalize(blurred, None, 0, 255, cv2.NORM_MINMAX)
    clahe = cv2.createCLAHE(clipLimit=4.5, tileGridSize=(8, 8))
    enhanced = clahe.apply(stretched)
    enhanced = cv2.convertScaleAbs(enhanced, alpha=1.8, beta=0)
    return Image.fromarray(enhanced)


def build_black_white_image(gray_pil):
    """Build binary image from enhanced grayscale."""
    gray = np.array(gray_pil.copy())
    if cv2 is None:
        bw = (gray > 127).astype(np.uint8) * 255
        return Image.fromarray(bw)

    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    bw = 255 - bw  # invert
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 3))
    bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, kernel)
    bw = 255 - bw  # restore
    return Image.fromarray(bw)


def detect_all_horizontal_bars(binary_pil):
    """
    Detect all horizontal bars in binary image.
    Returns list of (x, y, w, h) sorted by y.
    """
    if cv2 is None:
        return []

    bw = np.array(binary_pil)
    contours, _ = cv2.findContours(
        255 - bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        area = cv2.contourArea(c)
        # Horizontal bar filter
        if w > h * 3 and w > 20 and h > 3 and area > 20:
            boxes.append((x, y, w, h))
    boxes = sorted(boxes, key=lambda b: b[1])  # sort by y
    return boxes


def detect_test_bars(binary_pil):
    """Compatibility wrapper used by the UI to detect horizontal bars."""
    return detect_all_horizontal_bars(binary_pil)


def find_closest_bars_near_center(binary_pil, center_tolerance=0.5):
    """
    Find two horizontal bars that are closest to each other (vertical distance)
    and lie near the image center.
    Returns: list of two boxes [(x1,y1,w1,h1), (x2,y2,w2,h2)] or None.
    """
    all_bars = detect_all_horizontal_bars(binary_pil)
    if len(all_bars) < 2:
        return None

    h_img, w_img = np.array(binary_pil).shape[:2]
    center_y = h_img / 2.0
    y_range = center_tolerance * h_img

    # Filter bars whose center is within tolerance of image center
    near_center = []
    for (x, y, w, h) in all_bars:
        bar_center_y = y + h / 2.0
        if abs(bar_center_y - center_y) <= y_range:
            near_center.append((x, y, w, h))

    # Use near-center bars if at least 2, otherwise fallback to all bars
    candidate_bars = near_center if len(near_center) >= 2 else all_bars

    # Find pair with minimal vertical distance between consecutive bars
    min_dist = float('inf')
    best_pair = None
    for i in range(len(candidate_bars) - 1):
        bar1 = candidate_bars[i]
        bar2 = candidate_bars[i+1]
        # distance between bottom of bar1 and top of bar2
        dist = bar2[1] - (bar1[1] + bar1[3])
        if dist < min_dist:
            min_dist = dist
            best_pair = [bar1, bar2]

    return best_pair


def find_closest_bars_in_expanding_center_box(binary_pil, start_ratio=0.2, step_ratio=0.1, max_ratio=0.5):
    """
    Find two horizontal bars inside an expanding center box.
    The search starts from a small center box and expands until the box size
    reaches max_ratio of the image dimensions.

    Args:
        binary_pil: binary PIL image.
        start_ratio: initial center-box ratio (relative to image width/height).
        step_ratio: increment ratio for each expansion step.
        max_ratio: max center-box ratio; when reached with no pair, stop.

    Returns:
        (best_pair, used_box, used_ratio) where:
            best_pair: list of two boxes [(x,y,w,h), (x,y,w,h)] or None
            used_box: (x0, y0, x1, y1) for the box used at the final step
            used_ratio: float ratio used at the final step
    """
    all_bars = detect_all_horizontal_bars(binary_pil)
    if len(all_bars) < 2:
        return None, None, None

    h_img, w_img = np.array(binary_pil).shape[:2]
    cx, cy = w_img / 2.0, h_img / 2.0

    ratio = max(0.01, float(start_ratio))
    max_ratio = max(ratio, float(max_ratio))
    step_ratio = max(0.01, float(step_ratio))

    last_box = None
    last_ratio = ratio

    while ratio <= max_ratio + 1e-9:
        box_w = w_img * ratio
        box_h = h_img * ratio
        x0 = max(0.0, cx - box_w / 2.0)
        y0 = max(0.0, cy - box_h / 2.0)
        x1 = min(float(w_img), cx + box_w / 2.0)
        y1 = min(float(h_img), cy + box_h / 2.0)
        last_box = (int(x0), int(y0), int(x1), int(y1))
        last_ratio = ratio

        in_box = []
        for (x, y, w, h) in all_bars:
            bar_cx = x + w / 2.0
            bar_cy = y + h / 2.0
            if x0 <= bar_cx <= x1 and y0 <= bar_cy <= y1:
                in_box.append((x, y, w, h))

        if len(in_box) >= 2:
            candidate_bars = sorted(in_box, key=lambda b: b[1])
            min_dist = float('inf')
            best_pair = None
            for i in range(len(candidate_bars) - 1):
                bar1 = candidate_bars[i]
                bar2 = candidate_bars[i + 1]
                dist = bar2[1] - (bar1[1] + bar1[3])
                if dist < min_dist:
                    min_dist = dist
                    best_pair = [bar1, bar2]
            return best_pair, last_box, last_ratio

        ratio += step_ratio

    return None, last_box, last_ratio


def create_roi_from_bars(bars, image_shape, padding=20):
    """Create ROI from a pair of bars (x,y,w,h)."""
    h, w = image_shape[:2]
    x_min = min(b[0] for b in bars)
    y_min = min(b[1] for b in bars)
    x_max = max(b[0] + b[2] for b in bars)
    y_max = max(b[1] + b[3] for b in bars)

    x_min -= padding
    y_min -= padding
    x_max += padding
    y_max += padding

    x_min = max(0, x_min)
    y_min = max(0, y_min)
    x_max = min(w, x_max)
    y_max = min(h, y_max)
    return (x_min, y_min, x_max, y_max)


def crop_roi(image_pil, roi):
    """Crop image to ROI."""
    if roi is None:
        return image_pil
    return image_pil.crop(roi)


def build_intensity_profile(gray_pil):
    """
    Build row-wise intensity profile from a grayscale image.
    Lower values indicate darker rows.
    """
    img = np.array(gray_pil)
    if img.ndim == 3:
        img = np.mean(img, axis=2)
    return np.mean(img, axis=1)


def detect_vertical_line_regions(profile, threshold_scale=0.9, min_region_width=2):
    """
    Detect dark vertical line-like regions from a 1D column intensity profile.
    Returns list of (start_x, end_x) column indices.
    """
    profile = np.asarray(profile, dtype=float)
    mean_v = float(np.mean(profile))
    std_v = float(np.std(profile))
    threshold = mean_v * float(threshold_scale)
    threshold = max(threshold, mean_v - 0.5 * std_v)

    regions = []
    in_region = False
    start = 0

    for i, value in enumerate(profile):
        if value < threshold and not in_region:
            start = i
            in_region = True
        elif value >= threshold and in_region:
            end = i
            if end - start >= int(min_region_width):
                regions.append((start, end))
            in_region = False

    if in_region:
        end = len(profile)
        if end - start >= int(min_region_width):
            regions.append((start, end))

    return regions


def _detect_vertical_lines_morph(gray_pil):
    """Detect two dominant vertical lines with morphology on binary image."""
    if cv2 is None:
        return None

    img = np.array(gray_pil)
    if img.ndim == 3:
        img = cv2.cvtColor(img.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    else:
        img = img.astype(np.uint8)

    blur = cv2.GaussianBlur(img, (5, 5), 0)
    bw = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 7
    )
    h, w = bw.shape[:2]
    k_h = max(15, h // 10)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, k_h))
    vertical = cv2.morphologyEx(bw, cv2.MORPH_OPEN, kernel)
    vertical = cv2.dilate(vertical, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 7)), iterations=1)

    contours, _ = cv2.findContours(vertical, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for c in contours:
        x, y, ww, hh = cv2.boundingRect(c)
        if hh >= int(h * 0.25) and ww <= max(20, int(w * 0.08)):
            area = ww * hh
            cx = x + ww / 2.0
            candidates.append((area, cx))

    if len(candidates) < 2:
        return None

    candidates.sort(key=lambda t: t[0], reverse=True)
    centers = sorted(int(round(c[1])) for c in candidates[:6])
    # pick farthest pair among top candidates
    best = None
    best_gap = -1
    for i in range(len(centers)):
        for j in range(i + 1, len(centers)):
            gap = centers[j] - centers[i]
            if gap > best_gap:
                best_gap = gap
                best = (centers[i], centers[j])
    return best


def _detect_vertical_lines_from_binary(binary_pil):
    """Detect two vertical lines from black/white image by column darkness projection."""
    bw = np.array(binary_pil)
    if bw.ndim == 3:
        bw = np.mean(bw, axis=2)
    if cv2 is None:
        return None, []

    h, w = bw.shape[:2]
    y0_roi = int(h * 0.15)
    y1_roi = int(h * 0.85)
    bw_roi = bw[y0_roi:y1_roi, :]
    h_roi = max(1, y1_roi - y0_roi)

    def extract_candidates(mask):
        k_h = max(16, h_roi // 5)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, k_h))
        vertical = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        contours, _ = cv2.findContours(vertical, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        out = []
        for c in contours:
            x, y, ww, hh = cv2.boundingRect(c)
            if hh < int(h_roi * 0.35):
                continue
            if ww > max(30, int(w * 0.14)):
                continue
            cx = x + ww / 2.0
            out.append({
                "x": int(round(cx)),
                "y0": y + y0_roi,
                "y1": y + y0_roi + hh,
                "w": ww,
                "h": hh,
            })
        return out

    # Try both polarities because bw semantics can vary per image.
    black_mask = (bw_roi < 128).astype(np.uint8) * 255
    white_mask = (bw_roi >= 128).astype(np.uint8) * 255
    candidates = extract_candidates(black_mask) + extract_candidates(white_mask)

    # Hough fallback for vertical segments when morphology fails.
    if len(candidates) < 2:
        edges = cv2.Canny(bw_roi, 50, 150)
        lines = cv2.HoughLinesP(
            edges, 1, np.pi / 180, threshold=50,
            minLineLength=max(30, int(h_roi * 0.35)), maxLineGap=8
        )
        if lines is not None:
            for line in lines[:, 0, :]:
                x1, y1, x2, y2 = [int(v) for v in line]
                dx = abs(x2 - x1)
                dy = abs(y2 - y1)
                if dy < int(h_roi * 0.30):
                    continue
                if dx > max(6, int(w * 0.02)):
                    continue
                cx = int(round((x1 + x2) / 2.0))
                yy0 = min(y1, y2) + y0_roi
                yy1 = max(y1, y2) + y0_roi
                candidates.append({
                    "x": cx,
                    "y0": yy0,
                    "y1": yy1,
                    "w": max(1, dx + 1),
                    "h": max(1, yy1 - yy0),
                })

    if len(candidates) < 2:
        return None, []

    # De-duplicate close x candidates (keep the tallest one).
    candidates.sort(key=lambda c: (c["x"], -c["h"]))
    dedup = []
    for c in candidates:
        if not dedup or abs(c["x"] - dedup[-1]["x"]) > 4:
            dedup.append(c)
        elif c["h"] > dedup[-1]["h"]:
            dedup[-1] = c
    candidates = dedup

    candidate_xs = sorted(c["x"] for c in candidates)

    # choose two near-parallel lines:
    # high vertical overlap + similar width + enough spacing
    best_pair = None
    best_score = -1.0
    for i in range(len(candidates)):
        for j in range(i + 1, len(candidates)):
            a = candidates[i]
            b = candidates[j]
            dx = abs(a["x"] - b["x"])
            if dx < max(8, int(w * 0.03)):
                continue
            overlap = max(0, min(a["y1"], b["y1"]) - max(a["y0"], b["y0"]))
            min_h = max(1, min(a["h"], b["h"]))
            overlap_ratio = overlap / float(min_h)
            width_ratio = min(a["w"], b["w"]) / float(max(a["w"], b["w"]))
            score = overlap_ratio * 0.7 + width_ratio * 0.3
            if score > best_score:
                best_score = score
                xl, xr = sorted([a["x"], b["x"]])
                best_pair = (xl, xr)

    if best_pair is None:
        return None, candidate_xs

    return best_pair, candidate_xs


def crop_from_two_vertical_lines(gray_pil, threshold_scale=0.9, binary_pil=None):
    """
    Detect two dark vertical lines and crop around them.
    Output crop follows aspect ratio H = 2 * W.

    Returns:
        (cropped_pil, crop_box, line_xs, candidate_xs)
        cropped_pil: cropped grayscale PIL image
        crop_box: (x0, y0, x1, y1)
        line_xs: (x_left, x_right) or None if fallback
        candidate_xs: list of candidate x positions
    """
    img = np.array(gray_pil)
    if img.ndim == 3:
        img = np.mean(img, axis=2)
    h, w = img.shape[:2]

    morph_lines = None
    candidate_xs = []
    if binary_pil is not None:
        morph_lines, candidate_xs = _detect_vertical_lines_from_binary(binary_pil)
    if morph_lines is None:
        morph_lines = _detect_vertical_lines_morph(gray_pil)

    cx = w / 2.0
    line_xs = None
    if morph_lines is not None:
        x_left, x_right = morph_lines
        if x_right > x_left + 2:
            line_xs = (x_left, x_right)

    if line_xs is None:
        col_profile = np.mean(img, axis=0)
        regions = detect_vertical_line_regions(
            col_profile, threshold_scale=threshold_scale, min_region_width=2
        )
        left = []
        right = []
        for s, e in regions:
            mx = (s + e) / 2.0
            if mx < cx:
                left.append((s, e, mx))
            else:
                right.append((s, e, mx))

        if left and right:
            left_region = max(left, key=lambda r: r[2])
            right_region = min(right, key=lambda r: r[2])
            x_left = int(round(left_region[2]))
            x_right = int(round(right_region[2]))
            if x_right > x_left + 2:
                line_xs = (x_left, x_right)
        elif len(regions) >= 2:
            centers = sorted(int(round((s + e) / 2.0)) for s, e in regions)
            if not candidate_xs:
                candidate_xs = centers[:]
            x_left, x_right = centers[0], centers[-1]
            if x_right > x_left + 2:
                line_xs = (x_left, x_right)

    if line_xs is None:
        # Fallback: center crop with H=2W, using 30% height.
        crop_h = max(2, int(h * 0.3))
        crop_w = max(1, crop_h // 2)
        x0 = max(0, (w - crop_w) // 2)
        y0 = max(0, (h - crop_h) // 2)
        x1 = min(w, x0 + crop_w)
        y1 = min(h, y0 + crop_h)
        return gray_pil.crop((x0, y0, x1, y1)), (x0, y0, x1, y1), None, candidate_xs

    x_left, x_right = line_xs
    line_width = max(2, x_right - x_left)
    crop_w = line_width
    crop_h = crop_w * 2

    if crop_h > h:
        crop_h = h
        crop_w = max(1, crop_h // 2)

    x_center = (x_left + x_right) / 2.0
    y_center = h / 2.0

    x0 = int(round(x_center - crop_w / 2.0))
    y0 = int(round(y_center - crop_h / 2.0))
    x1 = x0 + int(crop_w)
    y1 = y0 + int(crop_h)

    if x0 < 0:
        x1 -= x0
        x0 = 0
    if x1 > w:
        shift = x1 - w
        x0 -= shift
        x1 = w
    if y0 < 0:
        y1 -= y0
        y0 = 0
    if y1 > h:
        shift = y1 - h
        y0 -= shift
        y1 = h

    x0 = max(0, x0)
    y0 = max(0, y0)
    x1 = min(w, x1)
    y1 = min(h, y1)

    return gray_pil.crop((x0, y0, x1, y1)), (x0, y0, x1, y1), line_xs, candidate_xs


def detect_line_regions(profile, threshold_scale=0.8, min_region_height=3):
    """
    Detect dark line-like regions from a 1D intensity profile.
    Returns list of (start, end) row indices.
    """
    profile = np.asarray(profile, dtype=float)
    mean_v = float(np.mean(profile))
    std_v = float(np.std(profile))
    threshold = mean_v * float(threshold_scale)
    # Fallback threshold for low-contrast profiles
    threshold = max(threshold, mean_v - 0.5 * std_v)
    regions = []
    in_region = False
    start = 0

    for i, value in enumerate(profile):
        if value < threshold and not in_region:
            start = i
            in_region = True
        elif value >= threshold and in_region:
            end = i
            if end - start > int(min_region_height):
                regions.append((start, end))
            in_region = False

    if in_region:
        end = len(profile)
        if end - start > int(min_region_height):
            regions.append((start, end))

    return regions


def measure_line_darkness(gray_pil, regions):
    """
    Measure mean darkness for each detected region.
    Darkness = image background mean - line region mean.
    """
    img = np.array(gray_pil)
    if img.ndim == 3:
        img = np.mean(img, axis=2)

    results = []
    background = float(np.mean(img))

    for start, end in regions:
        line_region = img[start:end, :]
        line_height = int(end - start)
        line_mean = float(np.mean(line_region))
        darkness = background - line_mean
        x_start = 0
        x_end = int(img.shape[1])
        line_width = int(x_end - x_start)
        results.append({
            "start": int(start),
            "end": int(end),
            "x_start": int(x_start),
            "x_end": int(x_end),
            "line_width": line_width,
            "line_height": line_height,
            "line_mean": line_mean,
            "darkness": float(darkness),
        })

    return results


# Main upload function (used in the main app)
def upload_and_convert_to_grayscale():
    uploaded_file = st.file_uploader(
        "Upload Image", type=["png", "jpg", "jpeg"])
    if uploaded_file is None:
        return None

    image = Image.open(uploaded_file)
    st.subheader("Original Image")
    st.image(image, width='stretch')

    # Original grayscale (no enhancement)
    gray = process_image_to_grayscale(image)
    st.subheader("Grayscale Image")
    st.image(gray, width='stretch')

    # Enhanced detection image
    detection_img = build_enhanced_detection_image(gray)
    st.subheader("Enhanced Detection Image")
    st.image(detection_img, width='stretch')

    # Binary image for bar detection
    bw_img = build_black_white_image(detection_img)
    st.subheader("Black White Image")
    st.image(bw_img, width='stretch')

    # Find closest bars near center
    bars = find_closest_bars_near_center(bw_img)

    if bars is not None:
        overlay = image.copy()
        overlay_np = np.array(overlay)
        for (x, y, w, h) in bars:
            cv2.rectangle(overlay_np, (x, y), (x+w, y+h), (0, 255, 0), 3)
        overlay = Image.fromarray(overlay_np)
        st.subheader("Detected Bars (Closest Pair Near Center)")
        st.image(overlay, width='stretch')

        # ROI based on bars, cropped from original grayscale
        roi = create_roi_from_bars(bars, np.array(gray).shape, padding=20)
        cropped = crop_roi(gray, roi)
        st.subheader("Cropped ROI (from original grayscale)")
        st.image(cropped, width='stretch')

    return gray
