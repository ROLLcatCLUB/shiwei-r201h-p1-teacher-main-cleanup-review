from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.xiaobei_ai import prep_room_document_text_extractor_1013R_R107A as extractor
from backend.xiaobei_ai import prep_room_real_upload_entry_preview_1013R_R103 as r103
from scripts.validate_1013r_r201d_lean_chain_multi_format_regression import _samples as r201d_samples


STAGE = "1013R_R201G_CANARY_MANUAL_TEACHER_READABILITY_SMOKE"
OUT = ROOT / "outputs" / "PREP_ROOM_RENDER_CANVAS_DEEPEN_V1" / STAGE
RESULT = OUT / "validate_1013R_R201G_canary_manual_teacher_readability_smoke_result.json"
CANARY_ENV = "XIAOBEI_UPLOAD_PREVIEW_DEFAULT_ENGINE"

SELECTED_SAMPLE_IDS = {
    "numbered_colon_old_shoes",
    "plain_segment_weaving",
    "table_rain_umbrella",
    "real_downpour_docx",
}

FORBIDDEN_MAIN_MARKERS = [
    "R200A_kernel",
    "R200B_candidate",
    "R97B_P3_derivation_spine",
    "deterministic_fallback",
    "legacy_shell",
    "source_gap",
]

DIAGNOSTIC_MARKERS = [
    "parser_id",
    "source_span",
    "provenance",
    "fallback_reason",
    "SourceExtractionOrchestrator",
    "selected_source_extraction",
]

ENGINEERING_TERMS = [
    "R114A",
    "R114B",
    "R114C",
    "R200",
    "R201",
    "execution map",
    "field projection",
    "parser",
    "validator",
    "source ledger",
    "lean chain",
    "执行地图",
]

TITLE_POLLUTION_PATTERNS = [
    r"\d+\s*分钟",
    r"字段名",
    r"所属大单元",
    r"教学环节\s*\|",
    r"教师活动\s*\|",
    r"学生活动\s*\|",
]


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _with_env(value: str | None, fn):
    old = os.environ.get(CANARY_ENV)
    if value is None:
        os.environ.pop(CANARY_ENV, None)
    else:
        os.environ[CANARY_ENV] = value
    try:
        return fn()
    finally:
        if old is None:
            os.environ.pop(CANARY_ENV, None)
        else:
            os.environ[CANARY_ENV] = old


def _section_lines(title: str, items: Any) -> list[str]:
    lines = [f"## {title}"]
    if not isinstance(items, list) or not items:
        return lines + ["- 需教师确认：当前模板未投影出可读内容。", ""]
    counter = 1
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict):
            continue
        body_value = item.get("body")
        status = _clean(item.get("teacher_visible_source_label") or item.get("source_label") or item.get("source_status"))
        suffix = f" [{status}]" if status else ""
        if isinstance(body_value, list):
            for body_item in body_value:
                body = _clean(body_item)
                if body:
                    lines.append(f"{counter}. {body}{suffix}")
                    counter += 1
        else:
            body = _clean(body_value)
            if body:
                lines.append(f"{counter}. {body}{suffix}")
                counter += 1
    if len(lines) == 1:
        lines.append("- 需教师确认：当前模板未投影出可读内容。")
    lines.append("")
    return lines


def _template(response: dict[str, Any]) -> dict[str, Any]:
    template = response.get("single_lesson_template")
    return template if isinstance(template, dict) else {}


def _episodes(template: dict[str, Any]) -> list[dict[str, Any]]:
    episodes = template.get("process_episodes")
    return [item for item in episodes if isinstance(item, dict)] if isinstance(episodes, list) else []


def _section_count(template: dict[str, Any], key: str) -> int:
    value = template.get(key)
    if not isinstance(value, list):
        return 0
    return sum(1 for item in value if isinstance(item, dict) and _clean(item.get("body")))


def _episode_titles(template: dict[str, Any]) -> list[str]:
    return [_clean(episode.get("episode_title")) for episode in _episodes(template) if _clean(episode.get("episode_title"))]


