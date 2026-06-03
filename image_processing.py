# image_processing.py

from PIL import Image, ImageOps, ImageDraw
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


def detect_line_regions(
    profile,
    threshold_scale=0.8,
    min_region_height=3,
    edge_exclusion_ratio=0.02,
    max_region_height_ratio=0.30,
):
    """
    Detect dark line-like regions from a 1D intensity profile.
    Returns list of (start, end) row indices.
    """
    profile = np.asarray(profile, dtype=float)
    if profile.size == 0:
        return []

    # Smooth to make faint valleys more stable.
    if profile.size >= 5:
        kernel = np.array([1, 2, 3, 2, 1], dtype=float)
        kernel /= np.sum(kernel)
        profile_s = np.convolve(profile, kernel, mode='same')
    else:
        profile_s = profile

    mean_v = float(np.mean(profile_s))
    std_v = float(np.std(profile_s))

    def _collect_regions_with_threshold(threshold_value):
        out = []
        in_region = False
        start = 0
        for i, value in enumerate(profile_s):
            if value < threshold_value and not in_region:
                start = i
                in_region = True
            elif value >= threshold_value and in_region:
                end = i
                if end - start > int(min_region_height):
                    out.append((start, end))
                in_region = False
        if in_region:
            end = len(profile_s)
            if end - start > int(min_region_height):
                out.append((start, end))
        return out

    base_thr = max(mean_v * float(threshold_scale), mean_v - 0.20 * std_v)
    relaxed_thr_1 = max(base_thr, mean_v - 0.10 * std_v)
    relaxed_thr_2 = max(relaxed_thr_1, float(np.percentile(profile_s, 52)))
    relaxed_thr_3 = max(relaxed_thr_2, float(np.percentile(profile_s, 58)))
    threshold_candidates = [base_thr, relaxed_thr_1, relaxed_thr_2, relaxed_thr_3]

    regions = []
    best_regions = []
    for thr in threshold_candidates:
        candidate = _collect_regions_with_threshold(thr)
        if len(candidate) > len(best_regions):
            best_regions = candidate
        if len(candidate) >= 2:
            regions = candidate
            break
    if not regions:
        regions = best_regions

    n = len(profile)
    if n <= 0:
        return regions

    edge_margin = max(2, int(round(n * float(edge_exclusion_ratio))))
    max_h = max(int(min_region_height), int(round(n * float(max_region_height_ratio))))

    filtered = []
    for s, e in regions:
        h = int(e - s)
        # Ignore edge-touching regions and overly thick regions (often cassette/frame background).
        if s <= edge_margin:
            continue
        if e >= (n - edge_margin):
            continue
        if h > max_h:
            continue
        filtered.append((s, e))

    # If too aggressive filtering removed faint valid lines, retry with looser guards once.
    if len(filtered) < 2 and len(regions) >= 2:
        relaxed_edge_margin = max(1, int(round(n * 0.01)))
        relaxed_max_h = max(max_h, int(round(n * 0.45)))
        relaxed = []
        for s, e in regions:
            h = int(e - s)
            if s <= relaxed_edge_margin:
                continue
            if e >= (n - relaxed_edge_margin):
                continue
            if h > relaxed_max_h:
                continue
            relaxed.append((s, e))
        if relaxed:
            filtered = relaxed

    return filtered


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
        line_pixels = line_region.astype(float).ravel()
        if line_pixels.size > 0:
            sorted_pixels = np.sort(line_pixels)
            trim_n = int(np.floor(sorted_pixels.size * 0.10))
            if trim_n > 0 and (sorted_pixels.size - 2 * trim_n) >= 1:
                trimmed_pixels = sorted_pixels[trim_n: sorted_pixels.size - trim_n]
            else:
                trimmed_pixels = sorted_pixels
            line_mean = float(np.mean(trimmed_pixels))
        else:
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


