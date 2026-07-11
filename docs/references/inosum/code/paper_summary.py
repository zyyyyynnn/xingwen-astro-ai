import re
import os
import json
import shutil
import traceback
from tqdm import tqdm
from LAG.config import call_deepseek_v3_2

LOG_FILE = r"C:\code\PaperSummary\log\token_usage.log"


# 将 token 使用情况和输入输出记录到日志文件
def log_token_usage(prompt, response, usage):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        log_entry = {
            "prompt": prompt,
            "response": response,
            "usage": {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens
            }
        }
        f.write(json.dumps(log_entry, ensure_ascii=False, indent=2) + "\n")
        f.write("-" * 50 + "\n")

def generate_with_llm(prompt):
    """统一封装：通过 DeepSeek 生成"""
    response = call_deepseek_v3_2(prompt)
    if response is None:
        return ""
    return response

# 读取文件
def read_md_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        return content
    except FileNotFoundError:
        print(f"文件 {file_path} 未找到")
    except Exception as e:
        print(f"读取文件时发生错误: {e}")

# 获取文章的背景
def extract_background(research_background_section):
    prompt = f"""
Please summarize the Research Background section of the paper based on the given input.
Please ensure the language is clear, logically coherent, and strictly based on the original text.Do not provide any extra explanation. Directly output the result in Markdown format.

Input:
{research_background_section}

Output format:
# Research Background
3–4 sentences summarizing the research field, existing challenges, and motivation for this study."""
    answer = generate_with_llm(prompt)
    return answer
# 获取文章方法论部分
def extract_methodology(methodology_section):
    prompt = f"""
Please summarize the Methodology section of the paper based on the given input.
Please ensure the language is clear, logically coherent, and strictly based on the original text.Do not provide any extra explanation. Directly output the result in Markdown format.

Input:
{methodology_section}

Output format:
# Methodology
- Overarching Goal of the method: One-sentence summary of the method’s overarching idea or goal.  
## Method Workflow
- [Module name] — [A brief summary of Core Objective and Key techniques used]   
// Add more as needed
## Key Formulas
If no formulas are found, return None.
- Formula: $LaTeX\ expression$
- Explanation: Brief explanation of purpose and variables
// Add more as needed"""
    answer = generate_with_llm(prompt)
    return answer
# 获取文章实验以及其结论
def extract_experiments_conclusion(experiments_section):
    prompt = f"""
Please summarize the Experiment Results section section of the paper based on the given input.
Please ensure the language is clear, logically coherent, and strictly based on the original text.Do not provide any extra explanation. Directly output the result in Markdown format.

Input:
{experiments_section}

Output format:
# Experiment Results
## Experiment 1
Experiment: A brief summary covering Purpose of validation, Experimental setup, Evaluation metrics.  
Conclusion: A brief summary of experiment conclusion. 
// Add more experiments as needed"""
    answer = generate_with_llm(prompt)
    return answer
# 获取数据集
def extract_dataset(dataset_section):
    prompt = f"""
Please summarize the Dataset section of the paper based on the given input.
Please ensure the language is clear, logically coherent, and strictly based on the original text.Do not provide any extra explanation. Directly output the result in Markdown format.

Input:
{dataset_section}

Output format:
# Datasets
## Dataset1
  Source:A brief summary of Dataset source  
  Description:A brief summary of data size, such as sample size, image size, division of training and testing sets, etc
// Add more as needed"""
    answer = generate_with_llm(prompt)
    return answer
# 获取文章讨论部分
def extract_discussion(discussion_section):
    prompt = f"""
Please summarize the Discussion section of the paper based on the given input.
Please ensure the language is clear, logically coherent, and strictly based on the original text.Do not provide any extra explanation. Directly output the result in Markdown format.

Input:
{discussion_section}

Output format:
# Discussion
4 to 5 sentences summarizing the core contributions, limitations, impacts, and future research directions. """
    answer = generate_with_llm(prompt)
    return answer
