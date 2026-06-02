from pathlib import Path
import sqlite3
import base64
import json

import pandas as pd
import streamlit as st


DB_PATH = Path(__file__).parent / 'experiment_data.db'
REMOVE_ICON_PATH = Path(__file__).parent / 'assets' / 'remove.png'
SCHEMA_PATH = Path(__file__).parent / 'experiment_schema.sql'

REAGENT_TYPE_OPTIONS = [
    'sample_pad_pretreatment_lot',
    'conjugate_pad_pretreatment_lot',
    'running_buffer_lot',
    'glide_buffer_lot',
    'reconstitution_buffer_lot',
    'gnp_lot',
]

def _display_label(text):
    return str(text).replace('_', ' ')

PAD_TYPE_OPTIONS = [
    'nitrocellulose_material',
    'sample_pad_material',
    'conjugate_pad_material',
    'absorbent_pad_material',
]


def _table_display_name(table_name):
    if table_name == 'reagent_lots':
        return 'reagent lots'
    if table_name == 'pad_material':
        return 'material'
    if table_name == 'conjugate_batch':
        return 'conjugate batch'
    return _display_label(table_name)


def _column_display_name(table_name, col_name):
    if table_name == 'pad_material' and col_name == 'pad_name':
        return 'name'
    return _display_label(col_name)

AUTO_GENERATED_FIELDS = {
    'experiments': {'experiment_id'},
    'strip_results': {'strip_id'},
    'reagent_lots': {'lot_id'},
    'pad_material': {'pad_id'},
    'conjugate_batch': {'id'},
}

DEFAULT_INPUT_VALUES = {
    ('experiments', 'operator'): 'A.Li',
    ('reagent_lots', 'prepared_by'): 'A.Li',
    ('pad_material', 'prepared_by'): 'A.Li',
}

UI_HIDDEN_FIELDS = {
    'reagent_lots': {'lot_id', 'prepared_by'},
    'pad_material': {'pad_id', 'prepared_by'},
    'conjugate_batch': {'id'},
}


def _table_exists(conn, table_name):
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None


