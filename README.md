# Image Analysis Studio

Streamlit app for strip image analysis, experiment tracking, and export.

## Run

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Database Structure

Main DB: `experiment_data.db`

- `experiments`
  - one row per experiment
  - key: `experiment_id`
  - includes `condition` (changed field name) and experiment metadata
- `strip_results`
  - one row per image/strip
  - key: `strip_id`
  - link: `experiment_id -> experiments.experiment_id`
  - includes:
    - `condition_value`
    - analysis metrics (`test/reference raw`, `corrected`, `ratio`, `background`, `valid_strip`, `failure_reason`, `quality_flags`)
    - strip metadata (`image_filename`, `sample_equivalent_mg_ml`, `image_upload_datetime`, etc.)
- `reagent_lots`
  - lot master data (`lot_id`, `lot_name`, `reagent_type`, ...)
- `pad_material`
  - pad material master data (`pad_id`, `pad_name`, `type`, ...)
- `conjugate_batch`
  - conjugate batch master data (`conjugate_batch_name`, `conjugate_ratio`, `reconstitution_volume_ul`)

In `experiment_data.db`:

- `upload_records`
  - image-level processed outputs and display data
- `upload_meta`
  - upload-related migration/state flags

## Pages

### Library

1. Select or create experiment.
2. Choose `changed` (default: `sample_equivalent_mg_ml`).
3. Upload images.
4. For each image, input changed value and click `Save`.
5. App writes images + metrics to `experiment_data.db`.

### Results

1. Filter by ID, changed field, ratio range, date, star.
2. Review table and open `Detail` per row.
3. Export from bottom-right floating button.

### Analysis

1. Open `Analysis`.
2. The page reads `experiments` and `strip_results` from `experiment_data.db`.
3. Experiments are grouped by shared experiment settings. `cassette`, `experiment_id`, and `experiment_title` are ignored for grouping.
4. The page outputs one summary row per analysis group.

## Analysis Grouping Rule

- Source tables: `experiments` + `strip_results`
- Join rule: `strip_results.experiment_id -> experiments.experiment_id`
- Grouping target: one analysis row represents one experiment setting group
- Ignored fields during grouping:
  - `cassette`
  - `experiment_id`
  - `experiment_title`
- Effective meaning:
  - if two experiment rows differ only in `cassette`, `experiment_id`, or `experiment_title`, they are treated as the same analysis group
  - strips from those experiments are pooled together for score calculation
- Display:
  - grouped `experiment_title` values are joined into one display label

### Database

1. Select table (`reagent_lots`, `pad_material`, `conjugate_batch`).
2. Fill input fields and click `Save`.
3. Use table-level remove action to delete rows.

## Export Format

- If changed filter = `Full`:
  - export `CSV`
  - columns: `star`, `id`, corrected intensities, `bg`, ratio, `(c-bg)+(t-bg)`, `date`
- If changed filter != `Full`:
  - export `Excel (.xlsx)` with 2 sheets:
    - `experiment`: matched experiment rows
    - `strip`: matched strip rows (merged strip results data)

## Analysis Metrics

| Metric | Weight | Calculation | Output | Higher Is Better? |
| --- | --- | --- | --- | --- |
| Competitive Response Score | 35% | `abs(Pearson r)` between IgG and T/R | 0-1 | Yes |
| Dynamic Range Score | 25% | `max(T/R) - min(T/R)` | Real number | Yes |
| Repeatability Score | 20% | `1 - CV(T/R)` | 0-1 | Yes |
| Background Quality Score | 10% | `1 - BG/255` | 0-1 | Yes |
| Reference Stability Score | 10% | `1 - CV(Control Line)` | 0-1 | Yes |

## Analysis Calculation Standard

- `IgG` uses `sample_equivalent_mg_ml`.
- `T/R` uses `test_reference_ratio`.
- `Control Line` uses `reference_line_corrected_intensity`.
- `Competitive Response Score`:
  - compute `abs(Pearson r)` between `sample_equivalent_mg_ml` and mean `T/R` inside one analysis group
  - score range is `0-1`
- `Dynamic Range Score`:
  - first compute `max(mean T/R) - min(mean T/R)` inside each analysis group
  - then normalize across all current analysis groups
  - best dynamic range = `1`, worst dynamic range = `0`
- `Repeatability Score`:
  - for each concentration, compute `CV(T/R)` across repeated strips
  - average the available CV values
  - final score = `1 - mean CV`
- `Background Quality Score`:
  - first compute mean `overall_membrane_background` inside each analysis group
  - then compute `1 - BG/255`
  - background near `0` = `1`, background near `255` = `0`
- `Reference Stability Score`:
  - compute `CV(reference_line_corrected_intensity)` across strips
  - final score = `1 - CV`
- `Total Score`:
  - weighted average of the five metric scores
  - if one metric is missing, the remaining weights are re-normalized automatically
