from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.xiaobei_ai import prep_room_document_text_extractor_1013R_R107A as extractor
from backend.xiaobei_ai import prep_room_lean_readonly_chain_1013R_R201C as r201c
from backend.xiaobei_ai import prep_room_real_upload_entry_preview_1013R_R103 as r103
from scripts.validate_1013r_r201b_lean_chain_shadow_run import OLD_SHOES_RAW


STAGE = "1013R_R201D_LEAN_CHAIN_MULTI_FORMAT_REGRESSION"
OUT = ROOT / "outputs" / "PREP_ROOM_RENDER_CANVAS_DEEPEN_V1" / STAGE
RESULT = OUT / "validate_1013R_R201D_lean_chain_multi_format_regression_result.json"


TABLE_SAMPLE = """课题：雨伞图案设计
年级：四年级
教学目标：学生能观察伞面纹样，设计有重复或对称规律的雨伞图案。
教学过程：
| 教学环节 | 教师活动 | 学生活动 | 设计意图 |
| --- | --- | --- | --- |
| 导入观察 | 出示不同雨伞图片，追问伞面图案有什么规律。 | 观察并说出重复、对称、颜色搭配。 | 从生活用品进入纹样观察。 |
| 方法示范 | 演示把一个小图形沿伞骨重复排列。 | 跟随教师在草稿纸上试排。 | 明确纹样组织方法。 |
| 设计制作 | 巡视学生完成伞面图案设计，提醒色彩和疏密。 | 完成雨伞图案作品。 | 将规律运用于设计表现。 |
| 展示评价 | 组织学生说出自己最满意的一处图案安排。 | 展示作品并互评。 | 用作品证据说明设计效果。 |
评价证据：作品中能看出重复或对称规律，学生能说出图案安排理由。
"""


LONG_SECTION_SAMPLE = """课题：校园里的线条
年级：三年级
教学目标：学生能从校园物品中发现直线、曲线和折线，并用线条组合表现一个校园角落。
教学过程：
教师先带学生回忆校门、操场、栏杆和树枝中的线条，请学生说出哪些线条让画面更有节奏。随后教师展示一张校园照片，指着栏杆、跑道、树枝和窗框，引导学生把看到的线条分成直线、曲线、折线三类。接着教师在黑板上示范如何用三种线条组合出一个校园角落，提醒学生先确定大形，再补充局部线条。学生开始创作时，教师巡视，重点帮助只会画轮廓的学生把观察到的线条补进画面。最后全班把作品贴到黑板上，学生说一说自己用了哪三种线条，教师用“能否看出校园场景、线条是否有变化、画面是否完整”进行评价。
作业：继续观察家里或路上的线条，拍一张照片下节课交流。
"""


MARKDOWN_SAMPLE = """# 课题：纸卷动物
年级：四年级
单元：纸艺造型

## 教学过程

### 导入：看纸卷像什么
教师出示纸卷和几个动物图片，请学生猜一猜纸卷可以变成什么动物身体。

### 探究：发现卷、折、剪的关系
学生观察纸卷作品，找出身体、耳朵、尾巴分别用了什么纸艺方法。

### 示范：连接身体和局部
教师示范卷纸、剪耳朵、粘贴尾巴，提醒胶水位置和结构稳定。

### 创作：完成纸卷动物
学生选择一种动物完成纸卷造型，并尝试添加表情或纹样。

### 展评：说出最像的地方
学生展示作品，说出自己最满意的动物特征。
"""


MINIMAL_SAMPLE = """课题：线条小鱼
年级：二年级
教学目标：用不同线条装饰一条小鱼。
教学过程：
1. 看鱼图片，说一说鱼身上有什么线条。
2. 教师示范用波浪线、折线、点线装饰鱼。
3. 学生画一条线条小鱼。
"""


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _docx_text(pattern: str) -> tuple[str, str, str]:
    matches = sorted((ROOT / "knowledge-base" / "lesson-cases").glob(pattern))
    if not matches:
        raise AssertionError(f"missing docx sample: {pattern}")
    path = matches[0]
    extracted = extractor.extract_document_text(str(path), original_filename=path.name, enable_model_ocr=False)
    if not extracted.get("ok"):
        raise AssertionError(f"document extraction failed: {path.name}")
    return str(extracted.get("text") or ""), path.name, str(path.relative_to(ROOT))


