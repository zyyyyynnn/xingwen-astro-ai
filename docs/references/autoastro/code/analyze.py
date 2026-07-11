import json
from llm_api import gemini_2_Flash_chat
from llm_api import deepseek_chat

def visual_analyze_png(task_description,data_describe,image_path):
#     visual_analyze_prompt=f"""# Role: Expert in Astronomical Experimental Image Analysis
#
# # Instructions:
# You are a highly skilled astronomical experimental image analysis expert. Your expertise covers astrophysics, image processing, and data interpretation. You specialize in analyzing astronomical images, extracting meaningful insights, and correlating findings with scientific data.
#
# # Task:
# Given the provided inputs:
# - **Image Information**: The astronomical image to analyze.
# - **Task Description**: {task_description}
# - **Data Description**: {data_describe}
#
# # Your Responsibilities:
# 1. **Image Analysis**:
#    - Examine the image for key astronomical features.
#    - Identify celestial objects, patterns, or anomalies.
#    - Apply relevant astrophysical principles to interpret the visual data.
#
# 2. **Data Correlation**:
#    - Cross-reference image findings with provided dataset details.
#    - Assess how the visual data aligns with known astronomical models or theories.
#    - Highlight any deviations or unexpected phenomena.
#
# 3. **Insight Extraction**:
#    - Provide a detailed, structured analysis of the observations.
#    - Identify scientifically interesting insights, trends, or anomalies.
#    - Suggest possible interpretations or further investigations.
#
# # Output Format:
# Ensure the response is well-structured, clear, and scientifically rigorous. Use bullet points, tables, or structured paragraphs to enhance readability. Where applicable, provide quantitative assessments, comparative analyses, and hypotheses based on astronomical theories."""

    visual_analyze_prompt = f"""# Role:
Expert in Astronomical Experimental Image Analysis

# Instructions:
You are a highly skilled astronomical experimental image analysis expert. Your expertise covers astrophysics, image processing, and data interpretation. You specialize in analyzing astronomical images, extracting meaningful insights, and correlating findings with scientific data.  

# Task:
Given the provided inputs:  
- Image Information: The astronomical image to analyze.  
- Task Description: {task_description}
- Data Description: {data_describe}

# Your Responsibilities:
1. Image Analysis:  
   - Examine the image for key astronomical features.  
   - Identify celestial objects, patterns, or anomalies.  
   - Apply relevant astrophysical principles to interpret the visual data.  

2. Data Correlation:
   - Cross-reference image findings with provided dataset details.  
   - Assess how the visual data aligns with known astronomical models or theories.  
   - Highlight any deviations or unexpected phenomena.  

3. Insight Extraction:
   - Provide a detailed, structured analysis of the observations.  
   - Identify scientifically interesting insights, trends, or anomalies.  

# Output Requirements:
Ensure the response is well-structured, clear, and scientifically rigorous. Use bullet points, tables, or structured paragraphs to enhance readability. Where applicable, provide quantitative assessments, comparative analyses, and hypotheses based on astronomical theories."""

    return gemini_2_Flash_chat(user=visual_analyze_prompt,image_path=image_path)

def data_analyze_md(task_description,data_describe,md_path):

    with open(md_path, 'r', encoding='utf-8') as file:
        content = file.read()

