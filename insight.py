import streamlit as st
import pandas as pd
import base64
from pathlib import Path
from insight_detail import render_insight_detail_page
from uploads_db import init_uploads_db, list_insight_rows, set_starred_status


ASSETS_DIR = Path(__file__).parent / 'assets'
STAR_ICON_PATH = ASSETS_DIR / 'star.png'
YELLOW_STAR_ICON_PATH = ASSETS_DIR / 'yellow_star.png'


@st.cache_data(show_spinner=False)
def _read_icon_base64(path_str):
    p = Path(path_str)
    if not p.exists():
        return ''
    return base64.b64encode(p.read_bytes()).decode('ascii')


def _build_star_button_label(starred):
    icon_path = YELLOW_STAR_ICON_PATH if starred else STAR_ICON_PATH
    icon_b64 = _read_icon_base64(str(icon_path))
    if not icon_b64:
        return '⭐' if starred else '☆'
    return f"![star](data:image/png;base64,{icon_b64})"


def _assign_ratio_groups(df, threshold=0.1):
    if df.empty:
        out = df.copy()
        out['ratio_group'] = None
        return out

    out = df.copy()
    out['ratio_num'] = pd.to_numeric(out['ratio'], errors='coerce')
    sortable = out.dropna(subset=['ratio_num']).sort_values(by='ratio_num').copy()

    group_ids = []
    current_group = -1
    group_anchor = None
    for ratio in sortable['ratio_num'].tolist():
        if group_anchor is None or abs(ratio - group_anchor) >= threshold:
            current_group += 1
            group_anchor = ratio
        group_ids.append(current_group)

    sortable['ratio_group'] = group_ids
    group_sizes = sortable.groupby('ratio_group')['id'].transform('count')
    sortable.loc[group_sizes < 2, 'ratio_group'] = None
    out = out.merge(
        sortable[['id', 'ratio_group']],
        on='id',
        how='left',
    )
    return out


def _ratio_group_color(group_id):
    palette = [
        '#1f77b4', '#2ca02c', '#d62728', '#ff7f0e', '#9467bd',
        '#17becf', '#bcbd22', '#8c564b', '#e377c2', '#7f7f7f',
    ]
    if group_id is None or pd.isna(group_id):
        return '#333333'
    return palette[int(group_id) % len(palette)]


