#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/3/4 13:26
# @Author : 桐
# @QQ:1041264242
# 注意事项：

def read_md(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
            print(f"\033[92m Info | 读取MD成功:{file_path}。\033[0m")
            return content
    except FileNotFoundError:
        print(f"\033[91m Info | 文件未找到，请检查路径是否正确。\033[0m")
        return False
    except Exception as e:
        print(f"\033[91m Info | 读取文件时发生错误: {e}。\033[0m")
        return False

def generate_plan(content):

    prompt=f"""# Instruction
You are an expert in research analysis. Given the content of a research paper, your task is to extract and summarize the following key aspects:  

1. **Task Objective:** Clearly define the primary goal of the research. What problem does the paper aim to solve?  
2. **Task Description:** Provide a concise description of the research problem, including its significance and context.  
3. **Solution Approach:** Summarize the proposed method or solution presented in the paper. What techniques, models, or frameworks are used?  
4. **Experimental Plan:** Outline the experimental setup in a structured manner, ensuring a clear step-by-step breakdown of the research validation process,  including datasets, evaluation metrics, and methodology used to validate the approach. 

# Research Paper
’‘’{content}‘’‘

# Output Format
Provide your response in the following structured format:  

```plaintext
**Task Objective:**  
[Briefly describe the main research goal.]  

**Task Description:**  
[Summarize the problem and its importance in a concise manner.]  

**Solution Approach:**  
[Explain the methods or techniques applied to address the problem.]  

**Experimental Plan:**  
[Detail the datasets, evaluation metrics, and experimental setup used to test the proposed approach.]  
```  
"""

    return prompt

# content=read_md(file_path=r"C:\Users\10412\Desktop\多模态大语言模型\Code\天文Code\AutoAstro\test\main.md")
