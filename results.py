import streamlit as st
import pandas as pd
import base64
import sqlite3
import io
from pathlib import Path
from result_detail import render_insight_detail_page
from uploads_db import init_uploads_db, list_insight_rows, set_starred_status
from ui_labels import display_label
from database import DB_PATH


ASSETS_DIR = Path(__file__).parent / 'assets'
STAR_ICON_PATH = ASSETS_DIR / 'star.png'
YELLOW_STAR_ICON_PATH = ASSETS_DIR / 'yellow_star.png'

def _sort_by_id_desc(df):
    if df.empty or 'id' not in df.columns:
        return df
    out = df.copy()
    out['_id_num'] = pd.to_numeric(out['id'], errors='coerce')
    out = out.sort_values(
        by=['_id_num', 'id'],
        ascending=[False, False],
        na_position='last',
    ).drop(columns=['_id_num'])
    return out.reset_index(drop=True)


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


def _assign_ratio_groups(df, threshold=0.2):
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


def _experiment_group_color(experiment_id):
    palette = [
        '#1f77b4', '#2ca02c', '#d62728', '#ff7f0e', '#9467bd',
        '#17becf', '#bcbd22', '#8c564b', '#e377c2', '#7f7f7f',
    ]
    if experiment_id is None or pd.isna(experiment_id):
        return '#333333'
    try:
        idx = int(experiment_id)
    except Exception:
        idx = abs(hash(str(experiment_id)))
    return palette[idx % len(palette)]


def _fmt4(v):
    if v is None or pd.isna(v):
        return ''
    try:
        return f'{float(v):.4f}'
    except Exception:
        return str(v)


def _fmt_date_simple(v):
    if v is None or pd.isna(v):
        return 'None'
    dt = pd.to_datetime(v, errors='coerce')
    if pd.notna(dt):
        return f"{dt.strftime('%b')} {int(dt.day)}"
    return 'None'


def _fmt_time_simple(v):
    if v is None or pd.isna(v):
        return 'None'
    text = str(v).strip()
    return text if text else 'None'


def _display_label(text):
    return display_label(text)


def _build_changed_specific_export_tables(filtered_df):
    strip_ids = [str(x) for x in filtered_df['id'].tolist()]
    if not strip_ids:
        return pd.DataFrame(), pd.DataFrame()

    conn = sqlite3.connect(DB_PATH)
    try:
        placeholders = ','.join(['?'] * len(strip_ids))

        strip_df = pd.read_sql_query(
            f'SELECT * FROM strip_results WHERE strip_id IN ({placeholders})',
            conn,
            params=strip_ids,
        )

        strip_df['strip_id'] = strip_df['strip_id'].astype(str)

        order_df = pd.DataFrame({'strip_id': strip_ids})
        merged = order_df.merge(strip_df, on='strip_id', how='left')

        ordered_cols = ['strip_id', 'experiment_id'] + [
            c for c in strip_df.columns if c not in ('strip_id', 'experiment_id')
        ]
        merged = merged[[c for c in ordered_cols if c in merged.columns]]

        exp_df = pd.DataFrame()
        if 'experiment_id' in strip_df.columns:
            exp_ids = [int(x) for x in strip_df['experiment_id'].dropna().unique().tolist()]
            if exp_ids:
                exp_ph = ','.join(['?'] * len(exp_ids))
                exp_df = pd.read_sql_query(
                    f'SELECT * FROM experiments WHERE experiment_id IN ({exp_ph}) ORDER BY experiment_id',
                    conn,
                    params=exp_ids,
                )
    finally:
        conn.close()

    return exp_df, merged


