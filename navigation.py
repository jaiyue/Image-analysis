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


def render_sidebar_navigation():
    default_page_label = PAGE_DEFINITIONS[0]['label']

    if 'selected_page_label' not in st.session_state:
        st.session_state.selected_page_label = default_page_label

    if st.session_state.selected_page_label not in PAGE_BY_LABEL:
        st.session_state.selected_page_label = default_page_label

    labels = [p['label'] for p in PAGE_DEFINITIONS]
    selected_idx = labels.index(st.session_state.selected_page_label)
    selected_page_label = st.sidebar.radio(
        'Pages',
        options=labels,
        index=selected_idx,
        key='selected_page_label_radio'
    )
    st.session_state.selected_page_label = selected_page_label
    return selected_page_label
