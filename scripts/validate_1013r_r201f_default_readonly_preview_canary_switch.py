from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.xiaobei_ai import prep_room_real_upload_entry_preview_1013R_R103 as r103
from scripts.validate_1013r_r201b_lean_chain_shadow_run import OLD_SHOES_RAW


STAGE = "1013R_R201F_DEFAULT_READONLY_PREVIEW_CANARY_SWITCH"
OUT = ROOT / "outputs" / "PREP_ROOM_RENDER_CANVAS_DEEPEN_V1" / STAGE
RESULT = OUT / "validate_1013R_R201F_default_readonly_preview_canary_switch_result.json"
CANARY_ENV = "XIAOBEI_UPLOAD_PREVIEW_DEFAULT_ENGINE"


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


def _run_case(case_id: str, *, env_value: str | None, payload: dict[str, Any], expected_engine: str, expect_fallback: bool = False) -> dict[str, Any]:
    def _call():
        return r103.handle_upload_entry_preview(payload)

    response, status = _with_env(env_value, _call)
    metadata = response.get("preview_engine_metadata") if isinstance(response.get("preview_engine_metadata"), dict) else {}
    boundary = response.get("boundary") if isinstance(response.get("boundary"), dict) else {}
    lean_ledger = response.get("ownership_ledger") if isinstance(response.get("ownership_ledger"), dict) else {}
    forbidden_hits = lean_ledger.get("forbidden_source_hits") if isinstance(lean_ledger.get("forbidden_source_hits"), list) else []
    gap_hits = lean_ledger.get("source_gap_as_content_hits") if isinstance(lean_ledger.get("source_gap_as_content_hits"), list) else []
    out = {
        "case_id": case_id,
        "env_value": env_value,
        "payload_preview_engine": payload.get("preview_engine"),
        "payload_engine": payload.get("engine"),
        "status_code": status,
        "stage": response.get("stage"),
        "viewmodel_type": response.get("viewmodel_type"),
        "preview_engine_metadata": metadata,
        "selected_engine_matches_expected": metadata.get("preview_engine_selected") == expected_engine,
        "fallback_matches_expected": bool(metadata.get("fallback_used")) == expect_fallback,
        "fallback_reason_present_when_needed": (not expect_fallback) or bool(metadata.get("fallback_reason")),
        "formal_apply_disabled": metadata.get("formal_apply_enabled") is False and response.get("formal_apply") is False,
        "write_disabled": metadata.get("write_enabled") is False,
        "provider_called": bool(boundary.get("provider_called")),
        "model_called": bool(boundary.get("model_called")),
        "lean_forbidden_source_hit_count": len(forbidden_hits),
        "lean_source_gap_as_content_count": len(gap_hits),
    }
    artifact_dir = OUT / "case_responses"
    _write_json(artifact_dir / f"{case_id}.json", response)
    out["response_artifact"] = str((artifact_dir / f"{case_id}.json").relative_to(ROOT))
    return out


def _feature_flag_contract() -> dict[str, Any]:
    return {
        "stage": STAGE,
        "feature_flag": CANARY_ENV,
        "default": "legacy",
        "allowed_values": ["legacy", "lean_canary", "lean"],
        "canary_enabled_values": ["lean_canary", "lean"],
        "scope": "uploaded lesson readonly preview only",
        "request_overrides": {
            "preview_engine=legacy": "force legacy even when canary is on",
            "preview_engine=lean": "force lean even when canary is off",
            "preview_engine=auto or missing": "legacy when canary off; lean when canary on",
        },
        "must_not_affect": ["formal apply", "save/write", "R95 export", "R21/R36 core", "teacher main page visual"],
    }


def _metadata_contract() -> dict[str, Any]:
    return {
        "stage": STAGE,
        "required_response_metadata": {
            "preview_engine_requested": "auto | lean | legacy",
            "preview_engine_selected": "lean | legacy",
            "canary_enabled": "boolean",
            "fallback_used": "boolean",
            "fallback_reason": "string|null",
            "lean_chain_available": "boolean",
            "legacy_chain_available": "boolean",
            "formal_apply_enabled": False,
            "write_enabled": False,
        },
        "location": "response.preview_engine_metadata",
        "boundary_mirror": [
            "boundary.preview_engine_selected",
            "boundary.canary_enabled",
            "boundary.fallback_used",
            "boundary.formal_apply_enabled",
            "boundary.write_enabled",
        ],
    }