@st.cache_data(show_spinner=False)
def _load_schema_metadata(schema_path_str, schema_mtime_ns):
    schema_path = Path(schema_path_str)
    if not schema_path.exists():
        return {'columns': {}, 'foreign_keys': {}}

    mem = sqlite3.connect(':memory:')
    mem.row_factory = sqlite3.Row
    try:
        script = schema_path.read_text(encoding='utf-8')
        mem.executescript(script)
        table_rows = mem.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            """
        ).fetchall()
        tables = [r['name'] for r in table_rows]

        columns_by_table = {}
        fks_by_table = {}
        for table_name in tables:
            col_rows = mem.execute(f'PRAGMA table_info("{table_name}")').fetchall()
            col_defs = []
            for r in col_rows:
                parts = [r['type'] or 'TEXT']
                if int(r['notnull']):
                    parts.append('NOT NULL')
                if r['dflt_value'] is not None:
                    parts.append(f"DEFAULT {r['dflt_value']}")
                if int(r['pk']):
                    parts.append('PRIMARY KEY')
                col_defs.append((r['name'], ' '.join(parts)))
            columns_by_table[table_name] = col_defs

            fk_rows = mem.execute(f'PRAGMA foreign_key_list("{table_name}")').fetchall()
            grouped = {}
            for r in fk_rows:
                fid = int(r['id'])
                grouped.setdefault(fid, []).append(r)
            fk_defs = []
            for fid in sorted(grouped.keys()):
                rows = sorted(grouped[fid], key=lambda x: int(x['seq']))
                from_cols = ', '.join([f'"{x["from"]}"' for x in rows])
                ref_table = rows[0]['table']
                to_cols = ', '.join([f'"{x["to"]}"' for x in rows])
                clause = f'FOREIGN KEY ({from_cols}) REFERENCES "{ref_table}"({to_cols})'
                on_update = (rows[0]['on_update'] or '').upper()
                on_delete = (rows[0]['on_delete'] or '').upper()
                if on_update and on_update != 'NO ACTION':
                    clause += f' ON UPDATE {on_update}'
                if on_delete and on_delete != 'NO ACTION':
                    clause += f' ON DELETE {on_delete}'
                fk_defs.append(clause)
            fks_by_table[table_name] = fk_defs

        return {'columns': columns_by_table, 'foreign_keys': fks_by_table}
    finally:
        mem.close()


def _schema_columns(table_name):
    mtime_ns = SCHEMA_PATH.stat().st_mtime_ns if SCHEMA_PATH.exists() else 0
    meta = _load_schema_metadata(str(SCHEMA_PATH), mtime_ns)
    return meta.get('columns', {}).get(table_name, [])


def _schema_foreign_keys(table_name):
    mtime_ns = SCHEMA_PATH.stat().st_mtime_ns if SCHEMA_PATH.exists() else 0
    meta = _load_schema_metadata(str(SCHEMA_PATH), mtime_ns)
    return meta.get('foreign_keys', {}).get(table_name, [])


def _next_prefixed_id(conn, table_name, id_col, prefix, min_width=2):
    rows = conn.execute(f'SELECT "{id_col}" FROM "{table_name}"').fetchall()
    max_n = 0
    for r in rows:
        raw = r[0]
        if raw is None:
            continue
        text = str(raw).strip()
        if not text.startswith(prefix):
            continue
        suffix = text[len(prefix):]
        if suffix.isdigit():
            n = int(suffix)
            if n > max_n:
                max_n = n
    next_n = max_n + 1
    return f'{prefix}{next_n:0{min_width}d}'


def _ensure_table_schema(conn, table_name, columns, foreign_keys=None, force_rebuild=False):
    if not columns:
        return
    desired_names = [c[0] for c in columns]
    if not _table_exists(conn, table_name):
        col_sql = [f'{name} {typ}' for name, typ in columns]
        fk_sql = foreign_keys or []
        conn.execute(f'CREATE TABLE {table_name} (\n    ' + ',\n    '.join(col_sql + fk_sql) + '\n)')
        return

    existing_cols = conn.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    existing_names = [r[1] for r in existing_cols]
    if existing_names == desired_names and not force_rebuild:
        return

    old_name = f'{table_name}_old'
    conn.execute(f'ALTER TABLE {table_name} RENAME TO {old_name}')
    col_sql = [f'{name} {typ}' for name, typ in columns]
    fk_sql = foreign_keys or []
    conn.execute(f'CREATE TABLE {table_name} (\n    ' + ',\n    '.join(col_sql + fk_sql) + '\n)')

    common = [n for n in desired_names if n in existing_names]
    if common:
        cols_join = ', '.join([f'"{c}"' for c in common])
        conn.execute(
            f"""
            INSERT INTO {table_name} ({cols_join})
            SELECT {cols_join}
            FROM {old_name}
            """
        )
    conn.execute(f'DROP TABLE {old_name}')


def _ensure_table_columns_additive(conn, table_name, columns):
    if not columns:
        return
    if not _table_exists(conn, table_name):
        col_sql = [f'{name} {typ}' for name, typ in columns]
        conn.execute(f'CREATE TABLE {table_name} (\n    ' + ',\n    '.join(col_sql) + '\n)')
        return

    existing_cols = conn.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    existing_names = {r[1] for r in existing_cols}
    for name, typ in columns:
        if name in existing_names:
            continue
        # SQLite ADD COLUMN cannot add PRIMARY KEY/UNIQUE constraints; skip such additions.
        if 'PRIMARY KEY' in typ.upper() or 'UNIQUE' in typ.upper():
            continue
        conn.execute(f'ALTER TABLE "{table_name}" ADD COLUMN "{name}" {typ}')


def _rebuild_experiments_with_schema_order(conn):
    if not _table_exists(conn, 'experiments'):
        return

    desired_cols = _schema_columns('experiments')
    if not desired_cols:
        return
    desired_names = [c[0] for c in desired_cols]

    existing_cols = conn.execute('PRAGMA table_info("experiments")').fetchall()
    existing_names = [r[1] for r in existing_cols]
    extra_names = [n for n in existing_names if n not in desired_names]
    target_names = desired_names + extra_names
    if existing_names == target_names:
        return

    col_defs = list(desired_cols)
    existing_map = {r[1]: r for r in existing_cols}
    for name in extra_names:
        r = existing_map.get(name)
        if not r:
            continue
        parts = [r[2] or 'TEXT']
        if int(r[3]):
            parts.append('NOT NULL')
        if r[4] is not None:
            parts.append(f'DEFAULT {r[4]}')
        if int(r[5]):
            parts.append('PRIMARY KEY')
        col_defs.append((name, ' '.join(parts)))

    col_sql = [f'{name} {typ}' for name, typ in col_defs]
    conn.execute('CREATE TABLE experiments_new (\n    ' + ',\n    '.join(col_sql) + '\n)')

    common = [n for n in target_names if n in existing_names]
    if common:
        cols_join = ', '.join([f'"{c}"' for c in common])
        conn.execute(
            f'''
            INSERT INTO experiments_new ({cols_join})
            SELECT {cols_join}
            FROM experiments
            '''
        )

    conn.execute('DROP TABLE experiments')
    conn.execute('ALTER TABLE experiments_new RENAME TO experiments')


def _has_expected_fk(conn, table_name, from_col, ref_table, ref_col):
    if not _table_exists(conn, table_name):
        return False
    rows = conn.execute(f'PRAGMA foreign_key_list("{table_name}")').fetchall()
    for r in rows:
        if str(r[3]) == from_col and str(r[2]) == ref_table and str(r[4]) == ref_col:
            return True
    return False


def _ensure_reagent_lots_schema(conn):
    desired_cols = _schema_columns('reagent_lots')
    desired_names = [c[0] for c in desired_cols]
    if not _table_exists(conn, 'reagent_lots'):
        col_sql = [f'{name} {typ}' for name, typ in desired_cols]
        conn.execute('CREATE TABLE reagent_lots (\n    ' + ',\n    '.join(col_sql) + '\n)')
        return

    existing_cols = conn.execute('PRAGMA table_info("reagent_lots")').fetchall()
    existing_names = [r[1] for r in existing_cols]
    if existing_names == desired_names:
        return

    conn.execute('ALTER TABLE reagent_lots RENAME TO reagent_lots_old')
    col_sql = [f'{name} {typ}' for name, typ in desired_cols]
    conn.execute('CREATE TABLE reagent_lots (\n    ' + ',\n    '.join(col_sql) + '\n)')
    old_rows = conn.execute("SELECT * FROM reagent_lots_old").fetchall()
    old_cols = [r[1] for r in conn.execute('PRAGMA table_info("reagent_lots_old")').fetchall()]
    for row in old_rows:
        data = dict(zip(old_cols, row))
        lot_name = (
            str(data.get('lot_name') or '').strip()
            or str(data.get('lot_number') or '').strip()
            or str(data.get('lot_id') or '').strip()
        )
        if lot_name == '':
            continue
        lot_id = _next_prefixed_id(conn, 'reagent_lots', 'lot_id', 'LOT')
        conn.execute(
            """
            INSERT OR IGNORE INTO reagent_lots (
                lot_id, lot_name, reagent_type, composition_details, manufacture_date, prepared_by, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lot_id,
                lot_name,
                data.get('reagent_type'),
                data.get('composition_details'),
                data.get('manufacture_date'),
                data.get('prepared_by') or 'A.Li',
                data.get('notes'),
            ),
        )
    conn.execute('DROP TABLE reagent_lots_old')


