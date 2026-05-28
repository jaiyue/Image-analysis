PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS experiments (
    experiment_id INTEGER PRIMARY KEY,
    experiment_name TEXT,
    experiment_date TEXT,
    operator_name TEXT DEFAULT 'A.Li',
    running_buffer_lot_id INTEGER,
    sample_pad_material TEXT,
    sample_pad_pretreatment_lot_id INTEGER,
    conjugate_pad_material TEXT,
    conjugate_pad_pretreatment_lot_id INTEGER,
    glide_buffer_lot_id INTEGER,
    test_line_concentration REAL,
    reference_line_concentration REAL,
    conjugate_batch_lot_id INTEGER,
    conjugate_ratio REAL,
    conjugate_loading_ul_per_cm REAL,
    reconstitution_volume_ul REAL,
    drying_condition TEXT,
    storage_condition TEXT,
    notes TEXT,
    FOREIGN KEY (running_buffer_lot_id) REFERENCES reagent_lots(lot_id)
        ON UPDATE CASCADE
        ON DELETE SET NULL,
    FOREIGN KEY (glide_buffer_lot_id) REFERENCES reagent_lots(lot_id)
        ON UPDATE CASCADE
        ON DELETE SET NULL,
    FOREIGN KEY (sample_pad_pretreatment_lot_id) REFERENCES reagent_lots(lot_id)
        ON UPDATE CASCADE
        ON DELETE SET NULL,
    FOREIGN KEY (conjugate_pad_pretreatment_lot_id) REFERENCES reagent_lots(lot_id)
        ON UPDATE CASCADE
        ON DELETE SET NULL,
    FOREIGN KEY (conjugate_batch_lot_id) REFERENCES reagent_lots(lot_id)
        ON UPDATE CASCADE
        ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS strip_results (
    strip_id INTEGER PRIMARY KEY,
    experiment_id INTEGER NOT NULL,
    image_filename TEXT,
    image_path TEXT,
    upload_time TEXT,
    sample_concentration REAL,
    concentration_unit TEXT,
    replicate_number INTEGER,
    condition_number TEXT,
    strip_batch TEXT,
    anomaly_notes TEXT,
    user_verified INTEGER DEFAULT 0 CHECK (user_verified IN (0, 1)),
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (experiment_id) REFERENCES experiments(experiment_id)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS image_analysis_results (
    analysis_id INTEGER PRIMARY KEY,
    strip_id INTEGER NOT NULL,
    analysis_version TEXT,
    test_line_intensity REAL,
    reference_line_intensity REAL,
    t_c_ratio REAL,
    detected_test_line INTEGER CHECK (detected_test_line IN (0, 1)),
    detected_reference_line INTEGER CHECK (detected_reference_line IN (0, 1)),
    strip_rotation_angle REAL,
    strip_width_px INTEGER,
    strip_height_px INTEGER,
    roi_coordinates TEXT,
    confidence_score REAL,
    processing_time_ms REAL,
    analysis_timestamp TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (strip_id) REFERENCES strip_results(strip_id)
        ON UPDATE CASCADE
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reagent_lots (
    lot_id INTEGER PRIMARY KEY,
    lot_number TEXT NOT NULL UNIQUE,
    reagent_type TEXT,
    composition_details TEXT,
    manufacture_date TEXT,
    prepared_by TEXT DEFAULT 'A.Li',
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_strip_results_experiment_id
    ON strip_results(experiment_id);

CREATE INDEX IF NOT EXISTS idx_image_analysis_results_strip_id
    ON image_analysis_results(strip_id);

CREATE INDEX IF NOT EXISTS idx_reagent_lots_lot_number
    ON reagent_lots(lot_number);
