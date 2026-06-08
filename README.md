# ETL Visual Data Mapper

A secure and scalable ETL data mapping platform built with Streamlit, PostgreSQL, and Supabase for uploading, mapping, validating, and managing large ETL datasets with user authentication, taxonomy search, project-wise templates, and export capabilities.

---

# 🚀 Features

## 🔐 Authentication & Role Management
- User Sign Up / Sign In using Supabase Auth
- Session persistence
- Role-based access:
  - User
  - Admin
- Admin-only permanent delete functionality

---

## 📂 File Upload Support
Supports:
- CSV
- XLSX
- XLS
- ODS

Features:
- Persistent upload cache
- Automatic dataframe restoration
- Duplicate upload detection
- Large file handling

---

## 🔄 ETL Mapping Workflow

Multi-step ETL processing UI:

1. Upload File
2. Field Mapping
3. Attribute Selection
4. Unmapped Fields Review
5. Summary
6. Database Insert Result

---

## 🧠 Smart Auto Mapping
- Automatic source-to-target field suggestion
- Fuzzy column matching
- Project-wise mapping template reuse

---

## 🗂 Project-Based Mapping Templates
Save and reuse mappings:
- Project-specific mappings
- User-specific templates
- Auto-apply mappings for future uploads

---

## 🔍 Advanced Search
Search uploaded files using:
- Project Code
- Batch Code
- Taxonomy

Includes:
- Pagination
- File-level taxonomy search
- Global SKU taxonomy search

---

## 📊 Export Capabilities
Export:
- CSV
- Excel

Supports:
- Full dataset export
- Project-wise export
- Active records only

---

## ⚡ Performance Optimizations
- PostgreSQL connection pooling
- Streamlit caching
- Vectorized dataframe operations
- Chunked bulk inserts
- Parquet caching for fast reloads

---

# 🏗 Tech Stack

| Technology | Purpose |
|---|---|
| Python | Backend Logic |
| Streamlit | Web UI |
| PostgreSQL | Database |
| Supabase | Authentication |
| Pandas | Data Processing |
| psycopg2 | PostgreSQL Connectivity |

---

# 📁 Project Structure

```bash
project/
│
├── etl_app.py
├── style.css
├── .env
├── requirements.txt
├── README.md
│
├── .upload_cache/
│
└── assets/
```

---

# ⚙️ Environment Variables

Create a `.env` file:

```env
# PostgreSQL
DB_HOST=localhost
DB_PORT=5432
DB_NAME=your_database
DB_USER=your_user
DB_PASSWORD=your_password

# Supabase
SUPABASE_URL=your_supabase_url
SUPABASE_ANON_KEY=your_supabase_anon_key
```

---

# 📦 Installation

## 1. Clone Repository

```bash
git clone https://github.com/your-username/etl-visual-data-mapper.git
cd etl-visual-data-mapper
```

---

## 2. Create Virtual Environment

### Windows

```bash
python -m venv venv
venv\Scripts\activate
```

### Linux / Mac

```bash
python3 -m venv venv
source venv/bin/activate
```

---

## 3. Install Dependencies

```bash
pip install -r requirements.txt
```

---

# ▶️ Run Application

```bash
streamlit run etl_app.py
```

Application runs on:

```bash
http://localhost:8501
```

---

# 🗄 Database Tables

The app automatically creates:

- `etl_upload_log`
- `etl_data`
- `etl_mapping_template`

---

# 🔒 Security Features

- Environment variable-based credentials
- No hardcoded database secrets
- User-isolated data access
- Role-based authorization
- Protected admin actions

---

# 📈 Use Cases

- ETL Data Mapping
- Product Catalog Processing
- SKU Management
- Taxonomy Classification
- Supplier Data Upload
- Bulk Data Transformation
- Product Information Management (PIM)

---

# 🧩 Core Functionalities

## Upload Management
- Duplicate prevention
- Metadata tracking
- Upload history

## Mapping Engine
- Source-to-target mapping
- Auto suggestions
- Reusable templates

## Attribute Handling
- Dynamic attribute selection
- Unmapped field tracking
- JSONB storage

## Search Engine
- Taxonomy filtering
- Global SKU search
- Paginated results

---

# 🛠 Future Improvements

- AI-based field mapping
- Drag-and-drop mapping UI
- Background task queue
- Multi-user collaboration
- Audit logs
- Dashboard analytics
- API integrations

---

# 👨‍💻 Author

Developed by **Thushara T S**

---

# 📄 License

This project is licensed under the MIT License.

---

# ⭐ GitHub Setup Tips

## Create `.gitignore`

```gitignore
venv/
__pycache__/
.upload_cache/
.env
*.parquet
```

---

## Generate requirements.txt

```bash
pip freeze > requirements.txt
```

---

# 🌟 Suggested Repository Names

- etl-visual-data-mapper
- smart-etl-mapper
- etl-mapping-platform
- streamlit-etl-workbench
- etl-taxonomy-manager

## Setup

pip install -r requirements.txt

## Run

streamlit run etl_app.py
