# 分类法 v2

版本：`2.2.0`

状态：当前有效

生效范围：本 skill 后续新建或重审的知识组件。

本分类法只描述知识的功能和读者任务，不表示领域、证据可信度、风险等级或发布权限。领域差异通过 [domain-profiles.md](domain-profiles.md) 叠加字段和门禁，不得改写核心类型语义。

## 受控类型

| type | 中文名 | 核心读者任务 |
|---|---|---|
| concept | 概念 | X 是什么？ |
| principle | 原理 | 为什么／如何运作？ |
| viewpoint | 观点 | 作者对此问题的立场是什么？ |
| misconception | 误区 | 常见理解错在哪里？ |
| guideline | 准则 | 应该或不应该怎么做？ |
| framework | 框架 | 从哪些部分或维度分析？ |
| rule | 规则 | 满足何种条件能得出何种结论？ |
| workflow | 流程 | 如何按步骤完成一件事？ |
| tool | 工具 | 如何用某个工具得到结果？ |
| solution | 方案 | 如何处理某一问题？ |
| scene | 场景 | 在何种现实情形下调用哪些组件？ |
| case | 案例 | 一个具体实例如何分析？ |
| analogy | 类比 | 如何借喻体理解本体？ |
| story | 故事 | 如何通过完整叙事获得启发？ |
| boundary | 边界 | 哪些风险、禁止事项或转介条件存在？ |
| source | 溯源 | 内容版本和引用链可靠吗？ |
| data | 数据 | 字段及其口径是什么？ |
| quote | 金句 | 原话在何种语境下可被引用？ |
| paradigm | 范式 | 如何编排任务、门禁、分支与产物？ |
| course | 课程 | 如何按学习目标组织先修、顺序、练习与完成标准？ |

完整准入门禁和正文契约以 `reference.md` 为准。

## 领域扩展规则

1. 先使用核心类型表达知识功能，再用 `domain`、`tags` 和领域画像表达主题归属。
2. 不得为每个领域复制一套同义类型，例如不创建 `medical-rule`、`legal-rule`；使用 `type: rule` 并叠加领域画像。
3. 领域确有新型读者任务时，先登记候选类型、相邻类型排除条件、正文契约和回归样本，再按演化策略试验。
4. 领域画像可提高风险门禁，不得降低来源可追溯、旧版可读、冲突保留和状态不虚增四项约束。

## 版本迁移

### v1 → v2 的类型映射

| 旧类型／旧用法 | v2 去向 | 迁移条件 |
|---|---|---|
| `principle` 中描述客观机制的内容 | `principle` | 保留；补齐机制、范围、推论 |
| `principle` 中表达课程立场的内容 | `viewpoint` | 有可争议问题和课程主张 |
| `principle` 中纠正常见错误的内容 | `misconception` | 存在“误区陈述→纠正”对照 |
| `principle` 中约束使用者行为的内容 | `guideline` | 有应该／禁止要求与违反后果 |
| `story` 中无 STAR 弧线的情境对举或拟人映射 | `analogy` | 有本体、喻体和映射关系 |
| 不满足任何门禁的叶子组件 | 容器／合并／暂缓 | 不允许仅为保留文件而强行分类 |

### 迁移规则

1. **ID 不因重分类自动改变**；除非 ID 本身含已失效类型语义并会误导调用者。
2. 若必须替换 ID：旧组件 frontmatter 标记 `deprecated: true`、`deprecated_by: 新ID`；新组件标记 `supersedes: 旧ID`。
3. 每次迁移在 `migration_log` 中记录迁移日期、`taxonomy_from`、`taxonomy_to`、原类型、新类型、理由和审批者。
4. 未经人工复核的迁移组件保持 `status: 已整理`，不得因为自动脚本通过而标记为“已复核”。

## 来源内容层级

组件正文必须区分以下层级，禁止把整理者补充伪装为来源原话：

| 层级 | frontmatter 值 | 使用规则 |
|---|---|---|
| 原文摘录 | `source_quote` | 必须可在 `source_file` + `source_lines` 中逐字定位 |
| 忠实改写 | `faithful_paraphrase` | 不得新增原文没有的因果、事实或结论 |
| 忠实综合 | `faithful_synthesis` | 综合多个来源共同支持的有限陈述；必须列出全部 provenance，不能写成单一来源原话 |
| 整理者补充 | `editorial_explanation` | 明示为整理者解释，并指明依据组件或来源 |
| 整理者推断 | `editorial_inference` | 必须标明推断，不得升级为原文主张 |
| 外部事实 | `external_fact` | 必须附外部来源与版本，不可只依赖课程原文 |

推荐 frontmatter：

```yaml
taxonomy_version: "2.2.0"
content_layers:
  - kind: source_quote
    source_lines: [93, 111]
  - kind: editorial_explanation
    basis: ["jishi.concept.bazi-gongneng"]
editorial_additions: true
migration_log: []
```
