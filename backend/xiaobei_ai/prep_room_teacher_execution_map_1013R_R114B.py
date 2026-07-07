from __future__ import annotations

import json
import re
import time
from typing import Any


STAGE_ID = "1013R_R114B_TEACHER_EXECUTION_MAP"


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _truncate(value: Any, limit: int = 320) -> str:
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


def _claim_text(claim: dict[str, Any] | None) -> str:
    return _clean((claim or {}).get("text"))


def _lesson_title(graph: dict[str, Any]) -> str:
    identity = graph.get("lesson_identity") or {}
    title = identity.get("title") or {}
    return _clean(title.get("text")).removeprefix("课题：") or "上传教案"


def _source_basis(node: dict[str, Any], lookup: dict[str, dict[str, Any]]) -> dict[str, Any]:
    claim = lookup.get(str(node.get("claim_id")))
    return {
        "claim_id": node.get("claim_id"),
        "claim_type": node.get("claim_type") or (claim or {}).get("claim_type"),
        "claim_text": _claim_text(claim) or _clean(node.get("why_now")),
        "source_evidence": [
            _truncate(item, 220)
            for item in (node.get("source_evidence") or (claim or {}).get("source_evidence") or [])
            if _clean(item)
        ],
        "confidence": (claim or {}).get("confidence"),
        "teacher_review_required": bool((claim or {}).get("teacher_review_required")),
    }


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
        "tool_safety": _contains(confirmation_text, ["剪刀", "胶水", "热熔胶", "工具安全"]),
        "gradient": (not shoe_observation) and _contains(learning_text, ["渐变", "颜色过渡", "颜色慢慢", "明度", "色阶"]),
        "tool_choice": _contains(learning_text, ["彩铅", "油画棒", "水彩笔"]),
    }


def _evidence_for_node(node: dict[str, Any], graph: dict[str, Any]) -> list[dict[str, Any]]:
    title = _clean(node.get("title"))
    evidence_graph = [item for item in graph.get("evidence_graph") or [] if isinstance(item, dict)]
    if not evidence_graph:
        return []
    flags = _feature_flags(graph)
    if any(token in title for token in ["制作", "动手", "改造", "尝试", "探索", "练习", "写生", "画"]):
        tokens = ["制作", "成品", "材料", "过程", "痕迹"]
        if flags.get("shoe_observation"):
            tokens = ["鞋", "角度", "结构", "局部", "轮廓", "线条", "作品", "细节"]
        elif _contains(graph, ["渐变", "颜色过渡", "色阶"]):
            tokens = ["渐变", "颜色", "过渡", "练习", "作品", "效果"]
    elif any(token in title for token in ["故事", "表达", "说明"]):
        tokens = ["故事", "口头", "表达", "5句话", "五句话"]
    elif any(token in title for token in ["发布", "展示", "小结", "交流", "预告"]):
        tokens = ["发布", "展示", "陈述", "成品"]
    elif any(token in title for token in ["导入", "回顾", "观察"]):
        tokens = ["设计", "观察", "过程", "任务"]
    else:
        tokens = []
    matched = []
    for item in evidence_graph:
        text = _json_text(item)
        if text.startswith('"| 节点 |') or "| 节点 |" in text:
            continue
        if not tokens or any(token in text for token in tokens):
            matched.append(
                {
                    "evidence_id": item.get("evidence_id"),
                    "evidence": _truncate(item.get("evidence"), 220),
                    "proves": _truncate(item.get("supports"), 220),
                    "source_claim_id": item.get("claim_id"),
                    "source_claim_type": item.get("claim_type"),
                }
            )
    return matched[:3]


