import streamlit as st


PAGE_GROUPS = [
    {
        'group': 'Workspace',
        'pages': [
            {
                'name': 'Library',
                'label': 'Library',
                'description': ''
            },
            {
                'name': 'Insights',
                'label': 'Insights',
                'description': 'A place for charts, summaries, and model outputs.'
            }
        ]
    },
    {
        'group': 'Admin',
        'pages': [
            {
                'name': 'Settings',
                'label': 'Settings',
                'description': 'A place for app preferences and UI controls.'
            }
        ]
    }
]


PAGE_DEFINITIONS = [
    page_definition
    for page_group in PAGE_GROUPS
    for page_definition in page_group['pages']
]


PAGE_BY_LABEL = {
    page_definition['label']: page_definition
    for page_definition in PAGE_DEFINITIONS
}


def show_navigation_button(label, page_label, key):
    if st.button(label, key=key, width='stretch'):
        st.session_state.selected_page_label = page_label
        st.rerun()


def render_sidebar_navigation():
    default_page_label = PAGE_DEFINITIONS[0]['label']

    if 'selected_page_label' not in st.session_state:
        st.session_state.selected_page_label = default_page_label

    if st.session_state.selected_page_label not in PAGE_BY_LABEL:
        st.session_state.selected_page_label = default_page_label

    selected_page_label = st.session_state.selected_page_label

    for page_group in PAGE_GROUPS:
        for page_definition in page_group['pages']:
            page_label = page_definition['label']

            if page_label == selected_page_label:
                st.sidebar.markdown(
                    f"<div class='analysis-sidebar-active-page'>{page_label}</div>",
                    unsafe_allow_html=True
                )
            else:
                nav_clicked = st.sidebar.button(
                    page_label,
                    key=f'nav_{page_label.lower().replace(" ", "_")}',
                    width='stretch'
                )

                if nav_clicked:
                    st.session_state.selected_page_label = page_label
                    st.rerun()

    return st.session_state.selected_page_label
