from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any


STAGE_ID = "1013R_R114C_GRAPH_FIELD_PROJECTION"

CORE_SECTION_ORDER = [
    "basis",
    "analysis",
    "goals",
    "keypoints",
    "preparation",
    "assessment",
    "reflection",
]

SECTION_TITLES = {
    "basis": "一、本课依据",
    "analysis": "二、学情分析",
    "goals": "三、教学目标",
    "keypoints": "四、教学重难点",
    "preparation": "五、教学准备",
    "assessment": "七、学习单与评价",
    "reflection": "八、课堂后记",
}


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _truncate(value: Any, limit: int = 260) -> str:
    text = _clean(value)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _contains(value: Any, tokens: list[str]) -> bool:
    text = _json_text(value)
    return any(token in text for token in tokens)


def _claim_lookup(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("claim_id")): item
        for item in graph.get("claim_registry") or []
        if isinstance(item, dict) and item.get("claim_id")
    }


def _identity_claim(graph: dict[str, Any], key: str) -> dict[str, Any]:
    identity = graph.get("lesson_identity") or {}
    item = identity.get(key) or {}
    return item if isinstance(item, dict) else {}


def _claim_text(claim: dict[str, Any], prefix: str = "") -> str:
    text = _clean(claim.get("text"))
    if prefix and text.startswith(prefix):
        return _clean(text[len(prefix) :])
    return text


def _lesson_title(graph: dict[str, Any]) -> str:
    return _claim_text(_identity_claim(graph, "title"), "课题：") or "上传教案"


def _unit_title(graph: dict[str, Any]) -> str:
    return _claim_text(_identity_claim(graph, "unit"), "单元：") or "上传单元待确认"


def _grade(graph: dict[str, Any]) -> str:
    return _claim_text(_identity_claim(graph, "grade"), "年级：") or "年级待确认"


def _source_summary(graph: dict[str, Any]) -> dict[str, Any]:
    faithful = graph.get("faithful_reconstruction") or {}
    summary = faithful.get("source_evidence_summary") or {}
    return summary if isinstance(summary, dict) else {}


def _core_transform(graph: dict[str, Any]) -> dict[str, Any]:
    core = graph.get("core_learning_transformation") or {}
    return core if isinstance(core, dict) else {"text": _clean(core)}


def _feature_flags(graph: dict[str, Any]) -> dict[str, bool]:
    lookup = _claim_lookup(graph)
    protected_ids = ((graph.get("faithful_reconstruction") or {}).get("protected_core_claim_ids") or [])
    protected_claims = [lookup.get(str(claim_id)) for claim_id in protected_ids]
    protected_text = _json_text([claim for claim in protected_claims if isinstance(claim, dict)])
    learning_text = _json_text(
        {
            "identity": graph.get("lesson_identity") or {},
            "core_learning_transformation": graph.get("core_learning_transformation") or {},
            "protected": protected_claims,
        }
    )
    confirmation_text = _json_text(graph.get("teacher_confirmation_gaps") or [])
    shoe_observation = _contains(
        learning_text,
        ["足下生辉", "画画鞋", "鞋的观察", "鞋面", "鞋底", "鞋带", "正面", "侧面", "局部细节", "线描"],
    ) or _contains(protected_text, ["鞋的观察", "鞋面", "鞋底", "鞋带", "线条"])
    return {
        "shoe_observation": shoe_observation,
        "prior_design": _contains(protected_text, ["设计草图", "前序设计"]),
        "reused_materials": _contains(protected_text, ["废旧材料", "旧材料", "变废为宝"]),
        "design_story": _contains(protected_text, ["设计故事", "5句话", "五句话"]),
        "launch": _contains(protected_text, ["发布会", "展示/发布证据"]),
        "tool_safety": _contains(confirmation_text, ["剪刀", "胶水", "热熔胶"]),
        "gradient": (not shoe_observation) and _contains(learning_text, ["渐变", "颜色过渡", "颜色慢慢", "明度", "色阶"]),
        "tool_choice": _contains(learning_text, ["彩铅", "油画棒", "水彩笔"]),
    }


