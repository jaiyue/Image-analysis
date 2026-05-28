from pathlib import Path
import sqlite3
from datetime import date
import base64

import pandas as pd
import streamlit as st


DB_PATH = Path(__file__).parent / 'experiment_data.db'
UPLOADS_DB_PATH = Path(__file__).parent / 'uploads.db'
REMOVE_ICON_PATH = Path(__file__).parent / 'assets' / 'remove.png'

AUTO_GENERATED_FIELDS = {
    'experiments': {'experiment_id'},
    'strip_results': {'strip_id', 'user_verified', 'created_at'},
    'image_analysis_results': {'analysis_id', 'analysis_timestamp'},
    'reagent_lots': {'lot_id'},
}

DEFAULT_INPUT_VALUES = {
    ('experiments', 'operator_name'): 'A.Li',
    ('reagent_lots', 'prepared_by'): 'A.Li',
}

UI_HIDDEN_FIELDS = {
    'experiments': {'experiment_date'},
}


def _get_table_names(conn):
    rows = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()
    names = [r[0] for r in rows]
    # Experiment input has been moved to Library page.
    return [n for n in names if n != 'experiments']


def _load_table_df(conn, table_name):
    # table_name comes from sqlite_master query above
    query = f'SELECT * FROM "{table_name}"'
    return pd.read_sql_query(query, conn)


def _get_table_columns(conn, table_name):
    rows = conn.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    columns = []
    for r in rows:
        col_name = r[1]
        col_type = (r[2] or '').upper()
        not_null = bool(r[3])
        default_value = r[4]
        is_pk = bool(r[5])
        columns.append({
            'name': col_name,
            'type': col_type,
            'not_null': not_null,
            'default': default_value,
            'is_pk': is_pk,
        })
    return columns


def _insert_row(conn, table_name, values_by_col):
    cols = list(values_by_col.keys())
    placeholders = ', '.join(['?'] * len(cols))
    cols_sql = ', '.join([f'"{c}"' for c in cols])
    query = f'INSERT INTO "{table_name}" ({cols_sql}) VALUES ({placeholders})'
    conn.execute(query, [values_by_col[c] for c in cols])
    conn.commit()


@st.cache_data(show_spinner=False)
def _read_icon_base64(path_str):
    p = Path(path_str)
    if not p.exists():
        return ''
    return base64.b64encode(p.read_bytes()).decode('ascii')


def _build_remove_button_label():
    icon_b64 = _read_icon_base64(str(REMOVE_ICON_PATH))
    if not icon_b64:
        return 'Delete'
    return f"![remove](data:image/png;base64,{icon_b64})"


def _delete_row_by_pk(conn, table_name, pk_payload):
    if not pk_payload:
        raise ValueError('Primary key not found for delete.')
    where_sql = ' AND '.join([f'"{k}" = ?' for k in pk_payload.keys()])
    query = f'DELETE FROM "{table_name}" WHERE {where_sql}'
    conn.execute(query, list(pk_payload.values()))
    conn.commit()


def _convert_input(raw, col_type):
    text = (raw or '').strip()
    if text == '':
        return None
    if 'INT' in col_type:
        return int(text)
    if any(t in col_type for t in ('REAL', 'FLOA', 'DOUB', 'NUM')):
        return float(text)
    return text


def _is_auto_generated_field(table_name, col):
    if col['name'] in AUTO_GENERATED_FIELDS.get(table_name, set()):
        return True
    if col['is_pk'] and 'INT' in col['type']:
        return True
    return False


def _is_ui_hidden_field(table_name, col):
    return col['name'] in UI_HIDDEN_FIELDS.get(table_name, set())


def _get_default_experiment_date():
    if not UPLOADS_DB_PATH.exists():
        return date.today().isoformat()
    conn = None
    try:
        conn = sqlite3.connect(UPLOADS_DB_PATH)
        row = conn.execute(
            """
            SELECT date
            FROM upload_records
            WHERE date IS NOT NULL
              AND TRIM(date) != ''
            ORDER BY date DESC, time DESC
            LIMIT 1
            """
        ).fetchone()
        if row and row[0]:
            return str(row[0])
    except Exception:
        pass
    finally:
        if conn is not None:
            conn.close()
    return date.today().isoformat()