#     data_analyze_prompt=f"""# Role:
# Expert in Astronomical Data Analysis
#
# # Instructions:
# You are a highly skilled expert in astronomical data analysis. Your expertise spans astrophysics, experimental data interpretation, and celestial object identification. You specialize in analyzing astronomical experiment results, extracting meaningful insights, and correlating findings with established scientific theories.
#
# # Task:
# Given the provided inputs:
# - **Experiment Results**: {content}
# - **Task Description**: {task_description}
# - **Data Description**: {data_describe}
#
# # Your Responsibilities:
# 1. **Result Analysis**:
#    - Examine the experiment results for key astronomical features.
#    - Identify celestial objects, patterns, or anomalies.
#    - Apply astrophysical principles to interpret the data effectively.
#
# 2. **Data Correlation**:
#    - Cross-reference findings with the provided dataset details.
#    - Assess how the results align with known astronomical models or theories.
#    - Highlight any deviations, anomalies, or unexpected findings.
#
# 3. **Insight Extraction**:
#    - Provide a detailed, structured analysis of the findings.
#    - Identify significant scientific insights, trends, or anomalies.
#    - Suggest possible interpretations or directions for further investigation.
#
# # Output Format:
# Ensure that your response is logically structured, scientifically rigorous, and clearly articulated. Use bullet points, tables, or structured paragraphs** to enhance readability. Where applicable, provide quantitative assessments, comparative analyses, and hypotheses based on astronomical theories.
# """
        data_analyze_prompt = f"""# Role:
Expert in Astronomical Data Analysis  

# Instructions:
You are a highly skilled expert in astronomical data analysis. Your expertise spans astrophysics, experimental data interpretation, and celestial object identification. You specialize in analyzing astronomical experiment results, extracting meaningful insights, and correlating findings with established scientific theories.  

# Task:
Given the provided inputs:  
- Experiment Results: {content}  
- Task Description: {task_description}  
- Data Description: {data_describe}  

# Your Responsibilities:
1. Result Analysis:
   - Examine the experiment results for key astronomical features.  
   - Identify celestial objects, patterns, or anomalies.  
   - Apply astrophysical principles to interpret the data effectively.  

2. Data Correlation:
   - Cross-reference findings with the provided dataset details.  
   - Assess how the results align with known astronomical models or theories.  
   - Highlight any deviations, anomalies, or unexpected findings.  

3. Insight Extraction:
   - Provide a detailed, structured analysis of the findings.  
   - Identify significant scientific insights, trends, or anomalies.

# Output Requirements:
Ensure that your response is logically structured, scientifically rigorous, and clearly articulated. Use bullet points, tables, or structured paragraphs** to enhance readability. Where applicable, provide quantitative assessments, comparative analyses, and hypotheses based on astronomical theories."""

    answer,histroy=deepseek_chat(user=data_analyze_prompt)

    return answer

def linking_insight(task,visual_insight,data_insight):

#     linking_insight_prompt=f"""# Positioning
# You are an expert in astronomical data analysis, responsible for standardizing and merging conclusions from different analysis methods (image analysis and data analysis), and evaluating whether the conclusions are sufficient to address the goal astronomical task. If the conclusions are insufficient, you need to recommend further subtasks.
#
# # Capabilities
# 1. **Text Merging and Standardization**: Ability to merge conclusions from "Visual Insight" and "Data Insight," remove redundancies, and generate concise, clear Markdown-formatted text.
# 2. **Conclusion Evaluation**: Ability to assess whether the merged conclusions are sufficient to solve the goal astronomical task.
# 3. **Task Recommendation**: If the conclusions are insufficient, ability to recommend further subtasks or areas worth deeper investigation.
#
# # Knowledge Base
# 1. Basic principles and methods of astronomical image analysis.
# 2. Basic principles and methods of astronomical data analysis.
# 3. Common resolution paths and further research directions for astronomical tasks.
#
# # Prompts
# 1. **Merge Conclusions**:
#    - Merge conclusions from "Visual Insight" and "Data Insight," removing redundant parts.
#    - Generate concise, clear Markdown-formatted text.
#
# 2. **Evaluate Conclusions**:
#    - Assess whether the merged conclusions are sufficient to solve the specified astronomical task.
#    - If insufficient, recommend further subtasks or areas worth deeper investigation.
#
# # Example Output
#
# # Merged Conclusions
# - **Image Analysis Conclusion**: Image analysis.
# - **Data Analysis Conclusion**: Data analysis.
#
# # Conclusion Evaluation
#
# # Recommended Subtasks
#   - Recommended Subtasks 1.
#   - Recommended Subtasks 2.
# """

    linking_insight_prompt = f"""# Instruction:
You are an expert in astronomical data analysis. Your task is to standardize and integrate conclusions from two different analysis methods: Visual Insight (image-based) and Data Insight (numerical/statistical analysis).

# Input:
You will receive conclusions from both sources, usually in bullet points or short text.

# Capabilities:
- Merge the insights from both analyses into a coherent summary.
- Eliminate redundant or overlapping points.
- Clarify and rephrase for precision and conciseness.
- Output should be in Markdown format with clear structure.

# Output Format:

## Conclusions
- Visual Insight: Insert insights from image-based analysis.
- Data Insight: Insert insights from data/statistical analysis.
- Final Conclusion: Provide an integrated, insightful conclusion that highlights correlations, discrepancies, or significant findings.

## Brief Summary
A simplified 1-2 sentence summary in no more than 50 words for non-expert readers.

# Style:
- Use clear, concise language.
- Highlight contrasts or confirmations between the two analysis types.
- Prefer active voice and domain-specific but understandable terms."""

    information=f"""Now, start your work.
The Goal astronomical task is ''{task}''
The Visual Insight is '''{visual_insight}'''
The Data_nsight is '''{data_insight}'''"""

    answer, histroy = deepseek_chat(user=information,history_message=[], system=linking_insight_prompt)

    return answer

