# 参考资料

本目录存放赛题原文与第三方研究资料。所有内容均为**非规范性参考**，不能覆盖 `PRD.md`、`DESIGN.md`、架构文档、当前源码或验收证据。

## 目录结构

```
docs/references/
├── README.md           # 本文件
├── 赛题要求.md         # 赛题整理版全文
├── papers/             # 三份论文 PDF（共 8.4MB）
│   ├── AutoAstro-天文自动化实验框架.pdf
│   ├── mavis-天文可视化工具.pdf
│   └── InnoSum-摘要质量指标构建.pdf
├── autoastro/          # 功能一：AutoAstro 参考
│   ├── 摘要.md         # 开发参考卡（架构与接口观察）
│   └── code/          # 12 个核心 .py 文件
├── mavis/              # 功能二：mavis 参考
│   ├── 摘要.md         # 开发参考卡
│   └── api/           # 11 个天文工具 API JSON
└── inosum/             # 功能三：InnoSum 参考
    ├── 摘要.md         # 开发参考卡
    └── code/          # 论文解析代码 paper_summary.py
```

## 三份参考资料与项目模块的映射

| 参考资料  | 对应模块                  | 岗位     | 核心复用点                                          |
| --------- | ------------------------- | -------- | --------------------------------------------------- |
| AutoAstro | `services/data_pipeline`  | C-夏铭灿 | 数据交叉匹配、LLM 任务推荐与分解、分析代码自动配置  |
| mavis     | `services/graph_pipeline` | D-梁津浩 | 天文工具 API 封装模式、任务分解结构、WWT 可视化集成 |
| InnoSum   | `services/paper_pipeline` | D-梁津浩 | 论文章节分类、结构化摘要提取、摘要质量评估          |

## Qwen 适配说明

三份参考代码均使用 DeepSeek V3，赛题要求 Qwen 系列 + 阿里云百炼平台。迁移方式统一：OpenAI 兼容模式，只改 `base_url`（`https://dashscope.aliyuncs.com/compatible-mode/v1`）、`api_key`（`DASHSCOPE_API_KEY`）和 `model`（`qwen-plus` 或 `qwen-max`），Prompt 和工具调用代码不用改。

## 未保留的原始文件

以下文件因体积过大或已提取关键内容，未纳入仓库：

- 功能一-参考代码.zip（2.5MB，核心 .py 已提取到 autoastro/code/）
- 功能二-参考代码.zip（372MB，API JSON 已提取到 mavis/api/；JPL 星历表和 benchmark 数据未保留）
- 星文智析_开发分工表.docx（内容已在 AGENTS.md 第 5 节和 BACKLOG.md 中）
- 星文智析_项目简报.docx（阶段性管理信息不作为当前工程规范）
- 申报记录.png（报名审核截图，状态已在简报中记录）
