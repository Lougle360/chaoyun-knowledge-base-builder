#!/usr/bin/env python3
"""跨格式摄取、来源登记、派生文本与碎片生成。

原始文件只读。文本格式直接读取；其他格式使用 Microsoft MarkItDown。
失败来源写入 sources.jsonl 和 validation/ingest-report.json，不会静默跳过。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml

BUILDER_VERSION = "1.0.0"
TEXT_EXTENSIONS = {".md", ".txt", ".csv", ".json", ".xml", ".yaml", ".yml", ".html", ".htm"}
DEFAULT_EXTENSIONS = TEXT_EXTENSIONS | {
    ".pdf", ".docx", ".pptx", ".xlsx", ".xls", ".epub",
    ".jpg", ".jpeg", ".png", ".gif", ".webp",
    ".wav", ".mp3", ".m4a", ".mp4",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_token(value: str, length: int = 12) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def slug(value: str, fallback: str = "source") -> str:
    result = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return (result or fallback)[:40]


def read_text_loss_aware(path: Path) -> tuple[str, list[str]]:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "utf-16"):
        try:
            text = raw.decode(encoding)
            issues = [] if encoding in {"utf-8", "utf-8-sig"} else [f"使用 {encoding} 解码"]
            return text, issues
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), ["无法可靠识别编码，已替换非法字符"]


def markitdown_version() -> str:
    try:
        return importlib.metadata.version("markitdown")
    except importlib.metadata.PackageNotFoundError:
        return "not-installed"


def convert_source(path: Path) -> tuple[str, str, str, list[str]]:
    if path.suffix.lower() in TEXT_EXTENSIONS:
        text, issues = read_text_loss_aware(path)
        return text, "direct-text", BUILDER_VERSION, issues

    try:
        from markitdown import MarkItDown
    except ImportError as exc:
        raise RuntimeError(
            "该格式需要 MarkItDown；运行 `python -m pip install \"markitdown[all]\"`"
        ) from exc

    try:
        result = MarkItDown().convert(str(path))
    except BaseException as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise RuntimeError(f"MarkItDown 转换失败：{exc}") from exc
    text = (result.text_content or "").strip()
    if not text:
        raise RuntimeError("转换结果为空")
    return text, "markitdown", markitdown_version(), []


def normalize_text(text: str) -> tuple[str, list[str]]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    log: list[str] = []
    if normalized != text:
        log.append("统一换行符为 LF")
    cleaned = re.sub(r"[ \t]+\n", "\n", normalized)
    if cleaned != normalized:
        log.append("移除行尾空白")
    cleaned = re.sub(r"\n{4,}", "\n\n\n", cleaned).strip() + "\n"
    return cleaned, log


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"{path} 第 {number} 行不是有效 JSON：{exc.msg}") from exc
        if not isinstance(row, dict):
            raise RuntimeError(f"{path} 第 {number} 行必须是 JSON 对象")
        rows.append(row)
    return rows


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]], keys: tuple[str, ...]) -> None:
    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        unique[tuple(row.get(key) for key in keys)] = row
    ordered = sorted(unique.values(), key=lambda row: tuple(str(row.get(key, "")) for key in keys))
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in ordered),
        encoding="utf-8",
    )


def load_profile(root: Path) -> dict[str, Any]:
    path = root / "kb-profile.yaml"
    if not path.is_file():
        raise RuntimeError("缺少 kb-profile.yaml；请先运行 build_kb.py init")
    profile = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(profile, dict):
        raise RuntimeError("kb-profile.yaml 必须是 YAML 对象")
    return profile


def relevance_for(text: str, profile: dict[str, Any]) -> dict[str, Any]:
    lowered = text.lower()
    included = [str(item).lower() for item in profile.get("included_topics", [])]
    excluded = [str(item).lower() for item in profile.get("excluded_topics", [])]
    include_hits = [item for item in included if item and item in lowered]
    exclude_hits = [item for item in excluded if item and item in lowered]
    threshold = float((profile.get("relevance") or {}).get("review_below", 0.75))

    if exclude_hits and not include_hits:
        return {
            "label": "exclude",
            "confidence": 0.9,
            "reason": f"命中排除主题：{', '.join(exclude_hits[:3])}",
            "review_status": "auto" if 0.9 >= threshold else "pending",
        }
    if include_hits:
        confidence = min(0.95, 0.7 + 0.05 * len(include_hits))
        return {
            "label": "include",
            "confidence": confidence,
            "reason": f"命中纳入主题：{', '.join(include_hits[:3])}",
            "review_status": "auto" if confidence >= threshold else "pending",
        }
    return {
        "label": "uncertain",
        "confidence": 0.5,
        "reason": "未命中明确的纳入或排除主题，需要语义复核",
        "review_status": "pending",
    }


def split_fragments(
    text: str,
    source_id: str,
    revision_id: str,
    profile: dict[str, Any],
    run_id: str,
    max_chars: int,
) -> list[dict[str, Any]]:
    lines = text.splitlines()
    fragments: list[dict[str, Any]] = []
    heading_path: list[str] = []
    block_lines: list[str] = []
    block_start = 1

    def flush(end_line: int) -> None:
        nonlocal block_lines, block_start
        raw = "\n".join(block_lines).strip()
        block_lines = []
        if not raw:
            return
        pieces = [raw[i:i + max_chars] for i in range(0, len(raw), max_chars)]
        for piece_index, piece in enumerate(pieces, 1):
            fingerprint = sha256_bytes(piece.encode("utf-8"))
            fragment_id = (
                f"frag.{source_id.removeprefix('src.')}."
                f"{revision_id.removeprefix('rev.')}.{len(fragments) + 1:05d}"
            )
            relevance = relevance_for(piece, profile)
            disposition = "excluded" if relevance["label"] == "exclude" else "deferred"
            reason = (
                relevance["reason"]
                if disposition == "excluded"
                else "等待跨来源聚类、组件映射与语义复核"
            )
            fragments.append(
                {
                    "schema_version": "1.0",
                    "fragment_id": fragment_id,
                    "source_id": source_id,
                    "revision_id": revision_id,
                    "anchor": {
                        "kind": "line_range",
                        "start": block_start,
                        "end": end_line,
                    },
                    "raw_text": piece,
                    "raw_sha256": fingerprint,
                    "normalized_text": re.sub(r"[ \t]+", " ", piece).strip(),
                    "normalization_log": [] if piece_index == 1 else ["超长块按字符上限续切"],
                    "language": "zh-CN" if re.search(r"[\u4e00-\u9fff]", piece) else "und",
                    "heading_path": list(heading_path),
                    "relevance": relevance,
                    "disposition": disposition,
                    "disposition_reason": reason,
                    "run_id": run_id,
                    "extensions": {},
                }
            )

    for line_number, line in enumerate(lines, 1):
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if heading:
            flush(line_number - 1)
            level = len(heading.group(1))
            heading_path[:] = heading_path[: level - 1]
            heading_path.append(heading.group(2))
            block_start = line_number
            block_lines = [line]
        elif not line.strip():
            flush(line_number - 1)
            block_start = line_number + 1
        else:
            if not block_lines:
                block_start = line_number
            block_lines.append(line)
    flush(len(lines))
    return fragments


def collect_files(input_root: Path, extensions: set[str]) -> list[Path]:
    return sorted(
        path
        for path in input_root.rglob("*")
        if path.is_file() and path.suffix.lower() in extensions
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="摄取零碎多格式资料并生成来源与碎片清单")
    parser.add_argument("input", type=Path, help="只读来源目录")
    parser.add_argument("output", type=Path, help="知识库工作目录")
    parser.add_argument("--run-id", help="运行 ID；默认按 UTC 时间生成")
    parser.add_argument("--max-chars", type=int, default=4000, help="单碎片最大字符数")
    parser.add_argument("--extensions", help="逗号分隔扩展名，例如 .md,.pdf,.docx")
    parser.add_argument("--limit", type=int, help="最多摄取前 N 个文件；0 表示不限")
    args = parser.parse_args()

    input_root = args.input.resolve()
    output_root = args.output.resolve()
    if not input_root.is_dir():
        print(f"错误：来源目录不存在：{input_root}", file=sys.stderr)
        return 2
    if input_root == output_root or input_root in output_root.parents:
        print("错误：输出目录不能位于来源目录内部", file=sys.stderr)
        return 2
    if args.max_chars < 200:
        print("错误：--max-chars 不能小于 200", file=sys.stderr)
        return 2

    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "derived").mkdir(exist_ok=True)
    (output_root / "validation").mkdir(exist_ok=True)
    (output_root / "state").mkdir(exist_ok=True)
    try:
        profile = load_profile(output_root)
    except RuntimeError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2

    run_id = args.run_id or datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%SZ")
    extensions = (
        {item.strip().lower() for item in args.extensions.split(",") if item.strip()}
        if args.extensions
        else DEFAULT_EXTENSIONS
    )
    extensions = {item if item.startswith(".") else f".{item}" for item in extensions}
    files = collect_files(input_root, extensions)
    if args.limit and args.limit > 0:
        files = files[: args.limit]

    sources_path = output_root / "sources.jsonl"
    fragments_path = output_root / "fragments.jsonl"
    existing_sources = load_jsonl(sources_path)
    existing_fragments = load_jsonl(fragments_path)
    latest_by_source: dict[str, dict[str, Any]] = {}
    for row in existing_sources:
        source_key = str(row.get("source_id", ""))
        if not source_key:
            continue
        current = latest_by_source.get(source_key)
        if current is None or str(row.get("ingested_at", "")) >= str(current.get("ingested_at", "")):
            latest_by_source[source_key] = row
    prior_paths = {
        row["path"]: row
        for row in latest_by_source.values()
        if row.get("status") == "ingested" and row.get("path")
    }
    current_paths: set[str] = set()
    new_sources: list[dict[str, Any]] = []
    new_fragments: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    reused = 0

    for path in files:
        relative = path.relative_to(input_root).as_posix()
        current_paths.add(str(path))
        original_hash = sha256_file(path)
        source_id = f"src.{slug(path.stem)}.{stable_token(relative.lower())}"
        revision_id = f"rev.{original_hash[:16]}"
        latest = latest_by_source.get(source_id)
        if latest and latest.get("status") == "tombstone":
            revision_id = f"{revision_id}.restored.{stable_token(run_id, 8)}"
        existing = next(
            (
                row
                for row in existing_sources
                if row.get("source_id") == source_id
                and row.get("revision_id") == revision_id
                and row.get("status") == "ingested"
            ),
            None,
        )
        if existing:
            reused += 1
            continue

        derived_rel = Path("derived") / source_id / f"{revision_id}.md"
        derived_path = output_root / derived_rel
        try:
            converted, parser_name, parser_version, issues = convert_source(path)
            if parser_name == "markitdown":
                issues.append("通用转换保证派生文本行锚点；原生页码、时间码或单元格需格式专用复核")
            normalized, normalization_log = normalize_text(converted)
            issues.extend(normalization_log)
            derived_path.parent.mkdir(parents=True, exist_ok=True)
            derived_path.write_text(normalized, encoding="utf-8", newline="\n")
            quality = max(0.1, 1.0 - 0.1 * len(issues))
            source_row = {
                "schema_version": "1.0",
                "source_id": source_id,
                "revision_id": revision_id,
                "path": str(path),
                "format": path.suffix.lower().lstrip("."),
                "sha256": original_hash,
                "title": path.stem,
                "author": None,
                "published_at": None,
                "effective_at": None,
                "license": None,
                "parser": {"name": parser_name, "version": parser_version},
                "quality": {"score": quality, "issues": issues},
                "derived_text_path": derived_rel.as_posix(),
                "status": "ingested",
                "error": None,
                "ingested_at": now_iso(),
                "run_id": run_id,
                "extensions": {
                    "source_relative_path": relative,
                    "native_anchor_available": parser_name == "direct-text",
                },
            }
            new_sources.append(source_row)
            new_fragments.extend(
                split_fragments(
                    normalized,
                    source_id,
                    revision_id,
                    profile,
                    run_id,
                    args.max_chars,
                )
            )
        except Exception as exc:
            error = str(exc)
            failures.append({"path": str(path), "error": error})
            new_sources.append(
                {
                    "schema_version": "1.0",
                    "source_id": source_id,
                    "revision_id": revision_id,
                    "path": str(path),
                    "format": path.suffix.lower().lstrip("."),
                    "sha256": original_hash,
                    "title": path.stem,
                    "author": None,
                    "published_at": None,
                    "effective_at": None,
                    "license": None,
                    "parser": {"name": "unavailable", "version": "unknown"},
                    "quality": {"score": 0, "issues": ["转换失败"]},
                    "derived_text_path": None,
                    "status": "failed",
                    "error": error,
                    "ingested_at": now_iso(),
                    "run_id": run_id,
                    "extensions": {"source_relative_path": relative},
                }
            )

    tombstones: list[dict[str, Any]] = []
    for old_path, old in prior_paths.items():
        if old_path in current_paths or not Path(old_path).is_relative_to(input_root):
            continue
        tombstone_id = f"rev.tombstone.{stable_token(run_id + old_path, 16)}"
        tombstones.append(
            {
                **old,
                "revision_id": tombstone_id,
                "sha256": sha256_bytes(b""),
                "derived_text_path": None,
                "status": "tombstone",
                "error": "来源在本次扫描中不存在，保留删除标记",
                "ingested_at": now_iso(),
                "run_id": run_id,
            }
        )

    write_jsonl(
        sources_path,
        [*existing_sources, *new_sources, *tombstones],
        ("source_id", "revision_id"),
    )
    write_jsonl(
        fragments_path,
        [*existing_fragments, *new_fragments],
        ("fragment_id",),
    )
    state = {
        "builder_version": BUILDER_VERSION,
        "run_id": run_id,
        "input_root": str(input_root),
        "scanned_at": now_iso(),
        "files": {str(path): sha256_file(path) for path in files},
    }
    (output_root / "state" / "input-state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report = {
        "run_id": run_id,
        "input_root": str(input_root),
        "scanned_files": len(files),
        "new_source_revisions": len(new_sources),
        "reused_source_revisions": reused,
        "new_fragments": len(new_fragments),
        "tombstones": len(tombstones),
        "failures": failures,
        "passed": not failures,
    }
    (output_root / "validation" / "ingest-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
