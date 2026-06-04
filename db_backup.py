from datetime import datetime
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile

import streamlit as st

from database import DB_PATH, sync_experiment_db


BACKUP_DIR = Path(__file__).parent / 'database_backups'


def _timestamp():
    return datetime.now().strftime('%Y%m%d_%H%M%S')


def _validate_sqlite_db(path):
    if not path.exists() or path.stat().st_size == 0:
        raise ValueError(f'{path.name} is empty or missing.')
    conn = sqlite3.connect(path)
    try:
        result = conn.execute('PRAGMA integrity_check').fetchone()
        if not result or str(result[0]).lower() != 'ok':
            raise ValueError(f'{path.name} failed integrity check: {result[0] if result else "unknown"}')
    finally:
        conn.close()


def create_database_backup(reason='manual'):
    if not DB_PATH.exists():
        raise FileNotFoundError(f'{DB_PATH.name} does not exist.')
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUP_DIR / f'experiment_data_{_timestamp()}_{reason}.db'
    shutil.copy2(DB_PATH, backup_path)
    _validate_sqlite_db(backup_path)
    return backup_path


def _replace_database(source_path, backup_reason):
    _validate_sqlite_db(source_path)
    backup_path = create_database_backup(backup_reason)
    shutil.copy2(source_path, DB_PATH)
    sync_experiment_db()
    _restore_strip_experiment_links(source_path)
    _validate_sqlite_db(DB_PATH)
    return backup_path


def _restore_strip_experiment_links(source_path):
    conn = sqlite3.connect(DB_PATH)
    try:
        source_db = str(Path(source_path).resolve()).replace("'", "''")
        conn.execute(f"ATTACH DATABASE '{source_db}' AS source_db")
        try:
            source_has_strip = conn.execute(
                "SELECT 1 FROM source_db.sqlite_master WHERE type = 'table' AND name = 'strip_results'"
            ).fetchone()
            if not source_has_strip:
                return
            conn.execute(
                """
                UPDATE strip_results AS target
                SET experiment_id = (
                    SELECT source.experiment_id
                    FROM source_db.strip_results AS source
                    WHERE source.strip_id = target.strip_id
                )
                WHERE EXISTS (
                    SELECT 1
                    FROM source_db.strip_results AS source
                    WHERE source.strip_id = target.strip_id
                      AND source.experiment_id IN (
                          SELECT experiment_id FROM experiments
                      )
                )
                """
            )
            conn.commit()
        finally:
            conn.execute('DETACH DATABASE source_db')
    finally:
        conn.close()


def restore_database_from_backup(source_path):
    return _replace_database(Path(source_path), 'before_restore')


def restore_database_from_committed():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmpdir:
        source_path = Path(tmpdir) / 'experiment_data_committed.db'
        data = subprocess.check_output(['git', 'show', 'HEAD:experiment_data.db'], cwd=Path(__file__).parent)
        source_path.write_bytes(data)
        return _replace_database(source_path, 'before_committed_restore')


def _database_counts(path):
    if not path.exists():
        return {}
    conn = sqlite3.connect(path)
    try:
        counts = {}
        for table_name in ('experiments', 'strip_results', 'upload_records', 'reagent_lots', 'pad_material', 'conjugate_batch'):
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table_name,),
            ).fetchone()
            if exists:
                counts[table_name] = conn.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
        return counts
    finally:
        conn.close()


def _backup_options():
    if not BACKUP_DIR.exists():
        return []
    return sorted(BACKUP_DIR.glob('experiment_data_*.db'), key=lambda p: p.stat().st_mtime, reverse=True)


def render_database_backup_page():
    st.subheader('Database Backup')
    st.caption('Create restore points for experiment_data.db and recover the database from a backup or the committed git copy.')

    counts = _database_counts(DB_PATH)
    if counts:
        cols = st.columns(3)
        for idx, (table_name, count) in enumerate(counts.items()):
            cols[idx % 3].metric(table_name.replace('_', ' ').title(), count)
    else:
        st.warning('experiment_data.db was not found.')

    st.divider()
    create_col, committed_col = st.columns(2)

    with create_col:
        st.markdown('**Create Backup**')
        if st.button('Back up current database', width='stretch'):
            try:
                backup_path = create_database_backup('manual')
                st.success(f'Created backup: {backup_path.name}')
            except Exception as exc:
                st.error(f'Failed to create backup: {exc}')

    with committed_col:
        st.markdown('**Restore Committed DB**')
        st.caption('This first backs up the current DB, then restores the tracked git version and reapplies the current schema.')
        confirm_committed = st.checkbox('I understand this replaces the current database file.', key='confirm_restore_committed')
        if st.button('Restore from committed database', disabled=not confirm_committed, width='stretch'):
            try:
                backup_path = restore_database_from_committed()
                st.cache_data.clear()
                st.success(f'Restored committed database. Current DB was backed up as {backup_path.name}.')
                st.rerun()
            except Exception as exc:
                st.error(f'Failed to restore committed database: {exc}')

    st.divider()
    st.markdown('**Restore Backup**')
    backups = _backup_options()
    if not backups:
        st.info('No backups found yet.')
        return

    selected_backup = st.selectbox(
        'Backup file',
        options=backups,
        format_func=lambda p: f'{p.name} ({datetime.fromtimestamp(p.stat().st_mtime).strftime("%d/%m/%Y %H:%M:%S")})',
    )
    confirm_backup = st.checkbox('I understand this replaces the current database file.', key='confirm_restore_backup')
    if st.button('Restore selected backup', disabled=not confirm_backup, width='stretch'):
        try:
            backup_path = restore_database_from_backup(selected_backup)
            st.cache_data.clear()
            st.success(f'Restored {selected_backup.name}. Previous current DB was backed up as {backup_path.name}.')
            st.rerun()
        except Exception as exc:
            st.error(f'Failed to restore backup: {exc}')