def extract_limitations(limitations_section):
    prompt = f"""
Please summarize the Limitations section of the paper based on the given input.
Please ensure the language is clear, logically coherent, and strictly based on the original text.Do not provide any extra explanation. Directly output the result in Markdown format.

Input:
{limitations_section}

Output format:
# Limitations
- List 3 to 6 key limitations as bullet points.
- Each point should be concise, clear, and strictly derived from the original text. """
    answer = generate_with_llm(prompt)
    return answer
def extract_questions(questions_section):
    prompt = f"""
Please summarize the Research Question section of the paper based on the given input.
Please ensure the language is clear, logically coherent, and strictly based on the original text.Do not provide any extra explanation. Directly output the result in Markdown format.

Input:
{questions_section}

Output format:
# Research Question
- List 3 to 6 key research question as bullet points.
- Each point should be concise, clear, and strictly derived from the original text. """
    answer = generate_with_llm(prompt)
    return answer

# 获取每个章节的分类
def get_splite_answer(splite_section):
    prompt = f"""
You are an expert in academic writing and research analysis. Your task is to classify multiple paragraphs from an engineering/construction-type research paper based on the predefined categories below.

### Steps:

1. Understand the Purpose of Each Paragraph
   Carefully read the title and corresponding content to identify the core focus of the paragraph.

2. Match Paragraph Content with Classification Criteria
Research Background (0): Introduces the engineering problem, research motivation, or related work.
Methodology (1): Describes system architecture, design framework, algorithm workflow, model construction, tools and technologies used; emphasizes how the method is implemented. Includes system design, algorithms, tools, and technical details.
Experiment (2): Describes experimental procedures, setup, performance testing, evaluation metrics, and results; emphasizes method validation and performance demonstration. Includes experiment design, execution, and result analysis.
Dataset (3): Data sources, scale, and selection criteria.
Discussion (4): Summarizes contributions, results, and future directions.
Limitations (5): Analyzes the weaknesses and constraints of the proposed method, such as assumptions, limited generalization, scalability issues, data dependency, or computational cost.
Research Questions (6): Highlights unresolved problems, key research questions, and future directions that require further investigation.

3. Handle Multiple Classifications
If a paragraph falls into multiple categories, return all applicable numbers separated by commas.

4. Output Requirements
   Output must be concise, accurate, and strictly based on the original content.
   Each paragraph title must be listed with its classification numbers.
   Do not include any explanations, notes, or extra formatting outside the classification list.

Input Format: The input is a JSON object, where each key is a paragraph title (e.g., "Abstract", "Introduction"), and the corresponding value is the text content under that title.
{splite_section}

Output Format:
ParagraphTitle: Number
ParagraphTitle: Number1,Number2
ParagraphTitle: Number
// Continue for all paragraphs

Example:
Abstract: 0
Introduction: 0
Data: 3
Experiment: 2,3"""

    answer = generate_with_llm(prompt)
    return answer

# 按照标题拆分markdown文件
def splite_paper_by_title(file_path, output_json):
    data = {}
    encodings = ['utf-8', 'gbk', 'iso-8859-1']

    # 读取文件内容，尝试多种编码
    for enc in encodings:
        try:
            with open(file_path, 'r', encoding=enc) as f:
                lines = f.readlines()
            break
        except UnicodeDecodeError:
            continue
    else:
        raise UnicodeDecodeError("无法用以下编码读取文件: " + str(encodings))

    current_title = None
    buffer = []

    for line in lines:
        # 如果遇到 References，停止处理
        if re.match(r"^#{1,6}\s*References\s*$", line.strip(), re.IGNORECASE):
            break

        heading_match = re.match(r'^(#{1,6})\s+(.*)', line)
        if heading_match:
            # 保存当前标题及其内容
            if current_title is not None:
                data[current_title] = ''.join(buffer).strip()
            current_title = heading_match.group(2).strip()
            buffer = []
        elif current_title is not None:
            buffer.append(line)

    # 处理最后一个标题的内容
    if current_title:
        data[current_title] = ''.join(buffer).strip()

    # 写入 JSON 文件
    with open(output_json, 'w', encoding='utf-8') as out_file:
        json.dump(data, out_file, ensure_ascii=False, indent=2)

