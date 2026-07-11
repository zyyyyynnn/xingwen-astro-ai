#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/3/10 16:07
# @Author : 桐
# @QQ:1041264242
# 注意事项：
import base64
from openai import OpenAI
from transformers import AutoTokenizer
# proxies ={
# 'http': 'http://localhost:7890',
# 'https': 'http://localhost:7890'
# }


#deepseek_chat_true
def deepseek_chat_true(user, history_message=[], system="You are a helpful assistant"):
    client = OpenAI(api_key="sk-xxxxxxx", base_url="https://api.deepseek.com/v1")

    if not history_message:
        if system=="":
            history_message = [
                {"role": "user", "content": user},
            ]
        else:
            history_message = [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]
    else:
        history_message.append({"role": "user", "content": user})

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=history_message,
        stream=False
    )

    history_message.append({"role": "assistant", "content": response.choices[0].message.content})

    count_tokens(text=user + system,type='in')
    count_tokens(text=response.choices[0].message.content, type='out')
    return response.choices[0].message.content, history_message

def qwen_vl_chat(user,image_path):
    client = OpenAI(api_key="sk-xxxxxxx", base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")

    # 读取本地图片并进行Base64编码
    base64_image=encode_image(image_path=image_path)

    completion = client.chat.completions.create(
        model="qwen-vl-max-0125",  # 此处以qwen-vl-plus为例，可按需更换模型名称。模型列表：https://help.aliyun.com/zh/model-studio/getting-started/models
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user},
                    {"type": "image_url","image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                ]
            }
        ]
    )

    print(completion.choices[0].message.content)

def gemini_2_Flash_chat(user,image_path):
    client = OpenAI(
        # 接入的close ai系列
        base_url='https://api.openai-proxy.org/v1',
        api_key='sk-xxxxxxx',
    )

    # 读取本地图片并进行Base64编码
    base64_image=encode_image(image_path=image_path)

    completion = client.chat.completions.create(
        model="gemini-2.0-flash",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user,},
                    {"type": "image_url","image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},},
                ],
            }
        ],

    )

    count_tokens(text=user,type='in')
    count_tokens(text=completion.choices[0].message.content, type='out')
    return completion.choices[0].message.content

# def deepseek_chat(user, history_message=[], system="You are a helpful assistant"):

# deepseek_chat qwen_max_chat
def qwen_max_chat(user, history_message=[], system="You are a helpful assistant"):
    client = OpenAI( api_key="sk-xxxxxxx", base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
    if not history_message:
        if system=="":
            history_message = [
                {"role": "user", "content": user},
            ]
        else:
            history_message = [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]
    else:
        history_message.append({"role": "user", "content": user})

    response = client.chat.completions.create(
        model="qwen-max-2025-01-25",
        messages=history_message,
        stream=False
    )

    history_message.append({"role": "assistant", "content": response.choices[0].message.content})

    count_tokens(text=user + system,type='in')
    count_tokens(text=response.choices[0].message.content, type='out')

    return response.choices[0].message.content, history_message

# deepseek_chat gpt4o_chat
def gpt4o_chat(user, history_message=[], system="You are a helpful assistant"):
    client = OpenAI(
        # openai系列的sdk，包括langchain，都需要这个/v1的后缀
        base_url='https://api.openai-proxy.org/v1',
        api_key='sk-xxxxxxx',
    )

    if not history_message:
        if system=="":
            history_message = [
                {"role": "user", "content": user},
            ]
        else:
            history_message = [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]
    else:
        history_message.append({"role": "user", "content": user})

    response = client.chat.completions.create(
        model="gpt-4o-2024-08-06",
        messages=history_message,
        stream=False
    )

    history_message.append({"role": "assistant", "content": response.choices[0].message.content})

    count_tokens(text=user + system,type='in')
    count_tokens(text=response.choices[0].message.content, type='out')
    return response.choices[0].message.content, history_message


in_put_token=0
out_put_token=0

#token计算
def count_tokens(text, type):

    global in_put_token
    global out_put_token

    chat_tokenizer_dir = "./"
    tokenizer = AutoTokenizer.from_pretrained(chat_tokenizer_dir, trust_remote_code=True)
    count = len(tokenizer.encode(text))

    if type=='in':
        in_put_token += count
    elif type=='out':
        out_put_token += count
    else:
        print("token erro")

    # 计算总计 token 数
    total_token = in_put_token + out_put_token
    # 使用紫色打印输出
    print(f"\033[35mInput tokens: {in_put_token}, Output tokens: {out_put_token}, Total tokens: {total_token}\033[0m")

#  base 64 编码格式
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


# print(gemini_2_Flash_chat(user="What is this image?",image_path=r"C:\Users\10412\Desktop\摩尔\微信图片_20250525163750.jpg"))
# user=f"""Please analyze the distribution of star types based on absolute magnitude and radius to identify patterns and anomalies.
#
# There is some background information:
# '''
# # The field description in the CSV file:
# Temperature (K) - This column consists of the Surface temperatures of several stars.
# Luminosity(L/Lo) - This column consists of the Luminosity of several stars calculated with respect to sun(L/Lo).
# Radius(R/Ro) - This column consists of the Radius of several stars calculated with respect to sun(R/Ro).
# Absolute magnitude(Mv) - This column consists of the Absolute Visual magnitude(Mv) of several stars.
# Star Color - This column contains the info about the colors of each star after Spectral Analysis(white,Red,Blue,Yellow,yellow-orange etc).
# Spectral Class - This column contains info about the spectral classes of each star(O,B,A,F,G,K,,M).
# Star type - This column is the output class (6 classes ranging from 0-5) 0: Brown Dwarf, 1: Red Dwarf, 2: White Dwarf, 3: Main Sequence, 4: Supergiant, 5: Hypergiant.
#
# # Note:
# The Luminosity and radius of each star is calculated w.r.t. that of the values of Sun.
# Lo = 3.828 x 10^26 Watts (Avg Luminosity of Sun)
# Ro = 6.9551 x 10^8 m (Avg Radius of Sun)'''"""
# qwen_vl_chat(user=user)
###--------test代码--------
# response,history=deepseek_chat(user="hello",history_message=[],system="You are a helpful assistant")
# response,history=gpt5_chat(user="hello",history_message=[],system="You are a helpful assistant")
# response,history=qwen_max_chat(user="hello",history_message=[],system="You are a helpful assistant")
# print(response)
#
# print(f"---------1111111----\n{response}\n---------------\n{history}\n------------")
#
# response,history=deepseek_chat(user="What's the highest people in the world?",history_message=history,system="You are a helpful assistant")
#
# print(f"---------2222222----\n{response}\n---------------\n{history}\n------------")
#
# response,history=deepseek_chat(user="What is the second?",history_message=history,system="You are a helpful assistant")
#
# print(f"---------333333----\n{response}\n---------------\n{history}\n------------")