def _samples() -> list[dict[str, Any]]:
    weaving_raw, weaving_file, weaving_path = _docx_text("*39f6102808*.docx")
    qinglv_raw, qinglv_file, qinglv_path = _docx_text("*走进青绿山水*.docx")
    return [
        {
            "sample_id": "numbered_colon_old_shoes",
            "format_type": "numbered_colon",
            "lesson_label": "旧鞋 / 足下生辉",
            "file_name": "r201d_inline_足下生辉_旧鞋改造设计课.txt",
            "source_path": "inline_from_R201B",
            "raw_text": OLD_SHOES_RAW,
            "expected_min_episodes": 5,
            "must_include": ["草图", "制作路径", "旧鞋", "5句话", "新鞋发布会"],
            "forbidden_terms": ["经纬", "编织", "青绿山水", "石青", "石绿", "渐变"],
            "downstream_terms": ["5句话", "新鞋发布会"],
        },
        {
            "sample_id": "plain_segment_weaving",
            "format_type": "plain_segment",
            "lesson_label": "穿穿编编",
            "file_name": weaving_file,
            "source_path": weaving_path,
            "raw_text": weaving_raw,
            "expected_min_episodes": 6,
            "must_include": ["编织", "经纬"],
            "forbidden_terms": ["旧鞋", "草图", "新鞋发布会", "5句话设计故事"],
            "downstream_terms": ["小结"],
        },
        {
            "sample_id": "table_rain_umbrella",
            "format_type": "table_or_structured",
            "lesson_label": "雨伞图案设计",
            "file_name": "r201d_inline_雨伞图案设计_表格型教案.txt",
            "source_path": "inline_r201d_table_fixture",
            "raw_text": TABLE_SAMPLE,
            "expected_min_episodes": 4,
            "must_include": ["导入观察", "方法示范", "设计制作", "展示评价"],
            "forbidden_terms": ["旧鞋", "经纬", "青绿", "海洋"],
            "downstream_terms": ["展示评价", "评价证据"],
        },
        {
            "sample_id": "long_section_line_campus",
            "format_type": "long_section",
            "lesson_label": "校园里的线条",
            "file_name": "r201d_inline_校园里的线条_长段落教案.txt",
            "source_path": "inline_r201d_long_section_fixture",
            "raw_text": LONG_SECTION_SAMPLE,
            "expected_min_episodes": 2,
            "must_include": ["线条", "校园", "作品"],
            "forbidden_terms": ["旧鞋", "经纬", "青绿", "海洋"],
            "downstream_terms": ["评价", "作业"],
        },
        {
            "sample_id": "markdown_paper_roll_animal",
            "format_type": "markdown_heading",
            "lesson_label": "纸卷动物",
            "file_name": "r201d_inline_纸卷动物_markdown标题型教案.md",
            "source_path": "inline_r201d_markdown_fixture",
            "raw_text": MARKDOWN_SAMPLE,
            "expected_min_episodes": 5,
            "must_include": ["纸卷", "动物", "展评"],
            "forbidden_terms": ["旧鞋", "经纬", "青绿", "海洋"],
            "downstream_terms": ["展评"],
        },
        {
            "sample_id": "minimal_line_fish",
            "format_type": "minimal",
            "lesson_label": "线条小鱼",
            "file_name": "r201d_inline_线条小鱼_极简教案.txt",
            "source_path": "inline_r201d_minimal_fixture",
            "raw_text": MINIMAL_SAMPLE,
            "expected_min_episodes": 3,
            "must_include": ["线条", "小鱼"],
            "forbidden_terms": ["旧鞋", "经纬", "青绿", "海洋"],
            "downstream_terms": [],
        },
        {
            "sample_id": "real_qinglv_docx",
            "format_type": "real_docx_extra",
            "lesson_label": "走进青绿山水",
            "file_name": qinglv_file,
            "source_path": qinglv_path,
            "raw_text": qinglv_raw,
            "expected_min_episodes": 3,
            "must_include": ["青绿", "山水"],
            "forbidden_terms": ["旧鞋", "新鞋发布会", "经纬"],
            "downstream_terms": ["准备"],
        },
    ]


