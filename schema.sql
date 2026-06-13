-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 0 : EXTENSIONS
-- ─────────────────────────────────────────────────────────────────────────────

CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- required for fast ILIKE / trigram indexes


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 1 : TABLE — etl_upload_log
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS etl_upload_log (
    id              SERIAL          PRIMARY KEY,
    project_name    TEXT            NOT NULL,
    batch_code      TEXT            NOT NULL,
    author_name     TEXT,
    file_name       TEXT            NOT NULL,
    upload_date     TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    sku_count       INTEGER         NOT NULL DEFAULT 0,
    status          TEXT            NOT NULL DEFAULT 'active'
                                    CHECK (status IN ('active', 'deleted')),
    user_id         UUID,
    user_email      TEXT,
    role            TEXT            NOT NULL DEFAULT 'user'
                                    CHECK (role IN ('user', 'admin')),
    CONSTRAINT unique_file_batch UNIQUE (batch_code, file_name)
);


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 2 : TABLE — etl_data
-- One row per SKU. PK: ANXT_<batch_code>_<sku_count>_<7-digit-serial>
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS etl_data (

    -- identity
    asn_altiusnxt_stock_number          TEXT            PRIMARY KEY,
    file_name                           TEXT            NOT NULL,
    author_name                         TEXT,
    upload_date                         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    sku_count                           INTEGER,
    user_id                             UUID,
    user_email                          TEXT,
    upload_log_id                       INTEGER         REFERENCES etl_upload_log(id) ON DELETE CASCADE,
    status                              TEXT            DEFAULT 'active',

    -- mapped target fields
    sku_id                              TEXT,
    initial_description                 TEXT,
    additional_description              TEXT,
    supplier                            TEXT,
    supplier_part_number                TEXT,
    manufacturer_name                   TEXT,
    manufacturer_part_number            TEXT,
    brand_name                          TEXT,
    series                              TEXT,
    category                            TEXT,
    taxonomy                            TEXT,
    end_node                            TEXT,
    manufacturer_name_1                 TEXT,
    manufacturer_part_number_1          TEXT,
    manufacturer_part_number_2          TEXT,
    data_source_status                  TEXT,
    html_1_url                          TEXT,
    html_2_url                          TEXT,
    specification_sheet_1_url           TEXT,
    specification_sheet_1_page          TEXT,
    catalog_1_url                       TEXT,
    catalog_1_page                      TEXT,
    brochure_1_url                      TEXT,
    brochure_1_page                     TEXT,
    msds_sds_url                        TEXT,
    sell_sheet_url                      TEXT,
    parts_url                           TEXT,
    instructions_url                    TEXT,
    owner_manual_url                    TEXT,
    drawing_sheet_url                   TEXT,
    schematic_url                       TEXT,
    warranty_url                        TEXT,
    video_link                          TEXT,
    client_url                          TEXT,

    -- product images (25 slots × 3 columns each)
    product_image_1_url                 TEXT,  client_image_1_url  TEXT,  remarks_1   TEXT,
    product_image_2_url                 TEXT,  client_image_2_url  TEXT,  remarks_2   TEXT,
    product_image_3_url                 TEXT,  client_image_3_url  TEXT,  remarks_3   TEXT,
    product_image_4_url                 TEXT,  client_image_4_url  TEXT,  remarks_4   TEXT,
    product_image_5_url                 TEXT,  client_image_5_url  TEXT,  remarks_5   TEXT,
    product_image_6_url                 TEXT,  client_image_6_url  TEXT,  remarks_6   TEXT,
    product_image_7_url                 TEXT,  client_image_7_url  TEXT,  remarks_7   TEXT,
    product_image_8_url                 TEXT,  client_image_8_url  TEXT,  remarks_8   TEXT,
    product_image_9_url                 TEXT,  client_image_9_url  TEXT,  remarks_9   TEXT,
    product_image_10_url                TEXT,  client_image_10_url TEXT,  remarks_10  TEXT,
    product_image_11_url                TEXT,  client_image_11_url TEXT,  remarks_11  TEXT,
    product_image_12_url                TEXT,  client_image_12_url TEXT,  remarks_12  TEXT,
    product_image_13_url                TEXT,  client_image_13_url TEXT,  remarks_13  TEXT,
    product_image_14_url                TEXT,  client_image_14_url TEXT,  remarks_14  TEXT,
    product_image_15_url                TEXT,  client_image_15_url TEXT,  remarks_15  TEXT,
    product_image_16_url                TEXT,  client_image_16_url TEXT,  remarks_16  TEXT,
    product_image_17_url                TEXT,  client_image_17_url TEXT,  remarks_17  TEXT,
    product_image_18_url                TEXT,  client_image_18_url TEXT,  remarks_18  TEXT,
    product_image_19_url                TEXT,  client_image_19_url TEXT,  remarks_19  TEXT,
    product_image_20_url                TEXT,  client_image_20_url TEXT,  remarks_20  TEXT,
    product_image_21_url                TEXT,  client_image_21_url TEXT,  remarks_21  TEXT,
    product_image_22_url                TEXT,  client_image_22_url TEXT,  remarks_22  TEXT,
    product_image_23_url                TEXT,  client_image_23_url TEXT,  remarks_23  TEXT,
    product_image_24_url                TEXT,  client_image_24_url TEXT,  remarks_24  TEXT,
    product_image_25_url                TEXT,  client_image_25_url TEXT,  remarks_25  TEXT,

    -- third-party URLs / images
    third_party_url_1                   TEXT,
    third_party_url_2                   TEXT,
    third_party_url_3                   TEXT,
    third_party_url_4                   TEXT,
    third_party_url_5                   TEXT,
    third_party_pdf_url                 TEXT,
    third_party_pdf_page                TEXT,
    third_party_image_1_url             TEXT,
    third_party_image_2_url             TEXT,
    third_party_image_3_url             TEXT,
    third_party_image_4_url             TEXT,
    third_party_image_5_url             TEXT,
    third_party_image_6_url             TEXT,
    third_party_image_7_url             TEXT,
    third_party_image_8_url             TEXT,
    third_party_image_9_url             TEXT,
    third_party_image_10_url            TEXT,

    -- descriptive / status fields
    short_description_as_is             TEXT,
    feature_copy                        TEXT,
	feature_bullets1 TEXT,
	feature_bullets2 TEXT,
	feature_bullets3 TEXT,
	feature_bullets4 TEXT,
	feature_bullets5 TEXT,
	feature_bullets6 TEXT,
	feature_bullets7 TEXT,
	feature_bullets8 TEXT,
	feature_bullets9 TEXT,
	feature_bullets10 TEXT,
	feature_bullets11 TEXT,
	feature_bullets12 TEXT,
	feature_bullets13 TEXT,
	feature_bullets14 TEXT,
	feature_bullets15 TEXT,
	feature_bullets16 TEXT,
	feature_bullets17 TEXT,
	feature_bullets18 TEXT,
	feature_bullets19 TEXT,
	feature_bullets20 TEXT,
	upc TEXT,
	unspsc TEXT,
	product_name TEXT,
    fill_rate                           TEXT,
    remarks                             TEXT,
    overall_status                      TEXT,
    duplicate_status_yes_no             TEXT,
    duplicate_remarks                   TEXT,

    -- flexible JSONB storage
    attributes                          JSONB,
    unmapped                            JSONB
);

