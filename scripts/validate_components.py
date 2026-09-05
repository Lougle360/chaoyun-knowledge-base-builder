#!/usr/bin/env python3
"""校验组件、来源、碎片、映射、冲突、风险与发布契约。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError as exc:
    print("缺少依赖：python -m pip install -r scripts/requirements.txt", file=sys.stderr)
    raise SystemExit(2) from exc

BUILDER_VERSION = "1.0.0"
RISK_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}
PROFILE_MIN_RISK = {
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
    "legal": "legal",
    "medical": "medical",
    "finance": "finance",
    "engineering-safety": "engineering",
}
TYPE_CN = {
    "concept": "概念类", "principle": "原理类", "viewpoint": "观点类",
    "misconception": "误区类", "guideline": "准则类", "framework": "框架类",
    "rule": "规则类", "workflow": "流程类", "tool": "工具类",
    "solution": "方案类", "scene": "场景类", "case": "案例类",
    "analogy": "类比类", "story": "故事类", "boundary": "边界类",
    "source": "溯源类", "data": "数据类", "quote": "金句类",
    "paradigm": "范式类", "course": "课程类",
}
CONTRACTS = {
    "concept": ["定义", "为什么", "构成", "识别线索", "易混", "应用入口", "边界"],
    "principle": ["原理陈述", "机制", "适用范围", "推论", "不可推论", "应用入口"],
    "viewpoint": ["观点陈述", "针对的问题", "理由", "服务目标", "边界声明"],
    "misconception": ["误区陈述", "触发情境", "为什么错", "正确理解", "行动指引", "防复发"],
    "guideline": ["准则条款", "适用角色", "违反后果", "执行动作", "例外"],
    "framework": ["框架目的", "使用时机", "组成部分", "部分间关系", "使用顺序", "输入", "边界"],
    "rule": ["适用条件", "观察输入", "规则本体", "结论强度", "例外", "边界", "输出格式"],
    "workflow": ["任务目标", "流程图", "前置条件", "步骤", "分支", "停止", "产物", "复核"],
    "tool": ["工具用途", "输入", "使用方法", "输出", "输出解读", "限制"],
    "solution": ["问题", "进入条件", "实施动作", "产物", "风险", "回退", "验收"],
    "scene": ["场景", "进入条件", "排除条件", "输入", "调用", "输出", "停止"],
    "case": ["案例目的", "事实", "信息缺口", "分析过程", "结论", "替代解释", "边界"],
    "analogy": ["本体", "喻体", "映射", "帮助理解", "失效边界", "应用入口"],
    "story": ["故事目的", "背景", "冲突", "行动", "结果", "启示", "边界"],
    "boundary": ["风险", "触发条件", "禁止", "停止", "转介", "记录"],
    "source": ["来源身份", "版本", "原文位置", "引用链", "可信状态", "限制"],
    "data": ["用途", "字段", "口径", "来源", "时间范围", "缺失", "更新", "限制"],
    "quote": ["原文", "出处语境", "关联知识", "解读", "适用", "不适用"],
    "paradigm": ["目标场景", "输入", "门禁", "任务编排", "分支", "产物", "停止", "复核", "组件清单"],
    "course": ["课程目标", "先修", "学习路径", "任务", "完成标准", "下一步", "边界"],
}


def issue(level: str, code: str, path: str, message: str) -> dict[str, str]:
    return {"level": level, "code": code, "path": path, "message": message}


def sha256_file(path: Path, cache: dict[Path, str]) -> str:
    resolved = path.resolve()
    if resolved not in cache:
        digest = hashlib.sha256()
        with resolved.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        cache[resolved] = digest.hexdigest()
    return cache[resolved]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    rows: list[dict[str, Any]] = []
    problems: list[dict[str, str]] = []
    if not path.is_file():
        return rows, [issue("error", "FILE_MISSING", str(path), "文件不存在")]
    with path.open("r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                problems.append(issue("error", "JSONL_PARSE", str(path), f"第 {number} 行：{exc.msg}"))
                continue
            if not isinstance(value, dict):
                problems.append(issue("error", "JSONL_OBJECT", str(path), f"第 {number} 行不是对象"))
                continue
            value["_line"] = number
            rows.append(value)
    return rows, problems


def clean_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if not key.startswith("_")}


def schema_problems(
    validator: Draft202012Validator,
    value: Any,
    path: str,
    code: str,
) -> list[dict[str, str]]:
    problems: list[dict[str, str]] = []
    for error in sorted(validator.iter_errors(value), key=lambda item: list(item.path)):
        location = ".".join(str(item) for item in error.path) or "$"
        problems.append(issue("error", code, path, f"{location}: {error.message}"))
    return problems


def parse_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\s*\r?\n(.*?)\r?\n---\s*\r?\n?(.*)$", text, re.S)
    if not match:
        raise ValueError("缺少 YAML frontmatter")
    meta = yaml.safe_load(match.group(1))
    if not isinstance(meta, dict):
        raise ValueError("frontmatter 必须是对象")
    return meta, match.group(2)


def section_content(body: str, keyword: str) -> str | None:
    matches = list(re.finditer(r"^(#{1,6})\s+(.+?)\s*$", body, re.M))
    for index, match in enumerate(matches):
        if keyword not in match.group(2):
            continue
        start = match.end()
        level = len(match.group(1))
        end = len(body)
        for later in matches[index + 1:]:
            if len(later.group(1)) <= level:
                end = later.start()
                break
        content = re.sub(r"<!--.*?-->", "", body[start:end], flags=re.S).strip()
        return content
    return None


def resolve(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def validate_component(
    path: Path,
    root: Path,
    validator: Draft202012Validator,
    strict: bool,
    require_mermaid: bool,
    hash_cache: dict[Path, str],
) -> tuple[list[dict[str, str]], dict[str, Any] | None]:
    rel = path.relative_to(root).as_posix()
    problems: list[dict[str, str]] = []
    try:
        meta, body = parse_frontmatter(path)
    except (UnicodeDecodeError, ValueError, yaml.YAMLError) as exc:
        return [issue("error", "FRONTMATTER_PARSE", rel, str(exc))], None
    problems.extend(schema_problems(validator, meta, rel, "COMPONENT_SCHEMA"))

    expected_cn = TYPE_CN.get(str(meta.get("type")))
    if expected_cn and meta.get("type_cn") != expected_cn:
        problems.append(issue("error", "TYPE_CN", rel, f"type_cn 应为 `{expected_cn}`"))

    if strict and meta.get("role") == "leaf":
        for heading in CONTRACTS.get(str(meta.get("type")), []):
            content = section_content(body, heading)
            if content is None:
                problems.append(issue("error", "TYPE_CONTRACT", rel, f"缺少章节「{heading}」"))
            elif not content:
                problems.append(issue("error", "EMPTY_SECTION", rel, f"章节「{heading}」为空"))

    mermaid = re.findall(r"```mermaid\s*\r?\n(.*?)```", body, re.S)
    if meta.get("type") == "workflow" and meta.get("role") == "leaf" and not mermaid:
        problems.append(issue("error", "WORKFLOW_MERMAID", rel, "流程叶子组件缺少 Mermaid"))
    if require_mermaid and meta.get("role") == "leaf" and not mermaid:
        problems.append(issue("error", "LEAF_MERMAID", rel, "可视化审计要求叶子组件含 Mermaid"))
    for block in mermaid if require_mermaid else []:
        if len(re.findall(r"-->|---|-.->|==>", block)) < 2:
            problems.append(issue("error", "MERMAID_RELATION", rel, "Mermaid 至少需要两个语义关系"))

    if meta.get("type") == "quote" and not (meta.get("related") or meta.get("depends_on")):
        problems.append(issue("error", "QUOTE_RELATION", rel, "金句缺少关联知识组件"))

    for provenance in meta.get("provenance") or []:
        source_file = provenance.get("source_file")
        if not source_file:
            problems.append(issue("error", "PROVENANCE_FILE", rel, "provenance 缺少 source_file"))
            continue
        source_path = resolve(root, source_file)
        if not source_path.is_file():
            problems.append(issue("error", "SOURCE_MISSING", rel, f"来源不存在：{source_file}"))
            continue
        expected_hash = provenance.get("source_sha256")
        if not expected_hash or sha256_file(source_path, hash_cache) != expected_hash:
            problems.append(issue("error", "SOURCE_HASH", rel, f"来源哈希缺失或不一致：{source_file}"))
        if source_path.suffix.lower() in {".md", ".txt"}:
            line_count = len(source_path.read_text(encoding="utf-8").splitlines())
            for anchor in provenance.get("anchors") or []:
                if anchor.get("kind") == "line_range":
                    start, end = anchor.get("start"), anchor.get("end")
                    if not isinstance(start, int) or not isinstance(end, int) or not (
                        1 <= start <= end <= line_count
                    ):
                        problems.append(
                            issue("error", "SOURCE_ANCHOR", rel, f"锚点越界：{start}-{end}/{line_count}")
                        )

    for target in re.findall(r"\[[^\]]+\]\(([^)#]+)(?:#[^)]+)?\)", body):
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        if not (path.parent / target).resolve().exists():
            problems.append(issue("error", "DEAD_LINK", rel, f"死链：{target}"))
    return problems, meta


def duplicate_values(rows: Iterable[dict[str, Any]], key: str) -> list[str]:
    values = [str(row[key]) for row in rows if row.get(key) is not None]
    return [value for value, count in Counter(values).items() if count > 1]


def dependency_cycles(graph: dict[str, list[str]]) -> list[list[str]]:
    cycles: list[list[str]] = []
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def walk(node: str) -> None:
        if node in visiting:
            cycles.append(stack[stack.index(node):] + [node])
            return
        if node in visited:
            return
        visiting.add(node)
        stack.append(node)
        for target in graph.get(node, []):
            if target in graph:
                walk(target)
        stack.pop()
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        walk(node)
    return cycles


def object_validator(schema: dict[str, Any], definition: str) -> Draft202012Validator:
    wrapper = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$ref": f"#/$defs/{definition}",
        "$defs": schema["$defs"],
    }
    return Draft202012Validator(wrapper, format_checker=FormatChecker())


def validate_pipeline(
    root: Path,
    pipeline_schema: dict[str, Any],
    components: dict[str, dict[str, Any]],
    hash_cache: dict[Path, str],
    release_mode: bool,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    problems: list[dict[str, str]] = []
    metrics: dict[str, Any] = {}
    profile_path = root / "kb-profile.yaml"
    manifest_path = root / "release-manifest.json"
    if not profile_path.is_file():
        return [issue("error", "PROFILE_MISSING", "kb-profile.yaml", "缺少主题画像")], metrics
    try:
        profile = load_yaml(profile_path)
    except Exception as exc:
        return [issue("error", "PROFILE_PARSE", "kb-profile.yaml", str(exc))], metrics
    problems.extend(
        schema_problems(object_validator(pipeline_schema, "kbProfile"), profile, "kb-profile.yaml", "PROFILE_SCHEMA")
    )

    collections: dict[str, list[dict[str, Any]]] = {}
    specs = {
        "sources": ("sources.jsonl", "sourceRevision", "source_id"),
        "fragments": ("fragments.jsonl", "fragment", "fragment_id"),
        "mappings": ("mappings.jsonl", "mappingDecision", "mapping_id"),
        "conflicts": ("conflicts.jsonl", "conflict", "conflict_id"),
    }
    for name, (filename, definition, id_key) in specs.items():
        rows, row_problems = load_jsonl(root / filename)
        problems.extend(row_problems)
        validator = object_validator(pipeline_schema, definition)
        for row in rows:
            problems.extend(
                schema_problems(
                    validator,
                    clean_row(row),
                    f"{filename}:{row.get('_line')}",
                    f"{name.upper()}_SCHEMA",
                )
            )
        for duplicate in duplicate_values(rows, id_key):
            problems.append(issue("error", f"{name.upper()}_DUPLICATE", filename, duplicate))
        collections[name] = rows

    sources = collections["sources"]
    fragments = collections["fragments"]
    mappings = collections["mappings"]
    conflicts = collections["conflicts"]
    source_keys = {(row.get("source_id"), row.get("revision_id")): row for row in sources}
    latest_source_by_id: dict[str, dict[str, Any]] = {}
    for row in sources:
        source_id = str(row.get("source_id", ""))
        current = latest_source_by_id.get(source_id)
        if source_id and (
            current is None
            or str(row.get("ingested_at", "")) >= str(current.get("ingested_at", ""))
        ):
            latest_source_by_id[source_id] = row
    fragment_by_id = {row.get("fragment_id"): row for row in fragments}

    failed_sources = 0
    for row in sources:
        row_path = f"sources.jsonl:{row.get('_line')}"
        status = row.get("status")
        if status == "failed":
            failed_sources += 1
            problems.append(issue("error", "SOURCE_FAILED", row_path, str(row.get("error") or "转换失败")))
            continue
        if status == "tombstone":
            continue
        original = resolve(root, str(row.get("path")))
        if not original.is_file():
            problems.append(issue("error", "SOURCE_ORIGINAL_MISSING", row_path, str(original)))
        elif row.get("sha256") != sha256_file(original, hash_cache):
            problems.append(issue("error", "SOURCE_ORIGINAL_HASH", row_path, "原始来源哈希不一致"))
        derived = row.get("derived_text_path")
        if not derived or not resolve(root, str(derived)).is_file():
            problems.append(issue("error", "DERIVED_MISSING", row_path, f"派生文本不存在：{derived}"))

    disposed = 0
    pending_relevance = 0
    for row in fragments:
        row_path = f"fragments.jsonl:{row.get('_line')}"
        source = source_keys.get((row.get("source_id"), row.get("revision_id")))
        if not source or source.get("status") != "ingested":
            problems.append(issue("error", "FRAGMENT_SOURCE", row_path, "来源修订不存在或不可用"))
        elif (row.get("anchor") or {}).get("kind") == "line_range":
            derived_path = resolve(root, str(source.get("derived_text_path")))
            if derived_path.is_file():
                line_count = len(derived_path.read_text(encoding="utf-8").splitlines())
                anchor = row["anchor"]
                start, end = anchor.get("start"), anchor.get("end")
                if not isinstance(start, int) or not isinstance(end, int) or not (
                    1 <= start <= end <= line_count
                ):
                    problems.append(
                        issue("error", "FRAGMENT_ANCHOR", row_path, f"锚点越界：{start}-{end}/{line_count}")
                    )
        raw = str(row.get("raw_text", ""))
        if hashlib.sha256(raw.encode("utf-8")).hexdigest() != row.get("raw_sha256"):
            problems.append(issue("error", "FRAGMENT_HASH", row_path, "raw_text 哈希不一致"))
        disposition = row.get("disposition")
        if disposition in {"mapped", "context-only", "deferred", "excluded"}:
            disposed += 1
        if disposition in {"context-only", "deferred", "excluded"} and not row.get("disposition_reason"):
            problems.append(issue("error", "FRAGMENT_REASON", row_path, "该处置必须有理由"))
        relevance = row.get("relevance") or {}
        if relevance.get("review_status") == "pending":
            pending_relevance += 1
            level = "error" if release_mode else "warning"
            problems.append(issue(level, "RELEVANCE_PENDING", row_path, "相关性等待复核"))

    mapped_by_decision: set[str] = set()
    target_components: set[str] = set()
    for row in mappings:
        row_path = f"mappings.jsonl:{row.get('_line')}"
        for fragment_id in row.get("fragment_ids") or []:
            mapped_by_decision.add(fragment_id)
            if fragment_id not in fragment_by_id:
                problems.append(issue("error", "MAPPING_FRAGMENT", row_path, f"碎片不存在：{fragment_id}"))
        target = row.get("target_component_id")
        if row.get("decision") in {"create", "merge", "keep-separate"} and not target:
            problems.append(issue("error", "MAPPING_TARGET_REQUIRED", row_path, "该决策必须指向组件"))
        if target:
            target_components.add(target)
            if target not in components:
                problems.append(issue("error", "MAPPING_COMPONENT", row_path, f"组件不存在：{target}"))
        if release_mode and row.get("review_status") != "reviewed":
            problems.append(issue("error", "MAPPING_REVIEW", row_path, "发布前映射必须复核"))

    for fragment_id, row in fragment_by_id.items():
        if row.get("disposition") == "mapped" and fragment_id not in mapped_by_decision:
            problems.append(issue("error", "ORPHAN_FRAGMENT", str(fragment_id), "mapped 碎片没有映射决策"))

    for component_id, meta in components.items():
        if meta.get("role") == "leaf" and component_id not in target_components:
            problems.append(issue("error", "ORPHAN_COMPONENT", component_id, "叶子组件没有反向映射"))
        for provenance in meta.get("provenance") or []:
            key = (provenance.get("source_id"), provenance.get("revision_id"))
            source = source_keys.get(key)
            if not source or source.get("status") != "ingested":
                problems.append(issue("error", "PROVENANCE_SOURCE", component_id, f"来源修订不可用：{key}"))
            elif latest_source_by_id.get(str(key[0]), {}).get("status") == "tombstone":
                problems.append(issue("error", "PROVENANCE_TOMBSTONE", component_id, f"来源已删除，组件须重审：{key[0]}"))
            for fragment_id in provenance.get("fragment_ids") or []:
                fragment = fragment_by_id.get(fragment_id)
                if not fragment:
                    problems.append(issue("error", "PROVENANCE_FRAGMENT", component_id, f"碎片不存在：{fragment_id}"))
                elif (fragment.get("source_id"), fragment.get("revision_id")) != key:
                    problems.append(issue("error", "PROVENANCE_MISMATCH", component_id, f"碎片来源不匹配：{fragment_id}"))

    policy = profile.get("release_policy") or {}
    open_conflicts = 0
    for row in conflicts:
        if row.get("status") == "open":
            open_conflicts += 1
            if not policy.get("unresolved_conflicts_allowed", False) or (
                release_mode and row.get("review_required")
            ):
                problems.append(
                    issue("error", "CONFLICT_OPEN", f"conflicts.jsonl:{row.get('_line')}", "未决冲突阻断发布")
                )
        for source_ref in row.get("source_refs") or []:
            if "@" not in str(source_ref):
                problems.append(
                    issue("error", "CONFLICT_SOURCE_REF", f"conflicts.jsonl:{row.get('_line')}", str(source_ref))
                )
                continue
            source_id, revision_id = str(source_ref).split("@", 1)
            if (source_id, revision_id) not in source_keys:
                problems.append(
                    issue("error", "CONFLICT_SOURCE_REF", f"conflicts.jsonl:{row.get('_line')}", str(source_ref))
                )

    profile_name = str(profile.get("domain_profile", "general"))
    profile_min = PROFILE_MIN_RISK.get(profile_name, "low")
    for component_id, meta in components.items():
        risk = meta.get("risk") or {}
        level = str(risk.get("level", "low"))
        if RISK_RANK.get(level, -1) < RISK_RANK[profile_min]:
            problems.append(
                issue("error", "RISK_PROFILE", component_id, f"{profile_name} 最低风险级别为 {profile_min}")
            )
        domain = PROFILE_DOMAIN.get(profile_name)
        if domain and domain not in (risk.get("domains") or []):
            problems.append(issue("error", "RISK_DOMAIN", component_id, f"风险域必须包含 {domain}"))
        if level in {"high", "critical"} and (
            meta.get("status") in {"已复核", "accepted"} or release_mode
        ):
            if (
                meta.get("status") not in {"已复核", "accepted"}
                or
                risk.get("approval_status") != "approved"
                or not risk.get("required_reviewer_role")
                or not risk.get("reviewer_identity")
                or not risk.get("approved_at")
                or not risk.get("approval_evidence")
            ):
                problems.append(issue("error", "RISK_APPROVAL", component_id, "高风险发布缺少专业批准"))

    if not manifest_path.is_file():
        problems.append(issue("error", "MANIFEST_MISSING", "release-manifest.json", "缺少发布清单"))
        manifest = None
    else:
        try:
            manifest = load_json(manifest_path)
            problems.extend(
                schema_problems(
                    object_validator(pipeline_schema, "releaseManifest"),
                    manifest,
                    "release-manifest.json",
                    "MANIFEST_SCHEMA",
                )
            )
        except Exception as exc:
            manifest = None
            problems.append(issue("error", "MANIFEST_PARSE", "release-manifest.json", str(exc)))
    if release_mode and manifest and manifest.get("release_status") not in {"ready", "released"}:
        problems.append(issue("error", "RELEASE_STATUS", "release-manifest.json", "发布状态必须为 ready 或 released"))
    fingerprint_values = sorted(
        f"{row.get('source_id')}@{row.get('revision_id')}:{row.get('sha256')}"
        for row in latest_source_by_id.values()
        if row.get("status") == "ingested"
    )
    expected_fingerprint = hashlib.sha256(
        "\n".join(fingerprint_values).encode("utf-8")
    ).hexdigest()
    if manifest and manifest.get("input_fingerprint") != expected_fingerprint:
        problems.append(
            issue("error", "MANIFEST_FINGERPRINT", "release-manifest.json", "输入指纹与当前有效来源不一致")
        )

    if release_mode:
        index_rows, index_problems = load_jsonl(root / "indexes" / "components.jsonl")
        problems.extend(index_problems)
        index_ids = {str(row.get("id")) for row in index_rows if row.get("id")}
        component_ids = set(components)
        for missing in sorted(component_ids - index_ids):
            problems.append(issue("error", "INDEX_MISSING_COMPONENT", missing, "组件未进入总索引"))
        for stale in sorted(index_ids - component_ids):
            problems.append(issue("error", "INDEX_STALE_COMPONENT", stale, "索引指向不存在组件"))
        if not (root / "relations.jsonl").is_file():
            problems.append(issue("error", "RELATIONS_MISSING", "relations.jsonl", "缺少机器关系表"))

    metrics.update(
        {
            "source_revision_count": len(sources),
            "failed_source_count": failed_sources,
            "fragment_count": len(fragments),
            "disposition_coverage": disposed / len(fragments) if fragments else 1.0,
            "pending_relevance_count": pending_relevance,
            "mapping_count": len(mappings),
            "conflict_count": len(conflicts),
            "open_conflict_count": open_conflicts,
            "orphan_fragment_count": sum(
                1
                for row in fragments
                if row.get("disposition") == "mapped"
                and row.get("fragment_id") not in mapped_by_decision
            ),
            "orphan_component_count": sum(
                1
                for component_id, meta in components.items()
                if meta.get("role") == "leaf" and component_id not in target_components
            ),
        }
    )
    return problems, metrics


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="校验超云知识库构建器产物")
    parser.add_argument("root", type=Path)
    parser.add_argument("--strict-v2", action="store_true", help="检查类型正文契约及空章节")
    parser.add_argument("--require-leaf-mermaid", action="store_true")
    parser.add_argument("--pipeline", action="store_true", help="检查完整流水线及交叉引用")
    parser.add_argument("--release", action="store_true", help="按发布门禁处理待复核项")
    parser.add_argument("--component-schema", type=Path)
    parser.add_argument("--pipeline-schema", type=Path)
    parser.add_argument("--report-json", type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    root = args.root.resolve()
    if not root.is_dir():
        print(f"错误：目录不存在：{root}", file=sys.stderr)
        return 2

    skill_root = Path(__file__).resolve().parent.parent
    component_schema_path = (args.component_schema or skill_root / "component-schema.json").resolve()
    pipeline_schema_path = (args.pipeline_schema or skill_root / "pipeline-schema.json").resolve()
    try:
        component_schema = load_json(component_schema_path)
        pipeline_schema = load_json(pipeline_schema_path)
        Draft202012Validator.check_schema(component_schema)
        Draft202012Validator.check_schema(pipeline_schema)
    except Exception as exc:
        print(f"错误：Schema 无法加载：{exc}", file=sys.stderr)
        return 2

    component_validator = Draft202012Validator(component_schema, format_checker=FormatChecker())
    component_root = root / "components"
    markdown_files = sorted(component_root.rglob("*.md")) if component_root.is_dir() else []
    problems: list[dict[str, str]] = []
    components: dict[str, dict[str, Any]] = {}
    hash_cache: dict[Path, str] = {}
    for path in markdown_files:
        file_problems, meta = validate_component(
            path,
            root,
            component_validator,
            args.strict_v2,
            args.require_leaf_mermaid,
            hash_cache,
        )
        problems.extend(file_problems)
        if meta and meta.get("id"):
            component_id = str(meta["id"])
            if component_id in components:
                problems.append(issue("error", "ID_DUPLICATE", component_id, "组件 ID 重复"))
            components[component_id] = meta

    id_set = set(components)
    graph: dict[str, list[str]] = {}
    for component_id, meta in components.items():
        graph[component_id] = list(meta.get("depends_on") or [])
        for field in ("depends_on", "related"):
            for target in meta.get(field) or []:
                if target not in id_set:
                    problems.append(issue("error", "RELATION_TARGET", component_id, f"{field} 目标不存在：{target}"))
    for cycle in dependency_cycles(graph):
        problems.append(issue("error", "DEPENDENCY_CYCLE", " -> ".join(cycle), "强依赖形成环"))

    metrics: dict[str, Any] = {"component_count": len(components)}
    if args.pipeline or args.release:
        pipeline_problems, pipeline_metrics = validate_pipeline(
            root, pipeline_schema, components, hash_cache, args.release
        )
        problems.extend(pipeline_problems)
        metrics.update(pipeline_metrics)

    errors = [item for item in problems if item["level"] == "error"]
    warnings = [item for item in problems if item["level"] == "warning"]
    metrics["duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
    metrics["hash_cache_entries"] = len(hash_cache)
    report = {
        "builder_version": BUILDER_VERSION,
        "root": str(root),
        "schemas": {
            "component": str(component_schema_path),
            "pipeline": str(pipeline_schema_path),
        },
        "metrics": metrics,
        "errors": errors,
        "warnings": warnings,
        "passed": not errors,
    }
    if args.report_json:
        output = args.report_json if args.report_json.is_absolute() else root / args.report_json
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"组件：{len(components)}；错误：{len(errors)}；警告：{len(warnings)}")
    for item in errors:
        print(f"ERROR [{item['code']}] {item['path']}: {item['message']}")
    for item in warnings:
        print(f"WARN  [{item['code']}] {item['path']}: {item['message']}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
