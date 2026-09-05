# 超云知识库构建器

将围绕某一主题的零碎、多格式、多来源资料，重构为可追溯、可检索、可编排、可增量更新和可验证的结构化知识库。

## 主要能力

- 摄取 Markdown、文本、PDF、DOCX、PPTX、XLSX、网页、图片和音视频等资料
- 建立来源修订、内容指纹、派生文本和原子碎片
- 支持跨来源聚类、同义去重、冲突保留和多源溯源
- 提供20类知识组件及跨领域适配画像
- 校验来源哈希、锚点、映射、依赖环、孤儿组件和发布状态
- 对医疗、法律、金融、工程、安全和隐私内容设置专业门禁
- 支持试点、增量更新、删除标记、失败隔离和发布清单

## 安装

将本仓库放入 Cursor 个人 Skill 目录：

```text
~/.cursor/skills/chaoyun-knowledge-base-builder/
```

安装依赖：

```text
python -m pip install -r scripts/requirements.txt
```

## 快速开始

```text
python scripts/build_kb.py run <来源目录> <输出目录> --kb-id <稳定英文ID> --title <知识库名称> --question <中心问题> --include <纳入主题>
```

默认只摄取前3个文件作为试点。

常用命令：

```text
python scripts/build_kb.py status <输出目录>
python scripts/build_kb.py ingest <来源目录> <输出目录> --limit 0
python scripts/build_kb.py validate <输出目录> --strict
python scripts/build_kb.py release <输出目录>
python scripts/build_kb.py release <输出目录> --publish
```

## 工作边界

脚本负责跨格式摄取、来源登记、碎片生成、索引、交叉校验和发布门禁。语义聚类、组件类型判定与正文生成由 Cursor Agent 按 `SKILL.md` 执行。

自动校验不等于人工或专业复核。高风险内容必须满足对应领域的现实审批要求。

## 测试

```text
python -m unittest scripts/test_validate_components.py scripts/test_ingest_sources.py -v
```

当前回归覆盖文本与 DOCX 摄取、幂等执行、来源修改与删除、转换失败、溯源完整性、风险降级、孤儿碎片、依赖环和正式发布。
