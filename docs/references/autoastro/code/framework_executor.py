#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time : 2025/3/11 14:47
# @Author : 桐
# @QQ:1041264242
# 注意事项：
import json
import os
import subprocess
from llm_api import deepseek_chat
from analyze import visual_analyze_png,data_analyze_md,linking_insight,update_node_content,task_eval,subtask_decompose,insert_history_tree
from error_correction import code_correction,check_for_none
from prompt import vis_prompt,data_prompt,train_prompt,self_model_prompt,image_cls_model_prompt,sub_vis_prompt,sub_data_prompt,sub_train_prompt
from client import submit_code_selfmodel,submit_code_mmpre
from AutoAstro.model.self_model.ts_model_example import select_model_code
from tools import parse_execution_order,extract_code,extract_json

SERVER_ADRESS="http://210.40.16.205:30369"
PYTHON_PATH=r'C:\Users\10412\.conda\envs\AutoAstro\python.exe'

def deep_learning_executor(data_intr,fold_path,requirements,pre_execute_task,mm_example,history_json_path):
    print(f"\033[92m Info | 执行Step4: 开始执行任务。\033[0m")

    for task in pre_execute_task:
        index=task['task_id']

        try:
            print(f"\033[93m    Info | 执行子任务: 构建模型配置\033[0m")

            with open(mm_example, 'r', encoding='utf-8') as file:
                models = json.load(file)

            model_des = models[task['type']]

            image_cls_model_execute_prompt = image_cls_model_prompt(requirements,models,data_intr,task['type'])
            print(image_cls_model_execute_prompt)

            # print(image_cls_model_execute_prompt)
            sm_answer, history = deepseek_chat(user=image_cls_model_execute_prompt, history_message=[], system="")
            print(sm_answer)

            auto_config = extract_json(sm_answer)

            configuration = None
            for select_model in model_des:
                if select_model["Model"] == auto_config["model"]:
                    # print(select_model)
                    configuration = {
                        "framework": {
                            "template": task['type'],
                            "config": select_model["Config"],
                            "pre_weights": select_model["Download"]
                        },
                        "data_name": data_intr['data_name'],
                        "load_path": data_intr['load_path'],
                        "num_classes": auto_config["num_classes"],
                        "classes": auto_config["classes"]
                    }
                    update_node_content(target_id=task['task_id'], new_content={"explanation": auto_config["explanation"]},history_json=history_json_path)

            print(configuration)

            # 确保目录存在
            os.makedirs(fr"{fold_path}\sub_task{index}", exist_ok=True)  # Create the directory if it doesn't exist
            submit_code_mmpre(SERVER_ADRESS, json.dumps(configuration), save_path=fr"{fold_path}\sub_task{index}")
            update_node_content(target_id=task['task_id'], new_content={"done": True}, history_json=history_json_path)
            print(f"\033[92m    Success | 执行子任务任务ID_{task['task_id']}, 执行成功\033[0m")

        except Exception as e:
            print(f"发生了异常：{e}")
            print(f"\033[91m    Info | 执行子任务任务ID_{task['task_id']}, 执行失败\033[0m")