def _route_policy_doc() -> str:
    return "\n".join(
        [
            "# R201F Route Selection Policy",
            "",
            "| Request | Canary Flag | Selected Engine |",
            "| --- | --- | --- |",
            "| no `preview_engine` / `auto` | off | legacy |",
            "| no `preview_engine` / `auto` | on | lean |",
            "| `preview_engine=legacy` | on or off | legacy |",
            "| `preview_engine=lean` | on or off | lean, unless lean fails and fallback is required |",
            "",
            "The route remains `/api/prep-room/uploaded-lesson-entry-preview`. R201F does not delete the legacy path.",
            "",
        ]
    )


def _fallback_doc() -> str:
    return "\n".join(
        [
            "# R201F Fallback And Rollback Policy",
            "",
            "Lean preview must fall back to legacy or fail closed when source extraction is unsafe.",
            "",
            "Fallback reasons include:",
            "",
            "- `lean_source_extraction_low_confidence`",
            "- `lean_selected_extraction_empty`",
            "- `lean_single_lesson_template_empty`",
            "- `lean_teacher_main_forbidden_source`",
            "- `lean_source_gap_as_content`",
            "- `lean_route_exception:<type>`",
            "",
            "Rollback is immediate: set `XIAOBEI_UPLOAD_PREVIEW_DEFAULT_ENGINE=legacy` or send `preview_engine=legacy`.",
            "",
            "Fallback does not grant R200A/R200B/R97B_P3 teacher-main ownership.",
            "",
        ]
    )


