# Image Analysis Studio

This is a standalone Streamlit project that contains only the basic dashboard shell:

- top bar / page header
- side bar navigation
- standalone theme and layout helpers
- a minimal set of placeholder pages

## Run

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Structure

- `app.py` entrypoint
- `layout.py` top bar and sidebar brand
- `navigation.py` sidebar navigation data and logic
- `theme.py` CSS and UI tuning
