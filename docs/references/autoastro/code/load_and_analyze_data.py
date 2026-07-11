#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/3/10 16:04
# @Author : 桐
# @QQ:1041264242
# 注意事项：n
import time
from datetime import datetime
import json
import os
import re
import pandas as pd
from AutoAstro.datacode.data_core import get_real_data_path
from prompt import framework_prompt,task_initial_prompt
from framework_executor import machine_learning_executor,self_model_executor,deep_learning_executor
from error_correction import outlier_search
from llm_api import deepseek_chat
from analyze import insert_history_tree, update_node_content
from cross_match import select_cross_table
from tools import extract_suggestions,find_radio_dataset,extract_json,read_csv

root_dir=r"C:\Users\10412\Desktop\多模态大语言模型\Code\天文Code\AutoAstro"
data_core=r"C:\Users\10412\Desktop\多模态大语言模型\Code\天文Code\AutoAstro\data\data_core.json"
mm_example=r"C:\Users\10412\Desktop\多模态大语言模型\Code\天文Code\AutoAstro\model\mmpretrain\example.json"

def analyze_dataset_with_requirements(data_name, requirements): #选定数据集，并给出需求，机器分析
    # 示例使用
    json_file_path = data_core  # 替换为你数据信息存储的 JSON 文件路径
    result = find_radio_dataset(json_file_path,data_name)

    # 获取当前时间并格式化为年月日时分
    current_time = datetime.now().strftime("%Y%m%d%H%M")
    fold_path = fr"{root_dir}\data\task_result\{current_time}"
    os.makedirs(fold_path, exist_ok=True)
    history_json_path=fr'{fold_path}\history_tree.json' #历史分析路径

    # 定义要插入的新数据
    root = {
        "id": 0,
        "total": 0,
        "task": requirements,
        "type": "goal",
        "framework": "",
        "children": []
    }

    with open(history_json_path, 'w', encoding='utf-8') as json_file:
        json.dump(root, json_file, indent=4)

    if result:
        print(f"\033[92m Info | Step1 数据库中成功查询到: {data_name}。\033[0m")
        data_intr=get_real_data_path(query_data=result)
    else:
        print(f"\033[91m Info | Step1 数据库中未能查询到: {data_name}。\033[0m")

    tool_prompt = framework_prompt(requirements,data_intr['task_background'],data_intr['task_describe'])

    answer,history=deepseek_chat(user=tool_prompt, history_message=[], system="")
    framework=extract_suggestions(answer)
    print(framework)
    print(f"\033[92m Info | 执行框架: {framework}。\033[0m")
    # framework=['Deep Learning']
    # print(framework)

    update_node_content(target_id=0, new_content={"framework": framework[0]}, history_json=history_json_path)

    if framework[0] == "Machine Learning" or framework[0] == "SelfModel":
        #交叉证认
        print(f"\033[92m Info | 执行Step2: 开始执行数据交叉证认。 注意：证认误差3角秒。\033[0m")
        data_intr = select_cross_table(data_intr)
        pre_data=read_csv(file_path=data_intr['load_path'])

        print(f"\033[92m Info | 执行Step2: 数据异常检测。\033[0m")
        clean_data=outlier_search(df=pre_data) #异常数据检测
        # 指定保存路径
        clean_save_path = fr"{root_dir}\data\clean_data\{data_intr['data_name']}.csv"
        # 确保目录存在
        os.makedirs(os.path.dirname(fr"{root_dir}\data\clean_data"), exist_ok=True)
        # 保存数据
        if os.path.exists(clean_save_path) == False:
            clean_data.to_csv(clean_save_path, index=False, encoding='utf-8')

        print(f"\033[92m Info | 执行Step2: 数据异常检测完毕。\033[0m")
        #推荐执行任务
        initial_task_list=step_one_task_recommendation(data_intr=data_intr,requirements=requirements,clean_save_path=clean_save_path,framework=framework[0])
        shown_list=""
        for index,task in enumerate(initial_task_list["exploratory_tasks"]):
            shown_list+=f"\n{index+1}.{task['task_description']}"
            new_data={
                "id": index+1,
                "task": task['task_description'] ,
                "explanation": task["explanation"],
                "type": task["task_type"],
                "done":False,
                "children": [],
            }
            insert_history_tree(target_id=0,new_data=new_data,history_json=history_json_path)

        try:
            user_input = input(f"根据您当前的需求: '{requirements}', 推荐的执行任务如下:{shown_list}\n请输入一个以逗号分隔的数组（例如：1,2,3,4,5）来选择您想要执行的任务：")
            # 将输入字符串按逗号分割，并转换为整数列表
            array = [int(item) for item in user_input.split(',')]
        except ValueError:
            # 如果输入的不是有效的整数，捕获异常并提示用户
            print(f"\033[91m Info | 输入无效，请确保输入的是以逗号分隔的整数。\033[0m")

        pre_execute_task=[]
        for num in array:
            pre_execute_task.append({'task_id':num,'task':initial_task_list["exploratory_tasks"][num-1],'data volume':len(clean_data)})
    elif framework[0] == "Deep Learning":
        print(f"\033[92m Info | 执行Step2: 图像数据无需进行数据异常检测。\033[0m")

        with open(mm_example, 'r', encoding='utf-8') as file:
            models = json.load(file)

        model_list=[]
        for index,model in enumerate(models):
            new_data={
                "id": index+1,
                "task": '' ,
                "explanation": '',
                "type": list(models.keys())[index],
                "done":False,
                "children": [],
            }
            insert_history_tree(target_id=0,new_data=new_data,history_json=history_json_path)
            model_list.append(list(models.keys())[index])

        try:
            user_input = input(f"根据您当前的需求: '{requirements}', 当前图像学习算法库中具有以下模型架构:{model_list}\n请输入一个以逗号分隔的数组（例如：1,2,3,4,5）来选择您希望训练的模型架构：")
            # 将输入字符串按逗号分割，并转换为整数列表
            array = [int(item) for item in user_input.split(',')]
        except ValueError:
            # 如果输入的不是有效的整数，捕获异常并提示用户
            print(f"\033[91m Info | 输入无效，请确保输入的是以逗号分隔的整数。\033[0m")

        pre_execute_task=[]
        for num in array:
            pre_execute_task.append({'task_id':num,'type':model_list[num-1]})

    else:
        print(f"\033[91m Info | 框架识别异常。\033[0m")

    if "Deep Learning" == framework[0]:
        print(f"\033[92m Info | Step3 执行框架选择: {framework}，开始执行图像分类任务。\033[0m")
        deep_learning_executor(data_intr,fold_path,requirements,pre_execute_task,mm_example,history_json_path)
    elif "Swift" == framework[0]:
        print(f"\033[92m Info | Step3 执行框架选择: {framework}，开始执行多模态微调任务。\033[0m")
    elif "Machine Learning" == framework[0]:
        print(f"\033[92m Info | Step3 执行框架选择: {framework}，开始执行传统机器学习任务。\033[0m")
        machine_learning_executor(data_intr,fold_path, requirements, initial_task_list["summary"],pre_execute_task,history_json_path,clean_save_path)
    elif "SelfModel" == framework[0]:
        print(f"\033[92m Info | Step3 执行框架选择: {framework}，开始执行自建模型任务。\033[0m")
        self_model_executor(data_intr,fold_path, requirements, initial_task_list["summary"],pre_execute_task,history_json_path,clean_save_path)

    else:
        print(f"\033[91m Info | Step3 执行框架选择出现错误。\033[0m")