def _ensure_pad_material_schema(conn):
    desired_cols = _schema_columns('pad_material')
    desired_names = [c[0] for c in desired_cols]
    if not _table_exists(conn, 'pad_material'):
        col_sql = [f'{name} {typ}' for name, typ in desired_cols]
        conn.execute('CREATE TABLE pad_material (\n    ' + ',\n    '.join(col_sql) + '\n)')
        return

    existing_cols = conn.execute('PRAGMA table_info("pad_material")').fetchall()
    existing_names = [r[1] for r in existing_cols]
    if existing_names == desired_names:
        return

    conn.execute('ALTER TABLE pad_material RENAME TO pad_material_old')
    col_sql = [f'{name} {typ}' for name, typ in desired_cols]
    conn.execute('CREATE TABLE pad_material (\n    ' + ',\n    '.join(col_sql) + '\n)')

    old_rows = conn.execute("SELECT * FROM pad_material_old").fetchall()
    old_cols = [r[1] for r in conn.execute('PRAGMA table_info("pad_material_old")').fetchall()]
    for row in old_rows:
        data = dict(zip(old_cols, row))
        pad_name = (
            str(data.get('pad_name') or '').strip()
            or str(data.get('pad_id') or '').strip()
        )
        if pad_name == '':
            continue
        pad_id = _next_prefixed_id(conn, 'pad_material', 'pad_id', 'PAD')
        conn.execute(
            """
            INSERT OR IGNORE INTO pad_material (
                pad_id, pad_name, type, composition_details, manufacture_date, prepared_by, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pad_id,
                pad_name,
                data.get('type'),
                data.get('composition_details'),
                data.get('manufacture_date'),
                data.get('prepared_by') or 'A.Li',
                data.get('notes'),
            ),
        )
    conn.execute('DROP TABLE pad_material_old')


def ensure_core_schema(conn):
    conn.execute('PRAGMA foreign_keys = OFF')
    if SCHEMA_PATH.exists():
        conn.executescript(SCHEMA_PATH.read_text(encoding='utf-8'))

    if _table_exists(conn, 'experiments'):
        exp_cols = {r[1] for r in conn.execute('PRAGMA table_info("experiments")').fetchall()}
        if 'conjugate_batch_name' not in exp_cols:
            conn.execute('ALTER TABLE experiments ADD COLUMN conjugate_batch_name TEXT')
        if 'conjugate_batch_id' in exp_cols:
            conn.execute(
                """
                UPDATE experiments
                SET conjugate_batch_name = COALESCE(conjugate_batch_name, conjugate_batch_id)
                WHERE conjugate_batch_id IS NOT NULL
                  AND TRIM(CAST(conjugate_batch_id AS TEXT)) != ''
                """
            )

    _ensure_table_columns_additive(conn, 'experiments', _schema_columns('experiments'))
    _rebuild_experiments_with_schema_order(conn)
    if _table_exists(conn, 'experiments'):
        conn.execute(
            """
            UPDATE experiments
            SET conjugate_pad_material = 'NGF66'
            WHERE conjugate_pad_material IS NULL
               OR TRIM(CAST(conjugate_pad_material AS TEXT)) = ''
            """
        )

    if _table_exists(conn, 'strip_results'):
        strip_col_names = {r[1] for r in conn.execute('PRAGMA table_info("strip_results")').fetchall()}
        if 'condition_id' in strip_col_names:
            rows = conn.execute(
                """
                SELECT sr.experiment_id, sr.condition_id
                FROM strip_results sr
                WHERE sr.experiment_id IS NOT NULL
                  AND sr.condition_id IS NOT NULL
                  AND TRIM(CAST(sr.condition_id AS TEXT)) != ''
                ORDER BY sr.rowid DESC
                """
            ).fetchall()
            seen = set()
            for exp_id, condition_id in rows:
                if exp_id in seen:
                    continue
                seen.add(exp_id)
                conn.execute(
                    """
                    UPDATE experiments
                    SET condition = COALESCE(NULLIF(TRIM(condition), ''), ?)
                    WHERE experiment_id = ?
                    """,
                    (str(condition_id), exp_id),
                )

    _ensure_reagent_lots_schema(conn)
    _ensure_pad_material_schema(conn)
    conn.execute(
        """
        UPDATE reagent_lots
        SET lot_name = lot_id
        WHERE lot_name IS NULL OR TRIM(lot_name) = ''
        """
    )
    conn.execute(
        """
        UPDATE pad_material
        SET pad_name = pad_id
        WHERE pad_name IS NULL OR TRIM(pad_name) = ''
        """
    )
    strip_cols = _schema_columns('strip_results')
    strip_fks = _schema_foreign_keys('strip_results')
    _ensure_table_schema(conn, 'strip_results', strip_cols, strip_fks)
    if not _has_expected_fk(conn, 'strip_results', 'experiment_id', 'experiments', 'experiment_id'):
        _ensure_table_schema(conn, 'strip_results', strip_cols, strip_fks, force_rebuild=True)

    _ensure_table_schema(
        conn,
        'conjugate_batch',
        _schema_columns('conjugate_batch'),
        _schema_foreign_keys('conjugate_batch'),
    )
    _ensure_table_schema(
        conn,
        'upload_records',
        _schema_columns('upload_records'),
        _schema_foreign_keys('upload_records'),
    )
    _ensure_table_schema(
        conn,
        'upload_meta',
        _schema_columns('upload_meta'),
        _schema_foreign_keys('upload_meta'),
    )

    if _table_exists(conn, 'image_analysis_results'):
        conn.execute(
            """
            UPDATE strip_results
            SET
                test_line_raw_intensity = COALESCE(strip_results.test_line_raw_intensity, (SELECT iar.test_line_raw_intensity FROM image_analysis_results iar WHERE iar.strip_id = strip_results.strip_id LIMIT 1)),
                condition_value = COALESCE(
                    strip_results.condition_value,
                    CAST((SELECT iar.reference_line_concentration_mg_ml FROM image_analysis_results iar WHERE iar.strip_id = strip_results.strip_id LIMIT 1) AS TEXT),
                    (SELECT iar.nitrocellulose_material FROM image_analysis_results iar WHERE iar.strip_id = strip_results.strip_id LIMIT 1),
                    (SELECT iar.sample_pad_material FROM image_analysis_results iar WHERE iar.strip_id = strip_results.strip_id LIMIT 1),
                    (SELECT iar.sample_pad_pretreatment_lot FROM image_analysis_results iar WHERE iar.strip_id = strip_results.strip_id LIMIT 1),
                    (SELECT iar.conjugate_pad_material FROM image_analysis_results iar WHERE iar.strip_id = strip_results.strip_id LIMIT 1),
                    (SELECT iar.conjugate_pad_pretreatment_lot FROM image_analysis_results iar WHERE iar.strip_id = strip_results.strip_id LIMIT 1),
                    (SELECT iar.absorbent_pad_material FROM image_analysis_results iar WHERE iar.strip_id = strip_results.strip_id LIMIT 1),
                    (SELECT iar.running_buffer_lot FROM image_analysis_results iar WHERE iar.strip_id = strip_results.strip_id LIMIT 1),
                    (SELECT iar.glide_buffer_lot FROM image_analysis_results iar WHERE iar.strip_id = strip_results.strip_id LIMIT 1),
                    (SELECT iar.test_line_reagent FROM image_analysis_results iar WHERE iar.strip_id = strip_results.strip_id LIMIT 1),
                    CAST((SELECT iar.test_line_concentration_mg_ml FROM image_analysis_results iar WHERE iar.strip_id = strip_results.strip_id LIMIT 1) AS TEXT),
                    (SELECT iar.reference_line_reagent FROM image_analysis_results iar WHERE iar.strip_id = strip_results.strip_id LIMIT 1),
                    CAST((SELECT iar.glide_volume_ul_per_cm FROM image_analysis_results iar WHERE iar.strip_id = strip_results.strip_id LIMIT 1) AS TEXT),
                    (SELECT iar.conjugate_batch_name FROM image_analysis_results iar WHERE iar.strip_id = strip_results.strip_id LIMIT 1),
                    (SELECT iar.gnp_lot FROM image_analysis_results iar WHERE iar.strip_id = strip_results.strip_id LIMIT 1),
                    CAST((SELECT iar.conjugate_loading_ul_per_cm FROM image_analysis_results iar WHERE iar.strip_id = strip_results.strip_id LIMIT 1) AS TEXT),
                    (SELECT iar.stability_timepoint FROM image_analysis_results iar WHERE iar.strip_id = strip_results.strip_id LIMIT 1),
                    (SELECT iar.experiment_notes FROM image_analysis_results iar WHERE iar.strip_id = strip_results.strip_id LIMIT 1)
                ),
                reference_line_raw_intensity = COALESCE(strip_results.reference_line_raw_intensity, (SELECT iar.reference_line_raw_intensity FROM image_analysis_results iar WHERE iar.strip_id = strip_results.strip_id LIMIT 1)),
                test_line_corrected_intensity = COALESCE(strip_results.test_line_corrected_intensity, (SELECT iar.test_line_corrected_intensity FROM image_analysis_results iar WHERE iar.strip_id = strip_results.strip_id LIMIT 1)),
                reference_line_corrected_intensity = COALESCE(strip_results.reference_line_corrected_intensity, (SELECT iar.reference_line_corrected_intensity FROM image_analysis_results iar WHERE iar.strip_id = strip_results.strip_id LIMIT 1)),
                test_reference_ratio = COALESCE(strip_results.test_reference_ratio, (SELECT iar.test_reference_ratio FROM image_analysis_results iar WHERE iar.strip_id = strip_results.strip_id LIMIT 1)),
                reference_test_ratio = COALESCE(strip_results.reference_test_ratio, (SELECT iar.reference_test_ratio FROM image_analysis_results iar WHERE iar.strip_id = strip_results.strip_id LIMIT 1)),
                overall_membrane_background = COALESCE(strip_results.overall_membrane_background, (SELECT iar.overall_membrane_background FROM image_analysis_results iar WHERE iar.strip_id = strip_results.strip_id LIMIT 1)),
                valid_strip = COALESCE(strip_results.valid_strip, (SELECT iar.valid_strip FROM image_analysis_results iar WHERE iar.strip_id = strip_results.strip_id LIMIT 1)),
                failure_reason = COALESCE(strip_results.failure_reason, (SELECT iar.failure_reason FROM image_analysis_results iar WHERE iar.strip_id = strip_results.strip_id LIMIT 1)),
                quality_flags = COALESCE(strip_results.quality_flags, (SELECT iar.quality_flags FROM image_analysis_results iar WHERE iar.strip_id = strip_results.strip_id LIMIT 1))
            WHERE EXISTS (SELECT 1 FROM image_analysis_results x WHERE x.strip_id = strip_results.strip_id)
            """
        )
        conn.execute('DROP TABLE image_analysis_results')

    conn.execute('CREATE INDEX IF NOT EXISTS idx_strip_results_experiment_id ON strip_results(experiment_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_strip_results_strip_id ON strip_results(strip_id)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_reagent_lots_reagent_type ON reagent_lots(reagent_type)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_pad_material_type ON pad_material(type)')
    conn.commit()
    conn.execute('PRAGMA foreign_keys = ON')


def _get_latest_experiment_id(conn):
    row = conn.execute('SELECT experiment_id FROM experiments ORDER BY experiment_id DESC LIMIT 1').fetchone()
    if not row:
        return None
    try:
        return int(row[0])
    except Exception:
        return None


def _sync_from_uploads(conn, default_experiment_id=None):
    if not _table_exists(conn, 'upload_records'):
        return

    # Keep filenames aligned for records that already exist in strip_results.
    rows = conn.execute(
        """
        SELECT id, original_name
        FROM upload_records
        """
    ).fetchall()

    if not rows:
        return

    # Defensive cleanup for legacy orphan references (e.g. experiment deleted
    # from a connection with foreign_keys disabled).
    conn.execute(
        """
        UPDATE strip_results
        SET experiment_id = NULL
        WHERE experiment_id IS NOT NULL
          AND experiment_id NOT IN (
            SELECT experiment_id FROM experiments
          )
        """
    )

    for row in rows:
        conn.execute(
            """
            UPDATE strip_results
            SET image_filename = COALESCE(image_filename, ?)
            WHERE strip_id = ?
            """,
            (
                row[1],
                str(row[0]),
            ),
        )

    conn.commit()


def sync_experiment_db(default_experiment_id=None):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        ensure_core_schema(conn)
        _sync_from_uploads(conn, default_experiment_id=default_experiment_id)
    finally:
        conn.close()


def _get_table_names(conn):
    all_names = {'reagent_lots', 'pad_material', 'conjugate_batch'}
    rows = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
        """
    ).fetchall()
    names = [r[0] for r in rows if r[0] in all_names]
    order = ['reagent_lots', 'pad_material', 'conjugate_batch']
    return [name for name in order if name in names]


