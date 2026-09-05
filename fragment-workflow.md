# 零碎多源资料工作流

本规范处理围绕同一主题、来自不同文件和格式、颗粒度不一且可能重复或冲突的资料。核心原则是先建立可审计的碎片层，再生成知识组件。

## 固定输出结构

```text
knowledge-base/
├── kb-profile.yaml
├── sources.jsonl
├── fragments.jsonl
├── mappings.jsonl
├── conflicts.jsonl
├── components/
├── relations.jsonl
├── indexes/
├── validation/
│   ├── report.json
│   └── report.md
└── release-manifest.json
```

JSONL 文件每行一个完整 JSON 对象，使用 UTF-8。原始来源保留在只读目录中，不复制到组件正文作为唯一存档。

## 可执行入口

```text
python scripts/build_kb.py run <来源目录> <输出目录> --kb-id <ID> --title <名称> --question <中心问题> --include <纳入主题>
python scripts/build_kb.py status <输出目录>
python scripts/build_kb.py validate <输出目录>
python scripts/build_kb.py release <输出目录>
```

`run` 默认只摄取 3 个文件用于试点；确认后使用 `build_kb.py ingest <来源目录> <输出目录> --limit 0` 扩展全量。跨格式转换失败会登记为 `failed` 并阻断发布，不会被静默排除。

## 1. KBProfile：先锁定主题边界

```yaml
schema_version: "1.0"
kb_id: product-management.discovery
title: 用户需求发现
central_question: 如何识别、验证并排序真实用户需求
audiences: [产品经理, 创业者]
target_tasks: [学习, 检索, 问答, 决策辅助]
included_topics: [访谈, 观察, 需求验证, 优先级]
excluded_topics: [广告投放, 纯销售话术]
boundary_examples:
  include: ["访谈问题如何避免诱导"]
  contextual: ["产品路线图，仅保留与需求优先级相关部分"]
  exclude: ["短视频投流技巧"]
domain_profile: business
risk_profile:
  level: medium
  domains: [privacy]
  jurisdictions: []
relevance:
  labels: [include, contextual, exclude, uncertain]
  review_below: 0.75
release_policy:
  unresolved_conflicts_allowed: true
  professional_approval_required: false
  minimum_review_rate: 1.0
extensions: {}
```

边界不明确时先收集 5～10 个纳入、排除和边界样本。`contextual` 表示只作为理解语境，不直接产出叶子组件；`uncertain` 必须进入复核队列。

## 2. SourceRevision：登记来源及修订版

`sources.jsonl` 每条至少包含：

```json
{
  "schema_version": "1.0",
  "source_id": "src.interview.001",
  "revision_id": "rev.2026-09-05.a",
  "path": "inputs/访谈记录.docx",
  "format": "docx",
  "sha256": "64位小写十六进制",
  "title": "用户访谈记录",
  "author": null,
  "published_at": null,
  "effective_at": null,
  "license": null,
  "parser": {"name": "markitdown", "version": "unknown"},
  "quality": {"score": 0.9, "issues": []},
  "derived_text_path": "derived/src.interview.001/rev.2026-09-05.a.md",
  "status": "ingested",
  "error": null,
  "ingested_at": "2026-09-05T02:30:00+00:00",
  "run_id": "run-20260905T023000Z",
  "extensions": {}
}
```

同一逻辑来源的内容变更创建新 `revision_id`；不要覆盖旧修订版。网页抓取时间、法规有效期、软件版本、访谈日期等不能混为一个字段。

## 3. Fragment：建立不可变碎片层

碎片以“可独立判断相关性和主读者任务的最小上下文”为边界，不按固定字数硬切。保留原文与规范化文本：

```json
{
  "schema_version": "1.0",
  "fragment_id": "frag.interview.001.0007",
  "source_id": "src.interview.001",
  "revision_id": "rev.2026-09-05.a",
  "anchor": {"kind": "paragraph_range", "start": 12, "end": 15},
  "raw_text": "逐字派生文本",
  "raw_sha256": "64位小写十六进制",
  "normalized_text": "仅做空白、断行或明确登记的规范化",
  "normalization_log": ["合并跨页断句"],
  "language": "zh-CN",
  "heading_path": ["访谈", "需求验证"],
  "relevance": {
    "label": "include",
    "confidence": 0.92,
    "reason": "直接说明验证方法",
    "review_status": "reviewed"
  },
  "disposition": "mapped",
  "disposition_reason": null,
  "run_id": "run-20260905T023000Z",
  "extensions": {}
}
```

通用锚点类型：

- Markdown/文本：`line_range`、`heading_range`、`paragraph_range`
- PDF：`page_bbox`、`page_range`
- 幻灯片：`slide`
- 音视频：`time_range`
- 表格：`sheet_range`
- 网页：`css_selector`、`xpath`、`text_quote`
- 图片：`region`

OCR、ASR、网页提取或格式转换产生的是派生文本。必须记录解析器、质量和损失，不能把派生文本冒充原始二进制文件。当前通用 MarkItDown 适配器保证派生文本行锚点；原生页码、时间码或单元格不可恢复时，`native_anchor_available` 必须为 `false` 并进入格式复核。

