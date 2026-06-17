from fastapi import Depends 
from fastapi.security import ( HTTPBearer, HTTPAuthorizationCredentials ) 
from jose import jwt 
from jose.exceptions import JWTError

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
from io import BytesIO
from fastapi.responses import StreamingResponse

from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from taxonomy_ai import AI_CATEGORY_GROUPS


from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_JWT_SECRET = os.getenv( "SUPABASE_JWT_SECRET" ) 
security = HTTPBearer()


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



def get_role_for_user(

    user_id,
    email

):

    # EXAMPLE

    admin_emails = [

        "govind@altiusnxt.com",

        "thushara@altiusnxt.com"

    ]

    if email in admin_emails:

        return "admin"

    return "user"




def verify_jwt_token(

    credentials: HTTPAuthorizationCredentials

):

    try:

        # -----------------------------------------
        # EXTRACT TOKEN
        # -----------------------------------------

        token = credentials.credentials

        # -----------------------------------------
        # DECODE JWT
        # -----------------------------------------

        payload = jwt.decode(

            token,

            SUPABASE_JWT_SECRET,

            algorithms=["HS256"]

        )

        # -----------------------------------------
        # EXTRACT USER DATA
        # -----------------------------------------

        user_id = payload.get("sub")

        email = payload.get("email")

        role = payload.get(

            "role",

            "authenticated"

        )

        # -----------------------------------------
        # VALIDATE USER
        # -----------------------------------------

        if not user_id:

            raise HTTPException(

                status_code=401,

                detail="Invalid token"

            )

        # -----------------------------------------
        # RETURN USER INFO
        # -----------------------------------------

        return {

            "user_id": user_id,

            "email": email,

            "role": role

        }

    except JWTError:

        raise HTTPException(

            status_code=401,

            detail="Invalid or expired token"

        )




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

    credentials: 
    HTTPAuthorizationCredentials 
    = Depends(security)

):

    conn = None

    cur = None

    try:

        
        # -----------------------------------------
        # VERIFY JWT TOKEN
        # -----------------------------------------

        user = verify_jwt_token(
            credentials
        )

        user_id = user["user_id"]

        user_email = user["email"]



        

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

    credentials:
    HTTPAuthorizationCredentials
    = Depends(security)

):

    # -----------------------------------------------------
    # VERIFY JWT
    # -----------------------------------------------------

    user = verify_jwt_token(
        credentials
    )

    # -----------------------------------------------------
    # ADMIN CHECK
    # -----------------------------------------------------

    if user["role"] != "admin":

        raise HTTPException(

            status_code=403,

            detail="Admin access required"

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
            


@app.get("/api/taxonomy/ai-search")
def ai_taxonomy_search(

    keyword: str,

    limit: int = 100,

    x_api_key: str = Header(...)

):

    conn = None

    cur = None

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
        # DB CONNECTION
        # -------------------------------------------------

        conn = get_conn()

        cur = conn.cursor()

        keyword_lower = keyword.lower()

        # -------------------------------------------------
        # AI SEMANTIC TERMS
        # -------------------------------------------------

        search_terms = AI_CATEGORY_GROUPS.get(

            keyword_lower,

            [keyword_lower]

        )

        if keyword_lower not in search_terms:

            search_terms.append(keyword_lower)

        # -------------------------------------------------
        # BUILD SQL CONDITIONS
        # -------------------------------------------------

        conditions = []

        params = []

        for term in search_terms:

            conditions.append(

                "LOWER(taxonomy) LIKE %s"

            )

            params.append(f"%{term}%")

        where_clause = " OR ".join(conditions)

        # -------------------------------------------------
        # QUERY
        # -------------------------------------------------

       
        
        query = f"""

            SELECT

                
                asn_altiusnxt_stock_number,

                file_name,


                manufacturer_name,
                manufacturer_part_number,

               
                taxonomy,

                manufacturer_name_1,
                manufacturer_part_number_1,
                manufacturer_part_number_2


                

            FROM etl_data

            WHERE taxonomy IS NOT NULL

            AND ({where_clause})

            ORDER BY sku_id

            LIMIT %s

        """





        params.append(limit)

        # -------------------------------------------------
        # EXECUTE
        # -------------------------------------------------

        cur.execute(query, tuple(params))

        columns = [

            desc[0]

            for desc in cur.description

        ]

        rows = cur.fetchall()

        result = []

        # -------------------------------------------------
        # CLEAN SERIALIZATION
        # -------------------------------------------------

        for row in rows:

            clean_row = {}

            for i, value in enumerate(row):

                if isinstance(value, datetime):

                    clean_row[columns[i]] = str(value)

                else:

                    clean_row[columns[i]] = value

            result.append(clean_row)

        return {

            "search_keyword": keyword,

            "matched_terms": search_terms,

            "total_products": len(result),

            "products": result

        }

    except Exception as e:

        return {

            "error": str(e)

        }

    finally:

        if cur:
            cur.close()

        if conn:
            release_conn(conn)
            
            
    
@app.get("/api/taxonomy/ai-search/download")
def download_ai_taxonomy_search(

    keyword: str,

    limit: int = 10000,

    x_api_key: str = Header(...)

):

    conn = None

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
        # DB CONNECTION
        # -------------------------------------------------

        conn = get_conn()

        keyword_lower = keyword.lower()

        # -------------------------------------------------
        # AI SEARCH TERMS
        # -------------------------------------------------

        search_terms = AI_CATEGORY_GROUPS.get(

            keyword_lower,

            [keyword_lower]

        )

        if keyword_lower not in search_terms:

            search_terms.append(keyword_lower)

        # -------------------------------------------------
        # BUILD SQL CONDITIONS
        # -------------------------------------------------

        conditions = []

        params = []

        for term in search_terms:

            conditions.append(

                "LOWER(taxonomy) LIKE %s"

            )

            params.append(f"%{term}%")

        where_clause = " OR ".join(conditions)

        # -------------------------------------------------
        # QUERY
        # -------------------------------------------------

        query = f"""

            SELECT 
            
            asn_altiusnxt_stock_number,

            file_name,

            manufacturer_name,

            manufacturer_part_number,

            taxonomy

            FROM etl_data

            WHERE taxonomy IS NOT NULL

            AND ({where_clause})

            ORDER BY sku_id

            LIMIT %s

        """

        params.append(limit)

        # -------------------------------------------------
        # LOAD DATAFRAME
        # -------------------------------------------------

        df = pd.read_sql_query(

            query,

            conn,

            params=tuple(params)

        )

        # -------------------------------------------------
        # EMPTY CHECK
        # -------------------------------------------------

        if df.empty:

            return {

                "message": "No matching products found"

            }
            
            
        # -------------------------------------------------
        # REMOVE TIMEZONE
        # -------------------------------------------------

        for col in df.select_dtypes(include=["datetimetz"]).columns:

            df[col] = df[col].dt.tz_localize(None)    

        # -------------------------------------------------
        # EXCEL EXPORT
        # -------------------------------------------------

        output = BytesIO()

        with pd.ExcelWriter(

            output,

            engine="openpyxl"

        ) as writer:

            df.to_excel(

                writer,

                index=False,

                sheet_name="AI_Search_Results"

            )

        output.seek(0)

        # -------------------------------------------------
        # RETURN EXCEL FILE
        # -------------------------------------------------

        filename = (
            f"taxonomy_ai_search_{keyword}.xlsx"
        )

        return StreamingResponse(

            output,

            media_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),

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

            
            
@app.get("/api/taxonomy/project/{project_name}")
def get_project_taxonomy(

    project_name: str,

    limit: int = 100,

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

        conn = get_conn()

        cur = conn.cursor()

        # -----------------------------------------
        # QUERY
        # -----------------------------------------

        cur.execute("""

            SELECT

                d.asn_altiusnxt_stock_number,

                d.file_name,

                d.manufacturer_name,

                d.manufacturer_part_number,

                d.taxonomy

            FROM etl_data d

            INNER JOIN etl_upload_log l

                ON d.upload_log_id = l.id

            WHERE l.project_name = %s

            AND d.taxonomy IS NOT NULL

            AND d.taxonomy <> ''

            ORDER BY d.taxonomy

            LIMIT %s

        """, (

            project_name,

            limit

        ))

        rows = cur.fetchall()

        # -----------------------------------------
        # FORMAT RESPONSE
        # -----------------------------------------

        result = []

        for row in rows:

            result.append({

                "asn_altiusnxt_stock_number": row[0],

                "file_name": row[1],

                "manufacturer_name": row[2],

                "manufacturer_part_number": row[3],

                "taxonomy": row[4]

            })

        return {

            "project_name": project_name,

            "limit": limit,

            "returned_rows": len(result),

            "products": result

        }

    except Exception as e:

        return {

            "error": str(e)

        }

    finally:

        if cur:
            cur.close()

        if conn:
            release_conn(conn)
@app.get("/api/taxonomy/project/{project_name}/download")
def download_project_taxonomy(

    project_name: str,

    x_api_key: str = Header(...)

):

    conn = None

    try:

        # -----------------------------------------
        # API KEY VALIDATION
        # -----------------------------------------

        if x_api_key != API_KEY:

            raise HTTPException(
                status_code=401,
                detail="Invalid API Key"
            )

        conn = get_conn()

        # -----------------------------------------
        # QUERY
        # -----------------------------------------

        query = """

            SELECT

                d.asn_altiusnxt_stock_number,

                d.file_name,

                d.manufacturer_name,

                d.manufacturer_part_number,

                d.taxonomy

            FROM etl_data d

            INNER JOIN etl_upload_log l

                ON d.upload_log_id = l.id

            WHERE l.project_name = %s

            AND d.taxonomy IS NOT NULL

            AND d.taxonomy <> ''

            ORDER BY d.taxonomy

        """

        df = pd.read_sql_query(

            query,

            conn,

            params=(project_name,)

        )

        # -----------------------------------------
        # EMPTY CHECK
        # -----------------------------------------

        if df.empty:

            return {
                "message": "No taxonomy found"
            }

        # -----------------------------------------
        # CSV EXPORT
        # -----------------------------------------

        csv_buffer = StringIO()

        df.to_csv(

            csv_buffer,

            index=False

        )

        csv_buffer.seek(0)

        # -----------------------------------------
        # RETURN DOWNLOAD
        # -----------------------------------------

        return StreamingResponse(

            iter([csv_buffer.getvalue()]),

            media_type="text/csv",

            headers={

                "Content-Disposition":
                f"attachment; filename={project_name}_taxonomy.csv"

            }
        )

    except Exception as e:

        return {
            "error": str(e)
        }

    finally:

        if conn:
            release_conn(conn)  
            
@app.get("/api/taxonomy/download/all")
def download_all_taxonomy(

    x_api_key: str = Header(...)

):

    conn = None

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
        # DB CONNECTION
        # -------------------------------------------------

        conn = get_conn()

        # -------------------------------------------------
        # QUERY
        # -------------------------------------------------

        query = """

            SELECT

                asn_altiusnxt_stock_number,

                file_name,

                manufacturer_name,

                manufacturer_part_number,

                taxonomy

            FROM etl_data

            WHERE taxonomy IS NOT NULL

            AND taxonomy <> ''

            ORDER BY taxonomy

        """

        df = pd.read_sql_query(

            query,

            conn

        )

        # -------------------------------------------------
        # EMPTY CHECK
        # -------------------------------------------------

        if df.empty:

            return {

                "message": "No taxonomy found"

            }

        # -------------------------------------------------
        # CSV EXPORT
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
                "attachment; filename=all_taxonomy.csv"

            }
        )

    except Exception as e:

        return {

            "error": str(e)

        }

    finally:

        if conn:

            release_conn(conn)   
