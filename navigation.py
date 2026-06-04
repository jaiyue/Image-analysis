import streamlit as st


PAGE_GROUPS = [
    {
        'group': 'Run Experiments',
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
            }
        ]
    },
    {
        'group': 'Review Results',
        'pages': [
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
            }
        ]
    },
    {
        'group': 'Manage Data',
        'pages': [
            {
                'name': 'Database',
                'label': 'Database',
                'description': 'View tables from experiment_data.db using a dropdown selector.'
            },
            {
                'name': 'Backup',
                'label': 'Backup',
                'description': 'Create and restore experiment_data.db backups.'
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


def _set_selected_page(label):
    st.session_state.selected_page_label = label
    st.session_state.selected_page_label_radio = label


def render_sidebar_navigation():
    default_page_label = PAGE_DEFINITIONS[0]['label']

    selected_page = st.session_state.get('selected_page_label', default_page_label)
    if selected_page not in PAGE_BY_LABEL:
        selected_page = default_page_label

    selected = selected_page
    for page_group in PAGE_GROUPS:
        st.sidebar.markdown(
            f"<div class='analysis-sidebar-section-title'>{page_group['group']}</div>",
            unsafe_allow_html=True,
        )
        for page_definition in page_group['pages']:
            label = page_definition['label']
            if st.sidebar.button(
                label,
                key=f'nav_button_{label}',
                type='primary' if label == selected else 'secondary',
                width='stretch',
                on_click=_set_selected_page,
                args=(label,),
            ):
                selected = label

    selected = st.session_state.get('selected_page_label', selected)
    if selected not in PAGE_BY_LABEL:
        selected = default_page_label
    _set_selected_page(selected)
    return selected