def self_model_executor(data_intr,fold_path,requirements,data_summary,pre_execute_task,history_json_path,save_path):

    print(f"\033[92m Info | 执行Step4: 开始执行任务。\033[0m")
    # print(pre_execute_task)
    for data in pre_execute_task:
        # print(data['task_id'])
        index = data['task_id']

        try:
            execute=data['task']

            if execute["task_type"] != "other":
                print(f"\033[93m    Info | 执行子任务任务ID_{index}:时序深度学习模型训练\033[0m")
                self_model_execute_prompt = self_model_prompt(execute["task_description"], data_intr["task_describe"], data_summary, execute["explanation"], execute["selected_columns"], data_intr["data_name"]+".csv", execute["task_type"])
                print(self_model_execute_prompt)

                sm_answer, history = deepseek_chat(user=self_model_execute_prompt, history_message=[], system="")
                print(sm_answer)

                generate_code = extract_code(text=sm_answer)
                execute_code = select_model_code(main_code=generate_code, type=execute["task_type"], data=data_intr["data_name"]+".csv")
                # 确保目录存在
                os.makedirs(fr"{fold_path}\sub_task{index}", exist_ok=True)  # Create the directory if it doesn't exist
                submit_code_selfmodel(SERVER_ADRESS, execute_code, save_path=fr"{fold_path}\sub_task{index}")

                update_node_content(target_id=data['task_id'], new_content={"done": True}, history_json=history_json_path)
                print(f"\033[92m    Success | 执行子任务任务ID_{data['task_id']}, 执行成功\033[0m")

            else:
                print(f"\033[93m    Info | 执行子任务任务{index}:可视化代码生成\033[0m")
                vis_execute_prompt = vis_prompt(execute["task_description"], data_intr["task_describe"], data_summary, execute["explanation"], execute["selected_columns"])

                print(vis_execute_prompt)
                vis_answer, history = deepseek_chat(user=vis_execute_prompt, history_message=[], system="")
                print(vis_answer)

                if check_for_none(vis_answer):
                    print(f"\033[93m    Info | 执行子任务任务ID_{index}:无需进行可视化分析\033[0m")
                else:
                    pre_vis_code = extract_code(text=vis_answer) + f"""
df = pd.read_csv(r"{save_path}")
final_chart=execute(df)
# final_chart.save(r'{fold_path}/sub_task{index}.html', embed_options={{'renderer':'svg'}})
# final_chart.save(r'{fold_path}/sub_task{index}.png')
final_chart.savefig(r'{fold_path}/sub_task{index}.png')
plt.close(final_chart)"""
                    vis_erro = write_and_execute(code=pre_vis_code, file_path=fr"{fold_path}/sub_task{index}_viscode_executor.py", column=execute["selected_columns"])
                    print(vis_erro)

                print(f"\033[93m    Info | 执行子任务任务ID_{index}:数据分析代码生成\033[0m")
                # 数据分析代码生成
                data_execute_prompt = data_prompt(execute["task_description"], data_intr["task_describe"], data_summary, execute["explanation"], execute["selected_columns"])

                dat_answer, history = deepseek_chat(user=data_execute_prompt, history_message=[], system="")
                print(dat_answer)

                if check_for_none(dat_answer):
                    print(f"\033[93m    Info | 执行子任务任务ID_{index}:无需进行数据分析\033[0m")
                else:
                    pre_dat_code = extract_code(text=dat_answer) + f"""
pd.set_option('display.max_rows', 10)  # 显示所有行
pd.set_option('display.max_columns', 10)  # 显示所有列
#pd.set_option('display.width', 1000)  # 设置输出宽度
pd.set_option('display.max_colwidth', None)  # 取消列内容截断
df = pd.read_csv(r"{save_path}")
results=execute(df)
result_shown=""
index=0
for key, value in results.items():
    index+=1
    result_shown+=f"{{index}}. **{{key}}**:\\n{{value}}\\n\\n"

with open(r'{fold_path}/sub_code_task{index}.md', "w", encoding="utf-8") as md_file:
    md_file.write(result_shown)"""
                    dat_erro = write_and_execute(code=pre_dat_code, file_path=fr"{fold_path}/sub_task{index}_datcode_executor.py", column=execute["selected_columns"])
                    print(dat_erro)

                if check_for_none(vis_answer):
                    print(f"\033[93m    Info | 执行子任务任务ID_{index}:无需进行可视化分析\033[0m")
                else:
                    print(f"\033[93m    Info | 执行子任务任务ID_{index}:可视化分析\033[0m")
                    #可视化分析
                    visual_analyze_result=visual_analyze_png(execute["task_description"],data_intr["task_describe"],fr'{fold_path}/sub_task{index}.png')


                if check_for_none(dat_answer):
                    print(f"\033[93m    Info | 执行子任务任务ID_{index}:无需进行数据分析\033[0m")
                else:
                    print(f"\033[93m    Info | 执行子任务任务ID_{index}:数据分析\033[0m")
                    #数据分析
                    data_analyze_result = data_analyze_md(execute["task_description"], data_intr["task_describe"],fr'{fold_path}/sub_code_task{index}.md')

                print(f"\033[93m    Info | 执行子任务任务ID_{index}:中间过程分析结果写入\033[0m")
                # 假设指定的 Markdown 文件路径为 output_path
                md_output_path = fr"{fold_path}/sub_sum_ori_task{index}.md"
                # 打开或创建 Markdown 文件
                with open(md_output_path, 'a', encoding='utf-8') as md_file:

                    if check_for_none(vis_answer) == False:
                        # 写入图像分析结果
                        image_markdown = fr"![sub_task{index}]({fold_path}/sub_task{index}.png)"
                        md_file.write("# visual_analyze_result\n" + image_markdown + "\n\n")
                        md_file.write(visual_analyze_result + "\n\n")

                    if check_for_none(dat_answer) == False:
                        # 写入数据分析结果
                        md_file.write("# data_analyze_result\n" + data_analyze_result + "\n\n")

                if check_for_none(vis_answer) == False and check_for_none(dat_answer) == False:
                    print(f"\033[93m    Info | 执行子任务任务{index}:子任务结果整合\033[0m")
                    visual_insight = "# visual_analyze_result\n" + image_markdown + "\n\n" + visual_analyze_result + "\n\n"
                    data_insight = "# data_analyze_result\n" + data_analyze_result + "\n\n"
                    answer = linking_insight(execute["task_description"], visual_insight, data_insight)
                    with open(fr"{fold_path}/sub_sum_norm_task{index}.md", 'a', encoding='utf-8') as md_file:
                        md_file.write(answer)

                update_node_content(target_id=data['task_id'], new_content={"done": True}, history_json=history_json_path)
                print(f"\033[92m    Success | 执行子任务任务ID_{data['task_id']}, 执行成功\033[0m")

        except Exception as e:
            print(f"发生了异常：{e}")
            print(f"\033[91m    Info | 执行子任务任务ID_{data['task_id']}, 执行失败\033[0m")

