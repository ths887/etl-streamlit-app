import time
import json
import os
import re
import hashlib
import streamlit as st
import pandas as pd
from io import BytesIO
import psycopg2
import psycopg2.extras
import psycopg2.pool
from datetime import datetime
from supabase import create_client, Client

# ── Persistent upload cache directory ─────────────────────────────────────────
# Unlike tempfile.NamedTemporaryFile, files here survive Streamlit reruns and
# browser refreshes. We use a stable path inside the project root so it is
# always accessible even after the OS reclaims /tmp.
_UPLOAD_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".upload_cache")
os.makedirs(_UPLOAD_CACHE_DIR, exist_ok=True)

# --- CHANGE START --- PATCH 1: Load credentials from .env via environment variables
from dotenv import load_dotenv
load_dotenv()  # reads .env file from project root at startup
# --- CHANGE END ---

def load_css(file_name):
    with open(file_name) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

load_css("style.css")

# ═══════════════════════════════════════════════════════════
# 1. CONFIG
# ═══════════════════════════════════════════════════════════

# --- CHANGE START --- PATCH 1: DB credentials from environment variables (no hardcoding)
DB_CONFIG = {
    "host":     os.getenv("DB_HOST"),
    "port":     int(os.getenv("DB_PORT", "5432")),
    "database": os.getenv("DB_NAME"),
    "user":     os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
}

if not all([DB_CONFIG["host"], DB_CONFIG["database"], DB_CONFIG["user"]]):
    raise ValueError("Database environment variables are not set properly")

# --- CHANGE END ---

# ══════════════════════════════════════════════════════════
# ADMIN CONFIGURATION
# ──────────────────────────────────────────────────────────
# Option A (recommended for small teams): list admin emails here.
#   Any user whose email is in this set gets role = 'admin'
#   automatically after login — no DB change needed.
#
# Option B (DB-based): leave ADMIN_EMAILS empty and instead
#   run this SQL once to promote a user:
#       UPDATE etl_upload_log SET role = 'admin'
#       WHERE user_email = 'boss@company.com';
#   The get_role_for_user() function will read role from DB.
#
# Both options work together — ADMIN_EMAILS is checked first.
# ══════════════════════════════════════════════════════════
ADMIN_EMAILS: set[str] = {
    "admin@yourcompany.com",   # ← replace with real admin email(s)
    # "another@yourcompany.com",
}

def get_role_for_user(user_id: str, user_email: str) -> str:
    # Option A: hardcoded admin list
    if user_email and user_email.lower() in {e.lower() for e in ADMIN_EMAILS}:
        return "admin"

    # Option B: DB lookup (NEW TABLE)
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur  = conn.cursor()

        cur.execute(
            "SELECT role FROM user_roles WHERE user_id = %s",
            (user_id,)
        )
        row = cur.fetchone()

        cur.close()
        release_conn(conn)

        if row and row[0] == "admin":
            return "admin"

    except Exception as e:
        print("Role fetch error:", e)

    return "user"

def is_admin() -> bool:
    """Convenience helper — True when the logged-in user is an admin."""
    return st.session_state.get("user_role") == "admin"


# --- CHANGE START --- PATCH 1: Supabase credentials from environment variables
SUPABASE_URL      = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
# --- CHANGE END ---

@st.cache_resource
def get_supabase() -> Client:
    # --- CHANGE START --- PATCH 1: validate env vars before creating client
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
         raise ValueError(
            "SUPABASE_URL and SUPABASE_ANON_KEY must be set in environment variables"
        )
    # --- CHANGE END ---
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

TARGET_FIELDS = [
    "sku_id", "initial_description", "additional_description", "supplier",
    "supplier_part_number", "manufacturer_name", "manufacturer_part_number",
    "brand_name", "series", "category", "taxonomy", "end_node",
    "manufacturer_name_1", "manufacturer_part_number_1", "manufacturer_part_number_2",
    "data_source_status", "html_1_url", "html_2_url", "specification_sheet_1_url",
    "specification_sheet_1_page", "catalog_1_url", "catalog_1_page", "brochure_1_url",
    "brochure_1_page", "msds_sds_url", "sell_sheet_url", "parts_url",
    "instructions_url", "owner_manual_url", "drawing_sheet_url", "schematic_url",
    "warranty_url", "video_link", "client_url",
    "product_image_1_url", "client_image_1_url", "remarks_1",
    "product_image_2_url", "client_image_2_url", "remarks_2",
    "product_image_3_url", "client_image_3_url", "remarks_3",
    "product_image_4_url", "client_image_4_url", "remarks_4",
    "product_image_5_url", "client_image_5_url", "remarks_5",
    "product_image_6_url", "client_image_6_url", "remarks_6",
    "product_image_7_url", "client_image_7_url", "remarks_7",
    "product_image_8_url", "client_image_8_url", "remarks_8",
    "product_image_9_url", "client_image_9_url", "remarks_9",
    "product_image_10_url", "client_image_10_url", "remarks_10",
    "product_image_11_url", "client_image_11_url", "remarks_11",
    "product_image_12_url", "client_image_12_url", "remarks_12",
    "product_image_13_url", "client_image_13_url", "remarks_13",
    "product_image_14_url", "client_image_14_url", "remarks_14",
    "product_image_15_url", "client_image_15_url", "remarks_15",
    "product_image_16_url", "client_image_16_url", "remarks_16",
    "product_image_17_url", "client_image_17_url", "remarks_17",
    "product_image_18_url", "client_image_18_url", "remarks_18",
    "product_image_19_url", "client_image_19_url", "remarks_19",
    "product_image_20_url", "client_image_20_url", "remarks_20",
    "product_image_21_url", "client_image_21_url", "remarks_21",
    "product_image_22_url", "client_image_22_url", "remarks_22",
    "product_image_23_url", "client_image_23_url", "remarks_23",
    "product_image_24_url", "client_image_24_url", "remarks_24",
    "product_image_25_url", "client_image_25_url", "remarks_25",
    "third_party_url_1", "third_party_url_2", "third_party_url_3",
    "third_party_url_4", "third_party_url_5", "third_party_pdf_url",
    "third_party_pdf_page",
    "third_party_image_1_url", "third_party_image_2_url", "third_party_image_3_url",
    "third_party_image_4_url", "third_party_image_5_url", "third_party_image_6_url",
    "third_party_image_7_url", "third_party_image_8_url", "third_party_image_9_url",
    "third_party_image_10_url",
    "short_description_as_is", "feature_copy", "feature_bullets1",
    "feature_bullets2",
    "feature_bullets3",
    "feature_bullets4",
    "feature_bullets5",
    "feature_bullets6",
    "feature_bullets7",
    "feature_bullets8",
    "feature_bullets9",
    "feature_bullets10",
    "feature_bullets11",
    "feature_bullets12",
    "feature_bullets13",
    "feature_bullets14",
    "feature_bullets15",
    "feature_bullets16",
    "feature_bullets17",
    "feature_bullets18",
    "feature_bullets19",
    "feature_bullets20",
    "upc",
    "unspsc",
    "overall_status",
    "product_name","fill_rate", "remarks",
    "duplicate_status_yes_no", "duplicate_remarks",
]

ROWS_PER_MAP_PAGE = 10


# ═══════════════════════════════════════════════════════════
# 2. PAGE CONFIG & CSS
# ═══════════════════════════════════════════════════════════

