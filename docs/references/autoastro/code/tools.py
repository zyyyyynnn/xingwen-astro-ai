#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/4/23 16:25
# @Author : 桐
# @QQ:1041264242
# 注意事项：
import json
import re
import pandas as pd


def tokenize(expr):
    return re.findall(r'\(|\)|Task \d+|AND|DOWN', expr)

def parse_expression(tokens):
    def get_task(token):
        return int(token.split()[-1]) - 1  # Task N -> index N-1

    def parse_tokens(tokens):
        stack = []
        output = []
        ops = []

        def apply_operator():
            op = ops.pop()
            if op == 'AND':
                b = output.pop()
                a = output.pop()
                output.append(('AND', a, b))
            elif op == 'DOWN':
                b = output.pop()
                a = output.pop()
                output.append(('DOWN', a, b))

        precedence = {'AND': 2, 'DOWN': 1}
        i = 0
        while i < len(tokens):
            token = tokens[i]
            if token == '(':
                j = i
                depth = 1
                while depth > 0:
                    i += 1
                    if tokens[i] == '(':
                        depth += 1
                    elif tokens[i] == ')':
                        depth -= 1
                output.append(parse_tokens(tokens[j + 1:i]))
            elif token.startswith('Task'):
                output.append(get_task(token))
            elif token in ('AND', 'DOWN'):
                while ops and precedence.get(ops[-1], 0) >= precedence[token]:
                    apply_operator()
                ops.append(token)
            i += 1

        while ops:
            apply_operator()

        return output[0]

    return parse_tokens(tokens)

def flatten_execution(ast):
    if isinstance(ast, int):
        return [[ast]]
    op, left, right = ast
    if op == 'AND':
        left_seq = flatten_execution(left)
        right_seq = flatten_execution(right)
        # merge levels (parallel execution)
        max_len = max(len(left_seq), len(right_seq))
        merged = []
        for i in range(max_len):
            step = []
            if i < len(left_seq): step += left_seq[i]
            if i < len(right_seq): step += right_seq[i]
            merged.append(step)
        return merged
    elif op == 'DOWN':
        return flatten_execution(left) + flatten_execution(right)

def parse_execution_order(expression):
    tokens = tokenize(expression)
    ast = parse_expression(tokens)
    return flatten_execution(ast)

def extract_suggestions(text):
    # 定义正则表达式模式，匹配<suggestion>标签中的内容
    pattern = r'<suggestion>(.*?)</suggestion>'

    # 使用findall方法查找所有匹配的内容
    suggestions = re.findall(pattern, text)

    # 使用set去除重复项，并转换回列表
    unique_suggestions = list(set(suggestions))

    return unique_suggestions

def find_radio_dataset(json_file_path,data_name):
    # 打开并读取 JSON 文件
    with open(json_file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)

    # 假设 JSON 文件中的数据是一个列表
    for item in data:
        # 检查 data_name 字段
        if item.get('data_name') == data_name:
            return item

    # 如果没有找到符合条件的项，返回 None
    return None

#json提取
def extract_json(text):
    # 使用正则表达式匹配json块
    pattern = r"```json\n(.*?)\n```"
    match = re.search(pattern, text, re.DOTALL)

    if match:
        message_json = match.group(1)
        # print(message_json)
        return json.loads(message_json)
    else:
        print("No json code block found. Trying to parse text directly as JSON.")

        # 尝试直接解析text内容为JSON
        try:
            # 去除首尾空白字符
            cleaned_text = text.strip()

            # 尝试解析
            return json.loads(cleaned_text)

        except json.JSONDecodeError:
            # 如果直接解析失败，尝试去除可能的代码块标记
            try:
                # 移除可能的 ```json 和 ``` 标记
                cleaned_text = re.sub(r'^```json|```$', '', text, flags=re.MULTILINE).strip()
                return json.loads(cleaned_text)
            except json.JSONDecodeError as e:
                print(f"Failed to parse text as JSON: {e}")
                return None

# 读取CSV文件
def read_csv(file_path):
    try:
        df = pd.read_csv(file_path)
        return df
    except Exception as e:
        print(f"读取CSV文件时出错: {e}")
        return None

#代码提取
def extract_code(text):
    # 使用正则表达式匹配Python代码块
    pattern = r"```python\n(.*?)\n```"
    match = re.search(pattern, text, re.DOTALL)

    if match:
        python_code = match.group(1)
        return python_code
    else:
        print("No Python code found.")

    # 使用正则表达式匹配json块
    pattern = r"```python\n(.*?)\n```"
    match = re.search(pattern, text, re.DOTALL)

    if match:
        python_code = match.group(1)
        return python_code
    else:
        print("No python code block found. Trying to parse text directly as CODE.")

        # 尝试直接解析text内容为JSON
        try:
            # 去除首尾空白字符
            cleaned_text = text.strip()

            # 尝试解析
            return cleaned_text

        except Exception as e:
            print(f"Failed to parse text as python code: {e}")



