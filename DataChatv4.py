# ============================================================
# NEXADATA AI
# Ask. Analyze. Discover.
# General Questions + Data Questions + Email / View / Download
# ============================================================
import ast
import html
import io
import json
import os
import re
import smtplib
from email.message import EmailMessage
from pathlib import Path
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import duckdb
import psycopg
from psycopg import sql
from openai import OpenAI
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    LongTable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    TableStyle,
)
# --------------------------- Page setup ---------------------------
st.set_page_config(
    page_title="NexaData AI",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)
DATA_FOLDER = Path(r"C:\AI_DATA_SOLUTION")
API_KEY = ""
MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()
try:
    secret_api_key = st.secrets.get("OPENAI_API_KEY", "")
except Exception:
    secret_api_key = ""
api_key = (os.getenv("OPENAI_API_KEY") or secret_api_key or API_KEY).strip()
client = OpenAI(api_key=api_key) if api_key else None
# ------------------------------ Styling ---------------------------
st.markdown(
    """
    <style>
    :root {
      --nexa-bg: #050814; --nexa-panel: #0b1328; --nexa-border: #1c2b45;
      --nexa-text: #f4f7ff; --nexa-muted: #9aa9c1; --nexa-blue: #079fe8;
    }
    .stApp { background: radial-gradient(ellipse at top, #0b1b30 0%, #050814 54%); color: var(--nexa-text); }
    .block-container { padding-top: 1.15rem; padding-bottom: 2rem; max-width: 1080px; }
    [data-testid="stSidebar"] { background: #070d1d; border-right: 1px solid var(--nexa-border); }
    [data-testid="stSidebar"] * { color: var(--nexa-text); }
    h1,h2,h3,h4,p,label,span,div { color: inherit; }
    .dm-brand { font-size: 1.55rem; font-weight: 800; letter-spacing: -.04em; color: #fff; }
    .dm-tagline { color: var(--nexa-muted); font-size: .9rem; margin-top: -.15rem; }
    .dm-hero {
      padding: 1.8rem 1.2rem; border-radius: 24px;
      background: linear-gradient(145deg, rgba(10,28,53,.98), rgba(5,10,25,.98));
      border: 1px solid #172c48; margin-bottom: 1.1rem; text-align: center;
      box-shadow: 0 16px 40px rgba(0,0,0,.22);
    }
    .dm-hero h2 { margin: 0; color: #f8fbff; font-size: clamp(1.5rem,4vw,2.2rem); }
    .dm-hero p { color: #9aa9c1; margin: .55rem auto 0; max-width: 680px; }
    .dm-card {
      padding: 1rem 1.15rem; border: 1px solid #1b2b45; border-radius: 18px;
      background: #0b1328;
    }
    div[data-testid="stTabs"] button[role="tab"] {
      border-radius: 999px; border: 1px solid #1b2b45; padding: .55rem 1rem;
      background: #0b1328; color: #c7d3e7;
    }
    div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
      background: linear-gradient(90deg,#087fbd,#1457cb); color: #fff; border-color: #159fe4;
    }
    div.stButton > button, div.stFormSubmitButton > button, div.stDownloadButton > button {
      border-radius: 999px; min-height: 2.7rem; border: 1px solid #21415f;
      background: #0c1a32; color: #f5f8ff;
    }
    div.stButton > button[kind="primary"], div.stFormSubmitButton > button[kind="primary"] {
      background: linear-gradient(90deg,#087fbd,#087fbd); border-color: #139fe2; color: white;
    }
    input, textarea, [data-baseweb="select"] > div {
      background: #091226 !important; color: #f4f7ff !important; border-color: #203653 !important;
    }
    [data-testid="stDataFrame"], [data-testid="stTable"] { border: 1px solid #1c2b45; border-radius: 12px; overflow: hidden; }
    [data-testid="stExpander"] { border: 1px solid #1c2b45; border-radius: 14px; background: #0a1225; }
    hr { border-color: #1b2b45; }
    [data-testid="stCaptionContainer"] { color: #93a4be; }
    @media (max-width: 700px) {
      .block-container { padding-left: .75rem; padding-right: .75rem; padding-top: .6rem; }
      .dm-hero { padding: 1.35rem .8rem; border-radius: 20px; }
      div[data-testid="stTabs"] button[role="tab"] { padding: .45rem .6rem; font-size: .85rem; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)
# Business terminology and table/column mappings are maintained in PostgreSQL:
# public.business_dictionary. The live schema is read from information_schema.
# Avoid hard-coded sample-database definitions so the app stays aligned with NexaData.
# ------------------------------ Helpers ---------------------------
@st.cache_data(show_spinner=False)
def read_dataset(file_path, file_bytes=None):
    suffix = Path(file_path).suffix.lower()
    source = io.BytesIO(file_bytes) if file_bytes is not None else file_path
    if suffix == ".csv":
        return pd.read_csv(source, low_memory=False)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(source)
    raise ValueError("Unsupported file format. Use CSV or Excel.")
def list_postgres_tables(config):
    """List tables across the NexaData business schemas."""
    query = """
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_type IN ('BASE TABLE', 'VIEW', 'MATERIALIZED VIEW')
          AND table_schema IN ('master', 'product', 'transactions', 'finance', 'logistics', 'analytics')
        ORDER BY table_schema, table_name;
    """
    with psycopg.connect(**config) as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            return [f"{schema_name}.{table_name}" for schema_name, table_name in cur.fetchall()]
def read_postgres_table(config, table_name, schema_name=None):
    """Load one selected schema-qualified PostgreSQL table safely."""
    if schema_name is None:
        if "." not in table_name:
            raise ValueError("Choose a schema-qualified table, for example master.customer.")
        schema_name, table_name = table_name.split(".", 1)
    query = sql.SQL("SELECT * FROM {}.{}").format(
        sql.Identifier(schema_name), sql.Identifier(table_name)
    )
    with psycopg.connect(**config) as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
            columns = [column.name for column in cur.description]
    return pd.DataFrame(rows, columns=columns)
def get_postgres_schema(config):
    """Return live columns/types for all NexaData business schemas."""
    query = """
        SELECT table_schema, table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema IN ('master', 'product', 'transactions', 'finance', 'logistics', 'analytics')
        ORDER BY table_schema, table_name, ordinal_position;
    """
    with psycopg.connect(**config) as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
    schema = {}
    for schema_name, table_name, column_name, data_type in rows:
        schema.setdefault(f"{schema_name}.{table_name}", []).append(
            f"{column_name} ({data_type})"
        )
    return "\n".join(
        f"{table}: " + ", ".join(columns)
        for table, columns in schema.items()
    )
def get_database_business_dictionary(config):
    """Read the live business dictionary stored in public.business_dictionary."""
    query = """
        SELECT business_term, definition, schema_name, table_name, column_name,
               synonyms, join_guidance, example_question
        FROM public.business_dictionary
        WHERE is_active = TRUE
        ORDER BY business_term;
    """
    with psycopg.connect(**config) as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
    if not rows:
        raise RuntimeError(
            "public.business_dictionary has no active terms. Add/activate NexaData "
            "business terms before asking data-specific questions."
        )
    return "\n".join(
        f"- Term: {term}; Meaning: {definition}; Table: "
        f"{(schema_name + '.' + table_name) if schema_name and table_name else 'not specified'}; "
        f"Column: {column_name or 'not specified'}; Synonyms: {synonyms or 'none'}; "
        f"Join guidance: {join_guidance or 'none'}; Example: {example_question or 'none'}"
        for term, definition, schema_name, table_name, column_name, synonyms,
            join_guidance, example_question in rows
    )
def ask_postgres_sql(question, config):
    """Generate read-only SQL using the live schema and DB-stored dictionary."""
    schema_description = get_postgres_schema(config)
    if not schema_description.strip():
        raise RuntimeError(
            "No columns were found in the master, product, transactions, finance, logistics, or analytics schemas. "
            "Confirm the app is connected to nexadata_db."
        )
    business_dictionary = get_database_business_dictionary(config)
    prompt = f"""
You are NexaData AI, a natural-language-to-SQL data analyst.
The connected database is the NexaData business database named nexadata_db.
It contains the master, product, transactions, finance, logistics, and analytics schemas. The analytics schema includes reporting views.
YOUR TASK:
Interpret the user's natural-language business question using the business dictionary,
then generate a PostgreSQL query using only the live database schema below.
Do not produce Python, Pandas code, a Pandas expression, or an explanation.
BUSINESS DICTIONARY FROM public.business_dictionary:
{business_dictionary}
LIVE DATABASE SCHEMA (authoritative; use schema-qualified table names):
{schema_description}
QUESTION:
{question}
RULES:
- Return exactly one PostgreSQL SELECT query. A WITH query is allowed only if it ultimately performs SELECT.
- Use schema-qualified names such as master.customer, transactions.payment, finance.invoice, logistics.shipment, and analytics.monthly_sales_summary.
- Use explicit JOIN ... ON conditions when multiple tables are needed.
- Revenue/collections means SUM(transactions.payment.amount); filter payment_status = 'Success'
  when the user specifically asks for successful payments.
- Sales line value means SUM(quantity * unit_price - discount_amount), using
  transactions.sales_order_item. Do not call this payment revenue unless asked.
- Customer count means COUNT(*) from master.customer unless a more specific definition is requested.
- Avoid double-counting by aggregating payments and order items at the appropriate grain.
- Never invent table names, columns, relationships, or business facts.
- Use only tables, views, and columns shown in the live schema. Never assume a column based on its name.
- For analytics.monthly_sales_summary, use its live columns exactly as listed (including sales_month, branch_id, total_orders, total_sales when present); never invent a column named month.
- Prefer a matching analytics view when it directly answers the user's question.
- If the question cannot be answered from the listed schema, return a safe SELECT that explains the limitation as a text result.
- Do not return markdown, comments, explanations, or multiple statements.
- Never generate INSERT, UPDATE, DELETE, MERGE, DDL, COPY, CALL, or admin commands.
- Return only the SQL query.
"""
    response = require_client().responses.create(
        model=MODEL_NAME,
        input=prompt,
        max_output_tokens=900,
    )
    return clean_code(response.output_text).strip().rstrip(";").strip()
def validate_readonly_sql(query):
    """Reject non-SELECT statements and risky PostgreSQL functions."""
    query = query.strip()
    if not re.match(r"^(SELECT|WITH)\b", query, flags=re.IGNORECASE):
        raise ValueError("Only SELECT queries are allowed for PostgreSQL data analysis.")
    if ";" in query:
        raise ValueError("Only one SQL statement is allowed; remove internal semicolons.")
    blocked_words = re.compile(
        r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|CREATE|TRUNCATE|COPY|CALL|DO|"
        r"GRANT|REVOKE|VACUUM|ANALYZE|SET|RESET|BEGIN|COMMIT|ROLLBACK)\b",
        flags=re.IGNORECASE,
    )
    if blocked_words.search(query):
        raise ValueError("The generated query contains a disallowed SQL operation.")
    blocked_functions = re.compile(
        r"\b(pg_read_file|pg_ls_dir|pg_sleep|dblink|lo_import|lo_export|"
        r"set_config|nextval|setval|pg_terminate_backend|pg_cancel_backend)\s*\(",
        flags=re.IGNORECASE,
    )
    if blocked_functions.search(query):
        raise ValueError("The generated query uses a disallowed PostgreSQL function.")
    return query
def execute_postgres_query(query, config):
    """Execute one validated SELECT in a read-only transaction and return rows."""
    query = validate_readonly_sql(query)
    with psycopg.connect(**config) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute(query)
            if cur.description is None:
                raise ValueError("The SQL query did not return a result set.")
            rows = cur.fetchall()
            columns = [column.name for column in cur.description]
    return pd.DataFrame(rows, columns=columns)
def require_client():
    if client is None:
        raise RuntimeError(
            "OpenAI API is not configured. Set the OPENAI_API_KEY environment "
            "variable or add your key to API_KEY near the top of app.py. "
            "A valid API key and available API credits are required."
        )
    return client
def ask_general(question):
    response = require_client().responses.create(
        model=MODEL_NAME,
        input=(
            "You are NexaData AI, a clear and helpful assistant. "
            "Answer the user's general question accurately and practically. "
            "Use headings or short bullet points when useful. Do not claim "
            "to have inspected the user's dataset unless the question asks "
            "about data and dataset context is provided.\n\n"
            f"User question: {question}"
        ),
        max_output_tokens=900,
    )
    return response.output_text.strip()
def ask_local_sql(question, frame):
    """Generate DuckDB SQL for a local CSV/Excel DataFrame."""
    if frame is None or frame.empty:
        raise ValueError("The selected file has no rows to query.")
    # DuckDB can struggle with duplicate column labels; fail clearly rather than
    # generate SQL that could refer to an ambiguous column.
    columns = [str(c) for c in frame.columns]
    if len(columns) != len(set(columns)):
        raise ValueError("The file contains duplicate column names. Rename duplicate columns and try again.")
    metadata = {
        "table_name": "uploaded_data",
        "row_count": int(len(frame)),
        "columns": [{"name": str(c), "dtype": str(frame[c].dtype)} for c in frame.columns],
        "sample_rows": frame.head(5).fillna("").astype(str).to_dict(orient="records"),
    }
    prompt = f"""
You are NexaData AI, an expert natural-language-to-SQL data analyst.
Generate a DuckDB SQL query for the local file currently loaded into a registered table named uploaded_data.
TABLE METADATA (authoritative; use only these columns):
{json.dumps(metadata, ensure_ascii=False, default=str)}
USER QUESTION:
{question}
RULES:
- Return exactly one DuckDB SELECT query. A WITH query is allowed only if it ultimately performs SELECT.
- The only available table is uploaded_data. Do not refer to any other table or database.
- Use exact column names from the metadata. Quote unusual or mixed-case names with double quotes.
- Do not invent columns, table names, values, or relationships.
- For aggregations, use appropriate GROUP BY / ORDER BY clauses.
- Use DuckDB-compatible SQL syntax.
- Do not output Python, Pandas, markdown fences, comments, explanations, or multiple statements.
- Never generate INSERT, UPDATE, DELETE, MERGE, DDL, COPY, ATTACH, DETACH, CALL, PRAGMA, or admin commands.
- Do not use file-reading functions or external access functions.
- Return only the SQL query.
"""
    response = require_client().responses.create(
        model=MODEL_NAME,
        input=prompt,
        max_output_tokens=700,
    )
    return clean_code(response.output_text).strip().rstrip(";").strip()
def clean_code(code):
    """Remove optional Markdown fences from model-generated SQL/Python."""
    code = code.strip()
    code = re.sub(r"^```(?:python|sql|postgresql)?\s*", "", code, flags=re.IGNORECASE)
    code = re.sub(r"\s*```$", "", code)
    return code.strip()
def validate_code(code):
    tree = ast.parse(code, mode="eval")
    allowed_names = {"df", "pd"}
    allowed_nodes = (
        ast.Expression, ast.Name, ast.Load, ast.Constant, ast.Subscript,
        ast.Slice, ast.Tuple, ast.List, ast.Dict, ast.Call, ast.Attribute,
        ast.Compare, ast.BoolOp, ast.BinOp, ast.UnaryOp, ast.And, ast.Or,
        ast.Not, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
        ast.In, ast.NotIn, ast.Is, ast.IsNot, ast.Add, ast.Sub, ast.Mult,
        ast.Div, ast.FloorDiv, ast.Mod, ast.USub, ast.UAdd,
    )
    blocked_names = {
        "eval", "exec", "open", "compile", "__import__", "globals", "locals",
        "getattr", "setattr", "delattr", "input", "breakpoint", "help",
        "dir", "vars",
    }
    blocked_attributes = {
        "to_csv", "to_excel", "to_pickle", "to_sql", "to_json", "to_parquet",
        "to_clipboard", "to_hdf", "to_feather", "to_stata", "read_csv",
        "read_excel", "read_parquet", "read_pickle", "read_json", "read_sql",
        "tofile", "save", "system", "popen",
    }
    for node in ast.walk(tree):
        if not isinstance(node, allowed_nodes):
            raise ValueError(f"Unsupported operation in expression: {type(node).__name__}")
        if isinstance(node, ast.Name):
            if node.id in blocked_names or node.id not in allowed_names:
                raise ValueError(f"Name not allowed: {node.id}")
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("_") or node.attr in blocked_attributes:
                raise ValueError(f"Operation not allowed: {node.attr}")
        if isinstance(node, ast.Call) and not isinstance(node.func, ast.Attribute):
            raise ValueError("Only DataFrame or pandas methods may be called.")
    return code
def result_to_df(result):
    """Convert query output for display/export without exposing a row index."""
    if isinstance(result, pd.DataFrame):
        return result.reset_index(drop=True).copy()
    if isinstance(result, pd.Series):
        return result.to_frame(name=result.name or "Value").reset_index(drop=True)
    return pd.DataFrame({"Answer": [result]})
def validate_local_sql(query):
    """Allow one read-only SELECT against the registered local table only."""
    query = clean_code(query).strip()
    if not re.match(r"^(SELECT|WITH)\b", query, flags=re.IGNORECASE):
        raise ValueError("Only SELECT queries are allowed for local-file analysis.")
    if ";" in query:
        raise ValueError("Only one SQL statement is allowed.")
    blocked_words = re.compile(
        r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|CREATE|TRUNCATE|COPY|ATTACH|DETACH|CALL|PRAGMA|INSTALL|LOAD|EXPORT|IMPORT|SET|RESET|BEGIN|COMMIT|ROLLBACK|GRANT|REVOKE)\b",
        flags=re.IGNORECASE,
    )
    if blocked_words.search(query):
        raise ValueError("The generated query contains a disallowed SQL operation.")
    blocked_functions = re.compile(
        r"\b(read_csv|read_csv_auto|read_parquet|read_json|read_json_auto|glob|httpfs|sqlite_scan|postgres_scan|parquet_scan|csv_scan)\s*\(",
        flags=re.IGNORECASE,
    )
    if blocked_functions.search(query):
        raise ValueError("The generated query contains a disallowed file or external-access function.")
    # DuckDB has only the registered uploaded_data relation in this in-memory
    # connection. Unknown tables fail at execution; CTE names remain supported.
    return query

def execute_local_sql(query, frame):
    """Execute a validated DuckDB query against the selected local file data."""
    query = validate_local_sql(query)
    if frame is None:
        raise ValueError("No local dataset is loaded.")
    with duckdb.connect(database=":memory:") as connection:
        connection.register("uploaded_data", frame)
        result = connection.execute(query).fetchdf()
    return result
def safe_filename(question):
    name = re.sub(r"[^a-zA-Z0-9_-]+", "_", question.lower()).strip("_")
    return (name or "nexadata_result")[:70]
def generate_excel(result):
    buffer = io.BytesIO()
    result_to_df(result).to_excel(
        buffer, index=False, sheet_name="Analysis Result", engine="openpyxl"
    )
    return buffer.getvalue()
def generate_pdf(question, dataset_name, result):
    output_df = result_to_df(result)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4), rightMargin=24, leftMargin=24,
        topMargin=24, bottomMargin=24,
    )
    styles = getSampleStyleSheet()
    story = [
        Paragraph("NexaData AI Report", styles["Title"]),
        Spacer(1, 10),
        Paragraph(f"<b>Dataset:</b> {html.escape(str(dataset_name))}", styles["Normal"]),
        Spacer(1, 6),
        Paragraph(f"<b>Question:</b> {html.escape(str(question))}", styles["Normal"]),
        Spacer(1, 10),
    ]
    pdf_df = output_df.head(500).fillna("").astype(str)
    table_data = [[str(c)[:40] for c in pdf_df.columns]]
    table_data.extend([[str(v)[:100] for v in row] for row in pdf_df.itertuples(index=False, name=None)])
    if pdf_df.empty:
        table_data = [["No result rows"]]
    table = LongTable(table_data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#243b80")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(table)
    if len(output_df) > 500:
        story.extend([
            Spacer(1, 8),
            Paragraph("PDF contains the first 500 result rows. Use CSV or Excel for the full result.", styles["Italic"]),
        ])
    doc.build(story)
    return buffer.getvalue()
def get_smtp_settings():
    """Read Gmail SMTP settings from environment variables or Streamlit secrets."""
    def setting(name, default=""):
        env_value = os.getenv(name)
        if env_value is not None and env_value.strip():
            return env_value.strip()
        try:
            secret_value = st.secrets.get(name, default)
            if secret_value is not None:
                return str(secret_value).strip()
        except Exception:
            # Streamlit secrets may not be configured; environment variables still work.
            pass
        return str(default).strip()
    smtp_host = setting("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(setting("SMTP_PORT", "587"))
    smtp_user = setting("SMTP_USER")
    smtp_password = setting("SMTP_PASSWORD")
    sender_email = setting("SENDER_EMAIL", smtp_user)
    if not all([smtp_host, smtp_user, smtp_password, sender_email]):
        raise ValueError(
            "Gmail email is not configured. Add SMTP_USER and SMTP_PASSWORD "
            "to .streamlit/secrets.toml or set them as environment variables."
        )
    return smtp_host, smtp_port, smtp_user, smtp_password, sender_email
def send_report_email(recipient, question, dataset_name, file_title, csv_data, excel_data, pdf_data):
    smtp_host, smtp_port, smtp_user, smtp_password, sender_email = get_smtp_settings()
    message = EmailMessage()
    message["Subject"] = f"NexaData AI Report: {file_title}"
    message["From"] = sender_email
    message["To"] = recipient
    message.set_content(
        "Hello,\n\nPlease find the NexaData AI report attached.\n\n"
        f"Dataset: {dataset_name}\nQuestion: {question}\n\n"
        "Attached files: CSV, Excel, and PDF."
    )
    message.add_attachment(csv_data, maintype="text", subtype="csv", filename=f"{file_title}.csv")
    message.add_attachment(
        excel_data, maintype="application",
        subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"{file_title}.xlsx",
    )
    message.add_attachment(pdf_data, maintype="application", subtype="pdf", filename=f"{file_title}.pdf")
    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(message)
def history_session_id():
    """Stable history namespace. Configure a unique ID per authenticated user when deployed."""
    return (os.getenv("NEXADATA_HISTORY_SESSION_ID") or "local-workspace").strip()


def get_saved_postgres_config():
    """Load PostgreSQL settings from environment variables or Streamlit secrets.

    This lets the app reconnect after a browser refresh, when Streamlit session state
    and the password entered into the connection form are no longer available.
    """
    def setting(env_name, secret_name, default=""):
        value = os.getenv(env_name)
        if value and value.strip():
            return value.strip()
        try:
            value = st.secrets.get(secret_name, default)
            return str(value).strip() if value is not None else str(default).strip()
        except Exception:
            return str(default).strip()

    host = setting("NEXADATA_PG_HOST", "POSTGRES_HOST", "")
    database = setting("NEXADATA_PG_DATABASE", "POSTGRES_DB", "nexadata_db")
    user = setting("NEXADATA_PG_USER", "POSTGRES_USER", "")
    password = setting("NEXADATA_PG_PASSWORD", "POSTGRES_PASSWORD", "")
    port = setting("NEXADATA_PG_PORT", "POSTGRES_PORT", "5432")
    if not all([host, database, user, password]):
        return None
    try:
        port = int(port)
    except (TypeError, ValueError):
        port = 5432
    return {
        "host": host,
        "port": port,
        "dbname": database,
        "user": user,
        "password": password,
        "connect_timeout": 5,
    }


def ensure_history_table(config):
    """Create or safely upgrade persistent history storage without deleting saved rows."""
    with psycopg.connect(**config) as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE SCHEMA IF NOT EXISTS app")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS app.chat_history (
                    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    session_id VARCHAR(100) NOT NULL DEFAULT 'local-workspace',
                    mode VARCHAR(50) NOT NULL DEFAULT 'General Questions',
                    question TEXT NOT NULL DEFAULT '',
                    answer TEXT NOT NULL DEFAULT '',
                    answer_text TEXT NOT NULL DEFAULT '',
                    dataset_name TEXT,
                    generated_code TEXT,
                    result_json JSONB,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )

            # Upgrade older versions of the table in place. These statements
            # preserve all existing rows and are safe to run on every startup.
            cur.execute(
                "ALTER TABLE app.chat_history "
                "ADD COLUMN IF NOT EXISTS session_id VARCHAR(100) NOT NULL DEFAULT 'local-workspace'"
            )
            cur.execute(
                "ALTER TABLE app.chat_history "
                "ADD COLUMN IF NOT EXISTS mode VARCHAR(50) NOT NULL DEFAULT 'General Questions'"
            )
            cur.execute(
                "ALTER TABLE app.chat_history "
                "ADD COLUMN IF NOT EXISTS question TEXT NOT NULL DEFAULT ''"
            )
            # Keep both legacy `answer` and newer `answer_text` columns because
            # existing installations may have a NOT NULL constraint on `answer`.
            cur.execute(
                "ALTER TABLE app.chat_history "
                "ADD COLUMN IF NOT EXISTS answer TEXT NOT NULL DEFAULT ''"
            )
            cur.execute(
                "ALTER TABLE app.chat_history "
                "ADD COLUMN IF NOT EXISTS answer_text TEXT NOT NULL DEFAULT ''"
            )
            cur.execute(
                "ALTER TABLE app.chat_history "
                "ADD COLUMN IF NOT EXISTS dataset_name TEXT"
            )
            cur.execute(
                "ALTER TABLE app.chat_history "
                "ADD COLUMN IF NOT EXISTS generated_code TEXT"
            )
            cur.execute(
                "ALTER TABLE app.chat_history "
                "ADD COLUMN IF NOT EXISTS result_json JSONB"
            )
            cur.execute(
                "ALTER TABLE app.chat_history "
                "ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
            )

            # Older versions stored the response in a column named "answer".
            # Copy it into answer_text only where the new field is blank.
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = 'app'
                      AND table_name = 'chat_history'
                      AND column_name = 'answer'
                )
                """
            )
            has_legacy_answer = cur.fetchone()[0]
            if has_legacy_answer:
                cur.execute(
                    """
                    UPDATE app.chat_history
                    SET answer_text = COALESCE(NULLIF(answer_text, ''), answer, ''),
                        answer = COALESCE(NULLIF(answer, ''), answer_text, '')
                    WHERE answer_text IS NULL OR answer_text = ''
                       OR answer IS NULL OR answer = ''
                    """
                )

            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_chat_history_session_created
                ON app.chat_history (session_id, created_at DESC)
                """
            )

def result_to_history_json(result):
    """Serialize tabular results so they can be restored from history."""
    if isinstance(result, pd.DataFrame):
        frame = result.astype(object).where(pd.notna(result), None)
        return {"kind": "dataframe", "columns": [str(c) for c in frame.columns],
                "rows": frame.values.tolist()}
    if isinstance(result, pd.Series):
        frame = result.rename(result.name or "Value").reset_index()
        frame = frame.astype(object).where(pd.notna(frame), None)
        return {"kind": "dataframe", "columns": [str(c) for c in frame.columns],
                "rows": frame.values.tolist()}
    if result is None:
        return None
    return {"kind": "text", "value": str(result)}


def restore_history_result(payload):
    if not payload:
        return None
    if payload.get("kind") == "dataframe":
        return pd.DataFrame(payload.get("rows", []), columns=payload.get("columns", []))
    return payload.get("value")


def save_history_item(config, item):
    if not config:
        return
    ensure_history_table(config)
    answer = item.get("answer")
    answer_text = answer if isinstance(answer, str) else "Data result"
    result_payload = result_to_history_json(item.get("result"))
    with psycopg.connect(**config) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO app.chat_history
                    (session_id, mode, question, answer, answer_text, dataset_name,
                     generated_code, result_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    history_session_id(), item.get("mode", "General Questions"),
                    item.get("question", ""), answer_text or "", answer_text or "",
                    item.get("dataset"), item.get("code", ""),
                    json.dumps(result_payload, default=str) if result_payload is not None else None,
                ),
            )


def load_history_from_postgres(config, limit=50):
    if not config:
        return []
    ensure_history_table(config)
    with psycopg.connect(**config) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, mode, question, answer_text, dataset_name,
                       generated_code, result_json, created_at
                FROM app.chat_history
                WHERE session_id = %s
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (history_session_id(), limit),
            )
            rows = cur.fetchall()
    return [{
        "id": row[0], "mode": row[1], "question": row[2],
        "answer": row[3] if row[1] == "General Questions" else "Data result",
        "dataset": row[4], "code": row[5] or "",
        "result": restore_history_result(row[6]), "created_at": row[7],
    } for row in rows]


def delete_history_from_postgres(config):
    if not config:
        return
    ensure_history_table(config)
    with psycopg.connect(**config) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM app.chat_history WHERE session_id = %s",
                (history_session_id(),),
            )


def add_history(mode, question, answer, dataset_name=None, code="", result=None):
    """Add to in-memory history and persist to PostgreSQL when connected."""
    if "history" not in st.session_state:
        st.session_state.history = []
    item = {
        "mode": mode, "question": question,
        "answer": answer if isinstance(answer, str) else "Data result",
        "dataset": dataset_name, "code": code or "", "result": result,
    }
    config = st.session_state.get("postgres_config")
    if config:
        save_history_item(config, item)
    st.session_state.history.insert(0, item)
    st.session_state.history = st.session_state.history[:50]


# ------------------------------ Sidebar ---------------------------
if "history" not in st.session_state:
    st.session_state.history = []
if "current" not in st.session_state:
    st.session_state.current = None
for key, default in {
    "show_full_result": False,
    "show_download_options": False,
    "show_email_form": False,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default
# Reconnect from environment/secrets on a fresh browser session. Without this,
# the connection form's credentials live only in session_state and disappear on refresh.
if not st.session_state.get("postgres_config"):
    st.session_state.postgres_config = get_saved_postgres_config()

# Load saved history from PostgreSQL whenever a connection is available.
if st.session_state.get("postgres_config"):
    try:
        # PostgreSQL is the source of truth for persisted history. Deduplicate
        # legacy duplicate rows for display only; do not delete database records.
        db_history = load_history_from_postgres(
            st.session_state.postgres_config, limit=100
        )

        def history_signature(item):
            return (
                str(item.get("mode", "General Questions")).strip().casefold(),
                re.sub(r"\\s+", " ", str(item.get("question", "")).strip()).casefold(),
                re.sub(r"\\s+", " ", str(item.get("code", "")).strip()).casefold(),
                str(item.get("dataset") or "").strip().casefold(),
            )

        def close_in_time(left, right):
            left_time = left.get("created_at")
            right_time = right.get("created_at")
            if left_time is None or right_time is None:
                return False
            try:
                return abs((left_time - right_time).total_seconds()) <= 120
            except Exception:
                return str(left_time) == str(right_time)

        merged_history = []
        # Process newest database records first, suppressing same-signature
        # records created within two minutes of one another.
        for item in db_history:
            signature = history_signature(item)
            if any(
                history_signature(previous) == signature
                and close_in_time(previous, item)
                for previous in merged_history
            ):
                continue
            merged_history.append(item)

        # Keep only unsaved in-memory items (e.g. when PostgreSQL saving failed).
        # If a matching persisted record exists, don't show it twice.
        for item in st.session_state.get("history", []):
            if item.get("id") is not None:
                continue
            signature = history_signature(item)
            if any(history_signature(saved) == signature for saved in merged_history):
                continue
            merged_history.append(item)

        st.session_state.history = merged_history[:50]
        st.session_state.pop("history_load_error", None)
    except Exception as exc:
        # Include connection identity so a stale/different PostgreSQL instance
        # can be identified from the UI instead of asking for repeated checks.
        diagnostic = ""
        try:
            with psycopg.connect(**st.session_state.postgres_config) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT current_database(), current_user, "
                        "inet_server_addr()::text, inet_server_port()"
                    )
                    db_name, db_user, db_host, db_port = cur.fetchone()
                    cur.execute(
                        """
                        SELECT string_agg(column_name, ', ' ORDER BY ordinal_position)
                        FROM information_schema.columns
                        WHERE table_schema = 'app' AND table_name = 'chat_history'
                        """
                    )
                    columns = cur.fetchone()[0] or "(table not found)"
                    diagnostic = (
                        f" Connected to database={db_name}, user={db_user}, "
                        f"server={db_host}:{db_port}. Columns found: {columns}."
                    )
        except Exception as diagnostic_exc:
            diagnostic = f" Could not inspect the connected database: {diagnostic_exc}"
        st.session_state.history_load_error = f"{exc}.{diagnostic}"

with st.sidebar:
    st.markdown('<div class="dm-brand">🧠 NexaData AI</div>', unsafe_allow_html=True)
    st.markdown('<div class="dm-tagline">Ask. Analyze. Discover.</div>', unsafe_allow_html=True)
    st.divider()
    st.markdown("### Question History")
    st.caption("History is saved in PostgreSQL when connected.")
    if st.session_state.get("history_load_error"):
        st.warning("Could not reload saved history from PostgreSQL: " + str(st.session_state.history_load_error))
    if st.session_state.get("history_save_error"):
        st.warning("A recent answer could not be saved to PostgreSQL: " + str(st.session_state.history_save_error))
    if not st.session_state.get("postgres_config"):
        st.info("To keep history after refreshing, configure PostgreSQL credentials in .streamlit/secrets.toml or environment variables, then restart the app.")
    if st.button("＋ New question", width="stretch"):
        st.session_state.current = None
        st.session_state.question_input = ""
        st.session_state.show_full_result = False
        st.session_state.show_download_options = False
        st.session_state.show_email_form = False
        st.rerun()
    if st.session_state.history:
        for i, item in enumerate(st.session_state.history):
            question_text = str(item.get("question", ""))
            label = question_text.strip()
            label = label if len(label) <= 42 else label[:39] + "..."
            with st.expander(f"{'◉' if item.get('mode') == 'Data-Specific Questions' else '○'} {label}", expanded=False):
                st.caption(f"Mode: {item.get('mode', 'Question')}" + (f" · {item.get('created_at').strftime('%Y-%m-%d %H:%M')}" if item.get('created_at') and hasattr(item.get('created_at'), 'strftime') else ""))
                st.markdown("**Question — use the copy icon to copy**")
                st.code(question_text or "(No question text)", language=None)
                saved_result = item.get("result")
                saved_answer = item.get("answer", "")
                st.markdown("**Saved answer — use the copy icon for text**")
                if isinstance(saved_result, (pd.DataFrame, pd.Series)):
                    st.dataframe(result_to_df(saved_result).head(100), width="stretch", hide_index=True)
                    try:
                        answer_for_copy = result_to_df(saved_result).to_csv(index=False)
                    except Exception:
                        answer_for_copy = str(saved_result)
                    st.code(answer_for_copy or "(Empty result)", language="text")
                elif saved_result is not None:
                    answer_for_copy = str(saved_result)
                    st.code(answer_for_copy, language="text")
                else:
                    answer_for_copy = str(saved_answer or "(No saved answer)")
                    st.code(answer_for_copy, language="text")
                if item.get("code"):
                    st.markdown("**Generated SQL / code — use the copy icon**")
                    st.code(str(item.get("code")), language="sql")
                if st.button("Open this conversation", key=f"history_{i}", width="stretch"):
                    st.session_state.current = {
                        "mode": item.get("mode", "General Questions"),
                        "question": question_text,
                        "answer": saved_answer,
                        "dataset": item.get("dataset"),
                        "code": item.get("code", ""),
                        "result": saved_result,
                    }
                    st.session_state.show_full_result = False
                    st.session_state.show_download_options = False
                    st.session_state.show_email_form = False
                    st.rerun()
    else:
        st.caption("Your questions will appear here.")
    if st.button("Clear History", width="stretch"):
        try:
            if st.session_state.get("postgres_config"):
                delete_history_from_postgres(st.session_state.postgres_config)
            st.session_state.history = []
            st.session_state.current = None
            st.rerun()
        except Exception as exc:
            st.error(f"Could not clear PostgreSQL history: {exc}")
    st.divider()
    st.caption("NexaData AI · Ask. Analyze. Discover.")
# ------------------------------ Header ----------------------------
st.markdown(
    '<div class="dm-hero"><h2>Ask. Analyze. Discover.</h2>'
    '<p>Your workspace for general questions and data-specific insights.</p></div>',
    unsafe_allow_html=True,
)
# ------------------------------ Data loading ----------------------
# Both experiences use matching top-level tabs. Data-specific questions support
# uploaded CSV/Excel files (DuckDB SQL) or PostgreSQL (PostgreSQL SQL).
general_tab, data_tab = st.tabs(["💬 General Questions", "📊 Data-Specific Questions"])
df = None
dataset_name = "No dataset"
source_mode = None
mode = None
question = ""
ask_clicked = False
if "postgres_config" not in st.session_state:
    st.session_state.postgres_config = None
if "postgres_tables" not in st.session_state:
    st.session_state.postgres_tables = []

with general_tab:
    st.caption("Ask about concepts, coding, SQL, Python, data engineering, or other general topics.")
    with st.form("general_ask_form", clear_on_submit=False):
        general_question = st.text_input(
            "Your question",
            placeholder="Example: Explain incremental loading in ETL.",
            key="general_question_input",
        )
        general_ask_clicked = st.form_submit_button(
            "✨ Ask NexaData AI", type="primary", width="stretch"
        )
    if general_ask_clicked:
        question = general_question
        data_intent_terms = (
            "show ", "list ", "total ", "count ", "sum ", "average ", "avg ",
            "sales", "revenue", "payment", "invoice", "expense", "budget",
            "refund", "customer", "branch", "product", "inventory", "stock",
            "shipment", "delivery", "order", "database", "table", "schema",
            "by month", "monthly", "by state", "top ", "highest", "lowest",
        )
        normalized_question = (general_question or "").strip().lower()
        looks_like_data_question = any(term in normalized_question for term in data_intent_terms)
        if (
            looks_like_data_question
            and st.session_state.get("dataset_source_mode") == "PostgreSQL"
            and st.session_state.postgres_config
        ):
            mode = "Data-Specific Questions"
        else:
            mode = "General Questions"
        ask_clicked = True

with data_tab:
    st.caption("Ask questions about an uploaded file or your connected PostgreSQL database.")
    source_mode = st.radio(
        "Data source",
        ["Upload File", "PostgreSQL"],
        horizontal=True,
        key="dataset_source_mode",
    )
    df = None
    dataset_name = "No dataset"

    if source_mode == "Upload File":
        uploaded_file = st.file_uploader(
            "Upload a CSV or Excel file", type=["csv", "xlsx", "xls"],
            key="manual_dataset_upload",
        )
        if uploaded_file is not None:
            try:
                df = read_dataset(uploaded_file.name, uploaded_file.getvalue())
                dataset_name = uploaded_file.name
                if df.empty:
                    st.warning("The selected file is empty.")
                else:
                    st.success(f"File ready: {uploaded_file.name}")
            except Exception as exc:
                st.error(f"Could not read the uploaded file: {exc}")
    else:
        # PostgreSQL connection details are loaded from .streamlit/secrets.toml
        # or environment variables. No database password is shown in the UI.
        saved_config = get_saved_postgres_config()
        if saved_config:
            st.session_state.postgres_config = saved_config
            try:
                with psycopg.connect(**saved_config) as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT current_database(), current_user")
                        connected_db, connected_user = cur.fetchone()
                dataset_name = f"PostgreSQL: {connected_db}"
                st.success(f"Connected to PostgreSQL database `{connected_db}` as `{connected_user}`.")
            except Exception as exc:
                st.session_state.postgres_config = None
                st.error(f"PostgreSQL connection failed. Check your private secrets/environment settings. Details: {exc}")
        else:
            st.session_state.postgres_config = None
            st.error(
                "PostgreSQL credentials are not configured. Add POSTGRES_HOST, POSTGRES_DB, "
                "POSTGRES_USER, POSTGRES_PASSWORD, and POSTGRES_PORT to "
                r"C:\AI_DATA_SOLUTION\.streamlit\secrets.toml, then restart the app."
            )

    # Query area stays at the bottom of the Data-Specific Questions tab,
    # matching the simple question-and-submit pattern in General Questions.
    st.divider()
    st.markdown("### Ask a data-specific question")
    with st.form("data_ask_form", clear_on_submit=False):
        data_question = st.text_input(
            "Your question",
            placeholder="Example: Which 10 customers made the highest total payments?",
            key="data_question_input",
        )
        data_ask_clicked = st.form_submit_button(
            "✨ Ask NexaData AI", type="primary", width="stretch"
        )
    if data_ask_clicked:
        mode = "Data-Specific Questions"
        question = data_question
        ask_clicked = True
if ask_clicked:
    if not question.strip():
        st.warning("Please enter a question.")
    else:
        try:
            with st.spinner("Generating and executing your query..."):
                if mode == "General Questions":
                    answer = ask_general(question.strip())
                    current = {
                        "mode": mode, "question": question.strip(),
                        "answer": answer, "dataset": None, "code": "", "result": None,
                    }
                else:
                    # Use PostgreSQL SQL when PostgreSQL is selected; otherwise
                    # generate and execute DuckDB SQL against the loaded CSV/Excel data.
                    # Prefer PostgreSQL only when it is selected AND connected.
                    # If a CSV/Excel DataFrame is loaded but the PostgreSQL radio
                    # state is stale or disconnected, analyze the loaded file instead
                    # of failing with a PostgreSQL connection message.
                    postgres_is_ready = (
                        source_mode == "PostgreSQL"
                        and bool(st.session_state.get("postgres_config"))
                    )
                    if postgres_is_ready:
                        generated_code = ask_postgres_sql(
                            question.strip(), st.session_state.postgres_config
                        )
                        result = execute_postgres_query(
                            generated_code, st.session_state.postgres_config
                        )
                        active_dataset_name = dataset_name
                    elif df is not None and not df.empty:
                        generated_code = ask_local_sql(question.strip(), df)
                        result = execute_local_sql(generated_code, df)
                        active_dataset_name = dataset_name
                    elif source_mode == "PostgreSQL":
                        raise ValueError(
                            "PostgreSQL is not connected. Configure the credentials in "
                            ".streamlit/secrets.toml or environment variables and retry."
                        )
                    else:
                        raise ValueError("Upload a CSV/Excel file or configure PostgreSQL before asking a data question.")
                    current = {
                        "mode": mode, "question": question.strip(),
                        "answer": result, "dataset": active_dataset_name,
                        "code": generated_code, "result": result,
                    }
                st.session_state.current = current
                st.session_state.show_full_result = False
                st.session_state.show_download_options = False
                st.session_state.show_email_form = False
                history_item = {
                    "mode": current["mode"],
                    "question": current["question"],
                    "answer": current["answer"] if mode == "General Questions" else "Data result",
                    "dataset": current.get("dataset"),
                    "code": current.get("code", ""),
                    "result": current.get("result"),
                }
                config = st.session_state.get("postgres_config")
                if config:
                    try:
                        save_history_item(config, history_item)
                        st.session_state.pop("history_save_error", None)
                    except Exception as exc:
                        st.session_state.history_save_error = str(exc)
                        st.warning(f"Answer generated, but PostgreSQL history could not be saved: {exc}")
                st.session_state.history.insert(0, history_item)
                st.session_state.history = st.session_state.history[:50]
            st.rerun()
        except Exception as exc:
            st.error(f"Could not process the question: {exc}")
# ------------------------------ Result ----------------------------
current = st.session_state.current
if current is not None:
    result_tab = data_tab if current.get("mode") == "Data-Specific Questions" else general_tab
    with result_tab:
        st.divider()
        # Scroll the page to the latest answer after a query finishes so the
        # user does not have to manually scroll down to find the result.
        st.markdown('<div id="nexadata-latest-result"></div>', unsafe_allow_html=True)
        components.html(
            """<script>
            const scrollToLatestResult = () => {
              try {
                const doc = window.parent.document;
                const target = doc.getElementById('nexadata-latest-result');
                if (target) target.scrollIntoView({behavior: 'smooth', block: 'start'});
              } catch (e) {}
            };
            setTimeout(scrollToLatestResult, 250);
            setTimeout(scrollToLatestResult, 800);
            </script>""",
            height=0,
        )
        st.markdown("### Your question")
        st.write(current["question"])
        st.markdown("### NexaData AI answer")
        is_data_result = current["mode"] == "Data-Specific Questions"
        result = current.get("result")
        display_result = result_to_df(result) if is_data_result and result is not None else None
        if is_data_result:
            if isinstance(result, (pd.DataFrame, pd.Series)):
                st.dataframe(display_result.head(500), width="stretch", hide_index=True)
                if len(display_result) > 500:
                    st.caption("Showing the first 500 rows here. Use View or Download for the complete result.")
                # Keep the visualization independent of the table's column menu.
                # Chart controls are based on the saved result, so changing a table
                # column or choosing a chart option will not discard the chart.
                st.markdown("### 📊 Visualization")
                chart_df = display_result.copy()

                # SQL drivers sometimes return numeric values as object/string dtype.
                # Detect columns that are genuinely numeric after safe conversion.
                numeric_cols = []
                for column in chart_df.columns:
                    converted = pd.to_numeric(chart_df[column], errors="coerce")
                    if converted.notna().sum() > 0:
                        chart_df[column] = converted
                        numeric_cols.append(column)

                category_cols = [c for c in chart_df.columns if c not in numeric_cols]

                if len(chart_df) >= 2 and numeric_cols:
                    chart_col1, chart_col2, chart_col3 = st.columns([1, 1, 1])
                    with chart_col1:
                        chart_type = st.selectbox(
                            "Chart type",
                            ["Bar chart", "Line chart", "Area chart"],
                            key="nexa_chart_type",
                        )
                    with chart_col2:
                        x_options = category_cols if category_cols else ["Row number"]
                        x_col = st.selectbox(
                            "Category / X-axis",
                            x_options,
                            key="nexa_chart_x",
                        )
                    with chart_col3:
                        y_col = st.selectbox(
                            "Value / Y-axis",
                            numeric_cols,
                            key="nexa_chart_y",
                        )

                    if x_col == "Row number":
                        plot_df = pd.DataFrame({
                            "Row number": range(1, len(chart_df) + 1),
                            y_col: chart_df[y_col].values,
                        })
                    else:
                        plot_df = chart_df[[x_col, y_col]].copy()
                        plot_df[x_col] = plot_df[x_col].astype(str)
                        plot_df = plot_df.dropna(subset=[y_col]).head(100)

                    if not plot_df.empty:
                        # Use explicit x/y arguments; do not set the category as
                        # the dataframe index. This keeps the chart easier to restore.
                        if chart_type == "Bar chart":
                            st.bar_chart(plot_df, x=x_col, y=y_col, width="stretch")
                        elif chart_type == "Line chart":
                            st.line_chart(plot_df, x=x_col, y=y_col, width="stretch")
                        else:
                            st.area_chart(plot_df, x=x_col, y=y_col, width="stretch")
                        st.caption(
                            f"{chart_type}: {y_col} by {x_col}. "
                            "Use the Chart type selector to switch back to Bar chart."
                        )
                    else:
                        st.info("There are no numeric values available to plot.")
                else:
                    st.info(
                        "This result does not contain enough numeric data for a chart. "
                        "Try a query that returns a category and a numeric value, "
                        "such as total sales by branch."
                    )

            else:
                st.success(str(result))
        else:
            st.markdown(current["answer"])
        st.divider()
        action_cols = st.columns(3)
        with action_cols[0]:
            if st.button("📧 Email", key="action_email", width="stretch"):
                st.session_state.show_email_form = not st.session_state.show_email_form
                st.session_state.show_full_result = False
                st.session_state.show_download_options = False
        with action_cols[1]:
            if st.button("👁️ View", key="action_view", width="stretch"):
                st.session_state.show_full_result = not st.session_state.show_full_result
                st.session_state.show_email_form = False
                st.session_state.show_download_options = False
        with action_cols[2]:
            if st.button("⬇️ Download", key="action_download", width="stretch"):
                st.session_state.show_download_options = not st.session_state.show_download_options
                st.session_state.show_email_form = False
                st.session_state.show_full_result = False
        if st.session_state.show_full_result:
            st.markdown("### Full result")
            if is_data_result:
                st.dataframe(display_result, width="stretch", height=450, hide_index=True)
            else:
                st.markdown(current["answer"])
        file_title = safe_filename(current["question"])
        if st.session_state.show_download_options:
            st.markdown("### Download report")
            if is_data_result:
                csv_data = display_result.to_csv(index=False).encode("utf-8-sig")
                excel_data = generate_excel(result)
                pdf_data = generate_pdf(current["question"], current.get("dataset"), result)
                dl1, dl2, dl3 = st.columns(3)
                with dl1:
                    st.download_button("Download CSV", csv_data, f"{file_title}.csv", "text/csv", width="stretch")
                with dl2:
                    st.download_button(
                        "Download Excel", excel_data, f"{file_title}.xlsx",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        width="stretch",
                    )
                with dl3:
                    st.download_button("Download PDF", pdf_data, f"{file_title}.pdf", "application/pdf", width="stretch")
            else:
                text_data = current["answer"].encode("utf-8")
                st.download_button(
                    "Download TXT", text_data, f"{file_title}.txt", "text/plain",
                    width="stretch",
                )
        if st.session_state.show_email_form:
            st.markdown("### Email answer")
            recipient = st.text_input("Recipient email address", placeholder="recipient@example.com", key="recipient_email")
            if st.button("Send email", type="primary", key="send_email"):
                if not re.fullmatch(r"[^@\s]+@[^@\s]+\\.[^@\s]+", recipient.strip()):
                    st.error("Please enter a valid email address.")
                else:
                    try:
                        if is_data_result:
                            csv_data = display_result.to_csv(index=False).encode("utf-8-sig")
                            excel_data = generate_excel(result)
                            pdf_data = generate_pdf(current["question"], current.get("dataset"), result)
                            send_report_email(
                                recipient.strip(), current["question"], current.get("dataset"),
                                file_title, csv_data, excel_data, pdf_data,
                            )
                        else:
                            # General answers are emailed as a simple text attachment.
                            smtp_host, smtp_port, smtp_user, smtp_password, sender_email = get_smtp_settings()
                            message = EmailMessage()
                            message["Subject"] = f"NexaData AI Answer: {file_title}"
                            message["From"] = sender_email
                            message["To"] = recipient.strip()
                            message.set_content(f"Question: {current['question']}\n\nAnswer:\n{current['answer']}")
                            with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
                                server.starttls()
                                server.login(smtp_user, smtp_password)
                                server.send_message(message)
                        st.success(f"Email sent to {recipient.strip()}.")
                    except Exception as exc:
                        st.error(f"Could not send email. Check your SMTP settings. Details: {exc}")
        # Keep generated SQL at the very end of the result page, after tables,
        # full-result view, downloads, and email actions.
        if is_data_result and current.get("code"):
            st.divider()
            with st.expander("Generated SQL query", expanded=False):
                st.code(current["code"], language="sql")
    st.caption("NexaData AI · Ask. Analyze. Discover.")