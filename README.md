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

## System dependencies (macOS)

If you see build or file-watching issues on macOS, install the Xcode command line tools and the `watchdog` package:

```bash
$ xcode-select --install
$ pip install watchdog
```

Note: OpenCV (installed via `opencv-python` in `requirements.txt`) may require a working build toolchain on macOS.

## Structure

- `app.py` entrypoint
- `layout.py` top bar and sidebar brand
- `navigation.py` sidebar navigation data and logic
- `theme.py` CSS and UI tuning
