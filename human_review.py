from pathlib import Path
import random
import sqlite3

import streamlit as st
from PIL import Image


PROJECT_ROOT = Path(__file__).parent
REFERENCE_IMAGE_PATH = PROJECT_ROOT / 'image.png'
UPLOADS_DIR = PROJECT_ROOT / 'uploads'
REVIEW_DB_PATH = PROJECT_ROOT / 'human_review.db'


def _pick_random_original_image():
    candidates = sorted(UPLOADS_DIR.glob('*_original.png'))
    if not candidates:
        return None
    return random.choice(candidates)


def _resize_to_height(img, target_height):
    if img.height == target_height:
        return img
    new_width = max(1, int(round(img.width * (target_height / float(img.height)))))
    return img.resize((new_width, target_height))


def _extract_image_id(filename):
    return filename.split('_')[0]


def _get_db_connection():
    conn = sqlite3.connect(REVIEW_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    conn = _get_db_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                image_id TEXT NOT NULL,
                image_name TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS review_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                review_id INTEGER NOT NULL,
                reviewer_id INTEGER NOT NULL,
                c REAL NOT NULL,
                t REAL NOT NULL,
                FOREIGN KEY(review_id) REFERENCES reviews(id)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _insert_review(image_id, image_name, review_rows):
    conn = _get_db_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO reviews (image_id, image_name)
            VALUES (?, ?)
            """,
            (image_id, image_name),
        )
        review_id = cursor.lastrowid

        conn.executemany(
            """
            INSERT INTO review_scores (review_id, reviewer_id, c, t)
            VALUES (?, ?, ?, ?)
            """,
            [
                (
                    review_id,
                    int(row['reviewer_id']),
                    float(row['c']),
                    float(row['t']),
                )
                for row in review_rows
            ],
        )
        conn.commit()
    finally:
        conn.close()


def _load_history_rows():
    conn = _get_db_connection()
    try:
        rows = conn.execute(
            """
            SELECT
                r.image_id AS image_id,
                ROUND(AVG(s.c), 2) AS c_avg,
                ROUND(AVG(s.t), 2) AS t_avg
            FROM reviews r
            JOIN review_scores s ON s.review_id = r.id
            GROUP BY r.id
            ORDER BY r.id DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def render_human_review_page():
    st.subheader('Human Visual Review')
    st.caption('Manual review page for future color-content correction calibration.')
    _init_db()

    if not REFERENCE_IMAGE_PATH.exists():
        st.error(f'Reference image not found: {REFERENCE_IMAGE_PATH}')
        return

    if 'review_random_image_name' not in st.session_state:
        initial = _pick_random_original_image()
        st.session_state.review_random_image_name = initial.name if initial else ''

    random_image_name = st.session_state.review_random_image_name
    if not random_image_name:
        st.warning('No uploaded original image found in uploads/*_original.png.')
        return
    random_image_path = UPLOADS_DIR / random_image_name
    if not random_image_path.exists():
        st.warning(f'Random image not found: {random_image_name}')
        return

    images_col, table_col = st.columns([3, 2])

    with images_col:
        left_col, right_col = st.columns(2)
        target_height = 330
        ref_img = _resize_to_height(Image.open(REFERENCE_IMAGE_PATH), target_height)
        random_img = _resize_to_height(Image.open(random_image_path), target_height)

        with left_col:
            st.image(ref_img, caption='Reference: image.png')

        with right_col:
            st.image(random_img, caption=f'Random Upload: {random_image_path.name}')

        if st.button('Change Image', key='review_pick_new_image', width='content'):
            picked = _pick_random_original_image()
            st.session_state.review_random_image_name = picked.name if picked else ''
            st.rerun()

        st.write('**History**')
        history_rows = _load_history_rows()
        if history_rows:
            slim_rows = [
                {
                    'image_id': row.get('image_id'),
                    'c_avg': row.get('c_avg'),
                    't_avg': row.get('t_avg'),
                }
                for row in history_rows
            ]
            st.dataframe(slim_rows, hide_index=True, width='stretch')
        else:
            st.info('No review history yet.')

    with table_col:
        st.write('**Visual Score**')

        header_cols = st.columns([1, 2, 2])
        header_cols[0].markdown('**title**')
        header_cols[1].markdown('**c**')
        header_cols[2].markdown('**t**')

        table_key_prefix = random_image_path.stem
        review_rows = []
        for row in range(1, 6):
            row_cols = st.columns([1, 2, 2])
            row_cols[0].markdown(f'**{row}**')
            c_value = row_cols[1].text_input(
                label=f'c_{row}',
                label_visibility='collapsed',
                key=f'{table_key_prefix}_c_{row}'
            )
            t_value = row_cols[2].text_input(
                label=f't_{row}',
                label_visibility='collapsed',
                key=f'{table_key_prefix}_t_{row}'
            )
            review_rows.append({
                'reviewer_id': row,
                'c': c_value.strip(),
                't': t_value.strip(),
            })

        _, submit_col = st.columns([3, 1])
        with submit_col:
            submit_clicked = st.button('Submit', key=f'{table_key_prefix}_save_review', width='content')

        if submit_clicked:
            missing = [
                r['reviewer_id']
                for r in review_rows
                if not r['c'] or not r['t']
            ]
            if missing:
                st.error(f'Please complete all fields. Missing reviewer rows: {missing}')
                return

            try:
                c_scores = [float(r['c']) for r in review_rows]
                t_scores = [float(r['t']) for r in review_rows]
            except ValueError:
                st.error('c/t must be numeric values.')
                return

            image_id = _extract_image_id(random_image_path.name)
            _insert_review(
                image_id=image_id,
                image_name=random_image_path.name,
                review_rows=review_rows,
            )
            st.success(f'Saved to {REVIEW_DB_PATH.name}')

            st.write(f'Image ID: **{image_id}**')
            st.write(
                f"c min/max/avg: **{min(c_scores):.2f} / {max(c_scores):.2f} / {sum(c_scores)/len(c_scores):.2f}**"
            )
            st.write(
                f"t min/max/avg: **{min(t_scores):.2f} / {max(t_scores):.2f} / {sum(t_scores)/len(t_scores):.2f}**"
            )


def main():
    st.set_page_config(
        page_title='Human Review',
        page_icon='IA',
        layout='wide'
    )
    render_human_review_page()


if __name__ == '__main__':
    main()