def _teacher_move(title: str, flags: dict[str, bool]) -> str:
    if flags.get("shoe_observation") and any(token in title for token in ["导入", "引入", "回顾"]):
        return "出示真实鞋或多角度鞋图，请学生先说看得见的外形、角度和局部差异，把问题收束到“怎样把观察到的鞋画出来”。"
    if flags.get("shoe_observation") and any(token in title for token in ["观察", "指导", "发现", "欣赏"]):
        return "带学生固定观察角度，依次找鞋头、鞋跟、鞋底方向、鞋面结构和鞋带纹样，要求每个发现都能指到具体位置。"
    if flags.get("shoe_observation") and any(token in title for token in ["写生", "动手", "画", "创作", "练习"]):
        return "巡视时先看大轮廓和比例，再看鞋面、鞋底、鞋带等细节是否来自观察；只给一处可修改的线条提示。"
    if flags.get("shoe_observation") and any(token in title for token in ["展示", "交流", "小结", "分享", "展评", "评价"]):
        return "请学生指着作品说明自己抓住了哪个观察角度或细节，再用同伴建议完成一处修订。"
    if flags["prior_design"] and any(token in title for token in ["回顾", "展示", "导入"]):
        return "请学生先对照自己的设计依据，说清今天要实现的一个关键改造点；教师保护原设计意图，不替学生重新设计。"
    if flags["gradient"] and any(token in title for token in ["导入", "引入"]):
        return "先用彩虹、天空或生活图片追问“颜色是一下子变过去，还是慢慢过渡”，把学生经验收束到本课关键词。"
    if flags["gradient"] and any(token in title for token in ["认识", "观察", "发现", "概念"]):
        return "带学生比较几张图中的颜色变化，让他们用自己的话说出“渐变”的规律，再给出教师板书。"
    if any(token in title for token in ["示范", "方法"]):
        if flags["gradient"] and flags["tool_choice"]:
            return "用短示范分别呈现彩铅叠色、油画棒推开和水彩笔色阶排列，让学生知道自己选的工具要怎么做出过渡。"
        if flags["reused_materials"]:
            return "用短示范拆出可选制作路径、材料连接方式和工具安全边界，强调材料选择要服务设计意图。"
        return "用短示范拆出关键方法、工具安全和可选择路径，避免学生只模仿范作。"
    if any(token in title for token in ["制作", "动手", "尝试", "创作", "探索", "练习"]):
        if flags["gradient"]:
            return "巡视时先看颜色是否逐步变化，再看学生是否按自己选择的工具方法推进；需要时只补一个最小动作提示。"
        if flags["prior_design"] and flags["reused_materials"]:
            return "巡视时优先看三件事：是否对照设计依据、材料是否服务造型或功能、困难学生是否需要模板或同伴支持。"
        return "巡视学生是否按任务目标推进，优先追问选择理由，再给技术帮助。"
    if flags["design_story"] and any(token in title for token in ["故事", "表达", "说明"]):
        return "把表达任务变成证据结构：对象、问题、材料方法、满意处和可改进处，让学生用作品说明设计理由。"
    if flags["launch"] and any(token in title for token in ["小结", "预告", "发布", "展示"]):
        return "收集作品或过程证据，说明后续展示还要准备什么，并把未定安排交给教师确认。"
    if flags["gradient"] and any(token in title for token in ["分享", "展评", "展示", "交流", "小结"]):
        return "把几份学生作品放在一起比较，请学生指出哪里过渡自然、哪里跳得太快，并把评价回收到渐变效果。"
    if any(token in title for token in ["展示", "交流", "小结", "分享", "展评"]):
        return "把学生作品或语言表达转成可观察证据，提醒哪些内容需要课后确认。"
    return "先把原稿任务说成学生听得懂的一句话，再追问他们看到了什么、准备怎样做；需要时只补一个方法提示。"