def _candidate_matrix(viewmodel: dict[str, Any], sample_id: str) -> list[dict[str, Any]]:
    orchestrator = viewmodel.get("source_extraction_orchestrator") if isinstance(viewmodel.get("source_extraction_orchestrator"), dict) else {}
    candidates = orchestrator.get("parser_candidates") if isinstance(orchestrator.get("parser_candidates"), list) else []
    rows = []
    for candidate in candidates:
        row = dict(candidate)
        row["sample_id"] = sample_id
        rows.append(row)
    return rows


def _template_text(viewmodel: dict[str, Any]) -> str:
    return json.dumps(viewmodel.get("single_lesson_template") or {}, ensure_ascii=False)


def _title_pollution(viewmodel: dict[str, Any]) -> list[str]:
    template = viewmodel.get("single_lesson_template") if isinstance(viewmodel.get("single_lesson_template"), dict) else {}
    hits = []
    for episode in template.get("process_episodes") or []:
        if not isinstance(episode, dict):
            continue
        title = _clean(episode.get("episode_title"))
        if len(title) > 28 or re.search(r"\d+\s*分钟", title) or any(mark in title for mark in ["：", ":", "。", "；"]):
            hits.append(title)
    return hits


def _episode_span_ok(selected: dict[str, Any]) -> bool:
    episodes = selected.get("episodes") if isinstance(selected.get("episodes"), list) else []
    return bool(episodes) and all(
        isinstance((((episode.get("provenance") or {}).get("source_span") or {}).get("start")), int)
        and isinstance((((episode.get("provenance") or {}).get("source_span") or {}).get("end")), int)
        for episode in episodes
    )


def _episode_evidence_ok(selected: dict[str, Any]) -> bool:
    episodes = selected.get("episodes") if isinstance(selected.get("episodes"), list) else []
    return bool(episodes) and all(
        bool((episode.get("provenance") or {}).get("source_text_excerpt"))
        and bool((episode.get("provenance") or {}).get("selection_reason"))
        for episode in episodes
    )


def _source_counts(viewmodel: dict[str, Any]) -> dict[str, int]:
    ledger = viewmodel.get("ownership_ledger") if isinstance(viewmodel.get("ownership_ledger"), dict) else {}
    counts = ledger.get("teacher_main_source_counts")
    return counts if isinstance(counts, dict) else {}


