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
def get_uploads(

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

    cur = conn.cursor()

    try:

        cur.execute("""

            SELECT
                id,
                project_name,
                batch_code,
                file_name,
                author_name,
                upload_date,
                sku_count

            FROM etl_upload_log

            ORDER BY upload_date DESC

        """)

        rows = cur.fetchall()

        data = []

        for row in rows:

            data.append({

                "upload_log_id": row[0],
                "project_name": row[1],
                "batch_code": row[2],
                "file_name": row[3],
                "author_name": row[4],
                "upload_date": str(row[5]),
                "sku_count": row[6]

            })

        return JSONResponse(data)

    finally:

        cur.close()

        release_conn(conn)


# =========================================================
# GET UPLOAD DATA
# =========================================================

@app.get("/api/uploads/{upload_log_id}")
def get_upload_data(

    upload_log_id: int,

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

    cur = conn.cursor()

    try:

        cur.execute("""

            SELECT *
            FROM etl_data
            WHERE upload_log_id = %s
            LIMIT 100

        """, (upload_log_id,))

        columns = [desc[0] for desc in cur.description]

        rows = cur.fetchall()

        result = []

        for row in rows:

            result.append(
                dict(zip(columns, row))
            )

        return JSONResponse(
            content=jsonable_encoder(result)
        )

    finally:

        cur.close()

        release_conn(conn)
        
        
@app.get("/api/uploads/{upload_log_id}/download")
def download_upload_data(

    upload_log_id: int,

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
        # LOAD DATA FROM DB
        # -------------------------------------------------

        query = """

            SELECT *
            FROM etl_data
            WHERE upload_log_id = %s

        """

        df = pd.read_sql_query(
            query,
            conn,
            params=(upload_log_id,)
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
                f"attachment; filename=upload_{upload_log_id}.csv"
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
            