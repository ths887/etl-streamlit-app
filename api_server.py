from fastapi import (
    FastAPI,
    UploadFile,
    File,
    Form,
    Header,
    HTTPException
)
from fastapi.responses import StreamingResponse
import pandas as pd
from io import StringIO

from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder


from io import BytesIO

from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()


from etl_core import (
    read_uploaded,
    insert_upload_log,
    insert_etl_data,
    get_conn,
    release_conn
)


# =========================================================
# API CONFIG
# =========================================================

API_KEY = os.getenv("API_KEY")


# =========================================================
# FASTAPI APP
# =========================================================

app = FastAPI(
    title="ETL Upload API",
    version="1.0"
)


# =========================================================
# HOME
# =========================================================

@app.get("/")
def home():

    return {
        "status": "running",
        "message": "ETL API is active"
    }


# =========================================================
# UPLOAD FILE API
# =========================================================

@app.post("/api/upload")
async def upload_file(

    x_api_key: str = Header(...),

    project_name: str = Form(...),
    batch_code: str = Form(...),
    author_name: str = Form(...),

    file: UploadFile = File(...)

):

    try:

        # -------------------------------------------------
        # API KEY VALIDATION
        # -------------------------------------------------

        if x_api_key != API_KEY:

            raise HTTPException(
                status_code=401,
                detail="Invalid API Key"
            )

        # -------------------------------------------------
        # READ FILE
        # -------------------------------------------------

        contents = await file.read()

        temp_file = BytesIO(contents)

        temp_file.name = file.filename

        # -------------------------------------------------
        # READ DATAFRAME
        # -------------------------------------------------

        df = read_uploaded(temp_file)

        sku_count = len(df)

        upload_date = datetime.now()

        # -------------------------------------------------
        # PLACEHOLDER MAPPING
        # -------------------------------------------------

        mapping = {}

        attr_cols = []

        unmapped_cols = []

        # -------------------------------------------------
        # INSERT UPLOAD LOG
        # -------------------------------------------------

        upload_log_id = insert_upload_log(
            project_name=project_name,
            batch_code=batch_code,
            author_name=author_name,
            file_name=file.filename,
            upload_date=upload_date,
            sku_count=sku_count,
            user_id=None,
            user_email=None
        )

        # -------------------------------------------------
        # INSERT ETL DATA
        # -------------------------------------------------

        inserted = insert_etl_data(
            df=df,
            mapping=mapping,
            attr_cols=attr_cols,
            unmapped_cols=unmapped_cols,
            batch_code=batch_code,
            author_name=author_name,
            file_name=file.filename,
            upload_date=upload_date,
            sku_count=sku_count,
            user_id=None,
            user_email=None,
            upload_log_id=upload_log_id
        )

        # -------------------------------------------------
        # SUCCESS RESPONSE
        # -------------------------------------------------

        return JSONResponse({

            "status": "success",
            "file_name": file.filename,
            "rows_inserted": inserted,
            "upload_log_id": upload_log_id

        })

    except Exception as e:

        return JSONResponse(

            status_code=500,

            content={
                "status": "error",
                "message": str(e)
            }
        )


# =========================================================
# GET ALL UPLOADS
# =========================================================
@app.get("/api/uploads")
def list_uploads(

    x_api_key: str = Header(...)

):

    conn = None

    cur = None

    try:

        # -----------------------------------------
        # API KEY VALIDATION
        # -----------------------------------------

        if x_api_key != API_KEY:

            raise HTTPException(
                status_code=401,
                detail="Invalid API Key"
            )

        # -----------------------------------------
        # DB CONNECTION
        # -----------------------------------------

        conn = get_conn()

        cur = conn.cursor()

        # -----------------------------------------
        # QUERY
        # -----------------------------------------

        cur.execute("""

            SELECT
                id,
                file_name,
                project_name,
                batch_code,
                author_name,
                upload_date,
                sku_count
            FROM etl_upload_log
            ORDER BY id DESC
            LIMIT 100

        """)

        rows = cur.fetchall()

        # -----------------------------------------
        # CLEAN SERIALIZATION
        # -----------------------------------------

        result = []

        for row in rows:

            result.append({

                "upload_log_id": row[0],

                "file_name": row[1],

                "project_name": row[2],

                "batch_code": row[3],

                "author_name": row[4],

                "upload_date": str(row[5]),

                "sku_count": row[6]

            })

        return result

    except Exception as e:

        return {
            "error": str(e)
        }

    finally:

        if cur:
            cur.close()

        if conn:
            release_conn(conn)
        
