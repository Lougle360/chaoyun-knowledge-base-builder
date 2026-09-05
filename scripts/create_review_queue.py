#!/usr/bin/env python3
"""生成面向 Agent/人工的待复核队列，不改变知识对象。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="生成知识库待复核队列")
    parser.add_argument("root", type=Path)
    parser.add_argument("--max-preview", type=int, default=500)
    args = parser.parse_args()
    root = args.root.resolve()
    validation = root / "validation"
    validation.mkdir(parents=True, exist_ok=True)

    sources = load_jsonl(root / "sources.jsonl")
    fragments = load_jsonl(root / "fragments.jsonl")
    conflicts = load_jsonl(root / "conflicts.jsonl")
    failed_sources = [
        {
            "source_id": row.get("source_id"),
            "revision_id": row.get("revision_id"),
            "path": row.get("path"),
            "error": row.get("error"),
        }
        for row in sources
        if row.get("status") == "failed"
    ]
    pending_fragments = [
        {
            "fragment_id": row.get("fragment_id"),
            "source_id": row.get("source_id"),
            "relevance": row.get("relevance"),
            "disposition": row.get("disposition"),
            "preview": str(row.get("normalized_text", ""))[: args.max_preview],
        }
        for row in fragments
        if (row.get("relevance") or {}).get("review_status") == "pending"
        or row.get("disposition") == "deferred"
    ]
    open_conflicts = [
        {
            "conflict_id": row.get("conflict_id"),
            "subject": row.get("subject"),
            "differences": row.get("differences"),
            "review_required": row.get("review_required"),
        }
        for row in conflicts
        if row.get("status") == "open"
    ]
    queue = {
        "failed_sources": failed_sources,
        "pending_fragments": pending_fragments,
        "open_conflicts": open_conflicts,
        "counts": {
            "failed_sources": len(failed_sources),
            "pending_fragments": len(pending_fragments),
            "open_conflicts": len(open_conflicts),
        },
    }
    (validation / "review-queue.json").write_text(
        json.dumps(queue, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = [
        "# 待复核队列",
        "",
        f"- 转换失败来源：{len(failed_sources)}",
        f"- 待复核或暂缓碎片：{len(pending_fragments)}",
        f"- 未决冲突：{len(open_conflicts)}",
        "",
        "## 转换失败来源",
    ]
    if failed_sources:
        for item in failed_sources:
            lines.append(f"- `{item['path']}`：{item['error']}")
    else:
        lines.append("- 无")
    lines += ["", "## 待复核碎片"]
    if pending_fragments:
        for item in pending_fragments:
            lines += [
                f"### {item['fragment_id']}",
                f"- 来源：`{item['source_id']}`",
                f"- 当前相关性：`{(item['relevance'] or {}).get('label')}`",
                f"- 当前处置：`{item['disposition']}`",
                "",
                item["preview"],
                "",
            ]
    else:
        lines.append("- 无")
    lines += ["", "## 未决冲突"]
    if open_conflicts:
        for item in open_conflicts:
            lines.append(f"- `{item['conflict_id']}` {item['subject']}")
    else:
        lines.append("- 无")
    (validation / "review-queue.md").write_text(
        "\n".join(lines).rstrip() + "\n",
        encoding="utf-8",
    )
    print(json.dumps(queue["counts"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
