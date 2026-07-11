#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/4/16 18:37
# @Author : 桐
# @QQ:1041264242
# 注意事项：
import json
import re

import pandas as pd
from astropy import units as u
from astroquery.xmatch import XMatch
from astropy.table import Table
from itertools import accumulate
from prompt import cross_col_recognition_prompt
from llm_api import deepseek_chat

catalogue_file_path = r'C:\Users\10412\Desktop\多模态大语言模型\Code\天文Code\AutoAstro\data\cross_data\json\common_tables.json'  # 替换为你的 JSON 文件路径

def select_cross_table(data_intr,json_file_path=catalogue_file_path):

    with open(json_file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)

    recommed_cross_table=""
    index = 0
    for key, value in data.items():
        index+=1
        recommed_cross_table+=f"\n{index}. {key}: {value['cat']['desc']}"

    try:
        user_input = input(f"\033[93m   Question | 推荐的交叉证认数据库为：{recommed_cross_table}\n是否希望尝试进行数据交叉证认？(如果不希望进行输入: n), 否则请输入一个1-5之间的数字来选择您希望进行交叉匹配的数据库: \033[0m")

        if user_input == 'n':
            print("\033[93m   Info | 已跳过自动交叉证认。\033[0m")
            return data_intr
        else:
            # 将输入字符串按逗号分割，并转换为整数列表
            id = int(user_input)-1

            df = pd.read_csv(data_intr["load_path"])
            ori_num_columns = df.shape[1]
            columns_info = [(col, str(df[col].dtype)) for col in df.columns]
            print(f"\033[93m   Info | 原始文件中的列信息：{columns_info}。\033[0m")

            input_table = Table.read(data_intr["load_path"])
            # print(input_table)
            prompt = cross_col_recognition_prompt(data_intr, columns_info)
            print(prompt)
            answer, history = deepseek_chat(user=prompt, history_message=[], system="")

            if 'None' in answer:
                print("\033[92m Info | 未查询到任何可能的赤经赤纬字段，已跳过自动交叉证认。\033[0m")
            else:
                ra_dec_columns = extract_json(answer)
                # print(ra_dec_columns)
                # print(list(data.keys())[id])
                table = XMatch.query(cat1=input_table, cat2=f'vizier:{list(data.keys())[id]}',
                                     max_distance=3 * u.arcsec,
                                     colRA1=ra_dec_columns['ra'], colDec1=ra_dec_columns['dec'])

                print(f"\033[93m   Info | 交叉证认后数据列：{table.colnames}。\033[0m")

                cross_colnames = table.colnames[ori_num_columns + 1:]

                # print(table.info)
                colnames_XMatch_des = extract_xmath_ifo(str(table.info))

                user_input = input(
                    f"\033[93m Question | 请选择需要保留的交叉证认字段：{cross_colnames}\n请输入要保留的字段(多个字段用逗号/空格分隔):\033[0m").strip()

                if not user_input:
                    print("\033[91m   Info | 错误: 输入不能为空\033[0m")
                    return data_intr

                # 处理输入：分割并去除空白
                selected_fields = [f.strip() for f in user_input.replace(",", " ").split()]
                # 验证字段是否存在
                invalid_fields = [f for f in selected_fields if f not in cross_colnames]
                if invalid_fields:
                    print(f"\033[31m   Info | 错误: 无效字段 {invalid_fields}\033[0m")

                # 步骤1：保留指定列
                columns_to_keep = list(df.columns) + selected_fields  # 替换为你的目标列名
                filtered_data = table[columns_to_keep]  # 直接通过列名选择

                print(f"\033[93m   Info | 最终数据列字段：{filtered_data.colnames}。\033[0m")

                from astroquery.vizier import Vizier
                v = Vizier(columns=["**"])  # 表示加载所有字段
                catalog = v.get_catalogs({list(data.keys())[id]})

                # 查看字段说明
                # print(catalog[0].colnames)
                # print(catalog[0].info)

                colnames_vizier_des = extract_vizier_ifo(text=str(catalog[0].info))
                matched=match_columns(selected_fields, colnames_vizier_des, colnames_XMatch_des)

                data_intr['data_name'] = data_intr['data_name']+"_cross"
                # 步骤2：写入 CSV 文件
                cross_save_path = fr"C:\Users\10412\Desktop\多模态大语言模型\Code\天文Code\AutoAstro\data\cross_data\{data_intr['data_name']}.csv"
                filtered_data.write(cross_save_path, format='csv', overwrite=True)
                data_intr['load_path'] = cross_save_path

                for key, value in matched.items():
                    data_intr['task_describe'] += f"\n{key}: {value}"

                print(data_intr)
                return data_intr

    except ValueError:
        # 如果输入的不是有效的整数，捕获异常并提示用户
        print(f"\033[91m Info | 输入无效，请确保输入正确。\033[0m")

    return 0

