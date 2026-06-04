import streamlit as st


def apply_custom_theme(dark_mode_enabled=False):
    if dark_mode_enabled:
        theme_values = {
            'bg': 'radial-gradient(circle at top left, rgba(127, 186, 43, 0.10), transparent 30rem), linear-gradient(180deg, #191837 0%, #11132d 48%, #191837 100%)',
            'text_primary': '#ffffff',
            'text_secondary': '#d7dceb',
            'text_muted': '#b7bed1',
            'green': '#7fba2b',
            'green_dark': '#6fa51f',
            'green_soft': 'rgba(127, 186, 43, 0.16)',
            'card': '#191837',
            'card_soft': 'rgba(25, 24, 55, 0.92)',
            'border': 'rgba(255, 255, 255, 0.16)',
            'border_strong': 'rgba(127, 186, 43, 0.35)',
            'shadow': 'rgba(0, 0, 0, 0.26)',
            'sidebar_background': 'linear-gradient(180deg, #191837 0%, #11132d 56%, #23311a 100%)',
            'sidebar_text': '#ffffff',
            'sidebar_muted': 'rgba(255, 255, 255, 0.72)',
            'sidebar_button': 'rgba(255, 255, 255, 0.08)',
            'sidebar_button_hover': 'rgba(127, 186, 43, 0.18)',
            'hero_bg': 'radial-gradient(circle at 95% 0%, rgba(127, 186, 43, 0.24), transparent 16rem), linear-gradient(135deg, #191837 0%, #11132d 62%, #20331e 100%)',
            'input_bg': '#11132d',
            'input_text': '#ffffff',
            'top_control_bg': 'rgba(25, 24, 55, 0.96)',
            'top_control_icon': '#ffffff',
            'button_bg': '#7fba2b',
            'button_text': '#10151f',
            'button_secondary_bg': 'rgba(255, 255, 255, 0.08)',
            'button_secondary_text': '#ffffff',
            'table_header_bg': '#232447',
            'row_hover': 'rgba(127, 186, 43, 0.10)',
        }
    else:
        theme_values = {
            'bg': 'radial-gradient(circle at top left, rgba(111, 165, 31, 0.14), transparent 30rem), linear-gradient(180deg, #ffffff 0%, #f7f9f5 28%, #f4f7f1 100%)',
            'text_primary': '#191837',
            'text_secondary': '#29284a',
            'text_muted': '#657064',
            'green': '#6fa51f',
            'green_dark': '#4f7d16',
            'green_soft': '#eef7e6',
            'card': '#ffffff',
            'card_soft': 'rgba(255, 255, 255, 0.84)',
            'border': '#dfe8d8',
            'border_strong': 'rgba(111, 165, 31, 0.28)',
            'shadow': 'rgba(25, 24, 55, 0.07)',
            'sidebar_background': 'linear-gradient(180deg, #ffffff 0%, #f7fbf2 24%, #e7f2dc 62%, #6fa51f 100%)',
            'sidebar_text': '#191837',
            'sidebar_muted': 'rgba(25, 24, 55, 0.72)',
            'sidebar_button': 'rgba(255, 255, 255, 0.42)',
            'sidebar_button_hover': 'rgba(255, 255, 255, 0.66)',
            'hero_bg': 'radial-gradient(circle at 95% 0%, rgba(111, 165, 31, 0.28), transparent 16rem), linear-gradient(135deg, #ffffff 0%, #f7fbf2 58%, #edf7e4 100%)',
            'input_bg': '#ffffff',
            'input_text': '#191837',
            'top_control_bg': 'rgba(255, 255, 255, 0.92)',
            'top_control_icon': '#191837',
            'button_bg': '#6fa51f',
            'button_text': '#ffffff',
            'button_secondary_bg': '#f7fbf2',
            'button_secondary_text': '#191837',
            'table_header_bg': '#eef7e6',
            'row_hover': 'rgba(111, 165, 31, 0.08)',
        }

    st.markdown(
        f'''
        <style>
        :root {{
            --biopanda-green: {theme_values['green']};
            --biopanda-green-dark: {theme_values['green_dark']};
            --biopanda-green-soft: {theme_values['green_soft']};
            --biopanda-navy: {theme_values['text_primary']};
            --biopanda-navy-soft: {theme_values['text_secondary']};
            --biopanda-bg: {theme_values['bg']};
            --biopanda-border: {theme_values['border']};
            --biopanda-border-strong: {theme_values['border_strong']};
            --biopanda-muted: {theme_values['text_muted']};
            --biopanda-card: {theme_values['card']};
            --biopanda-card-soft: {theme_values['card_soft']};
            --biopanda-shadow: {theme_values['shadow']};
            --biopanda-sidebar-bg: {theme_values['sidebar_background']};
            --biopanda-sidebar-text: {theme_values['sidebar_text']};
            --biopanda-sidebar-muted: {theme_values['sidebar_muted']};
            --biopanda-sidebar-button: {theme_values['sidebar_button']};
            --biopanda-sidebar-button-hover: {theme_values['sidebar_button_hover']};
            --biopanda-hero-bg: {theme_values['hero_bg']};
            --biopanda-input-bg: {theme_values['input_bg']};
            --biopanda-input-text: {theme_values['input_text']};
            --biopanda-top-control-bg: {theme_values['top_control_bg']};
            --biopanda-top-control-icon: {theme_values['top_control_icon']};
            --biopanda-button-bg: {theme_values['button_bg']};
            --biopanda-button-text: {theme_values['button_text']};
            --biopanda-button-secondary-bg: {theme_values['button_secondary_bg']};
            --biopanda-button-secondary-text: {theme_values['button_secondary_text']};
            --biopanda-table-header-bg: {theme_values['table_header_bg']};
            --biopanda-row-hover: {theme_values['row_hover']};
        }}

        .stApp {{
            background: var(--biopanda-bg);
            color: var(--biopanda-navy);
        }}

        header[data-testid='stHeader'] {{
            background: transparent !important;
            box-shadow: none !important;
        }}

        footer,
        div[data-testid='stDecoration'] {{
            visibility: hidden;
        }}

        #MainMenu,
        div[data-testid='stToolbar'] {{
            visibility: visible !important;
            opacity: 1 !important;
            pointer-events: auto !important;
        }}

        .block-container {{
            padding-top: 1.4rem;
            padding-bottom: 3rem;
            max-width: 1500px;
        }}

        section[data-testid='stSidebar'] {{
            background: var(--biopanda-sidebar-bg);
            border-right: 1px solid var(--biopanda-border-strong);
            box-shadow: 10px 0 30px var(--biopanda-shadow);
        }}

        section[data-testid='stSidebar'] * {{
            color: var(--biopanda-sidebar-text) !important;
        }}

        section[data-testid='stSidebar'] [data-testid='stMarkdownContainer'] p {{
            color: var(--biopanda-sidebar-muted) !important;
        }}

        div[data-testid='stToolbar'] button,
        header[data-testid='stHeader'] button,
        div[data-testid='collapsedControl'] button,
        div[data-testid='stSidebarCollapsedControl'] button,
        button[data-testid='collapsedControl'],
        button[data-testid='stSidebarCollapsedControl'],
        button[aria-label='Open sidebar'],
        button[aria-label='Close sidebar'],
        button[title='Open sidebar'],
        button[title='Close sidebar'],
        button[aria-label='Collapse sidebar'],
        button[title='Collapse sidebar'] {{
            background: var(--biopanda-top-control-bg) !important;
            border: 1px solid var(--biopanda-border-strong) !important;
            border-radius: 999px !important;
            box-shadow: 0 8px 20px var(--biopanda-shadow) !important;
        }}

        div[data-testid='collapsedControl'],
        div[data-testid='stSidebarCollapsedControl'],
        button[data-testid='collapsedControl'],
        button[data-testid='stSidebarCollapsedControl'] {{
            visibility: visible !important;
            display: flex !important;
            opacity: 1 !important;
            z-index: 999999 !important;
            pointer-events: auto !important;
        }}

        div[data-testid='stToolbar'] button svg,
        header[data-testid='stHeader'] button svg,
        div[data-testid='collapsedControl'] svg,
        div[data-testid='stSidebarCollapsedControl'] svg,
        button[data-testid='collapsedControl'] svg,
        button[data-testid='stSidebarCollapsedControl'] svg,
        button[aria-label='Open sidebar'] svg,
        button[aria-label='Close sidebar'] svg,
        button[title='Open sidebar'] svg,
        button[title='Close sidebar'] svg,
        button[aria-label='Collapse sidebar'] svg,
        button[title='Collapse sidebar'] svg {{
            color: var(--biopanda-top-control-icon) !important;
            fill: var(--biopanda-top-control-icon) !important;
            stroke: var(--biopanda-top-control-icon) !important;
        }}

        div[data-testid='stToolbar'] button svg path,
        header[data-testid='stHeader'] button svg path,
        div[data-testid='collapsedControl'] svg path,
        div[data-testid='stSidebarCollapsedControl'] svg path,
        button[data-testid='collapsedControl'] svg path,
        button[data-testid='stSidebarCollapsedControl'] svg path,
        button[aria-label='Open sidebar'] svg path,
        button[aria-label='Close sidebar'] svg path,
        button[title='Open sidebar'] svg path,
        button[title='Close sidebar'] svg path,
        button[aria-label='Collapse sidebar'] svg path,
        button[title='Collapse sidebar'] svg path {{
            fill: var(--biopanda-top-control-icon) !important;
            stroke: var(--biopanda-top-control-icon) !important;
        }}

        .biopanda-sidebar-brand,
        .analysis-sidebar-brand {{
            padding: 0.35rem 0.25rem 0.8rem 0.25rem;
            margin-bottom: 0.55rem;
            border-bottom: 1px solid var(--biopanda-border-strong);
        }}

        .biopanda-sidebar-logo-card,
        .analysis-sidebar-logo-card {{
            background: rgba(255, 255, 255, 0.94);
            border: 1px solid rgba(111, 165, 31, 0.22);
            border-radius: 1rem;
            padding: 0.55rem 0.65rem;
            box-shadow: 0 10px 26px var(--biopanda-shadow);
            margin-bottom: 0.65rem;
        }}

        .biopanda-sidebar-logo-card img,
        .analysis-sidebar-logo-card img {{
            display: block;
            width: 100%;
            height: auto;
            object-fit: contain;
        }}

        .biopanda-sidebar-caption,
        .analysis-sidebar-caption {{
            color: var(--biopanda-sidebar-muted) !important;
            font-size: 0.78rem;
            margin-top: 0.35rem;
            line-height: 1.35;
        }}

        .biopanda-sidebar-nav-title,
        .biopanda-sidebar-section-title,
        .analysis-sidebar-nav-title,
        .analysis-sidebar-section-title {{
            font-size: 0.74rem;
            font-weight: 850;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            margin: 0.85rem 0 0.35rem 0;
        }}

        .biopanda-sidebar-active-page,
        .analysis-sidebar-active-page {{
            background: rgba(255, 255, 255, 0.18);
            border: 1px solid rgba(255, 255, 255, 0.22);
            border-radius: 0.85rem;
            padding: 0.62rem 0.75rem;
            font-weight: 800;
        }}

        .stSidebar [data-testid='stButton'] button {{
            border: 1px solid rgba(255, 255, 255, 0.10) !important;
            background: var(--biopanda-sidebar-button) !important;
            box-shadow: none !important;
            color: var(--biopanda-sidebar-text) !important;
            text-align: left;
            justify-content: flex-start;
        }}

        .stSidebar [data-testid='stButton'] button:hover {{
            background: var(--biopanda-sidebar-button-hover) !important;
            border-color: rgba(255, 255, 255, 0.22) !important;
        }}

        .analysis-hero {{
            position: relative;
            overflow: hidden;
            background: var(--biopanda-hero-bg);
            border: 1px solid var(--biopanda-border);
            border-radius: 0.5rem;
            padding: 1.25rem 1.4rem;
            margin-bottom: 1.25rem;
            box-shadow: 0 18px 45px var(--biopanda-shadow);
        }}

        .analysis-hero:before {{
            display: none;
        }}

        .analysis-hero-title {{
            position: relative;
            color: var(--biopanda-navy);
            font-size: 2rem;
            line-height: 1.12;
            font-weight: 900;
            letter-spacing: -0.045em;
            margin: 0;
        }}

        .analysis-hero-title span {{
            color: var(--biopanda-green);
        }}

        .analysis-hero-kicker {{
            position: relative;
            display: inline-block;
            background: var(--biopanda-green-soft);
            color: var(--biopanda-green-dark);
            border: 1px solid var(--biopanda-border-strong);
            border-radius: 999px;
            padding: 0.2rem 0.6rem;
            font-size: 0.78rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
        }}

        .analysis-hero-subtitle {{
            position: relative;
            color: var(--biopanda-muted);
            max-width: 58rem;
            font-size: 0.98rem;
            line-height: 1.55;
            margin-top: 0.55rem;
            margin-bottom: 0;
        }}

        .analysis-card {{
            background: var(--biopanda-card);
            border: 1px solid var(--biopanda-border);
            border-left: 0.35rem solid var(--biopanda-green);
            border-radius: 0.5rem;
            padding: 1rem;
            box-shadow: 0 10px 26px var(--biopanda-shadow);
            min-height: 7rem;
        }}

        .analysis-card-label {{
            color: var(--biopanda-muted) !important;
            font-size: 0.78rem;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }}

        .analysis-card-value {{
            font-size: 1.9rem;
            font-weight: 900;
            margin-top: 0.2rem;
        }}

        .analysis-card-help {{
            color: var(--biopanda-muted) !important;
            font-size: 0.78rem;
            line-height: 1.35;
            margin-top: 0.35rem;
        }}

        .stApp div[data-testid='stTextInput'],
        .stApp div[data-testid='stNumberInput'],
        .stApp div[data-testid='stDateInput'],
        .stApp div[data-testid='stTextArea'],
        .stApp div[data-testid='stSelectbox'],
        .stApp div[data-testid='stMultiSelect'] {{
            background: transparent !important;
            box-shadow: none !important;
        }}

        .stApp label,
        .stApp p,
        .stApp div[data-testid='stMarkdownContainer'],
        .stApp div[data-testid='stCaptionContainer'] {{
            color: var(--biopanda-navy) !important;
        }}

        .stApp div[data-testid='stCaptionContainer'] *,
        .stApp small {{
            color: var(--biopanda-muted) !important;
        }}

        .stApp input,
        .stApp textarea,
        .stApp [data-baseweb='select'] > div,
        .stApp [data-baseweb='input'] > div,
        .stApp [data-baseweb='textarea'] > div,
        .stApp [data-baseweb='base-input'] {{
            background-color: var(--biopanda-input-bg) !important;
            color: var(--biopanda-input-text) !important;
            border-color: var(--biopanda-border) !important;
        }}

        .stApp [data-baseweb='popover'],
        .stApp [data-baseweb='menu'],
        .stApp [role='listbox'],
        .stApp [role='option'] {{
            background-color: var(--biopanda-card) !important;
            color: var(--biopanda-navy) !important;
            border-color: var(--biopanda-border) !important;
        }}

        .stApp [role='option']:hover {{
            background-color: var(--biopanda-row-hover) !important;
        }}

        .stApp div[data-testid='stMultiSelect'] [data-baseweb='tag'] {{
            background: var(--biopanda-green-soft) !important;
            border: 1px solid var(--biopanda-border-strong) !important;
            border-radius: 0.4rem !important;
            color: var(--biopanda-navy) !important;
            display: inline-flex !important;
            align-items: center !important;
            gap: 0 !important;
            margin-left: 1.35rem !important;
            min-height: 1.55rem !important;
            max-width: 100% !important;
            overflow: visible !important;
            padding: 0.12rem 1.45rem 0.12rem 0.45rem !important;
            position: relative !important;
        }}

        .stApp div[data-testid='stMultiSelect'] [data-baseweb='select']:focus-within [data-baseweb='tag'] {{
            margin-left: 0 !important;
        }}

        .stApp div[data-testid='stMultiSelect'] [data-baseweb='tag'] span,
        .stApp div[data-testid='stMultiSelect'] [data-baseweb='tag'] div:not([role='button']) {{
            color: var(--biopanda-navy) !important;
            display: inline-block !important;
            margin-left: 0 !important;
            min-width: 0 !important;
            overflow: hidden !important;
            padding-left: 0 !important;
            padding-right: 0 !important;
            text-overflow: ellipsis !important;
            white-space: nowrap !important;
            line-height: 1.2 !important;
        }}

        .stApp div[data-testid='stMultiSelect'] [data-baseweb='tag'] button {{
            position: absolute !important;
            left: auto !important;
            right: 0.25rem !important;
            top: 50% !important;
            transform: translateY(-50%) !important;
            width: 1rem !important;
            min-width: 1rem !important;
            height: 1rem !important;
            padding: 0 !important;
            margin: 0 !important;
            border: 0 !important;
            background: transparent !important;
            box-shadow: none !important;
            color: var(--biopanda-navy) !important;
        }}

        .stApp div[data-testid='stMultiSelect'] [data-baseweb='tag'] button svg {{
            display: block !important;
            height: 0.8rem !important;
            width: 0.8rem !important;
        }}

        .stApp button[kind='primary'],
        .stApp div[data-testid='stButton'] button[kind='primary'],
        .stApp div[data-testid='stDownloadButton'] button {{
            background: var(--biopanda-button-bg) !important;
            color: var(--biopanda-button-text) !important;
            border-color: var(--biopanda-button-bg) !important;
        }}

        .stApp div[data-testid='stButton'] button,
        .stApp div[data-testid='stFormSubmitButton'] button {{
            border-radius: 0.5rem !important;
            border-color: var(--biopanda-border) !important;
            background: var(--biopanda-button-secondary-bg) !important;
            color: var(--biopanda-button-secondary-text) !important;
        }}

        .stApp div[data-testid='stButton'] button:hover,
        .stApp div[data-testid='stFormSubmitButton'] button:hover {{
            border-color: var(--biopanda-border-strong) !important;
            background: var(--biopanda-row-hover) !important;
        }}

        .stApp section[data-testid='stSidebar'] div[data-testid='stButton'] {{
            margin-bottom: 0.35rem !important;
        }}

        .stApp section[data-testid='stSidebar'] div[data-testid='stButton'] button {{
            min-height: 2.75rem !important;
            padding: 0.7rem 0.85rem !important;
            border-radius: 0.5rem !important;
            justify-content: flex-start !important;
            text-align: left !important;
            font-size: 0.98rem !important;
            font-weight: 750 !important;
            background: var(--biopanda-sidebar-button) !important;
            border-color: rgba(255, 255, 255, 0.14) !important;
            color: var(--biopanda-sidebar-text) !important;
        }}

        .stApp section[data-testid='stSidebar'] div[data-testid='stButton'] button[kind='primary'] {{
            background: var(--biopanda-button-bg) !important;
            border-color: var(--biopanda-button-bg) !important;
            color: var(--biopanda-button-text) !important;
        }}

        .stApp section[data-testid='stSidebar'] div[data-testid='stButton'] button:hover {{
            background: var(--biopanda-sidebar-button-hover) !important;
            border-color: rgba(255, 255, 255, 0.28) !important;
        }}

        .stApp section[data-testid='stSidebar'] div[data-testid='stButton'] button[kind='primary']:hover {{
            background: var(--biopanda-button-bg) !important;
            border-color: var(--biopanda-button-bg) !important;
            color: var(--biopanda-button-text) !important;
        }}

        .stApp div[data-testid='stFileUploader'] button,
        .stApp div[data-testid='stFileUploader'] button[kind='secondary'] {{
            background: var(--biopanda-button-secondary-bg) !important;
            color: var(--biopanda-button-secondary-text) !important;
            border: 1px solid var(--biopanda-border-strong) !important;
            border-radius: 0.5rem !important;
        }}

        .stApp div[data-testid='stFileUploader'] button *,
        .stApp div[data-testid='stFileUploader'] button span,
        .stApp div[data-testid='stFileUploader'] button p {{
            color: var(--biopanda-button-secondary-text) !important;
        }}

        .stApp div[data-testid='stFileUploader'] button:hover {{
            background: var(--biopanda-row-hover) !important;
            color: var(--biopanda-navy) !important;
        }}

        .stApp input::placeholder,
        .stApp textarea::placeholder {{
            color: var(--biopanda-muted) !important;
            opacity: 0.82 !important;
        }}

        .stApp div[data-testid='stDataFrame'],
        .stApp div[data-testid='stDataEditor'] {{
            border: 1px solid var(--biopanda-border) !important;
            border-radius: 0.5rem !important;
            overflow: hidden !important;
            background: var(--biopanda-card) !important;
        }}

        .stApp div[data-testid='stDataFrame'] *,
        .stApp div[data-testid='stDataEditor'] * {{
            color: var(--biopanda-navy);
        }}

        .stApp [data-testid='stMetric'],
        .stApp [data-testid='stExpander'] {{
            background: var(--biopanda-card) !important;
            border-color: var(--biopanda-border) !important;
            border-radius: 0.5rem !important;
        }}

        .stApp div[data-testid='stAlert'] {{
            border-radius: 0.5rem !important;
            border-color: var(--biopanda-border-strong) !important;
        }}

        .stApp hr {{
            border-color: var(--biopanda-border) !important;
        }}

        .analysis-help-text {{
            color: var(--biopanda-muted) !important;
            font-size: 0.88rem;
            line-height: 1.35;
            margin-bottom: 0.6rem;
        }}

        .analysis-help-text code {{
            color: var(--biopanda-green-dark) !important;
            background: var(--biopanda-green-soft) !important;
            border-radius: 0.25rem;
            padding: 0.05rem 0.25rem;
        }}
        </style>
        ''',
        unsafe_allow_html=True
    )


def apply_minor_ui_fixes():
    return None


def get_native_theme_is_dark():
    try:
        return st.context.theme.type == 'dark'
    except Exception:
        return False