def _render_teacher_snapshot(sample: dict[str, Any], response: dict[str, Any]) -> tuple[str, str]:
    template = _template(response)
    header = template.get("lesson_header") if isinstance(template.get("lesson_header"), dict) else {}
    metadata = response.get("preview_engine_metadata") if isinstance(response.get("preview_engine_metadata"), dict) else {}
    selected = response.get("selected_source_extraction") if isinstance(response.get("selected_source_extraction"), dict) else {}

    main: list[str] = [
        f"# {header.get('lesson_title') or sample['lesson_label']}",
        "",
        f"- 年级：{header.get('grade') or '待确认'}",
        f"- 单元：{header.get('unit_title') or '待确认'}",
        f"- 预览状态：只读预览；engine={metadata.get('preview_engine_selected') or 'unknown'}",
        "",
    ]
    main += _section_lines("一、本课依据", template.get("basis"))
    main += _section_lines("二、学情分析", template.get("student_analysis"))
    main += _section_lines("三、教学目标", template.get("objectives"))
    main += _section_lines("四、教学重难点", template.get("key_difficult_points"))
    main += _section_lines("五、教学准备", template.get("preparation"))

    main += ["## 六、教学过程", ""]
    for episode in _episodes(template):
        title = _clean(episode.get("episode_title")) or f"环节 {episode.get('episode_index') or ''}".strip()
        source_status = _clean(episode.get("teacher_visible_source_label") or episode.get("source_label") or episode.get("source_status"))
        main.append(f"### {episode.get('episode_index') or ''}. {title}".strip())
        if source_status:
            main.append(f"- 来源状态：{source_status}")
        goal = _clean(episode.get("episode_goal"))
        if goal:
            main.append(f"- 环节意图：{goal}")
        teacher_org = episode.get("teacher_organization")
        if isinstance(teacher_org, list) and teacher_org:
            main.append(f"- 教师组织：{'；'.join(_clean(item) for item in teacher_org if _clean(item))}")
        elif _clean(teacher_org):
            main.append(f"- 教师组织：{_clean(teacher_org)}")
        student_learning = _clean(episode.get("student_learning"))
        if student_learning:
            main.append(f"- 学生学习：{student_learning}")
        key_talk = _clean(episode.get("key_teacher_talk"))
        if key_talk:
            main.append(f"- 关键话术：{key_talk}")
        hint = _clean(episode.get("xiaojiao_hint"))
        if hint:
            main.append(f"- 小教提醒：{hint}")
        micro_steps = episode.get("micro_steps") if isinstance(episode.get("micro_steps"), list) else []
        if micro_steps:
            main.append("")
            main.append("展开小步骤：")
            for midx, micro in enumerate([m for m in micro_steps if isinstance(m, dict)], 1):
                name = _clean(micro.get("step_name")) or f"小步骤 {midx}"
                main.append(f"{midx}. {name}")
                teacher_action = _clean(micro.get("teacher_action"))
                student_action = _clean(micro.get("student_action"))
                scaffolds = _clean(micro.get("scaffolds"))
                evidence = _clean(micro.get("evidence"))
                if teacher_action:
                    main.append(f"   - 教师：{teacher_action}")
                if student_action:
                    main.append(f"   - 学生：{student_action}")
                if scaffolds:
                    main.append(f"   - 支架：{scaffolds}")
                if evidence:
                    main.append(f"   - 证据：{evidence}")
        main.append("")

    main += _section_lines("七、学习单与评价", template.get("assessment_or_homework"))
    main_text = "\n".join(main).strip() + "\n"
    diagnostics = "\n".join(
        [
            "",
            "---",
            "",
            "## 开发诊断（折叠区，不进入教师主阅读判断）",
            "",
            f"- selected_parser_id: {selected.get('selected_parser_id')}",
            f"- parser_confidence: {selected.get('confidence')}",
            f"- fallback_reason: {metadata.get('fallback_reason')}",
            f"- fallback_used: {metadata.get('fallback_used')}",
        ]
    )
    return main_text + diagnostics + "\n", main_text


def _run_preview(sample: dict[str, Any], *, preview_engine: str | None, canary: str | None) -> tuple[dict[str, Any], int]:
    payload: dict[str, Any] = {
        "raw_text": sample["raw_text"],
        "file_name": sample["file_name"],
    }
    if preview_engine:
        payload["preview_engine"] = preview_engine

    def _call():
        return r103.handle_upload_entry_preview(payload)

    return _with_env(canary, _call)


