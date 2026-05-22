# Image Analysis Studio

A Streamlit app for grayscale image analysis with:

- image upload and analysis in `Library`
- standard reference generation in `Standard`
- summary table + CSV export in `Insights`
- detail view per analyzed record (opened from `Insights`)
- persisted run metadata in `uploads/meta.json`

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

## Structure

- `app.py`: app entrypoint
- `library.py`: upload + analysis + metadata write
- `standard.py`: standard reference generation
- `insight.py`: insights table + export + detail routing
- `insight_detail.py`: detail record viewer
- `navigation.py`: sidebar navigation
- `layout.py`, `theme.py`: UI shell/theme
- `uploads/`: generated images and `meta.json`
