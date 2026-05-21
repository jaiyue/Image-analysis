from PIL import Image
from io import BytesIO

import streamlit as st
from PIL import Image, ImageOps
import numpy as np
try:
    import cv2
except Exception:
    cv2 = None


def detect_and_crop_red_bars(pil_image, padding_cm=1.0, dpi=96, min_area_ratio=0.001):
    """Detect two red bars in the image and crop to include them with padding.

    If detection fails or OpenCV is not available, returns the original image.
    - padding_cm: how many centimeters of padding around the union box
    - dpi: dots per inch to convert cm -> pixels
    - min_area_ratio: minimum contour area ratio relative to image area
    """
    if cv2 is None:
        return pil_image

    img_rgb = pil_image.convert('RGB')
    arr = np.array(img_rgb)
    h, w = arr.shape[:2]

    # Convert to HSV and threshold red colors
    hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)
    # red wraps around 0/180 in HSV; use two ranges
    lower1 = np.array([0, 80, 40])
    upper1 = np.array([10, 255, 255])
    lower2 = np.array([170, 80, 40])
    upper2 = np.array([180, 255, 255])
    mask1 = cv2.inRange(hsv, lower1, upper1)
    mask2 = cv2.inRange(hsv, lower2, upper2)
    mask = cv2.bitwise_or(mask1, mask2)

    # Clean up mask
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

    contours, _ = cv2.findContours(
        mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours or len(contours) < 2:
        return pil_image

    # filter contours by area
    min_area = max(1, int(min_area_ratio * h * w))
    valid = [c for c in contours if cv2.contourArea(c) >= min_area]
    if len(valid) < 2:
        return pil_image

    # choose two largest contours
    valid_sorted = sorted(valid, key=cv2.contourArea, reverse=True)[:2]
    boxes = [cv2.boundingRect(c) for c in valid_sorted]

    x_min = min(b[0] for b in boxes)
    y_min = min(b[1] for b in boxes)
    x_max = max(b[0] + b[2] for b in boxes)
    y_max = max(b[1] + b[3] for b in boxes)

    pad_px = int(round(padding_cm * dpi / 2.54))
    x_min = max(0, x_min - pad_px)
    y_min = max(0, y_min - pad_px)
    x_max = min(w, x_max + pad_px)
    y_max = min(h, y_max + pad_px)

    cropped = arr[y_min:y_max, x_min:x_max]
    try:
        return Image.fromarray(cropped)
    except Exception:
        return pil_image


def process_image_to_grayscale(pil_image, resize_to=None):
    """Convert a PIL Image to grayscale and optionally resize.

    Returns a new PIL Image in RGB mode (so Streamlit displays consistently).
    """
    if pil_image.mode == 'RGBA':
        pil_image = pil_image.convert('RGB')

    img = pil_image.copy()

    if resize_to:
        img.thumbnail(resize_to)

    gray = ImageOps.grayscale(img)
    return gray.convert('RGB')
# image_processing.py


def upload_and_convert_to_grayscale():
    """
    Upload an image and convert it to grayscale.
    """

    # Upload image
    uploaded_file = st.file_uploader(
        "Upload an Image",
        type=["png", "jpg", "jpeg"]
    )

    if uploaded_file is not None:

        # Open image
        image = Image.open(uploaded_file)

        # Display original image
        st.subheader("Original Image")
        st.image(image, width='stretch')

        # Detect and crop red bars
        cropped_image = detect_and_crop_red_bars(image)

        # Show cropped image
        st.subheader("Cropped Image")
        st.image(cropped_image, width='stretch')

        # Convert cropped image to grayscale
        grayscale_image = cropped_image.convert("L")
        # Display grayscale image
        st.subheader("Grayscale Image")
        st.image(grayscale_image, width='stretch')

        # Save grayscale image to memory
        buffer = BytesIO()
        grayscale_image.save(buffer, format="PNG")

        # Download button
        st.download_button(
            label="Download Grayscale Image",
            data=buffer.getvalue(),
            file_name="grayscale_image.png",
            mime="image/png"
        )

        # Return grayscale image if needed elsewhere
        return grayscale_image

    return None