#任务评估与进一步分解
def task_eval(task,insight,column,requirements):
    task_eval_prompt=f"""# Instruction
You are a data analysis expert. For given goal: "{requirements}" and task: "{task}". You need to judge whether the task requires further analysis based on derived insights and used columns. The complexity of the task can be considered from data, data mining, and visualization methods. If the task appears incomplete, it needs to be decomposed further. Please rate the task from 1-10. For example, if the initial solution adequately segments the data or if the task requires advanced statistical analysis or visual analysis. You should output a score and explanation of no more than 50 words for your evaluation.

# Input
- Used columns: {column}
- Derived insights: '''{insight}'''

# Output Format
```json
{{
"score": "",
"explanation": ""
}}```"""

    # print(task_eval_prompt)
    answer,histroy=deepseek_chat(user=task_eval_prompt)

    return answer

def subtask_decompose(requirements,task,usedcolumn,data,insight,score,reasons):
    task_decompose_prompt = f"""# Instruction
You are a data analysis expert. For given goal: "{requirements}" and task: "{task}". You need to discriminating whether this task requires further analysis based on insights report, such as using more detailed data segmentation or advanced statistical methods. The completion score of this task is {score}/10, with the reasons: "{reasons}" If needed, please generate no more than 3 subtasks and indicate the methods they use respectively based on this. You should write the tasks begin with ```json and end with ```, and the json data includes a list of tasks like this:

```json
{{
    "tasks": ["","",""],
    "execution order": "(Task 1 AND Task 2 AND Task 3)",
    "methods": ["","",""],
    "data variables":[["",""],[],[]],
    "task type":["","",""]
}}```

For data variables, the task may not correspond to the data, so you need to go to the data description and find the corresponding data variables, and even if transformation is required, you need to write the original column. There are two operators “AND” and “DOWN” in the execution order to connect tasks. “AND” indicates that all subtasks need to complete successfully but there is no requirement for execution order, “DOWN” indicates that subtasks need to be executed step by step in order. Each task is a sentence no more than 20 words, methods include data segmentation, statistical methods. Do not recommend any tasks that require cross-verification with external data sources. If do not need to decompose, output {{"tasks": ‘null’}}.

# Input
- Data description:: '''{data}'''
- Used columns: {usedcolumn}
- Insights report: '''{insight}'''
"""

    print(task_decompose_prompt)
    answer, histroy = deepseek_chat(user=task_decompose_prompt)

    return answer

#存储历史记录
def insert_history_tree(target_id,new_data,history_json):

    with open(history_json, 'r', encoding='utf-8') as file:
        node=json.load(file)
    new_id=node["total"]+1

    # 递归查找目标节点并插入新数据
    def recursive_insert(node):
        if node['id'] == target_id:
            if 'children' not in node:
                node['children'] = []
            node['children'].append(new_data)
            return True

        for child in node.get('children', []):
            if recursive_insert(child):
                return True

        return False

    # 调用递归函数
    if recursive_insert(node):
        # 如果插入成功，将修改后的数据写回文件
        with open(history_json, 'w', encoding='utf-8') as file:
            json.dump(node, file, ensure_ascii=False, indent=4)
        update_node_content(target_id=0,new_content={'total': new_id},history_json=history_json)
        return new_id

    return False

#更新历史记录
def update_node_content(target_id, new_content, history_json):
    #new_content = {'name': 'Updated Node', 'value': 100}

    # 读取 JSON 文件
    with open(history_json, 'r', encoding='utf-8') as file:
        node = json.load(file)

    # 递归查找并更新目标节点
    def recursive_update(node):
        # 如果当前节点是目标节点，更新内容
        if node['id'] == target_id:
            node.update(new_content)  # 更新节点内容
            return True
        # 递归遍历子节点
        for child in node.get('children', []):
            if recursive_update(child):
                return True
        return False

    # 调用递归函数
    if recursive_update(node):
        # 将更新后的树结构写回文件
        with open(history_json, 'w', encoding='utf-8') as file:
            json.dump(node, file, ensure_ascii=False, indent=4)
        return True
    return False

