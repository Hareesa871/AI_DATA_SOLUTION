# ============================================================
# DATAMIND AI
# Ask. Analyze. Discover.
# General Questions + Data Questions + Email / View / Download
# ============================================================

import ast
import html
import io
import os
import re
import smtplib
from email.message import EmailMessage
from pathlib import Path

import pandas as pd
import streamlit as st
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
    page_title="DataMind AI",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

DATA_FOLDER = Path(r"C:\AI_DATA_SOLUTION")
API_KEY = ""  # Or set OPENAI_API_KEY as a Windows environment variable.
MODEL_NAME = "gpt-5.6-luna"

api_key = (os.getenv("OPENAI_API_KEY") or API_KEY).strip()
client = OpenAI(api_key=api_key) if api_key else None

# ------------------------------ Styling ---------------------------
st.markdown(
    """
    <style>
    :root { --dm-ink:#172554; --dm-blue:#3156d8; --dm-pale:#eef2ff; }
    .block-container { padding-top: 1.5rem; padding-bottom: 2.5rem; max-width: 1450px; }
    [data-testid="stSidebar"] { border-right: 1px solid #e5e7eb; }
    .dm-brand { font-size: 1.7rem; font-weight: 800; letter-spacing: -.04em; color: var(--dm-ink); }
    .dm-tagline { color: #64748b; font-size: .94rem; margin-top: -.15rem; }
    .dm-hero { padding: 1.25rem 1.4rem; border-radius: 18px; background: linear-gradient(120deg,#eef2ff,#f8fafc); border: 1px solid #e0e7ff; margin-bottom: 1.2rem; }
    .dm-hero h2 { margin: 0; color: #172554; font-size: 1.55rem; }
    .dm-hero p { color: #475569; margin: .35rem 0 0 0; }
    .dm-card { padding: 1rem 1.15rem; border: 1px solid #e2e8f0; border-radius: 14px; background: rgba(248,250,252,.7); }
    div.stButton > button { border-radius: 10px; }
    </style>
    """,
    unsafe_allow_html=True,
)

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
            "You are DataMind AI, a clear and helpful assistant. "
            "Answer the user's general question accurately and practically. "
            "Use headings or short bullet points when useful. Do not claim "
            "to have inspected the user's dataset unless the question asks "
            "about data and dataset context is provided.\n\n"
            f"User question: {question}"
        ),
        max_output_tokens=900,
    )
    return response.output_text.strip()


def ask_dataframe(question, frame):
    metadata = {
        "rows": len(frame),
        "columns": list(map(str, frame.columns)),
        "dtypes": frame.dtypes.astype(str).to_dict(),
    }
    prompt = f"""
You are an expert Python Pandas data analyst working with a DataFrame named df.

Dataset metadata:
{metadata}

User question:
{question}

Return exactly ONE Python expression that answers the question using df.
Rules:
- Use only columns that exist in the dataset.
- Do not create sample data, import modules, read/write files, or modify df.
- Do not use assignments, loops, comprehensions, lambda, eval, exec, open,
  private attributes, or markdown.
- Return only one expression. Use pandas operations where appropriate.
"""
    response = require_client().responses.create(
        model=MODEL_NAME,
        input=prompt,
        max_output_tokens=500,
    )
    return clean_code(response.output_text)


def clean_code(code):
    code = code.strip()
    code = re.sub(r"^```(?:python)?\s*", "", code)
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
    if isinstance(result, pd.DataFrame):
        output = result.copy()
        if output.index.name is not None or isinstance(output.index, pd.MultiIndex):
            output = output.reset_index()
        return output
    if isinstance(result, pd.Series):
        return result.rename("Value").reset_index()
    return pd.DataFrame({"Answer": [result]})


def execute_query(code, frame):
    validate_code(code)
    working_df = frame.copy()
    return eval(
        compile(ast.parse(code, mode="eval"), "<datamind-query>", "eval"),
        {"__builtins__": {}},
        {"df": working_df, "pd": pd},
    )


def safe_filename(question):
    name = re.sub(r"[^a-zA-Z0-9_-]+", "_", question.lower()).strip("_")
    return (name or "datamind_result")[:70]


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
        Paragraph("DataMind AI Report", styles["Title"]),
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