def _student_action(title: str, flags: dict[str, bool]) -> str:
    if flags.get("shoe_observation") and any(token in title for token in ["导入", "引入", "回顾"]):
        return "观察真实鞋或图片，说出一个外形、角度或局部细节上的发现。"
    if flags.get("shoe_observation") and any(token in title for token in ["观察", "指导", "发现", "欣赏"]):
        return "确定自己的观察角度，指出鞋头、鞋跟、鞋底、鞋面或鞋带等2个结构位置。"
    if flags.get("shoe_observation") and any(token in title for token in ["写生", "动手", "画", "创作", "练习"]):
        return "先画大轮廓和比例，再补一个来自观察的局部细节，并根据对象调整线条。"
    if flags.get("shoe_observation") and any(token in title for token in ["展示", "交流", "小结", "预告", "分享", "展评"]):
        return "展示作品，说明哪一处线条、比例或细节来自自己的观察。"
    if flags["prior_design"] and any(token in title for token in ["回顾", "展示", "导入"]):
        return "拿出或回忆自己的设计依据，说出今天最想实现的一处变化。"
    if flags["gradient"] and any(token in title for token in ["导入", "引入"]):
        return "回忆见过的颜色变化，说出彩虹或图片中颜色是怎样慢慢变过去的。"
    if flags["gradient"] and any(token in title for token in ["认识", "观察", "发现", "概念"]):
        return "观察图片里的颜色变化，用“慢慢过渡、由深到浅、由一种颜色到另一种颜色”等语言描述。"
    if any(token in title for token in ["示范", "方法"]):
        if flags["gradient"] and flags["tool_choice"]:
            return "观察三种工具的表现差异，判断自己带来的工具适合用叠色、推开还是色阶排列。"
        return "观察方法选择和工具使用要求，判断哪一种路径适合自己的任务。"
    if any(token in title for token in ["制作", "动手", "尝试", "创作", "探索", "练习"]):
        if flags["gradient"]:
            return "在学习单或作品中尝试画出一组颜色过渡，并边做边检查是否有明显断层。"
        return "边做边检查作品是否回应原任务，遇到困难先说明卡在哪里。"
    if flags["design_story"] and any(token in title for token in ["故事", "表达", "说明"]):
        return "用简短语言说明作品对象、解决的问题、材料方法、满意处和改进想法。"
    if any(token in title for token in ["展示", "交流", "小结", "预告", "分享", "展评"]):
        return "展示当前成果或学习发现，确认还需要补充的证据。"
    return "先说自己的发现或选择，再完成相应的观察、练习或作品片段。"


def _stuck_point(title: str, flags: dict[str, bool]) -> str:
    if flags.get("shoe_observation") and any(token in title for token in ["导入", "引入", "认识", "观察", "发现", "概念", "指导"]):
        return "学生可能只说鞋好看或颜色特别，却没有指向角度、结构和局部细节。"
    if flags.get("shoe_observation") and any(token in title for token in ["写生", "动手", "制作", "尝试", "创作", "探索", "练习", "画"]):
        return "学生可能凭印象画符号化的鞋，比例、鞋底方向或鞋带细节与观察对象脱节。"
    if flags.get("shoe_observation") and any(token in title for token in ["展示", "交流", "小结", "预告"]):
        return "学生可能只能说像不像或好不好看，不能说明作品中的观察证据。"
    if flags["prior_design"] and any(token in title for token in ["回顾", "展示", "导入"]):
        return "学生可能忘带或说不清设计依据，后续制作容易变成随意装饰。"
    if flags["gradient"] and any(token in title for token in ["导入", "引入", "认识", "观察", "发现", "概念"]):
        return "学生可能只说颜色好看，却说不出颜色是怎样慢慢过渡的。"
    if any(token in title for token in ["示范", "方法"]):
        if flags["gradient"] and flags["tool_choice"]:
            return "学生可能混淆三种工具的方法，把水彩笔当成可混色工具，或不知道怎样控制深浅。"
        return "学生可能把示范当成唯一答案，或忽略工具安全和材料连接限制。"
    if any(token in title for token in ["制作", "动手", "尝试", "创作", "探索", "练习"]):
        if flags["gradient"]:
            return "学生可能出现颜色断层、直接换色或只平涂，作品看不出逐步变化。"
        return "学生可能忙于装饰堆叠，却说不清材料选择和任务目标的关系。"
    if flags["design_story"] and any(token in title for token in ["故事", "表达", "说明"]):
        return "学生可能只说好看，不说明对象、问题、材料方法和改进依据。"
    if any(token in title for token in ["展示", "交流", "小结", "预告"]):
        return "展示证据、后续时间或家长协助安排可能还需要教师确认。"
    return "学生可能说得出想法却不知道从哪一步开始，或作品完成后说不清为什么这样处理。"


