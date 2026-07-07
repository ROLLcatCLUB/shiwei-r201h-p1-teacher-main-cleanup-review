from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from flask import jsonify, request

from . import prep_room_document_text_extractor_1013R_R107A as document_text_extractor
from . import prep_room_graph_field_projection_1013R_R114C as graph_field_projection_builder
from . import prep_room_import_field_reasoning_bridge_1013R_R111 as field_reasoning_bridge
from . import prep_room_import_lesson_understanding_1013R_R112 as lesson_understanding_builder
from . import prep_room_import_understanding_v2_graph_1013R_R114A as understanding_v2_graph
from . import prep_room_art_curriculum_standard_candidate_1013R_R200C as art_curriculum_standard_candidate_builder
from . import prep_room_art_lesson_design_kernel_1013R_R200A as art_lesson_design_kernel_builder
from . import prep_room_art_lesson_reasoning_candidate_1013R_R200B as art_lesson_reasoning_candidate_builder
from . import prep_room_single_lesson_derivation_spine_1013R_R97B_P3 as derivation_spine_builder
from . import prep_room_source_ownership_policy_1013R_R200F as source_ownership_policy
from . import prep_room_teacher_execution_map_1013R_R114B as teacher_execution_map_builder
from . import prep_room_teacher_readable_draft_1013R_R110 as teacher_readable_draft
from . import prep_room_uploaded_lesson_readonly_preview_1013R_R101A as readonly_preview


STAGE_ID = "1013R_R103_REAL_UPLOAD_ENTRY_PREVIEW"
UPLOAD_ENTRY_ROUTE = "/api/prep-room/uploaded-lesson-entry-preview"
UPLOAD_DOCUMENT_ROUTE = "/api/prep-room/uploaded-lesson-document-preview"
UPLOAD_ACTION_ROUTE = "/api/prep-room/uploaded-lesson-entry-preview/action"
PROVISIONAL_LABEL = "系统临时生成 · 需教师判断"
TEST_RECORD_STAGE_ID = "1013R_R97B_P2D_UPLOAD_PREVIEW_TEST_RECORDS"
TEST_RECORD_DIR = (
    Path(__file__).resolve().parents[2]
    / "outputs"
    / "PREP_ROOM_RENDER_CANVAS_DEEPEN_V1"
    / TEST_RECORD_STAGE_ID
)
TEST_RECORD_JSONL = TEST_RECORD_DIR / "r97b_upload_preview_test_records.jsonl"
TEST_RECORD_LATEST = TEST_RECORD_DIR / "r97b_upload_preview_test_record_latest.json"
CANARY_DEFAULT_ENGINE_ENV = "XIAOBEI_UPLOAD_PREVIEW_DEFAULT_ENGINE"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _blankish(value: Any) -> bool:
    text = _clean(value)
    return text in {"", "无", "无。", "无；", "暂无", "未提供", "不涉及", "无需"}


def _value_or_empty(value: Any) -> str:
    text = _clean(value)
    return "" if _blankish(text) else text


def _slug(value: str) -> str:
    text = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "_", value or "uploaded_lesson").strip("_")
    return text[:40] or "uploaded_lesson"


def _short_sha(value: Any) -> str:
    text = str(value or "")
    return text[:12].lower()


def _progress_event(
    event_id: str,
    label: str,
    status: str = "completed",
    detail: str = "",
    **extra: Any,
) -> dict[str, Any]:
    event = {
        "event_id": event_id,
        "label": label,
        "status": status,
        "teacher_visible_text": detail or label,
        "source": "runtime_event",
        "token_cost": 0,
    }
    for key, value in extra.items():
        if value is not None:
            event[key] = value
    return event


def _append_progress_event(response: dict[str, Any], event: dict[str, Any]) -> None:
    events = response.setdefault("runtime_progress_events", [])
    if isinstance(events, list):
        events.append(event)