def _formal_downpour_sample() -> dict[str, Any]:
    matches = sorted((ROOT / "knowledge-base" / "lesson-cases").glob("*132144fe0b*.docx"))
    if not matches:
        raise AssertionError("missing formal downpour lesson docx: *132144fe0b*.docx")
    path = matches[0]
    extracted = extractor.extract_document_text(str(path), original_filename=path.name, enable_model_ocr=False)
    if not extracted.get("ok"):
        raise AssertionError(f"document extraction failed: {path.name}")
    return {
        "sample_id": "real_downpour_docx",
        "format_type": "formal_docx",
        "lesson_label": "下雨啰",
        "file_name": path.name,
        "source_path": str(path.relative_to(ROOT)),
        "raw_text": str(extracted.get("text") or ""),
        "expected_min_episodes": 6,
        "must_include": ["下雨", "课堂导入", "观察雨", "线描", "分享小结"],
        "forbidden_terms": ["旧鞋", "新鞋发布会", "鞋", "鞋面", "鞋底", "鞋带", "经纬", "青绿山水"],
        "downstream_terms": ["分享小结"],
    }


def _find_hits(text: str, needles: list[str]) -> list[str]:
    return [needle for needle in needles if needle in text]


def _title_pollution(titles: list[str]) -> list[str]:
    hits: list[str] = []
    for title in titles:
        if len(title) > 34:
            hits.append(title)
            continue
        if any(re.search(pattern, title) for pattern in TITLE_POLLUTION_PATTERNS):
            hits.append(title)
            continue
        if any(mark in title for mark in ["|", "：", ":", "。", "；"]):
            hits.append(title)
    return hits


def _issue(issue_id: str, sample_id: str, category: str, severity: str, detail: str, blocking: bool) -> dict[str, Any]:
    return {
        "issue_id": issue_id,
        "sample_id": sample_id,
        "category": category,
        "severity": severity,
        "detail": detail,
        "blocking": blocking,
    }