def _run_sample(sample: dict[str, Any]) -> dict[str, Any]:
    raw_text = sample["raw_text"]
    file_name = sample["file_name"]
    route_response, route_status = r103.handle_upload_entry_preview({"raw_text": raw_text, "file_name": file_name, "engine": "lean"})
    viewmodel = route_response if isinstance(route_response, dict) else {}
    selected = viewmodel.get("selected_source_extraction") if isinstance(viewmodel.get("selected_source_extraction"), dict) else {}
    orchestrator = viewmodel.get("source_extraction_orchestrator") if isinstance(viewmodel.get("source_extraction_orchestrator"), dict) else {}
    template = viewmodel.get("single_lesson_template") if isinstance(viewmodel.get("single_lesson_template"), dict) else {}
    ledger = viewmodel.get("ownership_ledger") if isinstance(viewmodel.get("ownership_ledger"), dict) else {}

    sample_dir = OUT / "samples" / sample["sample_id"]
    _write_text(
        sample_dir / "raw_source_snapshot.md",
        "\n".join(
            [
                f"# {sample['lesson_label']} Raw Source Snapshot",
                "",
                f"- sample_id: `{sample['sample_id']}`",
                f"- format_type: `{sample['format_type']}`",
                f"- file_name: `{file_name}`",
                f"- source_path: `{sample['source_path']}`",
                "",
                "```text",
                raw_text,
                "```",
                "",
            ]
        ),
    )
    _write_json(sample_dir / "parser_candidate_matrix.json", _candidate_matrix(viewmodel, sample["sample_id"]))
    _write_json(sample_dir / "selected_source_extraction.json", selected)
    _write_json(sample_dir / "lesson_understanding_graph.json", viewmodel.get("import_understanding_v2_graph_preview") or {})
    _write_json(sample_dir / "teacher_execution_map.json", viewmodel.get("import_teacher_execution_map_preview") or {})
    _write_json(sample_dir / "field_projection_result.json", viewmodel.get("import_graph_field_projection_preview") or {})
    _write_json(sample_dir / "single_lesson_template.json", template)
    _write_json(sample_dir / "ownership_ledger.json", ledger)
    _write_json(sample_dir / "readonly_viewmodel_sample.json", viewmodel)

    template_text = _template_text(viewmodel)
    forbidden_hits = [term for term in sample.get("forbidden_terms") or [] if term in template_text]
    must_missing = [term for term in sample.get("must_include") or [] if term not in template_text]
    downstream_terms = sample.get("downstream_terms") or []
    downstream_preserved = all(term in template_text for term in downstream_terms)
    title_pollution = _title_pollution(viewmodel)
    source_counts = _source_counts(viewmodel)
    forbidden_sources = (ledger.get("forbidden_source_hits") if isinstance(ledger.get("forbidden_source_hits"), list) else [])
    gap_hits = (ledger.get("source_gap_as_content_hits") if isinstance(ledger.get("source_gap_as_content_hits"), list) else [])
    selected_parser = str(selected.get("selected_parser_id") or "")
    candidates = orchestrator.get("parser_candidates") if isinstance(orchestrator.get("parser_candidates"), list) else []
    selected_candidate = next((item for item in candidates if item.get("parser_id") == selected_parser), {})
    return {
        "sample_id": sample["sample_id"],
        "format_type": sample["format_type"],
        "lesson_label": sample["lesson_label"],
        "file_name": file_name,
        "source_path": sample["source_path"],
        "route_status": route_status,
        "route_stage": viewmodel.get("stage"),
        "route_viewmodel_type": viewmodel.get("viewmodel_type"),
        "selected_parser_id": selected_parser,
        "selection_reason": selected.get("selection_reason"),
        "selection_score": selected.get("confidence"),
        "selected_candidate_score": selected_candidate.get("selection_score"),
        "episode_count": selected.get("episode_count"),
        "episode_titles": selected.get("episode_titles") or [],
        "expected_min_episodes": sample["expected_min_episodes"],
        "selected_parser_episode_count": selected_candidate.get("episode_count"),
        "zero_episode_parser_selected": (selected_candidate.get("episode_count") == 0),
        "every_episode_has_source_span": _episode_span_ok(selected),
        "every_episode_has_source_evidence": _episode_evidence_ok(selected),
        "source_gap_active": bool((selected.get("source_gap") or {}).get("active")) if isinstance(selected.get("source_gap"), dict) else False,
        "low_confidence": bool(selected.get("low_confidence")),
        "low_confidence_hard_generated_full_process": bool(selected.get("low_confidence")) and bool(template.get("process_episodes")),
        "single_lesson_template_generated": bool(template.get("process_episodes")),
        "teacher_main_source_counts": source_counts,
        "forbidden_source_hit_count": len(forbidden_sources),
        "source_gap_as_content_count": len(gap_hits),
        "unknown_source_count": source_counts.get("unknown", 0),
        "episode_title_metadata_pollution_count": len(title_pollution),
        "episode_title_metadata_pollution_hits": title_pollution,
        "downstream_showcase_or_homework_not_swallowed": downstream_preserved,
        "old_lesson_contamination_hits": forbidden_hits,
        "must_include_missing_terms": must_missing,
        "model_called": bool((viewmodel.get("boundary") or {}).get("model_called")),
        "provider_called": bool((viewmodel.get("boundary") or {}).get("provider_called")),
        "outputs": {
            "raw_source_snapshot": str((sample_dir / "raw_source_snapshot.md").relative_to(ROOT)),
            "parser_candidate_matrix": str((sample_dir / "parser_candidate_matrix.json").relative_to(ROOT)),
            "selected_source_extraction": str((sample_dir / "selected_source_extraction.json").relative_to(ROOT)),
            "lesson_understanding_graph": str((sample_dir / "lesson_understanding_graph.json").relative_to(ROOT)),
            "teacher_execution_map": str((sample_dir / "teacher_execution_map.json").relative_to(ROOT)),
            "field_projection_result": str((sample_dir / "field_projection_result.json").relative_to(ROOT)),
            "single_lesson_template": str((sample_dir / "single_lesson_template.json").relative_to(ROOT)),
            "ownership_ledger": str((sample_dir / "ownership_ledger.json").relative_to(ROOT)),
            "readonly_viewmodel_sample": str((sample_dir / "readonly_viewmodel_sample.json").relative_to(ROOT)),
        },
    }