@app.get("/api/duplicates")
def get_duplicates(

    project_name: str,

    x_api_key: str = Header(...)

):

    conn = None

    try:

        # -----------------------------------------
        # API KEY VALIDATION
        # -----------------------------------------

        if x_api_key != API_KEY:

            raise HTTPException(

                status_code=401,

                detail="Invalid API Key"

            )

        conn = get_conn()

        # -----------------------------------------
        # QUERY
        # -----------------------------------------

        query = """

            SELECT

                e.asn_altiusnxt_stock_number,

                e.file_name,

                e.manufacturer_name,

                e.manufacturer_part_number

            FROM etl_data e

            INNER JOIN etl_upload_log l

                ON e.upload_log_id = l.id

            WHERE

                l.project_name = %s

                AND e.manufacturer_name IS NOT NULL

                AND e.manufacturer_part_number IS NOT NULL

                AND TRIM(e.manufacturer_name) <> ''

                AND TRIM(e.manufacturer_part_number) <> ''

                AND (

                    LOWER(TRIM(e.manufacturer_name)),

                    LOWER(TRIM(e.manufacturer_part_number))

                ) IN (

                    SELECT

                        LOWER(TRIM(d.manufacturer_name)),

                        LOWER(TRIM(d.manufacturer_part_number))

                    FROM etl_data d

                    INNER JOIN etl_upload_log l2

                        ON d.upload_log_id = l2.id

                    WHERE

                        l2.project_name = %s

                        AND d.manufacturer_name IS NOT NULL

                        AND d.manufacturer_part_number IS NOT NULL

                        AND TRIM(d.manufacturer_name) <> ''

                        AND TRIM(d.manufacturer_part_number) <> ''

                    GROUP BY

                        LOWER(TRIM(d.manufacturer_name)),

                        LOWER(TRIM(d.manufacturer_part_number))

                    HAVING COUNT(*) > 1

                )

            ORDER BY

                e.manufacturer_name,

                e.manufacturer_part_number

        """

        # -----------------------------------------
        # LOAD DATAFRAME
        # -----------------------------------------

        df = pd.read_sql_query(

            query,

            conn,

            params=(

                project_name,

                project_name

            )

        )

        # -----------------------------------------
        # EMPTY CHECK
        # -----------------------------------------

        if df.empty:

            return {

                "project_name": project_name,

                "total_duplicate_rows": 0,

                "message": "No duplicates found",

                "rows": []

            }

        # -----------------------------------------
        # RETURN RESPONSE
        # -----------------------------------------

        return {

            "project_name": project_name,

            "total_duplicate_rows": len(df),

            "columns": list(df.columns),

            "rows": df.to_dict(

                orient="records"

            )

        }

    except Exception as e:

        return {

            "error": str(e)

        }

    finally:

        if conn:

            release_conn(conn)
            
              
            