def _xiaojiao_support(title: str, flags: dict[str, bool]) -> str:
    if flags.get("shoe_observation") and any(token in title for token in ["导入", "引入", "认识", "观察", "发现", "概念", "指导"]):
        return "小教可提醒教师追问：你看到的是鞋的哪个角度？鞋面、鞋底或鞋带有什么具体变化？"
    if flags.get("shoe_observation") and any(token in title for token in ["写生", "动手", "制作", "尝试", "创作", "探索", "练习", "画"]):
        return "小教可给出巡视提示：先看大轮廓，再问这条线对应鞋的哪一部分。"
    if flags.get("shoe_observation") and any(token in title for token in ["展示", "交流", "小结", "预告", "分享", "展评"]):
        return "小教可把评价拉回证据：请学生指出作品里一处来自观察的角度、结构或细节。"
    if flags["prior_design"] and any(token in title for token in ["回顾", "展示", "导入"]):
        return "小教提示教师追问：你今天最想把草图里的哪一点做出来？"
    if flags["gradient"] and any(token in title for token in ["导入", "引入", "认识", "观察", "发现", "概念"]):
        return "小教可提醒教师追问：你看到颜色是突然跳过去，还是一层一层慢慢变过去？"
    if any(token in title for token in ["示范", "方法"]):
        if flags["gradient"] and flags["tool_choice"]:
            return "小教可生成三种工具的口头提示：彩铅轻叠、油画棒推开、水彩笔排色阶。"
        return "小教可生成方法选择清单和工具安全提醒，帮助教师快速口头提示。"
    if any(token in title for token in ["制作", "动手", "尝试", "创作", "探索", "练习"]):
        if flags["gradient"]:
            return "小教可按巡视发现给出一句话支架：从深到浅多加一格中间色，或把边界轻轻叠过去。"
        return "小教可按巡视发现给出分层追问：材料为什么这样选？哪里需要同伴或模板支持？"
    if flags["design_story"] and any(token in title for token in ["故事", "表达", "说明"]):
        return "小教可把表达任务变成句式支架，但不替学生编设计理由。"
    if flags["gradient"] and any(token in title for token in ["分享", "展评", "展示", "交流", "小结", "预告"]):
        return "小教可提醒教师把评价句收回到证据：哪里渐变自然，哪里颜色跳得太快。"
    if any(token in title for token in ["展示", "交流", "小结", "预告", "分享", "展评"]):
        return "小教可生成教师确认清单：作品证据、表达证据、后续展示安排。"
    return "小教可给教师一条追问：你这样选材料、颜色或方法，是想表现什么？"


def _build_classroom_flow(graph: dict[str, Any]) -> list[dict[str, Any]]:
    lookup = _claim_lookup(graph)
    flags = _feature_flags(graph)
    nodes = [item for item in graph.get("teaching_causal_chain") or [] if isinstance(item, dict)]
    if not nodes:
        core = graph.get("core_learning_transformation") or {}
        core = core if isinstance(core, dict) else {}
        nodes = [
            {
                "episode_index": 1,
                "source_episode_id": None,
                "title": "学习任务确认",
                "why_now": _clean(core.get("text"))
                or "R114A 未形成稳定环节链，本轮只生成教师确认型执行入口。",
                "source_evidence": core.get("source_evidence") or [],
                "claim_id": core.get("claim_id"),
                "claim_type": core.get("claim_type") or "teacher_confirm_required",
            }
        ]
    flow: list[dict[str, Any]] = []
    for index, node in enumerate(nodes, start=1):
        title = _clean(node.get("title")) or f"环节{index}"
        source_basis = _source_basis(node, lookup)
        evidence = _evidence_for_node(node, graph)
        review_required = bool(source_basis.get("teacher_review_required")) or source_basis.get("claim_type") == "teacher_confirm_required"
        flow.append(
            {
                "step_id": f"TEACHER_EXEC_{index:02d}",
                "episode_index": node.get("episode_index") or index,
                "source_episode_id": node.get("source_episode_id"),
                "title": title,
                "why_now": _clean(node.get("why_now")),
                "teacher_move": _teacher_move(title, flags),
                "student_action": _student_action(title, flags),
                "evidence_to_watch": evidence,
                "likely_stuck_point": _stuck_point(title, flags),
                "xiaojiao_support": _xiaojiao_support(title, flags),
                "source_basis": source_basis,
                "teacher_review_required": review_required,
            }
        )
    return flow