def render_insights_page():
    detail_id = st.query_params.get('insight_detail_id')
    if detail_id:
        render_insight_detail_page(detail_id)
        return

    st.subheader('Results')
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

    table_df = pd.DataFrame(
        rows,
        columns=['id', 'experiment_id', 'c', 't', 'bg', 'ratio', 'ct_bg_sum', 'date', 'time', 'starred', 'experiment_title', 'experiment_condition', 'changed_field', 'changed_value'],
    )
    if not table_df.empty:
        table_df = _sort_by_id_desc(table_df)
        st.session_state['insight_table_cache'] = table_df.copy()
    elif 'insight_table_cache' in st.session_state:
        table_df = st.session_state['insight_table_cache'].copy()

    if 'changed_field' not in table_df.columns:
        table_df['changed_field'] = None
    if 'changed_value' not in table_df.columns:
        table_df['changed_value'] = None
    if 'experiment_id' not in table_df.columns:
        table_df['experiment_id'] = None
    if 'experiment_title' not in table_df.columns:
        table_df['experiment_title'] = None
    if 'experiment_condition' not in table_df.columns:
        table_df['experiment_condition'] = None

    if table_df.empty:
        st.info('No insight data yet. Process images in Library first.')
        return

    results_state_key = 'results_persisted_filter_state'
    results_restore_key = 'results_restore_filter_state'
    if st.session_state.get(results_restore_key):
        persisted_state = st.session_state.get(results_state_key, {})
        if isinstance(persisted_state, dict):
            for key, value in persisted_state.items():
                st.session_state[key] = value
        st.session_state[results_restore_key] = False

    table_df['raw_c'] = pd.to_numeric(table_df['c'], errors='coerce')
    table_df['raw_t'] = pd.to_numeric(table_df['t'], errors='coerce')
    table_df['bg_num'] = pd.to_numeric(table_df['bg'], errors='coerce')
    table_df['correct_c'] = table_df['raw_c'] - table_df['bg_num']
    table_df['correct_t'] = table_df['raw_t'] - table_df['bg_num']
    table_df['reference_test_ratio'] = pd.to_numeric(table_df['ratio'], errors='coerce').apply(
        lambda x: (1.0 / x) if pd.notna(x) and abs(float(x)) > 1e-12 else None
    )

    st.caption('Ratio is the normalized T/R metric. Corrected total helps distinguish strips with similar ratios but different absolute color intensity.')

    filter_cols = st.columns([1.6, 2.0, 2.0, 1.3, 1.4])
    if 'results_filter_id_keyword' not in st.session_state:
        st.session_state['results_filter_id_keyword'] = ''
    id_keyword = filter_cols[0].text_input(
        'Filter ID',
        key='results_filter_id_keyword',
        placeholder='e.g. 00001',
    )
    experiment_title_options = ['All']
    try:
        title_values = sorted(
            {
                str(x).strip()
                for x in table_df['experiment_title'].tolist()
                if x is not None and str(x).strip() != ''
            }
        )
        experiment_title_options.extend(title_values)
    except Exception:
        pass
    if 'results_experiment_title_filter' not in st.session_state:
        st.session_state['results_experiment_title_filter'] = 'All'
    if st.session_state['results_experiment_title_filter'] not in experiment_title_options:
        st.session_state['results_experiment_title_filter'] = 'All'
    experiment_title_filter = filter_cols[1].selectbox(
        'Experiment title',
        options=experiment_title_options,
        key='results_experiment_title_filter',
    )
    changed_options = ['Full']
    try:
        condition_values = sorted(
            {
                str(x).strip()
                for x in table_df['experiment_condition'].tolist()
                if x is not None and str(x).strip() != ''
            }
        )
        changed_options.extend(condition_values)
    except Exception:
        pass
    if 'results_changed_filter' not in st.session_state:
        st.session_state['results_changed_filter'] = 'Full'
    if st.session_state['results_changed_filter'] not in changed_options:
        st.session_state['results_changed_filter'] = 'Full'
    changed_filter = filter_cols[2].selectbox(
        'Changed variable',
        options=changed_options,
        key='results_changed_filter',
        format_func=lambda x: x if x == 'Full' else _display_label(x),
    )
    if 'results_ratio_bucket' not in st.session_state:
        st.session_state['results_ratio_bucket'] = 'Full'
    ratio_bucket_options = ['0-0.9', '0.9-1.1', '1.1+', 'Full']
    if st.session_state['results_ratio_bucket'] not in ratio_bucket_options:
        st.session_state['results_ratio_bucket'] = 'Full'
    ratio_bucket = filter_cols[3].selectbox(
        'Ratio range',
        ratio_bucket_options,
        key='results_ratio_bucket',
    )

    date_series = pd.to_datetime(table_df['date'], errors='coerce').dropna()
    if not date_series.empty:
        default_min = date_series.min().date()
        default_max = date_series.max().date()
    else:
        default_min = None
        default_max = None
    date_range_key = 'results_date_range'
    if date_range_key not in st.session_state:
        st.session_state[date_range_key] = (default_min, default_max) if default_min and default_max else (None, None)
    date_range = filter_cols[4].date_input(
        'Date range',
        key=date_range_key,
    )

    option_cols = st.columns([1.2, 1.4, 1.5, 2.1])
    if 'results_star_only' not in st.session_state:
        st.session_state['results_star_only'] = False
    if 'results_ratio_grouping' not in st.session_state:
        st.session_state['results_ratio_grouping'] = False
    if 'results_experiment_grouping' not in st.session_state:
        st.session_state['results_experiment_grouping'] = True
    star_only = option_cols[0].checkbox('Starred only', key='results_star_only')
    ratio_grouping = option_cols[1].checkbox('Group similar ratio', key='results_ratio_grouping')
    experiment_grouping = option_cols[2].checkbox('Group by experiment', key='results_experiment_grouping')

    st.session_state[results_state_key] = {
        'results_filter_id_keyword': id_keyword,
        'results_experiment_title_filter': experiment_title_filter,
        'results_changed_filter': changed_filter,
        'results_ratio_bucket': ratio_bucket,
        'results_date_range': date_range,
        'results_star_only': star_only,
        'results_ratio_grouping': ratio_grouping,
        'results_experiment_grouping': experiment_grouping,
    }

    filtered_df = table_df.copy()
    if id_keyword.strip():
        filtered_df = filtered_df[filtered_df['id'].astype(str).str.contains(id_keyword.strip(), case=False, na=False)]
    if experiment_title_filter != 'All':
        filtered_df = filtered_df[filtered_df['experiment_title'].astype(str) == experiment_title_filter]
    if changed_filter != 'Full':
        filtered_df = filtered_df[filtered_df['experiment_condition'].astype(str) == changed_filter]
    if star_only:
        filtered_df = filtered_df[filtered_df['starred'].astype(bool)]
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
        if start_date is not None and end_date is not None:
            d = pd.to_datetime(filtered_df['date'], errors='coerce').dt.date
            in_range = (d >= start_date) & (d <= end_date)
            filtered_df = filtered_df[in_range | d.isna()]

    filtered_df['ratio_num'] = pd.to_numeric(filtered_df['ratio'], errors='coerce')
    if ratio_bucket == '0-0.9':
        filtered_df = filtered_df[
            filtered_df['ratio_num'].isna()
            | ((filtered_df['ratio_num'] >= 0.0) & (filtered_df['ratio_num'] < 0.9))
        ]
    elif ratio_bucket == '0.9-1.1':
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
        filtered_df = _assign_ratio_groups(filtered_df, threshold=0.2)
        filtered_df = filtered_df.sort_values(
            by=['ratio_group', 'ratio_num', 'date', 'time'],
            ascending=[True, True, False, False],
            na_position='last',
        ).reset_index(drop=True)
    else:
        filtered_df['ratio_group'] = None
        filtered_df = _sort_by_id_desc(filtered_df)

    if changed_filter == 'Full':
        export_df = pd.DataFrame({
            'star': filtered_df['starred'].astype(int),
            'id': filtered_df['id'].astype(str),
            'reference_line_corrected_intensity': filtered_df['correct_c'].apply(_fmt4),
            'test_line_corrected_intensity': filtered_df['correct_t'].apply(_fmt4),
            'bg': filtered_df['bg_num'].apply(_fmt4),
            'test_reference_ratio': filtered_df['ratio'].apply(_fmt4),
            '(c-bg)+(t-bg)': filtered_df['ct_bg_sum'].apply(_fmt4),
            'date': filtered_df['date'].apply(_fmt_date_simple),
        })
        csv_bytes = export_df.to_csv(index=False).encode('utf-8')
        export_name = 'insights_export.csv'
        export_mime = 'text/csv'
        export_label = 'Export CSV'
    else:
        exp_df, strip_df = _build_changed_specific_export_tables(filtered_df)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            exp_df.to_excel(writer, index=False, sheet_name='experiment')
            strip_df.to_excel(writer, index=False, sheet_name='strip')
        csv_bytes = output.getvalue()
        export_name = 'insights_export.xlsx'
        export_mime = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        export_label = 'Export Excel'
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
        export_label,
        data=csv_bytes,
        file_name=export_name,
        mime=export_mime,
        key='insights_export_csv'
    )

    if filtered_df.empty:
        st.info('No records matched current filters.')
        return

    head_cols = st.columns([0.70, 0.95, 1.5, 1.5, 0.95, 1.3, 1.3, 0.9, 1.20])
    headers = [
        'Star',
        'Image ID',
        'Reference corrected',
        'Test corrected',
        'Background',
        'T/R ratio',
        'Corrected total',
        'Date',
        'Detail',
    ]
    for i, h in enumerate(headers):
        with head_cols[i]:
            st.write(h)

    for _, row in filtered_df.iterrows():
        row_cols = st.columns([0.70, 0.95, 1.5, 1.5, 0.95, 1.3, 1.3, 0.9, 1.20])
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
            if experiment_grouping:
                id_color = _experiment_group_color(row.get('experiment_id'))
            else:
                id_color = _ratio_group_color(row.get('ratio_group'))
            st.markdown(
                f"<span style='color:{id_color};font-weight:400'>{row['id']}</span>",
                unsafe_allow_html=True,
            )
        with row_cols[2]:
            st.write(_fmt4(row.get('correct_c')))
        with row_cols[3]:
            st.write(_fmt4(row.get('correct_t')))
        with row_cols[4]:
            st.write(_fmt4(row.get('bg_num')))
        with row_cols[5]:
            st.write(_fmt4(row.get('ratio')))
        with row_cols[6]:
            st.write(_fmt4(row.get('ct_bg_sum')))
        with row_cols[7]:
            st.write(_fmt_date_simple(row.get('date')))
        with row_cols[8]:
            if st.button('Detail', key=f"insight_detail_{row['id']}"):
                st.session_state[results_restore_key] = True
                st.query_params['insight_detail_id'] = str(row['id'])
                st.rerun()