@app.get("/api/uploads/project/{project_name}/download")
def download_upload_data(

    project_name: str,

    x_api_key: str = Header(...)

):

    # -----------------------------------------------------
    # API KEY VALIDATION
    # -----------------------------------------------------

    if x_api_key != API_KEY:

        raise HTTPException(
            status_code=401,
            detail="Invalid API Key"
        )

    conn = get_conn()

    try:

        # -------------------------------------------------
        # LOAD DATA USING PROJECT NAME
        # -------------------------------------------------

        query = """

            SELECT d.*
            FROM etl_data d
            INNER JOIN etl_upload_log l
                ON d.upload_log_id = l.id
            WHERE l.project_name = %s

        """

        df = pd.read_sql_query(
            query,
            conn,
            params=(project_name,)
        )

        # -------------------------------------------------
        # CONVERT TO CSV
        # -------------------------------------------------

        csv_buffer = StringIO()

        df.to_csv(
            csv_buffer,
            index=False
        )

        csv_buffer.seek(0)

        # -------------------------------------------------
        # RETURN DOWNLOAD
        # -------------------------------------------------

        return StreamingResponse(

            iter([csv_buffer.getvalue()]),

            media_type="text/csv",

            headers={
                "Content-Disposition":
                f"attachment; filename={project_name}.csv"
            }
        )

    finally:

        release_conn(conn)
        
       
@app.get("/api/download/all")
def download_all_uploads(

    x_api_key: str = Header(...)

):

    # -----------------------------------------------------
    # API KEY VALIDATION
    # -----------------------------------------------------

    if x_api_key != API_KEY:

        raise HTTPException(
            status_code=401,
            detail="Invalid API Key"
        )

    conn = get_conn()

    try:

        # -------------------------------------------------
        # LOAD ALL DATA
        # -------------------------------------------------

        query = """

            SELECT *
            FROM etl_data
            ORDER BY upload_date DESC

        """

        df = pd.read_sql_query(
            query,
            conn
        )

        # -------------------------------------------------
        # CONVERT TO CSV
        # -------------------------------------------------

        csv_buffer = StringIO()

        df.to_csv(
            csv_buffer,
            index=False
        )

        csv_buffer.seek(0)

        # -------------------------------------------------
        # RETURN FILE
        # -------------------------------------------------

        return StreamingResponse(

            iter([csv_buffer.getvalue()]),

            media_type="text/csv",

            headers={

                "Content-Disposition":
                "attachment; filename=all_uploaded_data.csv"

            }
        )

    finally:

        release_conn(conn)   
        
        
