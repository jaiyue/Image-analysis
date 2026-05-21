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
        }}

        .stApp {{
            background: var(--biopanda-bg);
            color: var(--biopanda-navy);
        }}

        header[data-testid='stHeader'] {{
            background: transparent !important;
            box-shadow: none !important;
        }}

        #MainMenu,
        footer,
        div[data-testid='stDecoration'] {{
            visibility: hidden;
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

        .biopanda-sidebar-brand {{
            padding: 0.35rem 0.25rem 0.8rem 0.25rem;
            margin-bottom: 0.55rem;
            border-bottom: 1px solid var(--biopanda-border-strong);
        }}

        .biopanda-sidebar-logo-card {{
            background: rgba(255, 255, 255, 0.94);
            border: 1px solid rgba(111, 165, 31, 0.22);
            border-radius: 1rem;
            padding: 0.55rem 0.65rem;
            box-shadow: 0 10px 26px var(--biopanda-shadow);
            margin-bottom: 0.65rem;
        }}

        .biopanda-sidebar-logo-card img {{
            display: block;
            width: 100%;
            height: auto;
            object-fit: contain;
        }}

        .biopanda-sidebar-caption {{
            color: var(--biopanda-sidebar-muted) !important;
            font-size: 0.78rem;
            margin-top: 0.35rem;
            line-height: 1.35;
        }}

        .biopanda-sidebar-nav-title,
        .biopanda-sidebar-section-title {{
            font-size: 0.74rem;
            font-weight: 850;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            margin: 0.85rem 0 0.35rem 0;
        }}

        .biopanda-sidebar-active-page {{
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
            border-radius: 1.35rem;
            padding: 1.25rem 1.4rem;
            margin-bottom: 1.25rem;
            box-shadow: 0 18px 45px var(--biopanda-shadow);
        }}

        .analysis-hero:before {{
            content: '';
            position: absolute;
            top: -3rem;
            right: 2.6rem;
            width: 7.8rem;
            height: 13rem;
            border-radius: 4rem;
            background: linear-gradient(180deg, rgba(111, 165, 31, 0.18), rgba(111, 165, 31, 0.04));
            transform: rotate(24deg);
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
            border-radius: 1rem;
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
