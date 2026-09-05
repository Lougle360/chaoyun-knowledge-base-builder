#!/usr/bin/env python3
"""超云知识库构建器统一入口。

确定性阶段由脚本执行；语义聚类、类型判定和组件正文由 Agent 按 Skill 规范完成。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

BUILDER_VERSION = "1.0.0"
SCRIPT_DIR = Path(__file__).resolve().parent
SUBPROCESS_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}
PROFILE_RISK = {
    "general": "low",
    "education": "low",
    "research": "medium",
    "technical": "medium",
    "operations": "medium",
    "business": "medium",
    "legal": "high",
    "medical": "high",
    "finance": "high",
    "engineering-safety": "high",
}
PROFILE_DOMAIN = {
    "legal": ["legal"],
    "medical": ["medical"],
    "finance": ["finance"],
    "engineering-safety": ["engineering", "safety"],
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_id() -> str:
    return datetime.now(timezone.utc).strftime("run-%Y%m%dT%H%M%SZ")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def fingerprint(root: Path) -> str:
    rows = load_jsonl(root / "sources.jsonl")
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        source_id = str(row.get("source_id", ""))
        current = latest.get(source_id)
        if source_id and (
            current is None
            or str(row.get("ingested_at", "")) >= str(current.get("ingested_at", ""))
        ):
            latest[source_id] = row
    values = sorted(
        f"{row.get('source_id')}@{row.get('revision_id')}:{row.get('sha256')}"
        for row in latest.values()
        if row.get("status") == "ingested"
    )
    return hashlib.sha256("\n".join(values).encode("utf-8")).hexdigest()


def package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "not-installed"


def manifest(root: Path, kb_id: str, current_run: str, status: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "builder_version": BUILDER_VERSION,
        "run_id": current_run,
        "kb_id": kb_id,
        "created_at": now_iso(),
        "input_fingerprint": fingerprint(root),
        "taxonomy_version": "2.2.0",
        "component_schema_version": "2.2",
        "pipeline_schema_version": "1.0",
        "profile_version": "1.0",
        "tool_versions": {
            "python": sys.version.split()[0],
            "pyyaml": package_version("PyYAML"),
            "jsonschema": package_version("jsonschema"),
            "markitdown": package_version("markitdown"),
        },
        "metrics": {},
        "blocking_issues": [],
        "release_status": status,
        "previous_release": None,
        "extensions": {},
    }


def initialize(args: argparse.Namespace) -> int:
    root = args.output.resolve()
    profile_path = root / "kb-profile.yaml"
    if profile_path.exists() and not args.force:
        print(f"错误：{profile_path} 已存在；使用 --force 才能覆盖", file=sys.stderr)
        return 2
    root.mkdir(parents=True, exist_ok=True)
    for directory in ("components", "derived", "indexes", "validation", "state", "quarantine"):
        (root / directory).mkdir(exist_ok=True)
    risk_level = args.risk_level or PROFILE_RISK[args.profile]
    domains = list(PROFILE_DOMAIN.get(args.profile, []))
    if args.privacy and "privacy" not in domains:
        domains.append("privacy")
    profile = {
        "schema_version": "1.0",
        "kb_id": args.kb_id,
        "title": args.title,
        "central_question": args.question,
        "audiences": args.audience or ["知识库使用者"],
        "target_tasks": args.task or ["检索", "问答"],
        "included_topics": args.include,
        "excluded_topics": args.exclude or [],
        "boundary_examples": {},
        "domain_profile": args.profile,
        "risk_profile": {
            "level": risk_level,
            "domains": domains,
            "jurisdictions": args.jurisdiction or [],
        },
        "relevance": {
            "labels": ["include", "contextual", "exclude", "uncertain"],
            "review_below": args.review_below,
        },
        "release_policy": {
            "unresolved_conflicts_allowed": args.allow_open_conflicts,
            "professional_approval_required": risk_level in {"high", "critical"},
            "minimum_review_rate": 1.0,
        },
        "extensions": {},
    }
    profile_path.write_text(
        yaml.safe_dump(profile, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    for filename in ("sources.jsonl", "fragments.jsonl", "mappings.jsonl", "conflicts.jsonl"):
        path = root / filename
        if not path.exists() or args.force:
            path.write_text("", encoding="utf-8")
    current_run = run_id()
    (root / "release-manifest.json").write_text(
        json.dumps(manifest(root, args.kb_id, current_run, "draft"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"已初始化：{root}")
    print("下一步：运行 ingest，随后由 Agent 处理待复核碎片、映射和组件。")
    return 0


def call_script(script: str, arguments: list[str]) -> int:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / script), *arguments],
        env=SUBPROCESS_ENV,
        check=False,
    )
    return completed.returncode


def ingest(args: argparse.Namespace) -> int:
    arguments = [str(args.input), str(args.output)]
    if args.max_chars:
        arguments += ["--max-chars", str(args.max_chars)]
    if args.extensions:
        arguments += ["--extensions", args.extensions]
    if args.limit:
        arguments += ["--limit", str(args.limit)]
    result = call_script("ingest_sources.py", arguments)
    root = args.output.resolve()
    profile_path = root / "kb-profile.yaml"
    if profile_path.is_file():
        profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
        manifest_path = root / "release-manifest.json"
        previous = (
            json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest_path.is_file()
            else {}
        )
        refreshed = manifest(root, str(profile["kb_id"]), run_id(), "draft")
        if previous.get("release_status") == "released":
            refreshed["previous_release"] = previous.get("run_id")
        manifest_path.write_text(
            json.dumps(refreshed, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    call_script("create_review_queue.py", [str(args.output)])
    return result


def review(args: argparse.Namespace) -> int:
    return call_script("create_review_queue.py", [str(args.output)])


def index(args: argparse.Namespace) -> int:
    return call_script("build_indexes.py", [str(args.output)])


def validate(args: argparse.Namespace) -> int:
    arguments = [str(args.output), "--pipeline", "--report-json", "validation/report.json"]
    if args.strict:
        arguments.append("--strict-v2")
    if args.release:
        arguments.append("--release")
    return call_script("validate_components.py", arguments)


def release(args: argparse.Namespace) -> int:
    root = args.output.resolve()
    profile_path = root / "kb-profile.yaml"
    if not profile_path.is_file():
        print("错误：缺少 kb-profile.yaml", file=sys.stderr)
        return 2
    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    current_run = run_id()
    draft = manifest(root, str(profile["kb_id"]), current_run, "ready")
    manifest_path = root / "release-manifest.json"
    manifest_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    index_result = call_script("build_indexes.py", [str(root)])
    if index_result:
        draft["release_status"] = "blocked"
        draft["blocking_issues"] = ["INDEX_BUILD: 索引生成失败"]
        manifest_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
        return index_result
    result = call_script(
        "validate_components.py",
        [
            str(root),
            "--pipeline",
            "--release",
            "--strict-v2",
            "--report-json",
            "validation/report.json",
        ],
    )
    report_path = root / "validation" / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
    draft["metrics"] = report.get("metrics", {})
    draft["blocking_issues"] = [
        f"{item.get('code')}: {item.get('message')}"
        for item in report.get("errors", [])
    ]
    draft["release_status"] = (
        "released" if result == 0 and args.publish else "ready" if result == 0 else "blocked"
    )
    manifest_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"发布状态：{draft['release_status']}")
    return result


def status(args: argparse.Namespace) -> int:
    root = args.output.resolve()
    if not root.is_dir():
        print(f"错误：目录不存在：{root}", file=sys.stderr)
        return 2
    counts = {
        "sources": len(load_jsonl(root / "sources.jsonl")),
        "fragments": len(load_jsonl(root / "fragments.jsonl")),
        "mappings": len(load_jsonl(root / "mappings.jsonl")),
        "conflicts": len(load_jsonl(root / "conflicts.jsonl")),
        "components": len(list((root / "components").rglob("*.md"))) if (root / "components").is_dir() else 0,
    }
    report_path = root / "validation" / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
    manifest_path = root / "release-manifest.json"
    release_data = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    print(json.dumps({
        **counts,
        "last_validation_passed": report.get("passed"),
        "release_status": release_data.get("release_status", "missing"),
        "blocking_issues": len(release_data.get("blocking_issues", [])),
    }, ensure_ascii=False, indent=2))
    return 0


def run_all(args: argparse.Namespace) -> int:
    root = args.output.resolve()
    if not (root / "kb-profile.yaml").is_file():
        init_args = argparse.Namespace(
            output=args.output,
            kb_id=args.kb_id,
            title=args.title,
            question=args.question,
            audience=args.audience,
            task=args.task,
            include=args.include,
            exclude=args.exclude,
            profile=args.profile,
            risk_level=args.risk_level,
            jurisdiction=args.jurisdiction,
            privacy=args.privacy,
            review_below=args.review_below,
            allow_open_conflicts=args.allow_open_conflicts,
            force=False,
        )
        result = initialize(init_args)
        if result:
            return result
    ingest_args = argparse.Namespace(
        input=args.input,
        output=args.output,
        max_chars=args.max_chars,
        extensions=args.extensions,
        limit=args.limit,
    )
    result = ingest(ingest_args)
    if result:
        return result
    validate_args = argparse.Namespace(output=args.output, strict=False, release=False)
    return validate(validate_args)


def add_profile_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--kb-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--question", required=True)
    parser.add_argument("--include", action="append", required=True)
    parser.add_argument("--exclude", action="append")
    parser.add_argument("--audience", action="append")
    parser.add_argument(
        "--task",
        action="append",
        choices=["学习", "检索", "问答", "研究", "决策辅助", "应用工作流"],
    )
    parser.add_argument("--profile", choices=list(PROFILE_RISK), default="general")
    parser.add_argument("--risk-level", choices=["low", "medium", "high", "critical"])
    parser.add_argument("--jurisdiction", action="append")
    parser.add_argument("--privacy", action="store_true")
    parser.add_argument("--review-below", type=float, default=0.75)
    parser.add_argument("--allow-open-conflicts", action="store_true")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="超云知识库构建器")
    commands = parser.add_subparsers(dest="command", required=True)

    init_parser = commands.add_parser("init", help="建立主题画像和工作目录")
    init_parser.add_argument("output", type=Path)
    add_profile_arguments(init_parser)
    init_parser.add_argument("--force", action="store_true")
    init_parser.set_defaults(handler=initialize)

    ingest_parser = commands.add_parser("ingest", help="摄取来源并生成碎片")
    ingest_parser.add_argument("input", type=Path)
    ingest_parser.add_argument("output", type=Path)
    ingest_parser.add_argument("--max-chars", type=int, default=4000)
    ingest_parser.add_argument("--extensions")
    ingest_parser.add_argument("--limit", type=int)
    ingest_parser.set_defaults(handler=ingest)

    validate_parser = commands.add_parser("validate", help="执行完整交叉校验")
    validate_parser.add_argument("output", type=Path)
    validate_parser.add_argument("--strict", action="store_true")
    validate_parser.add_argument("--release", action="store_true")
    validate_parser.set_defaults(handler=validate)

    release_parser = commands.add_parser("release", help="执行发布门禁并生成清单")
    release_parser.add_argument("output", type=Path)
    release_parser.add_argument("--publish", action="store_true")
    release_parser.set_defaults(handler=release)

    status_parser = commands.add_parser("status", help="查看阶段状态")
    status_parser.add_argument("output", type=Path)
    status_parser.set_defaults(handler=status)

    review_parser = commands.add_parser("review", help="生成待复核队列")
    review_parser.add_argument("output", type=Path)
    review_parser.set_defaults(handler=review)

    index_parser = commands.add_parser("index", help="重建组件索引和关系")
    index_parser.add_argument("output", type=Path)
    index_parser.set_defaults(handler=index)

    run_parser = commands.add_parser("run", help="初始化、摄取并验证准备阶段")
    run_parser.add_argument("input", type=Path)
    run_parser.add_argument("output", type=Path)
    add_profile_arguments(run_parser)
    run_parser.add_argument("--max-chars", type=int, default=4000)
    run_parser.add_argument("--extensions")
    run_parser.add_argument("--limit", type=int, default=3, help="默认先摄取 3 个文件试点；0 表示不限")
    run_parser.set_defaults(handler=run_all)

    args = parser.parse_args()
    if hasattr(args, "review_below") and not 0 <= args.review_below <= 1:
        parser.error("--review-below 必须在 0 到 1 之间")
    if hasattr(args, "limit") and args.limit is not None and args.limit < 0:
        parser.error("--limit 不能小于 0")
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