def select_and_analyze_data_with_requirements(requirements): #给出需求，机器自主选择数据 验证 和 分析
    pass

def auto_analyze_and_generate_requirements(dataset): #选定数据集， 机器 自动提出需求 并 分析
    pass

def step_one_task_recommendation(data_intr,requirements,clean_save_path,framework):
    df=read_csv(file_path=clean_save_path)

    # 获取每列的数据类型
    headers = df.columns
    data_types = df.dtypes

    df_head=""
    # 以标准的格式输出表头及其对应的数据类型
    for header, dtype in zip(headers, data_types):
        df_head+=f"('{header}','{dtype}');"

    task_recommendation_initial_prompt = task_initial_prompt(requirements,data_intr['task_background'],df_head,data_intr['task_describe'],framework)

    print(task_recommendation_initial_prompt)
    answer, history = deepseek_chat(user=task_recommendation_initial_prompt, history_message=[], system="")
    print(answer)

    # print(answer)
#     answer={
#     "summary": "The dataset contains key features of stars, including temperature, luminosity, radius, absolute magnitude, star color, spectral class, and star type. The data is designed to align with the Hertzsprung-Russell (HR) Diagram, a fundamental tool in stellar classification. The goal is to analyze the distribution of star types based on absolute magnitude and radius, and identify anomalies or outliers. Potential challenges include missing values, outliers in temperature or luminosity, and the need to normalize or transform data for accurate HR Diagram plotting.",
#     "exploratory_tasks": [
#         {
#             "task_description": "Analyze the distribution of star types based on absolute magnitude and radius to identify patterns and anomalies.",
#             "task_type": "Distribution analysis and anomaly detection",
#             "selected_columns": [
#                 {
#                     "column_name": "Absolute magnitude(Mv)",
#                     "explanation": "Absolute magnitude is a key indicator of a star's intrinsic brightness and is critical for HR Diagram analysis."
#                 },
#                 {
#                     "column_name": "Radius(R/Ro)",
#                     "explanation": "Radius, relative to the Sun, helps classify stars into categories like dwarfs, giants, and supergiants."
#                 },
#                 {
#                     "column_name": "Star type",
#                     "explanation": "This is the target variable for classification and distribution analysis."
#                 }
#             ],
#             "explanation": "This task is essential for understanding how stars are distributed across different types based on their absolute magnitude and radius. It will help validate the HR Diagram and identify any outliers or anomalies that deviate from expected patterns."
#         },
#         {
#             "task_description": "Investigate the relationship between absolute magnitude and temperature to validate the HR Diagram.",
#             "task_type": "Correlation study",
#             "selected_columns": [
#                 {
#                     "column_name": "Absolute magnitude(Mv)",
#                     "explanation": "Absolute magnitude is a proxy for luminosity and is a key variable in the HR Diagram."
#                 },
#                 {
#                     "column_name": "Temperature (K)",
#                     "explanation": "Temperature is a fundamental property of stars and is plotted on the x-axis of the HR Diagram."
#                 }
#             ],
#             "explanation": "This task will help confirm the expected inverse relationship between absolute magnitude and temperature, a hallmark of the HR Diagram. It also aids in identifying stars that do not conform to this trend."
#         },
#         {
#             "task_description": "Classify stars into spectral classes and analyze their distribution across star types.",
#             "task_type": "Classification and distribution analysis",
#             "selected_columns": [
#                 {
#                     "column_name": "Spectral Class",
#                     "explanation": "Spectral class provides information about a star's temperature and composition, which are key to its classification."
#                 },
#                 {
#                     "column_name": "Star type",
#                     "explanation": "This column is used to map spectral classes to specific star types."
#                 }
#             ],
#             "explanation": "This task will reveal how spectral classes correlate with star types, providing insights into the physical properties of different star categories."
#         },
#         {
#             "task_description": "Detect outliers in luminosity and radius relative to star type.",
#             "task_type": "Anomaly detection",
#             "selected_columns": [
#                 {
#                     "column_name": "Luminosity(L/Lo)",
#                     "explanation": "Luminosity is a critical feature for identifying stars that deviate from expected brightness levels."
#                 },
#                 {
#                     "column_name": "Radius(R/Ro)",
#                     "explanation": "Radius helps identify stars that are unusually large or small for their type."
#                 },
#                 {
#                     "column_name": "Star type",
#                     "explanation": "Used as a reference to identify anomalies within each star type."
#                 }
#             ],
#             "explanation": "This task is crucial for identifying stars that do not conform to typical luminosity-radius relationships, which could indicate measurement errors or rare stellar phenomena."
#         },
#         {
#             "task_description": "Visualize the HR Diagram using absolute magnitude and temperature.",
#             "task_type": "Visualization",
#             "selected_columns": [
#                 {
#                     "column_name": "Absolute magnitude(Mv)",
#                     "explanation": "Plotted on the y-axis of the HR Diagram."
#                 },
#                 {
#                     "column_name": "Temperature (K)",
#                     "explanation": "Plotted on the x-axis of the HR Diagram."
#                 },
#                 {
#                     "column_name": "Star type",
#                     "explanation": "Used to color-code points for better visualization of star types."
#                 }
#             ],
#             "explanation": "Visualizing the HR Diagram is essential for validating the dataset's alignment with theoretical stellar classifications and identifying any deviations."
#         }
#     ]
# }

    # return extract_json(answer)

    return extract_json(answer)