def _old_vs_lean_artifacts() -> dict[str, str]:
    artifact_dir = OUT / "r201f_old_vs_lean_comparison_artifacts"

    def legacy_call():
        return r103.handle_upload_entry_preview(
            {"raw_text": OLD_SHOES_RAW, "file_name": "r201f_compare_old_shoes.txt", "preview_engine": "legacy"}
        )

    def lean_call():
        return r103.handle_upload_entry_preview(
            {"raw_text": OLD_SHOES_RAW, "file_name": "r201f_compare_old_shoes.txt", "preview_engine": "lean"}
        )

    legacy_response, legacy_status = _with_env("lean_canary", legacy_call)
    lean_response, lean_status = _with_env(None, lean_call)
    comparison = {
        "stage": STAGE,
        "sample": "old_shoes_zu_xia_sheng_hui",
        "legacy_status": legacy_status,
        "lean_status": lean_status,
        "legacy_engine_metadata": legacy_response.get("preview_engine_metadata"),
        "lean_engine_metadata": lean_response.get("preview_engine_metadata"),
        "lean_selected_parser": ((lean_response.get("selected_source_extraction") or {}).get("selected_parser_id") if isinstance(lean_response.get("selected_source_extraction"), dict) else None),
        "legacy_stage": legacy_response.get("stage"),
        "lean_stage": lean_response.get("stage"),
        "teacher_visible_by_default": False,
    }
    _write_json(artifact_dir / "old_shoes_legacy_response.json", legacy_response)
    _write_json(artifact_dir / "old_shoes_lean_response.json", lean_response)
    _write_json(artifact_dir / "old_shoes_comparison_summary.json", comparison)
    return {
        "legacy_response": str((artifact_dir / "old_shoes_legacy_response.json").relative_to(ROOT)),
        "lean_response": str((artifact_dir / "old_shoes_lean_response.json").relative_to(ROOT)),
        "comparison_summary": str((artifact_dir / "old_shoes_comparison_summary.json").relative_to(ROOT)),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sample_payload = {"raw_text": OLD_SHOES_RAW, "file_name": "r201f_old_shoes.txt"}
    bad_payload = {"raw_text": "这不是一份教案。", "file_name": "r201f_bad_source.txt"}
    cases = [
        _run_case("canary_off_default_legacy", env_value=None, payload=sample_payload, expected_engine="legacy"),
        _run_case("canary_on_default_lean", env_value="lean_canary", payload=sample_payload, expected_engine="lean"),
        _run_case("force_legacy_when_canary_on", env_value="lean_canary", payload={**sample_payload, "preview_engine": "legacy"}, expected_engine="legacy"),
        _run_case("force_lean_when_canary_off", env_value=None, payload={**sample_payload, "preview_engine": "lean"}, expected_engine="lean"),
        _run_case("lean_low_confidence_fallback_legacy", env_value="lean_canary", payload=bad_payload, expected_engine="legacy", expect_fallback=True),
    ]
    comparison_outputs = _old_vs_lean_artifacts()
    smoke_matrix = {
        "stage": STAGE,
        "cases": cases,
        "old_vs_lean_comparison_artifacts": comparison_outputs,
    }
    _write_json(OUT / "r201f_canary_feature_flag_contract.json", _feature_flag_contract())
    _write_text(OUT / "r201f_route_selection_policy.md", _route_policy_doc())
    _write_text(OUT / "r201f_fallback_and_rollback_policy.md", _fallback_doc())
    _write_json(OUT / "r201f_response_metadata_contract.json", _metadata_contract())
    _write_json(OUT / "r201f_canary_smoke_matrix.json", smoke_matrix)

    canary_off = next(item for item in cases if item["case_id"] == "canary_off_default_legacy")
    canary_on = next(item for item in cases if item["case_id"] == "canary_on_default_lean")
    force_legacy = next(item for item in cases if item["case_id"] == "force_legacy_when_canary_on")
    force_lean = next(item for item in cases if item["case_id"] == "force_lean_when_canary_off")
    fallback = next(item for item in cases if item["case_id"] == "lean_low_confidence_fallback_legacy")
    checks = {
        "canary_off_default_legacy": canary_off["selected_engine_matches_expected"] and canary_off["stage"] == "1013R_R103_REAL_UPLOAD_ENTRY_PREVIEW",
        "canary_on_default_lean": canary_on["selected_engine_matches_expected"] and canary_on["stage"] == "1013R_R201C_READONLY_ROUTE_SWITCH_TO_LEAN_CHAIN",
        "preview_engine_legacy_forces_legacy": force_legacy["selected_engine_matches_expected"] and force_legacy["stage"] == "1013R_R103_REAL_UPLOAD_ENTRY_PREVIEW",
        "preview_engine_lean_forces_lean": force_lean["selected_engine_matches_expected"] and force_lean["stage"] == "1013R_R201C_READONLY_ROUTE_SWITCH_TO_LEAN_CHAIN",
        "lean_failure_does_not_hard_generate_full_process": fallback["fallback_matches_expected"] and fallback["fallback_reason_present_when_needed"],
        "fallback_reason_traceable": bool((fallback["preview_engine_metadata"] or {}).get("fallback_reason")),
        "legacy_fallback_available": fallback["stage"] == "1013R_R103_REAL_UPLOAD_ENTRY_PREVIEW",
        "response_metadata_complete": all(
            set(
                [
                    "preview_engine_requested",
                    "preview_engine_selected",
                    "canary_enabled",
                    "fallback_used",
                    "fallback_reason",
                    "lean_chain_available",
                    "legacy_chain_available",
                    "formal_apply_enabled",
                    "write_enabled",
                ]
            ).issubset(set((item["preview_engine_metadata"] or {}).keys()))
            for item in cases
        ),
        "teacher_main_no_R200A_R200B_R97B_in_lean_cases": all(
            item["lean_forbidden_source_hit_count"] == 0 for item in [canary_on, force_lean]
        ),
        "source_gap_not_teacher_main_in_lean_cases": all(
            item["lean_source_gap_as_content_count"] == 0 for item in [canary_on, force_lean]
        ),
        "formal_apply_disabled": all(item["formal_apply_disabled"] for item in cases),
        "write_disabled": all(item["write_disabled"] for item in cases),
        "provider_not_called": all(not item["provider_called"] for item in cases),
        "model_not_called": all(not item["model_called"] for item in cases),
        "old_vs_lean_artifacts_written": all((ROOT / value).exists() for value in comparison_outputs.values()),
    }
    result = {
        "stage": STAGE,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "case_results": cases,
        "boundary": {
            "readonly_preview_canary_only": True,
            "full_default_switch": False,
            "formal_apply": False,
            "database_written": False,
            "feishu_written": False,
            "memory_written": False,
            "pptx_pdf_docx_generated": False,
            "R21_modified": False,
            "R36_modified": False,
            "R95_executed": False,
            "provider_called": any(item["provider_called"] for item in cases),
            "model_called": any(item["model_called"] for item in cases),
            "legacy_route_deleted": False,
        },
        "outputs": {
            "canary_feature_flag_contract": str((OUT / "r201f_canary_feature_flag_contract.json").relative_to(ROOT)),
            "route_selection_policy": str((OUT / "r201f_route_selection_policy.md").relative_to(ROOT)),
            "fallback_and_rollback_policy": str((OUT / "r201f_fallback_and_rollback_policy.md").relative_to(ROOT)),
            "response_metadata_contract": str((OUT / "r201f_response_metadata_contract.json").relative_to(ROOT)),
            "canary_smoke_matrix": str((OUT / "r201f_canary_smoke_matrix.json").relative_to(ROOT)),
            "old_vs_lean_comparison_artifacts": str((OUT / "r201f_old_vs_lean_comparison_artifacts").relative_to(ROOT)),
            "validation_result": str(RESULT.relative_to(ROOT)),
        },
    }
    _write_json(RESULT, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