ALTER TABLE etl_data
ADD COLUMN IF NOT EXISTS feature_bullets1 TEXT,
ADD COLUMN IF NOT EXISTS feature_bullets2 TEXT,
ADD COLUMN IF NOT EXISTS feature_bullets3 TEXT,
ADD COLUMN IF NOT EXISTS feature_bullets4 TEXT,
ADD COLUMN IF NOT EXISTS feature_bullets5 TEXT,
ADD COLUMN IF NOT EXISTS feature_bullets6 TEXT,
ADD COLUMN IF NOT EXISTS feature_bullets7 TEXT,
ADD COLUMN IF NOT EXISTS feature_bullets8 TEXT,
ADD COLUMN IF NOT EXISTS feature_bullets9 TEXT,
ADD COLUMN IF NOT EXISTS feature_bullets10 TEXT,
ADD COLUMN IF NOT EXISTS feature_bullets11 TEXT,
ADD COLUMN IF NOT EXISTS feature_bullets12 TEXT,
ADD COLUMN IF NOT EXISTS feature_bullets13 TEXT,
ADD COLUMN IF NOT EXISTS feature_bullets14 TEXT,
ADD COLUMN IF NOT EXISTS feature_bullets15 TEXT,
ADD COLUMN IF NOT EXISTS feature_bullets16 TEXT,
ADD COLUMN IF NOT EXISTS feature_bullets17 TEXT,
ADD COLUMN IF NOT EXISTS feature_bullets18 TEXT,
ADD COLUMN IF NOT EXISTS feature_bullets19 TEXT,
ADD COLUMN IF NOT EXISTS feature_bullets20 TEXT,
ADD COLUMN IF NOT EXISTS upc TEXT,
ADD COLUMN IF NOT EXISTS unspsc TEXT,
ADD COLUMN IF NOT EXISTS overall_status TEXT,
ADD COLUMN IF NOT EXISTS product_name TEXT,
ADD COLUMN IF NOT EXISTS fill_rate TEXT,
ADD COLUMN IF NOT EXISTS remarks TEXT,
ADD COLUMN IF NOT EXISTS duplicate_status_yes_no TEXT,
ADD COLUMN IF NOT EXISTS duplicate_remarks TEXT;