## 4. CandidateClaim 与跨源聚类

先从纳入碎片提取：

- 主读者任务
- 最小主张
- 条件、对象、时间、辖区、版本
- 候选类型
- 风险与证据角色

再聚类。聚类只表示“值得一起比较”，不表示内容等价。`mappings.jsonl` 至少记录：

```json
{
  "schema_version": "1.0",
  "mapping_id": "map.00031",
  "fragment_ids": ["frag.a.001", "frag.b.009"],
  "reader_task": "判断访谈问题是否具有诱导性",
  "candidate_type": "rule",
  "cluster_id": "cluster.leading-question",
  "relation_candidate": "equivalent",
  "decision": "merge",
  "target_component_id": "discovery.rule.leading-question",
  "basis": "条件、对象、结论与适用范围相同",
  "review_status": "reviewed",
  "run_id": "run-20260905T023000Z",
  "extensions": {}
}
```

## 5. 去重决策

按以下顺序判定：

1. 条件、对象、结论、强度、时间、辖区和版本是否相同。
2. 是否只是措辞差异。
3. 是否存在上下位、范围收窄或例外补充。
4. 是否是来源的新旧修订。
5. 是否结论相反或无法同时成立。

允许的关系：

- `exact_duplicate`：文本和语义均重复。
- `equivalent`：同义改写，可合并为一个 canonical 组件并保留全部来源。
- `broader_than` / `narrower_than`：上下位或范围不同，不合并。
- `updates`：新版本更新旧版本。
- `supersedes`：明确废止旧结论。
- `supports` / `contradicts`：支持或反驳。
- `related`：仅相关，无更强语义。

相似度只能生成候选。下列任一字段不同，默认不自动合并：适用条件、结论强度、时间、辖区、对象版本、风险级别。

## 6. 冲突管理

`conflicts.jsonl`：

```json
{
  "schema_version": "1.0",
  "conflict_id": "conflict.0012",
  "subject": "首次访谈是否应展示原型",
  "claim_refs": ["claim.0031", "claim.0048"],
  "source_refs": ["src.book.001@rev.1", "src.article.009@rev.2"],
  "conflict_type": "conditional",
  "differences": ["研究阶段不同", "原型保真度不同"],
  "resolution": "preserve-both",
  "resolution_basis": "适用条件不同",
  "status": "resolved",
  "review_required": false,
  "run_id": "run-20260905T023000Z",
  "extensions": {}
}
```

冲突类型可为 `direct`、`conditional`、`temporal`、`jurisdictional`、`versioned`、`terminological`、`unresolved`。无法解决时保留双方，不输出伪共识。

## 7. 多来源组件

组件以 `component-schema.json` 为准。`provenance` 中每条证据都要指向来源修订版和锚点：

```yaml
provenance:
  - source_id: src.book.001
    revision_id: rev.1
    source_file: inputs/书稿.md
    source_sha256: "..."
    anchors:
      - kind: line_range
        start: 81
        end: 96
    evidence_role: supports
    extraction_method: faithful_paraphrase
  - source_id: src.interview.001
    revision_id: rev.2026-09-05.a
    source_file: derived/src.interview.001/rev.2026-09-05.a.md
    source_sha256: "..."
    anchors:
      - kind: paragraph_range
        start: 12
        end: 15
    evidence_role: example
    extraction_method: direct
```

证据角色：`supports`、`contradicts`、`context`、`example`、`derivation_basis`。跨源综合不得使用 `source_quote` 层级；应使用 `faithful_synthesis` 或 `editorial_inference`。

## 8. 覆盖率与孤儿

必须计算：

- `disposition_coverage = 有处置碎片数 / 全部碎片数`，发布要求 100%。
- `mapping_coverage = mapped 碎片中已有有效映射数 / mapped 碎片数`。
- 有效孤儿碎片：标记 `mapped` 但无组件或映射。
- 反向孤儿组件：叶子组件无来源映射。
- 未决冲突：`status = open` 的冲突数量。

`deferred`、`excluded` 和 `context-only` 计入处置覆盖率，但必须有理由；不得用排除标签隐藏解析失败或难以处理的内容。

## 9. 增量更新

每次运行记录 `run_id`。比较来源指纹：

- 新增来源：只新增其碎片，重算相关聚类。
- 来源修改：创建新修订版，定位受影响碎片和组件。
- 来源删除：保留 tombstone，组件转为待复核，不立即物理删除。
- Schema/分类法/画像变化：按影响范围重审，不默认全库重写。

维护 `来源修订 → 碎片 → 映射 → 组件 → 索引` 影响链。发布快照不可变，工作区可增量更新。

## 10. 发布门禁

同时满足才可发布：

1. 处置覆盖率 100%，无有效孤儿碎片或无来源组件。
2. 来源、修订、锚点和指纹有效。
3. 无重复 ID、死引用或强依赖环。
4. 去重和冲突均有显式决策，未决冲突符合发布策略。
5. 高风险组件满足领域画像要求，否则保持草稿或停止。
6. 自动结构校验通过，语义抽检达到项目阈值。
7. `release-manifest.json` 记录输入、版本、指标、阻断项和发布状态。