def machine_learning_executor(data_intr,fold_path,requirements,data_summary,pre_execute_task,history_json_path,save_path):


    print(f"\033[92m Info | 执行Step4: 开始执行任务。\033[0m")

    for data in pre_execute_task:
        index=data['task_id']
        try:
            execute=data['task']

            print(f"\033[93m    Info | 执行子任务任务ID_{index}:可视化代码生成\033[0m")

            vis_execute_prompt = vis_prompt(execute["task_description"],data_intr["task_describe"],data_summary,execute["explanation"],execute["selected_columns"])

            print(vis_execute_prompt)
            vis_answer, history = deepseek_chat(user=vis_execute_prompt, history_message=[], system="")
            print(vis_answer)

            if check_for_none(vis_answer):
                print(f"\033[93m    Info | 执行子任务任务ID_{index}:无需进行可视化分析\033[0m")
            else:
                pre_vis_code=extract_code(text=vis_answer)+f"""
df = pd.read_csv(r"{save_path}")
final_chart=execute(df)
# final_chart.save(r'{fold_path}/sub_task{index}.html', embed_options={{'renderer':'svg'}})
# final_chart.save(r'{fold_path}/sub_task{index}.png')
final_chart.savefig(r'{fold_path}/sub_task{index}.png')
plt.close(final_chart)"""
                vis_erro = write_and_execute(code=pre_vis_code, file_path=fr"{fold_path}/sub_task{index}_viscode_executor.py", column=execute["selected_columns"])
                print(vis_erro )


            print(f"\033[93m    Info | 执行子任务任务ID_{index}:数据分析代码生成\033[0m")
            #数据分析代码生成
            data_execute_prompt = data_prompt(execute["task_description"],data_intr["task_describe"],data_summary,execute["explanation"],execute["selected_columns"])

            dat_answer, history = deepseek_chat(user=data_execute_prompt, history_message=[], system="")
            print(dat_answer)
            if check_for_none(dat_answer):
                print(f"\033[93m    Info | 执行子任务任务ID_{index}:无需进行数据分析\033[0m")
            else:
                pre_dat_code = extract_code(text=dat_answer) + f"""
pd.set_option('display.max_rows', 10)  # 显示所有行
pd.set_option('display.max_columns', 10)  # 显示所有列
#pd.set_option('display.width', 1000)  # 设置输出宽度
pd.set_option('display.max_colwidth', None)  # 取消列内容截断
df = pd.read_csv(r"{save_path}")
results=execute(df)
result_shown=""
index=0
for key, value in results.items():
    index+=1
    result_shown+=f"{{index}}. **{{key}}**:\\n{{value}}\\n\\n"
    
with open(r'{fold_path}/sub_code_task{index}.md', "w", encoding="utf-8") as md_file:
    md_file.write(result_shown)"""
                dat_erro = write_and_execute(code=pre_dat_code, file_path=fr"{fold_path}/sub_task{index}_datcode_executor.py", column=execute["selected_columns"])
                print(dat_erro)


            print(f"\033[93m    Info | 执行子任务任务ID_{index}:模型训练代码生成\033[0m")
            # 确保目录存在
            os.makedirs(fr"{fold_path}\img", exist_ok=True)  # Create the directory if it doesn't exist

            #训练模型代码生成
            train_execute_prompt = train_prompt(execute["task_description"],data_intr["task_describe"],data_summary,execute["explanation"],execute["selected_columns"],fold_path)

            train_answer, history = deepseek_chat(user=train_execute_prompt, history_message=[], system="")
            print(train_answer)


            if check_for_none(train_answer):
                print(f"\033[93m    Info | 执行子任务任务ID_{index}:无需进行模型训练\033[0m")
            else:
                pre_tra_code = extract_code(text=train_answer)+f"""
df = pd.read_csv(r"{save_path}")
results=execute(df)
index=0
result_shown=""
for key, value in results.items():
    index+=1
    result_shown+=f"{{index}}. **{{key}}**:\\n{{value}}\\n\\n"
with open(r'{fold_path}/sub_tra_task{index}.md', "w", encoding="utf-8") as md_file:
    md_file.write(result_shown)"""
                # print(pre_tra_code)
                tra_erro = write_and_execute(code=pre_tra_code, file_path=fr"{fold_path}/sub_task{index}_tracode_executor.py", column=execute["selected_columns"])
                print(tra_erro)

            if check_for_none(vis_answer):
                print(f"\033[93m    Info | 执行子任务任务ID_{index}:无需进行可视化分析\033[0m")
            else:
                print(f"\033[93m    Info | 执行子任务任务ID_{index}:可视化分析\033[0m")
                #可视化分析
                visual_analyze_result=visual_analyze_png(execute["task_description"],data_intr["task_describe"],fr'{fold_path}/sub_task{index}.png')


            if check_for_none(dat_answer):
                print(f"\033[93m    Info | 执行子任务任务ID_{index}:无需进行数据分析\033[0m")
            else:
                print(f"\033[93m    Info | 执行子任务任务ID_{index}:数据分析\033[0m")
                #数据分析
                data_analyze_result = data_analyze_md(execute["task_description"], data_intr["task_describe"],fr'{fold_path}/sub_code_task{index}.md')


            print(f"\033[93m    Info | 执行子任务任务ID_{index}:中间过程分析结果写入\033[0m")
            # 假设指定的 Markdown 文件路径为 output_path
            md_output_path = fr"{fold_path}/sub_sum_ori_task{index}.md"
            # 打开或创建 Markdown 文件
            with open(md_output_path, 'a', encoding='utf-8') as md_file:

                if check_for_none(vis_answer)==False:
                    # 写入图像分析结果
                    image_markdown = fr"![sub_task{index}]({fold_path}/sub_task{index}.png)"
                    md_file.write("# visual_analyze_result\n"+image_markdown + "\n\n")
                    md_file.write(visual_analyze_result + "\n\n")
                    answer=visual_analyze_result

                if check_for_none(dat_answer)==False:
                    # 写入数据分析结果
                    md_file.write("# data_analyze_result\n" + data_analyze_result + "\n\n")
                    answer=data_analyze_result

            if check_for_none(vis_answer)==False and check_for_none(dat_answer)==False:
                print(f"\033[93m    Info | 执行子任务任务ID_{index}:子任务结果整合\033[0m")
                visual_insight = "# visual_analyze_result\n" + image_markdown + "\n\n" + visual_analyze_result + "\n\n"
                data_insight = "# data_analyze_result\n" + data_analyze_result + "\n\n"
                answer=linking_insight(execute["task_description"],visual_insight,data_insight)
                with open(fr"{fold_path}/sub_sum_norm_task{index}.md", 'a', encoding='utf-8') as md_file:
                    md_file.write(answer)

            if check_for_none(train_answer)==0:
                try:
                    eval_answer = task_eval(requirements=requirements, task=execute["task_description"], insight=answer,column=execute["selected_columns"])
                    eval_result = extract_json(text=eval_answer)
                    update_node_content(target_id=data['task_id'], new_content={"done": True},history_json=history_json_path)
                    print(f"\033[92m    Success | 执行子任务任务ID_{data['task_id']}, 执行成功\033[0m")
                except:
                    print(f"\033[92m    Success | 执行子任务任务ID_{data['task_id']}, 执行成功\033[0m")
            else:
                eval_answer = task_eval(requirements=requirements, task=execute["task_description"], insight=answer, column=execute["selected_columns"])
                eval_result = extract_json(text=eval_answer)
                update_node_content(target_id=data['task_id'],new_content={"done":True}, history_json=history_json_path)
                print(f"\033[92m    Success | 执行子任务任务ID_{data['task_id']}, 执行成功\033[0m")

            # usedcolumn = ""
            # # 以标准的格式输出表头及其对应的数据类型
            # for col in execute["selected_columns"]:
            #     usedcolumn += f"('{col['column_name']}','{col['column_type']}');"
            # subtask_answer = subtask_decompose(requirements=requirements,task=execute["task_description"],usedcolumn=usedcolumn,data=data_intr["task_describe"],insight=answer,score=eval_result['score'],reasons=eval_result['explanation'])
            # subtask_result = extract_json(text=subtask_answer)
            #
            # # 询问用户是否执行代码
            # user_choice = input(f"\033[92m Info | 执行Step5: 当前推荐子任务为{subtask_result}\n是否要执行子任务分解？(y/n): \033[0m")
            # if user_choice.lower() == 'y':
            #     subtask_execution(data['task_id'], subtask_result, data_intr, fold_path, requirements, history_json_path, save_path)

        except Exception as e:
            print(f"发生了异常：{e}")
            print(f"\033[91m    Info | 执行子任务任务ID_{data['task_id']}, 执行失败\033[0m")
        # break

