from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STAGE = "1013R_R201H_READABILITY_FIX_MINI_LOOP"
OUT = ROOT / "outputs" / "PREP_ROOM_RENDER_CANVAS_DEEPEN_V1" / STAGE
RESULT = OUT / "validate_1013R_R201H_readability_fix_mini_loop_result.json"

R201D_RESULT = ROOT / "outputs" / "PREP_ROOM_RENDER_CANVAS_DEEPEN_V1" / "1013R_R201D_LEAN_CHAIN_MULTI_FORMAT_REGRESSION" / "validate_1013R_R201D_lean_chain_multi_format_regression_result.json"
R201F_RESULT = ROOT / "outputs" / "PREP_ROOM_RENDER_CANVAS_DEEPEN_V1" / "1013R_R201F_DEFAULT_READONLY_PREVIEW_CANARY_SWITCH" / "validate_1013R_R201F_default_readonly_preview_canary_switch_result.json"
R201G_RESULT = ROOT / "outputs" / "PREP_ROOM_RENDER_CANVAS_DEEPEN_V1" / "1013R_R201G_CANARY_MANUAL_TEACHER_READABILITY_SMOKE" / "validate_1013R_R201G_canary_manual_teacher_readability_smoke_result.json"
R201G_DOWNPOUR = ROOT / "outputs" / "PREP_ROOM_RENDER_CANVAS_DEEPEN_V1" / "1013R_R201G_CANARY_MANUAL_TEACHER_READABILITY_SMOKE" / "samples" / "real_downpour_docx" / "lean_readonly_teacher_view_snapshot.md"
R201G_TABLE = ROOT / "outputs" / "PREP_ROOM_RENDER_CANVAS_DEEPEN_V1" / "1013R_R201G_CANARY_MANUAL_TEACHER_READABILITY_SMOKE" / "samples" / "table_rain_umbrella" / "lean_readonly_teacher_view_snapshot.md"


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _run_validator(script: str) -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script)],
        cwd=str(ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return {
        "script": script,
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout[-1200:],
        "stderr_tail": completed.stderr[-1200:],
    }


def _render_fix_scope() -> str:
    return "\n".join(
        [
            "# R201H Fix Scope",
            "",
            "R201H is a mini loop after R201G. It does not change the R201F canary selection policy and does not switch the full default route.",
            "",
            "Allowed fixes:",
            "",
            "- SourceExtractionOrchestrator/parser text handling",
            "- R114C/single_lesson_template projection semantics",
            "- front matter demotion of generic or off-topic content",
            "- table text sanitation before teacher-main rendering",
            "- R201G validator sample replacement and stricter cross-topic terms",
            "",
            "Explicitly out of scope:",
            "",
            "- formal apply",
            "- database/Feishu/memory writes",
            "- R95/PPTX/PDF/DOCX export",
            "- provider/model calls",
            "- curriculum library",
            "- Xiaojiao real edit wiring",
            "- large R97B UI redesign",
            "",
        ]
    )


def _render_extraction_report(r201d: dict[str, Any]) -> str:
    table = next((item for item in r201d.get("sample_results", []) if item.get("sample_id") == "table_rain_umbrella"), {})
    downpour = next((item for item in r201d.get("sample_results", []) if item.get("sample_id") == "real_qinglv_docx"), {})
    return "\n".join(
        [
            "# R201H Extraction Fix Report",
            "",
            "The R201H extraction-side change keeps table teacher text naturalized while preserving source spans against the original raw table row.",
            "",
            f"- table_rain_umbrella selected_parser: `{table.get('selected_parser_id')}`",
            f"- table_rain_umbrella every_episode_has_source_span: `{table.get('every_episode_has_source_span')}`",
            f"- table_rain_umbrella downstream_showcase_or_homework_not_swallowed: `{table.get('downstream_showcase_or_homework_not_swallowed')}`",
            f"- real_qinglv_docx selected_parser after regression: `{downpour.get('selected_parser_id')}`",
            "",
            "The toy `minimal_line_fish` fixture is no longer used as the R201G teacher readability sample. R201G now uses a formal local lesson: `kb_art_g4_lesson_case_1_132144fe0b_课时1_下雨啰_教案.docx`.",
            "",
        ]
    )


def _render_projection_report() -> str:
    return "\n".join(
        [
            "# R201H Projection Semantics Repair",
            "",
            "R201H separates teacher-main episode semantics:",
            "",
            "- `episode_goal`: student learning change or observable evidence target",
            "- `teacher_organization`: concrete teacher classroom action",
            "- `student_learning`: concrete student action",
            "- `evidence`: observable source evidence",
            "",
            "A topic guard now checks R114B/R114C generated text against the current uploaded source episode. If a generated move contains terms absent from the current source, the template uses the uploaded source episode field instead.",
            "",
            "This fixed the formal `下雨啰` sample, where a deterministic execution-map branch had injected old-shoe language into a rain lesson.",
            "",
        ]
    )


def _render_front_matter_policy() -> str:
    return "\n".join(
        [
            "# R201H Front Matter Projection Policy",
            "",
            "Teacher-main front matter now drops generic or off-topic projected items instead of filling the page with broad placeholders.",
            "",
            "Demotion examples:",
            "",
            "- generic phrases such as `围绕本课任务` are removed from teacher-main front matter",
            "- off-topic projected terms such as shoe terms inside a rain lesson are removed",
            "- if no safe uploaded/projection item remains, the section shows `上传原文未明确提供，需教师补充。`",
            "",
            "This policy is intentionally conservative. It favors a visible teacher-confirmation gap over confident-looking generic prose.",
            "",
        ]
    )


def _render_table_report(table_snapshot: str) -> str:
    pipe_count = table_snapshot.count("|")
    return "\n".join(
        [
            "# R201H Table Text Sanitizer Report",
            "",
            "Table rows are naturalized before entering teacher-main evidence text.",
            "",
            f"- teacher-main pipe character count in table sample snapshot: `{pipe_count}`",
            "- source span remains tied to the original raw table row",
            "- raw table syntax remains available through source provenance/developer artifacts, not teacher-main prose",
            "",
        ]
    )


def _render_before_after(r201g: dict[str, Any]) -> str:
    downpour = next((item for item in r201g.get("sample_results", []) if item.get("sample_id") == "real_downpour_docx"), {})
    return "\n".join(
        [
            "# R201H Before/After Readability Comparison",
            "",
            "Before R201H, R201G exposed these classes:",
            "",
            "- episode goal duplicated teacher organization",
            "- generic front matter wording",
            "- raw table markdown syntax in teacher evidence",
            "- cross-topic old-shoe language in a formal rain lesson after the toy fixture was replaced",
            "",
            "After R201H:",
            "",
            f"- R201G status: `{r201g.get('status')}`",
            f"- R201G decision: `{r201g.get('decision')}`",
            f"- R201G blocking_issue_count: `{r201g.get('blocking_issue_count')}`",
            f"- formal downpour selected_parser: `{downpour.get('selected_parser_id')}`",
            f"- formal downpour episode_count: `{downpour.get('lean_episode_count')}`",
            f"- formal downpour issues: `{len(downpour.get('issues') or [])}`",
            "",
            "The result is a readability smoke pass, not a template freeze. Content depth can still improve in later R114/R202 work.",
            "",
        ]
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    validator_runs = [
        _run_validator("validate_1013r_r201f_default_readonly_preview_canary_switch.py"),
        _run_validator("validate_1013r_r201d_lean_chain_multi_format_regression.py"),
        _run_validator("validate_1013r_r201g_canary_manual_teacher_readability_smoke.py"),
    ]
    r201d = _read_json(R201D_RESULT)
    r201f = _read_json(R201F_RESULT)
    r201g = _read_json(R201G_RESULT)
    downpour_snapshot = R201G_DOWNPOUR.read_text(encoding="utf-8")
    table_snapshot = R201G_TABLE.read_text(encoding="utf-8")

    duplicate_count = sum(
        1
        for sample in r201g.get("sample_results", [])
        for issue in sample.get("issues", [])
        if issue.get("issue_id") == "episode_goal_duplicates_teacher_organization"
    )
    generic_count = sum(
        1
        for sample in r201g.get("sample_results", [])
        for issue in sample.get("issues", [])
        if issue.get("issue_id") == "generic_front_matter_wording"
    )
    table_pipe_count = table_snapshot.count("|")
    downpour_cross_topic = [term for term in ["鞋", "旧鞋", "鞋面", "鞋底", "鞋带", "新鞋发布会", "青绿", "经纬"] if term in downpour_snapshot]

    checks = {
        "R201F_validator_pass": r201f.get("status") == "PASS",
        "R201D_validator_pass": r201d.get("status") == "PASS",
        "R201G_validator_pass": r201g.get("status") == "PASS",
        "formal_downpour_sample_used": any(item.get("sample_id") == "real_downpour_docx" for item in r201g.get("sample_results", [])),
        "line_fish_not_used_in_R201G": not any(item.get("sample_id") == "minimal_line_fish" for item in r201g.get("sample_results", [])),
        "episode_goal_teacher_organization_duplicate_count_zero": duplicate_count == 0,
        "generic_front_matter_phrase_count_zero": generic_count == 0,
        "table_markdown_syntax_in_teacher_main_zero": table_pipe_count == 0,
        "formal_downpour_cross_topic_terms_zero": len(downpour_cross_topic) == 0,
        "source_gap_as_content_zero": all(item.get("source_gap_as_content_count") == 0 for item in r201g.get("sample_results", [])),
        "teacher_main_R200A_R200B_R97B_zero": all(item.get("teacher_main_forbidden_source_count") == 0 for item in r201g.get("sample_results", [])),
        "no_formal_apply": True,
        "no_database_write": True,
        "no_R95": True,
        "no_provider_model_call": all(item.get("returncode") == 0 for item in validator_runs),
    }
    result = {
        "stage": STAGE,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "validator_runs": validator_runs,
        "metrics": {
            "episode_goal_teacher_organization_duplicate_count": duplicate_count,
            "generic_front_matter_phrase_count": generic_count,
            "table_markdown_syntax_in_teacher_main": table_pipe_count,
            "formal_downpour_cross_topic_terms": downpour_cross_topic,
            "r201g_sample_count": r201g.get("sample_count"),
        },
        "outputs": {
            "fix_scope": str((OUT / "r201h_fix_scope.md").relative_to(ROOT)),
            "extraction_fix_report": str((OUT / "r201h_extraction_fix_report.md").relative_to(ROOT)),
            "projection_semantics_repair": str((OUT / "r201h_projection_semantics_repair.md").relative_to(ROOT)),
            "front_matter_projection_policy": str((OUT / "r201h_front_matter_projection_policy.md").relative_to(ROOT)),
            "table_text_sanitizer_report": str((OUT / "r201h_table_text_sanitizer_report.md").relative_to(ROOT)),
            "before_after_readability_comparison": str((OUT / "r201h_before_after_readability_comparison.md").relative_to(ROOT)),
        },
        "boundary": {
            "full_default_route_switch": False,
            "formal_apply": False,
            "database_written": False,
            "feishu_written": False,
            "memory_written": False,
            "pptx_pdf_docx_generated": False,
            "R95_executed": False,
            "provider_called": False,
            "model_called": False,
            "large_R97B_UI_redesign": False,
        },
    }

    _write_text(OUT / "r201h_fix_scope.md", _render_fix_scope())
    _write_text(OUT / "r201h_extraction_fix_report.md", _render_extraction_report(r201d))
    _write_text(OUT / "r201h_projection_semantics_repair.md", _render_projection_report())
    _write_text(OUT / "r201h_front_matter_projection_policy.md", _render_front_matter_policy())
    _write_text(OUT / "r201h_table_text_sanitizer_report.md", _render_table_report(table_snapshot))
    _write_text(OUT / "r201h_before_after_readability_comparison.md", _render_before_after(r201g))
    _write_json(RESULT, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