def _build_preview_progress_events(
    response: dict[str, Any],
    *,
    trigger: str,
    document_extract: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    template = response.get("single_lesson_template") or {}
    episodes = template.get("process_episodes") or []
    source_counts = _source_status_counts(template)
    boundary = response.get("boundary") or {}
    extract = document_extract or response.get("document_extract") or {}
    model_called = bool(boundary.get("model_called"))
    reasoning_candidate = response.get("art_lesson_reasoning_candidate_preview") or {}
    reasoning_status = str(reasoning_candidate.get("status") or "disabled")
    curriculum_candidate = response.get("curriculum_standard_candidate_preview") or {}
    curriculum_candidate_available = bool(curriculum_candidate.get("candidate_available"))
    if reasoning_status == "model_success":
        reasoning_event_status = "completed"
    elif reasoning_status in {"disabled", "provider_credentials_missing"}:
        reasoning_event_status = "skipped"
    else:
        reasoning_event_status = "failed"
    events = [
        _progress_event(
            "upload_input_received",
            "已接收上传内容",
            detail="已接收教案内容，只读预览，不保存原文。",
            trigger=trigger,
            file_name=(response.get("upload_session") or {}).get("file_name") or "",
        ),
    ]
    if trigger == "document_upload":
        events.append(
            _progress_event(
                "document_text_extracted",
                "已抽取文档文本",
                detail="已从文档中抽取正文，继续识别课题、字段和教学过程。",
                parser=extract.get("parser"),
                document_status=extract.get("status"),
                text_length=extract.get("text_length"),
            )
        )
    events.extend(
        [
            _progress_event(
                "upload_session_built",
                "已建立临时上传会话",
                detail="已生成临时 session 和 record_id 线索，仍不写入正式备课本。",
                session_id=(response.get("upload_session") or {}).get("session_id"),
            ),
            _progress_event(
                "lesson_fields_projected",
                "已归位教案字段",
                detail="已把课题、年级、单元和正文段落归位到只读预览字段。",
            ),
            _progress_event(
                "process_episodes_normalized",
                "已拆分教学过程环节",
                detail=f"已把教学过程规整为 {len(episodes)} 个环节，并进入 single_lesson_template。",
                episode_count=len(episodes),
            ),
            _progress_event(
                "derivation_spine_built",
                "已建立教案推导主干",
                detail="已把本课依据、学情、目标、重难点和教学过程挂到同一条只读推导链。",
                spine_status=(response.get("lesson_derivation_spine_preview") or {}).get("status"),
            ),
            _progress_event(
                "art_lesson_kernel_built",
                "已套入美术备课内核",
                detail="已区分课标候选/缺口、美术教学法规则和后续模型候选输入；当前仍是只读预览。",
                kernel_status=(response.get("art_lesson_design_kernel_preview") or {}).get("kernel_status"),
                standard_status=((response.get("art_lesson_design_kernel_preview") or {}).get("curriculum_standard_control") or {}).get("interpretation_status"),
            ),
            _progress_event(
                "curriculum_standard_candidate_bound",
                "已绑定课标候选切片",
                status="completed" if curriculum_candidate_available else "skipped",
                detail=(
                    f"已从本地 0928S 美术课标切片匹配 {len(curriculum_candidate.get('candidate_refs') or [])} 条候选依据；仍需教师确认。"
                    if curriculum_candidate_available
                    else "未形成可用课标候选切片，继续保留课标缺口标记。"
                ),
                candidate_id=curriculum_candidate.get("candidate_id"),
                candidate_count=len(curriculum_candidate.get("candidate_refs") or []),
                candidate_only=True,
            ),
            _progress_event(
                "source_gaps_checked",
                "已检查来源缺口",
                detail=f"已标记 {source_counts.get('source_gap', 0)} 处需教师确认的来源缺口。",
                source_gap_count=source_counts.get("source_gap", 0),
            ),
            _progress_event(
                "model_quality_checked",
                "已检查模型整理开关",
                status="completed" if model_called else "skipped",
                detail="已调用模型整理稿，结果只进入审校预览。"
                if model_called
                else "本次未启用模型整理稿，只使用解析和来源投影。",
                model_called=model_called,
                provider_called=bool(boundary.get("provider_called")),
            ),
            _progress_event(
                "art_reasoning_candidate_built",
                "已处理美术推理候选稿",
                status=reasoning_event_status,
                detail="已生成 provider-backed 美术推理候选稿；仅进入候选预览，不写入正式教案。"
                if reasoning_status == "model_success"
                else (
                    "本次未启用 R200B 美术推理候选，正文仍只来自解析、模板与规则内核。"
                    if reasoning_status == "disabled"
                    else f"R200B 美术推理候选未形成可用结果：{reasoning_status}。"
                ),
                candidate_id=reasoning_candidate.get("candidate_id"),
                candidate_available=bool(reasoning_candidate.get("candidate_available")),
                candidate_only=True,
                model_called=bool(reasoning_candidate.get("model_called")),
                provider_called=bool(reasoning_candidate.get("provider_called")),
            ),
            _progress_event(
                "readonly_preview_ready",
                "只读预览已生成",
                detail="已生成可检查的只读预览，等待教师确认；不保存、不导出、不写库。",
            ),
        ]
    )
    return events


def boundary_flags() -> dict[str, bool]:
    return {
        "stage": STAGE_ID,
        "real_upload_entry_preview": True,
        "temporary_upload_session_only": True,
        "real_upload_runtime_connected": False,
        "provider_called": False,
        "model_called": False,
        "runtime_call_allowed": False,
        "write_allowed": False,
        "database_written": False,
        "memory_written": False,
        "vector_index_written": False,
        "feishu_written": False,
        "pptx_generated": False,
        "pdf_docx_generated": False,
        "formal_apply_performed": False,
        "teacher_original_overwritten": False,
        "R21_modified": False,
        "R36_modified": False,
        "R95_executed": False,
        "main_shell_replaced": False,
        "render_layer_replaced": False,
        "static_html_created": False,
    }


def _source_status_counts(template: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    header = template.get("lesson_header") or {}
    for key in ["lesson_title", "unit_title", "grade", "lesson_code"]:
        if "上传原文未提供" in str(header.get(key) or ""):
            counts["source_gap"] = counts.get("source_gap", 0) + 1
    for section_key in [
        "basis",
        "student_analysis",
        "objectives",
        "key_difficult_points",
        "preparation",
        "assessment_or_homework",
        "reflection_or_notes",
    ]:
        for section in template.get(section_key) or []:
            status = section.get("source_status")
            if not status:
                continue
            key = str(status)
            counts[key] = counts.get(key, 0) + 1
    for episode in template.get("process_episodes") or []:
        for status in [
            episode.get("source_status"),
            episode.get("provenance"),
            *[micro.get("provenance") for micro in episode.get("micro_steps") or [] if isinstance(micro, dict)],
        ]:
            if not status:
                continue
            key = str(status)
            counts[key] = counts.get(key, 0) + 1
    return counts


def _build_upload_preview_test_record(response: dict[str, Any], trigger: str) -> dict[str, Any]:
    upload_session = response.get("upload_session") or {}
    template = response.get("single_lesson_template") or {}
    current_lesson = (response.get("prep_view_patch") or {}).get("current_lesson") or {}
    document_extract = response.get("document_extract") or {}
    runtime_progress_events = response.get("runtime_progress_events") or []
    art_kernel = response.get("art_lesson_design_kernel_preview") or {}
    art_reasoning_candidate = response.get("art_lesson_reasoning_candidate_preview") or {}
    curriculum_candidate = response.get("curriculum_standard_candidate_preview") or {}
    curriculum_control = art_kernel.get("curriculum_standard_control") if isinstance(art_kernel, dict) else {}
    if not isinstance(curriculum_control, dict):
        curriculum_control = {}
    source_counts = _source_status_counts(template)
    process_episodes = template.get("process_episodes") or []
    episode_titles = [
        str(episode.get("episode_title") or episode.get("title") or "")
        for episode in process_episodes
        if isinstance(episode, dict)
    ]
    parse_quality_flags = []
    if 0 < len(process_episodes) <= 1:
        parse_quality_flags.append("low_episode_count_review_required")
    if source_counts.get("source_gap", 0) > 0:
        parse_quality_flags.append("source_gap_present")
    if bool((response.get("boundary") or {}).get("model_called")):
        parse_quality_flags.append("model_called_review_required")
    if curriculum_control.get("interpretation_status") == "missing_structured_standard_ref":
        parse_quality_flags.append("structured_curriculum_standard_ref_missing")
    if curriculum_candidate.get("candidate_available"):
        parse_quality_flags.append("curriculum_standard_candidate_refs_available")
    lesson_focus = art_kernel.get("lesson_focus") if isinstance(art_kernel, dict) else {}
    if not isinstance(lesson_focus, dict):
        lesson_focus = {}
    main_section_diagnostic = _main_section_diagnostic_snapshot(template)
    visible_text_diagnostic = _visible_text_diagnostic_snapshot(template)
    focus_mismatch_flags = _focus_mismatch_flags(lesson_focus, visible_text_diagnostic)
    cross_topic_guard = art_kernel.get("cross_topic_guard") if isinstance(art_kernel, dict) else {}
    if isinstance(cross_topic_guard, dict) and cross_topic_guard.get("passed") is False:
        focus_mismatch_flags.append("r200a_cross_topic_visible_text_guard_failed")
    parse_quality_flags.extend(flag for flag in focus_mismatch_flags if flag not in parse_quality_flags)
    record_id = f"p2d_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{_short_sha(upload_session.get('raw_sha256'))}"
    return {
        "record_id": record_id,
        "stage": TEST_RECORD_STAGE_ID,
        "source_stage": response.get("stage") or STAGE_ID,
        "created_at": _now(),
        "trigger": trigger,
        "route": UPLOAD_DOCUMENT_ROUTE if trigger == "document_upload" else UPLOAD_ENTRY_ROUTE,
        "viewmodel_type": response.get("viewmodel_type"),
        "viewmodel_id": response.get("viewmodel_id"),
        "session_id": upload_session.get("session_id"),
        "raw_sha256_short": _short_sha(upload_session.get("raw_sha256")),
        "file_name": upload_session.get("file_name") or "",
        "lesson_title": current_lesson.get("lesson_title") or current_lesson.get("title") or "",
        "grade": current_lesson.get("grade") or "",
        "unit_title": (response.get("prep_view_patch") or {}).get("unit_title") or current_lesson.get("eyebrow") or "",
        "single_lesson_template_present": template.get("template_type") == "single_lesson_template",
        "template_route": template.get("route"),
        "template_episode_count": len(template.get("process_episodes") or []),
        "template_episode_titles": episode_titles[:12],
        "legacy_process_step_count": len(current_lesson.get("process_steps") or []),
        "source_status_counts": source_counts,
        "source_gap_count": source_counts.get("source_gap", 0),
        "provisional_candidate_count": source_counts.get("provisional_generated_candidate", 0),
        "parse_quality_flags": parse_quality_flags,
        "art_kernel_status": art_kernel.get("kernel_status") if isinstance(art_kernel, dict) else None,
        "lesson_focus_id": lesson_focus.get("focus_id"),
        "lesson_focus_description": lesson_focus.get("description"),
        "lesson_focus_matched_keywords": lesson_focus.get("matched_keywords") or [],
        "main_section_diagnostic": main_section_diagnostic,
        "visible_text_diagnostic": visible_text_diagnostic,
        "focus_mismatch_flags": focus_mismatch_flags,
        "cross_topic_guard": cross_topic_guard if isinstance(cross_topic_guard, dict) else {},
        "art_reasoning_candidate_status": art_reasoning_candidate.get("status") if isinstance(art_reasoning_candidate, dict) else None,
        "art_reasoning_candidate_available": bool(art_reasoning_candidate.get("candidate_available")) if isinstance(art_reasoning_candidate, dict) else False,
        "art_reasoning_candidate_id": art_reasoning_candidate.get("candidate_id") if isinstance(art_reasoning_candidate, dict) else None,
        "art_reasoning_candidate_only": bool(((art_reasoning_candidate.get("boundary") or {}) if isinstance(art_reasoning_candidate, dict) else {}).get("candidate_only")),
        "curriculum_standard_candidate_status": curriculum_candidate.get("status") if isinstance(curriculum_candidate, dict) else None,
        "curriculum_standard_candidate_id": curriculum_candidate.get("candidate_id") if isinstance(curriculum_candidate, dict) else None,
        "curriculum_standard_candidate_count": len(curriculum_candidate.get("candidate_refs") or []) if isinstance(curriculum_candidate, dict) else 0,
        "curriculum_standard_candidate_ref_ids": [
            item.get("slice_id")
            for item in (curriculum_candidate.get("candidate_refs") or [])[:8]
            if isinstance(item, dict) and item.get("slice_id")
        ] if isinstance(curriculum_candidate, dict) else [],
        "curriculum_standard_interpretation_status": curriculum_control.get("interpretation_status"),
        "official_curriculum_claim_created": curriculum_control.get("official_curriculum_claim_created"),
        "real_curriculum_standard_full_text_parsed": curriculum_control.get("real_curriculum_standard_full_text_parsed"),
        "document_parser": document_extract.get("parser"),
        "document_status": document_extract.get("status"),
        "document_text_length": document_extract.get("text_length"),
        "runtime_progress_event_count": len(runtime_progress_events) if isinstance(runtime_progress_events, list) else 0,
        "runtime_progress_events": [
            {
                "event_id": str(event.get("event_id") or ""),
                "label": str(event.get("label") or ""),
                "status": str(event.get("status") or ""),
                "teacher_visible_text": str(event.get("teacher_visible_text") or ""),
            }
            for event in runtime_progress_events[:20]
            if isinstance(event, dict)
        ] if isinstance(runtime_progress_events, list) else [],
        "provider_called": bool((response.get("boundary") or {}).get("provider_called")),
        "model_called": bool((response.get("boundary") or {}).get("model_called")),
        "template_first_expected": True,
        "preview_only": True,
        "formal_apply": False,
        "database_written": False,
        "raw_text_recorded": False,
        "note": "Local preview diagnostic record only. It does not save the lesson, write database, or formal apply.",
    }


def _template_section_items_for_record(template: dict[str, Any], section_key: str, limit: int = 5) -> list[str]:
    value = template.get(section_key)
    if not isinstance(value, list) or not value or not isinstance(value[0], dict):
        return []
    body = value[0].get("body")
    if isinstance(body, str):
        raw_items = [body]
    elif isinstance(body, list):
        raw_items = body
    else:
        raw_items = []
    return [_clean(item)[:220] for item in raw_items if _clean(item)][:limit]


def _main_section_diagnostic_snapshot(template: dict[str, Any]) -> dict[str, list[str]]:
    if not isinstance(template, dict):
        return {}
    return {
        "basis": _template_section_items_for_record(template, "basis"),
        "student_analysis": _template_section_items_for_record(template, "student_analysis"),
        "objectives": _template_section_items_for_record(template, "objectives"),
        "key_difficult_points": _template_section_items_for_record(template, "key_difficult_points"),
    }


def _visible_text_diagnostic_snapshot(template: dict[str, Any]) -> dict[str, list[str]]:
    diagnostic = _main_section_diagnostic_snapshot(template)
    episodes = []
    micro_steps = []
    for episode in template.get("process_episodes") or []:
        if not isinstance(episode, dict):
            continue
        for key in ["episode_title", "episode_goal", "teacher_organization", "student_learning", "key_talk", "evidence"]:
            value = episode.get(key)
            if isinstance(value, list):
                episodes.extend(_clean(item)[:220] for item in value if _clean(item))
            elif _clean(value):
                episodes.append(_clean(value)[:220])
        for micro in episode.get("micro_steps") or []:
            if not isinstance(micro, dict):
                continue
            for key in ["title", "step_name", "teacher_action", "student_action", "screen_or_materials", "scaffolds", "evidence"]:
                value = micro.get(key)
                if isinstance(value, list):
                    micro_steps.extend(_clean(item)[:220] for item in value if _clean(item))
                elif _clean(value):
                    micro_steps.append(_clean(value)[:220])
    diagnostic["process_episodes"] = episodes[:20]
    diagnostic["micro_steps"] = micro_steps[:30]
    return diagnostic


def _focus_mismatch_flags(lesson_focus: dict[str, Any], diagnostic: dict[str, list[str]]) -> list[str]:
    focus_id = str(lesson_focus.get("focus_id") or "")
    joined = "\n".join(item for values in diagnostic.values() for item in values)
    flags: list[str] = []
    if focus_id == "shoe_observation_drawing_expression" and any(
        token in joined for token in ["渐变", "色阶", "颜色逐步", "逐步过渡", "直接跳色", "青绿山水"]
    ):
        flags.append("focus_body_mismatch_color_gradation_terms_in_shoe_lesson")
    if focus_id == "color_gradation_expression" and any(token in joined for token in ["鞋底", "鞋面", "鞋带", "鞋的结构"]):
        flags.append("focus_body_mismatch_shoe_terms_in_color_lesson")
    return flags


def _attach_upload_preview_test_record(response: dict[str, Any], trigger: str) -> dict[str, Any]:
    record = _build_upload_preview_test_record(response, trigger)
    try:
        TEST_RECORD_DIR.mkdir(parents=True, exist_ok=True)
        with TEST_RECORD_JSONL.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        TEST_RECORD_LATEST.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        record_status = "written"
    except OSError as exc:
        record_status = "failed"
        record = {
            **record,
            "write_error": str(exc),
        }
    response["preview_test_record"] = {
        **record,
        "record_status": record_status,
        "record_path": str(TEST_RECORD_JSONL),
        "latest_record_path": str(TEST_RECORD_LATEST),
    }
    _append_progress_event(
        response,
        _progress_event(
            "preview_test_record_written",
            "已写入本地测试记录",
            status="completed" if record_status == "written" else "failed",
            detail="已写入本地测试记录，便于测试沟通和自检。"
            if record_status == "written"
            else "本地测试记录写入失败，但不影响只读预览响应。",
            record_id=record.get("record_id"),
        ),
    )
    return response


def _field(field: str, classification: str, value: Any, source: str, confidence: float) -> dict[str, Any]:
    provisional = classification == "provisional_generated_candidate"
    teacher_required = classification in {"low_confidence_confirm", "source_gap", "provisional_generated_candidate"}
    return {
        "field": field,
        "classification": classification,
        "value": value,
        "source": source,
        "confidence": confidence,
        "provisional_generated": provisional,
        "teacher_judgment_required": teacher_required,
        "notice": PROVISIONAL_LABEL if provisional else ("需教师确认" if teacher_required else None),
    }


def _source_gap(field: str, source: str = "上传原文未提供") -> dict[str, Any]:
    return _field(field, "source_gap", "上传原文未提供；需教师确认。", source, 0.0)


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _preview_engine_requested(payload: dict[str, Any]) -> str:
    raw = str(payload.get("preview_engine") or payload.get("engine") or "auto").strip().lower()
    if raw in {"lean", "r201c", "lean_chain"}:
        return "lean"
    if raw in {"legacy", "r103", "old"}:
        return "legacy"
    return "auto"


def _canary_enabled() -> bool:
    return str(os.environ.get(CANARY_DEFAULT_ENGINE_ENV) or "").strip().lower() in {"lean_canary", "lean"}


def _selected_preview_engine(requested: str, canary_enabled: bool) -> str:
    if requested == "lean":
        return "lean"
    if requested == "legacy":
        return "legacy"
    return "lean" if canary_enabled else "legacy"


def _attach_preview_engine_metadata(
    response: dict[str, Any],
    *,
    requested: str,
    selected: str,
    canary_enabled: bool,
    fallback_used: bool = False,
    fallback_reason: str | None = None,
) -> dict[str, Any]:
    metadata = {
        "preview_engine_requested": requested,
        "preview_engine_selected": selected,
        "canary_enabled": canary_enabled,
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason,
        "lean_chain_available": True,
        "legacy_chain_available": True,
        "formal_apply_enabled": False,
        "write_enabled": False,
    }
    response["preview_engine_metadata"] = metadata
    boundary = response.setdefault("boundary", {})
    if isinstance(boundary, dict):
        boundary["preview_engine_selected"] = selected
        boundary["canary_enabled"] = canary_enabled
        boundary["fallback_used"] = fallback_used
        boundary["formal_apply_enabled"] = False
        boundary["write_enabled"] = False
    return response


def _lean_response_fallback_reason(response: dict[str, Any], status_code: int) -> str:
    if status_code != 200:
        return f"lean_route_status_{status_code}"
    selected = response.get("selected_source_extraction") if isinstance(response.get("selected_source_extraction"), dict) else {}
    source_gap = selected.get("source_gap") if isinstance(selected.get("source_gap"), dict) else {}
    if selected.get("low_confidence") or source_gap.get("active"):
        return "lean_source_extraction_low_confidence"
    if not selected.get("episodes"):
        return "lean_selected_extraction_empty"
    template = response.get("single_lesson_template") if isinstance(response.get("single_lesson_template"), dict) else {}
    if not template.get("process_episodes"):
        return "lean_single_lesson_template_empty"
    ledger = response.get("ownership_ledger") if isinstance(response.get("ownership_ledger"), dict) else {}
    if ledger.get("forbidden_source_hits"):
        return "lean_teacher_main_forbidden_source"
    if ledger.get("source_gap_as_content_hits"):
        return "lean_source_gap_as_content"
    return ""


def _one(pattern: str, text: str, default: str = "") -> str:
    match = re.search(pattern, text, flags=re.M)
    return _clean(match.group(1)) if match else default


def _clean_markdown(value: Any) -> str:
    text = str(value or "").replace("\\_", "_").replace("\\*", "*")
    text = re.sub(r"^[#>\s]+", "", text)
    text = re.sub(r"[*`]+", "", text)
    return _clean(text)


def _clean_teacher_text(value: Any) -> str:
    text = str(value or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\\*", "*").replace("\\_", "_").replace("\\#", "#")
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"^\s*[-:| ]{3,}\s*$", "", text, flags=re.M)
    text = re.sub(r"^\s*#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"^\s*>\s*", "", text, flags=re.M)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.M)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"[*`]+", "", text)
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    return text.strip()


def _compact_teacher_text(value: Any) -> str:
    return _clean(_clean_teacher_text(value))


def _split_numbered_teacher_items(value: Any) -> list[str]:
    text = _clean_teacher_text(value)
    if not text:
        return []
    text = re.sub(r"(?<!\d)(?P<num>[1-9][0-9]?[.．、])\s*", r"\n\g<num> ", text)
    lines: list[str] = []
    for raw_line in text.split("\n"):
        line = _clean(raw_line)
        if not line:
            continue
        if re.fullmatch(r"[-:| ]+", line):
            continue
        line = re.sub(r"^\|?[-:| ]+\|?$", "", line).strip()
        if not line:
            continue
        lines.append(line)
    return lines


def _goal_value_from_text(value: Any) -> list[str] | str:
    lines = _split_numbered_teacher_items(value)
    if not lines:
        return ""
    goals: list[str] = []
    pending_prefix = ""
    for line in lines:
        line = re.sub(r"^(?:课时目标|教学目标|学习目标)\s*[：:]\s*", "", line)
        prefix_match = re.match(r"^(学生能|学生能够|学习者能|能)\s*[：:]\s*$", line)
        if prefix_match:
            pending_prefix = prefix_match.group(1)
            continue
        line = re.sub(r"^[1-9][0-9]?[.．、]\s*", "", line).strip()
        line = re.sub(r"^(学生能|学生能够|学习者能)\s*[：:]\s*", "", line).strip()
        if pending_prefix and not line.startswith(("学生", "能")):
            line = f"{pending_prefix}{line}"
        pending_prefix = ""
        line = line.strip("；;。 ")
        if line:
            goals.append(line + "。")
    if len(goals) == 1:
        return goals[0]
    return goals[:6]


def _teacher_value(value: Any) -> Any:
    if isinstance(value, list):
        return [_teacher_value(item) for item in value if _compact_teacher_text(item)]
    if isinstance(value, dict):
        return {
            key: _teacher_value(item)
            for key, item in value.items()
        }
    if isinstance(value, str):
        return _compact_teacher_text(value)
    return value


def _prep_value_from_text(value: Any) -> Any:
    text = _clean_teacher_text(value)
    if not text:
        return ""
    parts = re.split(r"【(学生|教师|老师)准备】", text)
    if len(parts) < 3:
        return _teacher_value(text)
    items: list[str] = []
    for index in range(1, len(parts), 2):
        label = "教师" if parts[index] in {"教师", "老师"} else "学生"
        body = parts[index + 1] if index + 1 < len(parts) else ""
        body = re.sub(r"^（[^）]*）", "", body).strip()
        body = re.sub(r"\s*\n\s*", "；", body)
        body = re.sub(r"\s{2,}", " ", body)
        body = body.strip("；;。 ")
        if body:
            items.append(f"{label}准备：{body}。")
    return items or _teacher_value(text)


def _label_value(raw_text: str, labels: list[str]) -> str:
    for line in raw_text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        plain = _clean_markdown(line)
        for label in labels:
            match = re.match(rf"^{re.escape(label)}\s*[：:]\s*(?P<value>.+)$", plain)
            if match:
                return _clean(match.group("value"))
    return ""


def _table_label_value(raw_text: str, labels: list[str]) -> str:
    for line in raw_text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if not line.strip().startswith("|"):
            continue
        cells = [_clean_markdown(cell) for cell in line.strip().strip("|").split("|")]
        if len(cells) < 2 or cells[0] in {"字段", "------", "---"}:
            continue
        for label in labels:
            if cells[0] != label:
                continue
            for cell in cells[1:]:
                text = _clean(cell)
                if not text or text in {"M", "S", "M+S", "M/S", "字段来源", "填写说明"}:
                    continue
                case_match = re.search(r"本案例填写[：:]\s*(?P<value>[^；;。|]+)", text)
                if case_match:
                    return _clean(case_match.group("value"))
                if re.search(r"(第[一二三四五六七八九十0-9]+单元|课时\s*[一二三四五六七八九十0-9]+|年级|《[^》]+》)", text):
                    return text
    return ""


def _title_from_heading(raw_text: str) -> str:
    for line in raw_text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if not line.lstrip().startswith("#"):
            continue
        plain = _clean_markdown(line)
        bracket = re.search(r"《(?P<title>[^》]{2,40})》", plain)
        if bracket:
            return _clean(bracket.group("title"))
        plain = re.sub(r"^课时\s*\d+\s*", "", plain)
        plain = re.sub(r"^第[一二三四五六七八九十0-9]+单元\s*", "", plain)
        plain = re.sub(r"(教案|教学过程案例.*|大单元备课文档|备课文档|大单元备课)$", "", plain)
        plain = re.split(r"[；;|｜]", plain)[0]
        plain = plain.strip(" ：:-_（）()")
        if 2 <= len(plain) <= 40:
            return plain
    return ""


def _title_from_leading_line(raw_text: str) -> str:
    for line in raw_text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        plain = _clean_markdown(line)
        if not plain:
            continue
        if re.match(r"^(一|二|三|四|五|六|七|八|九|十)[、.．]", plain):
            return ""
        if 2 <= len(plain) <= 40:
            return plain
        return ""
    return ""


def _unit_from_heading(raw_text: str) -> str:
    first_heading = ""
    for line in raw_text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line.lstrip().startswith("#"):
            first_heading = _clean_markdown(line)
            break
    match = re.search(r"(第[一二三四五六七八九十0-9]+单元)[《：:\s]*(?P<title>[^》\s]+)", first_heading)
    if match:
        return _clean(f"{match.group(1)} {match.group('title')}")
    return ""


def _table_blocks(raw_text: str) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in raw_text.splitlines():
        if line.strip().startswith("|"):
            current.append(line)
            continue
        if current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks


def _is_true_process_table(idx: dict[str, int]) -> bool:
    required = {"教学的步骤", "步骤顺序", "步骤名称", "步骤时长", "教师话术", "学生任务"}
    return required.issubset(set(idx))


def _lesson_title_from_cell(value: str) -> str:
    text = _clean(value)
    text = re.sub(r"^课时\s*[一二三四五六七八九十0-9]+\s*[：:、.-]\s*", "", text)
    text = text.strip("《》 ：:-")
    return text


def _lesson_period_from_cell(value: str) -> str:
    match = re.search(r"课时\s*[一二三四五六七八九十0-9]+", _clean(value))
    return _clean(match.group(0)) if match else ""


def _process_table_meta(raw_text: str) -> dict[str, str]:
    for block in _table_blocks(raw_text):
        header, rows = parse_markdown_table(block)
        if not header or not rows:
            continue
        idx = {name: i for i, name in enumerate(header)}
        if not _is_true_process_table(idx):
            continue
        first = rows[0]
        lesson_cell = _safe_index(first, idx.get("子课时名"))
        meta = {
            "unit": _value_or_empty(_safe_index(first, idx.get("所属大单元"))),
            "title": _lesson_title_from_cell(lesson_cell),
            "period": _lesson_period_from_cell(lesson_cell),
        }
        return {key: value for key, value in meta.items() if value}
    return {}


def extract_meta(raw_text: str) -> dict[str, str]:
    process_meta = _process_table_meta(raw_text)
    title = (
        _label_value(raw_text, ["子课时名", "课题", "课题名称", "名称"])
        or process_meta.get("title")
        or _table_label_value(raw_text, ["子课时名", "课题", "课题名称", "名称"])
        or _title_from_heading(raw_text)
        or _title_from_leading_line(raw_text)
        or _one(r"#\s*课时\d+《([^》]+)》", raw_text)
        or _one(r"#\s*《([^》]+)》", raw_text)
    )
    unit = (
        _label_value(raw_text, ["所属大单元", "大单元"])
        or _unit_from_heading(raw_text)
        or process_meta.get("unit")
        or _table_label_value(raw_text, ["所属大单元", "大单元"])
        or _table_label_value(raw_text, ["单元"])
        or _label_value(raw_text, ["单元"])
    )
    grade = _label_value(raw_text, ["年级", "适用年级"]) or _table_label_value(raw_text, ["年级", "适用年级"])
    period = process_meta.get("period") or _label_value(raw_text, ["课时", "总课时长"]) or _table_label_value(raw_text, ["课时", "总课时长"])
    core = _label_value(raw_text, ["核心活动", "核心表现性任务"]) or section_between_any(raw_text, ["核心活动"])
    return {"title": title, "unit": unit, "grade": grade, "period": period, "core_activity": core}


def section_between(raw_text: str, heading: str) -> str:
    pattern = rf"##\s*(?:\d+(?:\.\d+)*\s*)?{re.escape(heading)}[^\n]*\n(?P<body>.*?)(?=\n---\n\n##|\n##\s+|\Z)"
    match = re.search(pattern, raw_text, flags=re.S)
    return match.group("body").strip() if match else ""


SECTION_STOP_HEADINGS = (
    "本课依据|教材分析|学情分析|教学目标|课时目标|学习目标|主要内容|核心活动|证据节点|"
    "教学重难点|重点难点|教学准备|材料说明|教学过程|教学流程|"
    "教学环节表|完整填写内容|评价要点|评价方式|学习评价|学习单|PPT素材说明|PPT页面清单|"
    "给小美|教学反思|作业"
)


def _is_section_stop_line(line: str) -> bool:
    clean = _clean_markdown(re.sub(r"^[#\s]*", "", str(line or "").strip()))
    clean = re.sub(r"^[一二三四五六七八九十0-9]+[、.．]\s*", "", clean)
    clean = re.sub(r"^\d+(?:\.\d+)*\s*", "", clean)
    if clean.startswith("|") and any(token in clean for token in ["所属大单元", "教学的步骤", "步骤名称"]):
        return True
    return bool(re.match(rf"^(?:{SECTION_STOP_HEADINGS})(?:\s|$|[·：:（(])", clean))


def _trim_section_text(text: str) -> str:
    lines = [line.strip() for line in str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    kept: list[str] = []
    for index, line in enumerate(lines):
        if index > 0 and _is_section_stop_line(line):
            break
        kept.append(line)
    return "\n".join(line for line in kept if line).strip()


def section_between_any(raw_text: str, headings: list[str]) -> str:
    markdown = ""
    for heading in headings:
        markdown = section_between(raw_text, heading)
        if markdown:
            return _trim_section_text(markdown)

    lines = [line.strip() for line in raw_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    start = -1
    for index, line in enumerate(lines):
        clean = re.sub(r"^[#\s]*", "", line).strip()
        clean = re.sub(r"^[一二三四五六七八九十0-9]+[、.．]\s*", "", clean)
        clean = re.sub(r"^\d+(?:\.\d+)*\s*", "", clean)
        clean = _clean_markdown(clean)
        if any(re.match(rf"^{re.escape(heading)}(?:\\s|$|[·：:（(])", clean) for heading in headings):
            start = index + 1
            break
    if start < 0:
        return ""
    end = len(lines)
    for index in range(start, len(lines)):
        line = lines[index].strip()
        if index > start and _is_section_stop_line(line):
            end = index
            break
    return _trim_section_text("\n".join(line for line in lines[start:end] if line))


def parse_markdown_table(lines: list[str]) -> tuple[list[str], list[list[str]]]:
    header: list[str] = []
    rows: list[list[str]] = []
    for line in lines:
        if not line.strip().startswith("|"):
            continue
        cells = [
            _clean_markdown(cell)
            for cell in line.strip().strip("|").split("|")
        ]
        if all(not cell for cell in cells):
            continue
        if all(re.fullmatch(r":?-{3,}:?", cell or "") for cell in cells):
            continue
        if not header:
            header = cells
        else:
            rows.append(cells)
    return header, rows


def _safe_index(row: list[str], index: int | None, default: str = "") -> str:
    if index is None or index < 0 or index >= len(row):
        return default
    return row[index]


def _int_text(value: str, default: int = 0) -> int:
    digits = re.sub(r"\D", "", value or "")
    return int(digits) if digits else default


def _looks_like_tech_support(value: str) -> bool:
    text = _clean(value)
    if not text:
        return False
    return bool(re.search(r"(PPT|投影仪|实物投影|白板|大屏|图片|视频|课件)", text))


def _looks_like_success_standard(value: str) -> bool:
    text = _clean(value)
    if not text:
        return False
    return bool(
        re.search(
            r"^(能|能够|完成|说出|指出|画出|做出|描述|选择|展示|用|理解|区分|调出|形成|清晰)"
            r"|石青|石绿|色阶|水多|越来越|深浅|规律|层次",
            text,
        )
    )


def _looks_like_blank_or_tech_support(value: str) -> bool:
    return _blankish(value) or _looks_like_tech_support(value)


EPISODE_FIELD_LABELS = [
    "步骤名称",
    "步骤时长",
    "步骤目标",
    "教师话术",
    "教师活动",
    "教师组织",
    "学生任务",
    "学生活动",
    "学生学习",
    "材料需求",
    "教学材料",
    "技术支持",
    "大屏材料",
    "成功标准",
    "评价标准",
    "学习证据",
    "引导问题",
    "反馈要点",
    "备注",
    "PPT页面说明",
    "授课教师",
    "年级",
]


def _episode_field_value(block: str, labels: list[str]) -> str:
    label_alt = "|".join(re.escape(label) for label in labels)
    stop_alt = "|".join(re.escape(label) for label in EPISODE_FIELD_LABELS)
    pattern = (
        rf"(?ms)^\s*(?:[-*]\s*)?(?:\*\*)?\s*(?:{label_alt})\s*[：:]\s*(?:\*\*)?\s*"
        rf"(?P<value>.*?)(?="
        rf"\n\s*(?:[-*]\s*)?(?:\*\*)?\s*(?:{stop_alt})\s*[：:]"
        rf"|\n\s*---\s*$"
        rf"|\n\s*#{1,6}\s*(?:课时\s*\d+\s*[-－—–])?\s*步骤\s*\d+"
        rf"|\Z)"
    )
    match = re.search(pattern, block)
    if not match:
        return ""
    value = match.group("value")
    value = re.sub(r"\n{2,}", "\n", value)
    value = re.sub(r"^\s*(?:\*\*)?\s*$", "", value, flags=re.M)
    return _value_or_empty(_clean_teacher_text(value))


def _line_heading_step_matches(raw_text: str) -> list[re.Match[str]]:
    heading = re.compile(
        r"(?m)^\s*#{1,6}\s*"
        r"(?:课时\s*\d+\s*[-－—–])?\s*步骤\s*(?P<index>\d+)\s*[-－—–:：]\s*(?P<title>[^\n]+?)\s*$"
    )
    return list(heading.finditer(raw_text))


def _flat_step_matches(raw_text: str) -> list[re.Match[str]]:
    flat = re.compile(
        r"(?m)(?<!如[：:])(?<!如)"
        r"课时\s*\d+\s*[-－—–]\s*步骤\s*(?P<index>\d+)\s*[-－—–:：]\s*(?P<title>[^\n|]{2,40})"
    )
    return list(flat.finditer(raw_text))


def _episode_from_labeled_block(index: int, title: str, block: str) -> dict[str, Any] | None:
    field_title = _episode_field_value(block, ["步骤名称"])
    title = _value_or_empty(field_title or title)
    if not title:
        return None
    teacher_action = _episode_field_value(block, ["教师话术", "教师活动", "教师组织"])
    student_action = _episode_field_value(block, ["学生任务", "学生活动", "学生学习"])
    goal = _episode_field_value(block, ["步骤目标"])
    evidence = _episode_field_value(block, ["成功标准", "评价标准", "学习证据"])
    if not any([teacher_action, student_action, goal, evidence]):
        return None
    material = _episode_field_value(block, ["材料需求", "教学材料"])
    screen_or_tech = _episode_field_value(block, ["技术支持", "大屏材料", "PPT页面说明"])
    return {
        "index": index,
        "title": title,
        "duration_min": _int_text(_episode_field_value(block, ["步骤时长"])),
        "source_content": teacher_action or goal or title,
        "goal": goal,
        "teacher_action": teacher_action,
        "student_action": student_action,
        "material": material,
        "screen_or_tech": screen_or_tech,
        "evidence": evidence,
        "question": _episode_field_value(block, ["引导问题"]),
        "feedback": _episode_field_value(block, ["反馈要点"]),
    }


def parse_table_episodes(raw_text: str) -> list[dict[str, Any]]:
    episodes: list[dict[str, Any]] = []
    for block in _table_blocks(raw_text):
        header, rows = parse_markdown_table(block)
        if not header or not rows:
            continue
        idx = {name: i for i, name in enumerate(header)}
        if "步骤名称" in idx and "步骤时长" in idx and _is_true_process_table(idx):
            for row in rows:
                if len(row) < 4:
                    continue
                order = _int_text(_safe_index(row, idx.get("步骤顺序")), len(episodes) + 1)
                title = _value_or_empty(_safe_index(row, idx.get("步骤名称")))
                if not title:
                    continue
                material = _value_or_empty(_safe_index(row, idx.get("材料需求")))
                screen_or_tech = _value_or_empty(_safe_index(row, idx.get("技术支持")))
                evidence = _value_or_empty(_safe_index(row, idx.get("成功标准")))
                question = _value_or_empty(_safe_index(row, idx.get("引导问题")))
                feedback = _value_or_empty(_safe_index(row, idx.get("反馈要点")))
                remark = _value_or_empty(_safe_index(row, idx.get("备注")))
                if _looks_like_blank_or_tech_support(evidence) and _looks_like_success_standard(question):
                    screen_or_tech = "；".join(
                        item for item in [screen_or_tech, evidence] if _looks_like_tech_support(item)
                    )
                    evidence = question
                    question = feedback
                    feedback = remark
                elif _looks_like_blank_or_tech_support(evidence) and _looks_like_success_standard(feedback):
                    screen_or_tech = "；".join(item for item in [screen_or_tech, evidence] if _looks_like_tech_support(item))
                    evidence = feedback
                    feedback = remark
                teacher_action = _value_or_empty(_safe_index(row, idx.get("教师话术")))
                student_action = _value_or_empty(_safe_index(row, idx.get("学生任务")))
                goal = _value_or_empty(_safe_index(row, idx.get("步骤目标")))
                episodes.append(
                    {
                        "index": order,
                        "title": title,
                        "duration_min": _int_text(_safe_index(row, idx.get("步骤时长"))),
                        "source_content": teacher_action or goal or title,
                        "goal": goal,
                        "teacher_action": teacher_action,
                        "student_action": student_action,
                        "material": material,
                        "screen_or_tech": screen_or_tech,
                        "evidence": evidence,
                        "question": question,
                        "feedback": feedback,
                    }
                )
        elif "环节名" in idx and "主要内容" in idx:
            for row in rows:
                order = _int_text(_safe_index(row, idx.get("步骤")), len(episodes) + 1)
                title = _value_or_empty(_safe_index(row, idx.get("环节名")))
                content = _value_or_empty(_safe_index(row, idx.get("主要内容"))) or title
                if not title:
                    continue
                episodes.append(
                    {
                        "index": order,
                        "title": title,
                        "duration_min": _int_text(_safe_index(row, idx.get("时长"))),
                        "source_content": content,
                        "goal": content,
                        "teacher_action": content,
                        "student_action": "",
                        "material": "",
                        "screen_or_tech": "",
                        "evidence": "",
                        "question": "",
                        "feedback": "",
                    }
                )
        elif "课时" in idx and ("名称" in idx or "课题" in idx) and "核心活动" in idx:
            title_index = idx.get("名称") if "名称" in idx else idx.get("课题")
            for row in rows:
                lesson_no = _safe_index(row, idx.get("课时"))
                title = _value_or_empty(_safe_index(row, title_index))
                content = _value_or_empty(_safe_index(row, idx.get("核心活动"))) or title
                if not title or "评价维度" in title:
                    continue
                episodes.append(
                    {
                        "index": _int_text(lesson_no, len(episodes) + 1),
                        "title": f"{lesson_no} {title}".strip(),
                        "duration_min": None,
                        "source_content": content,
                        "goal": content,
                        "teacher_action": content,
                        "student_action": "",
                        "material": _value_or_empty(_safe_index(row, idx.get("工具"))),
                        "screen_or_tech": "",
                        "evidence": _value_or_empty(_safe_index(row, idx.get("作业"))),
                        "question": "",
                        "feedback": "",
                    }
                )
    return episodes


def parse_long_section_episodes(raw_text: str) -> list[dict[str, Any]]:
    matches = _line_heading_step_matches(raw_text)
    episodes: list[dict[str, Any]] = []
    for offset, match in enumerate(matches):
        end = matches[offset + 1].start() if offset + 1 < len(matches) else len(raw_text)
        block = raw_text[match.end():end]
        episode = _episode_from_labeled_block(
            _int_text(match.group("index"), len(episodes) + 1),
            _clean_markdown(match.group("title")),
            block,
        )
        if episode:
            episodes.append(episode)
    return episodes


def parse_flat_labeled_episodes(raw_text: str) -> list[dict[str, Any]]:
    matches = _flat_step_matches(raw_text)
    episodes: list[dict[str, Any]] = []
    for offset, match in enumerate(matches):
        end = matches[offset + 1].start() if offset + 1 < len(matches) else len(raw_text)
        block = raw_text[match.start():end]
        if "字段名" in block[:120] or "行标识" in block[:120]:
            continue
        episode = _episode_from_labeled_block(
            _int_text(match.group("index"), len(episodes) + 1),
            _clean_markdown(match.group("title")),
            block,
        )
        if episode:
            episodes.append(episode)
    return episodes


def parse_bracket_heading_episodes(raw_text: str) -> list[dict[str, Any]]:
    process_text = section_between_any(raw_text, ["教学过程", "教学流程", "教学环节", "课堂过程", "主要内容"])
    if not process_text:
        return []
    lines = [line.strip() for line in process_text.replace("\r\n", "\n").replace("\r", "\n").split("\n") if line.strip()]
    episodes: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    heading_re = re.compile(
        r"^(?:[*`\\\s]*)?[【\[](?P<title>[^】\]·]{2,36})(?:[·。．](?P<duration>\d+)\s*分钟)?[】\]](?:[*`\\\s]*)*$"
    )
    for line in lines:
        match = heading_re.match(line)
        if match:
            if current:
                episodes.append(current)
            current = {
                "index": len(episodes) + 1,
                "title": _clean_markdown(match.group("title")),
                "duration_min": _int_text(match.group("duration") or ""),
                "source_content": "",
            }
            continue
        if current:
            cleaned = _clean_markdown(re.sub(r"^-+\s*", "", line))
            if cleaned:
                current["source_content"] = _clean(f"{current.get('source_content', '')} {cleaned}")
    if current:
        episodes.append(current)

    normalized: list[dict[str, Any]] = []
    for episode in episodes[:10]:
        title = str(episode.get("title") or f"环节{len(normalized) + 1}")
        content = str(episode.get("source_content") or title)
        normalized.append(
            {
                "index": episode.get("index") or len(normalized) + 1,
                "title": title,
                "duration_min": episode.get("duration_min") or None,
                "source_content": content,
                "goal": content,
                "teacher_action": content,
                "student_action": "",
                "material": "",
                "screen_or_tech": "",
                "evidence": "",
                "question": "",
                "feedback": "",
            }
        )
    return normalized


def parse_plain_process_episodes(raw_text: str) -> list[dict[str, Any]]:
    process_text = section_between_any(raw_text, ["教学过程", "教学流程", "教学环节", "课堂过程", "主要内容"])
    if not process_text and re.search(r"(课时\d+-步骤\d+|教学的步骤|环节名|教师话术)", raw_text):
        process_text = raw_text
    if not process_text:
        return []
    source_lines = [
        line.strip()
        for line in process_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if line.strip()
    ]
    episodes: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    heading_re = re.compile(
        r"^(?:#{1,4}\s*)?(?:[（(]?([一二三四五六七八九十]|\d+)[）)]?[、.．]?\s*)"
        r"(?P<title>[^：:\n]{2,36})(?:[：:]\s*)?(?P<body>.*)$"
    )
    title_keys = "看|拆|试|变|做|评|导入|观察|示范|创作|展示|评价|小结|认识|探索|练习|制作|交流|总结|介绍|讨论|收尾|展评|引入"
    for line in source_lines:
        if re.search(r"(评价维度JSON|```json|assignment_id|dimensions|max_score)", line):
            continue
        match = heading_re.match(line)
        if match and re.search(title_keys, match.group("title")):
            if current:
                episodes.append(current)
            current = {
                "index": len(episodes) + 1,
                "title": _clean(match.group("title")),
                "source_content": _clean(match.group("body")) or _clean(match.group("title")),
            }
            continue
        if current:
            current["source_content"] = _clean(f"{current.get('source_content', '')} {line}")
    if current:
        episodes.append(current)
    normalized: list[dict[str, Any]] = []
    for episode in episodes[:10]:
        title = str(episode.get("title") or f"环节{len(normalized) + 1}")
        content = str(episode.get("source_content") or title)
        normalized.append(
            {
                "index": episode.get("index") or len(normalized) + 1,
                "title": title,
                "duration_min": None,
                "source_content": content,
                "goal": content,
                "teacher_action": content,
                "student_action": "",
                "material": "",
                "screen_or_tech": "",
                "evidence": "",
                "question": "",
                "feedback": "",
            }
        )
    return normalized


def classify_episode_type(title: str, index: int, total: int) -> str:
    if index == 1 or any(key in title for key in ["导入", "引入"]):
        return "情境导入型"
    if any(key in title for key in ["示范", "演示"]):
        return "技法示范型"
    if any(key in title for key in ["练习", "创作", "探索", "制作"]):
        return "操作练习型"
    if index == total or any(key in title for key in ["小结", "总结", "分享", "展示"]):
        return "展示收束型"
    if any(key in title for key in ["观察", "认识", "远观", "近触"]):
        return "观察辨析型"
    return "课堂推进型"


def normalize_episodes(raw_text: str) -> list[dict[str, Any]]:
    episodes = (
        parse_long_section_episodes(raw_text)
        or parse_flat_labeled_episodes(raw_text)
        or parse_table_episodes(raw_text)
        or parse_bracket_heading_episodes(raw_text)
        or parse_plain_process_episodes(raw_text)
    )
    normalized: list[dict[str, Any]] = []
    total = len(episodes)
    for raw in episodes:
        index = int(raw.get("index") or len(normalized) + 1)
        title = readonly_preview.clean_generated_candidate_text(raw.get("title") or f"环节{index}")
        title = re.sub(r"步骤时长|步骤目标|教师话术|学生任务", "", str(title)).strip(" ：:-")
        episode_type = classify_episode_type(title, index, total)
        source_gap_note = []
        teacher_action = _value_or_empty(raw.get("teacher_action"))
        student_action = _value_or_empty(raw.get("student_action"))
        evidence = _value_or_empty(raw.get("evidence"))
        goal = _value_or_empty(raw.get("goal"))
        source_content = _value_or_empty(raw.get("source_content")) or teacher_action or goal or title
        if not teacher_action:
            source_gap_note.append("上传原文未提供明确教师组织；需教师确认。")
        if not student_action:
            source_gap_note.append("上传原文未提供明确学生学习；需教师确认。")
        if not evidence:
            source_gap_note.append("上传原文未提供明确学习证据；需教师确认。")
        normalized.append(
            {
                "index": index,
                "title": title,
                "duration_min": raw.get("duration_min") or None,
                "source_content": source_content,
                "goal": goal,
                "teacher_action": teacher_action,
                "student_action": student_action,
                "material": _value_or_empty(raw.get("material")),
                "screen_or_tech": _value_or_empty(raw.get("screen_or_tech")),
                "evidence": evidence,
                "question": _value_or_empty(raw.get("question")),
                "feedback": _value_or_empty(raw.get("feedback")),
                "episode_id": f"uploaded_entry_episode_{index:02d}",
                "episode_type": episode_type,
                "source_gap_note": source_gap_note,
                "provisional_scaffolds": [],
                "screen_material_suggestions": [],
                "teacher_talk_suggestions": [],
                "metadata_slots": {
                    "raw_duration": raw.get("duration_min"),
                    "raw_question": raw.get("question"),
                    "raw_feedback": raw.get("feedback"),
                },
                "teacher_review_required": True,
                "preview_only": True,
                "formal_apply": False,
            }
        )
    return normalized


def build_fields(raw_text: str, meta: dict[str, str], episodes: list[dict[str, Any]]) -> dict[str, Any]:
    goal_text = section_between_any(raw_text, ["课时目标", "教学目标", "学习目标"]) or meta.get("core_activity")
    analysis_text = section_between_any(raw_text, ["学情分析", "学情"])
    keypoint_text = section_between_any(raw_text, ["教学重难点", "重点难点"])
    prep_text = section_between_any(raw_text, ["材料说明", "教学准备", "课前准备", "材料准备"])
    assessment_text = section_between_any(raw_text, ["评价要点", "评价方式", "评价标准", "学习评价"])
    screen_text = section_between_any(raw_text, ["PPT素材说明", "PPT页面清单", "大屏材料"])
    title = meta.get("title") or "未命名上传教案"
    grade = meta.get("grade")
    goal_value = _goal_value_from_text(goal_text)
    analysis_value = _teacher_value(analysis_text)
    keypoint_value = _teacher_value(keypoint_text)
    prep_value = _prep_value_from_text(prep_text)
    assessment_value = _teacher_value(assessment_text)
    screen_value = _teacher_value(screen_text)
    fields = {
        "课题": _field("课题", "uploaded_evidence", title, "上传原文标题", 0.92) if meta.get("title") else _source_gap("课题"),
        "年级": _field("年级", "uploaded_evidence", grade, "上传原文年级", 0.9) if grade else _source_gap("年级"),
        "教材/单元": _field("教材/单元", "high_confidence_mapping", meta["unit"], "上传原文所属大单元", 0.8) if meta.get("unit") else _source_gap("教材/单元"),
        "课时": _field("课时", "uploaded_evidence", meta["period"], "上传原文课时", 0.86) if meta.get("period") else _source_gap("课时"),
        "教学目标": _field("教学目标", "uploaded_evidence" if section_between_any(raw_text, ["课时目标", "教学目标", "学习目标"]) else "high_confidence_mapping", goal_value, "课时目标或核心活动；R110清洗为教师可读条目", 0.78) if goal_value else _source_gap("教学目标"),
        "学情": _field("学情", "uploaded_evidence", analysis_value, "上传原文学情分析", 0.78) if analysis_value else _source_gap("学情"),
        "教学重难点": _field("教学重难点", "uploaded_evidence", keypoint_value, "上传原文教学重难点", 0.78) if keypoint_value else _source_gap("教学重难点"),
        "教学准备": _field("教学准备", "high_confidence_mapping", prep_value, "材料说明；R110清洗为教师可读文本", 0.78) if prep_value else _source_gap("教学准备"),
        "教学过程": _field("教学过程", "high_confidence_mapping", f"{len(episodes)} episodes", "教学过程表或步骤段落", 0.88) if episodes else _source_gap("教学过程"),
        "评价方式": _field("评价方式", "high_confidence_mapping", assessment_value, "评价要点；R110清洗为教师可读文本", 0.75) if assessment_value else _source_gap("评价方式"),
        "大屏材料": _field("大屏材料", "uploaded_evidence", screen_value, "上传原文PPT素材说明", 0.7) if screen_value else _source_gap("大屏材料"),
        "小教支持": _source_gap("小教支持", "上传原文未提供小教支持"),
    }
    return fields


def sample_context_from_meta(session_id: str, meta: dict[str, str]) -> dict[str, Any]:
    title = meta.get("title") or "未命名上传教案"
    unit = meta.get("unit") or "上传教案单元待确认"
    grade = meta.get("grade") or "年级待确认"
    node_id = f"upload_preview_{_slug(title)}_{session_id[-6:]}"
    return {
        "tree": [
            {
                "id": f"upload_unit_{session_id[-8:]}",
                "label": unit,
                "type": "unit",
                "unit_no": None,
                "lessons": [
                    {
                        "id": node_id,
                        "code": "preview",
                        "title": title,
                        "page": None,
                        "active": True,
                        "source_status": "uploaded_lesson_entry_preview",
                    }
                ],
            }
        ],
        "node_id": node_id,
        "unit_title": unit,
        "lesson_title": title,
        "display_title": f"上传预览《{title}》",
        "grade": grade,
    }


def _apply_import_field_candidates_to_sections(sections: list[dict[str, Any]], preview: dict[str, Any]) -> None:
    candidates = preview.get("field_candidates") if isinstance(preview, dict) else {}
    if not isinstance(candidates, dict):
        return
    for section in sections:
        section_id = str(section.get("id") or "")
        candidate = candidates.get(section_id)
        if not isinstance(candidate, dict):
            continue
        items = candidate.get("items")
        if isinstance(items, list) and any(_clean(item) for item in items):
            section["items"] = [_clean(item) for item in items if _clean(item)]
        section["source_capsules"] = list(candidate.get("source_capsules") or [])
        section["source_policy"] = candidate.get("source_policy")
        section["classification"] = candidate.get("classification") or section.get("classification")
        section["field_reasoning_stage"] = preview.get("stage")
        section["field_reasoning_status"] = preview.get("status")
        section["teacher_review_required"] = True
        section["preview_only"] = True
        section["formal_apply"] = False


def _apply_lesson_understanding_to_process_steps(steps: list[dict[str, Any]], preview: dict[str, Any]) -> None:
    understanding = preview.get("understanding") if isinstance(preview, dict) else {}
    if not isinstance(understanding, dict):
        return
    episodes = understanding.get("episode_understanding") or []
    if not isinstance(episodes, list):
        return
    by_source = {
        str(item.get("source_episode_id")): item
        for item in episodes
        if isinstance(item, dict) and item.get("source_episode_id")
    }
    by_title = {
        _clean(item.get("title")): item
        for item in episodes
        if isinstance(item, dict) and _clean(item.get("title"))
    }
    for step in steps:
        item = by_source.get(str(step.get("source_episode_id"))) or by_title.get(_clean(step.get("title")))
        if not isinstance(item, dict):
            continue
        step["understanding_stage"] = preview.get("stage")
        step["understanding_status"] = preview.get("status")
        step["learning_role"] = item.get("learning_role")
        step["source_content"] = item.get("source_excerpt") or step.get("source_content")
        step["teacher_action"] = item.get("teacher_intent") or step.get("teacher_action")
        step["student_action"] = item.get("student_task") or step.get("student_action")
        step["evidence"] = item.get("evidence_to_watch") or step.get("evidence")
        step["provisional_scaffolds"] = [
            _clean(item.get("support_or_risk")) or "支架需教师结合学生材料、工具安全和完成进度判断。",
            "本环节已先经过 R112 理解层，不再逐句搬运原文。",
        ]


def build_upload_session(raw_text: str, file_name: str = "") -> dict[str, Any]:
    raw_sha = hashlib.sha256(raw_text.encode("utf-8")).hexdigest().upper()
    session_id = f"upload_preview_{raw_sha[:12].lower()}"
    meta = extract_meta(raw_text)
    episodes = normalize_episodes(raw_text)
    fields = build_fields(raw_text, meta, episodes)
    return {
        "session_id": session_id,
        "raw_sha256": raw_sha,
        "raw_text": raw_text,
        "raw_excerpt": raw_text[:500],
        "file_name": file_name,
        "meta": meta,
        "fields": fields,
        "episodes": episodes,
        "boundary": boundary_flags(),
    }


def build_readonly_viewmodel_from_upload_session(
    session: dict[str, Any],
    enable_teacher_model: bool | None = None,
    enable_art_reasoning_model: bool | None = None,
) -> dict[str, Any]:
    context = sample_context_from_meta(session["session_id"], session["meta"])
    fields = session["fields"]
    lesson_title = context["lesson_title"]
    steps = readonly_preview.build_process_steps(session["episodes"])
    current_lesson = {
        "id": context["node_id"],
        "title": context["display_title"],
        "lesson_title": lesson_title,
        "eyebrow": context["unit_title"],
        "grade": readonly_preview._field_items(fields.get("年级") or {"value": context["grade"]})[0],
        "term": "真实上传入口只读预览",
        "textbook_page": None,
        "status": "临时只读预览",
        "badges": ["真实上传入口 preview", "临时 session", "只读渲染", "不保存"],
        "sections": readonly_preview.build_sections(fields, lesson_title),
        "process_steps": steps,
        "provisional_generation_notice": f"{PROVISIONAL_LABEL}；不覆盖上传原文。",
    }
    single_lesson_template = readonly_preview.build_single_lesson_template_from_current_lesson(
        current_lesson,
        template_id=f"r103_real_upload::{session['session_id']}",
        route="uploaded_lesson",
        source_status="uploaded_source",
    )
    model_quality_enabled = _truthy(os.environ.get("XIAOBEI_R110_TEACHER_DRAFT_MODEL")) if enable_teacher_model is None else bool(enable_teacher_model)
    art_reasoning_model_enabled = model_quality_enabled if enable_art_reasoning_model is None else bool(enable_art_reasoning_model)
    teacher_readable_preview = teacher_readable_draft.build_teacher_readable_preview(
        session,
        enable_model=model_quality_enabled,
    )
    import_lesson_understanding_preview = lesson_understanding_builder.build_import_lesson_understanding_preview(
        session,
        enable_model=model_quality_enabled,
    )
    import_understanding_v2_graph_preview = understanding_v2_graph.build_import_understanding_v2_graph_preview(
        session,
        r112_preview=import_lesson_understanding_preview,
        enable_model=model_quality_enabled,
    )
    import_teacher_execution_map_preview = teacher_execution_map_builder.build_teacher_execution_map_preview(
        import_understanding_v2_graph_preview,
        enable_model=model_quality_enabled,
    )
    import_graph_field_projection_preview = graph_field_projection_builder.build_graph_field_projection_preview(
        import_understanding_v2_graph_preview,
        import_teacher_execution_map_preview,
        enable_model=model_quality_enabled,
    )
    import_field_reasoning_preview = field_reasoning_bridge.build_import_field_reasoning_preview(
        session,
        enable_model=model_quality_enabled,
        lesson_understanding=import_lesson_understanding_preview,
    )
    lesson_derivation_spine_preview = derivation_spine_builder.build_derivation_spine(
        single_lesson_template=single_lesson_template,
        import_understanding_v2_graph_preview=import_understanding_v2_graph_preview,
        import_teacher_execution_map_preview=import_teacher_execution_map_preview,
        import_graph_field_projection_preview=import_graph_field_projection_preview,
    )
    derivation_spine_builder.apply_derivation_spine_to_current_lesson_sections(
        current_lesson,
        lesson_derivation_spine_preview,
    )
    derivation_spine_builder.apply_derivation_spine_to_template(
        single_lesson_template,
        lesson_derivation_spine_preview,
    )
    r200f_teacher_main_baseline = {
        "single_lesson_template": deepcopy(single_lesson_template),
        "current_lesson": {
            "sections": deepcopy(current_lesson.get("sections") or []),
            "process_steps": deepcopy(current_lesson.get("process_steps") or []),
        },
    }
    art_lesson_design_kernel_preview = art_lesson_design_kernel_builder.build_art_lesson_design_kernel_preview(
        single_lesson_template=single_lesson_template,
        lesson_derivation_spine_preview=lesson_derivation_spine_preview,
        import_understanding_v2_graph_preview=import_understanding_v2_graph_preview,
    )
    art_lesson_design_kernel_builder.apply_art_kernel_to_current_lesson_sections(
        current_lesson,
        art_lesson_design_kernel_preview,
    )
    current_lesson["lesson_focus_preview"] = (
        art_lesson_design_kernel_preview.get("lesson_focus")
        if isinstance(art_lesson_design_kernel_preview, dict)
        else {}
    )
    art_lesson_design_kernel_builder.apply_art_kernel_to_template(
        single_lesson_template,
        art_lesson_design_kernel_preview,
    )
    curriculum_standard_candidate_preview = art_curriculum_standard_candidate_builder.build_curriculum_standard_candidate_preview(
        single_lesson_template=single_lesson_template,
        art_lesson_design_kernel_preview=art_lesson_design_kernel_preview,
    )
    art_curriculum_standard_candidate_builder.apply_curriculum_standard_candidate_to_art_kernel(
        art_lesson_design_kernel_preview,
        curriculum_standard_candidate_preview,
    )
    art_curriculum_standard_candidate_builder.apply_curriculum_standard_candidate_to_template(
        single_lesson_template,
        curriculum_standard_candidate_preview,
    )
    art_curriculum_standard_candidate_builder.apply_curriculum_standard_candidate_to_current_lesson(
        current_lesson,
        curriculum_standard_candidate_preview,
    )
    art_lesson_reasoning_candidate_preview = art_lesson_reasoning_candidate_builder.build_art_lesson_reasoning_candidate_preview(
        single_lesson_template=single_lesson_template,
        lesson_derivation_spine_preview=lesson_derivation_spine_preview,
        art_lesson_design_kernel_preview=art_lesson_design_kernel_preview,
        enable_model=art_reasoning_model_enabled,
    )
    if model_quality_enabled:
        _apply_import_field_candidates_to_sections(
            current_lesson["sections"],
            import_field_reasoning_preview,
        )
        _apply_lesson_understanding_to_process_steps(
            current_lesson["process_steps"],
            import_lesson_understanding_preview,
        )
    else:
        current_lesson["reasoning_application_status"] = "skipped_by_default_for_p2f_parse_quality_smoke"
    response = {
        "ok": True,
        "stage": STAGE_ID,
        "viewmodel_type": "prep_room_real_upload_entry_preview",
        "viewmodel_id": session["session_id"],
        "generated_at": _now(),
        "upload_session": {
            "session_id": session["session_id"],
            "raw_sha256": session["raw_sha256"],
            "file_name": session.get("file_name"),
            "raw_preserved": True,
            "raw_excerpt": session["raw_excerpt"],
            "persisted": False,
            "teacher_original_overwritten": False,
        },
        "source_round": "R103 real upload entry preview from request payload",
        "render_contract": {
            "target_shell": "existing_prep_room_shell",
            "target_state": "uploaded_lesson_entry_preview",
            "target_slot": "prep_notebook.current_lesson",
            "process_slot": "current_lesson.process_steps",
            "single_lesson_template_slot": "single_lesson_template",
            "must_preserve": ["top_shell", "left_unit_tree", "middle_prep_notebook_sections", "right_courseware_rail", "bottom_xiaojiao_input"],
            "renderer_must_not": ["replace_full_shell", "create_standalone_html", "write_database_or_memory", "formal_apply"],
        },
        "single_lesson_template": single_lesson_template,
        "prep_view_patch": {
            "active_view": "prepNotebook",
            "active_node_id": context["node_id"],
            "grade": current_lesson["grade"],
            "term": "真实上传入口只读预览",
            "unit_title": context["unit_title"],
            "lesson_tree": context["tree"],
            "current_lesson": current_lesson,
            "single_lesson_template": single_lesson_template,
        },
        "courseware_screen_patch": readonly_preview.build_courseware_screens(steps),
        "right_rail_patch": {
            "mode": "uploaded_lesson_session_episode_only",
            "screen_ids": [f"U{i:02d}" for i in range(1, len(steps) + 1)],
            "session_id": session["session_id"],
            "must_not_show": ["色彩的渐变", "多彩的世界", "P6 色彩渐变联动"],
        },
        "xiaojiao_context_patch": {
            "session_id": session["session_id"],
            "default_episode_id": "U01" if steps else None,
            "rows": [
                {
                    "episode_id": step["episode_id"],
                    "episode_title": step["title"],
                    "next_action_hint": (step.get("teacher_talk_suggestions") or [""])[0],
                    "evidence_check": step.get("evidence"),
                    "runtime_call_allowed": False,
                    "preview_only": True,
                }
                for step in steps
            ],
            "runtime_call_allowed": False,
        },
        "runtime_actions": readonly_preview.runtime_actions(),
        "boundary": boundary_flags(),
        "teacher_readable_quality_preview": teacher_readable_preview,
        "import_lesson_understanding_preview": import_lesson_understanding_preview,
        "import_understanding_v2_graph_preview": import_understanding_v2_graph_preview,
        "import_teacher_execution_map_preview": import_teacher_execution_map_preview,
        "import_graph_field_projection_preview": import_graph_field_projection_preview,
        "lesson_derivation_spine_preview": lesson_derivation_spine_preview,
        "art_lesson_design_kernel_preview": art_lesson_design_kernel_preview,
        "curriculum_standard_candidate_preview": curriculum_standard_candidate_preview,
        "art_lesson_reasoning_candidate_preview": art_lesson_reasoning_candidate_preview,
        "import_field_reasoning_preview": import_field_reasoning_preview,
        "teacher_review_required": True,
        "formal_apply": False,
    }
    source_ownership_policy.apply_response_ownership_gate(
        response,
        r200f_teacher_main_baseline,
    )
    response["boundary"]["provider_called"] = bool(
        teacher_readable_preview.get("provider_called")
        or import_lesson_understanding_preview.get("provider_called")
        or import_understanding_v2_graph_preview.get("provider_called")
        or import_teacher_execution_map_preview.get("provider_called")
        or import_graph_field_projection_preview.get("provider_called")
        or import_field_reasoning_preview.get("provider_called")
        or curriculum_standard_candidate_preview.get("provider_called")
        or art_lesson_reasoning_candidate_preview.get("provider_called")
    )
    response["boundary"]["model_called"] = bool(
        teacher_readable_preview.get("model_called")
        or import_lesson_understanding_preview.get("model_called")
        or import_understanding_v2_graph_preview.get("model_called")
        or import_teacher_execution_map_preview.get("model_called")
        or import_graph_field_projection_preview.get("model_called")
        or import_field_reasoning_preview.get("model_called")
        or curriculum_standard_candidate_preview.get("model_called")
        or art_lesson_reasoning_candidate_preview.get("model_called")
    )
    response["boundary"]["old_generation_chain_modified"] = False
    response["runtime_progress_events"] = _build_preview_progress_events(response, trigger="raw_text_upload")
    return response


def handle_upload_entry_preview(payload: Any) -> tuple[dict[str, Any], int]:
    if not isinstance(payload, dict):
        payload = {}
    raw_text = str(payload.get("raw_text") or payload.get("text") or "").strip()
    if not raw_text:
        return {
            "ok": False,
            "stage": STAGE_ID,
            "error_code": "UPLOAD_PREVIEW_RAW_TEXT_REQUIRED",
            "teacher_visible_message": "请先粘贴一份教案原文，再进入只读预览。",
            "boundary": boundary_flags(),
        }, 400

    requested_engine = _preview_engine_requested(payload)
    canary = _canary_enabled()
    selected_engine = _selected_preview_engine(requested_engine, canary)

    def build_legacy_response(*, fallback_used: bool = False, fallback_reason: str | None = None) -> tuple[dict[str, Any], int]:
        session = build_upload_session(raw_text, str(payload.get("file_name") or ""))
        teacher_model_enabled = _truthy(
            payload.get("enable_teacher_readable_model")
            or payload.get("enable_model_quality")
            or payload.get("r110_teacher_draft")
        )
        art_reasoning_model_enabled = _truthy(payload.get("enable_r200b_candidate_reasoning"))
        legacy_response = build_readonly_viewmodel_from_upload_session(
            session,
            enable_teacher_model=teacher_model_enabled,
            enable_art_reasoning_model=art_reasoning_model_enabled,
        )
        _attach_preview_engine_metadata(
            legacy_response,
            requested=requested_engine,
            selected="legacy",
            canary_enabled=canary,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
        )
        _attach_upload_preview_test_record(
            legacy_response,
            "raw_text_upload_fallback_legacy" if fallback_used else "raw_text_upload_legacy",
        )
        return legacy_response, 200

    if selected_engine == "lean":
        from . import prep_room_lean_readonly_chain_1013R_R201C as lean_readonly_chain

        try:
            response, status_code = lean_readonly_chain.handle_upload_entry_preview_lean(payload)
        except Exception as exc:  # pragma: no cover - defensive canary fallback.
            return build_legacy_response(fallback_used=True, fallback_reason=f"lean_route_exception:{type(exc).__name__}")
        fallback_reason = _lean_response_fallback_reason(response, status_code) if isinstance(response, dict) else f"lean_route_status_{status_code}"
        if fallback_reason:
            return build_legacy_response(fallback_used=True, fallback_reason=fallback_reason)
        _attach_preview_engine_metadata(
            response,
            requested=requested_engine,
            selected="lean",
            canary_enabled=canary,
            fallback_used=False,
            fallback_reason=None,
        )
        _attach_upload_preview_test_record(response, "raw_text_upload_lean")
        return response, status_code

    return build_legacy_response()


def handle_upload_document_preview(file_storage: Any, form_data: Any | None = None) -> tuple[dict[str, Any], int]:
    if file_storage is None or not getattr(file_storage, "filename", ""):
        return {
            "ok": False,
            "stage": STAGE_ID,
            "error_code": "UPLOAD_DOCUMENT_REQUIRED",
            "teacher_visible_message": "请先选择 docx、pdf、txt 或 md 文件。",
            "boundary": boundary_flags(),
        }, 400

    original_filename = str(file_storage.filename or "uploaded_lesson")
    suffix = ("." + original_filename.rsplit(".", 1)[-1].lower()) if "." in original_filename else ""
    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(prefix="xiaobei_upload_preview_", suffix=suffix, delete=False) as tmp:
            temp_path = tmp.name
        file_storage.save(temp_path)
        extract_result = document_text_extractor.extract_document_text(
            temp_path,
            original_filename=original_filename,
            enable_model_ocr=False,
        )
    finally:
        if temp_path:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except OSError:
                pass

    if not extract_result.get("ok"):
        return {
            "ok": False,
            "stage": STAGE_ID,
            "error_code": extract_result.get("status") or "DOCUMENT_TEXT_EXTRACT_FAILED",
            "document_extract": {
                key: value
                for key, value in extract_result.items()
                if key not in {"text"}
            },
            "teacher_visible_message": extract_result.get("teacher_visible_message")
            or "文档未能抽出正文，请改用粘贴正文。",
            "boundary": boundary_flags(),
        }, 400

    session = build_upload_session(str(extract_result.get("text") or ""), original_filename)
    form_data = form_data or {}
    teacher_model_enabled = _truthy(
        form_data.get("enable_teacher_readable_model")
        or form_data.get("enable_model_quality")
        or form_data.get("r110_teacher_draft")
    )
    art_reasoning_model_enabled = _truthy(form_data.get("enable_r200b_candidate_reasoning"))
    response = build_readonly_viewmodel_from_upload_session(
        session,
        enable_teacher_model=teacher_model_enabled,
        enable_art_reasoning_model=art_reasoning_model_enabled,
    )
    response["document_extract"] = {
        key: value
        for key, value in extract_result.items()
        if key not in {"text"}
    }
    response["source_round"] = "R107A MarkItDown document preview to R103 readonly upload entry"
    response["runtime_progress_events"] = _build_preview_progress_events(
        response,
        trigger="document_upload",
        document_extract=response["document_extract"],
    )
    _attach_upload_preview_test_record(response, "document_upload")
    return response, 200


def handle_upload_preview_action(payload: Any) -> tuple[dict[str, Any], int]:
    if not isinstance(payload, dict):
        payload = {}
    action_id = str(payload.get("action_id") or "").strip()
    session_id = str(payload.get("session_id") or "upload_preview_unsaved").strip()
    actions = {item["action_id"]: item for item in readonly_preview.runtime_actions()}
    if action_id not in actions:
        return {
            "ok": False,
            "stage": STAGE_ID,
            "error_code": "UNKNOWN_UPLOAD_ENTRY_PREVIEW_ACTION",
            "known_action_ids": sorted(actions),
            "boundary": boundary_flags(),
        }, 400
    return {
        "ok": True,
        "stage": STAGE_ID,
        "accepted_action": deepcopy(actions[action_id]),
        "state_patch_preview": {
            "session_id": session_id,
            "last_action_id": action_id,
            "write_allowed": False,
            "formal_apply_performed": False,
            "teacher_confirmation_required": True,
            "message": "真实上传入口仍处于只读预览：不保存、不导出、不覆盖原文。",
        },
        "boundary": boundary_flags(),
    }, 200


def register_routes(bp, cors_preflight):
    @bp.route(UPLOAD_ENTRY_ROUTE, methods=["POST", "OPTIONS"])
    def prep_room_real_upload_entry_preview_1013r_r103():
        if request.method == "OPTIONS":
            return cors_preflight()
        payload = request.get_json(silent=True)
        response, status_code = handle_upload_entry_preview(payload)
        return jsonify(response), status_code

    @bp.route(UPLOAD_DOCUMENT_ROUTE, methods=["POST", "OPTIONS"])
    def prep_room_real_upload_document_preview_1013r_r107a():
        if request.method == "OPTIONS":
            return cors_preflight()
        response, status_code = handle_upload_document_preview(request.files.get("file"), request.form)
        return jsonify(response), status_code

    @bp.route(UPLOAD_ACTION_ROUTE, methods=["POST", "OPTIONS"])
    def prep_room_real_upload_entry_preview_action_1013r_r103():
        if request.method == "OPTIONS":
            return cors_preflight()
        payload = request.get_json(silent=True)
        response, status_code = handle_upload_preview_action(payload)
        return jsonify(response), status_code
