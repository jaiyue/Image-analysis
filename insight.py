import streamlit as st
import pandas as pd
import json
from pathlib import Path
from insight_detail import render_insight_detail_page


def render_insights_page():
    detail_id = st.query_params.get('insight_detail_id')
    if detail_id:
        render_insight_detail_page(detail_id)
        return

    st.subheader('Insights')
    uploads_dir = Path(__file__).parent / 'uploads'
    meta_path = uploads_dir / 'meta.json'

    rows = []
    try:
        if meta_path.exists():
            with meta_path.open('r', encoding='utf-8') as f:
                meta = json.load(f)
            for item in meta:
                rows.append({
                    'id': item.get('id'),
                    'c': item.get('c'),
                    't': item.get('t'),
                    'ratio': item.get('ratio'),
                    'date': item.get('date'),
                    'time': item.get('time'),
                })
    except Exception:
        rows = []

    table_df = pd.DataFrame(rows, columns=['id', 'c', 't', 'ratio', 'date', 'time'])
    if not table_df.empty:
        table_df = table_df.sort_values(by=['date', 'time'], ascending=[False, False]).reset_index(drop=True)
        st.session_state['insight_table_cache'] = table_df.copy()
    elif 'insight_table_cache' in st.session_state:
        table_df = st.session_state['insight_table_cache'].copy()

    if table_df.empty:
        st.info('No insight data yet. Process images in Library first.')
        return

    table_df = table_df[['id', 'c', 't', 'ratio', 'date', 'time']]
    csv_bytes = table_df.to_csv(index=False).encode('utf-8')
    st.download_button(
        'Export CSV',
        data=csv_bytes,
        file_name='insights_export.csv',
        mime='text/csv',
        key='insights_export_csv'
    )

    head_cols = st.columns([1, 1, 1, 1, 1, 1, 1])
    headers = ['id', 'c', 't', 'ratio', 'date', 'time', 'detail']
    for i, h in enumerate(headers):
        with head_cols[i]:
            st.markdown(f'**{h}**')

    for _, row in table_df.iterrows():
        row_cols = st.columns([1, 1, 1, 1, 1, 1, 1])
        with row_cols[0]:
            st.write(row['id'])
        with row_cols[1]:
            st.write(row['c'])
        with row_cols[2]:
            st.write(row['t'])
        with row_cols[3]:
            st.write(row['ratio'])
        with row_cols[4]:
            st.write(row['date'])
        with row_cols[5]:
            st.write(row['time'])
        with row_cols[6]:
            if st.button('Detail', key=f"insight_detail_{row['id']}"):
                st.query_params['insight_detail_id'] = str(row['id'])
                st.rerun()
