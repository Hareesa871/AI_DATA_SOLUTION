# -*- coding: utf-8 -*-
"""
Created on Wed Sep 30 07:35:04 2026

@author: DELL
"""

import os
import pandas as pd
import streamlit as st
from openai import OpenAI

# -----------------------------
# Load DataFrame
# -----------------------------
input_file = r"c:\AI_DATA_SOLUTION"

df = pd.read_csv(
    input_file + r"\datainfo.csv",
    header=0
)

# -----------------------------
# OpenAI client
# -----------------------------
os.environ["OPENAI_API_KEY"] = ""

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

# -----------------------------
# Ask LLM
# -----------------------------
def ask_dataframe(question):

    metadata = {
        "rows": len(df),
        "columns": list(df.columns),
        "dtypes": df.dtypes.astype(str).to_dict()
    }

    prompt = f"""
You are a DataFrame analyst.

DataFrame metadata:
{metadata}

User question:
{question}

Generate ONE Python Pandas expression that answers the question.

Rules:
- Use the DataFrame named df.
- Do not create sample data.
- Do not import anything.
- Do not read or write files.
- Do not modify df.
- Return only the Python expression.
"""

    response = client.responses.create(
        model="gpt-5.6-luna",
        input=prompt,
        max_output_tokens=300
    )

    return response.output_text.strip()


# -----------------------------
# Streamlit UI
# -----------------------------
st.title("AI Data Analyst")

st.write("Ask a question about your DataFrame")

question = st.text_input(
    "Enter your question:"
)

if st.button("Ask Question"):

    if question:

        with st.spinner("Analyzing..."):

            generated_code = ask_dataframe(question)

            try:
                result = eval(
                    generated_code,
                    {"df": df}
                )

                st.subheader("Answer")
                st.write(result)

            except Exception as e:

                st.error(
                    f"Could not execute generated expression: {e}"
                )

    else:
        st.warning("Please enter a question.")