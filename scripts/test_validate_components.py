from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

SCRIPT = Path(__file__).with_name("validate_components.py")
BUILD = Path(__file__).with_name("build_kb.py")
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}


def digest(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def profile(name: str = "general") -> dict:
    risks = {
        "general": ("low", []),
        "medical": ("high", ["medical"]),
    }
    level, domains = risks[name]
    return {
        "schema_version": "1.0",
        "kb_id": "demo.kb",
        "title": "演示知识库",
        "central_question": "如何验证知识库流水线",
        "audiences": ["测试者"],
        "target_tasks": ["检索"],
        "included_topics": ["验证"],
        "excluded_topics": [],
        "boundary_examples": {},
        "domain_profile": name,
        "risk_profile": {"level": level, "domains": domains, "jurisdictions": []},
        "relevance": {
            "labels": ["include", "contextual", "exclude", "uncertain"],
            "review_below": 0.75,
        },
        "release_policy": {
            "unresolved_conflicts_allowed": False,
            "professional_approval_required": name == "medical",
            "minimum_review_rate": 1.0,
        },
        "extensions": {},
    }


def component(source_hash: str, *, component_id: str = "demo.concept.feedback-loop",
              depends_on: list[str] | None = None, risk: str = "low",
              domains: list[str] | None = None, approval: str = "not-required") -> str:
    metadata = {
        "id": component_id,
        "kb_id": "demo.kb",
        "type": "concept",
        "type_cn": "概念类",
        "domain_profile": "general",
        "role": "leaf",
        "title": "反馈回路",
        "summary": "说明输出如何返回系统并改变后续行为的基本概念。",
        "evidence_level": "原文主张",
        "status": "accepted",
        "taxonomy_version": "2.2.0",
        "component_version": "1.0.0",
        "content_layers": [{"kind": "faithful_paraphrase"}],
        "provenance": [{
            "source_id": "src.demo.001",
            "revision_id": "rev.demo.001",
            "source_file": "derived/source.md",
            "source_sha256": source_hash,
            "fragment_ids": ["frag.demo.001"],
            "anchors": [{"kind": "line_range", "start": 1, "end": 1}],
            "evidence_role": "supports",
            "extraction_method": "faithful_paraphrase",
        }],
        "canonical": True,
        "dedupe_status": "unique",
        "conflict_status": "none",
        "depends_on": depends_on or [],
        "related": [],
        "risk": {
            "level": risk,
            "domains": domains or [],
            "required_reviewer_role": "专业审核员" if risk in {"high", "critical"} else None,
            "reviewer_identity": "reviewer-001" if approval == "approved" else None,
            "approved_at": "2026-09-05T00:00:00+00:00" if approval == "approved" else None,
            "approval_evidence": "approval://demo/001" if approval == "approved" else None,
            "approval_status": approval,
            "prohibited_uses": [],
            "stop_or_refer": [],
        },
    }
    body = """
# 反馈回路

## 定义
反馈回路将系统输出重新作为输入。

## 为什么重要
它帮助理解系统行为如何持续变化。

## 构成
包括输入、处理、输出和反馈。

## 识别线索
观察输出是否影响下一轮输入。

## 易混淆概念
它不同于没有回流的单向流程。

## 应用入口
用于分析循环系统。

## 边界
不能仅凭反馈关系推断因果强度。
"""
    return f"---\n{yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False)}---\n{body}"


def build_fixture(root: Path, profile_name: str = "general") -> None:
    (root / "components").mkdir()
    (root / "derived").mkdir()
    (root / "indexes").mkdir()
    original = root / "original.txt"
    original.write_bytes("验证资料。\n".encode("utf-8"))
    derived = root / "derived" / "source.md"
    derived.write_bytes("验证资料。\n".encode("utf-8"))
    original_hash = hashlib.sha256(original.read_bytes()).hexdigest()
    derived_hash = hashlib.sha256(derived.read_bytes()).hexdigest()
    (root / "kb-profile.yaml").write_text(
        yaml.safe_dump(profile(profile_name), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    write_jsonl(root / "sources.jsonl", [{
        "schema_version": "1.0",
        "source_id": "src.demo.001",
        "revision_id": "rev.demo.001",
        "path": str(original),
        "format": "txt",
        "sha256": original_hash,
        "title": "演示",
        "author": None,
        "published_at": None,
        "effective_at": None,
        "license": None,
        "parser": {"name": "direct-text", "version": "1.0.0"},
        "quality": {"score": 1.0, "issues": []},
        "derived_text_path": "derived/source.md",
        "status": "ingested",
        "error": None,
        "ingested_at": "2026-09-05T00:00:00+00:00",
        "run_id": "run-test",
        "extensions": {},
    }])
    write_jsonl(root / "fragments.jsonl", [{
        "schema_version": "1.0",
        "fragment_id": "frag.demo.001",
        "source_id": "src.demo.001",
        "revision_id": "rev.demo.001",
        "anchor": {"kind": "line_range", "start": 1, "end": 1},
        "raw_text": "验证资料。",
        "raw_sha256": digest("验证资料。"),
        "normalized_text": "验证资料。",
        "normalization_log": [],
        "language": "zh-CN",
        "heading_path": [],
        "relevance": {
            "label": "include",
            "confidence": 0.9,
            "reason": "命中主题",
            "review_status": "reviewed",
        },
        "disposition": "mapped",
        "disposition_reason": None,
        "run_id": "run-test",
        "extensions": {},
    }])
    write_jsonl(root / "mappings.jsonl", [{
        "schema_version": "1.0",
        "mapping_id": "map.demo.001",
        "fragment_ids": ["frag.demo.001"],
        "reader_task": "理解验证",
        "candidate_type": "concept",
        "cluster_id": "cluster.demo",
        "relation_candidate": "none",
        "decision": "create",
        "target_component_id": "demo.concept.feedback-loop",
        "basis": "单一原子定义",
        "review_status": "reviewed",
        "run_id": "run-test",
        "extensions": {},
    }])
    write_jsonl(root / "conflicts.jsonl", [])
    manifest = {
        "schema_version": "1.0",
        "builder_version": "1.0.0",
        "run_id": "run-test",
        "kb_id": "demo.kb",
        "created_at": "2026-09-05T00:00:00+00:00",
        "input_fingerprint": digest(f"src.demo.001@rev.demo.001:{original_hash}"),
        "taxonomy_version": "2.2.0",
        "component_schema_version": "2.2",
        "pipeline_schema_version": "1.0",
        "profile_version": "1.0",
        "tool_versions": {},
        "metrics": {},
        "blocking_issues": [],
        "release_status": "ready",
        "previous_release": None,
        "extensions": {},
    }
    (root / "release-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )
    risk = "high" if profile_name == "medical" else "low"
    domains = ["medical"] if profile_name == "medical" else []
    approval = "approved" if profile_name == "medical" else "not-required"
    (root / "components" / "概念-反馈回路.md").write_text(
        component(derived_hash, risk=risk, domains=domains, approval=approval),
        encoding="utf-8",
    )
    write_jsonl(root / "indexes" / "components.jsonl", [{
        "id": "demo.concept.feedback-loop",
        "type": "concept",
        "title": "反馈回路",
        "path": "components/概念-反馈回路.md",
    }])
    write_jsonl(root / "relations.jsonl", [])


class ValidatorTests(unittest.TestCase):
    def run_validator(self, root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(root), *arguments],
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
            env=ENV,
        )

    def test_full_pipeline_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build_fixture(root)
            result = self.run_validator(root, "--pipeline", "--release")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_builder_release_publishes_valid_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build_fixture(root)
            result = subprocess.run(
                [sys.executable, str(BUILD), "release", str(root), "--publish"],
                text=True,
                encoding="utf-8",
                capture_output=True,
                check=False,
                env=ENV,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            release = json.loads((root / "release-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(release["release_status"], "released")

    def test_profile_prevents_risk_downgrade(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build_fixture(root, "medical")
            path = root / "components" / "概念-反馈回路.md"
            derived_hash = hashlib.sha256((root / "derived" / "source.md").read_bytes()).hexdigest()
            path.write_text(component(derived_hash, risk="low"), encoding="utf-8")
            result = self.run_validator(root, "--pipeline", "--release")
            self.assertEqual(result.returncode, 1)
            self.assertIn("RISK_PROFILE", result.stdout)
            self.assertIn("RISK_DOMAIN", result.stdout)

    def test_orphan_fragment_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build_fixture(root)
            (root / "mappings.jsonl").write_text("", encoding="utf-8")
            result = self.run_validator(root, "--pipeline")
            self.assertEqual(result.returncode, 1)
            self.assertIn("ORPHAN_FRAGMENT", result.stdout)

    def test_missing_provenance_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build_fixture(root)
            path = root / "components" / "概念-反馈回路.md"
            text = path.read_text(encoding="utf-8").replace(
                "  source_file: derived/source.md\n", ""
            )
            path.write_text(text, encoding="utf-8")
            result = self.run_validator(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn("COMPONENT_SCHEMA", result.stdout)

    def test_mapping_unknown_fragment_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build_fixture(root)
            path = root / "mappings.jsonl"
            path.write_text(
                path.read_text(encoding="utf-8").replace("frag.demo.001", "frag.missing"),
                encoding="utf-8",
            )
            result = self.run_validator(root, "--pipeline")
            self.assertEqual(result.returncode, 1)
            self.assertIn("MAPPING_FRAGMENT", result.stdout)

    def test_dependency_cycle_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build_fixture(root)
            source_hash = hashlib.sha256((root / "derived" / "source.md").read_bytes()).hexdigest()
            first = root / "components" / "概念-反馈回路.md"
            first.write_text(
                component(source_hash, depends_on=["demo.concept.second"]),
                encoding="utf-8",
            )
            second = root / "components" / "概念-第二.md"
            second.write_text(
                component(
                    source_hash,
                    component_id="demo.concept.second",
                    depends_on=["demo.concept.feedback-loop"],
                ),
                encoding="utf-8",
            )
            result = self.run_validator(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn("DEPENDENCY_CYCLE", result.stdout)


if __name__ == "__main__":
    unittest.main()