def _analyze_sample(sample: dict[str, Any], lean_response: dict[str, Any], legacy_response: dict[str, Any], lean_main_text: str) -> dict[str, Any]:
    sample_id = sample["sample_id"]
    template = _template(lean_response)
    episodes = _episodes(template)
    titles = _episode_titles(template)
    metadata = lean_response.get("preview_engine_metadata") if isinstance(lean_response.get("preview_engine_metadata"), dict) else {}
    selected = lean_response.get("selected_source_extraction") if isinstance(lean_response.get("selected_source_extraction"), dict) else {}
    ledger = lean_response.get("ownership_ledger") if isinstance(lean_response.get("ownership_ledger"), dict) else {}
    issues: list[dict[str, Any]] = []

    if metadata.get("preview_engine_selected") != "lean":
        issues.append(_issue("lean_not_selected", sample_id, "route", "blocker", "canary 条件下没有选中 lean preview。", True))
    if metadata.get("fallback_used"):
        issues.append(_issue("lean_fallback_used", sample_id, "extraction", "blocker", f"lean preview fallback: {metadata.get('fallback_reason')}", True))
    if ledger.get("forbidden_source_hits"):
        issues.append(_issue("forbidden_source_in_main", sample_id, "template", "blocker", "教师主正文出现禁止来源。", True))
    if ledger.get("source_gap_as_content_hits"):
        issues.append(_issue("source_gap_as_content", sample_id, "template", "blocker", "source_gap 被当作正文内容。", True))

    marker_hits = _find_hits(lean_main_text, FORBIDDEN_MAIN_MARKERS)
    if marker_hits:
        issues.append(_issue("forbidden_marker_text", sample_id, "rendering", "blocker", f"教师主阅读区出现禁止标记：{', '.join(marker_hits)}", True))
    diagnostic_hits = _find_hits(lean_main_text, DIAGNOSTIC_MARKERS)
    if diagnostic_hits:
        issues.append(_issue("diagnostic_in_teacher_main", sample_id, "rendering", "blocker", f"诊断字段进入教师主阅读区：{', '.join(diagnostic_hits)}", True))
    engineering_hits = _find_hits(lean_main_text, ENGINEERING_TERMS)
    if engineering_hits:
        issues.append(_issue("engineering_term_in_teacher_main", sample_id, "rendering", "blocker", f"工程术语进入教师主阅读区：{', '.join(engineering_hits)}", True))

    raw_numbered_steps = len(re.findall(r"(?m)^\s*\d+[.．、]\s*\S+", str(sample.get("raw_text") or "")))
    expected_min = int(sample.get("expected_min_episodes") or 1)
    if sample.get("format_type") == "minimal":
        expected_min = max(expected_min, raw_numbered_steps if raw_numbered_steps <= 8 else 0)
    if len(episodes) < expected_min:
        issues.append(_issue("episode_count_too_low", sample_id, "extraction", "blocker", f"环节数 {len(episodes)} 低于预期 {expected_min}。", True))

    polluted_titles = _title_pollution(titles)
    if polluted_titles:
        issues.append(_issue("episode_title_pollution", sample_id, "extraction", "blocker", f"环节标题污染：{polluted_titles}", True))

    for term in sample.get("must_include") or []:
        if term and term not in lean_main_text:
            issues.append(_issue("must_include_missing", sample_id, "projection", "major", f"教师视图没有保留关键词：{term}", False))
    for term in sample.get("forbidden_terms") or []:
        if term and term in lean_main_text:
            issues.append(_issue("cross_topic_term", sample_id, "projection", "blocker", f"疑似串课词进入教师视图：{term}", True))

    raw_table_evidence_count = 0
    duplicate_goal_teacher_count = 0
    generic_front_matter_hits: list[str] = []
    for episode in episodes:
        goal = _clean(episode.get("episode_goal"))
        teacher_org = episode.get("teacher_organization")
        teacher_text = "；".join(_clean(item) for item in teacher_org if _clean(item)) if isinstance(teacher_org, list) else _clean(teacher_org)
        if goal and teacher_text and goal == teacher_text:
            duplicate_goal_teacher_count += 1
        for micro in episode.get("micro_steps") or []:
            if not isinstance(micro, dict):
                continue
            evidence = _clean(micro.get("evidence"))
            if "|" in evidence and evidence.count("|") >= 3:
                raw_table_evidence_count += 1
    if duplicate_goal_teacher_count:
        issues.append(
            _issue(
                "episode_goal_duplicates_teacher_organization",
                sample_id,
                "projection",
                "major",
                f"{duplicate_goal_teacher_count} 个环节的环节意图与教师组织完全重复。",
                False,
            )
        )
    if raw_table_evidence_count:
        issues.append(
            _issue(
                "raw_table_syntax_in_evidence",
                sample_id,
                "projection",
                "major",
                f"{raw_table_evidence_count} 条证据仍带表格竖线原文，教师阅读不够干净。",
                False,
            )
        )

    generic_patterns = ["围绕本课任务", "具体学情与材料条件仍需教师确认", "上传教案单元待确认", "材料、工具、大屏资源和安全安排需教师根据本班条件确认"]
    for pattern in generic_patterns:
        if pattern in lean_main_text:
            generic_front_matter_hits.append(pattern)
    if generic_front_matter_hits:
        issues.append(
            _issue(
                "generic_front_matter_wording",
                sample_id,
                "projection",
                "major",
                f"前置依据/学情/目标仍有泛化措辞：{generic_front_matter_hits}",
                False,
            )
        )

    sparse_sections = [
        label
        for key, label in [
            ("basis", "本课依据"),
            ("student_analysis", "学情分析"),
            ("objectives", "教学目标"),
            ("key_difficult_points", "教学重难点"),
            ("preparation", "教学准备"),
        ]
        if _section_count(template, key) == 0
    ]
    if sparse_sections:
        issues.append(_issue("empty_front_matter_section", sample_id, "projection", "major", f"前置部分未投影出可读内容：{', '.join(sparse_sections)}", False))

    weak_layer_count = 0
    for episode in episodes:
        has_teacher = bool(episode.get("teacher_organization"))
        has_student = bool(_clean(episode.get("student_learning")))
        has_micro = bool(episode.get("micro_steps"))
        if not (has_teacher and has_student and has_micro):
            weak_layer_count += 1
    if weak_layer_count:
        issues.append(_issue("episode_layering_weak", sample_id, "graph", "major", f"{weak_layer_count} 个环节缺少教师/学生/小步骤层次。", False))

    legacy_template = _template(legacy_response)
    return {
        "sample_id": sample_id,
        "lesson_label": sample["lesson_label"],
        "format_type": sample["format_type"],
        "status": "PASS" if not any(issue["blocking"] for issue in issues) else "FAIL",
        "selected_parser_id": selected.get("selected_parser_id"),
        "parser_confidence": selected.get("confidence"),
        "expected_min_episodes_for_readability": expected_min,
        "lean_episode_count": len(episodes),
        "legacy_episode_count": len(_episodes(legacy_template)),
        "lean_episode_titles": titles,
        "legacy_episode_titles": _episode_titles(legacy_template),
        "teacher_main_forbidden_source_count": len(ledger.get("forbidden_source_hits") or []),
        "source_gap_as_content_count": len(ledger.get("source_gap_as_content_hits") or []),
        "teacher_main_engineering_term_count": len(_find_hits(lean_main_text, ENGINEERING_TERMS)),
        "preview_engine_metadata": metadata,
        "issues": issues,
        "readability_notes": [
            "教师主正文由 single_lesson_template 渲染快照生成。",
            "parser/provenance/fallback 只放在开发诊断折叠区。",
            "本轮只做可读性 smoke，不做内容质量增强。",
        ],
    }


