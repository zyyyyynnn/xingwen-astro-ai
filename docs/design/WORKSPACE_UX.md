# Research Workspace UX

| 元数据    | 值                                     |
| --------- | -------------------------------------- |
| Authority | Workspace 信息架构、页面状态与核心交互 |

本文定义 Research Workspace 的产品合同，不规定具体上游产品、源码目录或实现技术。

`/workspace` 是唯一私有工作台入口；实现可采用批准的 OpenHands-derived interaction
mechanics，但产品契约仍由本文件定义。Workspace 只有在真实 ResearchRun 服务可验证
时才允许显示运行结果；无运行服务时必须显示明确的未连接/不可执行状态，禁止注入假事件。
`/share/$shareToken` 是固定版本的只读安全边界。自动化覆盖与门禁见
[Test Strategy](../engineering/TEST_STRATEGY.md)。

## 1. 目标

Workspace 支持用户在同一研究上下文中完成：

```text
提出研究意图
→ 确认研究协议
→ 观察 Agent 执行
→ 审查科研产物
→ 核验证据与来源
→ 作出人类决策
→ 修订、导出或分享
```

## 2. 核心工作面

选定上游产品必须提供以下工作面；具体排列、折叠和响应式行为继承其成熟实现。

| 工作面              | 职责                                                   |
| ------------------- | ------------------------------------------------------ |
| Research Navigation | 新建、选择、固定、分组和恢复 Project / Run             |
| Agent Activity      | 展示用户指令、Agent 计划、执行事件、审批、错误和交付物 |
| Artifact Workspace  | 阅读、比较和审查科研产物                               |
| Context Inspector   | 核验当前对象的 Evidence、Source、Version 与执行详情    |
| Research Composer   | 提交研究指令、修订请求、范围变化和人类决策             |

任一正式 Workspace 状态不得退化为只含静态内容的页面。

## 3. Research Navigation

导航项至少展示：

- 人类可读标题；
- Run 状态；
- 当前阶段或最近结果；
- 最近更新时间；
- 待复核或失败提示。

必须支持：

- 当前项；
- Recent；
- Pin / Unpin；
- Group / Filter / Sort；
- Collapse；
- 键盘导航。

导航不显示原始内部 ID，不使用大面积卡片替代列表结构。

## 4. Agent Activity

Agent Activity 以可理解的研究事件组织，不直接呈现原始日志。

界面保留 OpenHands 的事件列表、连续工具/进度分组、可展开详情、运行中/完成/错误状态与滚动跟随机制。运行时只提供公开可审计事件；没有运行服务或事件时显示空状态，不生成演示数据。

事件类别：

```text
User Instruction
Agent Plan
Research Step
Tool Execution
Human Checkpoint
Artifact Produced
Evidence Added
Conflict Detected
Revision Produced
Error / Recovery
Completion
```

默认层回答：

```text
为什么执行
正在执行什么
发现了什么
产生了什么
下一步是什么
```

工具参数、完整请求、Hash、耗时与 Raw 输出进入可展开详情。

Tool 与 Deliverable 分离：

- Tool 表示执行过程；
- Deliverable 表示可审查结果；
- Artifact 事件打开 Artifact Workspace；
- Evidence 事件打开 Context Inspector；
- Checkpoint 阻塞后续执行并要求用户决策。

## 5. Artifact Workspace

Artifact Workspace 承载：

- Dataset；
- Field Dictionary；
- Source Collection；
- Paper Collection；
- Paper Summary；
- Literature Claim / Relation；
- Reasoning Trace；
- Candidate Dossier；
- Artifact Version；
- Export / Share。

工作模式：

| 模式          | 用途                       |
| ------------- | -------------------------- |
| Docked        | 与 Agent Activity 并列查看 |
| Focus         | 长文、数据或复杂产物审查   |
| Compare       | 两个明确对象的科研比较     |
| Source Review | 完整来源阅读与定位         |

每个 Artifact Kind 使用专属 Renderer。未知类型显示明确不支持状态，不以 Hash 或内部 Metadata 充当内容。

## 6. Context Inspector

Inspector 由当前选中对象驱动。

