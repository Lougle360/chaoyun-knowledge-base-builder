#!/usr/bin/env python3
"""从组件 frontmatter 重建机器索引和关系表，输出稳定排序。"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import yaml


def metadata(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\s*\r?\n(.*?)\r?\n---", text, re.S)
    if not match:
        raise ValueError(f"{path} 缺少 frontmatter")
    value = yaml.safe_load(match.group(1))
    if not isinstance(value, dict):
        raise ValueError(f"{path} frontmatter 不是对象")
    return value


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="重建组件索引与关系表")
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    component_root = root / "components"
    index_root = root / "indexes"
    index_root.mkdir(parents=True, exist_ok=True)

    component_rows: list[dict[str, Any]] = []
    relation_rows: list[dict[str, Any]] = []
    by_type: dict[str, list[str]] = {}
    for path in sorted(component_root.rglob("*.md")) if component_root.is_dir() else []:
        meta = metadata(path)
        component_id = str(meta.get("id", ""))
        if not component_id:
            continue
        component_rows.append({
            "id": component_id,
            "type": meta.get("type"),
            "title": meta.get("title"),
            "summary": meta.get("summary"),
            "path": path.relative_to(root).as_posix(),
            "domain_profile": meta.get("domain_profile"),
            "evidence_level": meta.get("evidence_level"),
            "status": meta.get("status"),
            "risk_level": (meta.get("risk") or {}).get("level"),
        })
        by_type.setdefault(str(meta.get("type")), []).append(component_id)
        for field, relation in (
            ("depends_on", "depends_on"),
            ("related", "related"),
            ("conflict_ids", "has_conflict"),
        ):
            for target in meta.get(field) or []:
                relation_rows.append({
                    "source": component_id,
                    "relation": relation,
                    "target": target,
                })
        for field, relation in (
            ("variant_of", "variant_of"),
            ("supersedes", "supersedes"),
            ("deprecated_by", "deprecated_by"),
        ):
            if meta.get(field):
                relation_rows.append({
                    "source": component_id,
                    "relation": relation,
                    "target": meta[field],
                })

    component_rows.sort(key=lambda row: row["id"])
    relation_rows.sort(key=lambda row: (row["source"], row["relation"], row["target"]))
    for values in by_type.values():
        values.sort()
    write_jsonl(index_root / "components.jsonl", component_rows)
    write_jsonl(root / "relations.jsonl", relation_rows)
    (index_root / "by-type.json").write_text(
        json.dumps(dict(sorted(by_type.items())), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"索引组件：{len(component_rows)}；关系：{len(relation_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
