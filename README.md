# Image Analysis Studio

A Streamlit app for grayscale image analysis with:

- image upload and analysis in `Library`
- standard reference generation in `Standard`
- summary table + CSV export in `Insights`
- detail view per analyzed record (opened from `Insights`)
- persisted run metadata in `uploads.db`

## Run

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Main pages

- `Library`
- Upload images/CSV.
- Detect dark regions and compute `c`, `t`, `background`, `ratio`.
- Save generated images and metadata.

- `Standard`
- Process `image.jpeg`.
- Generate `standard_reference.json`.

- `Insights`
- Show `id`, `c`, `t`, `ratio`, `date`, `time`.
- Export CSV (without `detail` payload).
- Open per-row detail page.

- `Clear All` (sidebar)
- Remove generated files in `uploads/`.
- Clear app session cache/state.

## Image Processing Flow (Library) & Display Names

`Library` page uses `analyze_library_image` in `image_processing.py`.

1. `Original`
- source RGB image from uploader.
- saved as `uploads/{id}_original.png`.

2. `Grayscale`
- convert to grayscale (`process_image_to_grayscale`).
- saved as `uploads/{id}_gray.png`.

3. `Cropped` (center ROI for vertical-line search)
- center crop with width/height ratio logic.
- saved as `uploads/{id}_cropped.png`.
- this is mainly an intermediate image and is usually not shown directly in `Insight Detail`.

4. `Cropped Vertical Overlay` (vertical candidate boxes)
- detect vertical dark regions and draw cyan boxes.
- saved as `uploads/{id}_cropped_vertical.png`.
- in Insight Detail this is shown under caption:
  - `Cropped Vertical Overlay` (priority path is `cropped_vertical_path`; fallback is `cropped_path`).

5. `Vertical Crop (Length Limited)`
- crop area between selected vertical guide lines.
- saved as `uploads/{id}_vertical_crop.png` when available.
- shown in Insight Detail as:
  - `Vertical Crop (Length Limited)`.

6. `Cropped (Top/Bottom 20% Removed)`
- trim top/bottom 20% and left/right 5% before horizontal line detection.
- saved as `uploads/{id}_cropped_trimmed.png`.
- shown in Insight Detail as:
  - `Cropped (Top/Bottom 20% Removed)`.

7. `Dark Regions Overlay` (first-pass horizontal regions)
- draw red boxes for initial horizontal dark-region detection.
- saved as `uploads/{id}_dark_regions.png`.

8. `Re-Crop Overlay` (final c/t regions)
- re-crop around selected regions and redraw labeled boxes (`c`, `t`, ...).
- saved as `uploads/{id}_recrop.png`.
- shown in Library as:
  - `Dark Line Regions Re-Crop — {original_name}`
- shown in Insight Detail as:
  - `Re-Crop Overlay`.

9. `c/t/background/ratio` metrics
- line intensity for each detected region uses a trimmed mean:
  - flatten region pixels
  - drop lowest 10% and highest 10%
  - average the remaining 80%
- stored values are converted to dark-value scale (`255 - gray`) and rounded to 4 decimals.

## Structure

- `app.py`: app entrypoint
- `library.py`: upload + analysis + metadata write
- `standard.py`: standard reference generation
- `insight.py`: insights table + export + detail routing
- `insight_detail.py`: detail record viewer
- `navigation.py`: sidebar navigation
- `layout.py`, `theme.py`: UI shell/theme
- `uploads/`: generated images
- `uploads.db`: persisted upload/analysis records
