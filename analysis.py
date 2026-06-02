from pathlib import Path
import sqlite3

import pandas as pd
import streamlit as st


DB_PATH = Path(__file__).parent / 'experiment_data.db'

WEIGHTS = {
    'competitive_response_score': 0.35,
    'dynamic_range_score': 0.25,
    'repeatability_score': 0.20,
    'background_quality_score': 0.10,
    'reference_stability_score': 0.10,
}

GROUP_IGNORE_EXPERIMENT_FIELDS = {
    'experiment_id',
    'experiment_title',
    'cassette',
}


def _fmt4(v):
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except Exception:
        pass
    try:
        return round(float(v), 4)
    except Exception:
        return v


def _clip01(v):
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
        return max(0.0, min(1.0, float(v)))
    except Exception:
        return None


def _cv(series):
    s = pd.to_numeric(series, errors='coerce').dropna()
    if len(s) < 2:
        return None
    mean_v = float(s.mean())
    if abs(mean_v) < 1e-12:
        return None
    std_v = float(s.std(ddof=1))
    return std_v / abs(mean_v)


def _minmax_normalize(series, invert=False):
    s = pd.to_numeric(series, errors='coerce')
    out = pd.Series([None] * len(s), index=s.index, dtype='object')
    valid = s.dropna()
    if valid.empty:
        return out
    vmin = float(valid.min())
    vmax = float(valid.max())
    if abs(vmax - vmin) < 1e-12:
        value = 1.0
        for idx in valid.index:
            out.loc[idx] = value
        return out
    norm = (valid - vmin) / (vmax - vmin)
    if invert:
        norm = 1.0 - norm
    for idx, value in norm.items():
        out.loc[idx] = _clip01(value)
    return out


def _weighted_total_score(row):
    weighted_sum = 0.0
    total_weight = 0.0
    for col, weight in WEIGHTS.items():
        value = row.get(col)
        if value is None:
            continue
        try:
            if pd.isna(value):
                continue
        except Exception:
            pass
        weighted_sum += float(value) * weight
        total_weight += weight
    if total_weight <= 0:
        return None
    return weighted_sum / total_weight


def _joined_titles(series):
    values = []
    seen = set()
    for raw in series.tolist():
        text = str(raw).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        values.append(text)
    if not values:
        return ''
    if len(values) <= 3:
        return ' / '.join(values)
    return ' / '.join(values[:3]) + f' (+{len(values) - 3} more)'


def _fetch_analysis_df():
    conn = sqlite3.connect(DB_PATH)
    try:
        return pd.read_sql_query(
            """
            SELECT
                e.*,
                s.strip_id,
                s.sample_equivalent_mg_ml,
                s.test_reference_ratio,
                s.reference_line_corrected_intensity,
                s.overall_membrane_background,
                s.valid_strip
            FROM strip_results s
            INNER JOIN experiments e
                ON e.experiment_id = s.experiment_id
            ORDER BY e.experiment_id, s.strip_id
            """,
            conn,
        )
    finally:
        conn.close()


def _build_group_key_columns(df):
    experiment_cols = [c for c in df.columns if c in {
        'experiment_id',
        'condition',
        'experiment_date',
        'experiment_title',
        'operator',
        'nitrocellulose_material',
        'cassette',
        'sample_pad_material',
        'sample_pad_pretreatment_lot',
        'conjugate_pad_material',
        'conjugate_pad_pretreatment_lot',
        'absorbent_pad_material',
        'running_buffer_lot',
        'glide_buffer_lot',
        'reconstitution_buffer_lot',
        'test_line_reagent',
        'test_line_concentration_mg_ml',
        'reference_line_reagent',
        'reference_line_concentration_mg_ml',
        'glide_volume_ul_per_cm',
        'conjugate_batch_name',
        'gnp_lot',
        'conjugate_loading_ul_per_cm',
        'drying_time',
        'storage_condition',
        'stability_timepoint',
        'experiment_notes',
    }]
    return [c for c in experiment_cols if c not in GROUP_IGNORE_EXPERIMENT_FIELDS]


def _group_analysis_rows(df):
    group_cols = _build_group_key_columns(df)
    work = df.copy()
    if not group_cols:
        work['_analysis_group_key'] = 'all'
    else:
        work['_analysis_group_key'] = work[group_cols].astype(object).where(pd.notna(work[group_cols]), None).apply(
            lambda row: tuple(row.tolist()),
            axis=1,
        )
    return work