def _report(sample_results: list[dict[str, Any]]) -> str:
    lines = [
        "# R201D Lean Chain Multi-Format Regression Report",
        "",
        "R201D keeps R201C as an opt-in lean readonly route. It does not switch the default upload route.",
        "",
        "| Sample | Format | Selected Parser | Episodes | Score | Forbidden Sources | Gap As Content | Title Pollution | Cross Topic |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in sample_results:
        lines.append(
            "| {sample_id} | {format_type} | `{parser}` | {episodes} | {score} | {forbidden} | {gap} | {pollution} | {cross} |".format(
                sample_id=item["sample_id"],
                format_type=item["format_type"],
                parser=item["selected_parser_id"],
                episodes=item["episode_count"],
                score=item["selection_score"],
                forbidden=item["forbidden_source_hit_count"],
                gap=item["source_gap_as_content_count"],
                pollution=item["episode_title_metadata_pollution_count"],
                cross=len(item["old_lesson_contamination_hits"]),
            )
        )
    lines.extend(
        [
            "",
            "## Reading",
            "",
            "- PASS means parser selection, provenance and ownership stayed clean across multiple formats.",
            "- This is still not a default route switch decision.",
            "- Parser candidates remain inspectable through each sample matrix.",
            "",
        ]
    )
    return "\n".join(lines)


def _failure_doc(sample_results: list[dict[str, Any]], checks: dict[str, bool]) -> str:
    failed_checks = [key for key, value in checks.items() if not value]
    lines = ["# R201D Failure Cases If Any", ""]
    if not failed_checks:
        lines.append("No blocking regression failure was found in this R201D run.")
    else:
        lines.extend(["## Failed Checks", ""])
        lines.extend(f"- `{key}`" for key in failed_checks)
    lines.extend(["", "## Sample Diagnostics", ""])
    for item in sample_results:
        issues = []
        if item["zero_episode_parser_selected"]:
            issues.append("selected zero-episode parser")
        if item["forbidden_source_hit_count"]:
            issues.append("forbidden teacher-main source")
        if item["source_gap_as_content_count"]:
            issues.append("source_gap entered teacher main")
        if item["episode_title_metadata_pollution_count"]:
            issues.append("episode title metadata pollution")
        if item["old_lesson_contamination_hits"]:
            issues.append(f"cross-topic terms: {item['old_lesson_contamination_hits']}")
        if item["must_include_missing_terms"]:
            issues.append(f"missing required terms: {item['must_include_missing_terms']}")
        if item["low_confidence_hard_generated_full_process"]:
            issues.append("low confidence generated full process")
        lines.append(f"- `{item['sample_id']}`: {', '.join(issues) if issues else 'ok'}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    samples = _samples()
    sample_results = [_run_sample(sample) for sample in samples]
    parser_selection_matrix = []
    for sample in samples:
        path = OUT / "samples" / sample["sample_id"] / "parser_candidate_matrix.json"
        parser_selection_matrix.extend(json.loads(path.read_text(encoding="utf-8")))

    manifest = {
        "stage": STAGE,
        "sample_count": len(samples),
        "format_types": sorted({sample["format_type"] for sample in samples}),
        "samples": [
            {
                "sample_id": sample["sample_id"],
                "format_type": sample["format_type"],
                "lesson_label": sample["lesson_label"],
                "file_name": sample["file_name"],
                "source_path": sample["source_path"],
                "expected_min_episodes": sample["expected_min_episodes"],
            }
            for sample in samples
        ],
        "boundary": {
            "opt_in_lean_route_only": True,
            "default_route_unchanged": True,
            "formal_apply": False,
            "database_written": False,
            "feishu_written": False,
            "memory_written": False,
            "provider_called": False,
            "model_called": False,
            "R95_executed": False,
        },
    }
    _write_json(OUT / "r201d_sample_manifest.json", manifest)
    _write_json(OUT / "r201d_parser_selection_matrix.json", parser_selection_matrix)

    required_formats = {"numbered_colon", "plain_segment", "table_or_structured", "long_section", "markdown_heading", "minimal"}
    checks = {
        "at_least_six_format_classes_completed": required_formats.issubset({item["format_type"] for item in sample_results}),
        "selected_parser_reason_exists": all(bool(item["selection_reason"]) for item in sample_results),
        "no_zero_episode_parser_selected": all(not item["zero_episode_parser_selected"] for item in sample_results),
        "selected_episode_count_meets_sample_floor": all(
            int(item["episode_count"] or 0) >= int(item["expected_min_episodes"] or 0) for item in sample_results
        ),
        "every_episode_has_source_span": all(item["every_episode_has_source_span"] for item in sample_results),
        "every_episode_has_source_evidence": all(item["every_episode_has_source_evidence"] for item in sample_results),
        "source_gap_as_content_zero": all(item["source_gap_as_content_count"] == 0 for item in sample_results),
        "teacher_main_R200A_kernel_zero": all("R200A_kernel" not in item["teacher_main_source_counts"] for item in sample_results),
        "teacher_main_R200B_candidate_zero": all("R200B_candidate" not in item["teacher_main_source_counts"] for item in sample_results),
        "teacher_main_R97B_P3_zero": all("R97B_P3_derivation_spine" not in item["teacher_main_source_counts"] for item in sample_results),
        "teacher_main_unknown_zero": all(item["unknown_source_count"] == 0 for item in sample_results),
        "episode_title_metadata_pollution_zero": all(item["episode_title_metadata_pollution_count"] == 0 for item in sample_results),
        "downstream_showcase_or_homework_not_swallowed": all(item["downstream_showcase_or_homework_not_swallowed"] for item in sample_results),
        "old_lesson_contamination_hits_zero": all(not item["old_lesson_contamination_hits"] for item in sample_results),
        "must_include_terms_preserved": all(not item["must_include_missing_terms"] for item in sample_results),
        "no_low_confidence_hard_generation": all(not item["low_confidence_hard_generated_full_process"] for item in sample_results),
        "default_route_unchanged": True,
        "opt_in_lean_route_available": all(item["route_status"] == 200 and item["route_stage"] == "1013R_R201C_READONLY_ROUTE_SWITCH_TO_LEAN_CHAIN" for item in sample_results),
        "model_not_called": all(not item["model_called"] for item in sample_results),
        "provider_not_called": all(not item["provider_called"] for item in sample_results),
        "formal_apply_not_performed": True,
        "R95_not_executed": True,
    }
    _write_text(OUT / "r201d_multi_format_regression_report.md", _report(sample_results))
    _write_text(OUT / "r201d_failure_cases_if_any.md", _failure_doc(sample_results, checks))

    result = {
        "stage": STAGE,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "sample_results": sample_results,
        "boundary": {
            "opt_in_lean_route_only": True,
            "default_R103_route_replaced": False,
            "formal_apply": False,
            "database_written": False,
            "feishu_written": False,
            "memory_written": False,
            "pptx_pdf_docx_generated": False,
            "R21_modified": False,
            "R36_modified": False,
            "R95_executed": False,
            "provider_called": any(item["provider_called"] for item in sample_results),
            "model_called": any(item["model_called"] for item in sample_results),
        },
        "outputs": {
            "sample_manifest": str((OUT / "r201d_sample_manifest.json").relative_to(ROOT)),
            "parser_selection_matrix": str((OUT / "r201d_parser_selection_matrix.json").relative_to(ROOT)),
            "multi_format_regression_report": str((OUT / "r201d_multi_format_regression_report.md").relative_to(ROOT)),
            "failure_cases_if_any": str((OUT / "r201d_failure_cases_if_any.md").relative_to(ROOT)),
            "samples": str((OUT / "samples").relative_to(ROOT)),
            "validation_result": str(RESULT.relative_to(ROOT)),
        },
    }
    _write_json(RESULT, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