#json提取
def extract_json(text):
    # 使用正则表达式匹配Python代码块
    pattern = r"```json\n(.*?)\n```"
    match = re.search(pattern, text, re.DOTALL)

    if match:
        message_json = match.group(1)
        return json.loads(message_json)
    else:
        print("No json found.")

#正则处理xmatch字段描述信息:
def extract_xmath_ifo_bf(text):
    # 正则表达式解析每一行
    pattern = re.compile(r"""
^\s*(\S+)          # name
\s+(\S+)           # dtype
(?:\s+(\S+))?      # unit (optional)
\s+(.*?)           # description (optional, greedy to whitespace before last number)
\s+(\d+)\s*$       # n_bad
""", re.VERBOSE)

    result = []

    for line in text.strip().split("\n")[2:]:  # 跳过前两行标题
        match = pattern.match(line)
        if match:
            name, dtype, unit, desc, n_bad = match.groups()
            result.append({
                "name": name,
                "dtype": dtype,
                "unit": unit if unit else "",
                "description": desc.strip(),
                "n_bad": int(n_bad)
            })

    # 输出 JSON
    json_output = json.dumps(result, indent=4)
    print(json_output)

#正则处理xmatch字段描述信息:
def extract_xmath_ifo(text):
    result = []
    lengths = []
    for index, line in enumerate(text.strip().split("\n")[2:]):  # 跳过前两行标题
        if index == 0:
            standard=line.split(" ")
            # print(standard)
            # 统计每个字符串的长度
            # lengths = list(accumulate([len(s) for s in standard]))
            lengths = [val + idx for idx, val in enumerate(accumulate([len(s) for s in standard]))]
            # print(lengths)
        else:
            result.append({
                "name": line[0:lengths[0]].strip(),
                "dtype": line[lengths[0]:lengths[1]].strip(),
                "unit": line[lengths[1]:lengths[2]].strip(),
                "description": line[lengths[2]:lengths[3]].strip(),
                "n_bad": line[lengths[3]:lengths[4]].strip()
            })
    # 输出 JSON
    # json_output = json.dumps(result,indent=4)
    # print(json_output)
    return result

#正则处理vizier字段描述信息:
def extract_vizier_ifo_bf(text):
    print(text.split(" "))

    # 正则表达式解析每一行
    pattern = re.compile(r"""
^\s*(\S+)          # name
\s+(\S+)           # dtype
\s+(\S*)            # unit
\s+(\{\S+\})        # format
\s+(.*?)           # description (optional, greedy to whitespace before last number)
\s+(\d+)\s*$       # n_bad
""", re.VERBOSE)

    result = []

    for line in text.strip().split("\n")[2:]:  # 跳过前两行标题
        match = pattern.match(line)
        if match:
            name, dtype, unit, fmt, desc, n_bad = match.groups()
            result.append({
                "name": name,
                "dtype": dtype,
                "unit": unit,
                "format": fmt,
                "description": desc.strip(),
                "n_bad": int(n_bad)
            })

    # 输出 JSON
    json_output = json.dumps(result, indent=4)
    print(json_output)

#正则处理vizier字段描述信息:
def extract_vizier_ifo(text):
    result = []
    lengths = []
    for index, line in enumerate(text.strip().split("\n")[2:]):  # 跳过前两行标题
        if index == 0:
            standard=line.split(" ")
            # print(standard)
            # 统计每个字符串的长度
            # lengths = list(accumulate([len(s) for s in standard]))
            lengths = [val + idx for idx, val in enumerate(accumulate([len(s) for s in standard]))]
            # print(lengths)
        else:
            result.append({
                "name": line[0:lengths[0]].strip(),
                "dtype": line[lengths[0]:lengths[1]].strip(),
                "unit": line[lengths[1]:lengths[2]].strip(),
                "format": line[lengths[2]:lengths[3]].strip(),
                "description": line[lengths[3]:lengths[4]].strip(),
                "n_bad": line[lengths[4]:lengths[5]].strip()
            })

    # 输出 JSON
    json_output = json.dumps(result,indent=4)
    # print(json_output)
    # return json_output
    return result