| 选中对象                 | Inspector 内容                               |
| ------------------------ | -------------------------------------------- |
| Statement / Cell / Claim | Evidence 状态与关联证据                      |
| Evidence                 | SourceSnapshot、locator、quote / value、版本 |
| Artifact                 | Metadata、Evidence Coverage、Review          |
| ArtifactVersion          | 版本关系与 Scientific Diff                   |
| Human Checkpoint         | 决策上下文                                   |
| Tool Execution           | 执行详情                                     |

Inspector 支持返回、固定和关闭，并保持最小访问历史。

## 7. Research Composer

Composer 继承上游成熟输入、附件、快捷键、提交、取消和焦点行为。

提交语义：

```text
Start Research
Continue Research
Revise Artifact
Verify Statement
Change Scope
Resolve Checkpoint
Derive Run
```

前端将输入映射为结构化 Research Intent，不直接创建科研事实。

Completed 状态不得禁用 Composer；必须允许继续研究、请求修订或派生 Run。

## 8. 页面状态

### Empty

展示研究意图入口、可用输入、最近项目和真实数据边界。不得使用虚构 Project 填充空状态。

### Draft

展示 Research Contract Draft 与计划预览。Contract 未确认时不得启动 Run。

### Running

展示 Agent Plan、当前步骤、最新 Deliverable、暂停或取消入口。Checkpoint 到达时突出用户决策。

### Needs Review

默认打开待复核对象。支持接受、请求修订、扩大来源、改变条件和继续研究。

### Completed

保留完整 Agent Activity，并突出最终 Artifact、关键 Evidence、冲突、局限、未解决问题与推荐下一步。

主要动作：

```text
继续研究
请求修订
派生新任务
导出
分享
```

### Failed

展示失败阶段、公开错误、已产生 Artifact、重试条件、缓存边界和可执行下一步。

## 9. Evidence 与来源

核心链路在两次交互内成立：

```text
Statement / Cell / Claim
→ Evidence
→ Source / Locator / Snapshot
```

Evidence 状态：

```text
Supported
Conflicted
Unresolved
Source Version Conflict
```

状态同时使用文字与视觉标识。未经校准的百分比不得替代 Evidence 事实。

## 10. Human Checkpoints

Workspace 固定支持三类决策：

| Checkpoint            | 核心内容                                     |
| --------------------- | -------------------------------------------- |
| Protocol              | 研究问题、范围、纳入排除、目标产物、停止条件 |
| Evidence Set          | 接受来源、排除理由、冲突、版本问题、数据缺口 |
| Conclusion / Revision | 接受、修订、扩大来源、改变条件、派生 Run     |

Checkpoint 的状态与可用动作由后端 Workflow 提供，前端不维护第二套状态机。

## 11. Version 与修订

Scientific Version Diff 至少展示：

- Contract 变化；
- Source Set 变化；
- Evidence 变化；
- Statement / Claim 变化；
- 冲突与局限变化；
- Artifact 内容变化。

修订创建新 Contract、派生 Run 或新 ArtifactVersion，不原地覆盖历史。

## 12. 响应式与可访问性

- 完整键盘路径；
- 可见 Focus Ring；
- Skip Link；
- 正确 Heading 层级；
- 状态不只靠颜色；
- 200% 字体可完成核心路径；
- Reduced Motion；
- Overlay 关闭后恢复焦点；
- Resize 提供键盘替代。

Workspace 当前仅支持宽度不低于 1024px 的桌面窗口；`<1024px` 只显示明确的桌面边界提示，不挂载 Workspace、移动导航、抽屉、触控分支或移动断点。桌面实现需在 1440×900、1280×800 与 200% 字体下保持核心机械结构可操作。

## 13. 产品语言

界面结构与操作以中文为主。标准、论文标题、DOI 与 Artifact Kind 可保留英文。

默认视图禁止出现：

- Preview、阶段编号或内部项目代号；
- Adapter、Fixture、Hash、Execution Mode；
- 失效功能提示占据主操作区；
- 假 Project、假 Run、假 Evidence；
- 原始模型思维过程。

## 14. 验收边界

产品视觉由用户确认。自动化测试、构建和截图差异不能单独判定 Workspace 可用。
