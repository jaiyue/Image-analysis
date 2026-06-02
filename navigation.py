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
                'name': 'Standard',
                'label': 'Standard',
                'description': 'Standard rule image preview and vertical dark-line detection.'
            },
            {
                'name': 'Results',
                'label': 'Results',
                'description': 'A place for charts, summaries, and model outputs.'
            },
            {
                'name': 'Analysis',
                'label': 'Analysis',
                'description': 'Analysis workspace based on experiment_data.db.'
            },
            {
                'name': 'Review',
                'label': 'Review',
                'description': 'Manual review page with side-by-side image checks and visual score inputs.'
            },
            {
                'name': 'Database',
                'label': 'Database',
                'description': 'View tables from experiment_data.db using a dropdown selector.'
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


def render_sidebar_navigation():
    default_page_label = PAGE_DEFINITIONS[0]['label']

    if 'selected_page_label_radio' not in st.session_state:
        st.session_state.selected_page_label_radio = default_page_label

    if st.session_state.selected_page_label_radio not in PAGE_BY_LABEL:
        st.session_state.selected_page_label_radio = default_page_label

    # Keep canonical selection synced from widget state to avoid
    # two-click updates caused by mixed index/key/session assignments.
    def _sync_selected_page():
        st.session_state.selected_page_label = st.session_state.selected_page_label_radio

    labels = [p['label'] for p in PAGE_DEFINITIONS]
    st.sidebar.radio(
        'Pages',
        options=labels,
        key='selected_page_label_radio',
        on_change=_sync_selected_page,
    )
    st.session_state.selected_page_label = st.session_state.selected_page_label_radio
    return st.session_state.selected_page_label_radio