def _build_evidence_collection_plan(graph: dict[str, Any], flow: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence_graph = [item for item in graph.get("evidence_graph") or [] if isinstance(item, dict)]
    plan: list[dict[str, Any]] = []
    for item in evidence_graph:
        evidence = _clean(item.get("evidence"))
        if not evidence or "| 节点 |" in evidence:
            continue
        matched_step = None
        for step in flow:
            step_evidence = _json_text(step.get("evidence_to_watch") or [])
            if evidence and evidence in step_evidence:
                matched_step = step.get("step_id")
                break
        plan.append(
            {
                "evidence_id": item.get("evidence_id"),
                "evidence": _truncate(evidence, 220),
                "proves": _truncate(item.get("supports"), 220),
                "source_claim_id": item.get("claim_id"),
                "source_claim_type": item.get("claim_type"),
                "suggested_moment": matched_step or "teacher_confirm_required",
                "teacher_action": "课堂中只采集必要证据，不因为导入预览结果直接写入正式系统。",
            }
        )
    if plan:
        return plan[:10]
    for step in flow:
        plan.append(
            {
                "evidence_id": f"derived_from_{step['step_id']}",
                "evidence": step.get("title"),
                "proves": step.get("why_now") or "证明该环节确实推进了学习变化。",
                "source_claim_id": (step.get("source_basis") or {}).get("claim_id"),
                "source_claim_type": (step.get("source_basis") or {}).get("claim_type"),
                "suggested_moment": step.get("step_id"),
                "teacher_action": "证据形式需教师根据课堂实际确认。",
            }
        )
    return plan


def _teacher_review_queue(graph: dict[str, Any], flow: list[dict[str, Any]]) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    for item in graph.get("teacher_confirmation_gaps") or []:
        if not isinstance(item, dict):
            continue
        queue.append(
            {
                "review_id": item.get("claim_id"),
                "source": "R114A.teacher_confirmation_gaps",
                "text": _clean(item.get("text")),
                "source_evidence": item.get("source_evidence") or [],
                "required_before": "formal_lesson_apply",
            }
        )
    for step in flow:
        if not step.get("teacher_review_required"):
            continue
        basis = step.get("source_basis") or {}
        queue.append(
            {
                "review_id": basis.get("claim_id") or step.get("step_id"),
                "source": "R114B.classroom_flow",
                "text": f"{step.get('title')} 的现场推进依据需要教师确认。",
                "source_evidence": basis.get("source_evidence") or [],
                "required_before": "classroom_execution",
            }
        )
    return queue


def _build_agent_execution_steps(graph: dict[str, Any], execution_ready: bool) -> list[dict[str, Any]]:
    guard = graph.get("contamination_guard") or {}
    faithful_done = bool(graph.get("faithful_reconstruction")) and bool(guard.get("passed", True))
    evidence_done = bool(graph.get("teaching_causal_chain")) and bool(graph.get("evidence_graph"))
    return [
        {
            "step_id": "STEP_1_SOURCE_BOUNDARY",
            "label": "原文接收与边界检查",
            "status": "completed",
            "stage_refs": ["R107A", "R103"],
            "teacher_visible_text": "已完成上传文本读取和只读边界确认。",
        },
        {
            "step_id": "STEP_2_FAITHFUL_UNDERSTANDING",
            "label": "忠实理解原教案",
            "status": "completed" if faithful_done else "needs_attention",
            "stage_refs": ["R112", "R114A"],
            "teacher_visible_text": "正在区分原文事实、结构理解和需要教师确认的内容。",
        },
        {
            "step_id": "STEP_3_PEDAGOGICAL_JUDGEMENT",
            "label": "教学判断与证据链",
            "status": "completed" if evidence_done else "needs_attention",
            "stage_refs": ["R114A"],
            "teacher_visible_text": "正在把教学因果链和课堂证据对应起来。",
        },
        {
            "step_id": "STEP_4_EXECUTION_MAP",
            "label": "教师执行地图",
            "status": "completed" if execution_ready else "pending",
            "stage_refs": ["R114B"],
            "teacher_visible_text": "已生成教师推进、学生行动、卡点和小教支持建议。",
        },
        {
            "step_id": "STEP_5_FIELD_PROJECTION_REVIEW",
            "label": "字段投影与教师确认",
            "status": "pending",
            "stage_refs": ["R114C"],
            "teacher_visible_text": "下一步才会把理解图投影到备课字段，不会直接覆盖原稿。",
        },
    ]


def _build_deterministic_preview(graph: dict[str, Any]) -> dict[str, Any]:
    flow = _build_classroom_flow(graph)
    core = graph.get("core_learning_transformation") or {}
    flow_ready = bool(flow)
    teacher_execution_map = {
        "map_version": "teacher_execution_map_r114b_v0.1",
        "source_graph_stage": "1013R_R114A_IMPORT_UNDERSTANDING_V2_GRAPH",
        "lesson_title": _lesson_title(graph),
        "core_learning_transformation": _clean(core.get("text")) if isinstance(core, dict) else _clean(core),
        "execution_principles": [
            "先保护原教案的核心任务，再补执行支架。",
            "原文事实、系统推断和改进建议分开呈现。",
            "教师确认缺口不能被自动写成已确认字段。",
        ],
        "classroom_flow": flow,
        "evidence_collection_plan": _build_evidence_collection_plan(graph, flow),
        "teacher_review_queue": _teacher_review_queue(graph, flow),
        "xiaojiao_runtime_support_policy": {
            "runtime_call_allowed": False,
            "preview_only": True,
            "role": "只给教师提示、检查和支架，不替教师做正式确认。",
        },
        "field_projection_basis": {
            "status": "not_projected_in_R114B",
            "field_projection_performed": False,
            "projection_stage": "R114C",
        },
    }
    return {
        "stage": STAGE_ID,
        "status": "deterministic_ready" if flow_ready else "needs_graph_review",
        "teacher_execution_map": teacher_execution_map,
        "agent_execution_steps": _build_agent_execution_steps(graph, flow_ready),
    }


def _contamination_report(graph: dict[str, Any], teacher_execution_map: dict[str, Any]) -> dict[str, Any]:
    blocked = (graph.get("contamination_guard") or {}).get("blocked_source_fact_phrases") or []
    text = _json_text(teacher_execution_map)
    violations = [
        {
            "phrase": phrase,
            "violation": "blocked_phrase_introduced_by_R114B",
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
            "R114B must use R114A graph only and must not reread raw text.",
            "Blocked sample-specific phrases from R114A must not be introduced into the execution map.",
            "Field projection remains disabled until R114C.",
        ],
        "blocked_phrases_from_R114A": blocked,
        "violations": violations,
        "passed": not violations,
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


def _call_model(graph: dict[str, Any], deterministic_preview: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
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
        "你是小学美术备课导入的教师执行地图助手，只输出 JSON。"
        "你只能使用给定的 R114A understanding graph，不允许重新推测原文没有的事实。"
        "你的任务不是字段投影，也不是正式改写教案，而是把教学因果链转换为教师可执行地图。"
        "必须区分原文事实、教学推断、改进建议和教师确认事项。"
    )
    payload = {
        "task": "build_teacher_execution_map_from_R114A_graph",
        "boundary": {
            "preview_only": True,
            "raw_text_available": False,
            "field_projection_allowed": False,
            "formal_apply": False,
            "database_written": False,
        },
        "understanding_graph": graph,
        "deterministic_preview": deterministic_preview,
        "required_output": {
            "teacher_execution_map": {
                "classroom_flow": [
                    "teacher_move/student_action/evidence_to_watch/likely_stuck_point/xiaojiao_support/source_basis"
                ],
                "teacher_review_queue": ["items"],
                "field_projection_basis": "not_projected_in_R114B",
            },
            "agent_execution_steps": ["STEP 1..5 status objects"],
        },
    }
    try:
        from . import providers

        log["provider_called"] = True
        log["model_called"] = True
        result = providers.generate_json_patch(
            {"stage": STAGE_ID, "mode": "teacher_execution_map_preview", "sandbox_only": True},
            {"system_prompt": system_prompt, "user_prompt": json.dumps(payload, ensure_ascii=False)},
            {
                "provider": provider_status.get("provider") or "openai_compatible",
                "model": provider_status.get("model") or "MiniMax-M3",
                "response_format": "json_object",
                "temperature": 0.08,
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


def _merge_model_preview(
    graph: dict[str, Any],
    deterministic_preview: dict[str, Any],
    model_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(model_payload, dict):
        return deterministic_preview
    candidate_map = model_payload.get("teacher_execution_map")
    if not isinstance(candidate_map, dict):
        candidate_map = model_payload.get("teacher_execution_map_preview")
        candidate_map = candidate_map.get("teacher_execution_map") if isinstance(candidate_map, dict) else None
    if not isinstance(candidate_map, dict):
        return deterministic_preview
    if not isinstance(candidate_map.get("classroom_flow"), list) or not candidate_map.get("classroom_flow"):
        return deterministic_preview
    candidate_map.setdefault("field_projection_basis", deterministic_preview["teacher_execution_map"]["field_projection_basis"])
    basis = candidate_map.get("field_projection_basis") or {}
    if isinstance(basis, dict):
        basis["status"] = "not_projected_in_R114B"
        basis["field_projection_performed"] = False
        basis["projection_stage"] = "R114C"
    contamination = _contamination_report(graph, candidate_map)
    if not contamination.get("passed"):
        deterministic_preview.setdefault("model_rejected", []).append(
            {
                "reason": "model_execution_map_contamination_guard_failed",
                "violations": contamination.get("violations"),
            }
        )
        return deterministic_preview
    merged = {
        "stage": STAGE_ID,
        "status": "model_success",
        "teacher_execution_map": candidate_map,
        "agent_execution_steps": model_payload.get("agent_execution_steps")
        if isinstance(model_payload.get("agent_execution_steps"), list)
        else deterministic_preview.get("agent_execution_steps"),
    }
    return merged


def build_teacher_execution_map_preview(
    understanding_v2_graph_preview: dict[str, Any],
    enable_model: bool = False,
) -> dict[str, Any]:
    graph = (
        understanding_v2_graph_preview.get("graph")
        if isinstance(understanding_v2_graph_preview, dict)
        else None
    )
    graph = graph if isinstance(graph, dict) else {}
    deterministic_preview = _build_deterministic_preview(graph)
    model_payload: dict[str, Any] | None = None
    model_log: dict[str, Any] = {
        "provider_called": False,
        "model_called": False,
        "status": "disabled",
        "reason_code": "R114B_model_not_enabled",
    }
    if enable_model:
        model_payload, model_log = _call_model(graph, deterministic_preview)
    merged = _merge_model_preview(graph, deterministic_preview, model_payload)
    teacher_execution_map = merged.get("teacher_execution_map") or {}
    contamination = _contamination_report(graph, teacher_execution_map)
    status = merged.get("status") or deterministic_preview.get("status")
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
            "source": "R114A understanding graph only",
            "raw_text_used": False,
            "reread_original_document": False,
            "upstream_stage": understanding_v2_graph_preview.get("stage")
            if isinstance(understanding_v2_graph_preview, dict)
            else None,
            "upstream_status": understanding_v2_graph_preview.get("status")
            if isinstance(understanding_v2_graph_preview, dict)
            else None,
        },
        "teacher_execution_map": teacher_execution_map,
        "agent_execution_steps": merged.get("agent_execution_steps") or [],
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
            "field_projection_performed": False,
            "target_shell": "R97B validation carrier only",
        },
    }
