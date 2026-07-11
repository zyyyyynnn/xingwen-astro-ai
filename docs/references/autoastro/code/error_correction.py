#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/3/12 17:58
# @Author : 桐
# @QQ:1041264242
# 注意事项：
import re
import numpy as np
import pandas as pd
from llm_api import deepseek_chat
from tools import extract_code

def code_correction(code_erro,ori_code, column):
    correction_prompt=f"""# Role
You are an expert in in coding.

# Instruction
You need to correct and optimize the error based on the error messages provided by the existing code.

# Input
- Column(s) to process: ```{column}```

- Error messages: ```{code_erro}```

- Existing code: ```{ori_code}```

# Output
```python
    <corrected code>
```
"""
    answer, history = deepseek_chat(user=correction_prompt, history_message=[], system="")

    return extract_code(answer)

#检测None
def check_for_none(text):
    if 'Over' in text:
        return True
    else:
        return False

# 数据异常检测
def outlier_search(df):
    # 1. 查看基本信息
    print(
        f"\033[93m    Info | 数据预览: -------------------------------------------------------\nFirst 3 Rows:\n{df.head(3)}\nDescriptive Statistics:\n{df.describe()} \033[0m")
    print(f"\033[93m---------------------------------------------------------------------------------\033[0m")

    print(len(df))

    # 2.异常列检测
    # 询问用户是否希望自动处理缺失值
    user_input = input("\033[93m    Question | 是否希望自动进行列异常处理？(y/n): \033[0m").strip().lower()

    if user_input == 'y':
        # 自动处理：删除包含非数值类型缺失值的行
        df=detect_and_remove_abnormal_columns(df)
    elif user_input == 'n':
        print("\033[93m    Info | 已跳过自动处理，请手动处理可能存在的异常列。\033[0m")
    else:
        print("\033[91m    Error | 输入无效，已跳过自动处理。\033[0m")

    # 3. 缺失值检测
    missing_values = df.isna().sum()  # 初始缺失值检测
    if missing_values.any():
        print(f"\033[93m    Info | 检测到缺失值（包括NaN）: \n{missing_values[missing_values > 0]} \033[0m")
        # 处理数值类型的缺失值
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        for col in numeric_cols:
            if df[col].isna().all():  # 若整列全为空，跳过填充
                print(f"\033[91m    Warning | 数值列 {col} 全为 NaN，无法用中位数填充！\033[0m")
                continue
            median_value = df[col].median()
            if np.isnan(median_value):  # 额外检查中位数是否仍为 NaN
                print(f"\033[91m    Warning | 数值列 {col} 计算中位数失败，无法填充！\033[0m")
                continue
            df[col] = df[col].fillna(median_value)  # 修正 inplace=True 问题
        # 重新检测缺失值
        missing_values_after = df.isna().sum()
        # 输出数值类型的填充情况
        still_missing = missing_values_after[numeric_cols][missing_values_after[numeric_cols] > 0]
        if not still_missing.empty:
            print(f"\033[91m    Warning | 处理后仍然存在数值类型缺失值: \n{still_missing} \033[0m")
        else:
            print("\033[93m    Info | 数值类型的缺失值已全部填充！\033[0m")

        # 识别非数值类型的缺失列
        non_numeric_cols = df.select_dtypes(exclude=[np.number])
        missing_non_numeric = non_numeric_cols.isnull().sum()
        missing_non_numeric = missing_non_numeric[missing_non_numeric > 0]

        # 输出非数值列的名称及其数据类型
        if not missing_non_numeric.empty:
            print(f"\033[93m    Info | 非数值类型的缺失列名称和对应数据类型为： \033[0m")
            for col in missing_non_numeric.index:
                print(f"\033[93m - {col} (数据类型: {df[col].dtype}) \033[0m")

            # 询问用户是否希望自动处理缺失值
            user_input = input("\033[93m    Question | 是否希望自动处理非数值类型的缺失值？(y/n): \033[0m").strip().lower()

            if user_input == 'y':
                # 自动处理：删除包含非数值类型缺失值的行
                df = df.dropna(subset=missing_non_numeric.index)
                print("\033[92m    Success | 已自动删除包含非数值类型缺失值的行。\033[0m")
                print("\033[92m    Info | 处理后的数据行数: \033[0m", len(df))
            elif user_input == 'n':
                print("\033[93m    Info | 已跳过自动处理，请手动处理非数值类型的缺失值。\033[0m")
            else:
                print("\033[91m    Error | 输入无效，已跳过自动处理。\033[0m")

    else:
        print(f"\033[93m    Info | 未检测到缺失值。 \033[0m")

    # 4. 检测重复数据
    duplicates = df.duplicated()
    if duplicates.any():
        print(f"\033[93m    Info | 检测到 {duplicates.sum()} 条重复数据。 \033[0m")
        df = df.drop_duplicates()  # 删除重复数据
        print(f"\033[93m    Info | 重复数据已删除。处理后的数据行数: \033[0m", len(df))
        print(df[duplicates])
    else:
        print(f"\033[93m    Info | 未检测到重复数据。 \033[0m")

    return df

def detect_and_remove_abnormal_columns(df, threshold=0.3):
    """
    检测并删除异常缺失值占比超过阈值的列，并输出统计信息

    参数:
    df (pd.DataFrame): 输入的DataFrame
    threshold (float): 异常缺失值占比的阈值，默认为0.3（30%）

    返回:
    pd.DataFrame: 处理后的DataFrame
    """
    abnormal_values = ['unknown', 'Unknown', 'UNKNOWN', 'NA', '-999']

    stats = {}

    for col in df.columns:
        abnormal_count = df[col].apply(lambda x:
            pd.isna(x) or (isinstance(x, str) and x.strip() in abnormal_values) or (isinstance(x, str) and x.strip() == '')
        ).sum()

        abnormal_ratio = abnormal_count / len(df)
        stats[col] = {
            'abnormal_count': abnormal_count,
            'abnormal_ratio': abnormal_ratio,
            'is_removed': abnormal_ratio > threshold
        }

        if abnormal_ratio > threshold:
            df.drop(columns=[col], inplace=True)

    print("\033[92m    Success | 列异常值统计信息:\033[0m")
    print("-" * 90)
    for col, info in stats.items():
        print(f"-列 '{col}':  异常值数量: {info['abnormal_count']}  异常值占比: {info['abnormal_ratio']:.2%}  是否删除: {'是' if info['is_removed'] else '否'}")
    print("-" * 90)

    return df



