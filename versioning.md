# 版本兼容与迁移

## 当前稳定组合

- Skill 技术名：`chaoyun-knowledge-base-builder`
- Builder：`1.0.0`
- Taxonomy：`2.2.0`
- Component Schema：`2.2`
- Pipeline Schema：`1.0`
- KB Profile：`1.0`
- Evolution Policy：`1.1.0`

发布清单必须记录以上版本。版本缺失或不兼容时，校验器应阻断发布。

## 兼容规则

- Builder `1.x` 只承诺读取 Component Schema `2.2.x` 与 Pipeline Schema `1.0.x`。
- Taxonomy 的主版本变化要求全量类型回归；次版本变化要求重审受影响类型。
- Component Schema 新增必填字段属于破坏性变化，必须生成迁移报告。
- Pipeline Schema 主版本变化要求迁移全部 JSONL 中间产物。
- 领域画像只能提高门禁；降低高风险门禁属于人工批准事项。

## 旧版组件迁移

仅有 `source_file/source_lines/source_sha256` 的旧组件：

1. 保留旧组件只读快照。
2. 为来源建立 `source_id` 和 `revision_id`。
3. 将旧行号转换为 `provenance[].anchors`。
4. 补齐 `kb_id`、`component_version`、`canonical`、`dedupe_status`、`conflict_status` 和 `risk`。
5. 运行完整流水线校验；不得因为字段自动补齐而升级人工复核状态。

## 安装目录

Cursor 以 `SKILL.md` frontmatter 中的 `name` 作为技术身份。当前历史安装目录可保留为 `structuring-content-knowledge-base` 以避免已有引用失效；新安装建议使用目录 `chaoyun-knowledge-base-builder`。目录迁移时只移动 Skill 文件，不修改知识组件 ID。