def match_columns(cross_colnames, colnames_des1, colnames_des2):
    matched = {}
    unmatched = []

    # 第一步：匹配 colnames_des1
    des1_dict = {item['name']: item['description'] for item in colnames_des1 if item.get('description')}
    for col in cross_colnames:
        if col in des1_dict:
            matched[col] = des1_dict[col]  # 只存储description
        else:
            unmatched.append(col)

    # 第二步：匹配未命中的去 colnames_des2
    final_unmatched = []
    des2_dict = {item['name']: item['description'] for item in colnames_des2 if item.get('description')}
    for col in unmatched:
        if col in des2_dict:
            matched[col] = des2_dict[col]  # 只存储description
        else:
            final_unmatched.append(col)

    print(f"\033[93m   Info | 无法匹配列字段描述：{final_unmatched}。\033[0m")
    print(f"\033[93m   Info | 匹配列字段描述：{matched}。\033[0m")
    return matched


# data_intr=     {
#         "index": 9,
#         "data_name": "Star dataset to predict star types",
#         "task_background": "This is a dataset consisting of several features of stars. The purpose of making the dataset is to prove that the stars follows a certain graph in the celestial Space , specifically called Hertzsprung-Russell Diagram or simply HR-Diagram so that we can classify stars by plotting its features based on that graph.",
#         "task_describe": "## The field description in the CSV file:\nTemperature (K) - This column consists of the Surface temperatures of several stars.\nLuminosity(L/Lo) - This column consists of the Luminosity of several stars calculated with respect to sun(L/Lo).\nRadius(R/Ro) - This column consists of the Radius of several stars calculated with respect to sun(R/Ro).\nAbsolute magnitude(Mv) - This column consists of the Absolute Visual magnitude(Mv) of several stars.\nStar color - This column contains the info about the colors of each star after Spectral Analysis(white,Red,Blue,Yellow,yellow-orange etc).\nSpectral Class - This column contains info about the spectral classes of each star(O,B,A,F,G,K,,M).\nStar type - This column is the output class (6 classes ranging from 0-5) 0: Brown Dwarf, 1: Red Dwarf, 2: White Dwarf, 3: Main Sequence, 4: Supergiant, 5: Hypergiant.\n\n## Note:\nThe Luminosity and radius of each star is calculated w.r.t. that of the values of Sun.\nLo = 3.828 x 10^26 Watts (Avg Luminosity of Sun)\nRo = 6.9551 x 10^8 m (Avg Radius of Sun)",
#         "type": "local",
#         "load_path": "C:\\Users\\10412\\Desktop\\多模态大语言模型\\Code\\天文Code\\AutoAstro\\data\\ml_data\\Star dataset to predict star types.csv"
#     }
#
# data_intr1=    {
#         "index": 19,
#         "data_name": "Bright Star Dataset",
#         "task_background": "This dataset is a bright star dataset.",
#         "task_describe": "## The field description in the CSV file:\nHIP：The Hipparcos Catalog is a high-precision stellar catalog created by the European Space Agency's (ESA) Hipparcos satellite. Each star is assigned a unique HIP identifier (e.g., HIP 12345).\nRA：Stands for Right Ascension. Measured in degrees(0° to 360°). This is the celestial equivalent of longitude, specifying a star's position along the celestial equator.\nDec：Stands for Declination. Measured in degrees(-90° to 90°). This is the celestial equivalent of latitude, specifying a star's position north or south of the celestial equator.\nvmag：Stands for Visual Magnitude (V-band magnitude).",
#         "type": "local",
#         "load_path": "C:\\Users\\10412\\Desktop\\多模态大语言模型\\Code\\天文Code\\AutoAstro\\data\\ml_data\\Bright Star Dataset.csv"
#     }
#
# select_cross_table(data_intr1)

# input_table = Table.read(r'C:\Users\10412\Desktop\多模态大语言模型\Code\天文Code\AutoAstro\data\ml_data\celestial_object_classify.csv')
# print(input_table)
#
# # table = XMatch.query(cat1=input_table, cat2=f'vizier:II/246/out',
# #                      max_distance=3 * u.arcsec,
# #                      colRA1='RA', colDec1='Dec')
#
#
# table = XMatch.query(cat1=input_table, cat2=f'vizier:II/246/out',
#                      max_distance=3 * u.arcsec,
#                      colRA1='RightAscension', colDec1='Declination')
#
#
# print(table)
# # 查看所有列名
# print(table.colnames)