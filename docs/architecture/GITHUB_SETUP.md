# GitHub Setup

## 1. 推荐仓库名

推荐：

```text
xingwen-astro-ai
```

备选：

```text
xingwen-ai-research-tool
astro-research-ai
```

## 2. 推荐仓库设置

- Owner：`zyyyyynnn`
- Visibility：初期建议 Private，提交前再按要求决定是否公开
- Default branch：`main`
- Issues：开启
- Projects：开启
- Pull Requests：开启
- Wiki：可不开启

## 3. 分支保护建议

`main` 分支建议开启：

- Require a pull request before merging
- Require approvals: 1
- Require conversation resolution before merging
- Require status checks to pass before merging
- Do not allow force pushes

## 4. Labels 建议

| Label | 用途 |
| --- | --- |
| `area:frontend` | 前端 |
| `area:backend` | 后端 |
| `area:data` | 数据分析 |
| `area:paper` | 文献总结 |
| `area:graph` | 学术图谱 |
| `area:docs` | 文档 |
| `priority:p0` | 必须完成 |
| `priority:p1` | 重要 |
| `priority:p2` | 可延后 |
| `type:feature` | 新功能 |
| `type:bug` | 缺陷 |
| `type:chore` | 工程任务 |

## 5. Milestones 建议

- M0 Repository Foundation
- M1 Skeleton and API
- M2 Data Pipeline
- M3 Paper Summary
- M4 Academic Graph
- M5 Public Demo