def _load_table_df(conn, table_name):
    return pd.read_sql_query(f'SELECT * FROM "{table_name}"', conn)


def _get_table_columns(conn, table_name):
    rows = conn.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    out = []
    for r in rows:
        out.append({
            'name': r[1],
            'type': (r[2] or '').upper(),
            'not_null': bool(r[3]),
            'default': r[4],
            'is_pk': bool(r[5]),
        })
    return out


def _load_distinct_non_empty(conn, table_name, col_name):
    rows = conn.execute(
        f'''
        SELECT DISTINCT "{col_name}"
        FROM "{table_name}"
        WHERE "{col_name}" IS NOT NULL
          AND TRIM(CAST("{col_name}" AS TEXT)) != ''
        ORDER BY "{col_name}"
        '''
    ).fetchall()
    return [str(r[0]).strip() for r in rows if r[0] is not None and str(r[0]).strip() != '']


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


def _update_row_by_pk(conn, table_name, pk_payload, values_by_col):
    if not pk_payload:
        raise ValueError('Primary key not found for update.')
    if not values_by_col:
        return
    set_sql = ', '.join([f'"{k}" = ?' for k in values_by_col.keys()])
    where_sql = ' AND '.join([f'"{k}" = ?' for k in pk_payload.keys()])
    query = f'UPDATE "{table_name}" SET {set_sql} WHERE {where_sql}'
    conn.execute(query, list(values_by_col.values()) + list(pk_payload.values()))
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

    sync_experiment_db()

    conn = sqlite3.connect(DB_PATH)
    try:
        table_names = _get_table_names(conn)
        if not table_names:
            st.info('No tables found in experiment_data.db.')
            return

        selected_table = st.selectbox(
            'Select table',
            options=table_names,
            index=0,
            format_func=_table_display_name,
        )

        columns = _get_table_columns(conn, selected_table)
        input_columns = [
            c for c in columns
            if not _is_auto_generated_field(selected_table, c)
            and not _is_ui_hidden_field(selected_table, c)
        ]

        input_values = {}
        reagent_type_selected = ''
        reagent_type_custom = ''
        pad_type_selected = ''
        pad_type_custom = ''

        for start in range(0, len(input_columns), 3):
            cols_ui = st.columns(3)
            for offset, col in enumerate(input_columns[start:start + 3]):
                col_name = col['name']
                required = col['not_null'] and not (col['is_pk'] and 'INT' in col['type'])
                if selected_table == 'reagent_lots' and col_name == 'lot_name':
                    required = True
                if selected_table == 'pad_material' and col_name == 'pad_name':
                    required = True
                if selected_table == 'conjugate_batch' and col_name == 'conjugate_batch_name':
                    required = True

                label = _column_display_name(selected_table, col_name) + (' *' if required else '')
                default_value = DEFAULT_INPUT_VALUES.get((selected_table, col_name), '')
                placeholder = 'not empty' if required else ''

                with cols_ui[offset]:
                    if selected_table == 'reagent_lots' and col_name == 'reagent_type':
                        existing_types = _load_distinct_non_empty(conn, 'reagent_lots', 'reagent_type')
                        merged_options = list(dict.fromkeys(REAGENT_TYPE_OPTIONS + existing_types))
                        preset_options = [''] + merged_options + ['Custom...']
                        default_option = default_value if default_value in REAGENT_TYPE_OPTIONS else ('Custom...' if default_value else '')
                        if default_value and default_value in merged_options:
                            default_option = default_value
                        selected_option = st.selectbox(
                            label,
                            options=preset_options,
                            index=preset_options.index(default_option),
                            key=f'{selected_table}_{col_name}_select',
                            format_func=lambda x: 'Select type' if x == '' else x,
                        )
                        reagent_type_selected = selected_option
                        if selected_option == 'Custom...':
                            custom_val = st.text_input(
                                'custom reagent_type',
                                value=default_value if default_option == 'Custom...' else '',
                                key=f'{selected_table}_{col_name}_custom_input',
                            )
                            reagent_type_custom = custom_val
                            input_values[col_name] = custom_val
                        else:
                            input_values[col_name] = selected_option
                    elif selected_table == 'pad_material' and col_name == 'type':
                        existing_types = _load_distinct_non_empty(conn, 'pad_material', 'type')
                        merged_options = list(dict.fromkeys(PAD_TYPE_OPTIONS + existing_types))
                        preset_options = [''] + merged_options + ['Custom...']
                        default_option = default_value if default_value in PAD_TYPE_OPTIONS else ('Custom...' if default_value else '')
                        if default_value and default_value in merged_options:
                            default_option = default_value
                        selected_option = st.selectbox(
                            label,
                            options=preset_options,
                            index=preset_options.index(default_option),
                            key=f'{selected_table}_{col_name}_select',
                            format_func=lambda x: 'Select type' if x == '' else x,
                        )
                        pad_type_selected = selected_option
                        if selected_option == 'Custom...':
                            custom_val = st.text_input(
                                'custom type',
                                value=default_value if default_option == 'Custom...' else '',
                                key=f'{selected_table}_{col_name}_custom_input',
                            )
                            pad_type_custom = custom_val
                            input_values[col_name] = custom_val
                        else:
                            input_values[col_name] = selected_option
                    else:
                        input_values[col_name] = st.text_input(
                            label,
                            value=default_value,
                            placeholder=placeholder,
                            key=f'{selected_table}_{col_name}_input',
                        )

        save_col, _, _ = st.columns([1, 1, 1])
        with save_col:
            save_clicked = st.button('Save', width='content')

        if save_clicked:
            missing = []
            payload = {}
            convert_errors = []

            for col in input_columns:
                name = col['name']
                raw = input_values.get(name, '')

                if selected_table == 'reagent_lots' and name == 'reagent_type' and reagent_type_selected == 'Custom...':
                    raw = reagent_type_custom
                    if (raw or '').strip() == '':
                        missing.append('reagent_type')
                        continue
                if selected_table == 'pad_material' and name == 'type' and pad_type_selected == 'Custom...':
                    raw = pad_type_custom
                    if (raw or '').strip() == '':
                        missing.append('type')
                        continue

                required = col['not_null'] and not (col['is_pk'] and 'INT' in col['type'])
                if selected_table == 'reagent_lots' and name == 'lot_name':
                    required = True
                if selected_table == 'pad_material' and name == 'pad_name':
                    required = True
                if selected_table == 'conjugate_batch' and name == 'conjugate_batch_name':
                    required = True

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

            if missing:
                missing_labels = [_column_display_name(selected_table, n) for n in missing]
                st.error(f'Not empty required: {", ".join(missing_labels)}')
            elif convert_errors:
                st.error('; '.join(convert_errors))
            elif not payload:
                st.error('No input to save.')
            else:
                try:
                    if selected_table == 'reagent_lots':
                        raw_name = str(payload.get('lot_name', '') or '').strip()
                        if ',' in raw_name or '，' in raw_name:
                            parts = [p.strip() for p in raw_name.replace('，', ',').split(',')]
                            lot_names = [p for p in parts if p != '']
                            if not lot_names:
                                st.error('lot_name is empty.')
                                return
                            inserted_n = 0
                            failed = []
                            base_payload = dict(payload)
                            for lot_name in lot_names:
                                row_payload = dict(base_payload)
                                row_payload['lot_name'] = lot_name
                                row_payload['lot_id'] = _next_prefixed_id(conn, 'reagent_lots', 'lot_id', 'LOT')
                                try:
                                    _insert_row(conn, selected_table, row_payload)
                                    inserted_n += 1
                                except Exception as e:
                                    failed.append(f'{lot_name}: {e}')
                            if inserted_n > 0:
                                st.success(f'Saved {inserted_n} records.')
                            if failed:
                                st.error('Failed: ' + '; '.join(failed))
                        else:
                            payload['lot_id'] = _next_prefixed_id(conn, 'reagent_lots', 'lot_id', 'LOT')
                            _insert_row(conn, selected_table, payload)
                            st.success('Saved successfully.')
                    elif selected_table == 'pad_material':
                        raw_name = str(payload.get('pad_name', '') or '').strip()
                        if ',' in raw_name or '，' in raw_name:
                            parts = [p.strip() for p in raw_name.replace('，', ',').split(',')]
                            pad_names = [p for p in parts if p != '']
                            if not pad_names:
                                st.error('pad_name is empty.')
                                return
                            inserted_n = 0
                            failed = []
                            base_payload = dict(payload)
                            for pad_name in pad_names:
                                row_payload = dict(base_payload)
                                row_payload['pad_name'] = pad_name
                                row_payload['pad_id'] = _next_prefixed_id(conn, 'pad_material', 'pad_id', 'PAD')
                                try:
                                    _insert_row(conn, selected_table, row_payload)
                                    inserted_n += 1
                                except Exception as e:
                                    failed.append(f'{pad_name}: {e}')
                            if inserted_n > 0:
                                st.success(f'Saved {inserted_n} records.')
                            if failed:
                                st.error('Failed: ' + '; '.join(failed))
                        else:
                            payload['pad_id'] = _next_prefixed_id(conn, 'pad_material', 'pad_id', 'PAD')
                            _insert_row(conn, selected_table, payload)
                            st.success('Saved successfully.')
                    elif selected_table == 'conjugate_batch':
                        raw_name = str(payload.get('conjugate_batch_name', '') or '').strip()
                        if ',' in raw_name or '，' in raw_name:
                            parts = [p.strip() for p in raw_name.replace('，', ',').split(',')]
                            batch_names = [p for p in parts if p != '']
                            if not batch_names:
                                st.error('conjugate_batch_name is empty.')
                                return
                            inserted_n = 0
                            failed = []
                            base_payload = dict(payload)
                            for batch_name in batch_names:
                                row_payload = dict(base_payload)
                                row_payload['conjugate_batch_name'] = batch_name
                                try:
                                    _insert_row(conn, selected_table, row_payload)
                                    inserted_n += 1
                                except Exception as e:
                                    failed.append(f'{batch_name}: {e}')
                            if inserted_n > 0:
                                st.success(f'Saved {inserted_n} records.')
                            if failed:
                                st.error('Failed: ' + '; '.join(failed))
                        else:
                            _insert_row(conn, selected_table, payload)
                            st.success('Saved successfully.')
                    st.rerun()
                except Exception as e:
                    st.error(f'Failed to save: {e}')

        df = _load_table_df(conn, selected_table)
        visible_df = df.copy()
        hidden_in_table = UI_HIDDEN_FIELDS.get(selected_table, set())
        if hidden_in_table:
            visible_cols = [c for c in visible_df.columns if c not in hidden_in_table]
            visible_df = visible_df[visible_cols]

        st.caption(f'Table: {_table_display_name(selected_table)} | Rows: {len(df)}')
        if df.empty:
            st.info('No rows in this table.')
            return

        pk_names = [c['name'] for c in columns if c['is_pk']]
        display_to_real = {
            _column_display_name(selected_table, col_name): col_name
            for col_name in visible_df.columns
        }
        editor_df = visible_df.rename(columns={v: k for k, v in display_to_real.items()}).copy()
        editor_df['remove'] = False

        edit_key = f'db_edit_mode_{selected_table}'
        prev_edit_key = f'db_prev_edit_mode_{selected_table}'
        cache_key = f'db_editor_cache_{selected_table}'
        prev_edit_mode = bool(st.session_state.get(prev_edit_key, False))
        edit_mode = st.toggle('Edit table', key=edit_key)
        st.session_state[prev_edit_key] = bool(edit_mode)

        edited_df = st.data_editor(
            editor_df,
            hide_index=True,
            width='stretch',
            key=f'db_editor_{selected_table}_{"edit" if edit_mode else "view"}',
            disabled=(not edit_mode),
        )

        if edit_mode:
            st.session_state[cache_key] = edited_df.copy()

        if prev_edit_mode and not edit_mode:
            try:
                edited_df = st.session_state.get(cache_key)
                if edited_df is None:
                    st.info('No changes to save.')
                    return
                editable_col_meta = {c['name']: c for c in columns if c['name'] in visible_df.columns}
                updated_rows = 0
                deleted_rows = 0
                for row_idx, edited_row in edited_df.iterrows():
                    if bool(edited_row.get('remove', False)):
                        pk_payload = {pk_name: df.iloc[row_idx][pk_name] for pk_name in pk_names if pk_name in df.columns}
                        _delete_row_by_pk(conn, selected_table, pk_payload)
                        deleted_rows += 1
                        continue

                    original_row = visible_df.iloc[row_idx]
                    row_payload = {}
                    missing = []
                    convert_errors = []

                    for display_name, raw_value in edited_row.items():
                        if display_name == 'remove':
                            continue
                        real_name = display_to_real[display_name]
                        col_meta = editable_col_meta[real_name]
                        required = col_meta['not_null'] and not (col_meta['is_pk'] and 'INT' in col_meta['type'])
                        if selected_table == 'reagent_lots' and real_name == 'lot_name':
                            required = True
                        if selected_table == 'pad_material' and real_name == 'pad_name':
                            required = True
                        if selected_table == 'conjugate_batch' and real_name == 'conjugate_batch_name':
                            required = True

                        raw_text = '' if pd.isna(raw_value) else str(raw_value)
                        if required and raw_text.strip() == '':
                            missing.append(_column_display_name(selected_table, real_name))
                            continue

                        try:
                            converted = _convert_input(raw_text, col_meta['type'])
                        except ValueError:
                            convert_errors.append(f'{real_name} expects {col_meta["type"]}')
                            continue
                        row_payload[real_name] = converted

                    if missing:
                        raise ValueError(f'Row {row_idx + 1} missing required: {", ".join(missing)}')
                    if convert_errors:
                        raise ValueError(f'Row {row_idx + 1}: {"; ".join(convert_errors)}')

                    has_changes = False
                    for col_name, new_value in row_payload.items():
                        old_value = original_row[col_name]
                        if pd.isna(old_value):
                            old_value = None
                        if new_value != old_value:
                            has_changes = True
                            break
                    if not has_changes:
                        continue

                    pk_payload = {pk_name: df.iloc[row_idx][pk_name] for pk_name in pk_names if pk_name in df.columns}
                    _update_row_by_pk(conn, selected_table, pk_payload, row_payload)
                    updated_rows += 1

                if updated_rows == 0 and deleted_rows == 0:
                    st.info('No changes to save.')
                else:
                    msg = []
                    if updated_rows:
                        msg.append(f'updated {updated_rows} row(s)')
                    if deleted_rows:
                        msg.append(f'deleted {deleted_rows} row(s)')
                    st.success('Saved table changes: ' + ', '.join(msg) + '.')
                    st.session_state.pop(cache_key, None)
                    st.rerun()
            except Exception as e:
                st.error(f'Failed to save table changes: {e}')
    except Exception as e:
        st.error(f'Failed to load table data: {e}')
    finally:
        conn.close()
