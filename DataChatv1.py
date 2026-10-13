import os
import pandas as pd
from openai import OpenAI

# --------------------------------------------------
# 1. LOAD DATAFRAME
# --------------------------------------------------

input_file = r"c:\AI_DATA_SOLUTION\datainfo.csv"

df = pd.read_csv(input_file)

print("DataFrame loaded successfully")
print("Shape:", df.shape)


# --------------------------------------------------
# 2. OPENAI CLIENT
# --------------------------------------------------

os.environ["OPENAI_API_KEY"] = ""

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


# --------------------------------------------------
# 3. ASK DATAFRAME
# --------------------------------------------------

def ask_dataframe(question):

    # Give the model metadata about the dataframe
    dataframe_info = f"""
DataFrame shape:
{df.shape}

Columns:
{df.columns.tolist()}

Data types:
{df.dtypes.to_string()}

First 5 rows:
{df.head().to_string()}
"""

    # Ask OpenAI to determine what Pandas operation is required
    prompt = f"""
You are an expert Python Pandas data analyst.

You have access to a Pandas DataFrame called `df`.

DATAFRAME INFORMATION:
{dataframe_info}

USER QUESTION:
{question}

Your job is to determine the correct Pandas operation needed
to answer the user's question.

Return ONLY valid Python code that produces the answer.

Rules:
- Use the dataframe variable `df`.
- Do not create sample data.
- Do not modify df.
- Do not use file operations.
- Do not use network operations.
- Do not import libraries.
- Return one expression whenever possible.
"""

    response = client.responses.create(
        model="gpt-5.6-luna",
        input=prompt
    )

    generated_code = response.output_text.strip()

    print("\nGenerated Pandas code:")
    print(generated_code)

    # --------------------------------------------------
    # 4. EXECUTE MODEL-GENERATED CODE
    # --------------------------------------------------

    try:
        result = eval(
            generated_code,
            {
                "__builtins__": {},
                "df": df
            }
        )

        return result

    except Exception as e:

        return f"Unable to execute generated code: {e}"


# --------------------------------------------------
# 5. CHAT WITH DATAFRAME
# --------------------------------------------------

while True:

    question = input("\nAsk a question about your dataframe: ")

    if question.lower() in ["exit", "quit"]:
        break

    result = ask_dataframe(question)

    print("\nAnswer:")
    print(result)