def _capsule(section_id: str, kind: str, label: str, excerpt: str, graph_path: str = "", claim_id: str | None = None) -> dict[str, Any]:
    digest = hashlib.sha1(f"{section_id}|{kind}|{label}|{excerpt}|{graph_path}|{claim_id}".encode("utf-8")).hexdigest()[:10]
    return {
        "capsule_id": f"r114c_{section_id}_{kind}_{digest}",
        "label": label,
        "kind": kind,
        "graph_path": graph_path,
        "claim_id": claim_id,
        "source_excerpt": _truncate(excerpt, 260),
        "display_mode": "click_to_show_graph_basis",
        "click_action": "show_graph_source_basis",
    }


def _basis_from_claims(section_id: str, claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    basis = []
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        basis.append(
            {
                "claim_id": claim.get("claim_id"),
                "claim_type": claim.get("claim_type"),
                "graph_path": claim.get("graph_path"),
                "text": _truncate(claim.get("text"), 260),
                "source_evidence": [_truncate(item, 220) for item in (claim.get("source_evidence") or []) if _clean(item)],
                "confidence": claim.get("confidence"),
                "teacher_review_required": bool(claim.get("teacher_review_required")),
                "section_id": section_id,
            }
        )
    return basis


def _candidate(
    section_id: str,
    items: list[str],
    basis_claims: list[dict[str, Any]],
    *,
    classification: str = "r114c_graph_projected_candidate",
    projection_policy: str = "从 R114A 理解图和 R114B 教师执行地图投影；保留教师确认缺口。",
    pass_with_gaps: bool = False,
) -> dict[str, Any]:
    clean_items = [_clean(item) for item in items if _clean(item)]
    if not clean_items:
        clean_items = ["理解图未形成稳定字段候选，本项保留为教师确认。"]
        pass_with_gaps = True
    capsules = [
        _capsule(
            section_id,
            "graph_basis",
            "理解图依据",
            claim.get("text") or "",
            claim.get("graph_path") or "",
            claim.get("claim_id"),
        )
        for claim in basis_claims
        if isinstance(claim, dict)
    ]
    if pass_with_gaps:
        capsules.append(
            _capsule(
                section_id,
                "confirm",
                "需确认",
                "本字段仍有原稿缺口，进入正式备课前需教师判断。",
                "teacher_confirmation_gaps",
            )
        )
    return {
        "section_id": section_id,
        "title": SECTION_TITLES.get(section_id, section_id),
        "items": clean_items[:6],
        "classification": classification,
        "projection_policy": projection_policy,
        "projection_source": "R114A_understanding_graph + R114B_teacher_execution_map",
        "graph_basis": _basis_from_claims(section_id, basis_claims),
        "source_capsules": capsules,
        "teacher_review_required": True,
        "pass_with_gaps": bool(pass_with_gaps),
        "preview_only": True,
        "formal_apply": False,
    }


def _teacher_review_claims(graph: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in graph.get("teacher_confirmation_gaps") or [] if isinstance(item, dict)]


def _improvement_claims(graph: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in graph.get("improvement_opportunities") or [] if isinstance(item, dict)]


def _student_difficulties(graph: dict[str, Any], execution_map: dict[str, Any]) -> list[str]:
    items = []
    difficulty_model = graph.get("student_difficulty_model") or {}
    if isinstance(difficulty_model, dict):
        items.extend(_clean(item) for item in difficulty_model.get("items") or [] if _clean(item))
    for step in execution_map.get("classroom_flow") or []:
        stuck = _clean(step.get("likely_stuck_point")) if isinstance(step, dict) else ""
        if stuck:
            items.append(stuck)
    seen: set[str] = set()
    unique = []
    for item in items:
        if item not in seen:
            unique.append(item)
            seen.add(item)
    return unique[:4]


def _support_items(execution_map: dict[str, Any]) -> list[str]:
    items = []
    for step in execution_map.get("classroom_flow") or []:
        if not isinstance(step, dict):
            continue
        teacher_move = _clean(step.get("teacher_move"))
        xiaojiao_support = _clean(step.get("xiaojiao_support"))
        if teacher_move:
            items.append(teacher_move)
        if xiaojiao_support:
            items.append(xiaojiao_support)
    return items[:5]


def _flow_claims(graph: dict[str, Any], execution_map: dict[str, Any]) -> list[dict[str, Any]]:
    lookup = _claim_lookup(graph)
    claims: list[dict[str, Any]] = []
    for step in execution_map.get("classroom_flow") or []:
        if not isinstance(step, dict):
            continue
        basis = step.get("source_basis") or {}
        claim = lookup.get(str(basis.get("claim_id")))
        if claim:
            claims.append(claim)
    return claims


def _build_field_candidates(graph: dict[str, Any], execution_map: dict[str, Any]) -> dict[str, Any]:
    lookup = _claim_lookup(graph)
    flags = _feature_flags(graph)
    summary = _source_summary(graph)
    review_claims = _teacher_review_claims(graph)
    improvements = _improvement_claims(graph)
    core = _core_transform(graph)
    core_claim = lookup.get(str(core.get("claim_id"))) or core
    title = _lesson_title(graph)
    unit = _unit_title(graph)
    grade = _grade(graph)

    title_claim = _identity_claim(graph, "title")
    unit_claim = _identity_claim(graph, "unit")
    grade_claim = _identity_claim(graph, "grade")
    protected_claims = [
        lookup.get(str(claim_id))
        for claim_id in ((graph.get("faithful_reconstruction") or {}).get("protected_core_claim_ids") or [])
    ]
    protected_claims = [claim for claim in protected_claims if isinstance(claim, dict)]
    flow_claims = _flow_claims(graph, execution_map)

    basis_items = [
        f"本课依据上传原稿定位为{grade}《{title}》，所属单元为“{unit}”。",
    ]
    if _clean(core.get("text")):
        basis_items.append(_clean(core.get("text")))
    basis_items.append("教材版本、册次、页码和学校实际进度仍需教师确认后再进入正式备课。")
    basis_claims = [title_claim, unit_claim, grade_claim, core_claim] + review_claims[:1]

    difficulties = _student_difficulties(graph, execution_map)
    analysis_items = []
    if difficulties:
        analysis_items.append(f"{grade}学生进入本课时，可能先卡在这里：{difficulties[0]}")
    if len(difficulties) > 1:
        focus_text = "；".join(_clean(item).rstrip("。；;") for item in difficulties[1:3] if _clean(item))
        analysis_items.append("课堂上可重点看：" + focus_text + "。")
    if not analysis_items:
        analysis_items = ["学生学习基础和现场困难仍需教师结合本班情况确认。"]
    analysis_claims = [core_claim] + flow_claims[:3] + review_claims[:1]

    goal_items: list[str] = []
    if flags.get("shoe_observation"):
        goal_items.append("学生能从正面、侧面、后面或局部角度观察鞋，说出外形比例、鞋面结构、鞋底方向或鞋带纹样等2-3个发现。")
        goal_items.append("学生能用线条和形状画出鞋的基本轮廓、主要结构和至少一处局部细节，画面依据来自实际观察。")
    elif flags["gradient"]:
        goal_items.append("学生能观察生活和画面中的颜色过渡现象，说出渐变是颜色逐步变化的效果。")
        if flags["tool_choice"]:
            goal_items.append("学生能选择彩铅、油画棒或水彩笔中的一种方法，画出一组有过渡层次的渐变效果。")
        else:
            goal_items.append("学生能选择合适工具尝试表现一组有过渡层次的渐变效果。")
    elif flags["prior_design"] and flags["reused_materials"]:
        goal_items.append("学生能依据前序设计想法，选择合适材料推进作品制作，并说明材料选择与设计意图的关系。")
    elif flags["reused_materials"]:
        goal_items.append("学生能围绕任务目标选择材料和方法，完成有明确意图的美术表达。")
    else:
        goal_items.append("学生能围绕本课任务完成一次有目标的观察、尝试或表达。")
    if flags.get("shoe_observation"):
        goal_items.append("学生能在交流中指出作品中的一个观察证据，并根据同伴或教师提示完成一处调整。")
    elif flags["gradient"]:
        goal_items.append("学生能在交流中指出作品哪里体现了渐变，并说明还可以怎样调整。")
    elif flags["design_story"]:
        goal_items.append("学生能用简短语言说明作品对象、解决的问题、材料方法、满意处和可改进处。")
    else:
        goal_items.append("学生能说出自己的学习发现、方法选择或作品特点。")
    if flags.get("shoe_observation"):
        pass
    elif flags["gradient"]:
        pass
    elif flags["launch"]:
        goal_items.append("学生能整理作品和表达证据，为后续展示或交流做好准备。")
    else:
        goal_items.append("学生能在交流中用课堂证据说明自己的学习成果。")
    goal_claims = protected_claims[:4] + [core_claim]

    keypoint_items = []
    if flags.get("shoe_observation"):
        keypoint_items.append("重点：引导学生从真实鞋或图片中观察不同角度的外形、结构和局部细节，并把观察发现转化为线描表达。")
        keypoint_items.append("难点：帮助学生处理比例、遮挡、鞋面与鞋底方向、局部纹样等容易被忽略的细节，避免画成概念化、符号化的鞋。")
    elif flags["gradient"]:
        keypoint_items.append("重点：识别颜色逐步过渡的规律，并用工具把渐变效果表现出来。")
        keypoint_items.append("难点：避免直接跳色或平涂，引导学生通过叠色、推开或色阶排列形成自然过渡。")
    elif flags["prior_design"] and flags["reused_materials"]:
        keypoint_items.append("重点：把前序设计想法转化为材料选择、结构处理和可观察的作品变化。")
        keypoint_items.append("难点：避免学生只做装饰堆叠，引导其说明材料、功能或造型与设计意图之间的关系。")
    else:
        keypoint_items.append("重点：围绕本课任务形成清楚的观察、方法尝试和作品表达。")
        keypoint_items.append("难点：让学生说清方法选择和学习成果之间的关系。")
    if flags["design_story"]:
        keypoint_items.append("表达难点：把作品说明从“好看”推进到对象、问题、材料方法和改进依据。")
    keypoint_claims = [core_claim] + flow_claims[:4] + improvements[:2]

    student_prep = [_clean(item) for item in summary.get("student_preparation") or [] if _clean(item)]
    teacher_prep = [_clean(item) for item in summary.get("teacher_preparation") or [] if _clean(item)]
    prep_items = []
    if student_prep:
        prep_items.append(f"学生准备：{'；'.join(student_prep[:6])}。")
    if teacher_prep:
        prep_items.append(f"教师准备：{'；'.join(teacher_prep[:6])}。")
    if not prep_items:
        prep_items.append("材料、工具、大屏资源和安全安排需教师根据本班条件确认。")
    prep_claims = protected_claims + review_claims[:2]

    evidence_plan = [item for item in execution_map.get("evidence_collection_plan") or [] if isinstance(item, dict)]
    assessment_items = []
    for item in evidence_plan[:3]:
        evidence = _clean(item.get("evidence"))
        proves = _clean(item.get("proves"))
        if evidence and proves:
            assessment_items.append(f"观察证据：{evidence}，用于{proves}")
    if not assessment_items:
        assessment_items.append("评价需基于课堂可观察证据，具体证据形式由教师确认。")
    if flags["design_story"]:
        assessment_items.append("表达评价关注学生是否能说明对象、问题、材料方法、满意处和改进想法。")
    assessment_claims = [lookup.get(str(item.get("source_claim_id"))) for item in evidence_plan[:4]]
    assessment_claims = [claim for claim in assessment_claims if isinstance(claim, dict)] + [core_claim]

    reflection_items = ["课前导入预览阶段不生成课堂后记；真实授课后再根据课堂证据和教师判断形成反思候选。"]
    reflection_claims = review_claims[:1] + [core_claim]

    return {
        "basis": _candidate("basis", basis_items, basis_claims, classification="r114c_graph_basis_projection", pass_with_gaps=True),
        "analysis": _candidate("analysis", analysis_items, analysis_claims, classification="r114c_graph_analysis_projection", pass_with_gaps=bool(review_claims)),
        "goals": _candidate("goals", goal_items, goal_claims, classification="r114c_graph_goal_projection"),
        "keypoints": _candidate("keypoints", keypoint_items, keypoint_claims, classification="r114c_graph_keypoint_projection"),
        "preparation": _candidate("preparation", prep_items, prep_claims, classification="r114c_graph_preparation_projection", pass_with_gaps=not (student_prep or teacher_prep)),
        "assessment": _candidate("assessment", assessment_items, assessment_claims, classification="r114c_graph_assessment_projection"),
        "reflection": _candidate("reflection", reflection_items, reflection_claims, classification="r114c_before_class_reflection_gap", pass_with_gaps=True),
    }


def _build_process_projection(graph: dict[str, Any], execution_map: dict[str, Any]) -> dict[str, Any]:
    flow = []
    for step in execution_map.get("classroom_flow") or []:
        if not isinstance(step, dict):
            continue
        flow.append(
            {
                "step_id": step.get("step_id"),
                "title": step.get("title"),
                "teacher_move": step.get("teacher_move"),
                "student_action": step.get("student_action"),
                "evidence_to_watch": step.get("evidence_to_watch") or [],
                "likely_stuck_point": step.get("likely_stuck_point"),
                "xiaojiao_support": step.get("xiaojiao_support"),
                "source_claim_id": (step.get("source_basis") or {}).get("claim_id"),
                "source_claim_type": (step.get("source_basis") or {}).get("claim_type"),
                "teacher_review_required": bool(step.get("teacher_review_required")),
            }
        )
    return {
        "status": "projected_from_R114B",
        "process_step_count": len(flow),
        "items": flow,
        "preview_only": True,
        "formal_apply": False,
    }


def _resource_summary() -> dict[str, Any]:
    try:
        from . import prep_room_import_field_reasoning_bridge_1013R_R111 as r111

        summary = r111._resource_summary()
        return summary if isinstance(summary, dict) else {}
    except Exception as exc:
        return {"loaded": {}, "reason_code": "r111_resource_summary_unavailable", "safe_message": str(exc)[:300]}


def _build_agent_execution_steps(r114b_steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    steps = []
    for step in r114b_steps:
        if not isinstance(step, dict):
            continue
        item = dict(step)
        if item.get("step_id") == "STEP_5_FIELD_PROJECTION_REVIEW":
            item["status"] = "completed"
            item["stage_refs"] = ["R114C"]
            item["teacher_visible_text"] = "已从理解图和执行地图生成字段候选；正式采用前仍需教师确认。"
        steps.append(item)
    if not any(step.get("step_id") == "STEP_5_FIELD_PROJECTION_REVIEW" for step in steps):
        steps.append(
            {
                "step_id": "STEP_5_FIELD_PROJECTION_REVIEW",
                "label": "字段投影与教师确认",
                "status": "completed",
                "stage_refs": ["R114C"],
                "teacher_visible_text": "已从理解图和执行地图生成字段候选；正式采用前仍需教师确认。",
            }
        )
    return steps


def _contamination_report(graph: dict[str, Any], projection: dict[str, Any]) -> dict[str, Any]:
    blocked = (graph.get("contamination_guard") or {}).get("blocked_source_fact_phrases") or []
    text = _json_text(projection)
    violations = [
        {
            "phrase": phrase,
            "violation": "blocked_phrase_introduced_by_R114C_projection",
        }
        for phrase in blocked
        if phrase and phrase in text
    ]
    if (graph.get("contamination_guard") or {}).get("passed") is False:
        violations.append(
            {
                "phrase": "R114A_contamination_guard",
                "violation": "upstream_graph_contamination_failed",
            }
        )
    return {
        "guard_rules": [
            "R114C projects fields from R114A/R114B only and must not reread raw text.",
            "Blocked sample-specific phrases from R114A must not be introduced into projected fields.",
            "Projection creates candidates only; it must not formal apply or write storage.",
        ],
        "blocked_phrases_from_R114A": blocked,
        "violations": violations,
        "passed": not violations,
    }


def _build_deterministic_projection(graph: dict[str, Any], execution_preview: dict[str, Any]) -> dict[str, Any]:
    execution_map = execution_preview.get("teacher_execution_map") or {}
    field_candidates = _build_field_candidates(graph, execution_map)
    all_capsules = []
    for section_id in CORE_SECTION_ORDER:
        all_capsules.extend(field_candidates.get(section_id, {}).get("source_capsules") or [])
    resource_summary = _resource_summary()
    return {
        "projection_version": "graph_field_projection_r114c_v0.1",
        "field_candidates": field_candidates,
        "section_patch_order": CORE_SECTION_ORDER,
        "source_capsules": all_capsules,
        "process_projection": _build_process_projection(graph, execution_map),
        "teacher_review_queue": execution_map.get("teacher_review_queue") or [],
        "field_projection_basis": {
            "status": "projected_from_graph_in_R114C",
            "field_projection_performed": True,
            "projection_source": "R114A_understanding_graph + R114B_teacher_execution_map",
            "formal_apply_performed": False,
        },
        "old_chain_usage": {
            "official_unit_field_prompt_standard_readonly_used": bool((resource_summary.get("loaded") or {}).get("official_unit_field_prompt_standard_v1")),
            "R82_readonly_used": bool((resource_summary.get("loaded") or {}).get("R82_prompt_contract")),
            "R88_readonly_used": bool((resource_summary.get("loaded") or {}).get("R88_field_lab_ledger")),
            "R90A_readonly_used": bool((resource_summary.get("loaded") or {}).get("R90A_profile_manifest")),
            "old_generation_chain_modified": False,
            "R21_modified": False,
            "R36_modified": False,
            "R82_modified": False,
            "R88_modified": False,
            "R89_modified": False,
            "R90A_modified": False,
            "R90B_modified": False,
        },
        "resource_summary": resource_summary,
        "projection_quality": {
            "status": "PASS_WITH_GAPS",
            "field_count": len(field_candidates),
            "teacher_review_required": True,
            "reason": "字段候选来自理解图和执行地图，但教材页码、真实班情和正式采用仍需教师确认。",
        },
    }


def _extract_json(value: str) -> dict[str, Any] | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        fence = re.match(r"^```[A-Za-z0-9_-]*\s*(.*?)\s*```$", text, flags=re.S)
        text = fence.group(1).strip() if fence else re.sub(r"^```[A-Za-z0-9_-]*\s*", "", text, flags=re.I)
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for index, char in enumerate(text):
            if char != "{":
                continue
            try:
                parsed, _ = decoder.raw_decode(text[index:])
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                continue
    return None


def _provider_public_status() -> dict[str, Any]:
    try:
        from . import providers

        status = providers.provider_status()
        generation = status.get("generation") or {}
        return {
            "credential_available": bool(status.get("credential_available") or generation.get("credential_available")),
            "provider": generation.get("provider") or status.get("provider_name") or "openai_compatible",
            "model": generation.get("model") or "MiniMax-M3",
            "credential_source": generation.get("credential_source") or status.get("credential_source"),
            "base_url": generation.get("base_url"),
        }
    except Exception as exc:
        return {
            "credential_available": False,
            "provider": "unknown",
            "model": "",
            "reason_code": "provider_status_failed",
            "safe_message": str(exc)[:300],
        }


def _call_model(
    graph: dict[str, Any],
    execution_preview: dict[str, Any],
    deterministic_projection: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    started = time.perf_counter()
    log: dict[str, Any] = {
        "provider_called": False,
        "model_called": False,
        "status": "not_started",
        "latency_ms": 0,
    }
    provider_status = _provider_public_status()
    log["provider_status"] = provider_status
    if not provider_status.get("credential_available"):
        log.update({"status": "fallback", "reason_code": "provider_credentials_missing"})
        return None, log
    system_prompt = (
        "你是小学美术大单元备课字段投影助手，只输出 JSON。"
        "你只能使用 R114A 理解图和 R114B 教师执行地图，不允许回读或虚构原文。"
        "本轮允许生成字段候选，但不允许 formal apply，不允许写库。"
        "尊重原稿核心任务；已有证据做匹配，缺口标注教师确认。"
    )
    payload = {
        "task": "project_fields_from_understanding_graph_and_teacher_execution_map",
        "boundary": {
            "preview_only": True,
            "raw_text_available": False,
            "field_projection_performed": True,
            "formal_apply": False,
            "database_written": False,
        },
        "understanding_graph": graph,
        "teacher_execution_map_preview": execution_preview,
        "deterministic_projection": deterministic_projection,
        "required_output": {
            "field_candidates": {section_id: {"items": ["string"], "projection_policy": "string"} for section_id in CORE_SECTION_ORDER},
            "projection_quality": "object",
        },
    }
    try:
        from . import providers

        log["provider_called"] = True
        log["model_called"] = True
        result = providers.generate_json_patch(
            {"stage": STAGE_ID, "mode": "graph_field_projection_preview", "sandbox_only": True},
            {"system_prompt": system_prompt, "user_prompt": json.dumps(payload, ensure_ascii=False)},
            {
                "provider": provider_status.get("provider") or "openai_compatible",
                "model": provider_status.get("model") or "MiniMax-M3",
                "response_format": "json_object",
                "temperature": 0.1,
                "max_tokens": 3600,
                "timeout_ms": 120000,
            },
        )
        raw = str(result.get("raw_text") or "")
        provider_meta = dict(result.get("provider_meta") or {})
        parsed = _extract_json(raw)
        log.update(
            {
                "status": "success" if parsed else "fallback",
                "reason_code": None if parsed else "provider_response_not_json",
                "latency_ms": round((time.perf_counter() - started) * 1000),
                "provider_meta": {
                    key: value
                    for key, value in provider_meta.items()
                    if key not in {"token", "api_key", "authorization"}
                },
            }
        )
        return parsed, log
    except Exception as exc:
        log.update(
            {
                "status": "fallback",
                "reason_code": str(getattr(exc, "code", "") or "provider_call_failed"),
                "safe_message": str(exc)[:800],
                "latency_ms": round((time.perf_counter() - started) * 1000),
            }
        )
        return None, log


def _merge_model_projection(
    graph: dict[str, Any],
    deterministic_projection: dict[str, Any],
    model_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(model_payload, dict):
        return deterministic_projection
    raw_candidates = model_payload.get("field_candidates")
    if not isinstance(raw_candidates, dict):
        return deterministic_projection
    merged = json.loads(json.dumps(deterministic_projection, ensure_ascii=False))
    for section_id in CORE_SECTION_ORDER:
        candidate = raw_candidates.get(section_id)
        if not isinstance(candidate, dict):
            continue
        items = candidate.get("items")
        if isinstance(items, list):
            clean_items = [_clean(item) for item in items if _clean(item)]
            if clean_items:
                merged["field_candidates"][section_id]["items"] = clean_items[:6]
                merged["field_candidates"][section_id]["classification"] = "r114c_model_refined_graph_projection"
        if _clean(candidate.get("projection_policy")):
            merged["field_candidates"][section_id]["projection_policy"] = _clean(candidate.get("projection_policy"))
    contamination = _contamination_report(graph, merged)
    if not contamination.get("passed"):
        deterministic_projection.setdefault("model_rejected", []).append(
            {
                "reason": "model_field_projection_contamination_guard_failed",
                "violations": contamination.get("violations"),
            }
        )
        return deterministic_projection
    return merged


def build_graph_field_projection_preview(
    understanding_v2_graph_preview: dict[str, Any],
    teacher_execution_map_preview: dict[str, Any],
    enable_model: bool = False,
) -> dict[str, Any]:
    graph = understanding_v2_graph_preview.get("graph") if isinstance(understanding_v2_graph_preview, dict) else None
    graph = graph if isinstance(graph, dict) else {}
    deterministic_projection = _build_deterministic_projection(graph, teacher_execution_map_preview if isinstance(teacher_execution_map_preview, dict) else {})
    model_payload: dict[str, Any] | None = None
    model_log: dict[str, Any] = {
        "provider_called": False,
        "model_called": False,
        "status": "disabled",
        "reason_code": "R114C_model_not_enabled",
    }
    if enable_model:
        model_payload, model_log = _call_model(graph, teacher_execution_map_preview, deterministic_projection)
    projection = _merge_model_projection(graph, deterministic_projection, model_payload)
    contamination = _contamination_report(graph, projection)
    status = "model_success" if model_payload and projection is not deterministic_projection else ("model_fallback" if enable_model else "deterministic_ready")
    if not contamination.get("passed"):
        status = "contamination_guard_failed"
    return {
        "stage": STAGE_ID,
        "status": status,
        "model_quality_enabled": bool(enable_model),
        "provider_called": bool(model_log.get("provider_called")),
        "model_called": bool(model_log.get("model_called")),
        "model_log": model_log,
        "input_contract": {
            "source": "R114A understanding graph + R114B teacher execution map only",
            "raw_text_used": False,
            "reread_original_document": False,
            "upstream_graph_stage": understanding_v2_graph_preview.get("stage") if isinstance(understanding_v2_graph_preview, dict) else None,
            "upstream_graph_status": understanding_v2_graph_preview.get("status") if isinstance(understanding_v2_graph_preview, dict) else None,
            "upstream_execution_stage": teacher_execution_map_preview.get("stage") if isinstance(teacher_execution_map_preview, dict) else None,
            "upstream_execution_status": teacher_execution_map_preview.get("status") if isinstance(teacher_execution_map_preview, dict) else None,
        },
        "field_projection": projection,
        "field_candidates": projection.get("field_candidates") or {},
        "section_patch_order": projection.get("section_patch_order") or CORE_SECTION_ORDER,
        "source_capsules": projection.get("source_capsules") or [],
        "process_projection": projection.get("process_projection") or {},
        "agent_execution_steps": _build_agent_execution_steps(
            teacher_execution_map_preview.get("agent_execution_steps") if isinstance(teacher_execution_map_preview, dict) else []
        ),
        "contamination_guard": contamination,
        "boundary": {
            "preview_only": True,
            "write_allowed": False,
            "database_written": False,
            "memory_written": False,
            "feishu_written": False,
            "formal_apply": False,
            "formal_apply_performed": False,
            "teacher_original_overwritten": False,
            "old_generation_chain_modified": False,
            "field_projection_performed": True,
            "field_projection_applied_to_current_lesson": False,
            "target_shell": "R97B validation carrier only",
        },
    }