def _compute_group_scores(group_df):
    valid_df = group_df.copy()
    if 'valid_strip' in valid_df.columns:
        valid_df = valid_df[valid_df['valid_strip'].fillna(1).astype(int) != 0]

    curve_df = (
        valid_df[['sample_equivalent_mg_ml', 'test_reference_ratio']]
        .dropna()
        .groupby('sample_equivalent_mg_ml', as_index=False)['test_reference_ratio']
        .mean()
        .sort_values(by='sample_equivalent_mg_ml')
    )

    competitive_raw = None
    if len(curve_df) >= 2 and curve_df['sample_equivalent_mg_ml'].nunique() >= 2:
        corr = curve_df['sample_equivalent_mg_ml'].corr(curve_df['test_reference_ratio'])
        if pd.notna(corr):
            competitive_raw = abs(float(corr))

    dynamic_range_raw = None
    if len(curve_df) >= 2:
        dynamic_range_raw = float(curve_df['test_reference_ratio'].max() - curve_df['test_reference_ratio'].min())

    repeatability_raw = None
    if not valid_df.empty:
        cv_values = []
        for _, conc_df in valid_df.groupby('sample_equivalent_mg_ml'):
            cv = _cv(conc_df['test_reference_ratio'])
            if cv is not None:
                cv_values.append(cv)
        if cv_values:
            repeatability_raw = 1.0 - float(pd.Series(cv_values).mean())

    background_raw = None
    bg_series = pd.to_numeric(valid_df['overall_membrane_background'], errors='coerce').dropna()
    if not bg_series.empty:
        background_raw = float(bg_series.mean())

    reference_stability_raw = None
    ref_cv = _cv(valid_df['reference_line_corrected_intensity'])
    if ref_cv is not None:
        reference_stability_raw = 1.0 - ref_cv

    return {
        'experiment_title': _joined_titles(group_df['experiment_title']),
        'experiment_ids': ', '.join([str(int(x)) for x in pd.to_numeric(group_df['experiment_id'], errors='coerce').dropna().astype(int).drop_duplicates().tolist()]),
        'strip_count': int(len(valid_df)),
        'competitive_response_score': _clip01(competitive_raw),
        'dynamic_range_raw': dynamic_range_raw,
        'repeatability_score': _clip01(repeatability_raw),
        'background_raw': background_raw,
        'reference_stability_score': _clip01(reference_stability_raw),
    }


def _build_analysis_table(df):
    grouped = _group_analysis_rows(df)
    rows = []
    for _, group_df in grouped.groupby('_analysis_group_key', sort=False):
        rows.append(_compute_group_scores(group_df))

    if not rows:
        return pd.DataFrame()

    result_df = pd.DataFrame(rows)
    result_df['dynamic_range_score'] = _minmax_normalize(result_df['dynamic_range_raw'], invert=False)
    result_df['background_quality_score'] = _minmax_normalize(result_df['background_raw'], invert=True)
    result_df['total_score'] = result_df.apply(_weighted_total_score, axis=1)

    display_cols = [
        'experiment_title',
        'competitive_response_score',
        'dynamic_range_score',
        'repeatability_score',
        'background_quality_score',
        'reference_stability_score',
        'total_score',
    ]
    result_df = result_df[display_cols]
    result_df = result_df.sort_values(by='total_score', ascending=False, na_position='last').reset_index(drop=True)
    for col in display_cols[1:]:
        result_df[col] = result_df[col].apply(_fmt4)
    return result_df


def render_analysis_page():
    st.subheader('Analysis')

    if not DB_PATH.exists():
        st.info('experiment_data.db not found.')
        return

    try:
        df = _fetch_analysis_df()
    except Exception as e:
        st.error(f'Failed to read experiment_data.db: {e}')
        return

    if df.empty:
        st.info('No joined experiment/strip data found.')
        return

    st.markdown(
        """
        <div style="font-size:0.88rem; line-height:1.2; color:rgba(49, 51, 63, 0.78); margin-bottom:0.6rem;">
            <div><strong>Competitive Response Score (35%)</strong>: <code>abs(Pearson r)</code> between <code>sample_equivalent_mg_ml</code> and mean <code>test_reference_ratio</code>. Range: 0-1.</div>
            <div><strong>Dynamic Range Score (25%)</strong>: first compute <code>max(mean T/R) - min(mean T/R)</code> inside each analysis group; then normalize across all groups, with best = 1 and worst = 0.</div>
            <div><strong>Repeatability Score (20%)</strong>: <code>1 - mean CV(T/R)</code> across repeated strips at the same concentration. Range: 0-1.</div>
            <div><strong>Background Quality Score (10%)</strong>: first compute mean <code>overall_membrane_background</code> inside each group; then normalize across all groups as <code>1 - normalized BG</code>, with lowest background = 1 and highest background = 0.</div>
            <div><strong>Reference Stability Score (10%)</strong>: <code>1 - CV(reference_line_corrected_intensity)</code> across strips. Range: 0-1.</div>
            <div><strong>Total Score</strong>: weighted average of available metric scores. If one metric is missing, the remaining weights are re-normalized automatically.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    result_df = _build_analysis_table(df)
    if result_df.empty:
        st.info('No analysis result could be computed from current data.')
        return

    st.table(result_df)