def subtask_execution(pre_id,subtask_result,data_intr,fold_path,requirements,history_json_path,save_path):
    print(subtask_result)

    orders = parse_execution_order(subtask_result['execution order'])

    sub_temp = []
    for index, order in enumerate(orders):
        for sub_index in order:
            # 读取 JSON 文件
            with open(history_json_path, 'r', encoding='utf-8') as file:
                node = json.load(file)

            new_data = {
                "id": node['total']+1,
                "task": subtask_result["tasks"][sub_index],
                "explanation": "",
                "type": subtask_result["task type"][sub_index],
                "done": False,
                "children": [],
            }

            #插入子任务
            if index==0:
                insert_history_tree(target_id=pre_id, new_data=new_data, history_json=history_json_path)
            else:
                for data in sub_temp:
                    insert_history_tree(target_id=data["id"], new_data=new_data, history_json=history_json_path)

            #任务执行
            try:

                print(f"\033[93m    Info | 执行原任务ID_{pre_id}的分解任务ID_{new_data['id']}:可视化代码生成\033[0m")
                vis_execute_prompt = sub_vis_prompt(new_data["task"], data_intr["task_describe"], subtask_result["data variables"][sub_index])
                print(vis_execute_prompt)
                vis_answer, history = deepseek_chat(user=vis_execute_prompt, history_message=[], system="")
                print(vis_answer)
                if check_for_none(vis_answer):
                    print(f"\033[93m    Info | 执行原任务ID_{pre_id}的分解任务ID_{new_data['id']}:无需进行可视化分析\033[0m")
                else:
                    pre_vis_code = extract_code(text=vis_answer) + f"""
df = pd.read_csv(r"{save_path}")
final_chart=execute(df)
# final_chart.save(r'{fold_path}/sub_task{new_data['id']}.html', embed_options={{'renderer':'svg'}})
# final_chart.save(r'{fold_path}/sub_task{new_data['id']}.png')
final_chart.savefig(r'{fold_path}/sub_task{new_data['id']}.png')
plt.close(final_chart)"""
                    vis_erro = write_and_execute(code=pre_vis_code,
                                                 file_path=fr"{fold_path}/sub_task{new_data['id']}_viscode_executor.py",
                                                 column=subtask_result["data variables"][sub_index])
                    print(vis_erro)


                print(f"\033[93m    Info | 执行原任务ID_{pre_id}的分解任务ID_{new_data['id']}:数据分析代码生成\033[0m")
                # 数据分析代码生成
                data_execute_prompt = sub_data_prompt(new_data["task"], data_intr["task_describe"], subtask_result["data variables"][sub_index])
                dat_answer, history = deepseek_chat(user=data_execute_prompt, history_message=[], system="")
                print(dat_answer)
                if check_for_none(dat_answer):
                    print(f"\033[93m    Info | 执行原任务ID_{pre_id}的分解任务ID_{new_data['id']}:无需进行数据分析\033[0m")
                else:
                    pre_dat_code = extract_code(text=dat_answer) + f"""
pd.set_option('display.max_rows', 10)  # 显示所有行
pd.set_option('display.max_columns', 10)  # 显示所有列
#pd.set_option('display.width', 1000)  # 设置输出宽度
pd.set_option('display.max_colwidth', None)  # 取消列内容截断
df = pd.read_csv(r"{save_path}")
results=execute(df)
result_shown=""
index=0
for key, value in results.items():
    index+=1
    result_shown+=f"{{index}}. **{{key}}**:\\n{{value}}\\n\\n"

with open(r'{fold_path}/sub_code_task{new_data['id']}.md', "w", encoding="utf-8") as md_file:
    md_file.write(result_shown)"""
                    dat_erro = write_and_execute(code=pre_dat_code,
                                                 file_path=fr"{fold_path}/sub_task{new_data['id']}_datcode_executor.py",
                                                 column=subtask_result["data variables"][sub_index])
                    print(dat_erro)


                print(f"\033[93m    Info | 执行原任务ID_{pre_id}的分解任务ID_{new_data['id']}:模型训练代码生成\033[0m")
                # 训练模型代码生成
                train_execute_prompt = sub_train_prompt(new_data["task"], data_intr["task_describe"], subtask_result["data variables"][sub_index], fold_path)
                train_answer, history = deepseek_chat(user=train_execute_prompt, history_message=[], system="")
                print(train_answer)
                if check_for_none(train_answer):
                    print(f"\033[93m    Info | 执行原任务ID_{pre_id}的分解任务ID_{new_data['id']}:无需进行模型训练\033[0m")
                else:
                    pre_tra_code = extract_code(text=train_answer) + f"""
df = pd.read_csv(r"{save_path}")
results=execute(df)
index=0
result_shown=""
for key, value in results.items():
    index+=1
    result_shown+=f"{{index}}. **{{key}}**:\\n{{value}}\\n\\n"
with open(r'{fold_path}/sub_tra_task{new_data['id']}.md', "w", encoding="utf-8") as md_file:
    md_file.write(result_shown)"""

                    tra_erro = write_and_execute(code=pre_tra_code,
                                                 file_path=fr"{fold_path}/sub_task{new_data['id']}_tracode_executor.py",
                                                 column=subtask_result["data variables"][sub_index])
                    print(tra_erro)

                if check_for_none(vis_answer):
                    print(f"\033[93m    Info | 执行原任务ID_{pre_id}的分解任务ID_{new_data['id']}:无需进行可视化分析\033[0m")
                else:
                    print(f"\033[93m    Info | 执行原任务ID_{pre_id}的分解任务ID_{new_data['id']}:可视化分析\033[0m")
                    # 可视化分析
                    visual_analyze_result = visual_analyze_png(new_data["task"], data_intr["task_describe"], fr"{fold_path}/sub_task{new_data['id']}.png")
                if check_for_none(dat_answer):
                    print(f"\033[93m    Info | 执行原任务ID_{pre_id}的分解任务ID_{new_data['id']}:无需进行数据分析\033[0m")
                else:
                    print(f"\033[93m    Info | 执行原任务ID_{pre_id}的分解任务ID_{new_data['id']}:数据分析\033[0m")
                    # 数据分析
                    data_analyze_result = data_analyze_md(new_data["task"], data_intr["task_describe"],fr"{fold_path}/sub_code_task{new_data['id']}.md")

                print(f"\033[93m    Info | 执行原任务ID_{pre_id}的分解任务ID_{new_data['id']}:中间过程分析结果写入\033[0m")
                # 假设指定的 Markdown 文件路径为 output_path
                md_output_path = fr"{fold_path}/sub_sum_ori_task{new_data['id']}.md"
                # 打开或创建 Markdown 文件
                with open(md_output_path, 'a', encoding='utf-8') as md_file:

                    if check_for_none(vis_answer) == False:
                        # 写入图像分析结果
                        image_markdown = fr"![sub_task{new_data['id']}]({fold_path}/sub_task{new_data['id']}.png)"
                        md_file.write("# visual_analyze_result\n" + image_markdown + "\n\n")
                        md_file.write(visual_analyze_result + "\n\n")

                    if check_for_none(dat_answer) == False:
                        # 写入数据分析结果
                        md_file.write("# data_analyze_result\n" + data_analyze_result + "\n\n")

                if check_for_none(vis_answer) == False and check_for_none(dat_answer) == False:
                    print(f"\033[93m    Info | 执行原任务ID_{pre_id}的分解任务ID_{new_data['id']}:子任务结果整合\033[0m")
                    visual_insight = "# visual_analyze_result\n" + image_markdown + "\n\n" + visual_analyze_result + "\n\n"
                    data_insight = "# data_analyze_result\n" + data_analyze_result + "\n\n"
                    sub_insight = linking_insight(new_data["task"], visual_insight, data_insight)
                    with open(fr"{fold_path}/sub_sum_norm_task{new_data['id']}.md", 'a', encoding='utf-8') as md_file:
                        md_file.write(sub_insight)

                if index == 0:
                    sub_temp.append({"id": new_data["id"], "insight": sub_insight})

                eval_answer = task_eval(requirements=requirements, task=new_data["task"], insight=sub_insight, column=subtask_result["data variables"][sub_index])
                eval_result = extract_json(text=eval_answer)
                print(eval_result)

                update_node_content(target_id=new_data['id'], new_content={"done": True}, history_json=history_json_path)
                print(f"\033[92m    Success | 执行原任务ID_{pre_id}的分解任务ID_{new_data['id']}, 执行成功\033[0m")

            except Exception as e:
                print(f"发生了异常：{e}")
                print(f"\033[91m    Info | 执行原任务ID_{pre_id}的分解任务ID_{new_data['id']}, 执行失败\033[0m")


    print(sub_temp)

    # print(subtask_result)
    # print("--------------------------------------------------")
    # print(data_intr)
    pass


