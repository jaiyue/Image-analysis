import streamlit as st
from pathlib import Path

from layout import render_dashboard_header, render_sidebar_brand
from navigation import PAGE_BY_LABEL, render_sidebar_navigation
from theme import apply_custom_theme, apply_minor_ui_fixes, get_native_theme_is_dark
from library import render_library_page
from standard import render_standard_page
from insight import render_insights_page
from human_review import render_human_review_page
from database import render_database_page
from image_processing import upload_and_convert_to_grayscale

st.set_page_config(
    page_title='Image Analysis Studio',
    page_icon='IA',
    layout='wide',
    initial_sidebar_state='expanded'
)


PAGE_HANDLERS = {
    'Home': lambda: render_home_page(),
    'Library': lambda: render_library_page(),
    'Standard': lambda: render_standard_page(),
    'Insights': lambda: render_insights_page(),
    'Review': lambda: render_human_review_page(),
    'Database': lambda: render_database_page(),
    'Settings': lambda: render_settings_page(),
}


def clear_all_content():
    project_root = Path(__file__).parent
    uploads_dir = project_root / 'uploads'

    if uploads_dir.exists():
        for p in uploads_dir.iterdir():
            if p.is_file():
                p.unlink(missing_ok=True)

    for ref_name in ('standard_reference.json', 'standard_ref.json'):
        ref_path = project_root / ref_name
        if ref_path.exists():
            ref_path.unlink(missing_ok=True)

    for db_name in ('uploads.db', 'human_review.db'):
        db_path = project_root / db_name
        if db_path.exists():
            db_path.unlink(missing_ok=True)

    preserved_selected = st.session_state.get('selected_page_label', 'Library')
    st.session_state.clear()
    st.session_state['selected_page_label'] = preserved_selected
    st.session_state['selected_page_label_radio'] = preserved_selected


def render_home_page():
    st.subheader('Workspace Overview')
    st.write('This project contains the core dashboard shell: a top bar, a sidebar, and a simple content area.')

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown(
            """
            <div class='analysis-card'>
                <div class='analysis-card-label'>Active modules</div>
                <div class='analysis-card-value'>4</div>
                <div class='analysis-card-help'>Layout, navigation, theme, and app entrypoint.</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    with col2:
        st.markdown(
            """
            <div class='analysis-card'>
                <div class='analysis-card-label'>Runtime</div>
                <div class='analysis-card-value'>Local</div>
                <div class='analysis-card-help'>Run directly with Streamlit, no dependency on the invoice dashboard.</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    with col3:
        st.markdown(
            """
            <div class='analysis-card'>
                <div class='analysis-card-label'>Scope</div>
                <div class='analysis-card-value'>Shell</div>
                <div class='analysis-card-help'>Framework only, ready for your own pages and data sources.</div>
            </div>
            """,
            unsafe_allow_html=True
        )


# `render_library_page` is implemented in `library.py` and imported above.


def render_settings_page():
    st.subheader('Settings')
    st.write(
        'Use this area for environment settings, theme controls, and app preferences.')
    st.warning('No invoice-dashboard settings are imported here.')


def main():
    apply_custom_theme(dark_mode_enabled=get_native_theme_is_dark())
    apply_minor_ui_fixes()
    render_sidebar_brand()

    selected_page_label = render_sidebar_navigation()
    st.sidebar.divider()
    if st.sidebar.button('Clear All', key='clear_all_content', width='stretch'):
        clear_all_content()
        st.session_state.selected_page_label = 'Library'
        st.session_state.selected_page_label_radio = 'Library'
        st.rerun()

    page_definition = PAGE_BY_LABEL[selected_page_label]

    render_dashboard_header(
        page_name=page_definition['name'],
        page_description=page_definition['description']
    )

    page_handler = PAGE_HANDLERS.get(selected_page_label)

    if page_handler is None:
        st.error(
            f'No page handler has been configured for: {selected_page_label}')
        return

    page_handler()


if __name__ == '__main__':
    main()
