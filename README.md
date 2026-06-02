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

### Insights

1. Filter by ID, changed field, ratio range, date, star.
2. Review table and open `Detail` per row.
3. Export from bottom-right floating button.

### Database

1. Select table (`reagent_lots`, `pad_material`, `conjugate_batch`).
2. Fill input fields and click `Save`.
3. Use table-level remove action to delete rows.

## Export Format

- If changed filter = `Full`:
  - export `CSV`
  - columns: `star`, `id`, corrected intensities, ratio, `(c-bg)+(t-bg)`, `date`, `time`
- If changed filter != `Full`:
  - export `Excel (.xlsx)` with 2 sheets:
    - `experiment`: matched experiment rows
    - `strip`: matched strip rows (merged strip results data)
