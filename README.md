# 超云知识库构建器

将围绕某一主题的零碎、多格式、多来源资料，重构为可追溯、可检索、可编排、可增量更新和可验证的结构化知识库。

## 主要能力

- 摄取 Markdown、文本、PDF、DOCX、PPTX、XLSX、网页、图片和音视频等资料
- 建立来源修订、内容指纹、派生文本和原子碎片
- 支持跨来源聚类、同义去重、冲突保留和多源溯源
- 提供 20 类知识组件及跨领域适配画像
- 校验来源哈希、锚点、映射、依赖环、孤儿组件和发布状态
- 对医疗、法律、金融、工程、安全和隐私内容设置专业门禁
- 支持试点、增量更新、删除标记、失败隔离和发布清单

## 安装

在仓库根目录创建独立虚拟环境。Windows + Python 3.14 可使用已验证的锁定依赖：

```powershell
py -3.14 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r scripts\requirements-python314.lock.txt
```

其他 Python 3.11+ 环境可从通用约束安装：

```text
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r scripts/requirements.txt
```

锁文件是 Windows x64、CPython 3.14.9 的验证快照；跨平台安装应优先使用 `requirements.txt`，再按实际环境生成自己的锁文件。

## 快速开始

```text
.venv\Scripts\python.exe scripts/build_kb.py run <来源目录> <输出目录> --kb-id <稳定英文ID> --title <知识库名称> --question <中心问题> --include <纳入主题>
```

`run` 默认只摄取前 3 个文件作为试点。常用命令：

```text
.venv\Scripts\python.exe scripts/build_kb.py status <输出目录>
.venv\Scripts\python.exe scripts/build_kb.py ingest <来源目录> <输出目录> --limit 0
.venv\Scripts\python.exe scripts/build_kb.py validate <输出目录> --strict
.venv\Scripts\python.exe scripts/build_kb.py release <输出目录>
.venv\Scripts\python.exe scripts/build_kb.py release <输出目录> --publish
```

## PDF 失败隔离

PDF 转换前会同时检查文件签名和可解析的文档结构。扩展名伪装、只有 `%PDF-` 文件头的损坏文件或无法解析的文档会写入失败隔离报告，不会被通用转换器静默当作纯文本接收。

结构校验通过仍不等于内容提取完整。扫描件、缺字、乱码和版面顺序问题仍需人工或专项工具复核。

## 工作边界

脚本负责跨格式摄取、来源登记、碎片生成、索引、交叉校验和发布门禁。语义聚类、组件类型判定与正文生成由 Agent 按 `SKILL.md` 执行。

自动校验不等于人工或专业复核。高风险内容必须满足对应领域的现实审批要求。

## 测试

```text
.venv\Scripts\python.exe -m unittest discover -s scripts -p "test_*.py" -v
.venv\Scripts\python.exe -m pip check
```

当前回归覆盖文本、DOCX 和有效 PDF 摄取，幂等执行，来源修改与删除，伪造及损坏 PDF 隔离，转换失败，溯源完整性，风险降级，孤儿碎片，依赖环和正式发布。Windows x64、Python 3.14.9、MarkItDown 0.1.9 下共 15 项测试通过、无跳过。
