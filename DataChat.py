# -*- coding: utf-8 -*-
"""
Created on Wed Sep 30 06:25:38 2026

@author: DELL
"""

#!pip install openai

from openai import OpenAI
import pandas as pd
### working on data info ### 
input_file = 'c:\AI_DATA_SOLUTION'
data_info = pd.read_csv(input_file+'\\'+'datainfo'+'.csv',header=True, inferSchema=True)
print('detail of data info is:-')



API_KEY = ""

#### this is working ####
'''
client = OpenAI(api_key=API_KEY)
response = client.responses.create(
    model="gpt-5.6-luna",
    input="What is data quality?"
)

print(response.output_text)
'''



from openai import OpenAI
import pandas as pd
import os

# Read CSV
input_file = r'F:\data_info\input_file'

data_info = pd.read_csv(
    input_file + r'\datainfo.csv',
    header=0
)

print(data_info.head())
print(data_info.columns)

os.environ["OPENAI_API_KEY"] = ""

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

import os
import pandas as pd
from openai import OpenAI

# Load dataframe
input_file = r'F:\data_info\input_file'

df = pd.read_csv(
    input_file + r'\datainfo.csv',
    header=0
)



def ask_dataframe(question):

    # Give the model the dataframe structure
    info = {
        "columns": df.columns.tolist(),
        "dtypes": df.dtypes.astype(str).to_dict(),
        "rows": len(df)
    }

    prompt = f"""
You are helping analyze a Pandas DataFrame.

DataFrame information:
{info}

User question:
{question}

Write Python/Pandas code that answers the question.

Return ONLY the Python code.
"""

    response = client.responses.create(
        model="gpt-5.6-luna",
        input=prompt
    )

    code = response.output_text

    print("Generated code:")
    print(code)

    return code