def render_database_page():
    st.subheader('Database')
    st.markdown(
        """
        <style>
        div[data-testid="stButton"] button:has(img[alt="remove"]) {
            border: none !important;
            background: transparent !important;
            box-shadow: none !important;
            padding: 0 !important;
            min-height: auto !important;
            line-height: 1 !important;
        }
        div[data-testid="stButton"] button:has(img[alt="remove"]):hover {
            background: transparent !important;
        }
        div[data-testid="stButton"] button:has(img[alt="remove"]) img {
            width: 16px !important;
            height: 16px !important;
            display: block !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if not DB_PATH.exists():
        st.warning(f'Database file not found: {DB_PATH.name}')
        return

    try:
        conn = sqlite3.connect(DB_PATH)
    except Exception as e:
        st.error(f'Failed to connect database: {e}')
        return

    try:
        table_names = _get_table_names(conn)
        if not table_names:
            st.info('No tables found in experiment_data.db.')
            return

        selected_table = st.selectbox('Select table', options=table_names, index=0)
        columns = _get_table_columns(conn, selected_table)
        input_columns = [
            c for c in columns
            if not _is_auto_generated_field(selected_table, c)
            and not _is_ui_hidden_field(selected_table, c)
        ]

        st.caption('Input fields (3 per row). Required fields must be not empty.')
        auto_fields = [c['name'] for c in columns if _is_auto_generated_field(selected_table, c)]
        hidden_fields = [c['name'] for c in columns if _is_ui_hidden_field(selected_table, c)]
        if auto_fields:
            st.caption(f'Auto-generated fields (hidden): {", ".join(auto_fields)}')
        if selected_table == 'experiments':
            st.caption(f'Hidden autofill: experiment_date = {_get_default_experiment_date()}')
        elif hidden_fields:
            st.caption(f'UI-hidden fields: {", ".join(hidden_fields)}')
        form_key = f'db_form_{selected_table}'
        with st.form(form_key):
            input_values = {}
            for start in range(0, len(input_columns), 3):
                cols_ui = st.columns(3)
                for offset, col in enumerate(input_columns[start:start + 3]):
                    col_name = col['name']
                    required = col['not_null'] and not (col['is_pk'] and 'INT' in col['type'])
                    label = f"{col_name} ({col['type'] or 'TEXT'})"
                    if required:
                        label += ' *'
                    default_value = DEFAULT_INPUT_VALUES.get((selected_table, col_name), '')
                    placeholder = 'not empty' if required else ''
                    with cols_ui[offset]:
                        input_values[col_name] = st.text_input(
                            label,
                            value=default_value,
                            placeholder=placeholder,
                            key=f'{selected_table}_{col_name}_input',
                        )

            save_col, _, _ = st.columns([1, 1, 1])
            with save_col:
                save_clicked = st.form_submit_button('Save', width='content')

        if save_clicked:
            missing = []
            payload = {}
            convert_errors = []
            for col in input_columns:
                name = col['name']
                raw = input_values.get(name, '')
                required = col['not_null'] and not (col['is_pk'] and 'INT' in col['type'])
                if required and (raw or '').strip() == '':
                    missing.append(name)
                    continue
                try:
                    converted = _convert_input(raw, col['type'])
                except ValueError:
                    convert_errors.append(f'{name} expects {col["type"]}')
                    continue
                if converted is None:
                    continue
                payload[name] = converted

            if selected_table == 'experiments':
                payload['experiment_date'] = _get_default_experiment_date()

            if missing:
                st.error(f'Not empty required: {", ".join(missing)}')
            elif convert_errors:
                st.error('; '.join(convert_errors))
            elif not payload:
                st.error('No input to save.')
            else:
                try:
                    _insert_row(conn, selected_table, payload)
                    st.success('Saved successfully.')
                    st.rerun()
                except Exception as e:
                    st.error(f'Failed to save: {e}')

        df = _load_table_df(conn, selected_table)
        st.caption(f'Table: {selected_table} | Rows: {len(df)}')
        if df.empty:
            st.info('No rows in this table.')
            return

        pk_names = [c['name'] for c in columns if c['is_pk']]
        header_cols = st.columns([1] * len(df.columns) + [0.6])
        for idx, col_name in enumerate(df.columns):
            header_cols[idx].write(col_name)
        header_cols[-1].write('remove')

        remove_label = _build_remove_button_label()
        for row_idx, row in df.iterrows():
            row_cols = st.columns([1] * len(df.columns) + [0.6])
            for col_idx, col_name in enumerate(df.columns):
                val = row[col_name]
                row_cols[col_idx].write('' if pd.isna(val) else str(val))

            pk_payload = {}
            for pk_name in pk_names:
                if pk_name in row.index:
                    pk_payload[pk_name] = row[pk_name]

            with row_cols[-1]:
                if st.button(
                    remove_label,
                    key=f"db_remove_{selected_table}_{row_idx}_{'_'.join([str(pk_payload.get(k, '')) for k in pk_names])}",
                    width='content',
                    type='tertiary',
                ):
                    try:
                        _delete_row_by_pk(conn, selected_table, pk_payload)
                        st.success('Row deleted.')
                        st.rerun()
                    except Exception as e:
                        st.error(f'Failed to delete row: {e}')
    except Exception as e:
        st.error(f'Failed to load table data: {e}')
    finally:
        conn.close()