if __name__ == "__main__":
    time_start=time.time()
    #test
    # analyze_dataset_with_requirements(data_name="Star dataset to predict star types", requirements="Help me train a model for classifying star types and test its effectiveness")
    # analyze_dataset_with_requirements(data_name="Star dataset to predict star types", requirements="How does the temperature of stars correlate with their luminosity, and how well does this relationship align with the expected pattern on the Hertzsprung-Russell Diagram?")
    # analyze_dataset_with_requirements(data_name="Asteroid Dataset",requirements="Help me train a classification model")
    # analyze_dataset_with_requirements(data_name="Asteroid Dataset", requirements="help me analyze the interesting information in the following data")

    # analyze_dataset_with_requirements(data_name="The light curve of a variable star", requirements="Help me analyze the data below and draw some interesting insights,Please use machine learning for analysis")

    # analyze_dataset_with_requirements(data_name="Bright Star Dataset", requirements="Please use right ascension and declination to draw a mollwide diagram")

    # analyze_dataset_with_requirements(data_name="Bright Star Dataset",
    #                                   requirements="Please use right ascension and declination to draw a mollwide diagram")
    # analyze_dataset_with_requirements(data_name="Bright Star Dataset",requirements="Create 2D heatmap of RA/Dec binned by median vmag and Identify outliers in visual magnitude (vmag) for potential anomalies or data errors.")


    # analyze_dataset_with_requirements(data_name="Bright Star Dataset",
    #                                   requirements="Help me analyze the data below and find some interesting insights")

    # analyze_dataset_with_requirements(data_name="Star dataset to predict star types",
    #                                   requirements="Help me analyze the data below and find some interesting insights")
    # analyze_dataset_with_requirements(data_name="Star dataset to predict star types",
    #                                   requirements="Investigate the relationship between absolute magnitude and luminosity to validate the inverse square law of brightness.")
    # analyze_dataset_with_requirements(data_name="Star dataset to predict star types",
    #                                   requirements="Analyze the distribution of star radii to understand the prevalence of different stellar sizes (e.g., dwarfs, giants, supergiants).")
    # analyze_dataset_with_requirements(data_name="Star dataset to predict star types",
    #                                   requirements="Identify outliers or anomalies in the dataset that do not conform to expected HR Diagram patterns..")

    # analyze_dataset_with_requirements(data_name="Star dataset to predict star types",
    #                                   requirements="Plot stars on the HR Diagram (Temperature vs. Luminosity) to visually identify outliers that do not conform to expected patterns.")

    # analyze_dataset_with_requirements(data_name="Star dataset to predict star types",
    #                                   requirements="Build a  classification model using 'Temperature (K)', 'Luminosity(L/Lo)', 'Radius(R/Ro)' and 'Absolute magnitude(Mv)' to predict the 'Spectral Class' field.")
    # analyze_dataset_with_requirements(data_name="Star dataset to predict star types",
    #                                   requirements="Build a  classification model using 'Temperature (K)', 'Luminosity(L/Lo)', 'Radius(R/Ro)' and 'Absolute magnitude(Mv)' to predict the 'Star type' field.")

    # analyze_dataset_with_requirements(data_name="Star dataset to predict star types",
    #                                   requirements="Use clustering (e.g., DBSCAN or k-means) to group stars based on Temperature, Luminosity, and Radius, then identify points far from any cluster.")

    # analyze_dataset_with_requirements(data_name="Star dataset to predict star types",
    #                                   requirements="Analyze the distribution of star colors and their frequency in the dataset.")

    # analyze_dataset_with_requirements(data_name="simulated Hubbles Law Data",
    #                                   requirements="Help me analyze the data below and find some interesting insights")

    # analyze_dataset_with_requirements(data_name="simulated Hubbles Law Data",
    #                                   requirements="Investigate the relationship between apparent magnitude and redshift to understand how galaxy distance correlates with velocity")

    # analyze_dataset_with_requirements(data_name="simulated Hubbles Law Data",
    #                                   requirements="Analyze the distribution of redshift values to identify any anomalies or clustering that might indicate peculiar velocities or measurement biases.")

    # analyze_dataset_with_requirements(data_name="simulated Hubbles Law Data",
    #                                   requirements="Convert apparent magnitude to luminosity distance and plot against redshift to visualize the Hubble relationship.")

    # analyze_dataset_with_requirements(data_name="Gaia Astronomical Data",
    #                                   requirements="Visualize the 2D spatial distribution of object types in the Galactic plane using Galactic longitude (glon) and latitude (glat).")

    # analyze_dataset_with_requirements(data_name="Gaia Astronomical Data",
    #                                   requirements="Build a classification model using 'distance (parsecs)' and 'radius (parsecs)' to predict the 'type' field.")

    # analyze_dataset_with_requirements(data_name="Gaia Astronomical Data",
    #                                   requirements="Investigate correlations between vertical (z) and radial (xy) distances to test for systematic trends (e.g., warp/flare).")

    # analyze_dataset_with_requirements(data_name="Gaia Astronomical Data",
    #                                   requirements="Analyze the vertical (z-axis) distribution of objects to identify trends or clustering relative to the Galactic plane.")

    # analyze_dataset_with_requirements(data_name="Stellar Classification Dataset - SDSS17",
    #                                   requirements="Analyze the distribution of object classes (stars, galaxies, quasars) to understand dataset composition and be careful not to perform any sampling during the analysis process. ")

    # analyze_dataset_with_requirements(data_name="Stellar Classification Dataset - SDSS17",
    #                                   requirements="Compare photometric measurements (u, g, r, i, z) across object classes and be careful not to perform any sampling during the analysis process. ")

    # analyze_dataset_with_requirements(data_name="Stellar Classification Dataset - SDSS17",
    #                                   requirements="Train a logistic regression model to predict 'class' using photometric features and redshift.")

    # analyze_dataset_with_requirements(data_name="Stellar Classification Dataset - SDSS17",
    #                                   requirements="Investigate how redshift affects the correlations between photometric bands (u-z) in quasars, to understand their evolution with distance and improve redshift estimation methods.")


    # analyze_dataset_with_requirements(data_name="Stellar Classification Dataset - SDSS17",
    #                                   requirements="Build a regression model to predict redshift using photometric bands (u-z) for quasars and evaluate its performance.")

    # analyze_dataset_with_requirements(data_name="Solar Flares from RHESSI Mission Data",
    #                                   requirements="Using visualization methods to analyze the temporal distribution of solar flares to identify seasonal or cyclic patterns.")

    # analyze_dataset_with_requirements(data_name="Solar Flares from RHESSI Mission Data",
    #                                   requirements="Classify flares based on their duration and peak count rates to identify distinct temporal patterns.")

    # analyze_dataset_with_requirements(data_name="celestial_object_classify",
    #                                   requirements="Analyze the distribution of celestial object classes to identify potential class imbalance and be careful not to perform any sampling during the analysis process.")

    # analyze_dataset_with_requirements(data_name="celestial_object_classify",
    #                                   requirements="Examine spatial distribution of objects using Right Ascension and Declination on a mollwide diagram and be careful not to perform any sampling during the analysis process.")

    # analyze_dataset_with_requirements(data_name="celestial_object_classify",
    #                                   requirements="Compare Petrosian radii and fluxes across classes to study object morphologies.")

    # analyze_dataset_with_requirements(data_name="celestial_object_classify",
    #                                   requirements="Train a preliminary classification model using photometric features and evaluate performance.")

    # analyze_dataset_with_requirements(data_name="celestial_object_classify",
    #                                   requirements="Investigate correlations between Petrosian fluxes and radii within each class.")

    # analyze_dataset_with_requirements(data_name="Tycho Astrometry Catalog",
    #                                   requirements="Analyze the distribution of proper motions (pmRA, pmDE) to identify high-velocity stars or outliers.")

    # analyze_dataset_with_requirements(data_name="Tycho Astrometry Catalog",
    #                                   requirements="Examine spatial distribution of stars using RAdeg and DEdeg to identify overdensities or voids.")

    # analyze_dataset_with_requirements(data_name="Tycho Astrometry Catalog",
    #                                   requirements="Investigate the relationship between BTmag and VTmag to classify stars by color and identify potential variable stars.")

    # analyze_dataset_with_requirements(data_name="Tycho Astrometry Catalog",
    #                                   requirements="Explore correlations between positional errors (e_RA, e_DE) and epoch differences (epRA, epDE) to assess temporal effects.")


    # analyze_dataset_with_requirements(data_name="Solar Flares from RHESSI Mission Data",
    #                                   requirements="Train and evaluate a logistic regression model predicting peak.c/s (binned into categories) using duration.s and temporal features.")


    #时序
    # analyze_dataset_with_requirements(data_name="plasticc", requirements="Help me train a model based on data, and try to do some clustering analysis")
    # analyze_dataset_with_requirements(data_name="plasticc",
    #                                   requirements="Help me train a model based on data")
    # analyze_dataset_with_requirements(data_name="Loamst_Class",requirements="Help me train a model based on data")
    # analyze_dataset_with_requirements(data_name="Loamst_Pre", requirements="Help me train a model based on data")


    #图像测试
    # analyze_dataset_with_requirements(data_name="Loamst_Pre", requirements="Help me train a model based on data")
    # analyze_dataset_with_requirements(data_name="RadioGalaxyDataset", requirements="Please help me train a classification model")
    # analyze_dataset_with_requirements(data_name="SpectrumCls",
    #                                   requirements="Please help me train a classification model")
    # time_start=time.time()
    # analyze_dataset_with_requirements(data_name="HTRU_Medlat", requirements="Please help me train a classification model")
    # analyze_dataset_with_requirements(data_name="FAST_2018",
    #                                   requirements="Please help me train a classification model")
    # time_end=time.time()
    # print(time_end-time_start)

    #cross
    # analyze_dataset_with_requirements(data_name=r"plasticc",
    #                                   requirements="Explore how 'Teff' and 'logg' vary with target classes (e.g., supernovae, variable stars) to identify class-specific physical properties.")

    analyze_dataset_with_requirements(data_name="Tycho Astrometry Catalog",
                                      requirements="Investigate the relationship between BTmag and VTmag to classify stars by color and identify potential variable stars.")

    time_end=time.time()
    print(time_end-time_start)