# print(parse_execution_order("(Task 1 AND Task 2) DOWN Task 3"))
test="""
```json
{
    "summary": "The dataset contains photometric and positional data for astronomical sources, focusing on infrared magnitudes (Jmag, Hmag, Kmag) for clustering. Key features include redshift information (host_specz, host_photoz), sky coordinates (ra, decl), observed fluxes across multiple passbands (fulx_0 to fulx_27), and a target class for known sources. Potential challenges include the presence of noisy or missing data in host_photoz, host_photoz_error, and flux measurements, which can affect clustering accuracy. DDF flags may also indicate data with higher precision. This analysis will aim to group objects based on their infrared magnitudes, which can hint at underlying physical processes or object types.",
    "exploratory_tasks": [
        {
            "task_description": "Explore the distribution of Jmag, Hmag, and Kmag values to understand their variation.",
            "task_type": "Distribution analysis",
            "selected_columns": [
                {
                    "column_name": "Jmag",
                    "column_type": "float64",
                    "explanation": "Jmag is a crucial feature for clustering and its range must be understood."
                },
                {
                    "column_name": "Hmag",
                    "column_type": "float64",
                    "explanation": "Hmag complements Jmag and shows the infrared magnitude in another band."
                },
                {
                    "column_name": "Kmag",
                    "column_type": "float64",
                    "explanation": "Kmag completes the trio of infrared magnitudes, essential for clustering."
                }
            ],
            "explanation": "Infrared magnitudes form the basis for clustering; understanding their range and distribution is critical for algorithm design. Visualization with histograms and KDE (Kernel Density Estimate) plots can help identify outliers and patterns."
        },
        {
            "task_description": "Analyze the correlation between Jmag, Hmag, and Kmag.",
            "task_type": "Correlation study",
            "selected_columns": [
                {
                    "column_name": "Jmag",
                    "column_type": "float64",
                    "explanation": "To examine how Jmag relates to other infrared bands."
                },
                {
                    "column_name": "Hmag",
                    "column_type": "float64",
                    "explanation": "To determine its correlation with other bands like Jmag and Kmag."
                },
                {
                    "column_name": "Kmag",
                    "column_type": "float64",
                    "explanation": "Investigating correlations helps understand the dependence between bands."
                }
            ],
            "explanation": "Strong correlations between these columns can simplify the clustering process or justify dimensionality reduction. Scatter plots and correlation matrices with heatmaps are effective here."
        },
        {
            "task_description": "Perform clustering on Jmag, Hmag, and Kmag to identify distinct groups.",
            "task_type": "Clustering analysis",
            "selected_columns": [
                {
                    "column_name": "Jmag",
                    "column_type": "float64",
                    "explanation": "Primary feature for clustering to identify object groups based on magnitude."
                },
                {
                    "column_name": "Hmag",
                    "column_type": "float64",
                    "explanation": "Used in conjunction with Jmag for cluster differentiation in infrared space."
                },
                {
                    "column_name": "Kmag",
                    "column_type": "float64",
                    "explanation": "Provides additional dimensionality for accurate clustering."
                }
            ],
            "explanation": "Clustering can reveal natural groupings of objects, which might correspond to physical differences. Techniques like K-Means or DBSCAN can be applied, and results visualized in 2D/3D plots using dimensionality reduction (e.g., PCA, t-SNE)."
        },
        {
            "task_description": "Assess the spatial distribution of clusters in terms of sky coordinates (ra, decl).",
            "task_type": "Spatial distribution analysis",
            "selected_columns": [
                {
                    "column_name": "ra",
                    "column_type": "float64",
                    "explanation": "Right ascension provides the horizontal coordinate for spatial analysis."
                },
                {
                    "column_name": "decl",
                    "column_type": "float64",
                    "explanation": "Declination complements ra and represents the vertical sky coordinate."
                },
                {
                    "column_name": "target",
                    "column_type": "int64",
                    "explanation": "The target class helps validate clustering results against known object types."
                }
            ],
            "explanation": "This task helps evaluate whether identified clusters are spatially related, indicating astrophysical patterns. Utilize sky maps or heatmaps for effective visualization."
        },
        {
            "task_description": "Identify and analyze outliers in the dataset, particularly in the Jmag-Hmag-Kmag space.",
            "task_type": "Anomaly detection",
            "selected_columns": [
                {
                    "column_name": "Jmag",
                    "column_type": "float64",
                    "explanation": "To find anomalous values that deviate significantly from the mean."
                },
                {
                    "column_name": "Hmag",
                    "column_type": "float64",
                    "explanation": "Helps identify objects with unusual infrared profiles."
                },
                {
                    "column_name": "Kmag",
                    "column_type": "float64",
                    "explanation": "Necessary for detecting anomalous combinations across the magnitude trio."
                }
            ],
            "explanation": "Outliers may signify rare or unique objects worth studying separately. Dimensionality reduction techniques like PCA combined with scatter plots can visually isolate anomalies."
        }
    ]
}
```
"""
print(extract_json(text=test))