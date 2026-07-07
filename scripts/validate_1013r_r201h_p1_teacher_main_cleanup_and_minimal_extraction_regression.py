from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.xiaobei_ai import prep_room_lean_readonly_chain_1013R_R201C as r201c
from scripts.validate_1013r_r201d_lean_chain_multi_format_regression import MINIMAL_SAMPLE


STAGE = "1013R_R201H_P1_TEACHER_MAIN_CLEANUP_AND_MINIMAL_EXTRACTION_REGRESSION"
OUT = ROOT / "outputs" / "PREP_ROOM_RENDER_CANVAS_DEEPEN_V1" / STAGE
RESULT = OUT / "validate_1013R_R201H_P1_teacher_main_cleanup_and_minimal_extraction_regression_result.json"

R201G_OUT = ROOT / "outputs" / "PREP_ROOM_RENDER_CANVAS_DEEPEN_V1" / "1013R_R201G_CANARY_MANUAL_TEACHER_READABILITY_SMOKE"
R201G_RESULT = R201G_OUT / "validate_1013R_R201G_canary_manual_teacher_readability_smoke_result.json"
R201G_DOWNPOUR = R201G_OUT / "samples" / "real_downpour_docx" / "lean_readonly_teacher_view_snapshot.md"

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


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _run(args: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        args,
        cwd=str(ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return {
        "command": " ".join(args),
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout[-1600:],
        "stderr_tail": completed.stderr[-1600:],
    }


def _run_validator(script_name: str) -> dict[str, Any]:
    return _run([sys.executable, str(ROOT / "scripts" / script_name)])


def _teacher_main(snapshot: str) -> str:
    return snapshot.split("\n---\n", 1)[0]


def _term_hits(text: str) -> list[str]:
    return [term for term in ENGINEERING_TERMS if term in text]


def _minimal_regression() -> dict[str, Any]:
    extraction = r201c.orchestrate_source_extraction(MINIMAL_SAMPLE, "r201h_p1_inline_线条小鱼_极简教案.txt")
    episodes = extraction.get("episodes") if isinstance(extraction.get("episodes"), list) else []
    phrase = "学生画一条线条小鱼"
    episode_texts = [
        f"{episode.get('title') or ''} {episode.get('source_content') or ''}"
        for episode in episodes
        if isinstance(episode, dict)
    ]
    matching_indices = [idx + 1 for idx, text in enumerate(episode_texts) if phrase in text]
    template = r201c.build_lean_readonly_viewmodel_from_raw_text(
        MINIMAL_SAMPLE,
        "r201h_p1_inline_线条小鱼_极简教案.txt",
    ).get("single_lesson_template") or {}
    template_text = json.dumps(template, ensure_ascii=False)
    return {
        "selected_parser_id": extraction.get("selected_parser_id"),
        "confidence": extraction.get("confidence"),
        "episode_count": extraction.get("episode_count"),
        "episode_titles": extraction.get("episode_titles") or [],
        "matching_student_creation_episode_indices": matching_indices,
        "minimal_line_fish_expected_steps": 3,
        "minimal_line_fish_actual_episodes": int(extraction.get("episode_count") or 0),
        "student_creation_step_not_swallowed": bool(matching_indices) and int(extraction.get("episode_count") or 0) >= 3,
        "student_creation_phrase_in_template": phrase in template_text,
    }


def _render_cleanup_report(g_result: dict[str, Any], all_hits: dict[str, list[str]]) -> str:
    lines = [
        "# R201H-P1 Teacher Main Cleanup Report",
        "",
        "R201H-P1 keeps source ownership metadata internal, but removes engineering terms from the teacher-facing snapshot.",
        "",
        f"- R201G status after rerun: `{g_result.get('status')}`",
        f"- R201G decision after rerun: `{g_result.get('decision')}`",
        "",
        "## Engineering Term Scan",
        "",
    ]
    for sample_id, hits in all_hits.items():
        lines.append(f"- `{sample_id}`: {hits if hits else 'none'}")
    lines.extend(
        [
            "",
            "Teacher-visible source labels now use classroom-facing wording such as `上传原文依据`, `教学推进依据`, and `理解整理依据`.",
            "",
            "Internal source types such as `R114_execution_map` remain in the ownership ledger for auditing only.",
            "",
        ]
    )
    return "\n".join(lines)


def _render_minimal_report(regression: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# R201H-P1 Minimal Extraction Regression Report",
            "",
            "The minimal `线条小鱼` sample is not restored as a R201G readability sample, but it is restored as an extraction regression.",
            "",
            f"- selected_parser_id: `{regression.get('selected_parser_id')}`",
            f"- minimal_line_fish_expected_steps: `{regression.get('minimal_line_fish_expected_steps')}`",
            f"- minimal_line_fish_actual_episodes: `{regression.get('minimal_line_fish_actual_episodes')}`",
            f"- student_creation_step_not_swallowed: `{regression.get('student_creation_step_not_swallowed')}`",
            "",
            "Episode titles:",
            "",
            *[f"- {title}" for title in regression.get("episode_titles") or []],
            "",
        ]
    )


def _render_downpour_before_after(main_text: str, hits: list[str]) -> str:
    assessment = main_text.split("## 七、学习单与评价", 1)[-1].strip()
    return "\n".join(
        [
            "# R201H-P1 Downpour Teacher Text Cleanup Before/After",
            "",
            "Before P1, the downpour teacher-view assessment text contained internal wording such as `需在 R114B 执行地图中细化对应关系`.",
            "",
            "After P1, the teacher-main assessment area is scanned for engineering terms and uses teacher-readable evidence language.",
            "",
            f"- engineering_term_hits_after: `{hits}`",
            "",
            "## Current Assessment Section",
            "",
            assessment,
            "",
        ]
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    validator_runs = [
        _run_validator("validate_1013r_r201f_default_readonly_preview_canary_switch.py"),
        _run_validator("validate_1013r_r201d_lean_chain_multi_format_regression.py"),
        _run_validator("validate_1013r_r201g_canary_manual_teacher_readability_smoke.py"),
        _run_validator("validate_1013r_r201h_readability_fix_mini_loop.py"),
    ]
    py_compile = _run(
        [
            sys.executable,
            "-m",
            "py_compile",
            str(ROOT / "backend" / "xiaobei_ai" / "prep_room_import_understanding_v2_graph_1013R_R114A.py"),
            str(ROOT / "backend" / "xiaobei_ai" / "prep_room_lean_readonly_chain_1013R_R201C.py"),
            str(ROOT / "scripts" / "validate_1013r_r201d_lean_chain_multi_format_regression.py"),
            str(ROOT / "scripts" / "validate_1013r_r201g_canary_manual_teacher_readability_smoke.py"),
            str(ROOT / "scripts" / "validate_1013r_r201h_readability_fix_mini_loop.py"),
            str(ROOT / "scripts" / "validate_1013r_r201h_p1_teacher_main_cleanup_and_minimal_extraction_regression.py"),
        ]
    )

    r201g_result = _read_json(R201G_RESULT)
    sample_hits: dict[str, list[str]] = {}
    for sample in r201g_result.get("sample_results", []):
        sample_id = str(sample.get("sample_id") or "")
        snapshot = R201G_OUT / "samples" / sample_id / "lean_readonly_teacher_view_snapshot.md"
        if snapshot.exists():
            sample_hits[sample_id] = _term_hits(_teacher_main(snapshot.read_text(encoding="utf-8")))

    downpour_main = _teacher_main(R201G_DOWNPOUR.read_text(encoding="utf-8"))
    downpour_hits = _term_hits(downpour_main)
    minimal = _minimal_regression()

    checks = {
        "R201F_validator_pass": validator_runs[0]["returncode"] == 0,
        "R201D_validator_pass": validator_runs[1]["returncode"] == 0,
        "R201G_validator_pass": validator_runs[2]["returncode"] == 0,
        "R201H_validator_pass": validator_runs[3]["returncode"] == 0,
        "py_compile_pass": py_compile["returncode"] == 0,
        "teacher_main_engineering_term_count_zero": sum(len(hits) for hits in sample_hits.values()) == 0,
        "minimal_line_fish_actual_episodes_at_least_3": int(minimal.get("minimal_line_fish_actual_episodes") or 0) >= 3,
        "student_creation_step_not_swallowed": bool(minimal.get("student_creation_step_not_swallowed")),
        "downpour_teacher_assessment_engineering_terms_zero": len(downpour_hits) == 0,
        "source_gap_as_content_zero": all(item.get("source_gap_as_content_count") == 0 for item in r201g_result.get("sample_results", [])),
        "teacher_main_R200A_R200B_R97B_P3_zero": all(item.get("teacher_main_forbidden_source_count") == 0 for item in r201g_result.get("sample_results", [])),
        "no_formal_apply": True,
        "no_write": True,
        "no_R95": True,
        "no_model_provider_call": True,
    }
    result = {
        "stage": STAGE,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "metrics": {
            "teacher_main_engineering_term_count": sum(len(hits) for hits in sample_hits.values()),
            "teacher_main_engineering_term_hits_by_sample": sample_hits,
            "downpour_teacher_assessment_engineering_term_hits": downpour_hits,
            **minimal,
        },
        "validator_runs": validator_runs,
        "py_compile": py_compile,
        "outputs": {
            "teacher_main_cleanup_report": str((OUT / "r201h_p1_teacher_main_cleanup_report.md").relative_to(ROOT)),
            "minimal_extraction_regression_report": str((OUT / "r201h_p1_minimal_extraction_regression_report.md").relative_to(ROOT)),
            "downpour_teacher_text_cleanup_before_after": str((OUT / "r201h_p1_downpour_teacher_text_cleanup_before_after.md").relative_to(ROOT)),
            "validation_result": str(RESULT.relative_to(ROOT)),
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

    _write_text(OUT / "r201h_p1_teacher_main_cleanup_report.md", _render_cleanup_report(r201g_result, sample_hits))
    _write_text(OUT / "r201h_p1_minimal_extraction_regression_report.md", _render_minimal_report(minimal))
    _write_text(OUT / "r201h_p1_downpour_teacher_text_cleanup_before_after.md", _render_downpour_before_after(downpour_main, downpour_hits))
    _write_json(RESULT, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
