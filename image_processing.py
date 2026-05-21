# image_processing.py

from PIL import Image, ImageOps
import streamlit as st
import numpy as np

try:
    import cv2
except Exception:
    cv2 = None


def process_image_to_grayscale(
    pil_image,
    resize_to=None
):

    if pil_image.mode == "RGBA":
        pil_image = pil_image.convert("RGB")

    img = pil_image.copy()

    if resize_to:
        img = img.resize(resize_to)

    return ImageOps.grayscale(img)


def build_enhanced_detection_image(gray_pil):
    """Return enhanced grayscale image used for detection preview."""
    gray = np.array(gray_pil)

    if cv2 is None:
        return gray_pil

    detection = cv2.equalizeHist(gray)
    detection = cv2.GaussianBlur(detection, (5, 5), 0)
    return Image.fromarray(detection)


# Main upload function
def upload_and_convert_to_grayscale():

    uploaded_file = st.file_uploader(
        "Upload Image",
        type=["png", "jpg", "jpeg"]
    )

    if uploaded_file is None:
        return None

    # Original image
    image = Image.open(uploaded_file)

    st.subheader("Original Image")
    st.image(image, width='stretch')

    # Grayscale image
    gray = process_image_to_grayscale(image)

    st.subheader("Grayscale Image")
    st.image(gray, width='stretch')

    # Enhanced detection image
    detection_img = build_enhanced_detection_image(gray)

    # Enhanced image
    st.subheader("Enhanced Detection Image")

    st.image(
        detection_img,
        width='stretch'
    )

    return gray