def render_insights_page():
    detail_id = st.query_params.get('insight_detail_id')
    if detail_id:
        render_insight_detail_page(detail_id)
        return

    st.subheader('Insights')
    init_uploads_db()
    st.markdown(
        """
        <style>
        div[data-testid="stButton"] button:has(img[alt="star"]) {
            border: none !important;
            background: transparent !important;
            box-shadow: none !important;
            padding: 0 !important;
            min-height: auto !important;
            line-height: 1 !important;
        }
        div[data-testid="stButton"] button:has(img[alt="star"]):hover {
            background: transparent !important;
        }
        div[data-testid="stButton"] button:has(img[alt="star"]) img {
            width: 20px !important;
            height: 20px !important;
            display: block !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    rows = []
    try:
        rows = list_insight_rows()
    except Exception:
        rows = []

    table_df = pd.DataFrame(rows, columns=['id', 'c', 't', 'ratio', 'ct_bg_sum', 'date', 'time', 'starred'])
    if not table_df.empty:
        table_df = table_df.sort_values(by=['date', 'time'], ascending=[False, False]).reset_index(drop=True)
        st.session_state['insight_table_cache'] = table_df.copy()
    elif 'insight_table_cache' in st.session_state:
        table_df = st.session_state['insight_table_cache'].copy()

    if table_df.empty:
        st.info('No insight data yet. Process images in Library first.')
        return

    st.caption('Note: `ratio` is the normalized T/C metric; `(c-bg)+(t-bg)` helps distinguish strips with similar ratio but different absolute color intensity.')

    filter_cols = st.columns([1.8, 1.4, 1.4])
    id_keyword = filter_cols[0].text_input('Filter ID', value='', placeholder='e.g. 00001')
    ratio_bucket = filter_cols[1].selectbox('Ratio range', ['0~0.9', '0.9~1.1', '1.1+', 'Full'], index=3)

    date_series = pd.to_datetime(table_df['date'], errors='coerce').dropna()
    if not date_series.empty:
        default_min = date_series.min().date()
        default_max = date_series.max().date()
    else:
        default_min = None
        default_max = None
    if default_min and default_max:
        date_range = filter_cols[2].date_input(
            'Date range',
            value=(default_min, default_max),
        )
    else:
        date_range = (None, None)

    option_cols = st.columns([1.2, 1.2, 2.6])
    star_only = option_cols[0].checkbox('Starred only', value=False)
    ratio_grouping = option_cols[1].checkbox('Group similar ratio', value=True)

    filtered_df = table_df.copy()
    if id_keyword.strip():
        filtered_df = filtered_df[filtered_df['id'].astype(str).str.contains(id_keyword.strip(), case=False, na=False)]
    if star_only:
        filtered_df = filtered_df[filtered_df['starred'].astype(bool)]
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
        if start_date is not None and end_date is not None:
            d = pd.to_datetime(filtered_df['date'], errors='coerce').dt.date
            filtered_df = filtered_df[(d >= start_date) & (d <= end_date)]

    filtered_df['ratio_num'] = pd.to_numeric(filtered_df['ratio'], errors='coerce')
    if ratio_bucket == '0~0.9':
        filtered_df = filtered_df[
            filtered_df['ratio_num'].isna()
            | ((filtered_df['ratio_num'] >= 0.0) & (filtered_df['ratio_num'] < 0.9))
        ]
    elif ratio_bucket == '0.9~1.1':
        filtered_df = filtered_df[
            filtered_df['ratio_num'].isna()
            | ((filtered_df['ratio_num'] >= 0.9) & (filtered_df['ratio_num'] <= 1.1))
        ]
    elif ratio_bucket == '1.1+':
        filtered_df = filtered_df[
            filtered_df['ratio_num'].isna()
            | (filtered_df['ratio_num'] > 1.1)
        ]
    else:
        # Full: do not filter by ratio bucket
        filtered_df = filtered_df

    if ratio_grouping:
        filtered_df = _assign_ratio_groups(filtered_df, threshold=0.1)
        filtered_df = filtered_df.sort_values(
            by=['ratio_group', 'ratio_num', 'date', 'time'],
            ascending=[True, True, False, False],
            na_position='last',
        ).reset_index(drop=True)
    else:
        filtered_df['ratio_group'] = None
        filtered_df = filtered_df.sort_values(
            by=['date', 'time'],
            ascending=[False, False],
        ).reset_index(drop=True)

    export_df = filtered_df[['id', 'c', 't', 'ratio', 'ct_bg_sum', 'date', 'time', 'starred']]
    csv_bytes = export_df.to_csv(index=False).encode('utf-8')
    st.markdown(
        """
        <style>
        div[data-testid="stDownloadButton"] {
            position: fixed;
            right: 20px;
            bottom: 20px;
            z-index: 1000;
            margin: 0;
        }
        div[data-testid="stDownloadButton"] > button {
            border-radius: 999px;
            box-shadow: 0 8px 20px rgba(0, 0, 0, 0.20);
            padding: 0.5rem 0.9rem;
        }
        @media (max-width: 768px) {
            div[data-testid="stDownloadButton"] {
                right: 12px;
                bottom: 12px;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.download_button(
        'Export CSV',
        data=csv_bytes,
        file_name='insights_export.csv',
        mime='text/csv',
        key='insights_export_csv'
    )

    if filtered_df.empty:
        st.info('No records matched current filters.')
        return

    head_cols = st.columns([0.8, 1, 1, 1, 1, 1.3, 1, 1, 1])
    headers = ['star', 'id', 'c', 't', 'ratio', '(c-bg)+(t-bg)', 'date', 'time', 'detail']
    for i, h in enumerate(headers):
        with head_cols[i]:
            st.write(h)

    for _, row in filtered_df.iterrows():
        row_cols = st.columns([0.8, 1, 1, 1, 1, 1.3, 1, 1, 1])
        with row_cols[0]:
            is_starred = bool(row.get('starred'))
            if st.button(
                _build_star_button_label(is_starred),
                key=f"insight_star_{row['id']}",
                width='content',
                type='tertiary',
            ):
                set_starred_status(row['id'], not is_starred)
                st.rerun()
        with row_cols[1]:
            id_color = _ratio_group_color(row.get('ratio_group'))
            st.markdown(
                f"<span style='color:{id_color};font-weight:400'>{row['id']}</span>",
                unsafe_allow_html=True,
            )
        with row_cols[2]:
            st.write(row['c'])
        with row_cols[3]:
            st.write(row['t'])
        with row_cols[4]:
            st.write(row['ratio'])
        with row_cols[5]:
            st.write(row['ct_bg_sum'])
        with row_cols[6]:
            st.write(row['date'])
        with row_cols[7]:
            st.write(row['time'])
        with row_cols[8]:
            if st.button('Detail', key=f"insight_detail_{row['id']}"):
                st.query_params['insight_detail_id'] = str(row['id'])
                st.rerun()