st.set_page_config(
    page_title="ETL Mapper",
    page_icon="🔀",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
.stApp { background: #f0f2f6; }
.block-container { padding-top: 1rem; padding-bottom: 1rem; padding-left: 2rem; padding-right: 2rem; }

/* ── step progress bar ── */
.step-bar {
    display: flex; gap: 0; margin-bottom: 28px;
    border-radius: 8px; overflow: hidden;
    border: 1px solid #d0d4de;
}
.step-item {
    flex: 1; padding: 9px 6px; text-align: center;
    font-size: 12px; font-weight: 500;
    background: #fff; color: #9099a8;
    border-right: 1px solid #d0d4de;
}
.step-item:last-child { border-right: none; }
.step-item.done   { background: #e6f4f0; color: #1a7a5e; }
.step-item.active { background: #1a7a5e; color: #fff; }

/* ── panel headers ── */
.panel-header {
    font-size: 12px; font-weight: 700; letter-spacing: .06em;
    text-transform: uppercase; color: #6b7280;
    padding-bottom: 10px; margin-bottom: 10px;
    border-bottom: 1px solid #e5e7eb;
}

/* ── field badges ── */
.source-tag {
    background: #f0f4ff; border: 1px solid #c7d2fe;
    border-radius: 6px; padding: 5px 10px;
    font-size: 13px; color: #3730a3;
    display: inline-block; width: 100%;
    font-family: monospace;
}
.mapped-badge {
    background: #d1fae5; border: 1px solid #6ee7b7;
    border-radius: 6px; padding: 5px 10px;
    font-size: 12px; color: #065f46;
    display: inline-block;
}
.auto-badge {
    background: #fef9c3; border: 1px solid #fde047;
    border-radius: 6px; padding: 2px 7px;
    font-size: 10px; color: #854d0e;
    display: inline-block; margin-left: 6px;
    vertical-align: middle;
}
.proj-auto-badge {
    background: #dbeafe; border: 1px solid #93c5fd;
    border-radius: 6px; padding: 2px 8px;
    font-size: 10px; color: #1d4ed8;
    display: inline-block; margin-left: 6px;
    vertical-align: middle;
}
.unmapped-badge {
    background: #fef3c7; border: 1px solid #fcd34d;
    border-radius: 6px; padding: 5px 10px;
    font-size: 12px; color: #92400e;
    display: inline-block;
}
.attr-badge {
    background: #ede9fe; border: 1px solid #c4b5fd;
    border-radius: 6px; padding: 5px 10px;
    font-size: 12px; color: #5b21b6;
    display: inline-block;
}
.deleted-row { opacity: 0.55; }

/* ── file info strip ── */
.file-strip {
    display: flex; gap: 24px; align-items: center;
    background: #f8fafc; border: 1px solid #e2e8f0;
    border-radius: 8px; padding: 10px 16px;
    font-size: 13px; margin-bottom: 18px;
}
.file-strip strong { color: #1e293b; }
.file-strip span   { color: #64748b; }

/* ── summary section headers ── */
.sum-section {
    font-size: 13px; font-weight: 600; color: #374151;
    padding: 6px 12px; background: #f3f4f6;
    border-left: 3px solid #1a7a5e;
    border-radius: 0 6px 6px 0;
    margin: 14px 0 8px;
}

/* ── dividers ── */
.divider { border-top: 1px solid #e5e7eb; margin: 14px 0; }

/* ── arrow between panels ── */
.arrow-cell {
    text-align: center; font-size: 20px;
    color: #9ca3af; padding-top: 4px;
}

/* ── input section card ── */
.input-card {
    background: #fff; border: 1px solid #e2e8f0;
    border-radius: 10px; padding: 18px 20px;
    margin-bottom: 18px;
}
.input-card-title {
    font-size: 13px; font-weight: 600; color: #374151;
    margin-bottom: 14px; padding-bottom: 8px;
    border-bottom: 1px solid #e5e7eb;
}

/* ── project group card ── */
.project-group {
    background: #fff; border: 1px solid #e2e8f0;
    border-radius: 10px; padding: 14px 18px;
    margin-bottom: 14px;
}
.project-group-title {
    font-size: 14px; font-weight: 700; color: #1e293b;
    margin-bottom: 10px; padding-bottom: 6px;
    border-bottom: 2px solid #1a7a5e;
}

/* ── search section ── */
.search-section {
    background: #fff; border: 1px solid #e2e8f0;
    border-radius: 10px; padding: 16px 20px;
    margin-bottom: 18px;
}
.search-section-title {
    font-size: 14px; font-weight: 700; color: #1e293b;
    margin-bottom: 12px;
}
.file-card {
    background: #f8fafc; border: 1px solid #e2e8f0;
    border-radius: 8px; padding: 12px 16px;
    margin-bottom: 8px;
}
.file-card-meta {
    font-size: 12px; color: #64748b; margin-top: 4px;
}
.taxonomy-match-badge {
    background: #dcfce7; border: 1px solid #86efac;
    border-radius: 4px; padding: 2px 8px;
    font-size: 11px; color: #166534;
    display: inline-block;
}
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════
# 3. DATABASE — connection, DDL, DML
# ═══════════════════════════════════════════════════════════

# ── OPT 1: Connection pool ──────────────────────────────────
# Reuses existing TCP+auth connections instead of creating new
# ones on every DB call. minconn=1 keeps one warm; maxconn=10.
@st.cache_resource
def _get_pool() -> psycopg2.pool.SimpleConnectionPool:
    return psycopg2.pool.SimpleConnectionPool(minconn=1, maxconn=10, **DB_CONFIG)

def get_conn():
    """Return a connection from the pool."""
    return _get_pool().getconn()

def release_conn(conn):
    """Return a connection to the pool (never call conn.close() directly)."""
    try:
        _get_pool().putconn(conn)
    except Exception:
        pass


def create_tables():
    """Idempotent table creation + ensure all required columns exist."""
    target_col_defs = "\n".join(
        f"        {col:<40} TEXT," for col in TARGET_FIELDS
    )
    ddl = f"""
    CREATE TABLE IF NOT EXISTS etl_upload_log (
        id              SERIAL          PRIMARY KEY,
        project_name    TEXT            NOT NULL,
        batch_code      TEXT            NOT NULL,
        author_name     TEXT,
        file_name       TEXT            NOT NULL,
        upload_date     TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
        sku_count       INTEGER         NOT NULL DEFAULT 0,
        status          TEXT            NOT NULL DEFAULT 'active'
                                        CHECK (status IN ('active','deleted')),
        user_id         UUID,
        user_email      TEXT,
        role            TEXT            NOT NULL DEFAULT 'user'
                                        CHECK (role IN ('user','admin')),
        CONSTRAINT unique_file_batch UNIQUE (batch_code, file_name)
    );

    CREATE TABLE IF NOT EXISTS etl_data (
        asn_altiusnxt_stock_number      TEXT            PRIMARY KEY,
        file_name                       TEXT            NOT NULL,
        author_name                     TEXT,
        upload_date                     TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
        sku_count                       INTEGER,
        user_id                         UUID,
        user_email                      TEXT,
        upload_log_id                   INTEGER         REFERENCES etl_upload_log(id) ON DELETE CASCADE,
        status                          TEXT            DEFAULT 'active',
{target_col_defs}
        attributes                      JSONB,
        unmapped                        JSONB
    );

    -- NEW: mapping template table (FEATURE 1)
    CREATE TABLE IF NOT EXISTS etl_mapping_template (
        id              SERIAL          PRIMARY KEY,
        project_name    TEXT            NOT NULL,
        source_column   TEXT            NOT NULL,
        target_column   TEXT            NOT NULL,
        user_id         UUID,
        created_at      TIMESTAMP       DEFAULT NOW(),
        UNIQUE (project_name, source_column, user_id)
    );

    CREATE INDEX IF NOT EXISTS idx_upload_log_user_id   ON etl_upload_log (user_id);
    CREATE INDEX IF NOT EXISTS idx_upload_log_status    ON etl_upload_log (status);
    CREATE INDEX IF NOT EXISTS idx_upload_log_file_name ON etl_upload_log (file_name);
    CREATE INDEX IF NOT EXISTS idx_etl_data_file_name   ON etl_data (file_name);
    CREATE INDEX IF NOT EXISTS idx_etl_data_user_id     ON etl_data (user_id);
    CREATE INDEX IF NOT EXISTS idx_etl_data_log_id      ON etl_data (upload_log_id);
    CREATE INDEX IF NOT EXISTS idx_mapping_tmpl_project ON etl_mapping_template (project_name, user_id);
    """
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute(ddl)
    conn.commit()
    cur.close()
    release_conn(conn)


# ── FIX #1: Duplicate detection — pre-check before insert ──────────────────
def check_duplicate(batch_code: str, file_name: str) -> bool:
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute(
        "SELECT 1 FROM etl_upload_log WHERE batch_code = %s AND file_name = %s LIMIT 1",
        (batch_code, file_name),
    )
    exists = cur.fetchone() is not None
    cur.close()
    release_conn(conn)
    return exists


def generate_stock_number(batch_code: str, sku_count: int, serial: int) -> str:
    serial_str = str(serial).zfill(7)
    return f"ANXT_{batch_code}_{sku_count}_{serial_str}"


def insert_etl_data(
    df: pd.DataFrame,
    mapping: dict,
    attr_cols: list,
    unmapped_cols: list,
    batch_code: str,
    author_name: str,
    file_name: str,
    upload_date: str,
    sku_count: int,
    user_id: str = None,
    user_email: str = None,
    upload_log_id=None,
):
    mapped_source_cols: set[str] = {
        src for src, tgt in mapping.items()
        if tgt != "— skip —" and tgt in TARGET_FIELDS
    }
    attribute_cols_set: set[str] = set(attr_cols)
    all_source_cols: list[str]   = list(df.columns)
    computed_unmapped_cols: list[str] = [
        col for col in all_source_cols
        if col not in mapped_source_cols and col not in attribute_cols_set
    ]
    src_to_target: dict[str, str] = {
        src: tgt
        for src, tgt in mapping.items()
        if tgt != "— skip —" and tgt in TARGET_FIELDS
    }

    fixed_cols = [
        "asn_altiusnxt_stock_number", "file_name", "author_name",
        "upload_date", "sku_count", "user_id", "user_email", "upload_log_id",
    ]
    all_insert_cols = fixed_cols + TARGET_FIELDS + ["attributes", "unmapped"]
    col_list        = ", ".join(all_insert_cols)
    insert_sql = f"INSERT INTO etl_data ({col_list}) VALUES %s"

    # ── OPT: Vectorized row building ──────────────────────────────────────────
    # Replace Python-level row-by-row loop with vectorized pandas operations.
    # Steps:
    #   1. Replace NaN with None once up-front (avoids per-cell pd.notna checks).
    #   2. Build target columns via bulk column rename/select — no per-row dict.
    #   3. Serialise attributes + unmapped columns as JSON using .apply(json.dumps)
    #      on a pre-filtered sub-DataFrame — much faster than building dicts in a loop.
    total_rows = len(df)

    # Step 1: normalise DataFrame — convert NaN → None (Python None → SQL NULL)
    df_clean = df.where(df.notna(), other=None)

    # Step 2: build target-field columns as a new DataFrame
    target_df = pd.DataFrame(index=df_clean.index, columns=TARGET_FIELDS, dtype=object)
    target_df[:] = None
    for src_col, tgt_col in src_to_target.items():
        if src_col in df_clean.columns:
            target_df[tgt_col] = df_clean[src_col].astype(str).where(
                df_clean[src_col].notna(), other=None
            )

    # Step 3: attributes JSON per row
    attr_df = df_clean[[c for c in attr_cols if c in df_clean.columns]].copy()
    # Add fixed metadata columns to every attribute dict
    attr_df = attr_df.astype(str)
    attr_df["file_name"]   = file_name
    attr_df["author_name"] = author_name
    attr_json_series = attr_df.apply(
        lambda row: json.dumps({
            k: (
                None
                if pd.isna(v) or str(v).strip().lower() in ("nan", "none", "")
                else str(v)
            )
            for k, v in row.items()
        }),
        axis=1,
    )

    # Step 4: unmapped JSON per row
    unmap_cols_present = [c for c in computed_unmapped_cols if c in df_clean.columns]
    if unmap_cols_present:
        unmap_df = df_clean[unmap_cols_present].astype(str)
        unmap_json_series = unmap_df.apply(
            lambda row: json.dumps({
                k: (
                    None
                    if pd.isna(v) or str(v).strip().lower() in ("nan", "none", "")
                    else str(v)
                )
                for k, v in row.items()
            }),
            axis=1,
        )
    else:
        unmap_json_series = pd.Series(["{}"] * total_rows, index=df_clean.index)

    # Step 5: stock numbers (vectorized via pandas string ops)
    serials       = pd.RangeIndex(1, total_rows + 1)
    stock_numbers = pd.Series(
        [f"ANXT_{batch_code}_{sku_count}_{str(i).zfill(7)}" for i in serials],
        dtype=str,
    )

    # Step 6: assemble all_rows as list of tuples
    fixed_static = (file_name, author_name, upload_date, sku_count, user_id, user_email, upload_log_id)
    target_values_matrix = target_df[TARGET_FIELDS].values  # shape: (rows, len(TARGET_FIELDS))

    all_rows: list[tuple] = []
    for i in range(total_rows):
        row_tuple = (
            (stock_numbers.iloc[i],) +
            fixed_static +
            tuple(target_values_matrix[i]) +
            (attr_json_series.iloc[i], unmap_json_series.iloc[i])
        )
        all_rows.append(row_tuple)

    conn = get_conn()
    cur  = conn.cursor()
    inserted = 0
    CHUNK = 1000
    try:

        prog = None

        # Streamlit progress only if running inside Streamlit
        try:
            from streamlit.runtime.scriptrunner import get_script_run_ctx
            if get_script_run_ctx() and total_rows > 0:
                prog = st.progress(0, text="Inserting rows…")

        except:
            prog = None
        for start in range(0, total_rows, CHUNK):
            chunk = all_rows[start:start + CHUNK]
            psycopg2.extras.execute_values(cur, insert_sql, chunk, page_size=CHUNK)
            inserted += len(chunk)
            if prog:
                prog.progress(
                    min(inserted / total_rows, 1.0),
                    text=f"Inserting rows… {inserted:,} / {total_rows:,}"
                )
                conn.commit()
        if prog:
            prog.empty()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        release_conn(conn)
    return inserted


def insert_upload_log(
    project_name, batch_code, author_name,
    file_name, upload_date, sku_count,
    user_id=None, user_email=None,
) -> int:
    conn = get_conn()
    cur  = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO etl_upload_log
                (project_name, batch_code, author_name, file_name,
                 upload_date, sku_count, status, user_id, user_email)
            VALUES (%s, %s, %s, %s, %s, %s, 'active', %s, %s)
            RETURNING id
            """,
            (project_name, batch_code, author_name, file_name,
             upload_date, sku_count, user_id, user_email),
        )
        log_id = cur.fetchone()[0]
        conn.commit()
        return log_id
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        release_conn(conn)


def fetch_upload_logs(show_deleted: bool = False) -> pd.DataFrame:
    """Return etl_upload_log rows for the logged-in user only.
    status column is intentionally excluded from SELECT — kept in DB, hidden from UI.
    show_deleted is admin-only; non-admins always see active records only.
    """
    conn = get_conn()
    uid  = st.session_state.get("user_id")
    # Non-admins can never see deleted records regardless of argument
    if not is_admin():
        show_deleted = False
    clean_cols = "id, project_name, batch_code, author_name, file_name, upload_date, sku_count, user_id, user_email, role"
    try:
        if show_deleted:
            df = pd.read_sql_query(
                f"SELECT {clean_cols} FROM etl_upload_log WHERE user_id = %s ORDER BY upload_date DESC",
                conn, params=(uid,)
            )
        else:
            df = pd.read_sql_query(
                f"SELECT {clean_cols} FROM etl_upload_log "
                "WHERE status = 'active' AND user_id = %s ORDER BY upload_date DESC",
                conn, params=(uid,)
            )
        return df
    finally:
        release_conn(conn)


def fetch_etl_data_for_log(log_id: int) -> pd.DataFrame:
    """Return etl_data rows linked to a specific upload_log_id."""
    conn = get_conn()
    try:
        df = pd.read_sql_query(
            "SELECT asn_altiusnxt_stock_number, sku_id, initial_description, "
            "manufacturer_name, brand_name, category, taxonomy, file_name, upload_date "
            "FROM etl_data WHERE upload_log_id = %s ORDER BY asn_altiusnxt_stock_number",
            conn, params=(log_id,)
        )
        return df
    finally:
        release_conn(conn)

def fetch_full_etl_export(log_id: int) -> pd.DataFrame:
    """
    Return FULL ETL dataset for export/download.
    Includes all columns from etl_data.
    """

    conn = get_conn()

    try:
        df = pd.read_sql_query(
            """
            SELECT *
            FROM etl_data
            WHERE upload_log_id = %s
            ORDER BY asn_altiusnxt_stock_number
            """,
            conn,
            params=(log_id,)
        )

        return df

    finally:
        release_conn(conn)   

def fetch_all_etl_export(user_id: str) -> pd.DataFrame:

    conn = get_conn()

    try:
        df = pd.read_sql_query(
            """
            SELECT *
            FROM etl_data
            WHERE user_id = %s
              AND status = 'active'
            ORDER BY upload_date DESC
            """,
            conn,
            params=(user_id,)
        )

        return df

    finally:
        release_conn(conn)             





def hard_delete_log(log_id: int):
    """Permanently delete log row. etl_data rows deleted via ON DELETE CASCADE.
    ADMIN ONLY — raises PermissionError if caller is not admin.
    """
    if st.session_state.get("user_role") != "admin":
        raise PermissionError("Only admin users can permanently delete records.")
    conn = get_conn()
    cur  = conn.cursor()
    try:
        cur.execute("DELETE FROM etl_upload_log WHERE id=%s", (log_id,))
        conn.commit()
    except PermissionError:
        raise
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        release_conn(conn)


def update_log_metadata(log_id: int, project_name: str, batch_code: str):
    """Update project_name and batch_code for an existing upload log row."""
    conn = get_conn()
    cur  = conn.cursor()
    try:
        cur.execute(
            "UPDATE etl_upload_log SET project_name=%s, batch_code=%s WHERE id=%s",
            (project_name, batch_code, log_id)
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        release_conn(conn)


# ═══════════════════════════════════════════════════════════
# NEW: FEATURE 1 — PROJECT-WISE MAPPING TEMPLATE DB FUNCTIONS
# ═══════════════════════════════════════════════════════════

def save_mapping_template(project_name: str, mapping: dict, user_id: str):
    """
    NEW FUNCTION — Save mapping for a project to etl_mapping_template.
    Upserts on (project_name, source_column, user_id).
    Only saves non-skip mappings.
    """
    conn = get_conn()
    cur  = conn.cursor()
    try:
        for src, tgt in mapping.items():
            if tgt == "— skip —" or tgt not in TARGET_FIELDS:
                continue
            cur.execute(
                """
                INSERT INTO etl_mapping_template (project_name, source_column, target_column, user_id)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (project_name, source_column, user_id)
                DO UPDATE SET target_column = EXCLUDED.target_column,
                              created_at    = NOW()
                """,
                (project_name, src, tgt, user_id),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        release_conn(conn)


def fetch_mapping_template(project_name: str, user_id: str) -> dict:
    """
    NEW FUNCTION — Fetch saved mapping for a project.
    Returns {source_column: target_column}.
    """
    conn = get_conn()
    try:
        df = pd.read_sql_query(
            "SELECT source_column, target_column FROM etl_mapping_template "
            "WHERE project_name = %s AND user_id = %s",
            conn, params=(project_name, user_id)
        )
        if df.empty:
            return {}
        return dict(zip(df["source_column"], df["target_column"]))
    finally:
        release_conn(conn)


def fetch_user_projects(user_id: str) -> list:
    """
    Return project code.

    Admin  -> all projects
    User   -> only own projects
    """

    conn = get_conn()

    try:

        if is_admin():

            df = pd.read_sql_query(
                """
                SELECT DISTINCT project_name
                FROM etl_upload_log
                WHERE status = 'active'
                ORDER BY project_name
                """,
                conn
            )

        else:

            df = pd.read_sql_query(
                """
                SELECT DISTINCT project_name
                FROM etl_upload_log
                WHERE user_id = %s
                  AND status = 'active'
                ORDER BY project_name
                """,
                conn,
                params=(user_id,)
            )

        return df["project_name"].tolist() if not df.empty else []

    finally:
        release_conn(conn)

# ═══════════════════════════════════════════════════════════
# AUTOCOMPLETE / DROPDOWN API HELPERS (Requirements 3 + 4)
# ═══════════════════════════════════════════════════════════

# OPT 6: @st.cache_data(ttl=60) means these DB queries run at most once per minute
# instead of on every Streamlit rerun — dramatically reduces rerender latency.

@st.cache_data(ttl=60)
def get_project_names(user_id: str) -> list[str]:
    """Return DISTINCT active project code — powers Project Code dropdown."""
    conn = get_conn()
    try:
        if is_admin():

            df = pd.read_sql_query(
                """
                SELECT DISTINCT project_name
                FROM etl_upload_log
                WHERE status = 'active'
                ORDER BY project_name
                """,
                conn
            )

        else:

            df = pd.read_sql_query(
                """
                SELECT DISTINCT project_name
                FROM etl_upload_log
                WHERE user_id = %s
                AND status = 'active'
                ORDER BY project_name
                """,
                conn,
                params=(user_id,)
            )
        return df["project_name"].tolist() if not df.empty else []
    finally:
        release_conn(conn)


@st.cache_data(ttl=60)
def get_batch_codes(user_id: str, project_name: str = "") -> list[str]:
    """
    Return DISTINCT active batch codes.
    Admin -> all users
    User -> only own uploads
    """
    conn = get_conn()

    try:

        if is_admin():

            if project_name.strip():

                df = pd.read_sql_query(
                    """
                    SELECT DISTINCT batch_code
                    FROM etl_upload_log
                    WHERE status = 'active'
                      AND project_name = %s
                    ORDER BY batch_code
                    """,
                    conn,
                    params=(project_name,)
                )

            else:

                df = pd.read_sql_query(
                    """
                    SELECT DISTINCT batch_code
                    FROM etl_upload_log
                    WHERE status = 'active'
                    ORDER BY batch_code
                    """,
                    conn
                )

        else:

            if project_name.strip():

                df = pd.read_sql_query(
                    """
                    SELECT DISTINCT batch_code
                    FROM etl_upload_log
                    WHERE user_id = %s
                      AND status = 'active'
                      AND project_name = %s
                    ORDER BY batch_code
                    """,
                    conn,
                    params=(user_id, project_name)
                )

            else:

                df = pd.read_sql_query(
                    """
                    SELECT DISTINCT batch_code
                    FROM etl_upload_log
                    WHERE user_id = %s
                      AND status = 'active'
                    ORDER BY batch_code
                    """,
                    conn,
                    params=(user_id,)
                )

        return df["batch_code"].tolist() if not df.empty else []

    finally:
        release_conn(conn)


@st.cache_data(ttl=60)
def get_taxonomy_values(user_id: str) -> list[str]:
    """Return DISTINCT non-null taxonomy values from active SKU rows — powers Taxonomy dropdown."""
    conn = get_conn()
    try:
        df = pd.read_sql_query(
            """
            SELECT DISTINCT d.taxonomy
            FROM etl_data d
            JOIN etl_upload_log l ON d.upload_log_id = l.id
            WHERE l.user_id = %s
              AND l.status  = 'active'
              AND d.status  = 'active'
              AND d.taxonomy IS NOT NULL
              AND d.taxonomy <> ''
            ORDER BY d.taxonomy
            LIMIT 50
            """,
            conn, params=(user_id,)
        )
        return df["taxonomy"].tolist() if not df.empty else []
    finally:
        release_conn(conn)


# ═══════════════════════════════════════════════════════════
# NEW: FEATURE 3+4 — SEARCH + PAGINATED FILE LIST DB FUNCTIONS
# ═══════════════════════════════════════════════════════════

def fetch_upload_logs_paginated(
    user_id: str,
    project_name_filter: str = "",
    batch_code_filter: str = "",
    taxonomy_filter: str = "",
    limit: int = 20,
    offset: int = 0,
) -> pd.DataFrame:
    """
    NEW FUNCTION — Fetch upload logs with search filters and pagination.
    Taxonomy filter does a subquery into etl_data to find matching log IDs.
    """
    conn = get_conn()
    params = []
    where_clauses = ["l.status = 'active'"]

    if not is_admin():
        where_clauses.append("l.user_id = %s")
        params.append(user_id)

    if project_name_filter.strip():
        where_clauses.append("l.project_name ILIKE %s")
        params.append(f"%{project_name_filter.strip()}%")

    if batch_code_filter.strip():
        where_clauses.append("l.batch_code ILIKE %s")
        params.append(f"%{batch_code_filter.strip()}%")

    if taxonomy_filter.strip():
        where_clauses.append(
            "l.id IN (SELECT DISTINCT upload_log_id FROM etl_data "
            "WHERE taxonomy ILIKE %s AND status = 'active')"
        )
        params.append(f"%{taxonomy_filter.strip()}%")

    where_sql = " AND ".join(where_clauses)
    sql = f"""
        SELECT l.id, l.project_name, l.batch_code, l.author_name,
               l.file_name, l.upload_date, l.sku_count
        FROM etl_upload_log l
        WHERE {where_sql}
        ORDER BY l.upload_date DESC
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])
    try:
        df = pd.read_sql_query(sql, conn, params=params)
        return df
    finally:
        release_conn(conn)
        
def get_total_file_count(
    user_id: str,
    project_name_filter: str = "",
    batch_code_filter: str = "",
):
    conn = get_conn()
    cur = conn.cursor()

    params = [] 
    where_clauses = ["status = 'active'"]

    if not is_admin():
        where_clauses.append("user_id = %s")
        params.append(user_id)

    if project_name_filter.strip():
        where_clauses.append("project_name ILIKE %s")
        params.append(f"%{project_name_filter.strip()}%")

    if batch_code_filter.strip():
        where_clauses.append("batch_code ILIKE %s")
        params.append(f"%{batch_code_filter.strip()}%")

    sql = f"""
        SELECT
            COUNT(*) AS total_files,
            COALESCE(SUM(sku_count), 0) AS total_skus
        FROM etl_upload_log
        WHERE {' AND '.join(where_clauses)}
    """

    cur.execute(sql, params)

    total_files, total_skus = cur.fetchone()

    cur.close()
    release_conn(conn)

    return total_files, total_skus


def get_duplicate_count():
    conn = get_conn()
    cur = conn.cursor()

    sql = """
        SELECT COUNT(*)
        FROM etl_data e
        WHERE
            e.manufacturer_name IS NOT NULL
            AND e.manufacturer_part_number IS NOT NULL
            AND TRIM(e.manufacturer_name) <> ''
            AND TRIM(e.manufacturer_part_number) <> ''
            AND (
                LOWER(TRIM(e.manufacturer_name)),
                LOWER(TRIM(e.manufacturer_part_number))
            ) IN (
                SELECT
                    LOWER(TRIM(manufacturer_name)),
                    LOWER(TRIM(manufacturer_part_number))
                FROM etl_data
                WHERE
                    manufacturer_name IS NOT NULL
                    AND manufacturer_part_number IS NOT NULL
                    AND TRIM(manufacturer_name) <> ''
                    AND TRIM(manufacturer_part_number) <> ''
                GROUP BY
                    LOWER(TRIM(manufacturer_name)),
                    LOWER(TRIM(manufacturer_part_number))
                HAVING COUNT(*) > 1
            )
    """

    cur.execute(sql)
    count = cur.fetchone()[0]

    cur.close()
    release_conn(conn)

    return count

# ═══════════════════════════════════════════════════════════
# NEW: FEATURE 5 — TAXONOMY SEARCH DB FUNCTIONS
# ═══════════════════════════════════════════════════════════

def taxonomy_search_file_level(user_id: str, taxonomy_query: str) -> pd.DataFrame:

    conn = get_conn()

    try:

        if is_admin():

            df = pd.read_sql_query(
                """
                SELECT l.id AS upload_log_id,
                       l.project_name,
                       l.batch_code,
                       l.file_name,
                       l.upload_date,
                       l.sku_count,
                       COUNT(*) AS match_count
                FROM etl_data d
                JOIN etl_upload_log l
                    ON d.upload_log_id = l.id
                WHERE l.status = 'active'
                  AND d.status = 'active'
                  AND d.taxonomy ILIKE %s
                GROUP BY l.id, l.project_name, l.batch_code,
                         l.file_name, l.upload_date, l.sku_count
                ORDER BY l.upload_date DESC
                """,
                conn,
                params=(f"%{taxonomy_query}%",)
            )

        else:

            df = pd.read_sql_query(
                """
                SELECT l.id AS upload_log_id,
                       l.project_name,
                       l.batch_code,
                       l.file_name,
                       l.upload_date,
                       l.sku_count,
                       COUNT(*) AS match_count
                FROM etl_data d
                JOIN etl_upload_log l
                    ON d.upload_log_id = l.id
                WHERE l.user_id = %s
                  AND l.status = 'active'
                  AND d.status = 'active'
                  AND d.taxonomy ILIKE %s
                GROUP BY l.id, l.project_name, l.batch_code,
                         l.file_name, l.upload_date, l.sku_count
                ORDER BY l.upload_date DESC
                """,
                conn,
                params=(user_id, f"%{taxonomy_query}%")
            )

        return df

    finally:
        release_conn(conn)

def taxonomy_search_global(user_id: str, taxonomy_query: str) -> pd.DataFrame:

    conn = get_conn()

    try:

        if is_admin():

            df = pd.read_sql_query(
                """
                SELECT d.asn_altiusnxt_stock_number,
                       d.sku_id,
                       d.initial_description,
                       d.taxonomy,
                       d.brand_name,
                       d.category,
                       l.project_name,
                       l.batch_code,
                       l.file_name
                FROM etl_data d
                JOIN etl_upload_log l
                    ON d.upload_log_id = l.id
                WHERE l.status = 'active'
                  AND d.status = 'active'
                  AND d.taxonomy ILIKE %s
               
                """,
                conn,
                params=(f"%{taxonomy_query}%",)
            )

        else:

            df = pd.read_sql_query(
                """
                SELECT d.asn_altiusnxt_stock_number,
                       d.sku_id,
                       d.initial_description,
                       d.taxonomy,
                       d.brand_name,
                       d.category,
                       l.project_name,
                       l.batch_code,
                       l.file_name
                FROM etl_data d
                JOIN etl_upload_log l
                    ON d.upload_log_id = l.id
                WHERE l.user_id = %s
                  AND l.status = 'active'
                  AND d.status = 'active'
                  AND d.taxonomy ILIKE %s
                
                """,
                conn,
                params=(user_id, f"%{taxonomy_query}%")
            )

        return df

    finally:
        release_conn(conn)


def fetch_etl_data_for_log_with_taxonomy(
    log_id: int,
    taxonomy_filter: str = ""
) -> pd.DataFrame:

    conn = get_conn()

    try:

        if taxonomy_filter.strip():

            df = pd.read_sql_query(
                """
                SELECT
                    asn_altiusnxt_stock_number,
                    sku_id,
                    initial_description,
                    manufacturer_name,
                    brand_name,
                    category,
                    taxonomy,
                    file_name,
                    upload_date
                FROM etl_data
                WHERE upload_log_id = %s
                  AND taxonomy ILIKE %s
                ORDER BY asn_altiusnxt_stock_number
                """,
                conn,
                params=(log_id, f"%{taxonomy_filter}%")
            )

        else:

            df = pd.read_sql_query(
                """
                SELECT
                    asn_altiusnxt_stock_number,
                    sku_id,
                    initial_description,
                    manufacturer_name,
                    brand_name,
                    category,
                    taxonomy,
                    file_name,
                    upload_date
                FROM etl_data
                WHERE upload_log_id = %s
                ORDER BY asn_altiusnxt_stock_number
                """,
                conn,
                params=(log_id,)
            )

        return df

    finally:
        release_conn(conn)


# ═══════════════════════════════════════════════════════════
# 12. AUTH — Login / Signup page
# (MOVED HERE — must be defined before init_state() call and login gate)
# ═══════════════════════════════════════════════════════════

# --- MOVE START ---
# --- CHANGE START --- PATCH 2: is_logged_in helper for strict session gate
def is_logged_in():
    return st.session_state.get("user_id") is not None
# --- CHANGE END ---


def show_login_page():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("""
            <h1 style="text-align:center; color:#ffffff; margin-top:10px;">
                🔀 ETL Visual Data Mapper
            </h1>
            <p style="text-align:center; color:#ffffff; margin-bottom:10px;">
                Sign in or create an account
            </p>
        """, unsafe_allow_html=True)

        st.markdown("<p style='text-align:center; color:#facc15; margin-bottom:5px;'>Choose Action</p>", unsafe_allow_html=True)
        mode = st.radio("", ["Sign In", "Sign Up"], horizontal=True)
        st.markdown(f"<h3 style='text-align:center; color:#ffffff;'>🔐 {mode}</h3>", unsafe_allow_html=True)

        email    = st.text_input("Email",    placeholder="you@example.com")
        password = st.text_input("Password", placeholder="••••••••", type="password")

        if mode == "Sign In":
            
            if st.button("Sign In", type="primary", use_container_width=True):
                if not email or not password:
                    st.error("Please enter both email and password.")
                    return
                try:
                    supabase = get_supabase()
                    resp     = supabase.auth.sign_in_with_password({"email": email, "password": password})
                    user     = resp.user

                    if not user:
                        st.error("Invalid login response. Please try again.")
                        return
                    # --- CHANGE START --- PATCH 2: Store all three auth keys on successful login
                    st.session_state.user_id    = str(user.id)
                    st.session_state.user_email = user.email
                    st.session_state.user_role  = get_role_for_user(str(user.id), user.email)
                    st.query_params["uid"] = str(user.id)
                    st.query_params["email"] = user.email
                    st.query_params["role"] = st.session_state.user_role
                    # --- CHANGE END ---
                    st.success("Login successful!")
                    st.rerun()
                except Exception as e:
                    err_msg = str(e)

                    if "email not confirmed" in err_msg.lower():
                        st.warning("You must confirm your email before signing in.")
                    else:
                        st.error(f"Login failed: {err_msg}")

        # --- CHANGE START --- PATCH 3: Sign Up with email confirmation message + input validation
        elif mode == "Sign Up":
            if st.button("Create Account", type="primary", use_container_width=True):
                if not email or not password:
                    st.error("Please enter both email and password.")
                    return
                if len(password) < 6:
                    st.error("Password must be at least 6 characters.")
                    return
                try:
                    supabase = get_supabase()
                    supabase.auth.sign_up({"email": email, "password": password})
                    st.success(
                        "✅ Account created! Please Sign in"
                    )
                except Exception as e:
                    err_msg = str(e)
                    if "already registered" in err_msg.lower() or "already exists" in err_msg.lower():
                        st.error("An account with this email already exists. Please sign in instead.")
                    else:
                        st.error(f"Signup failed: {err_msg}")
        # --- CHANGE END ---
# --- MOVE END ---


# ═══════════════════════════════════════════════════════════
# 4. SESSION STATE INIT
# ═══════════════════════════════════════════════════════════

def save_workflow_state():

    if not st.session_state.get("_df_path"):
        return
    workflow_state = {
         "step": st.session_state.get("step", 1),
        "mapping": st.session_state.get("mapping", {}),
        "auto_mapped": st.session_state.get("auto_mapped", {}),
        "attr_selected": st.session_state.get("attr_selected", []),
        "select_all_prev": st.session_state.get("select_all_prev", False),
        "unmapped_fields": st.session_state.get("unmapped_fields", []),
        "source_columns": st.session_state.get("source_columns", []),
        "project_name": st.session_state.get("project_name", ""),
        "batch_code": st.session_state.get("batch_code", ""),
        "file_name": st.session_state.get("file_name"),
        "upload_date": st.session_state.get("upload_date"),
        "sku_count": st.session_state.get("sku_count"),
        }

    df_path = st.session_state.get("_df_path")

    if not df_path:
        return

    state_path = df_path + ".state.json"

    with open(state_path, "w") as f:
        json.dump(workflow_state, f)     


def restore_workflow_state():

    if not st.session_state.get("_df_path"):
        return

    df_path = st.session_state.get("_df_path")

    if not df_path:
        return

    state_path = df_path + ".state.json"

    if not os.path.exists(state_path):
        return

    with open(state_path, "r") as f:
        workflow_state = json.load(f)

    for k, v in workflow_state.items():
        st.session_state[k] = v 

    if "auto_mapped" not in st.session_state:
        st.session_state.auto_mapped = {}   

    if "attr_selected" not in st.session_state:
        st.session_state.attr_selected = []       

def init_state():
    # Auth keys — NEVER cleared by "Process Another File"
    for k, v in [("user_id", None), ("user_email", None), ("user_role", "user")]:
        if k not in st.session_state:
            st.session_state[k] = v

    # ETL workflow keys — reset on new file
    etl_defaults = {
        "step":             1,
        "map_page":         0,
        "submitted":        False,
        "file_name":        None,
        "upload_date":      None,
        "sku_count":        None,
        "df":               None,
        "_df_path":         None,   # persistent cache file path
        "_df_orig_suffix":  None,   # original file extension for reload
        "source_columns":   [],
        "attribute_columns": [],
        "mapping":          {},
        "attr_selected":    [],
        "unmapped_fields":  [],
        "project_name":     "",
        "batch_code":       "",
        "select_all_attrs": False,
        "auto_mapped":      {},
        # NEW: pagination state
        "file_list_offset": 0,
        "file_list_rows":   [],
        # NEW: search state
        "search_project":   "",
        "search_batch":     "",
        # NEW: taxonomy search state
        "tax_search_query": "",
        "tax_search_mode":  "File-level (Recommended)",
        "tax_search_results": None,
        "processing_completed": False,
        "inserted_rows": None,
        "upload_log_id": None,
        # NEW: view panel state per log_id stored dynamically
    }
    for k, v in etl_defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_state()

# ── Restore session + workflow after browser refresh ─────────────────────

qp = st.query_params

# Restore authentication
if qp.get("uid") and qp.get("email"):

    st.session_state.user_id = qp.get("uid")
    st.session_state.user_email = qp.get("email")
    st.session_state.user_role = qp.get("role", "user")

# Restore workflow state
if qp.get("fp") and os.path.exists(qp.get("fp")):

    st.session_state._df_path = qp.get("fp")
    st.session_state._df_orig_suffix = qp.get("ds", "")

    try:
        st.session_state.step = int(qp.get("step", 1))
    except:
        st.session_state.step = 1

    restore_workflow_state()


# ── Login gate ──
#if not is_logged_in():
 #   show_login_page()
  #  st.stop()




#st.markdown(
 #   f"<p style='color:#facc15; font-weight:600; padding:7px;'>SESSION ROLE: "
  #  f"<span style='color:#ffffff'>{st.session_state.user_role}</span></p>",
   # unsafe_allow_html=True
#)





# ═══════════════════════════════════════════════════════════
# 5. SHARED UI HELPERS
# ═══════════════════════════════════════════════════════════

def _sync_query_params():
    """Write all restorable session state into query_params.

    Called after every step transition so that a browser refresh restores the
    exact same step, file, mapping, attributes, and unmapped fields — without
    restarting from the upload page.

    Query-param key budget (keys kept short to stay well under browser URL limits):
      uid, email, role  — auth
      step              — current step number
      fn                — file_name
      ud                — upload_date
      sc                — sku_count (int)
      pn                — project_name
      bc                — batch_code
      fp                — _df_path  (cache file path on server)
      ds                — _df_orig_suffix
      scols             — source_columns  (JSON list)
      mp                — mapping         (JSON dict)
      at                — attr_selected   (JSON list)
      uf                — unmapped_fields (JSON list)
    """
    ss = st.session_state
    qp = st.query_params

    qp["uid"]   = ss.get("user_id", "") or ""
    qp["email"] = ss.get("user_email", "") or ""
    qp["role"]  = ss.get("user_role", "user") or "user"
    qp["step"]  = str(ss.get("step", 1))

    if ss.get("file_name"):
        qp["fn"] = ss["file_name"]
        qp["ud"] = ss.get("upload_date", "")
        qp["sc"] = str(ss.get("sku_count", 0) or 0)
        qp["pn"] = ss.get("project_name", "")
        qp["bc"] = ss.get("batch_code", "")

    if ss.get("_df_path"):
        qp["fp"] = ss["_df_path"]
        qp["ds"] = ss.get("_df_orig_suffix", "")

    # Encode lists/dicts as JSON — only when they carry real data
    # to avoid bloating the URL unnecessarily.
            
    
def progress_bar(current_step):

    labels = [
        "Upload",
        "Field Mapping",
        "Attributes",
        "Unmapped",
        "Summary",
        "Result"
    ]

    cols = st.columns(len(labels))

    for i, label in enumerate(labels, start=1):

        btn_type = "primary" if i == current_step else "secondary"

        if cols[i-1].button(
            label,
            key=f"step_btn_{i}",
            use_container_width=True,
            type=btn_type
        ):
            st.session_state.step = i
            save_workflow_state()
            _sync_query_params()
            st.rerun()

def file_info_strip():
    if st.session_state.file_name:
        st.markdown(
            f'<div class="file-strip">'
            f'📄 <strong>{st.session_state.file_name}</strong>'
            f'&nbsp;|&nbsp;<span>📅 {st.session_state.upload_date}</span>'
            f'&nbsp;|&nbsp;<span>🔢 {st.session_state.sku_count:,} SKUs</span>'
            f'</div>',
            unsafe_allow_html=True,
        )


def used_targets() -> set:
    return {v for v in st.session_state.mapping.values() if v != "— skip —"}


def read_uploaded(file) -> pd.DataFrame:

    name = file.name.lower()

    # CSV FILES
    if name.endswith(".csv"):

        try:

            return pd.read_csv(
                file,
                dtype=str,
                engine="python",
                encoding="utf-8",
                keep_default_na=False,
                na_filter=False,
                on_bad_lines="warn"
            ).fillna("")

        except UnicodeDecodeError:

            file.seek(0)

            return pd.read_csv(
                file,
                dtype=str,
                engine="python",
                encoding="latin1",
                keep_default_na=False,
                na_filter=False,
                on_bad_lines="warn"
            ).fillna("")

    # EXCEL FILES
    elif name.endswith(".xlsx") or name.endswith(".xls"):

        return pd.read_excel(
            file,
            dtype=str,
            engine="openpyxl"
        ).fillna("")

    # ODS FILES
    elif name.endswith(".ods"):

        return pd.read_excel(
            file,
            dtype=str,
            engine="odf"
        ).fillna("")

    else:
        raise ValueError(f"Unsupported file format: {name}")
   
# OPT 4 (REVISED): On-demand DataFrame loader.
# Primary path: load from a parquet cache file (10-50× faster than re-parsing CSV/XLSX).
# The parquet cache is written alongside the original upload cache file on first load.
# Fallback: re-parse the original file if parquet cache is missing.
def _load_df() -> pd.DataFrame | None:
    """Reload DataFrame from parquet cache (fast) or original file (fallback)."""
    path = st.session_state.get("_df_path")
    if not path or not os.path.exists(path):
        return st.session_state.get("df")

    # Fast path — parquet cache
    parquet_path = path + ".parquet"
    if os.path.exists(parquet_path):
        try:
            return pd.read_parquet(parquet_path)
        except Exception:
            pass  # fall through to raw file

    # Slow path — re-read original file and write parquet cache for next time
    try:
        df = read_uploaded(open(path, "rb"))
        try:
            df.to_parquet(parquet_path, index=False)
        except Exception:
            pass  # parquet write failure is non-fatal
        return df
    except Exception:
        return st.session_state.get("df")


# ═══════════════════════════════════════════════════════════
# AUTO MAPPING HELPER (unchanged)
# ═══════════════════════════════════════════════════════════

def _normalise(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def auto_suggest_mapping(source_cols: list[str]) -> dict[str, str]:
    suggestions: dict[str, str] = {}
    for src in source_cols:
        src_norm  = _normalise(src)
        src_words = set(src_norm.split())
        best_tgt  = None
        best_score = 0.0
        for tgt in TARGET_FIELDS:
            tgt_norm  = _normalise(tgt)
            tgt_words = set(tgt_norm.split())
            if not tgt_words:
                continue
            overlap = len(src_words & tgt_words)
            score   = overlap / len(tgt_words)
            if src_norm == tgt_norm:
                score = 1.0
            if score > best_score and score >= 0.6:
                best_score = score
                best_tgt   = tgt
        if best_tgt:
            suggestions[src] = best_tgt
    return suggestions


# ═══════════════════════════════════════════════════════════
# NEW: FEATURE 1 — APPLY PROJECT MAPPING TEMPLATE
# ═══════════════════════════════════════════════════════════

def apply_project_mapping_template(source_cols: list, project_name: str, user_id: str) -> tuple[dict, dict]:
    """
    NEW FUNCTION — Load saved mapping for project and apply to source_cols.
    Returns (applied_mapping, project_auto_mapped).
    applied_mapping: {source_col: target_col or "— skip —"}
    project_auto_mapped: {source_col: target_col} — only cols matched from template
    """
    template = fetch_mapping_template(project_name, user_id)
    if not template:
        return {}, {}

    # Build normalised lookup: normalised_source -> target
    norm_template = {_normalise(k): v for k, v in template.items()}

    applied = {}
    matched = {}
    for col in source_cols:
        col_norm = _normalise(col)
        # 1. Exact match
        if col in template:
            applied[col] = template[col]
            matched[col] = template[col]
        # 2. Case-insensitive / normalised match
        elif col_norm in norm_template:
            tgt = norm_template[col_norm]
            applied[col] = tgt
            matched[col] = tgt
        # 3. No match — leave for fuzzy auto_suggest_mapping
    return applied, matched


# ═══════════════════════════════════════════════════════════
# NEW: FEATURE 2 — FAVORITES / PROJECT GROUPING SECTION
# ═══════════════════════════════════════════════════════════

def render_favorites_section():
    """
    NEW FUNCTION — Display projects grouped with their file counts.
    Clicking a project code filters the file list below.
    """
    uid = st.session_state.get("user_id")
    if not uid:
        return

    try:
        projects = fetch_user_projects(uid)
    except Exception as e:
        st.warning(f"Could not load projects: {e}")
        return

    if not projects:
        return

    with st.expander("📁 Favorites — Project Groups", expanded=False):
        st.caption("Click a project to filter the file list below.")
        cols_per_row = 4
        chunks = [projects[i:i+cols_per_row] for i in range(0, len(projects), cols_per_row)]
        for chunk in chunks:
            row_cols = st.columns(cols_per_row)
            for i, proj in enumerate(chunk):
                with row_cols[i]:
                    # Get file count for this project
                    try:
                        conn = get_conn()
                        cur  = conn.cursor()
                        cur.execute(
                            "SELECT COUNT(*) FROM etl_upload_log "
                            "WHERE project_name = %s AND user_id = %s AND status = 'active'",
                            (proj, uid)
                        )
                        cnt = cur.fetchone()[0]
                        cur.close()
                        release_conn(conn)
                    except Exception:
                        cnt = "?"

                    btn_label = f"📁 {proj}\n({cnt} file{'s' if cnt != 1 else ''})"
                    if st.button(btn_label, key=f"fav_proj_{proj}", use_container_width=True):
                        st.session_state.search_project   = proj
                        st.session_state.file_list_offset = 0
                        st.session_state.file_list_rows   = []
                        st.rerun()


# ═══════════════════════════════════════════════════════════
# NEW: FEATURE 3+4 — SEARCH + PAGINATED FILE LIST SECTION
# ═══════════════════════════════════════════════════════════

def render_search_and_file_list():
    """
    NEW FUNCTION — Search inputs + paginated file list displayed ABOVE upload.
    """
    uid = st.session_state.get("user_id")
    if not uid:
        return

    st.markdown("""
<h3 style="
    font-size:22px;
    font-weight:600;
    margin-bottom:8px;
    color: #ffffff;
">
🔍 Search Uploaded Files
</h3>
""", unsafe_allow_html=True)

    # ── Search inputs with autocomplete dropdowns ──────────────────
    s1, s2, s4 = st.columns([4, 2, 3])

    # Fetch dropdown options from DB (cached per render via try/except)
    try:
        proj_options = get_project_names(uid)
    except Exception:
        proj_options = []
    try:
        batch_options = get_batch_codes(uid, st.session_state.search_project)
    except Exception:
        batch_options = []
    

    with s1:
        # Selectbox with blank "All" option at top; user types to filter
        proj_list = [""] + proj_options
        cur_proj  = st.session_state.search_project
        proj_idx  = proj_list.index(cur_proj) if cur_proj in proj_list else 0
        pf = st.selectbox(
            "Project Code",
            options=proj_list,
            index=proj_idx,
            format_func=lambda x: "— All Projects —" if x == "" else x,
            key="inp_search_project",
        )
    with s2:
        batch_list  = [""] + batch_options
        cur_batch   = st.session_state.search_batch
        batch_idx   = batch_list.index(cur_batch) if cur_batch in batch_list else 0
        bf = st.selectbox(
            "Batch Code",
            options=batch_list,
            index=batch_idx,
            format_func=lambda x: "— All Batches —" if x == "" else x,
            key="inp_search_batch",
        )
    
    with s4:
        st.markdown("<br>", unsafe_allow_html=True)
        search_clicked = st.button("🔍 Search", type="primary", use_container_width=True, key="btn_search_main")
        clear_clicked  = st.button("✖ Clear",  use_container_width=True, key="btn_clear_search")

    if clear_clicked:
        st.session_state.search_project   = ""
        st.session_state.search_batch     = ""
        
        st.session_state.file_list_offset = 0
        st.session_state.file_list_rows   = []
        st.rerun()

    if search_clicked:
        st.session_state.search_project   = pf
        st.session_state.search_batch     = bf
        
        st.session_state.file_list_offset = 0
        st.session_state.file_list_rows   = []

    # ── Load initial batch if list is empty ──
    if len(st.session_state.file_list_rows) == 0:
        try:
            initial = fetch_upload_logs_paginated(
                user_id=uid,
                project_name_filter=st.session_state.search_project,
                batch_code_filter=st.session_state.search_batch,
                taxonomy_filter="",
                limit=20,
                offset=0,
            )
            st.session_state.file_list_offset = 20
            if not initial.empty:
                st.session_state.file_list_rows = initial.to_dict("records")
        except Exception as e:
            st.error(f"Could not load file list: {e}")
            return

    rows = st.session_state.file_list_rows

    # ── OPT 5: Global Export Section ─────────────────────────────────────────
    # fetch_all_etl_export() used to run on EVERY rerun (very slow for large datasets).
    # Now it only runs when the user explicitly clicks "Prepare Export".
    # Result is cached in session_state["_export_cache"] until cleared.
    try:
        export_ready = st.session_state.get("_export_cache") is not None

        if st.button("📦 Prepare Export (All Files)", key="btn_prepare_export"):
            with st.spinner("Generating export…"):
                st.session_state["_export_cache"] = fetch_all_etl_export(uid)
            export_ready = True

        if export_ready:
            export_df = st.session_state["_export_cache"]
            if not export_df.empty:
                # CSV Export
                csv_data = export_df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    label="⬇ Download ALL as CSV",
                    data=csv_data,
                    file_name="all_uploaded_etl_data.csv",
                    mime="text/csv",
                    key="download_all_csv",
                )

                # Remove timezone info for Excel compatibility
                excel_df = export_df.copy()
                for col in excel_df.columns:
                    if pd.api.types.is_datetime64tz_dtype(excel_df[col]):
                        excel_df[col] = excel_df[col].dt.tz_localize(None)

                excel_buffer = BytesIO()
                with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
                    excel_df.to_excel(writer, index=False)

                st.download_button(
                    label="⬇ Download ALL as Excel",
                    data=excel_buffer.getvalue(),
                    file_name="all_uploaded_etl_data.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="download_all_excel",
                )

                if st.button("🗑 Clear Export Cache", key="btn_clear_export"):
                    st.session_state.pop("_export_cache", None)
                    st.rerun()

    except Exception as e:
        st.error(f"Global export failed: {e}")

    if not rows:
        st.info("No uploaded files found. Try adjusting search filters.")
    else:
        total_files, total_skus = get_total_file_count(
            user_id=uid,
            project_name_filter=st.session_state.search_project,
            batch_code_filter=st.session_state.search_batch,
        )
        duplicate_count = get_duplicate_count()

        c1, c2, c3 = st.columns(3)
        
    

        with c1:
            st.metric(
                "Total Files",
                f"{total_files:,}"
            )

        with c2:
            st.metric(
                "Total SKUs",
                f"{total_skus:,}"
            )
            
        with c3:
            st.metric(
                "Duplicate Rows",
                f"{duplicate_count:,}"
            )    

        st.caption(
            f"Showing {len(rows)} of {total_files:,} file(s)"
        )

        render_file_cards(rows)
        
        

        # ── FEATURE 4: Load More button ──
        if st.button("⬇ Load More", key="btn_load_more_search"):
            try:
                more = fetch_upload_logs_paginated(
                    user_id=uid,
                    project_name_filter=st.session_state.search_project,
                    batch_code_filter=st.session_state.search_batch,
                    taxonomy_filter="",
                    limit=20,
                    offset=st.session_state.file_list_offset,
                )
                if more.empty:
                    st.info("No more records to load.")
                else:
                    # APPEND — do NOT overwrite
                    existing_ids = {r["id"] for r in st.session_state.file_list_rows}
                    new_rows = [r for r in more.to_dict("records") if r["id"] not in existing_ids]
                    st.session_state.file_list_rows.extend(new_rows)
                    st.session_state.file_list_offset += 20
                    st.rerun()
            except Exception as e:
                st.error(f"Load more failed: {e}")


def render_file_cards(rows: list, taxonomy_filter: str = ""):
    """
    Render file cards with View File button.
    Status column is hidden from UI — cards always render with clean white background.
    Delete button is shown ONLY to admin users (Requirement 1 UI layer).
    """
    admin = is_admin()

    for row in rows:
        rid = int(row["id"])

        col_info, col_actions = st.columns([7, 3])

        with col_info:
            st.markdown(
                f'<div style="background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;padding:10px 14px;margin-bottom:8px">'
                f'<strong style="color:#1e293b">📁 {row["project_name"]}</strong>'
                f' &nbsp;/&nbsp; <span style="color:#4b5563">🏷 {row["batch_code"]}</span>'
                f'<br><span class="file-card-meta">'
                f'📄 {row["file_name"]}  ·  '
                f'📅 {str(row["upload_date"])[:10]}  ·  '
                f'🔢 {int(row["sku_count"]):,} SKUs'
                f'  ·  ✍ {row.get("author_name","—")}'
                f'</span></div>',
                unsafe_allow_html=True,
            )

        with col_actions:
            if st.button("👁 View File", key=f"fc_view_{rid}", use_container_width=True):
                st.session_state[f"fc_show_{rid}"] = not st.session_state.get(f"fc_show_{rid}", False)

   

            # ── Admin-only delete button (UI layer guard) ──
            # ── Admin-only permanent delete ──
            if admin:

                confirm_key = f"fc_confirm_del_{rid}"

                # FIRST CLICK → show confirmation
                if not st.session_state.get(confirm_key, False):

                    if st.button(
                        "🗑 Delete",
                        key=f"fc_del_{rid}",
                        use_container_width=True
                    ):

                        st.session_state[confirm_key] = True
                        st.rerun()

                # CONFIRMATION UI
                else:

                    st.warning(
                        "⚠ This will permanently delete:\n\n"
                        "• Uploaded file\n"
                        "• Cached parquet/state files\n"
                        "• All related database records\n\n"
                        "This action cannot be undone."
                    )

                    dc1, dc2 = st.columns(2)

                    # CONFIRM DELETE
                    with dc1:

                        if st.button(
                            "✅ Confirm Permanent Delete",
                            key=f"fc_del_yes_{rid}",
                            use_container_width=True
                        ):

                            try:

                                hard_delete_log(rid)

                                st.session_state.file_list_rows = [
                                    r for r in st.session_state.file_list_rows
                                    if int(r["id"]) != rid
                                ]

                                st.session_state.pop(confirm_key, None)

                                st.success(
                                    f"Record #{rid} permanently deleted."
                                )

                                st.rerun()

                            except Exception as e:

                                st.error(f"Delete failed: {e}")

                    # CANCEL
                    with dc2:

                        if st.button(
                            "❌ Cancel",
                            key=f"fc_del_no_{rid}",
                            use_container_width=True
                        ):

                            st.session_state.pop(confirm_key, None)

                            st.info("Delete cancelled.")

                            st.rerun()
        # ── Inline View Panel ──
        if st.session_state.get(f"fc_show_{rid}", False):
            try:
                data_df = fetch_etl_data_for_log_with_taxonomy(rid, taxonomy_filter)
            except Exception as e:
                st.error(f"Could not load data: {e}")
                data_df = pd.DataFrame()

            if data_df.empty:
                st.info("No rows found for this file.")
            else:
                label = (
                    f"📋 {len(data_df):,} matching SKU rows (taxonomy: '{taxonomy_filter}')"
                    if taxonomy_filter.strip()
                    else f"📋 {len(data_df):,} SKU rows (first 100 shown)"
                )
                st.markdown(f"**{label}** — File: `{row['file_name']}`")
                st.dataframe(data_df, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════
# NEW: FEATURE 5 — TAXONOMY SEARCH SECTION
# ═══════════════════════════════════════════════════════════


def render_taxonomy_search_section():
    """
    Dedicated taxonomy search with file-level and global modes.
    """

    uid = st.session_state.get("user_id")

    if not uid:
        return

    with st.expander("🔬 Taxonomy Search", expanded=False):

        st.caption(
            "Search SKUs by taxonomy across your uploaded files."
        )

        # ==========================================
        # INPUTS
        # ==========================================

        mode = st.radio(
            "Search Mode",
            [
                "File-level (Recommended)",
                "Global (All Rows)"
            ],
            horizontal=True,
            key="tax_mode_radio",
        )

        tax_q = st.text_input(
            "Taxonomy keyword",
            placeholder="e.g. Fasteners",
            key="tax_search_input"
        )

        # ==========================================
        # SEARCH BUTTON
        # ==========================================

        if st.button(
            "🔬 Run Taxonomy Search",
            type="primary",
            key="btn_tax_search"
        ):

            if not tax_q.strip():

                st.warning(
                    "Enter a taxonomy keyword to search."
                )

            else:

                # Save search state
                st.session_state.tax_search_query = (
                    tax_q.strip()
                )

                st.session_state.tax_search_mode = (
                    mode
                )

                # Force fresh search
                st.session_state.tax_search_results = None

                st.rerun()

        # ==========================================
        # DISPLAY RESULTS
        # ==========================================

        if st.session_state.get("tax_search_query"):

            q = st.session_state.get(
                "tax_search_query",
                ""
            )

            current_mode = st.session_state.get(
                "tax_search_mode",
                "File-level (Recommended)"
            )

            # ==========================================
            # RUN SEARCH
            # ==========================================

            if st.session_state.get(
                "tax_search_results"
            ) is None:

                try:

                    if current_mode == "File-level (Recommended)":

                        results = taxonomy_search_file_level(
                            uid,
                            q
                        )

                    else:

                        results = taxonomy_search_global(
                            uid,
                            q
                        )

                    st.session_state.tax_search_results = (
                        results
                    )

                except Exception as e:

                    st.error(
                        f"Taxonomy search failed: {e}"
                    )

                    return

            results = st.session_state.get(
                "tax_search_results",
                pd.DataFrame()
            )

            # ==========================================
            # EMPTY RESULTS
            # ==========================================

            if results.empty:

                st.info(
                    f"No matches found for taxonomy: '{q}'"
                )

                return

            # ==========================================
            # FILE LEVEL MODE
            # ==========================================

            if current_mode == "File-level (Recommended)":

                total_taxonomy_count = (
                    results["match_count"].sum()
                )

                st.success(
                    f"Found {len(results):,} file(s) "
                    f"with {total_taxonomy_count:,} total taxonomy matches"
                )

                # ==========================================
                # DOWNLOAD ALL MATCHING FILES
                # ==========================================

                if not results.empty:

                    log_ids = (
                        results["upload_log_id"]
                        .tolist()
                    )

                    conn = get_conn()

                    try:

                        placeholders = ",".join(
                            ["%s"] * len(log_ids)
                        )

                        export_df = pd.read_sql_query(
                            f"""
                            SELECT *
                            FROM etl_data
                            WHERE upload_log_id IN ({placeholders})
                              AND status = 'active'
                            """,
                            conn,
                            params=log_ids
                        )

                    finally:
                        release_conn(conn)

                    # Remove timezone columns
                    for col in export_df.columns:

                        try:

                            if pd.api.types.is_datetime64tz_dtype(
                                export_df[col]
                            ):

                                export_df[col] = (
                                    export_df[col]
                                    .dt.tz_localize(None)
                                )

                        except Exception:
                            pass

                    excel_buffer = BytesIO()

                    with pd.ExcelWriter(
                        excel_buffer,
                        engine="openpyxl"
                    ) as writer:

                        export_df.to_excel(
                            writer,
                            index=False
                        )

                    st.download_button(
                        label="⬇ Download All Matching Files",
                        data=excel_buffer.getvalue(),
                        file_name=f"taxonomy_{q}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                        key=f"download_file_tax_{q}_{len(results)}"
                    )

                # ==========================================
                # FILE CARDS
                # ==========================================

                for _, row in results.iterrows():

                    lid = int(row["upload_log_id"])

                    col_info, col_btn = st.columns([8, 2])

                    with col_info:

                        st.markdown(
                            f'''
                            <div class="file-card">
                                <strong>{row["project_name"]}</strong>
                                / {row["batch_code"]}<br>

                                <span class="file-card-meta">
                                    📄 {row["file_name"]}
                                    · 📅 {str(row["upload_date"])[:10]}
                                    · 🔢 {int(row["sku_count"]):,} SKUs
                                </span>

                                <span class="taxonomy-match-badge">
                                    ✅ {int(row["match_count"])} taxonomy matches
                                </span>
                            </div>
                            ''',
                            unsafe_allow_html=True,
                        )

                    with col_btn:

                        if st.button(
                            "👁 View File",
                            key=f"tax_view_{lid}",
                            use_container_width=True
                        ):

                            tk = f"tax_show_{lid}"

                            st.session_state[tk] = (
                                not st.session_state.get(
                                    tk,
                                    False
                                )
                            )

                    if st.session_state.get(
                        f"tax_show_{lid}",
                        False
                    ):

                        try:

                            view_df = (
                                fetch_etl_data_for_log_with_taxonomy(
                                    lid,
                                    q
                                )
                            )

                        except Exception as e:

                            st.error(
                                f"Could not load: {e}"
                            )

                            view_df = pd.DataFrame()

                        if view_df.empty:

                            st.info("No rows found.")

                        else:

                            st.markdown(
                                f"**📋 {len(view_df):,} matching rows**"
                            )

                            st.dataframe(
                                view_df,
                                use_container_width=True,
                                hide_index=True
                            )

            # ==========================================
            # GLOBAL MODE
            # ==========================================

            else:

                st.success(
                    f"Found {len(results):,} SKU row(s) "
                    f"matching taxonomy: '{q}'"
                )

                # ==========================================
                # DOWNLOAD GLOBAL RESULTS
                # ==========================================

                export_df = results.copy()

                for col in export_df.columns:

                    try:

                        if pd.api.types.is_datetime64tz_dtype(
                            export_df[col]
                        ):

                            export_df[col] = (
                                export_df[col]
                                .dt.tz_localize(None)
                            )

                    except Exception:
                        pass

                excel_buffer = BytesIO()

                with pd.ExcelWriter(
                    excel_buffer,
                    engine="openpyxl"
                ) as writer:

                    export_df.to_excel(
                        writer,
                        index=False
                    )

                st.download_button(
                    label="⬇ Download Global Taxonomy Results",
                    data=excel_buffer.getvalue(),
                    file_name=f"global_taxonomy_{q}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                    key=f"download_global_tax_{q}_{len(results)}"
                )

                # ==========================================
                # SHOW GLOBAL RESULTS
                # ==========================================

                st.dataframe(
                    results,
                    use_container_width=True,
                    hide_index=True
                )



# =========================================================
# ATTRIBUTE SECTION SPLITTER
# =========================================================

def split_primary_and_attribute_columns(all_columns):

    attr_start_idx = None

    for idx, col in enumerate(all_columns):

        col_clean = (
            str(col)
            .strip()
            .lower()
        )

        # attribute section starts here
        if (
            col_clean.startswith("att")
            or col_clean.startswith("attr")
            or col_clean.startswith("attribute")
        ):

            attr_start_idx = idx
            break

    # -----------------------------------------------------
    # NO ATTRIBUTE SECTION
    # -----------------------------------------------------

    if attr_start_idx is None:

        primary_columns = all_columns
        attribute_columns = []

    # -----------------------------------------------------
    # SPLIT FROM FIRST ATTRIBUTE COLUMN
    # -----------------------------------------------------

    else:

        primary_columns = all_columns[:attr_start_idx]

        attribute_columns = all_columns[attr_start_idx:]

    return primary_columns, attribute_columns                


# ═══════════════════════════════════════════════════════════
# 6. STEP 1 — FILE UPLOAD (MODIFIED — adds project mapping suggestion)
# ═══════════════════════════════════════════════════════════

def step_upload():
    progress_bar(1)
    st.markdown( """
<h3 style="
    font-size:22px;
    font-weight:600;
    margin-bottom:8px;
    color:#ffffff;            
">
📂 Step 1 - Upload Source File
</h3>
""", unsafe_allow_html=True)
    st.caption("Upload your Excel or CSV file. File name, date, and SKU count are extracted automatically.")

    uploaded = st.file_uploader("Drop file here", type=["csv", "xlsx", "ods"])

    if not uploaded:
        # OPT 3: hint user that CSV is fastest for large files
        st.info("Accepted formats: .csv (fastest for 10k+ rows)  ·  .xlsx  ·  .ods")
        return

    with st.spinner("Reading file…"):
        try:
            df = read_uploaded(uploaded)
        except Exception as e:
            st.error(f"Could not read file: {e}")
            return

    file_name   = uploaded.name
    upload_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sku_count   = len(df)

    st.success("File loaded — metadata extracted automatically")
    c1, c2, c3 = st.columns(3)
    c1.metric("📄 File Name",   file_name)
    c2.metric("📅 Upload Date", upload_date[:10])
    c3.metric("🔢 SKU Count",   f"{sku_count:,}")

    with st.expander("📊 Preview — first 5 rows", expanded=True):
        st.dataframe(df.head(5), use_container_width=True)

    st.markdown(
    f"<p style='color:#ffffff; font-size:14px;'>"
    f"<b style='color:#facc15;'>{len(df.columns)} source columns:</b> "
    + "  ".join([f"<span style='color:#e5e7eb;'>`{c}`</span>" for c in df.columns[:14]])
    + ("…" if len(df.columns) > 14 else "")
    + "</p>",
    unsafe_allow_html=True
    )

    # ── NEW: Project Code input here for early mapping suggestion ──
    uid = st.session_state.get("user_id")
    try:
        user_projects = fetch_user_projects(uid) if uid else []
    except Exception:
        user_projects = []

    project_hint = ""
    if user_projects:
        project_hint = st.selectbox(
            "📁 Project Code (optional — helps auto-suggest mapping from previous files)",
            options=["— Select or type below —"] + user_projects,
            key="upload_project_hint",
        )
        if project_hint == "— Select or type below —":
            project_hint = ""

    if st.button("Proceed to Field Mapping →", type="primary", use_container_width=True):
        source_cols = list(df.columns)

        # Step 1: Try project-level mapping template
        proj_applied, proj_matched = {}, {}
        if project_hint and uid:
            proj_applied, proj_matched = apply_project_mapping_template(source_cols, project_hint, uid)

        # Step 2: Fuzzy auto-suggest for any remaining cols
        if not st.session_state.mapping:

            fuzzy_suggestions = auto_suggest_mapping(source_cols)

        else:

            fuzzy_suggestions = st.session_state.mapping.copy()

        # Step 3: Merge — project template takes priority over fuzzy
        init_mapping = {}
        all_auto_mapped = {}
        for col in source_cols:
            if col in proj_applied:
                init_mapping[col] = proj_applied[col]
                all_auto_mapped[col] = proj_applied[col]
            elif col in fuzzy_suggestions:
                init_mapping[col] = fuzzy_suggestions[col]
                all_auto_mapped[col] = fuzzy_suggestions[col]
            else:
                init_mapping[col] = "— skip —"

        # ── Persist uploaded file to stable cache directory ──────────────────
        # Use a hash of file content so the same file is never written twice.
        file_bytes   = uploaded.getvalue()
        file_hash    = hashlib.md5(file_bytes).hexdigest()
        suffix       = "." + uploaded.name.rsplit(".", 1)[-1].lower()
        cache_path   = os.path.join(_UPLOAD_CACHE_DIR, f"{file_hash}{suffix}")
        parquet_path = cache_path + ".parquet"

        if not os.path.exists(cache_path):
            with open(cache_path, "wb") as fh:
                fh.write(file_bytes)

        # Write parquet cache immediately for fast future reloads
        if not os.path.exists(parquet_path):
            try:
                df.to_parquet(parquet_path, index=False)
            except Exception:
                pass  # non-fatal

        st.session_state.df                 = None          # never store full df in session
        st.session_state._df_path           = cache_path
        st.session_state._df_orig_suffix    = suffix
        st.session_state.file_name          = file_name
        st.session_state.upload_date        = upload_date
        st.session_state.sku_count          = sku_count
        # =========================================================
        # SPLIT COLUMNS
        # =========================================================

        all_columns = list(source_cols)

        primary_columns, attribute_columns = (
            split_primary_and_attribute_columns(all_columns)
        )

        # =========================================================
        # SAVE SESSION STATE
        # =========================================================

        st.session_state.source_columns = primary_columns

        st.session_state.attribute_columns = attribute_columns

        # all attribute cols selected by default
        st.session_state.attr_selected = attribute_columns.copy()
        if not st.session_state.mapping:

            st.session_state.mapping = init_mapping
            st.session_state.auto_mapped = fuzzy_suggestions
        st.session_state.proj_auto_mapped   = proj_matched
        st.session_state.project_name       = project_hint if project_hint else st.session_state.project_name

        st.session_state.step = 2
        st.query_params["step"] = "2"

        st.session_state.step               = 2

        # ── Encode all restorable state into query_params ────────────────────
        # This allows browser refresh to fully restore the current step without
        # restarting from the upload page.
        save_workflow_state()
        _sync_query_params()
        st.rerun()


# ═══════════════════════════════════════════════════════════
# 7. STEP 2 — PRIMARY FIELD MAPPING (MODIFIED — sorted display + project mapping label)
# ═══════════════════════════════════════════════════════════

def step_mapping():
    progress_bar(2)
    file_info_strip()

    # OPT 4: reload df on demand from temp file — not kept in session_state
    if not st.session_state.get("_df_path") and st.session_state.get("df") is None:
        st.warning("No file uploaded yet.")
        return

    st.markdown("""
<h3 style="
    font-size:22px;
    font-weight:600;
    margin-bottom:9px;
    color: #ffffff;            
">
🔀 Step 2 — Primary Field Mapping
</h3>
""", unsafe_allow_html=True )


    # ── NEW: Show project mapping banner if applicable ──
    proj_matched = st.session_state.get("proj_auto_mapped", {})
    if proj_matched:
        proj_name = st.session_state.get("project_name", "this project")
        st.info(
            f"📂 **Auto-suggested mapping from previous project** — "
            f"'{proj_name}' ({len(proj_matched)} column(s) matched from saved template). "
            f"🔵 = project template match · 🤖 = name-based auto match. "
            f"All mappings are editable below.",
            icon=None,
        )
    else:
        st.caption(
            "Source columns are **auto-matched** to target fields where possible. "
            "🤖 = auto-suggested. Override any mapping using the dropdown."
        )

    source_cols = st.session_state.get(
        "source_columns",
        []
    )
    total       = len(source_cols)
    auto_mapped = st.session_state.get("auto_mapped", {})

    # --- CHANGE START --- PATCH 4: Sort columns — project-mapped first, auto-mapped next, unmapped last
    proj_matched_keys = set(st.session_state.get("proj_auto_mapped", {}).keys())
    auto_mapped_keys  = set(auto_mapped.keys()) - proj_matched_keys
    unmapped_keys     = [
        c for c in source_cols
        if c not in proj_matched_keys and c not in auto_mapped_keys
    ]
    sorted_cols = (
        [c for c in source_cols if c in proj_matched_keys] +
        [c for c in source_cols if c in auto_mapped_keys] +
        unmapped_keys
    )
    # --- CHANGE END ---

    # ── Reversed UI: paginate over TARGET_FIELDS instead of source columns ──────
    # Only show target fields that are either already mapped or not yet taken
    # (i.e. all TARGET_FIELDS — user assigns a source to each via dropdown).
    # Pagination still uses ROWS_PER_MAP_PAGE; total is now len(TARGET_FIELDS).
    total_targets = len(TARGET_FIELDS)
    n_pages       = max(1, (total_targets + ROWS_PER_MAP_PAGE - 1) // ROWS_PER_MAP_PAGE)
    page          = st.session_state.map_page
    page_targets  = TARGET_FIELDS[page * ROWS_PER_MAP_PAGE : (page + 1) * ROWS_PER_MAP_PAGE]

    # Build reverse lookup: target_field -> source_col  (from current mapping dict)
    target_to_source: dict[str, str] = {
        tgt: src
        for src, tgt in st.session_state.mapping.items()
        if tgt != "— skip —"
    }

    # summary bar (computed from existing mapping dict — unchanged backend format)
    auto_count   = sum(1 for c in source_cols if auto_mapped.get(c) and st.session_state.mapping.get(c) == auto_mapped.get(c))
    proj_count   = sum(1 for c in source_cols if proj_matched.get(c) and st.session_state.mapping.get(c) == proj_matched.get(c))
    mapped_count = sum(1 for v in st.session_state.mapping.values() if v != "— skip —")
    st.info(
        f"📂 **{proj_count}** project-template mapped  ·  "
        f"🤖 **{auto_count}** name-matched  ·  "
        f"✅ **{mapped_count}** total mapped  ·  "
        f"⏭ **{total - mapped_count}** source(s) skipped",
        icon=None,
    )

    h_tgt, h_arrow, h_src = st.columns([5, 1, 5])
    h_tgt.markdown(
        '<div class="panel-header" style="background:#f0fdf4;border-radius:6px;padding:8px 12px">'
        '⬤ TARGET FIELDS</div>', unsafe_allow_html=True)
    h_arrow.markdown("")
    h_src.markdown(
        '<div class="panel-header" style="background:#f0f4ff;border-radius:6px;padding:8px 12px">'
        '⬤ SOURCE FIELDS</div>', unsafe_allow_html=True)
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    for tgt in page_targets:
        # Which source is currently mapped to this target (if any)?
        current_src = target_to_source.get(tgt, "— skip —")

        # Build source options: skip + all source cols not already used by another target,
        # but always include the currently selected source for this row.
        used_sources = {
            src for src, t in st.session_state.mapping.items()
            if t != "— skip —" and t != tgt          # exclude current target's own source
        }
        source_options = ["— skip —"] + [
            c for c in source_cols
            if c not in used_sources or c == current_src
        ]

        # Badge detection: was this target auto-mapped or project-mapped?
        is_auto      = (current_src != "— skip —" and auto_mapped.get(current_src) == tgt)
        is_proj_auto = (current_src != "— skip —" and proj_matched.get(current_src) == tgt)

        col_tgt, col_arrow, col_src_dd = st.columns([5, 1, 5])
        with col_tgt:
            badges = ""
            if is_proj_auto:
                badges += '<span class="proj-auto-badge">📂 PROJECT</span>'
            elif is_auto:
                badges += '<span class="auto-badge">🤖 AUTO</span>'
            st.markdown(
                f'<div style="padding:4px 0"><span class="source-tag">🎯 {tgt}</span>{badges}</div>',
                unsafe_allow_html=True)
        with col_arrow:
            st.markdown('<div class="arrow-cell">←</div>', unsafe_allow_html=True)
        with col_src_dd:
            idx        = source_options.index(current_src) if current_src in source_options else 0
            chosen_src = st.selectbox(
                label=tgt, options=source_options, index=idx,
                key=f"map_tgt_{tgt}", label_visibility="collapsed")

            # ── Update mapping[source] = target (backend format preserved) ──────
            # 1. Remove old mapping entry for this target if source changed
            if current_src != "— skip —" and chosen_src != current_src:
                st.session_state.mapping[current_src] = "— skip —"
            # 2. Write new mapping entry
            if chosen_src != "— skip —":
                st.session_state.mapping[chosen_src] = tgt
        st.markdown('<div style="margin-bottom:2px"></div>', unsafe_allow_html=True)
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    st.caption(
        f"Page {page + 1} of {n_pages}  ·  "
        f"{mapped_count} field(s) mapped  ·  "
        f"{total - mapped_count} source(s) skipped"
    )

    # =========================================================
    # PERSIST CURRENT SELECTBOX VALUES
    # =========================================================
    def persist_mapping_state():
        # Reversed UI: selectbox key is map_tgt_{target}, value is chosen source col.
        # Rebuild mapping as {source: target} for full backend compatibility.
        for tgt in TARGET_FIELDS:
            map_key = f"map_tgt_{tgt}"
            if map_key in st.session_state:
                chosen_src = st.session_state[map_key]
                # Clear any existing source→target entry that pointed to this target
                for src in list(st.session_state.mapping.keys()):
                    if st.session_state.mapping.get(src) == tgt:
                        st.session_state.mapping[src] = "— skip —"
                # Write new entry
                if chosen_src != "— skip —":
                    st.session_state.mapping[chosen_src] = tgt

    # =========================================================
    # NAVIGATION BUTTONS
    # =========================================================
    n1, n2, n3, n4, n5 = st.columns([2, 2, 2, 2, 4])

    # ---------------------------------------------------------
    # BACK TO UPLOAD
    # ---------------------------------------------------------
    with n1:

        if st.button(
            "← Back to Upload",
            disabled=(page > 0),
            use_container_width=True,
            key="mapping_back_upload_btn"
        ):

            persist_mapping_state()

            save_workflow_state()
            _sync_query_params()

            st.session_state.step = 1

            st.rerun()

    # ---------------------------------------------------------
    # PREVIOUS PAGE
    # ---------------------------------------------------------
    with n2:

        if st.button(
            "⬅ Prev",
            disabled=(page == 0),
            use_container_width=True,
            key="mapping_prev_page_btn"
        ):

            persist_mapping_state()

            st.session_state.map_page -= 1

            save_workflow_state()
            _sync_query_params()

            st.rerun()

    # ---------------------------------------------------------
    # NEXT PAGE
    # ---------------------------------------------------------
    with n3:

        if st.button(
            "Next ➡",
            disabled=(page >= n_pages - 1),
            use_container_width=True,
            key="mapping_next_page_btn"
        ):

            persist_mapping_state()

            st.session_state.map_page += 1

            save_workflow_state()
            _sync_query_params()

            st.rerun()

    # ---------------------------------------------------------
    # SAVE BUTTON
    # ---------------------------------------------------------
    with n4:

        if st.button(
            "💾 Save",
            use_container_width=True,
            key="mapping_save_btn"
        ):

            persist_mapping_state()

            save_workflow_state()
            _sync_query_params()

            st.success("Mapping saved successfully.")

    # ---------------------------------------------------------
    # NEXT TO ATTRIBUTE GROUPING
    # ---------------------------------------------------------
    with n5:

        if st.button(
            "Save & Next: Attribute Grouping →",
            type="primary",
            use_container_width=True,
            key="mapping_next_attributes_btn"
        ):

            persist_mapping_state()

            mapped_count = sum(
                1 for v in st.session_state.mapping.values()
                if v != "— skip —"
            )

            if mapped_count == 0:

                st.warning(
                    "Please map at least one source field before continuing."
                )

            else:

                st.session_state.map_page = 0

                st.session_state.step = 3

                save_workflow_state()
                _sync_query_params()

                st.rerun()
            


# ═══════════════════════════════════════════════════════════
# 8. STEP 3 — ATTRIBUTE GROUPING (unchanged)
# ═══════════════════════════════════════════════════════════

def step_attributes():
    progress_bar(3)
    file_info_strip()

    if not st.session_state.get("_df_path") and st.session_state.get("df") is None:
        st.warning("No file uploaded yet.")
        return

    st.markdown("""
<h3 style="
    font-size:22px;
    font-weight:600;
    margin-bottom:9px;
    color: #ffffff;            
">
🏷️ Step 3 — Attribute Grouping
</h3>
""", unsafe_allow_html=True )
    st.caption("Select source columns to treat as product attributes. Already-mapped columns are hidden.")

    mapped_cols = {c for c, v in st.session_state.mapping.items() if v != "— skip —"}
    # =========================================================
    # ATTRIBUTE COLUMNS
    # =========================================================

    attribute_cols = st.session_state.get(
        "attribute_columns",
        []
    )

    primary_cols = st.session_state.get(
        "source_columns",
        []
    )

    mapped_cols = set(
        st.session_state.mapping.keys()
    )

    # =========================================================
    # UNMAPPED PRIMARY COLS
    # =========================================================

    unmapped_primary = [

        c for c in primary_cols

        if c not in mapped_cols
    ]

    # =========================================================
    # FINAL ATTRIBUTE SECTION
    # =========================================================

    available = list(dict.fromkeys(
        attribute_cols + unmapped_primary
    ))
    search   = st.text_input("🔍 Filter columns", placeholder="Type to search…", key="attr_search")
    filtered = [c for c in available if search.lower() in c.lower()] if search else available

    for col in filtered:

        if f"attrL_{col}" not in st.session_state:
            st.session_state[f"attrL_{col}"] = col in st.session_state.attr_selected

        if f"attrR_{col}" not in st.session_state:
            st.session_state[f"attrR_{col}"] = col in st.session_state.attr_selected

    st.markdown(
        f'<div style="font-size:12px;color:#ffffff;margin:4px 0 8px">'
        f'Showing <strong>{len(filtered)}</strong> of <strong>{len(available)}</strong> '
        f'available columns</div>',
        unsafe_allow_html=True,
    )

    all_selected    = all(c in st.session_state.attr_selected for c in filtered) and len(filtered) > 0
    prev_select_all = st.session_state.get("select_all_prev", False)
    select_all      = st.checkbox(
        f"✅ Select All ({len(filtered)} visible columns)",
        value=all_selected,
        key="select_all_checkbox",
    )

    if select_all != prev_select_all:

        if select_all:

            for col in filtered:

                if col not in st.session_state.attr_selected:
                    st.session_state.attr_selected.append(col)

        else:

            st.session_state.attr_selected = [
                c for c in st.session_state.attr_selected
                if c not in filtered
            ]

        st.session_state["select_all_prev"] = select_all

        save_workflow_state()
        _sync_query_params()

        st.rerun()

    st.session_state["select_all_prev"] = select_all
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    if len(filtered) > 0:
        half       = len(filtered) // 2 + len(filtered) % 2
        left_cols  = filtered[:half]
        right_cols = filtered[half:]
    else:
        left_cols = right_cols = []

    panel_l, gap_col, panel_r = st.columns([5, 0.3, 5])

    with panel_l:
        st.markdown(
            '<div class="panel-header" style="background:#faf5ff;border-radius:6px;padding:8px 12px">'
            '⬤ COLUMNS A–M</div>', unsafe_allow_html=True)
        with st.container(height=380):
            for col in left_cols:
                checked = col in st.session_state.attr_selected
                ticked  = st.checkbox(col, value=st.session_state.get(f"attrL_{col}", checked), key=f"attrL_{col}")
                prev_selected = col in st.session_state.attr_selected

                if ticked and not prev_selected:
                    st.session_state.attr_selected.append(col)
                    save_workflow_state()
                    _sync_query_params()

                elif not ticked and prev_selected:
                    st.session_state.attr_selected.remove(col)
                    save_workflow_state()
                    _sync_query_params()

    with panel_r:
        st.markdown(
            '<div class="panel-header" style="background:#faf5ff;border-radius:6px;padding:8px 12px">'
            '⬤ COLUMNS N–Z</div>', unsafe_allow_html=True)
        with st.container(height=380):
            for col in right_cols:
                checked = col in st.session_state.attr_selected
                ticked  = st.checkbox(col, value=st.session_state.get(f"attrR_{col}", checked), key=f"attrR_{col}")
                prev_selected = col in st.session_state.attr_selected

                if ticked and not prev_selected:
                    st.session_state.attr_selected.append(col)
                    save_workflow_state()
                    _sync_query_params()

                elif not ticked and prev_selected:
                    st.session_state.attr_selected.remove(col)
                    save_workflow_state()
                    _sync_query_params()
    n_sel = len(st.session_state.attr_selected)
    if n_sel:
        preview = ", ".join(st.session_state.attr_selected[:8])
        st.success(f"{n_sel} attributes selected: {preview}")

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    b1, _, b3 = st.columns([2, 6, 2])
    with b1:
        if st.button("← Back to Mapping"):
            st.session_state.step = 2
            save_workflow_state()
            _sync_query_params()
            st.rerun()
    with b3:
        if st.button("Next: Unmapped Fields →", type="primary", use_container_width=True):
            st.session_state.step = 4
            save_workflow_state()
            _sync_query_params()
            st.rerun()


# ═══════════════════════════════════════════════════════════
# 9. STEP 4 — UNMAPPED FIELDS (unchanged)
# ═══════════════════════════════════════════════════════════

def step_unmapped():
    progress_bar(4)
    file_info_strip()

    if not st.session_state.get("_df_path") and st.session_state.get("df") is None:
        st.warning("No file uploaded yet.")
        return

    st.markdown("""
<h3 style="
    font-size:22px;
    font-weight:600;
    margin-bottom:9px;
    color:#ffffff;            
">
🚫 Step 4 — Unmapped Fields
</h3>
""", unsafe_allow_html=True)
    st.caption("Columns not used in field mapping or attribute grouping — auto-derived, read-only.")

    mapped_cols = {c for c, v in st.session_state.mapping.items() if v != "— skip —"}
    attr_cols   = set(st.session_state.attr_selected)
    unmapped    = [c for c in st.session_state.source_columns
                   if c not in mapped_cols and c not in attr_cols]

    s1, s2, s3 = st.columns(3)
    s1.metric("✅ Mapped",     len(mapped_cols))
    s2.metric("🏷️ Attributes", len(attr_cols))
    s3.metric("⚠️ Unmapped",   len(unmapped))

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    if unmapped:
        st.markdown("<h4 style='color:#ffffff;'>####Columns stored as unmapped</h4>",  unsafe_allow_html=True)
        col_a, col_b = st.columns(2)
        half = len(unmapped) // 2 + len(unmapped) % 2
        with col_a:
            for u in unmapped[:half]:
                st.markdown(f'<span class="unmapped-badge">⚠ {u}</span><br>', unsafe_allow_html=True)
        with col_b:
            for u in unmapped[half:]:
                st.markdown(f'<span class="unmapped-badge">⚠ {u}</span><br>', unsafe_allow_html=True)
    else:
        st.success("🎉 All source columns are accounted for — nothing is unmapped!")

    st.session_state.unmapped_fields = unmapped
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    b1, _, b3 = st.columns([2, 6, 2])
    with b1:
        if st.button("← Back to Attributes"):
            st.session_state.step = 3
            save_workflow_state()
            _sync_query_params()
            st.rerun()
    with b3:
        if st.button("Next: Summary →", type="primary", use_container_width=True):
            st.session_state.step = 5
            save_workflow_state()
            _sync_query_params()
            st.rerun()


# ═══════════════════════════════════════════════════════════
# 10. STEP 5 — SUMMARY & SUBMIT (MODIFIED — saves mapping template)
# ═══════════════════════════════════════════════════════════

def step_summary():
    progress_bar(5)
    file_info_strip()

    if not st.session_state.get("_df_path") and st.session_state.get("df") is None:
        st.warning("No file uploaded yet.")
        return

    st.markdown("""
<h3 style="
    font-size:22px;
    font-weight:600;
    margin-bottom:9px;
    color:#ffffff;            
">
📋 Step 5 — Final Summary & Submit
</h3>
""", unsafe_allow_html=True)
    st.caption("Fill in project details, review all sections, then click Submit.")

    st.markdown('<div class="input-card">', unsafe_allow_html=True)
    st.markdown('<div class="input-card-title">📝 Project Details</div>', unsafe_allow_html=True)

    pi1, pi2, pi3 = st.columns(3)
    project_name = pi1.text_input("Project Code *", value=st.session_state.project_name,
                                   placeholder="e.g. AltiusNXT Q2 2026", key="input_project_name")
    batch_code   = pi2.text_input("Batch Code *",   value=st.session_state.batch_code,
                                   placeholder="e.g. BATCH01",           key="input_batch_code")
    with pi3:
        st.markdown("**Author**")
        st.info(st.session_state.get("user_email", "—"), icon="👤")

    st.session_state.project_name = project_name
    st.session_state.batch_code   = batch_code
    st.markdown("</div>", unsafe_allow_html=True)

    mapped   = {c: v for c, v in st.session_state.mapping.items() if v != "— skip —"}
    attrs    = st.session_state.attr_selected
    unmapped = st.session_state.unmapped_fields

    st.markdown('<div class="sum-section">① Primary Field Mapping</div>', unsafe_allow_html=True)
    if mapped:
        h1, h2, h3 = st.columns([5, 1, 5])
        h1.markdown('<div class="panel-header">SOURCE</div>', unsafe_allow_html=True)
        h2.markdown("")
        h3.markdown('<div class="panel-header">TARGET</div>', unsafe_allow_html=True)
        for src, tgt in mapped.items():
            c1, c2, c3 = st.columns([5, 1, 5])
            c1.markdown(f'<span class="source-tag">📌 {src}</span>', unsafe_allow_html=True)
            c2.markdown('<div class="arrow-cell">→</div>', unsafe_allow_html=True)
            c3.markdown(f'<span class="mapped-badge">✔ {tgt}</span>', unsafe_allow_html=True)
    else:
        st.info("No fields mapped.")

    st.markdown('<div class="sum-section">② Attribute Grouping</div>', unsafe_allow_html=True)
    if attrs:
        for chunk in [attrs[i:i+4] for i in range(0, len(attrs), 4)]:
            cols = st.columns(4)
            for i, a in enumerate(chunk):
                cols[i].markdown(f'<span class="attr-badge">🏷 {a}</span>', unsafe_allow_html=True)
    else:
        st.info("No attributes selected.")

    st.markdown('<div class="sum-section">③ Unmapped Fields</div>', unsafe_allow_html=True)
    if unmapped:
        for chunk in [unmapped[i:i+4] for i in range(0, len(unmapped), 4)]:
            cols = st.columns(4)
            for i, u in enumerate(chunk):
                cols[i].markdown(f'<span class="unmapped-badge">⚠ {u}</span>', unsafe_allow_html=True)
    else:
        st.success("No unmapped fields.")

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    b1, _, b3 = st.columns([2, 5, 3])
    with b1:
        if st.button("← Back to Unmapped"):
            st.session_state.step = 4
            save_workflow_state()
            _sync_query_params()
            st.rerun()
    with b3:
        if st.button("🚀 Submit & Upload", type="primary", use_container_width=True):
            errors = []
            if not st.session_state.project_name.strip():
                errors.append("Project Code is required.")
            if not st.session_state.batch_code.strip():
                errors.append("Batch Code is required.")

            if errors:
                for e in errors:
                    st.error(e)
                return

            # ── pre-check for duplicate BEFORE hitting DB ──
            try:
                is_dup = check_duplicate(
                    batch_code=st.session_state.batch_code.strip(),
                    file_name=st.session_state.file_name,
                )
            except Exception as e:
                st.error(f"DB connection error during duplicate check: {e}")
                return

            if is_dup:
                st.warning(
                    f"⚠️ **Duplicate detected!** The file "
                    f"`{st.session_state.file_name}` has already been uploaded "
                    f"under batch code `{st.session_state.batch_code.strip()}`. "
                    f"Please use a different batch code or check your records."
                )
                return


            if not st.session_state.get("processing_completed"):
                with st.spinner("Saving to PostgreSQL…"):
                    # STEP 1 — INSERT LOG
                    try:
                        log_id = insert_upload_log(
                            project_name = st.session_state.project_name.strip(),
                            batch_code   = st.session_state.batch_code.strip(),
                            author_name  = st.session_state.get("user_email", ""),
                            file_name    = st.session_state.file_name,
                            upload_date  = st.session_state.upload_date,
                            sku_count    = st.session_state.sku_count,
                            user_id      = st.session_state.get("user_id"),
                            user_email   = st.session_state.get("user_email"),
                        )
                    except Exception as e:
                        err = str(e).lower()
                        if "unique" in err or "duplicate key" in err:
                            st.warning("⚠️ Duplicate file detected (DB constraint). Upload skipped.")
                        else:
                            st.error(f"❌ Failed to create upload log: {e}")
                        return

                    # STEP 2 — INSERT ETL DATA
                    try:
                        # OPT 4: reload DataFrame from temp file at submit time
                        _df_to_insert = _load_df()
                        if _df_to_insert is None:
                            st.error("❌ Source file could not be reloaded. Please re-upload.")
                            return
                        inserted = insert_etl_data(
                            df            = _df_to_insert,
                            mapping       = st.session_state.mapping,
                            attr_cols     = st.session_state.attr_selected,
                            unmapped_cols = st.session_state.unmapped_fields,
                            batch_code    = st.session_state.batch_code.strip(),
                            author_name   = st.session_state.get("user_email", ""),
                            file_name     = st.session_state.file_name,
                            upload_date   = st.session_state.upload_date,
                            sku_count     = st.session_state.sku_count,
                            user_id       = st.session_state.get("user_id"),
                            user_email    = st.session_state.get("user_email"),
                            upload_log_id = log_id,
                        )
                    except Exception as e:
                        try:
                            hard_delete_log(log_id)
                        except Exception:
                            pass
                        st.error(f"❌ Failed to insert ETL data: {e}")
                        return

                    # NEW STEP 3 — SAVE MAPPING TEMPLATE (FEATURE 1)
                    try:
                        save_mapping_template(
                            project_name = st.session_state.project_name.strip(),
                            mapping      = st.session_state.mapping,
                            user_id      = st.session_state.get("user_id"),
                        )
                    except Exception as e:
                        # Non-fatal — warn but don't block
                        st.warning(f"⚠️ Mapping template could not be saved: {e}")

                st.session_state.processing_completed = True
                st.session_state.submitted = True
                st.session_state.upload_log_id = log_id
                st.session_state.inserted_rows = inserted
                st.session_state.step      = 6
                save_workflow_state()
                _sync_query_params()
                st.rerun()


# ═══════════════════════════════════════════════════════════
# 11. STEP 6 — RESULT PAGE (MODIFIED — adds new sections)
# ═══════════════════════════════════════════════════════════

def step_result():
    progress_bar(6)

    if st.session_state.get("df") is None:

        restored_df = _load_df()

        if restored_df is not None:
            st.session_state.df = restored_df
        else:
            st.warning("Session expired. Please upload again.")

            # Don't stop page rendering
            st.session_state.file_name = st.session_state.get("file_name", "No File")
            st.session_state.upload_date = st.session_state.get("upload_date", "-")
            st.session_state.sku_count = st.session_state.get("sku_count", 0)
        
    
    _sync_query_params()
    st.markdown("<h4 style='color:#ffffff;'>✅ Upload Complete!</h4>",
    unsafe_allow_html=True)

    result_df = pd.DataFrame([{
        "File Name":     st.session_state.file_name,
        "Date":          st.session_state.upload_date,
        "SKU Count":     f"{int(st.session_state.sku_count or 0):,}",
        "Project Code":  st.session_state.project_name,
        "Batch Code":    st.session_state.batch_code,
        "Author":        st.session_state.get("user_email", "—"),
        "Fields Mapped": len({c for c, v in st.session_state.mapping.items() if v != "— skip —"}),
        "Attributes":    len(st.session_state.attr_selected),
        "Unmapped":      len(st.session_state.unmapped_fields),
        "Status":        "✅ Complete",
    }])
    st.markdown("<h4 style='color:#ffffff;'>📊 Upload Result</h4>",
    unsafe_allow_html=True
)
    st.dataframe(result_df, use_container_width=True, hide_index=True)

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    # ── FEATURE 2: Favorites / Project Grouping ──
    render_favorites_section()

    # ── FEATURE 3+4: Search + Paginated File List ──
    render_search_and_file_list()

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    # ── FEATURE 5: Taxonomy Search ──
    render_taxonomy_search_section()

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    # ── FULL CRUD Records Manager ──────────────────────────
    st.markdown("<h4 style='color:#ffffff;'>🗃️ All Uploaded Records</h4>",
    unsafe_allow_html=True)

    admin = is_admin()

    # "Show deleted" toggle is admin-only
    show_deleted = False
    if admin:
        show_deleted = st.checkbox("🗑️ Show deleted records (admin only)", value=False, key="show_deleted_chk")

    try:
        logs_df = fetch_upload_logs(show_deleted=show_deleted)
    except Exception as e:
        st.error(f"Could not fetch records: {e}")
        logs_df = pd.DataFrame()

    if logs_df.empty:
        st.info("No upload records found.")
    else:
        projects = logs_df["project_name"].unique().tolist()

        for project in projects:
            proj_df = logs_df[logs_df["project_name"] == project]

            with st.expander(f"📁 {project}  ({len(proj_df)} file{'s' if len(proj_df) != 1 else ''})", expanded=True):
                for _, row in proj_df.iterrows():
                    rid       = int(row["id"])
                    row_style = "background:#ffffff;border:1px solid #e2e8f0;border-radius:8px;padding:10px 14px;margin-bottom:8px"

                    col_info, col_actions = st.columns([6, 4])

                    with col_info:
                        # status NOT shown in card (Requirement 2)
                        st.markdown(
                            f'<div style="{row_style}">'
                            f'<strong style="color:#1e293b">{row["project_name"]}</strong>'
                            f' &nbsp;/&nbsp; <span style="color:#4b5563">{row["batch_code"]}</span>'
                            f'<br><span style="font-size:11px;color:#9ca3af">'
                            f'📄 {row["file_name"]}  ·  📅 {str(row["upload_date"])[:10]}'
                            f'  ·  🔢 {row["sku_count"]:,} SKUs'
                            f'  ·  ✍ {row["author_name"]}'
                            f'</span></div>',
                            unsafe_allow_html=True,
                        )

                    with col_actions:
                        if admin:
                            a1, a2, a3, a4 = st.columns(4)
                        else:
                            a1, a2 = st.columns(2)
                            a3 = a4 = None   # not rendered for non-admins

                        if a1.button("👁 View", key=f"view_{rid}", use_container_width=True):
                            st.session_state[f"show_data_{rid}"] = not st.session_state.get(f"show_data_{rid}", False)

                        if a2.button("✏️ Edit", key=f"edit_{rid}", use_container_width=True):
                            st.session_state[f"edit_mode_{rid}"] = not st.session_state.get(f"edit_mode_{rid}", False)

                    if st.session_state.get(f"show_data_{rid}"):
                        try:
                            data_df = fetch_etl_data_for_log(rid)
                        except Exception as e:
                            st.error(f"Could not load data: {e}")
                            data_df = pd.DataFrame()

                        if data_df.empty:
                            st.info("No ETL data rows found for this record.")
                        else:
                            st.markdown(f"**📋 {len(data_df):,} SKU rows for record #{rid}**")
                            st.dataframe(data_df, use_container_width=True, hide_index=True)

                    if st.session_state.get(f"edit_mode_{rid}"):
                        with st.form(key=f"edit_form_{rid}"):
                            st.markdown(f"**✏️ Edit metadata for record #{rid}**")
                            new_project = st.text_input("Project Code", value=str(row["project_name"]))
                            new_batch   = st.text_input("Batch Code",   value=str(row["batch_code"]))
                            submitted   = st.form_submit_button("💾 Save Changes", type="primary")
                            if submitted:
                                if not new_project.strip() or not new_batch.strip():
                                    st.error("Project Code and Batch Code cannot be empty.")
                                else:
                                    try:
                                        update_log_metadata(rid, new_project.strip(), new_batch.strip())
                                        st.session_state.pop(f"edit_mode_{rid}", None)
                                        st.success("Record updated.")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Update failed: {e}")

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    # Field Mapping / Attributes / Unmapped summary tables
    mapped = {c: v for c, v in st.session_state.mapping.items() if v != "— skip —"}
    if mapped:
        st.markdown("<h4 style='color:#ffffff;'>🔀 Field Mapping</h4>",
    unsafe_allow_html=True
)
        st.dataframe(
            pd.DataFrame([(s, "→", t) for s, t in mapped.items()],
                         columns=["Source Field", "", "Target Field"]),
            use_container_width=True, hide_index=True,
        )
    if st.session_state.attr_selected:
        st.markdown("<h4 style='color:#ffffff;'>🏷️ Attribute Fields</h4>",
    unsafe_allow_html=True)
        st.dataframe(
            pd.DataFrame(st.session_state.attr_selected, columns=["Attribute Column"]),
            use_container_width=True, hide_index=True,
        )
    if st.session_state.unmapped_fields:
        st.markdown("<h4 style='color:#ffffff;'>⚠️ Unmapped Fields</h4>",
    unsafe_allow_html=True)
        st.dataframe(
            pd.DataFrame(st.session_state.unmapped_fields, columns=["Unmapped Column"]),
            use_container_width=True, hide_index=True,
        )

    st.markdown("---")
    if st.button("🔄 Process Another File", type="primary"):
        # Clean up persistent cache files for this upload (both raw + parquet)
        _cache = st.session_state.get("_df_path")
        if _cache:
            for _path in (_cache, _cache + ".parquet"):
                if os.path.exists(_path):
                    try:
                        os.unlink(_path)
                    except Exception:
                        pass

        auth_backup = {
            "user_id":    st.session_state.get("user_id"),
            "user_email": st.session_state.get("user_email"),
            "user_role":  st.session_state.get("user_role", "user"),
        }
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.session_state["user_id"]    = auth_backup["user_id"]
        st.session_state["user_email"] = auth_backup["user_email"]
        st.session_state["user_role"]  = auth_backup["user_role"]
        st.session_state["step"]       = 1
        # Clear all workflow query params; keep auth
        for _qk in ["fn", "ud", "sc", "pn", "bc", "fp", "ds", "scols", "mp", "at", "uf", "step"]:
            st.query_params.pop(_qk, None)
            save_workflow_state()
        _sync_query_params()
        st.rerun()



# ═══════════════════════════════════════════════════════════
# 13. MAIN ROUTER
# ═══════════════════════════════════════════════════════════

def main():

    # ── Login gate ─────────────────────────────────────────
    if not is_logged_in():
        show_login_page()
        st.stop()

    # ── Session Role Display ──────────────────────────────
    st.markdown(
        f"<p style='color:#facc15; font-weight:600; padding:7px;'>SESSION ROLE: "
        f"<span style='color:#ffffff'>{st.session_state.user_role}</span></p>",
        unsafe_allow_html=True
    )

    # ── Top Header ────────────────────────────────────────
    top_l, top_r = st.columns([8, 2])

    with top_l:

        st.markdown(
            '<h1 style="font-size:26px;font-weight:700;color:#ffffff;margin-bottom:2px;margin-top:15px">'
            '🔀 ETL Visual Data Mapper</h1>'
            '<p style="font-size:14px;color:#ffffff;margin-bottom:22px">'
            'Map source file columns to target fields — step by step</p>',
            unsafe_allow_html=True,
        )

    with top_r:

        role_label = "🔴 Admin" if is_admin() else "👤 User"

        st.markdown(
            f'<div style="text-align:right;font-size:12px;color:#ffffff;padding-top:8px">'
            f'{role_label} &nbsp;·&nbsp; {st.session_state.get("user_email", "")}</div>',
            unsafe_allow_html=True,
        )

        # ── Logout Button ────────────────────────────────
        if st.button("🚪 Logout", use_container_width=True):

            try:
                get_supabase().auth.sign_out()

            except Exception as e:
                print("Logout error:", e)

            # Clear URL params
            st.query_params.clear()

            # Clear all session state
            for k in list(st.session_state.keys()):
                del st.session_state[k]

            # Reset defaults
            st.session_state.user_id = None
            st.session_state.user_email = None
            st.session_state.user_role = "user"
            st.session_state.step = 1

            st.success("Logged out successfully.")

            st.rerun()

    # ── Create Tables ─────────────────────────────────────
    try:

        create_tables()

    except Exception as e:

        st.warning(
            f"⚠️ PostgreSQL not connected ({e}). Data will not be saved."
        )

    # ── Current Step ──────────────────────────────────────
    step = st.session_state.step

    # progress_bar(step)

    # ── UI FLOW ───────────────────────────────────────────
    if step == 1:

        # Favorites Section
        try:
            render_favorites_section()
        except Exception:
            pass

        # Search + Uploaded Files
        try:
            render_search_and_file_list()
        except Exception:
            pass

        # Taxonomy Search
        try:
            render_taxonomy_search_section()
        except Exception:
            pass

        st.markdown(
            '<div class="divider"></div>',
            unsafe_allow_html=True
        )

        # Upload Section
        step_upload()

    elif step == 2:

        step_mapping()

    elif step == 3:

        step_attributes()

    elif step == 4:

        step_unmapped()

    elif step == 5:

        step_summary()

    elif step == 6:

        step_result()


if __name__ == "__main__":
    main()