def analyze_library_image(gray_pil):
    """
    Run Library-page crop/detection pipeline and return display/persist artifacts.
    """
    result = {
        "cropped": None,
        "vertical_overlay": None,
        "cropped_between": None,
        "analysis_img_trimmed": None,
        "cropped_overlay": None,
        "recrop_overlay": None,
        "table_rows": [],
        "c": None,
        "t": None,
        "bg": None,
        "ratio": None,
        "ct_bg_sum": None,
        "vertical_crop_reason": "no_vertical_lines",
        "trim_percent_used": 20,
    }

    def _to_dark_value(v):
        if v is None:
            return None
        return float(255.0 - float(v))

    def _r4(v):
        if v is None:
            return None
        return round(float(v), 4)

    w_gray, h_gray = gray_pil.size
    crop_w = max(1, int(w_gray * 0.25))
    crop_h = max(1, int(h_gray * 0.25))
    x0 = (w_gray - crop_w) // 2
    y0 = (h_gray - crop_h) // 2
    x1 = x0 + crop_w
    y1 = y0 + crop_h
    cropped = gray_pil.crop((x0, y0, x1, y1))
    result["cropped"] = cropped

    lr_trim = int(round(cropped.width * 0.10))
    if cropped.width - 2 * lr_trim >= 2:
        cropped_for_vertical = cropped.crop(
            (lr_trim, 0, cropped.width - lr_trim, cropped.height)
        )
    else:
        cropped_for_vertical = cropped

    cropped_np = np.array(cropped_for_vertical)
    if cropped_np.ndim == 3:
        cropped_np = np.mean(cropped_np, axis=2)
    col_profile_raw = np.mean(cropped_np, axis=0).astype(float)

    # Smooth profile to reduce local noise and make weak guide lines detectable.
    if len(col_profile_raw) >= 5:
        kernel = np.array([1, 2, 3, 2, 1], dtype=float)
        kernel /= np.sum(kernel)
        col_profile = np.convolve(col_profile_raw, kernel, mode='same')
    else:
        col_profile = col_profile_raw

    def _collect_regions(dark_mask, min_width):
        regions_local = []
        run_start_local = None
        for idx, is_dark in enumerate(dark_mask):
            if is_dark and run_start_local is None:
                run_start_local = idx
            elif (not is_dark) and run_start_local is not None:
                run_end_local = idx
                if run_end_local - run_start_local >= int(min_width):
                    regions_local.append((run_start_local, run_end_local))
                run_start_local = None
        if run_start_local is not None:
            run_end_local = len(dark_mask)
            if run_end_local - run_start_local >= int(min_width):
                regions_local.append((run_start_local, run_end_local))
        return regions_local

    mean_col = float(np.mean(col_profile))
    std_col = float(np.std(col_profile))
    primary_thr = min(float(mean_col * 0.90), float(mean_col - 0.3 * std_col))
    raw_v_regions = _collect_regions(col_profile < primary_thr, min_width=2)

    # Fallback: relax threshold and min width for low-contrast images.
    if len(raw_v_regions) < 2:
        relaxed_thr_1 = float(mean_col - 0.15 * std_col)
        relaxed_thr_2 = float(np.percentile(col_profile, 45))
        for thr in (relaxed_thr_1, relaxed_thr_2):
            candidate_regions = _collect_regions(col_profile < thr, min_width=1)
            if len(candidate_regions) >= 2:
                raw_v_regions = candidate_regions
                break

    # Remove edge-touching regions to avoid detecting the outer cassette/image border.
    edge_guard = max(2, int(round(cropped_for_vertical.width * 0.04)))
    v_regions = [
        (s, e) for s, e in raw_v_regions
        if s > edge_guard and e < (cropped_for_vertical.width - edge_guard)
    ]
    # If all removed, keep original to avoid total detection failure.
    if not v_regions:
        v_regions = raw_v_regions

    vertical_overlay = cropped_for_vertical.convert('RGB')
    draw_v = ImageDraw.Draw(vertical_overlay)
    w_crop, h_crop = vertical_overlay.size
    for xs, xe in v_regions:
        rx0 = max(0, int(xs))
        rx1 = min(w_crop - 1, int(xe))
        draw_v.rectangle((rx0, 0, rx1, h_crop - 1), outline=(0, 255, 255), width=2)
    result["vertical_overlay"] = vertical_overlay

    cropped_between = None
    vertical_crop_reason = 'ok'
    if len(v_regions) >= 2:
        centers = sorted([((s + e) / 2.0, (s, e)) for s, e in v_regions], key=lambda x: x[0])
        cx = w_crop / 2.0
        min_gap = max(8.0, w_crop * 0.08)
        max_gap = max(min_gap + 2.0, w_crop * 0.42)
        target_gap = w_crop * 0.24

        best_pair = None
        best_score = float('inf')
        # Preferred: pair straddling center with reasonable gap.
        for i in range(len(centers)):
            c_l, r_l = centers[i]
            if c_l >= cx:
                continue
            for j in range(i + 1, len(centers)):
                c_r, r_r = centers[j]
                if c_r <= cx:
                    continue
                gap = c_r - c_l
                if gap < min_gap or gap > max_gap:
                    continue
                pair_center = (c_l + c_r) / 2.0
                center_pen = abs(pair_center - cx) / max(1.0, w_crop)
                gap_pen = abs(gap - target_gap) / max(1.0, w_crop)
                score = 0.65 * gap_pen + 0.35 * center_pen
                if score < best_score:
                    best_score = score
                    best_pair = (r_l, r_r)

        # Fallback: choose center-straddling pair with minimum gap.
        if best_pair is None:
            best_gap = float('inf')
            for i in range(len(centers)):
                c_l, r_l = centers[i]
                if c_l >= cx:
                    continue
                for j in range(i + 1, len(centers)):
                    c_r, r_r = centers[j]
                    if c_r <= cx:
                        continue
                    gap = c_r - c_l
                    if gap < min_gap:
                        continue
                    if gap < best_gap:
                        best_gap = gap
                        best_pair = (r_l, r_r)

        if best_pair is None:
            left_region = v_regions[0]
            right_region = v_regions[-1]
        else:
            left_region, right_region = best_pair

        pad_x = 3
        x_left = max(0, int(left_region[1]) - pad_x)
        x_right = min(w_crop, int(right_region[0]) + pad_x)
        if x_right - x_left >= 2:
            cropped_between = cropped_for_vertical.crop((x_left, 0, x_right, h_crop))
        else:
            vertical_crop_reason = 'width_insufficient'
    elif len(v_regions) == 1:
        one_region = v_regions[0]
        x_left = max(0, int(one_region[0]))
        x_right = min(w_crop, int(one_region[1]))
        if x_right - x_left >= 2:
            cropped_between = cropped_for_vertical.crop((x_left, 0, x_right, h_crop))
            vertical_crop_reason = 'single_line_cropped'
        else:
            vertical_crop_reason = 'single_line_width_insufficient'
    else:
        vertical_crop_reason = 'no_vertical_lines'
    result["cropped_between"] = cropped_between
    result["vertical_crop_reason"] = vertical_crop_reason

    analysis_img = cropped_between if cropped_between is not None else cropped_for_vertical

    def _run_trim_pass(src_img, trim_percent):
        trim_top = int(round(src_img.height * trim_percent))
        trim_bottom = int(round(src_img.height * (1.0 - trim_percent)))
        trim_left = int(round(src_img.width * 0.05))
        trim_right = int(round(src_img.width * 0.95))
        if (trim_bottom - trim_top >= 2) and (trim_right - trim_left >= 2):
            analysis_img_trimmed_local = src_img.crop((trim_left, trim_top, trim_right, trim_bottom))
        else:
            analysis_img_trimmed_local = src_img

        profile = build_intensity_profile(analysis_img_trimmed_local)
        regions = detect_line_regions(profile, threshold_scale=0.85, min_region_height=2)
        darkness_results = measure_line_darkness(analysis_img_trimmed_local, regions)
        if not regions:
            return {
                "analysis_img_trimmed": analysis_img_trimmed_local,
                "cropped_overlay": None,
                "recrop_overlay": None,
                "table_rows": [],
                "c": None,
                "t": None,
                "bg": None,
                "ratio": None,
                "ct_bg_sum": None,
                "recrop_results_count": 0,
                "trim_percent_used": int(round(trim_percent * 100)),
            }

        cropped_overlay = analysis_img_trimmed_local.convert('RGB')
        draw = ImageDraw.Draw(cropped_overlay)
        w_crop2, h_crop2 = cropped_overlay.size
        for row in darkness_results:
            y0_r = max(0, int(row['start']))
            y1_r = min(h_crop2 - 1, int(row['end']))
            x0_r = max(0, int(row.get('x_start', 0)))
            x1_r = min(w_crop2 - 1, int(row.get('x_end', w_crop2)))
            draw.rectangle((x0_r, y0_r, x1_r, y1_r), outline=(255, 0, 0), width=2)

        pad = 20
        n_regions = len(darkness_results)
        take_n = 3 if n_regions == 3 else min(2, n_regions)
        cy = h_crop2 / 2.0
        sorted_by_center = sorted(
            darkness_results,
            key=lambda r: abs(((r['start'] + r['end']) / 2.0) - cy)
        )
        selected = sorted_by_center[:take_n]
        x_min = min(int(r.get('x_start', 0)) for r in selected)
        x_max = max(int(r.get('x_end', w_crop2)) for r in selected)
        y_min = min(int(r['start']) for r in selected)
        y_max = max(int(r['end']) for r in selected)
        cx_sel = (x_min + x_max) / 2.0
        cy_sel = (y_min + y_max) / 2.0
        half_w = max(cx_sel - x_min, x_max - cx_sel) + pad
        half_h = max(cy_sel - y_min, y_max - cy_sel) + pad
        x0_c = max(0, int(round(cx_sel - half_w)))
        x1_c = min(w_crop2, int(round(cx_sel + half_w)))
        y0_c = max(0, int(round(cy_sel - half_h)))
        y1_c = min(h_crop2, int(round(cy_sel + half_h)))
        refined_crop = analysis_img_trimmed_local.crop((x0_c, y0_c, x1_c, y1_c))

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
            draw_recrop.rectangle((0, y0_rr, w_ref - 1, y1_rr), outline=(255, 0, 0), width=2)
            draw_recrop.text((4, max(0, y0_rr - 14)), label_map.get(idx, f"line_{idx}"), fill=(255, 0, 0))

        name_map = {1: 'c', 2: 't'}
        table_rows = [{
            'name': name_map.get(i, f"line_{i}"),
            'gray_mean': _r4(_to_dark_value(r.get('line_mean', 0.0)))
        } for i, r in enumerate(recrop_results, start=1)]
        if len(recrop_results) >= 2:
            sorted_rows = sorted(recrop_results, key=lambda r: int(r.get('start', 0)))
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
                    table_rows.append({'name': 'background', 'gray_mean': _r4(_to_dark_value(float(np.mean(bg_region))))})

        c_val = next((r['gray_mean'] for r in table_rows if r.get('name') == 'c'), None)
        t_val = next((r['gray_mean'] for r in table_rows if r.get('name') == 't'), None)
        bg_val = next((r['gray_mean'] for r in table_rows if r.get('name') == 'background'), None)
        ratio_val = None
        ct_bg_sum_val = None
        if c_val is not None and t_val is not None and bg_val is not None:
            denom = c_val - bg_val
            if abs(denom) > 1e-12:
                ratio_val = _r4(float((t_val - bg_val) / denom))
                table_rows.append({'name': 'ratio', 'gray_mean': ratio_val})
            ct_bg_sum_val = _r4(float((c_val - bg_val) + (t_val - bg_val)))
            table_rows.append({'name': '(c-bg)+(t-bg)', 'gray_mean': ct_bg_sum_val})

        return {
            "analysis_img_trimmed": analysis_img_trimmed_local,
            "cropped_overlay": cropped_overlay,
            "recrop_overlay": recrop_overlay,
            "table_rows": table_rows,
            "c": _r4(c_val),
            "t": _r4(t_val),
            "bg": _r4(bg_val),
            "ratio": ratio_val,
            "ct_bg_sum": ct_bg_sum_val,
            "recrop_results_count": len(recrop_results),
            "trim_percent_used": int(round(trim_percent * 100)),
        }

    trim_schedule = [0.20, 0.15, 0.10, 0.05, 0.00]
    best_pass = None
    for trim_percent in trim_schedule:
        pass_result = _run_trim_pass(analysis_img, trim_percent)
        if best_pass is None:
            best_pass = pass_result
        if int(pass_result.get("recrop_results_count", 0)) >= 2:
            best_pass = pass_result
            break
        if int(pass_result.get("recrop_results_count", 0)) > int(best_pass.get("recrop_results_count", 0)):
            best_pass = pass_result

    result["analysis_img_trimmed"] = best_pass.get("analysis_img_trimmed")
    result["cropped_overlay"] = best_pass.get("cropped_overlay")
    result["recrop_overlay"] = best_pass.get("recrop_overlay")
    result["table_rows"] = best_pass.get("table_rows", [])
    result["c"] = best_pass.get("c")
    result["t"] = best_pass.get("t")
    result["bg"] = best_pass.get("bg")
    result["ratio"] = best_pass.get("ratio")
    result["ct_bg_sum"] = best_pass.get("ct_bg_sum")
    result["trim_percent_used"] = best_pass.get("trim_percent_used", 20)
    return result


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