def send_report_email(recipient, question, dataset_name, file_title, csv_data, excel_data, pdf_data):
    smtp_host = os.getenv("SMTP_HOST", "").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "").strip()
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    sender_email = os.getenv("SENDER_EMAIL", smtp_user).strip()
    if not all([smtp_host, smtp_user, smtp_password, sender_email]):
        raise ValueError(
            "Email is not configured. Set SMTP_HOST, SMTP_PORT, SMTP_USER, "
            "SMTP_PASSWORD, and SENDER_EMAIL as environment variables."
        )
    message = EmailMessage()
    message["Subject"] = f"DataMind AI Report: {file_title}"
    message["From"] = sender_email
    message["To"] = recipient
    message.set_content(
        "Hello,\n\nPlease find the DataMind AI report attached.\n\n"
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


def add_history(mode, question, answer, dataset_name=None):
    if "history" not in st.session_state:
        st.session_state.history = []
    st.session_state.history.insert(0, {
        "mode": mode,
        "question": question,
        "answer": answer,
        "dataset": dataset_name,
    })
    st.session_state.history = st.session_state.history[:30]


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

with st.sidebar:
    st.markdown('<div class="dm-brand">🧠 DataMind AI</div>', unsafe_allow_html=True)
    st.markdown('<div class="dm-tagline">Ask. Analyze. Discover.</div>', unsafe_allow_html=True)
    st.divider()
    st.markdown("### Question History")
    if st.button("＋ New question", use_container_width=True):
        st.session_state.current = None
        st.session_state.question_input = ""
        st.session_state.show_full_result = False
        st.session_state.show_download_options = False
        st.session_state.show_email_form = False
        st.rerun()
    if st.session_state.history:
        for i, item in enumerate(st.session_state.history):
            label = item["question"].strip()
            label = label if len(label) <= 42 else label[:39] + "..."
            if st.button(f"{'◉' if item['mode'] == 'Data-Specific Questions' else '○'} {label}",
                         key=f"history_{i}", use_container_width=True):
                st.session_state.current = {
                    "mode": item["mode"],
                    "question": item["question"],
                    "answer": item["answer"],
                    "dataset": item.get("dataset"),
                    "code": item.get("code", ""),
                    "result": item.get("result"),
                }
                st.session_state.show_full_result = False
                st.session_state.show_download_options = False
                st.session_state.show_email_form = False
                st.rerun()
    else:
        st.caption("Your questions will appear here.")
    if st.button("Clear History", use_container_width=True):
        st.session_state.history = []
        st.rerun()
    st.divider()
    st.caption("DataMind AI · Ask. Analyze. Discover.")

# ------------------------------ Header ----------------------------
st.markdown(
    '<div class="dm-hero"><h2>Ask. Analyze. Discover.</h2>'
    '<p>Your workspace for general questions and data-specific insights.</p></div>',
    unsafe_allow_html=True,
)

# ------------------------------ Data loading ----------------------
source_mode = st.radio(
    "Data source",
    ["Automatic Folder Loading", "Upload File"],
    horizontal=True,
    key="dataset_source_mode",
)
df = None
dataset_name = "No dataset"

if source_mode == "Automatic Folder Loading":
    supported_extensions = {".csv", ".xlsx", ".xls"}
    available_files = sorted(
        [p for p in DATA_FOLDER.iterdir()
         if p.is_file() and p.suffix.lower() in supported_extensions],
        key=lambda p: p.name.lower(),
    ) if DATA_FOLDER.exists() else []
    if available_files:
        default_path = DATA_FOLDER / "datainfo.csv"
        default_index = available_files.index(default_path) if default_path in available_files else 0
        selected_file = st.selectbox(
            "Select a file from C:\\AI_DATA_SOLUTION",
            available_files,
            index=default_index,
            format_func=lambda p: p.name,
            key="automatic_dataset_file",
        )
        try:
            df = read_dataset(str(selected_file))
            dataset_name = selected_file.name
        except Exception as exc:
            st.error(f"Could not read the selected file: {exc}")
    else:
        st.info(f"No CSV or Excel files were found in `{DATA_FOLDER}`. You can switch to Upload File.")
else:
    uploaded_file = st.file_uploader(
        "Upload a CSV or Excel file", type=["csv", "xlsx", "xls"],
        key="manual_dataset_upload",
    )
    if uploaded_file is not None:
        try:
            df = read_dataset(uploaded_file.name, uploaded_file.getvalue())
            dataset_name = uploaded_file.name
        except Exception as exc:
            st.error(f"Could not read the uploaded file: {exc}")

if df is not None and df.empty:
    st.warning("The selected dataset is empty.")
if df is not None and not df.empty:
    metric1, metric2, metric3 = st.columns(3)
    metric1.metric("Rows", f"{len(df):,}")
    metric2.metric("Columns", f"{len(df.columns):,}")
    metric3.metric("Dataset", dataset_name)
    with st.expander("Preview dataset"):
        st.dataframe(df.head(10), use_container_width=True)
    with st.expander("Column information"):
        st.dataframe(pd.DataFrame({
            "Column": df.columns.astype(str),
            "Data Type": df.dtypes.astype(str).values,
            "Missing Values": df.isna().sum().values,
        }), use_container_width=True, hide_index=True)

# ------------------------------ Ask mode --------------------------
st.divider()
mode = st.radio(
    "Choose a question mode",
    ["General Questions", "Data-Specific Questions"],
    horizontal=True,
    key="question_mode",
)
if mode == "General Questions":
    st.caption("Ask about concepts, coding, SQL, Python, data engineering, or other general topics.")
    placeholder = "Example: Explain incremental loading in ETL."
else:
    st.caption("Ask questions about the currently selected dataset.")
    placeholder = "Example: What is the total income for each religion?"
    if df is None or df.empty:
        st.warning("Load a dataset above to use Data-Specific Questions.")

with st.form("ask_form", clear_on_submit=False):
    question = st.text_input(
        "Your question",
        placeholder=placeholder,
        key="question_input",
    )
    ask_clicked = st.form_submit_button("✨ Ask DataMind AI", type="primary", use_container_width=True)

if ask_clicked:
    if not question.strip():
        st.warning("Please enter a question.")
    elif mode == "Data-Specific Questions" and (df is None or df.empty):
        st.warning("Please load a non-empty dataset first.")
    else:
        try:
            with st.spinner("Thinking through your question..."):
                if mode == "General Questions":
                    answer = ask_general(question.strip())
                    current = {
                        "mode": mode, "question": question.strip(),
                        "answer": answer, "dataset": None, "code": "", "result": None,
                    }
                else:
                    generated_code = ask_dataframe(question.strip(), df)
                    result = execute_query(generated_code, df)
                    current = {
                        "mode": mode, "question": question.strip(),
                        "answer": result, "dataset": dataset_name,
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
                st.session_state.history.insert(0, history_item)
                st.session_state.history = st.session_state.history[:30]
            st.rerun()
        except Exception as exc:
            st.error(f"Could not process the question: {exc}")

# ------------------------------ Result ----------------------------
current = st.session_state.current
if current is not None:
    st.divider()
    st.markdown("### Your question")
    st.write(current["question"])
    st.markdown("### DataMind AI answer")

    is_data_result = current["mode"] == "Data-Specific Questions"
    result = current.get("result")
    display_result = result_to_df(result) if is_data_result and result is not None else None

    if is_data_result:
        if isinstance(result, (pd.DataFrame, pd.Series)):
            st.dataframe(display_result.head(500), use_container_width=True)
            if len(display_result) > 500:
                st.caption("Showing the first 500 rows here. Use View or Download for the complete result.")
        else:
            st.success(str(result))
    else:
        st.markdown(current["answer"])

    st.divider()
    action_cols = st.columns(3)
    with action_cols[0]:
        if st.button("📧 Email", key="action_email", use_container_width=True):
            st.session_state.show_email_form = not st.session_state.show_email_form
            st.session_state.show_full_result = False
            st.session_state.show_download_options = False
    with action_cols[1]:
        if st.button("👁️ View", key="action_view", use_container_width=True):
            st.session_state.show_full_result = not st.session_state.show_full_result
            st.session_state.show_email_form = False
            st.session_state.show_download_options = False
    with action_cols[2]:
        if st.button("⬇️ Download", key="action_download", use_container_width=True):
            st.session_state.show_download_options = not st.session_state.show_download_options
            st.session_state.show_email_form = False
            st.session_state.show_full_result = False

    if st.session_state.show_full_result:
        st.markdown("### Full result")
        if is_data_result:
            st.dataframe(display_result, use_container_width=True, height=450)
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
                st.download_button("Download CSV", csv_data, f"{file_title}.csv", "text/csv", use_container_width=True)
            with dl2:
                st.download_button(
                    "Download Excel", excel_data, f"{file_title}.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
            with dl3:
                st.download_button("Download PDF", pdf_data, f"{file_title}.pdf", "application/pdf", use_container_width=True)
        else:
            text_data = current["answer"].encode("utf-8")
            st.download_button(
                "Download TXT", text_data, f"{file_title}.txt", "text/plain",
                use_container_width=True,
            )

    if st.session_state.show_email_form:
        st.markdown("### Email answer")
        recipient = st.text_input("Recipient email address", placeholder="recipient@example.com", key="recipient_email")
        if st.button("Send email", type="primary", key="send_email"):
            if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", recipient.strip()):
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
                        smtp_host = os.getenv("SMTP_HOST", "").strip()
                        smtp_port = int(os.getenv("SMTP_PORT", "587"))
                        smtp_user = os.getenv("SMTP_USER", "").strip()
                        smtp_password = os.getenv("SMTP_PASSWORD", "")
                        sender_email = os.getenv("SENDER_EMAIL", smtp_user).strip()
                        if not all([smtp_host, smtp_user, smtp_password, sender_email]):
                            raise ValueError("Email is not configured. Set SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, and SENDER_EMAIL.")
                        message = EmailMessage()
                        message["Subject"] = f"DataMind AI Answer: {file_title}"
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

st.caption("DataMind AI · Ask. Analyze. Discover.")
