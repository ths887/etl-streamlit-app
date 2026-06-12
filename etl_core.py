import json
from io import BytesIO

import pandas as pd
import psycopg2
import psycopg2.extras
from psycopg2.pool import SimpleConnectionPool


# =========================================================
# DATABASE CONFIG
# =========================================================

DB_CONFIG = {
    "host": "localhost",
    "database": "Product_Data",
    "user": "postgres",
    "password": "Altius@123",
    "port": "5432",
}


# =========================================================
# CONNECTION POOL
# =========================================================

pool = SimpleConnectionPool(
    1,
    10,
    **DB_CONFIG
)


def get_conn():
    return pool.getconn()


def release_conn(conn):
    pool.putconn(conn)


# =========================================================
# TARGET FIELDS
# =========================================================

TARGET_FIELDS = [
    "sku_id",
    "initial_description",
    "additional_description",
    "supplier",
    "supplier_part_number",
    "manufacturer_name",
    "manufacturer_part_number",
    "brand_name",
    "series",
    "category",
    "taxonomy",
    "end_node",
    "manufacturer_name_1",
    "manufacturer_part_number_1",
    "manufacturer_part_number_2",
    "data_source_status",
    "html_1_url",
    "html_2_url",
    "specification_sheet_1_url",
    "specification_sheet_1_page",
    "catalog_1_url",
    "catalog_1_page",
    "brochure_1_url",
    "brochure_1_page",
    "msds_sds_url",
    "sell_sheet_url",
    "parts_url",
    "instructions_url",
    "owner_manual_url",
    "drawing_sheet_url",
    "schematic_url",
    "warranty_url",
    "video_link",
    "client_url",
    "short_description_as_is",
    "feature_copy",
    "feature_bullets1",
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
    "product_name",
    "fill_rate",
    "remarks",
    "overall_status",
    "duplicate_status_yes_no",
    "duplicate_remarks",
]


# =========================================================
# READ UPLOADED FILE
# =========================================================

def read_uploaded(uploaded_file):

    if uploaded_file.name.endswith(".csv"):

        return pd.read_csv(uploaded_file, dtype=str)

    elif uploaded_file.name.endswith(".xlsx"):

        return pd.read_excel(
            uploaded_file,
            dtype=str,
            engine="openpyxl"
        )

    else:
        raise ValueError("Unsupported file type")


# =========================================================
# INSERT UPLOAD LOG
# =========================================================

def insert_upload_log(
    project_name,
    batch_code,
    author_name,
    file_name,
    upload_date,
    sku_count,
    user_id=None,
    user_email=None,
):

    conn = get_conn()

    cur = conn.cursor()

    try:

        cur.execute(
            """
            INSERT INTO etl_upload_log (
                project_name,
                batch_code,
                author_name,
                file_name,
                upload_date,
                sku_count,
                user_id,
                user_email
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (
                project_name,
                batch_code,
                author_name,
                file_name,
                upload_date,
                sku_count,
                user_id,
                user_email,
            ),
        )

        upload_log_id = cur.fetchone()[0]

        conn.commit()

        return upload_log_id

    finally:

        cur.close()

        release_conn(conn)


# =========================================================
# INSERT ETL DATA
# =========================================================

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

    mapped_source_cols = {
        src for src, tgt in mapping.items()
        if tgt != "— skip —" and tgt in TARGET_FIELDS
    }

    attribute_cols_set = set(attr_cols)

    all_source_cols = list(df.columns)

    computed_unmapped_cols = [
        col for col in all_source_cols
        if col not in mapped_source_cols
        and col not in attribute_cols_set
    ]

    src_to_target = {
        src: tgt
        for src, tgt in mapping.items()
        if tgt != "— skip —" and tgt in TARGET_FIELDS
    }

    fixed_cols = [
        "asn_altiusnxt_stock_number",
        "file_name",
        "author_name",
        "upload_date",
        "sku_count",
        "user_id",
        "user_email",
        "upload_log_id",
    ]

    all_insert_cols = (
        fixed_cols +
        TARGET_FIELDS +
        ["attributes", "unmapped"]
    )

    col_list = ", ".join(all_insert_cols)

    insert_sql = f"""
        INSERT INTO etl_data ({col_list})
        VALUES %s
    """

    total_rows = len(df)

    df_clean = df.where(df.notna(), other=None)

    target_df = pd.DataFrame(
        index=df_clean.index,
        columns=TARGET_FIELDS,
        dtype=object
    )

    target_df[:] = None

    for src_col, tgt_col in src_to_target.items():

        if src_col in df_clean.columns:

            target_df[tgt_col] = (
                df_clean[src_col]
                .astype(str)
                .where(df_clean[src_col].notna(), other=None)
            )

    attr_df = df_clean[
        [c for c in attr_cols if c in df_clean.columns]
    ].copy()

    attr_df = attr_df.astype(str)

    attr_df["file_name"] = file_name

    attr_df["author_name"] = author_name

    attr_json_series = attr_df.apply(
        lambda row: json.dumps({
            k: (
                None
                if pd.isna(v)
                or str(v).strip().lower() in ("nan", "none", "")
                else str(v)
            )
            for k, v in row.items()
        }),
        axis=1,
    )

    unmap_cols_present = [
        c for c in computed_unmapped_cols
        if c in df_clean.columns
    ]

    if unmap_cols_present:

        unmap_df = df_clean[unmap_cols_present].astype(str)

        unmap_json_series = unmap_df.apply(
            lambda row: json.dumps({
                k: (
                    None
                    if pd.isna(v)
                    or str(v).strip().lower() in ("nan", "none", "")
                    else str(v)
                )
                for k, v in row.items()
            }),
            axis=1,
        )

    else:

        unmap_json_series = pd.Series(
            ["{}"] * total_rows,
            index=df_clean.index
        )

    serials = pd.RangeIndex(1, total_rows + 1)

    stock_numbers = pd.Series(
        [
            f"ANXT_{batch_code}_{sku_count}_{str(i).zfill(7)}"
            for i in serials
        ],
        dtype=str,
    )

    fixed_static = (
        file_name,
        author_name,
        upload_date,
        sku_count,
        user_id,
        user_email,
        upload_log_id,
    )

    target_values_matrix = target_df[TARGET_FIELDS].values

    all_rows = []

    for i in range(total_rows):

        row_tuple = (
            (stock_numbers.iloc[i],) +
            fixed_static +
            tuple(target_values_matrix[i]) +
            (
                attr_json_series.iloc[i],
                unmap_json_series.iloc[i]
            )
        )

        all_rows.append(row_tuple)

    conn = get_conn()

    cur = conn.cursor()

    inserted = 0

    CHUNK = 1000

    try:

        for start in range(0, total_rows, CHUNK):

            chunk = all_rows[start:start + CHUNK]

            psycopg2.extras.execute_values(
                cur,
                insert_sql,
                chunk,
                page_size=CHUNK
            )

            inserted += len(chunk)

        conn.commit()

    except Exception:

        conn.rollback()

        raise

    finally:

        cur.close()

        release_conn(conn)

    return inserted
