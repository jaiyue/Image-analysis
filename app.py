import streamlit as st

from layout import render_dashboard_header, render_sidebar_brand
from navigation import PAGE_BY_LABEL, render_sidebar_navigation
from theme import apply_custom_theme, apply_minor_ui_fixes, get_native_theme_is_dark


st.set_page_config(
    page_title='Image Analysis Studio',
    page_icon='IA',
    layout='wide',
    initial_sidebar_state='expanded'
)


PAGE_HANDLERS = {
    'Home': lambda: render_home_page(),
    'Library': lambda: render_library_page(),
    'Insights': lambda: render_insights_page(),
    'Settings': lambda: render_settings_page(),
}


def render_home_page():
    st.subheader('Workspace Overview')
    st.write('This standalone project contains only the core dashboard shell: a top bar, a sidebar, and a simple content area.')

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


def render_library_page():
    st.subheader('Library')
    st.write('Use this area for datasets, image collections, or uploaded files.')
    st.info('This is a placeholder page inside the standalone root project.')


def render_insights_page():
    st.subheader('Insights')
    st.write('Use this area for charts, model outputs, or visual review summaries.')
    st.info('Replace this page with your own image-analysis logic when ready.')


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