@app.get("/api/duplicates/download")
def download_duplicates(

    x_api_key: str = Header(...)

):

    conn = None

    try:

        # -----------------------------------------
        # API KEY VALIDATION
        # -----------------------------------------

        if x_api_key != API_KEY:

            raise HTTPException(

                status_code=401,

                detail="Invalid API Key"

            )

        conn = get_conn()

        # -----------------------------------------
        # QUERY
        # -----------------------------------------

        
        query = """

            SELECT
                asn_altiusnxt_stock_number,
                file_name,
                manufacturer_name,
                manufacturer_part_number
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
            ORDER BY
                manufacturer_name,
                manufacturer_part_number;

        """


        
        # -----------------------------------------
        # LOAD DATAFRAME
        # -----------------------------------------

        df = pd.read_sql_query(

            query,

            conn

        )




        # -----------------------------------------
        # EMPTY CHECK
        # -----------------------------------------

        if df.empty:

            return {

                "message": "No duplicates found"

            }

        
        # -------------------------------------------------
        # REMOVE TIMEZONE FOR EXCEL
        # -------------------------------------------------

        for col in df.select_dtypes(
            include=["datetimetz"]
        ).columns:

            df[col] = df[col].dt.tz_localize(None)

        # -------------------------------------------------
        # EXCEL EXPORT
        # -------------------------------------------------

        output = BytesIO()

        with pd.ExcelWriter(

            output,

            engine="openpyxl"

        ) as writer:

            df.to_excel(

                writer,

                index=False,

                sheet_name="Duplicate_Report"

            )

        output.seek(0)

        # -------------------------------------------------
        # RETURN EXCEL
        # -------------------------------------------------

        return StreamingResponse(

            output,

            media_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),

            headers={

                "Content-Disposition":
                "attachment; filename=duplicate_report.xlsx"

            }
        )



    except Exception as e:

        return {

            "error": str(e)

        }

    finally:

        if conn:

            release_conn(conn)                                               