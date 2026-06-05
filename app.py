import streamlit as st
from pathlib import Path
import sqlite3

from layout import render_dashboard_header, render_sidebar_brand
from navigation import PAGE_BY_LABEL, render_sidebar_navigation
from theme import apply_custom_theme, apply_minor_ui_fixes, get_native_theme_is_dark
from library import render_library_page
from standard import render_standard_page
from results import render_insights_page
from analysis import render_analysis_page
from human_review import render_human_review_page
from database import render_database_page
from db_backup import render_database_backup_page

st.set_page_config(
    page_title='Image Analysis Studio',
    page_icon='IA',
    layout='wide',
    initial_sidebar_state='expanded'
)


PAGE_HANDLERS = {
    'Library': lambda: render_library_page(),
    'Standard': lambda: render_standard_page(),
    'Results': lambda: render_insights_page(),
    'Analysis': lambda: render_analysis_page(),
    'Review': lambda: render_human_review_page(),
    'Database': lambda: render_database_page(),
    'Backup': lambda: render_database_backup_page(),
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

    for db_name in ('human_review.db',):
        db_path = project_root / db_name
        if db_path.exists():
            db_path.unlink(missing_ok=True)

    experiment_db_path = project_root / 'experiment_data.db'
    if experiment_db_path.exists():
        conn = sqlite3.connect(experiment_db_path)
        try:
            conn.execute('DELETE FROM strip_results')
            conn.execute('DELETE FROM upload_records')
            conn.execute('DELETE FROM upload_meta')
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()

    preserved_selected = st.session_state.get('selected_page_label', 'Library')
    st.session_state.clear()
    st.session_state['selected_page_label'] = preserved_selected
    st.session_state['selected_page_label_radio'] = preserved_selected

def _theme_is_dark():
    return get_native_theme_is_dark()


def main():
    apply_custom_theme(dark_mode_enabled=_theme_is_dark())
    apply_minor_ui_fixes()
    render_sidebar_brand()

    selected_page_label = render_sidebar_navigation()
    st.sidebar.divider()
    with st.sidebar.expander('Danger zone', expanded=False):
        confirm_clear = st.checkbox(
            'Confirm clearing uploaded results',
            key='confirm_clear_all_content',
        )
        if st.button('Clear All', key='clear_all_content', disabled=not confirm_clear, width='stretch'):
            clear_all_content()
            st.session_state.selected_page_label = 'Library'
            st.session_state.selected_page_label_radio = 'Library'
            st.session_state.confirm_clear_all_content = False
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