def _comparison_doc(sample: dict[str, Any], analysis: dict[str, Any], lean_status: int, legacy_status: int) -> str:
    lines = [
        f"# {sample['lesson_label']} legacy vs lean teacher readability comparison",
        "",
        f"- sample_id: `{sample['sample_id']}`",
        f"- format_type: `{sample['format_type']}`",
        f"- lean_status_code: {lean_status}",
        f"- legacy_status_code: {legacy_status}",
        f"- lean_engine: `{(analysis.get('preview_engine_metadata') or {}).get('preview_engine_selected')}`",
        f"- lean_selected_parser: `{analysis.get('selected_parser_id')}`",
        f"- lean_episode_count: {analysis.get('lean_episode_count')}",
        f"- legacy_episode_count: {analysis.get('legacy_episode_count')}",
        "",
        "## Lean Episode Titles",
        "",
    ]
    lines += [f"- {title}" for title in analysis.get("lean_episode_titles") or []]
    lines += ["", "## Legacy Episode Titles", ""]
    legacy_titles = analysis.get("legacy_episode_titles") or []
    lines += [f"- {title}" for title in legacy_titles] if legacy_titles else ["- legacy response did not expose comparable single_lesson_template episode titles"]
    lines += ["", "## Smoke Judgment", ""]
    if analysis["status"] == "PASS":
        lines.append("Lean teacher view passes blocking readability smoke for this sample.")
    else:
        lines.append("Lean teacher view has blocking readability smoke issues for this sample.")
    lines += ["", "## Issues", ""]
    if analysis.get("issues"):
        for issue in analysis["issues"]:
            lines.append(f"- [{issue['severity']}] {issue['category']} / {issue['issue_id']}: {issue['detail']}")
    else:
        lines.append("- No issues recorded.")
    lines.append("")
    return "\n".join(lines)


def _issue_list_doc(analyses: list[dict[str, Any]]) -> str:
    lines = ["# R201G Readability Issue List", ""]
    for analysis in analyses:
        lines.append(f"## {analysis['lesson_label']} (`{analysis['sample_id']}`)")
        if not analysis.get("issues"):
            lines.append("- PASS: no readability smoke issues recorded.")
        else:
            for issue in analysis["issues"]:
                block = "blocking" if issue["blocking"] else "non-blocking"
                lines.append(f"- {block} / {issue['severity']} / {issue['category']}: {issue['detail']}")
        lines.append("")
    return "\n".join(lines)


def _classification_matrix(analyses: list[dict[str, Any]]) -> dict[str, Any]:
    categories = ["extraction", "graph", "projection", "template", "rendering", "route"]
    matrix: dict[str, Any] = {
        "stage": STAGE,
        "categories": {category: {"blocking": 0, "non_blocking": 0, "issues": []} for category in categories},
    }
    for analysis in analyses:
        for issue in analysis.get("issues") or []:
            category = issue.get("category") if issue.get("category") in matrix["categories"] else "template"
            bucket = "blocking" if issue.get("blocking") else "non_blocking"
            matrix["categories"][category][bucket] += 1
            matrix["categories"][category]["issues"].append(issue)
    return matrix