-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 3 : TABLE — etl_mapping_template
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS etl_mapping_template (
    id              SERIAL      PRIMARY KEY,
    project_name    TEXT        NOT NULL,
    source_column   TEXT        NOT NULL,
    target_column   TEXT        NOT NULL,
    user_id         UUID,
    created_at      TIMESTAMP   DEFAULT NOW(),
    CONSTRAINT uq_mapping_template UNIQUE (project_name, source_column, user_id)
);


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 4 : INDEXES — etl_upload_log
-- ─────────────────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_upload_log_user_id          ON etl_upload_log (user_id);
CREATE INDEX IF NOT EXISTS idx_upload_log_status           ON etl_upload_log (status);
CREATE INDEX IF NOT EXISTS idx_upload_log_file_name        ON etl_upload_log (file_name);
CREATE INDEX IF NOT EXISTS idx_upload_log_upload_date      ON etl_upload_log (upload_date DESC);
CREATE INDEX IF NOT EXISTS idx_upload_log_project_name     ON etl_upload_log (project_name);
CREATE INDEX IF NOT EXISTS idx_upload_log_project_trgm     ON etl_upload_log USING GIN (project_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_upload_log_batch_trgm       ON etl_upload_log USING GIN (batch_code  gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_upload_log_user_status_date ON etl_upload_log (user_id, status, upload_date DESC);


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 5 : INDEXES — etl_data
-- ─────────────────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_etl_data_file_name          ON etl_data (file_name);
CREATE INDEX IF NOT EXISTS idx_etl_data_user_id            ON etl_data (user_id);
CREATE INDEX IF NOT EXISTS idx_etl_data_log_id             ON etl_data (upload_log_id);
CREATE INDEX IF NOT EXISTS idx_etl_data_taxonomy           ON etl_data (taxonomy);
CREATE INDEX IF NOT EXISTS idx_etl_data_taxonomy_trgm      ON etl_data USING GIN (taxonomy gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_etl_data_attributes_gin     ON etl_data USING GIN (attributes);
CREATE INDEX IF NOT EXISTS idx_etl_data_unmapped_gin       ON etl_data USING GIN (unmapped);


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 6 : INDEXES — etl_mapping_template
-- ─────────────────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_mapping_tmpl_project ON etl_mapping_template (project_name, user_id);


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 7 : ALTER PATCHES  (safe for existing databases)
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE etl_upload_log
    ADD COLUMN IF NOT EXISTS user_id    UUID,
    ADD COLUMN IF NOT EXISTS user_email TEXT;

-- role column: add if missing, then apply constraint idempotently
ALTER TABLE etl_upload_log
    ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'user';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.check_constraints
        WHERE constraint_name = 'etl_upload_log_role_check'
    ) THEN
        ALTER TABLE etl_upload_log
            ADD CONSTRAINT etl_upload_log_role_check CHECK (role IN ('user','admin'));
    END IF;
END $$;

ALTER TABLE etl_data
    ADD COLUMN IF NOT EXISTS user_id        UUID,
    ADD COLUMN IF NOT EXISTS user_email     TEXT,
    ADD COLUMN IF NOT EXISTS upload_log_id  INTEGER REFERENCES etl_upload_log(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS status         TEXT DEFAULT 'active';

CREATE INDEX IF NOT EXISTS idx_etl_data_log_id ON etl_data (upload_log_id);


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 8 : PROMOTE A USER TO ADMIN
-- ─────────────────────────────────────────────────────────────────────────────

SELECT DISTINCT user_id, user_email
FROM etl_upload_log;


-- Option A — promote by email (recommended):
---UPDATE etl_upload_log SET role = 'admin' WHERE user_email = 'govind@altiusnxt.com';
--
-- Option B — promote by UUID:
--UPDATE etl_upload_log SET role = 'admin' WHERE user_id = 'd04c7987-b833-4651-b8c5-57be1ba974d9';
--
-- Tip: you can also skip the DB step entirely and just add the email
--      to ADMIN_EMAILS in final1_v4.py — that's checked first at login.
--
-- Verify admins:
  SELECT DISTINCT user_id, user_email, role FROM etl_upload_log WHERE role = 'admin';


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 9 : AUTOCOMPLETE VIEWS  (back the dropdown helpers in Python)
-- ─────────────────────────────────────────────────────────────────────────────

-- get_project_names(user_id)
CREATE OR REPLACE VIEW v_project_names AS
SELECT user_id, project_name
FROM   etl_upload_log
WHERE  status = 'active'
GROUP  BY user_id, project_name
ORDER  BY project_name;

-- get_batch_codes(user_id, project_name)
CREATE OR REPLACE VIEW v_batch_codes AS
SELECT user_id, project_name, batch_code
FROM   etl_upload_log
WHERE  status = 'active'
GROUP  BY user_id, project_name, batch_code
ORDER  BY batch_code;

-- get_taxonomy_values(user_id)
CREATE OR REPLACE VIEW v_taxonomy_values AS
SELECT l.user_id, d.taxonomy
FROM   etl_data d
JOIN   etl_upload_log l ON d.upload_log_id = l.id
WHERE  l.status = 'active'
  AND  d.status = 'active'
  AND  d.taxonomy IS NOT NULL
  AND  d.taxonomy <> ''
GROUP  BY l.user_id, d.taxonomy
ORDER  BY d.taxonomy;

-- Example: fetch project names for a user
-- SELECT project_name FROM v_project_names WHERE user_id = '<uuid>';
-- SELECT batch_code    FROM v_batch_codes    WHERE user_id = '<uuid>' AND project_name = 'MyProj';
-- SELECT taxonomy      FROM v_taxonomy_values WHERE user_id = '<uuid>';


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 10 : UPSERT PATTERN (optional — idempotent re-uploads)
-- ─────────────────────────────────────────────────────────────────────────────
/*
INSERT INTO etl_data (asn_altiusnxt_stock_number, file_name, sku_id, ...)
VALUES ('ANXT_BATCH01_510_0000001', 'file.xlsx', 'SKU123', ...)
ON CONFLICT (asn_altiusnxt_stock_number) DO UPDATE
    SET file_name  = EXCLUDED.file_name,
        sku_id     = EXCLUDED.sku_id,
        attributes = EXCLUDED.attributes,
        unmapped   = EXCLUDED.unmapped;
*/


-- ─────────────────────────────────────────────────────────────────────────────
-- SECTION 11 : USEFUL OPERATIONAL QUERIES
-- ─────────────────────────────────────────────────────────────────────────────

-- Check active files for a specific file name
SELECT * FROM etl_data;
select * from etl_upload_log;

ALTER TABLE etl_data ADD COLUMN overall_status TEXT;

ALTER TABLE etl_data
DROP COLUMN feature_bullets;

--WHERE file_name = '3M UK_Batch3_Data_510 SKUs.xlsx' AND status = 'active';

-- Soft-delete a file (admin runs this directly if needed)
UPDATE etl_upload_log SET status = 'deleted' WHERE file_name = 'bad_file.xlsx';
UPDATE etl_data        SET status = 'deleted' WHERE file_name = 'bad_file.xlsx';

-- Hard-delete a log row (cascades to etl_data via FK)
--DELETE FROM etl_upload_log WHERE id = 3;

-- Check how many files a user uploaded
--SELECT COUNT(*) FROM etl_upload_log WHERE author_name = 'thushara@altiusnxt.com';

-- Files per user ranked by SKU count
--SELECT file_name, COUNT(*) AS rows
--FROM etl_data GROUP BY file_name ORDER BY rows DESC;

-- Taxonomy search (file-level)
SELECT l.id, l.project_name, l.batch_code, l.file_name, COUNT(*) AS matches
FROM etl_data d
JOIN etl_upload_log l ON d.upload_log_id = l.id
WHERE l.status = 'active' AND d.status = 'active'
AND d.taxonomy ILIKE '%Fasteners%'
GROUP BY l.id, l.project_name, l.batch_code, l.file_name
ORDER BY l.upload_date DESC;

-- Paginated file list with filters
SELECT id, project_name, batch_code, author_name, file_name, upload_date, sku_count
FROM etl_upload_log
WHERE user_id = '<uuid>' AND status = 'active' AND project_name ILIKE '%3M%'
ORDER BY upload_date DESC LIMIT 20 OFFSET 0;

-- Database size
 --SELECT pg_size_pretty(pg_database_size('Product_Data'));

-- Check all indexes on both tables
SELECT indexname, tablename FROM pg_indexes
WHERE tablename IN ('etl_upload_log','etl_data','etl_mapping_template')
ORDER BY tablename, indexname;



-- Add a new admin (user must have logged in at least once)
INSERT INTO user_roles (user_id, user_email, role)
VALUES ('<uuid>', 'newadmin@company.com', 'admin')
ON CONFLICT (user_id) DO UPDATE SET role = 'admin', updated_at = NOW();

-- Or promote by email if they already exist in the table
UPDATE user_roles SET role = 'admin', updated_at = NOW()
WHERE user_email = 'newadmin@company.com';

-- Remove an admin
UPDATE user_roles SET role = 'user', updated_at = NOW()
WHERE user_email = 'formeradmin@company.com';

-- See all current admins
SELECT user_id, user_email, role, updated_at
FROM user_roles
WHERE role = 'admin'
ORDER BY updated_at DESC;

--- CReate Admin Role

CREATE TABLE IF NOT EXISTS user_roles (
    user_id UUID PRIMARY KEY,
    user_email TEXT,
    role TEXT DEFAULT 'user',
    updated_at TIMESTAMP DEFAULT NOW()
);

INSERT INTO user_roles (user_id, user_email, role)
VALUES ('894fb229-ee51-4e44-af4c-39218980378f', 'govind@altiusnxt.com', 'admin');

--UPDATE user_roles
--SET user_email = 'govind@altiusnxt.com',
    --role = 'admin'
--WHERE user_id = '894fb229-ee51-4e44-af4c-39218980378f';

--DELETE FROM user_roles;

SELECT user_id, user_email, role 
FROM etl_upload_log
WHERE user_email = 'thushara@altiusnxt.com';

SELECT * FROM user_roles;


CREATE INDEX idx_etl_taxonomy
ON etl_data(taxonomy);

CREATE INDEX idx_etl_mpn
ON etl_data(manufacturer_part_number);

CREATE INDEX idx_etl_mfr
ON etl_data(manufacturer_name);

SELECT column_name
FROM information_schema.columns
WHERE table_name = 'etl_data';
