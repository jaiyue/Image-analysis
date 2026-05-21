import base64
from pathlib import Path

import streamlit as st


ASSETS_DIR = Path(__file__).parent / 'assets'
LOGO_CANDIDATES = [
    ASSETS_DIR / 'biopanda_logo.png',
    ASSETS_DIR / 'image-analysis-logo.svg'
]


def render_sidebar_brand():
    logo_html = '<strong>Image Analysis Studio</strong>'

    for logo_path in LOGO_CANDIDATES:
        if logo_path.exists():
            if logo_path.suffix.lower() == '.png':
                encoded_logo = base64.b64encode(
                    logo_path.read_bytes()).decode('utf-8')
                logo_html = f"<img src='data:image/png;base64,{encoded_logo}' alt='Image Analysis logo'>"
            else:
                logo_html = logo_path.read_text(encoding='utf-8')
            break

    st.sidebar.markdown(
        f'''
        <div class='analysis-sidebar-brand'>
            <div class='analysis-sidebar-logo-card'>
                {logo_html}
            </div>
        </div>
        ''',
        unsafe_allow_html=True
    )


def render_dashboard_header(page_name, page_description):
    st.markdown(
        f"""
        <div class='analysis-hero'>
            <div class='analysis-hero-kicker'>Standalone project</div>
            <h1 class='analysis-hero-title'>{page_name}</h1>
            <p class='analysis-hero-subtitle'>{page_description}</p>
        </div>
        """,
        unsafe_allow_html=True
    )