@app.get("/api/uploads/search")
def search_uploads(

    project_name: str = None,
    batch_code: str = None,
    upload_log_id: int = None,

    x_api_key: str = Header(...)

):

    conn = None

    cur = None

    try:

        # -----------------------------------------------------
        # API KEY VALIDATION
        # -----------------------------------------------------

        if x_api_key != API_KEY:

            raise HTTPException(
                status_code=401,
                detail="Invalid API Key"
            )

        conn = get_conn()

        cur = conn.cursor()

        # -------------------------------------------------
        # BASE QUERY
        # -------------------------------------------------

        query = """

            SELECT d.*
            FROM etl_data d
            INNER JOIN etl_upload_log l
                ON d.upload_log_id = l.id
            WHERE 1=1

        """

        params = []

        # -------------------------------------------------
        # OPTIONAL FILTERS
        # -------------------------------------------------

        if project_name:

            query += " AND l.project_name = %s "

            params.append(project_name)

        if batch_code:

            query += " AND l.batch_code = %s "

            params.append(batch_code)

        if upload_log_id:

            query += " AND l.id = %s "

            params.append(upload_log_id)

        query += " LIMIT 100 "

        # -------------------------------------------------
        # EXECUTE
        # -------------------------------------------------

        cur.execute(query, tuple(params))

        columns = [desc[0] for desc in cur.description]

        rows = cur.fetchall()

        result = []

        for row in rows:

            clean_row = {}

            for i, value in enumerate(row):

                if isinstance(value, datetime):

                    clean_row[columns[i]] = str(value)

                else:

                    clean_row[columns[i]] = value

            result.append(clean_row)

        return result

    except Exception as e:

        return {
            "error": str(e)
        }

    finally:

        if cur:
            cur.close()

        if conn:
            release_conn(conn)
        
@app.get("/api/download/search")
def download_search(

    project_name: str = None,
    batch_code: str = None,
    upload_log_id: int = None,

    x_api_key: str = Header(...)

):

    conn = None

    try:

        # -----------------------------------------------------
        # API KEY VALIDATION
        # -----------------------------------------------------

        if x_api_key != API_KEY:

            raise HTTPException(
                status_code=401,
                detail="Invalid API Key"
            )

        # -----------------------------------------------------
        # DB CONNECTION
        # -----------------------------------------------------

        conn = get_conn()

        # -----------------------------------------------------
        # BASE QUERY
        # -----------------------------------------------------

        query = """

            SELECT d.*
            FROM etl_data d
            INNER JOIN etl_upload_log l
                ON d.upload_log_id = l.id
            WHERE 1=1

        """

        params = []

        # -----------------------------------------------------
        # OPTIONAL FILTERS
        # -----------------------------------------------------

        if project_name:

            query += " AND l.project_name = %s "

            params.append(project_name)

        if batch_code:

            query += " AND l.batch_code = %s "

            params.append(batch_code)

        if upload_log_id:

            query += " AND l.id = %s "

            params.append(upload_log_id)

        # -----------------------------------------------------
        # ORDERING
        # -----------------------------------------------------

        query += " ORDER BY d.upload_date DESC "

        # -----------------------------------------------------
        # LOAD DATAFRAME
        # -----------------------------------------------------

        df = pd.read_sql_query(
            query,
            conn,
            params=tuple(params)
        )

        # -----------------------------------------------------
        # EMPTY RESULT CHECK
        # -----------------------------------------------------

        if df.empty:

            return {
                "message": "No matching records found"
            }

        # -----------------------------------------------------
        # CONVERT DATETIME COLUMNS
        # -----------------------------------------------------

        for col in df.columns:

            if pd.api.types.is_datetime64_any_dtype(df[col]):

                df[col] = df[col].astype(str)

        # -----------------------------------------------------
        # CSV EXPORT
        # -----------------------------------------------------

        csv_buffer = StringIO()

        df.to_csv(
            csv_buffer,
            index=False
        )

        csv_buffer.seek(0)

        # -----------------------------------------------------
        # DYNAMIC FILENAME
        # -----------------------------------------------------

        filename = "etl_export.csv"

        if project_name:

            filename = f"{project_name}.csv"

        if batch_code:

            filename = f"{batch_code}.csv"

        if upload_log_id:

            filename = f"upload_{upload_log_id}.csv"

        # -----------------------------------------------------
        # RETURN DOWNLOAD
        # -----------------------------------------------------

        return StreamingResponse(

            iter([csv_buffer.getvalue()]),

            media_type="text/csv",

            headers={

                "Content-Disposition":
                f"attachment; filename={filename}"

            }
        )

    except Exception as e:

        return {
            "error": str(e)
        }

    finally:

        if conn:

            release_conn(conn)