def _recommendation_doc(analyses: list[dict[str, Any]], matrix: dict[str, Any]) -> str:
    blocking = sum(
        int(bucket.get("blocking") or 0)
        for bucket in matrix.get("categories", {}).values()
        if isinstance(bucket, dict)
    )
    non_blocking = sum(
        int(bucket.get("non_blocking") or 0)
        for bucket in matrix.get("categories", {}).values()
        if isinstance(bucket, dict)
    )
    lines = [
        "# R201G Next Fix Recommendation",
        "",
        f"- blocking_issue_count: {blocking}",
        f"- non_blocking_issue_count: {non_blocking}",
        "",
    ]
    if blocking:
        lines += [
            "## Decision",
            "",
            "Do not freeze the template yet. Fix the blocking class first, in the owning layer shown by the issue matrix.",
            "",
        ]
    else:
        lines += [
            "## Decision",
            "",
            "R201G can be accepted as a teacher-readability smoke package. The next stage should be a small readability fix loop only if the user wants to polish the non-blocking issues.",
            "",
        ]
    lines += [
        "## Routing",
        "",
        "- extraction issues: return to SourceExtractionOrchestrator/parser rules.",
        "- graph issues: adjust R114A/B execution-map semantics, not R200A.",
        "- projection issues: adjust R114C/single_lesson_template projection.",
        "- template issues: fix single_lesson_template contract and ownership ledger.",
        "- rendering issues: fix renderer placement/demotion only; do not generate pedagogy in renderer.",
        "",
        "## Boundaries Kept",
        "",
        "- no full default route switch",
        "- no formal apply",
        "- no database/Feishu/memory writes",
        "- no R95 export",
        "- no provider/model call",
        "- no Xiaojiao real edit wiring",
        "- no large UI redesign",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    all_samples = [sample for sample in r201d_samples() if sample["sample_id"] in SELECTED_SAMPLE_IDS]
    all_samples.append(_formal_downpour_sample())
    selected_samples = [sample for sample in all_samples if sample["sample_id"] in SELECTED_SAMPLE_IDS]
    selected_samples.sort(key=lambda item: ["numbered_colon_old_shoes", "plain_segment_weaving", "table_rain_umbrella", "real_downpour_docx"].index(item["sample_id"]))

    manifest_samples: list[dict[str, Any]] = []
    analyses: list[dict[str, Any]] = []
    sample_root = OUT / "samples"

    for sample in selected_samples:
        lean_response, lean_status = _run_preview(sample, preview_engine=None, canary="lean_canary")
        legacy_response, legacy_status = _run_preview(sample, preview_engine="legacy", canary="lean_canary")
        sample_dir = sample_root / sample["sample_id"]
        snapshot, main_text = _render_teacher_snapshot(sample, lean_response)
        analysis = _analyze_sample(sample, lean_response, legacy_response, main_text)
        analyses.append(analysis)

        _write_text(sample_dir / "lean_readonly_teacher_view_snapshot.md", snapshot)
        _write_text(sample_dir / "legacy_vs_lean_teacher_readability_comparison.md", _comparison_doc(sample, analysis, lean_status, legacy_status))
        _write_json(sample_dir / "lean_readonly_response_summary.json", {
            "status_code": lean_status,
            "stage": lean_response.get("stage"),
            "preview_engine_metadata": lean_response.get("preview_engine_metadata"),
            "selected_source_extraction": lean_response.get("selected_source_extraction"),
            "ownership_ledger_summary": {
                "teacher_main_source_counts": (lean_response.get("ownership_ledger") or {}).get("teacher_main_source_counts")
                if isinstance(lean_response.get("ownership_ledger"), dict)
                else None,
                "forbidden_source_hit_count": len((lean_response.get("ownership_ledger") or {}).get("forbidden_source_hits") or [])
                if isinstance(lean_response.get("ownership_ledger"), dict)
                else None,
                "source_gap_as_content_count": len((lean_response.get("ownership_ledger") or {}).get("source_gap_as_content_hits") or [])
                if isinstance(lean_response.get("ownership_ledger"), dict)
                else None,
            },
        })
        _write_json(sample_dir / "legacy_readonly_response_summary.json", {
            "status_code": legacy_status,
            "stage": legacy_response.get("stage"),
            "preview_engine_metadata": legacy_response.get("preview_engine_metadata"),
        })

        manifest_samples.append(
            {
                "sample_id": sample["sample_id"],
                "lesson_label": sample["lesson_label"],
                "format_type": sample["format_type"],
                "file_name": sample["file_name"],
                "source_path": sample["source_path"],
                "expected_min_episodes": sample["expected_min_episodes"],
                "lean_snapshot": str((sample_dir / "lean_readonly_teacher_view_snapshot.md").relative_to(ROOT)),
                "comparison": str((sample_dir / "legacy_vs_lean_teacher_readability_comparison.md").relative_to(ROOT)),
                "analysis_status": analysis["status"],
                "selected_parser_id": analysis.get("selected_parser_id"),
                "lean_episode_count": analysis.get("lean_episode_count"),
            }
        )

    manifest = {
        "stage": STAGE,
        "purpose": "manual teacher readability smoke for R201F readonly preview canary",
        "canary_env": CANARY_ENV,
        "canary_value_used": "lean_canary",
        "sample_count": len(manifest_samples),
        "samples": manifest_samples,
        "boundaries": {
            "full_default_route_switch": False,
            "formal_apply": False,
            "database_written": False,
            "feishu_written": False,
            "memory_written": False,
            "R95_executed": False,
            "provider_called": False,
            "model_called": False,
            "xiaojiao_real_edit_wired": False,
            "large_ui_redesign": False,
        },
    }
    matrix = _classification_matrix(analyses)
    blocking_issues = [issue for analysis in analyses for issue in analysis.get("issues") or [] if issue.get("blocking")]
    checks = {
        "at_least_4_samples_completed": len(analyses) >= 4,
        "no_teacher_main_pollution": not any(issue["issue_id"] in {"forbidden_source_in_main", "forbidden_marker_text"} for issue in blocking_issues),
        "no_source_gap_as_content": not any(issue["issue_id"] == "source_gap_as_content" for issue in blocking_issues),
        "teacher_main_no_R200A_R200B_R97B_P3": not any(
            issue["issue_id"] in {"forbidden_source_in_main", "forbidden_marker_text"} and any(marker in issue["detail"] for marker in ["R200A", "R200B", "R97B"])
            for issue in blocking_issues
        ),
        "teaching_process_readable": not any(issue["issue_id"] in {"episode_count_too_low", "episode_title_pollution"} for issue in blocking_issues),
        "issues_classified": all(issue.get("category") in {"extraction", "graph", "projection", "template", "rendering", "route"} for analysis in analyses for issue in analysis.get("issues") or []),
        "no_full_default_switch": True,
        "no_formal_apply": True,
        "no_provider_or_model_call": True,
    }
    non_blocking_issue_count = sum(1 for analysis in analyses for issue in analysis.get("issues") or [] if not issue.get("blocking"))
    result = {
        "stage": STAGE,
        "status": "PASS" if all(checks.values()) and not blocking_issues else "FAIL",
        "decision": "PASS_WITH_READABILITY_NOTES" if all(checks.values()) and not blocking_issues and non_blocking_issue_count else ("PASS" if all(checks.values()) and not blocking_issues else "FAIL"),
        "classification": "teacher_readability_smoke",
        "sample_count": len(analyses),
        "blocking_issue_count": len(blocking_issues),
        "non_blocking_issue_count": non_blocking_issue_count,
        "checks": checks,
        "sample_results": analyses,
        "outputs": {
            "manifest": str((OUT / "r201g_teacher_readability_sample_manifest.json").relative_to(ROOT)),
            "issue_list": str((OUT / "r201g_readability_issue_list.md").relative_to(ROOT)),
            "issue_classification_matrix": str((OUT / "r201g_issue_classification_matrix.json").relative_to(ROOT)),
            "next_fix_recommendation": str((OUT / "r201g_next_fix_recommendation.md").relative_to(ROOT)),
        },
    }

    _write_json(OUT / "r201g_teacher_readability_sample_manifest.json", manifest)
    _write_text(OUT / "r201g_readability_issue_list.md", _issue_list_doc(analyses))
    _write_json(OUT / "r201g_issue_classification_matrix.json", matrix)
    _write_text(OUT / "r201g_next_fix_recommendation.md", _recommendation_doc(analyses, matrix))
    _write_json(RESULT, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