# 根据内容拆分论文章节，支持标题规范化并跳过空内容
def splite_paper_by_content(title_paragraph_data, folder_path):
    """
    不再按词数拆分，直接整篇调用模型进行章节分类。
    """
    print("🚀 开始论文章节分类...")

    # 过滤空标题或内容
    title_paragraph_data = {k: v for k, v in title_paragraph_data.items() if v and str(v).strip()}

    # === 调用模型分类 ===
    answer_text = get_splite_answer(title_paragraph_data)

    # 保存分类结果
    os.makedirs(folder_path, exist_ok=True)
    md_path = os.path.join(folder_path, "classification_result.md")
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(answer_text.strip())

    # === 解析分类结果 ===
    raw_answer = {}
    for line in answer_text.strip().splitlines():
        if ':' in line:
            title, classes = line.split(':', 1)
            raw_answer[title.strip()] = classes.strip()

    section_to_index = {
        "Research Background": "0",
        "Methodology": "1",
        "Experiments": "2",
        "Dataset": "3",
        "Discussion": "4",
        "Limitations": "5",
        "Research Questions": "6",
    }

    index_to_content = {}
    for raw_title, index_str in raw_answer.items():
        content = title_paragraph_data.get(raw_title)
        if not content:
            continue
        for idx in [i.strip() for i in index_str.split(',') if i.strip()]:
            index_to_content.setdefault(idx, []).append(f"# {raw_title}\n{content}")

    splite_paper = {
        section: "\n".join(index_to_content.get(idx, []))
        for section, idx in section_to_index.items()
    }

    # 输出文件
    json_path = os.path.join(folder_path, 'splite_paper.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(splite_paper, f, ensure_ascii=False, indent=4)

    print(f"✅ 分类完成，结果已保存到：{json_path}")
    return splite_paper

# 判断论文是否存在标题
def has_markdown_title(markdown_text):
    """
    判断一个 Markdown 文本中是否包含 Markdown 标题。
    包括 # 语法 和 === / --- 下划线语法。
    """
    lines = markdown_text.strip().splitlines()

    for i, line in enumerate(lines):
        line = line.strip()

        # 方式 1：以 # 开头的标题
        if re.match(r'^#{1,6}\s+\S+', line):
            return True

        # 方式 2：下划线风格标题（至少2个=或-）
        if i < len(lines) - 1:
            next_line = lines[i + 1].strip()
            if re.match(r'^={2,}$', next_line) or re.match(r'^-{2,}$', next_line):
                return True

    return False

# 删除markdwon文件中的参考文献，作者等部分
def clean_markdown(text):
    lines = text.splitlines()

    # 模糊匹配这些结束标题，包含数字、空格等前缀
    end_patterns = [
        re.compile(r"#\s*\d*\s*ACKNOWLEDGEMENTS", re.IGNORECASE),
        re.compile(r"#\s*\d*\s*ACKNOWLEDGMENTS", re.IGNORECASE),
        re.compile(r"#\s*\d*\s*REFERENCES", re.IGNORECASE),
    ]

    # 查找截断结束点
    end_index = None
    for i, line in enumerate(lines):
        for pattern in end_patterns:
            if pattern.match(line.strip()):
                end_index = i
                break
        if end_index is not None:
            break

    if end_index is not None:
        lines = lines[:end_index]

    # 模糊匹配 ABSTRACT 或 INTRODUCTION 起点
    abstract_pattern = re.compile(r"#\s*\d*\.?\s*ABSTRACT", re.IGNORECASE)
    intro_pattern = re.compile(r"#\s*\d*\.?\s*INTRODUCTION", re.IGNORECASE)

    start_index = None
    for i, line in enumerate(lines):
        if abstract_pattern.match(line.strip()):
            start_index = i
            break

    if start_index is None:
        for i, line in enumerate(lines):
            if intro_pattern.match(line.strip()):
                start_index = i
                break

    if start_index is not None:
        lines = lines[start_index:]

    return '\n'.join(lines)

# ====================== STEP 1: 分类拆分 ======================
def step1_generate_single(md_file_path, temp_dir):
    """对单个 Markdown 文件执行分类拆分（Step 1）"""
    try:
        markdown_paper = read_md_file(md_file_path)

        if not markdown_paper:
            print(f"⚠️ 跳过（未读取到内容）: {md_file_path}")
            return False

        markdown_paper = clean_markdown(markdown_paper)

        full_md_path = os.path.join(temp_dir, "full.md")

        with open(full_md_path, "w", encoding="utf-8") as f:
            f.write(markdown_paper)

        # 判断是否有 Markdown 标题
        if not has_markdown_title(markdown_paper): #正则判断
            splite_paper = {
                "Research Background": markdown_paper,
                "Methodology": markdown_paper,
                "Experiments": markdown_paper,
                "Dataset": markdown_paper,
                "Discussion": markdown_paper,
                "Limitations": markdown_paper,
                "Research Questions": markdown_paper
            }
            with open(os.path.join(temp_dir, "splite_paper.json"), 'w', encoding='utf-8') as f:
                json.dump(splite_paper, f, ensure_ascii=False, indent=4)
        else:
            _ = splite_paper_by_title(
                full_md_path,
                os.path.join(temp_dir, "title_paragraph.json")
            )
            with open(os.path.join(temp_dir, "title_paragraph.json"), 'r', encoding='utf-8') as f:
                title_paragraph_data = json.load(f)

            splite_paper_by_content(title_paragraph_data, temp_dir)

        return True

    except Exception as e:
        print(f"❌ Step1 处理出错: {e}")
        traceback.print_exc()
        return False

# ====================== STEP 2: 合并与结果生成 ======================
def step2_generate_single(temp_dir, result_root, result_json_dir,paper_name):
    """
    Step 2: 对分类后的每个章节整章提取，无分块逻辑。
    """
    print(f"🚀 开始 Step 2：{paper_name}")

    try:
        splite_paper_path = os.path.join(temp_dir, "splite_paper.json")
        if not os.path.exists(splite_paper_path):
            print(f"⚠️ 文件不存在：{splite_paper_path}")
            return

        with open(splite_paper_path, "r", encoding="utf-8") as f:
            splite_paper_data = json.load(f)

        # === 整章提取 ===
        background_md  = extract_background(splite_paper_data.get("Research Background", "")) or "## Research Background\nNone"
        methodology_md = extract_methodology(splite_paper_data.get("Methodology", "")) or "## Methodology\nNone"
        dataset_md     = extract_dataset(splite_paper_data.get("Dataset", "")) or "## Dataset\nNone"
        experiments_md = extract_experiments_conclusion(splite_paper_data.get("Experiments", "")) or "## Experiments\nNone"
        discussion_md  = extract_discussion(splite_paper_data.get("Discussion", "")) or "## Discussion\nNone"

        limitations_md  = extract_limitations(splite_paper_data.get("Limitations", "")) or "## Limitations\nNone"
        questions_md  = extract_questions(splite_paper_data.get("Research Questions", "")) or "## Research Questions\nNone"


        # === 合并输出 ===
        combined_md = "\n\n".join([
            background_md,
            methodology_md,
            dataset_md,
            experiments_md,
            discussion_md,
            limitations_md,
            questions_md,
        ])


        os.makedirs(result_root, exist_ok=True)
        result_md_path = os.path.join(result_root, f"{paper_name}.md")
        with open(result_md_path, "w", encoding="utf-8") as f:
            f.write(combined_md)

        print(f"✅ Step 2 完成，结果已保存到：{result_md_path}")


        result_json_path = os.path.join(result_json_dir, f"{paper_name}.json")
        with open(result_json_path, "w", encoding="utf-8") as f:
            json.dump(
                markdown_h1_to_json(combined_md),
                f,
                ensure_ascii=False,
                indent=4
            )

        print(f"✅ Step 3 完成，结果Json形式已保存到：{result_json_path}")

    except Exception as e:
        print(f"❌ Step 2 出错：{e}")
        import traceback; traceback.print_exc()

# ====================== 主函数：逐篇执行 ======================
def process_md_files(md_files_dict, temp_root, result_root, result_json_dir, keep_temp=True):
    """依次处理每个 MD 文件：分类 -> 生成结果 -> 清理"""
    os.makedirs(temp_root, exist_ok=True)

    for md_file_key,md_file_value in tqdm(md_files_dict.items(), desc="论文处理进度", ncols=100):

        paper_name = md_file_key[:-4]
        md_path = md_file_value

        paper_temp_dir = os.path.join(temp_root, paper_name)
        os.makedirs(paper_temp_dir, exist_ok=True)
        print(f"\n🔹 正在处理: {paper_name}")

        # Step1 + Step2
        if step1_generate_single(md_path, paper_temp_dir):

            step2_generate_single(paper_temp_dir, result_root, result_json_dir,paper_name)

        # 清理临时目录
        if not keep_temp:
            shutil.rmtree(paper_temp_dir, ignore_errors=True)

    print(f"\n🎉 所有论文处理完成！结果已保存到：{result_root}")

def markdown_h1_to_json(md_text: str):
    # 匹配一级标题
    pattern = re.compile(r'^# (.+)', re.MULTILINE)

    result = {}
    matches = list(pattern.finditer(md_text))

    for i, match in enumerate(matches):
        title = match.group(1).strip()

        # 当前段起始位置（标题行结束）
        start = match.end()

        # 结束位置：下一个一级标题 or 文本结束
        end = matches[i + 1].start() if i + 1 < len(matches) else len(md_text)

        content = md_text[start:end].strip()

        result[title] = content

    return result


if __name__ == "__main__":
    md_files_dict={
        'One Example Shown, Many Concepts Known! Counterexample-Driven Conceptual Reasoning in Mathematical LLMs.pdf': '../paper_data/md\\One Example Shown, Many Concepts Known! Counterexample-Driven Conceptual Reasoning in Mathematical LLMs.md',
        'STEERING LARGE LANGUAGE MODELS BETWEEN CODE EXECUTION AND TEXTUAL REASONING.pdf': '../paper_data/md\\STEERING LARGE LANGUAGE MODELS BETWEEN CODE EXECUTION AND TEXTUAL REASONING.md',
        'Unveiling the power of multimodal large language models for radio astronomical image understanding and question answering.pdf': '../paper_data/md\\Unveiling the power of multimodal large language models for radio astronomical image understanding and question answering.md',
        # 'The adverse effects of code duplication in machine learning models of code.pdf': '../paper_data/md\\The adverse effects of code duplication in machine learning models of code.md'
    }

    model = "deepseek"
    md_dir = r"/LAG/paper_data/md"
    output_root = fr"C:\Users\10412\Desktop\多模态大语言模型\Code\天文Code\LAG\paper_data\papersummary\{model}"

    os.makedirs(output_root, exist_ok=True)

    # 路径配置
    temp_dir = os.path.join(output_root, "_tmp_processing")
    result_dir = os.path.join(output_root, f"_result")
    result_json_dir = os.path.join(output_root, f"_json_result")
    os.makedirs(result_dir, exist_ok=True)
    os.makedirs(result_json_dir, exist_ok=True)

    process_md_files(md_files_dict, temp_dir, result_dir,result_json_dir, keep_temp=True)

