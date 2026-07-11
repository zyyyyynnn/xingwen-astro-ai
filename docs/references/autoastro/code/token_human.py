#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/5/19 11:27
# @Author : 桐
# @QQ:1041264242
# 注意事项：
from llm_api import count_tokens

# 打开并读取md文件内容到变量text中

# 定义md文件路径（替换为你的实际文件路径）
file_path = r"C:\Users\10412\Desktop\SpectrumCls.md"  # 可以是相对路径或绝对路径

try:
    # 使用with语句打开文件，确保文件正确关闭
    with open(file_path, 'r', encoding='utf-8') as file:
        text = file.read()  # 读取全部内容到text变量

    # 打印前200个字符作为验证（可选）
    print(f"成功读取文件，前200个字符为：\n{text[:200]}...")

except FileNotFoundError:
    print(f"错误：文件 {file_path} 未找到，请检查路径")
except Exception as e:
    print(f"读取文件时发生错误: {e}")
else:
    # 这里可以继续使用text变量处理文件内容
    print(f"\n文件已成功读取，总字符数：{len(text)}")

print(count_tokens(text=text,type='in'))