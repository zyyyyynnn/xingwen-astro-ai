# Risk Register

| 元数据    | 值                                         |
| --------- | ------------------------------------------ |
| Status    | Accepted                                   |
| Authority | 当前有效风险、触发信号、缓解措施和关闭条件 |

本文只记录仍需主动管理的风险。已解决问题应关闭或降级，并在相关 Issue / PR 留下证据；一般编码规则不在这里重复。

## 1. 评分

- **Critical**：可能导致来源失真、数据泄露、不可恢复版本损坏或作品失效。
- **High**：可能阻塞核心链路或使关键科研结论不可审查。
- **Medium**：会显著增加迁移、联调、性能或材料成本。
- **Low**：影响体验或维护效率，但存在清晰绕行路径。

## 2. Active risks

| ID   | Severity | 风险                                   | 触发信号                                             | 主要缓解                                                             | 关闭条件 / Owner                |
| ---- | -------- | -------------------------------------- | ---------------------------------------------------- | -------------------------------------------------------------------- | ------------------------------- |
| R-01 | Critical | Fixture、Live、Cached 或 Revision 失真 | 页面/材料无法定位来源 Run 或把 seed 当自动结果       | 分离 execution/source/derivation；CacheRecord 与 provenance manifest | X-08、A-09、B-10 通过           |
| R-02 | Critical | Session / Share 越权                   | 跨会话 ID 可读取；分享暴露编辑能力或动态 latest      | 服务端 ownership、CSRF、token hash、冻结 ShareSnapshot               | B-04、B-11、X-02 安全测试通过   |
| R-03 | Critical | ArtifactVersion 原地覆盖或版本链损坏   | 历史截图无法复现；supersedes 环或 latest 指向不一致  | 追加式版本、事务约束、RevisionPlan、冲突测试                         | X-08 版本与并发测试通过         |
| R-04 | High     | 外部数据/论文来源不稳定                | 超时、限流、Schema 漂移、空结果显著增加              | Adapter、重试分类、SourceSnapshot、真实缓存建议                      | X-06 真实/录制源与失败测试通过  |
| R-05 | High     | 模型输出无效或编造                     | Schema 失败、Evidence 缺失、unsupported 增加         | 结构校验、Evidence 门、Benchmark、禁止自由文本直出                   | D-03/D-04 与 X-07 指标达标      |
| R-06 | High     | Relation / Graph 产生无证据关系        | Accepted Relation 无双方 Evidence；Graph 悬空引用    | candidate/accepted/rejected、Trace、Graph 完整性门                   | X-07 Benchmark 与完整性测试通过 |
| R-07 | High     | Case Manifest 与实现漂移               | 字段、单位、来源或 taxonomy 在代码中出现第二套定义   | C-01/D-01/X-00 单一版本、Contract 校验和 hash                        | X-00 冻结且 stale check 进入 CI |
| R-08 | High     | v1/v2 Contract 与实现状态漂移          | v1 DTO 被当作 v2 目标，或 Pending 资源被写成 Current | 版本边界、生成 Contract、状态口径与集成测试                          | B-04、A-03、X-01 通过           |
| R-09 | Medium   | WebGL 性能或 context loss 破坏主体验   | 低端设备卡顿、页面隐藏仍渲染、Canvas 崩溃后空白      | 质量档、Poster、Reduced Motion、pause/dispose                        | A-02 与 X-02 降级测试通过       |
| R-10 | Medium   | 数据 crossmatch 或单位规则错误         | 匹配冲突率高、单位不可转换、误差/limit 丢失          | 版本化规则、人工样例、冲突保留、Evidence                             | C-03～C-05 固定样例通过         |
| R-11 | Medium   | Prompt / model 变更导致结果不可复现    | 使用“最新版本”、历史缓存无法定位生成条件             | Prompt registry、ProducerExecution、input/output hash                | D-03/D-04 和 X-08 版本链通过    |
| R-12 | Medium   | 部署配置与本地基线漂移                 | 深链接 404、Cookie/CORS 失败、migration 不一致       | Preview smoke、路由 fallback、环境隔离、发布记录                     | X-02 发布检查通过               |
| R-13 | Medium   | 文档、Issue 与实现再次漂移             | Backlog 标题/依赖过期；同一规则多处冲突              | 文档治理、唯一事实源、索引和 PR 检查                                 | 文档 CI / Review 持续执行       |
| R-14 | Medium   | 第三方许可或字体来源不清               | 无许可证、受限全文或不可分发资产进入发布物           | 来源/许可记录、Reference 隔离、资产审查                              | A-02、X-03 资产清单通过         |
| R-15 | Low      | 材料与系统版本不一致                   | 视频、PDF、截图和网页展示不同结果                    | provenance manifest、固定 Run/Version、content hash                  | X-03 自主走读通过               |
| R-16 | Medium   | v2 Session/限流/幂等使用内存存储      | API 重启或水平扩容后匿名 Session、限流窗口、幂等键全部丢失 | PostgreSQL 持久化适配器（后续 Issue）；当前仅在单实例本地基线使用 | 持久化 Session 适配器 + 跨实例测试通过 |

## 3. 风险处理流程

1. 在 Issue / PR 中引用 Risk ID。
2. 记录触发信号、影响范围和临时缓解。
3. Critical / High 风险必须有明确 Owner Issue 和验证计划。
4. 缓解措施进入代码、Contract、测试或运行门禁，不能只写说明。
5. 关闭风险时附 Commit、测试、运行或材料证据。
6. 风险条件变化时调整 Severity，不删除历史讨论。

## 4. 接受与例外

风险接受必须说明：

- 为什么当前不修；
- 暴露范围和最长接受时间；
- 用户/评审可见影响；
- 监测信号和触发修复条件；
- 负责人批准。

不能接受的例外包括：来源伪装、密钥暴露、跨会话越权、历史版本破坏、无 Evidence 最终关系和绕过必要 CI。

## 5. Review 要求

PR 审查时检查：

- 是否新增或显著改变风险；
- 是否使已有缓解失效；
- 是否需要更新 Severity、Owner 或关闭条件；
- 是否引入未经 ADR 的基础设施或权限面；
- 是否有可重复的风险验证证据。

没有活跃风险变化时，不为形式修改本文件。
