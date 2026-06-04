PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS experiments (
    experiment_id INTEGER PRIMARY KEY,
    condition TEXT,
    experiment_date TEXT,
    experiment_title TEXT,
    operator TEXT DEFAULT 'A.Li',
    nitrocellulose_material TEXT,
    cassette TEXT,
    sample_pad_material TEXT,
    sample_pad_pretreatment_lot TEXT,
    conjugate_pad_material TEXT DEFAULT 'NGF66',
    conjugate_pad_pretreatment_lot TEXT,
    absorbent_pad_material TEXT,
    running_buffer_lot TEXT,
    glide_buffer_lot TEXT,
    reconstitution_buffer_lot TEXT,
    test_line_reagent TEXT,
    test_line_concentration_mg_ml REAL,
    reference_line_reagent TEXT,
    reference_line_concentration_mg_ml REAL,
    line_gliding_date TEXT,
    line_storage_condition TEXT,
    line_drying_time TEXT,
    glide_volume_ul_per_cm REAL,
    conjugate_batch_name TEXT,
    gnp_lot TEXT,
    conjugate_loading_ul_per_cm REAL,
    drying_time TEXT,
    storage_condition TEXT,
    stability_timepoint TEXT,
    experiment_notes TEXT
);

CREATE TABLE IF NOT EXISTS strip_results (
    strip_id TEXT PRIMARY KEY,
    experiment_id INTEGER,
    changed_field TEXT,
    condition_value TEXT,
    test_line_raw_intensity REAL,
    reference_line_raw_intensity REAL,
    test_line_corrected_intensity REAL,
    reference_line_corrected_intensity REAL,
    test_reference_ratio REAL,
    reference_test_ratio REAL,
    overall_membrane_background REAL,
    ct_bg_sum REAL,
    valid_strip INTEGER,
    failure_reason TEXT,
    quality_flags TEXT,
    image_filename TEXT,
    sample_equivalent_mg_ml REAL,
    dilution_equivalent REAL,
    image_upload_datetime TEXT,
    read_time_minutes REAL,
    anomaly_flag INTEGER DEFAULT 0,
    FOREIGN KEY (experiment_id) REFERENCES experiments(experiment_id)
        ON UPDATE CASCADE
        ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS conjugate_batch (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conjugate_batch_name TEXT,
    conjugate_ratio TEXT,
    reconstitution_volume_ul REAL,
    active INTEGER DEFAULT 1 CHECK (active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS reagent_lots (
    lot_id TEXT PRIMARY KEY NOT NULL,
    lot_name TEXT,
    reagent_type TEXT,
    composition_details TEXT,
    manufacture_date TEXT,
    prepared_by TEXT DEFAULT 'A.Li',
    notes TEXT,
    active INTEGER DEFAULT 1 CHECK (active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS pad_material (
    pad_id TEXT PRIMARY KEY NOT NULL,
    pad_name TEXT,
    type TEXT,
    composition_details TEXT,
    manufacture_date TEXT,
    prepared_by TEXT DEFAULT 'A.Li',
    notes TEXT,
    active INTEGER DEFAULT 1 CHECK (active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS upload_records (
    id TEXT PRIMARY KEY,
    original_name TEXT,
    original_path TEXT,
    gray_path TEXT,
    cropped_name TEXT,
    cropped_path TEXT,
    dark_regions_path TEXT,
    starred INTEGER DEFAULT 0 CHECK (starred IN (0, 1)),
    detail_json TEXT
);

CREATE TABLE IF NOT EXISTS upload_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE INDEX IF NOT EXISTS idx_strip_results_experiment_id
    ON strip_results(experiment_id);

CREATE INDEX IF NOT EXISTS idx_conjugate_batch_name
    ON conjugate_batch(conjugate_batch_name);

CREATE INDEX IF NOT EXISTS idx_reagent_lots_reagent_type
    ON reagent_lots(reagent_type);

CREATE INDEX IF NOT EXISTS idx_pad_material_type
    ON pad_material(type);

CREATE INDEX IF NOT EXISTS idx_upload_records_id
    ON upload_records(id);