#代码执行
def write_and_execute(code: str, file_path: str, column: str):
    max_attempts = 3  # 最大尝试修正次数
    attempt = 0

    while attempt < max_attempts:
        try:
            # 写入代码到指定文件
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(code)

            # 执行该 Python 文件
            result = subprocess.run([PYTHON_PATH, file_path], capture_output=True, text=True, encoding="utf-8", errors="replace")

            # 检查是否有错误
            if result.returncode != 0:
                # 如果执行失败，调用修正函数
                print(f"erro: {result.stderr}")
                code = code_correction(result.stderr, code, column)
                attempt += 1
            else:
                # 执行成功，返回结果
                return f"Execution succeeded: {result.stdout} attempts:{attempt}"
        except Exception as e:
            # 捕获其他异常，调用修正函数
            code = code_correction(str(e), code, column)
            attempt += 1

    # 如果超过最大尝试次数仍然失败，返回报错异常
    return f"Execution failed after {max_attempts} attempts: {result.stderr if 'result' in locals() else str(e)}"




# 可视化分析代码生成
#             vis_execute_prompt=f"""# Instruction
# According to whether the current task needs to perform a visual analysis, make the following decision:
# - If no visual analysis is needed in the task description (e.g., only train the model or perform statistical analysis on the data), return `Over`, and do not return any other values.
# - If visual analysis is needed in the task description, proceed to write Python code to analyze the data and solve this task. After finishing the data analysis, use Altair to generate an interactive visualization. Add a brush function, tooltip, and legend if different colors are used. Ensure that each generated visualization has a brush function that allows you to select a subset of the data. Please ensure that only one view is generated. No combination of views is required. If the dataset is large, use stratified sampling by category to ensure representativeness, keeping the total sample size ≤ 1000 for efficient and clear visualization.
#
#
# # User Input
# - Task description: {execute["task_description"]}
# - Data description: '''{data_intr["task_describe"]}'''
# - Data summary: {data_summary}
# - Task explanation: {execute["explanation"]}
# - Selected columns: {execute["selected_columns"]}
# - Data Volume
#
# # Output Example
# ```python
# import pandas as pd
# import altair as alt
# def execute(data: pd.DataFrame):
#     # Data preprocessing
#          <codes>
#     # Chart generation
#     chart = alt.Chart().mark_bar().encode().properties()
#     return chart
# ```"""
