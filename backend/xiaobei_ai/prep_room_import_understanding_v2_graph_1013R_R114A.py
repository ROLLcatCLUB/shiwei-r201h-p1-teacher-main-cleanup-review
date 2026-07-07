from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any


STAGE_ID = "1013R_R114A_IMPORT_UNDERSTANDING_V2_GRAPH"

CLAIM_TYPES = {
    "source_fact",
    "source_interpretation",
    "pedagogical_inference",
    "improvement_suggestion",
    "teacher_confirm_required",
}


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _clean_markdown(value: Any) -> str:
    text = str(value or "")
    text = text.replace("\\*", "*").replace("\\_", "_")
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"[*`>#]+", "", text)
    return _clean(text)


def _truncate(value: Any, limit: int = 360) -> str:
    text = _clean_markdown(value)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def _claim_id(text: str, graph_path: str) -> str:
    digest = hashlib.sha1(f"{graph_path}|{text}".encode("utf-8")).hexdigest()[:10]
    return f"r114a_claim_{digest}"


def _claim(
    claims: list[dict[str, Any]],
    *,
    text: str,
    claim_type: str,
    graph_path: str,
    source_evidence: list[str] | None = None,
    confidence: float = 0.6,
    teacher_review_required: bool | None = None,
) -> dict[str, Any]:
    if claim_type not in CLAIM_TYPES:
        claim_type = "pedagogical_inference"
    review_required = teacher_review_required
    if review_required is None:
        review_required = claim_type in {"pedagogical_inference", "improvement_suggestion", "teacher_confirm_required"}
    item = {
        "claim_id": _claim_id(text, graph_path),
        "claim_type": claim_type,
        "text": _clean(text),
        "graph_path": graph_path,
        "source_evidence": [_truncate(value, 260) for value in (source_evidence or []) if _clean(value)],
        "confidence": round(float(confidence), 2),
        "teacher_review_required": bool(review_required),
    }
    claims.append(item)
    return item


def _table_label_value(raw_text: str, label: str) -> str:
    for line in str(raw_text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if not line.strip().startswith("|"):
            continue
        cells = [_clean_markdown(cell) for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 2 and cells[0] == label:
            return cells[1]
    return ""


def _section_between_any(raw_text: str, headings: list[str]) -> str:
    lines = [line.strip() for line in str(raw_text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    start = -1
    for index, line in enumerate(lines):
        clean = _clean_markdown(re.sub(r"^[#\s]*", "", line))
        clean = re.sub(r"^[0-9]+(?:\.[0-9]+)*\s*", "", clean)
        clean = re.sub(r"^[一二三四五六七八九十0-9]+[、.．]\s*", "", clean)
        if any(re.match(rf"^{re.escape(heading)}(?:\\s|$|[：:（(])", clean) for heading in headings):
            start = index + 1
            break
    if start < 0:
        return ""
    stop = (
        "基本信息|课时目标|教学目标|学习目标|主要内容|核心活动|证据节点|学生准备|教师准备|老师准备|"
        "教学准备|差异化任务|作业|评价要点|评价方式|学习评价|教学反思|教学过程|教学流程|"
        "教学环节表|学习单|PPT素材说明|PPT页面清单|给小美"
    )
    end = len(lines)
    for index in range(start, len(lines)):
        clean = _clean_markdown(re.sub(r"^[#\s]*", "", lines[index]))
        clean = re.sub(r"^[0-9]+(?:\.[0-9]+)*\s*", "", clean)
        if index > start and re.match(rf"^(?:{stop})(?:\\s|$|[：:（(])", clean):
            end = index
            break
    return "\n".join(line for line in lines[start:end] if line).strip()


def _section_items(raw_text: str, headings: list[str], limit: int = 10) -> list[str]:
    section = _section_between_any(raw_text, headings)
    items: list[str] = []
    for line in section.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        cleaned = _clean_markdown(re.sub(r"^[-*+0-9.、\s]+", "", line))
        if cleaned and not re.fullmatch(r"[-|:\s]+", cleaned):
            items.append(cleaned)
    return items[:limit]


def _contains(raw_text: str, tokens: list[str]) -> bool:
    return any(token in raw_text for token in tokens)


def _blocked_phrases(raw_text: str) -> list[str]:
    checks = [
        ("上一课设计草图", ["上一课设计草图", "第2课设计草图", "设计草图"]),
        ("新鞋发布会", ["新鞋发布会"]),
        ("发布会", ["发布会"]),
        ("5句话设计故事", ["5句话", "五句话", "设计故事"]),
        ("废旧材料", ["废旧材料", "废旧", "旧材料"]),
        ("纸鞋模板", ["纸鞋模板"]),
    ]
    return [phrase for phrase, tokens in checks if not _contains(raw_text, tokens)]


def _source_fact_texts(graph: dict[str, Any]) -> list[str]:
    claims = graph.get("claim_registry") or []
    return [str(item.get("text") or "") for item in claims if item.get("claim_type") == "source_fact"]


def _contamination_report(raw_text: str, graph: dict[str, Any]) -> dict[str, Any]:
    blocked = _blocked_phrases(raw_text)
    source_facts = _source_fact_texts(graph)
    violations = []
    for phrase in blocked:
        for fact in source_facts:
            if phrase in fact:
                violations.append(
                    {
                        "phrase": phrase,
                        "claim_text": fact,
                        "violation": "absent_phrase_used_as_source_fact",
                    }
                )
    return {
        "guard_rules": [
            "Absent sample-specific phrases must not appear as source_fact.",
            "System improvements must stay in improvement_opportunities, not faithful_reconstruction.",
            "Teacher-confirmation gaps must not be converted into confirmed facts.",
        ],
        "blocked_source_fact_phrases": blocked,
        "violations": violations,
        "passed": not violations,
    }


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


def _build_deterministic_graph(session: dict[str, Any], r112_preview: dict[str, Any] | None = None) -> dict[str, Any]:
    raw_text = str(session.get("raw_text") or "")
    meta = session.get("meta") or {}
    fields = session.get("fields") or {}
    episodes = session.get("episodes") or []
    r112_understanding = (r112_preview or {}).get("understanding") if isinstance(r112_preview, dict) else {}
    r112_understanding = r112_understanding if isinstance(r112_understanding, dict) else {}

    title = _clean(meta.get("title")) or "未命名上传教案"
    unit = _clean(meta.get("unit")) or "上传教案单元待确认"
    grade = _clean(meta.get("grade")) or "年级待确认"
    period = _clean(meta.get("period")) or "课时待确认"
    theme = _table_label_value(raw_text, "主题")
    core_activity = _truncate(meta.get("core_activity") or _section_between_any(raw_text, ["核心活动"]), 320)
    student_prep = _section_items(raw_text, ["学生准备"], limit=12)
    teacher_prep = _section_items(raw_text, ["教师准备", "老师准备"], limit=12)
    evidence_nodes = _section_items(raw_text, ["证据节点"], limit=10)
    differentiation = _section_items(raw_text, ["差异化任务"], limit=10)
    homework = _section_items(raw_text, ["作业"], limit=8)

    has_prior_design = _contains(raw_text, ["上一课设计草图", "第2课设计草图", "设计草图"])
    has_launch = _contains(raw_text, ["新鞋发布会", "发布会"])
    has_design_story = _contains(raw_text, ["5句话", "五句话", "设计故事"])
    has_reused_materials = _contains(raw_text, ["废旧材料", "废旧", "旧材料"])
    has_real_making = _contains(raw_text, ["制作", "做出来", "真实", "成品", "作品"])
    has_safety_tools = _contains(raw_text, ["剪刀", "热熔胶", "胶水"])
    has_shoe_observation = (
        _contains(f"{title} {unit} {core_activity} {raw_text}", ["足下生辉", "画画鞋", "鞋", "靴"])
        and _contains(raw_text, ["观察", "写生", "正面", "侧面", "后面", "局部", "轮廓", "线条"])
    )
    has_gradient = (not has_shoe_observation) and _contains(
        f"{title} {core_activity} {raw_text}",
        ["渐变", "彩虹", "明度", "色阶", "颜色慢慢", "由深到浅", "颜色过渡"],
    )
    has_tool_choice = _contains(raw_text, ["彩铅", "油画棒", "水彩笔"])

    claims: list[dict[str, Any]] = []
    lesson_identity = {
        "title": _claim(
            claims,
            text=f"课题：{title}",
            claim_type="source_fact" if meta.get("title") else "teacher_confirm_required",
            graph_path="lesson_identity.title",
            source_evidence=[title] if meta.get("title") else [],
            confidence=0.92 if meta.get("title") else 0.2,
            teacher_review_required=not bool(meta.get("title")),
        ),
        "unit": _claim(
            claims,
            text=f"单元：{unit}",
            claim_type="source_fact" if meta.get("unit") else "teacher_confirm_required",
            graph_path="lesson_identity.unit",
            source_evidence=[unit] if meta.get("unit") else [],
            confidence=0.88 if meta.get("unit") else 0.2,
            teacher_review_required=not bool(meta.get("unit")),
        ),
        "grade": _claim(
            claims,
            text=f"年级：{grade}",
            claim_type="source_fact" if meta.get("grade") else "teacher_confirm_required",
            graph_path="lesson_identity.grade",
            source_evidence=[grade] if meta.get("grade") else [],
            confidence=0.9 if meta.get("grade") else 0.2,
            teacher_review_required=not bool(meta.get("grade")),
        ),
        "period": _claim(
            claims,
            text=f"课时位置：{period}",
            claim_type="source_fact" if meta.get("period") else "teacher_confirm_required",
            graph_path="lesson_identity.period",
            source_evidence=[period] if meta.get("period") else [],
            confidence=0.86 if meta.get("period") else 0.2,
            teacher_review_required=not bool(meta.get("period")),
        ),
    }
    if theme:
        lesson_identity["theme"] = _claim(
            claims,
            text=f"主题：{theme}",
            claim_type="source_fact",
            graph_path="lesson_identity.theme",
            source_evidence=[theme],
            confidence=0.82,
            teacher_review_required=False,
        )

    protected_core_claims = []
    if core_activity:
        protected_core_claims.append(
            _claim(
                claims,
                text=f"核心活动：{core_activity}",
                claim_type="source_fact",
                graph_path="faithful_reconstruction.protected_core.core_activity",
                source_evidence=[core_activity],
                confidence=0.85,
                teacher_review_required=False,
            )
        )
    if has_prior_design:
        protected_core_claims.append(
            _claim(
                claims,
                text="原文包含前序设计草图或第2课设计草图作为本课制作依据。",
                claim_type="source_fact",
                graph_path="faithful_reconstruction.protected_core.prior_design",
                source_evidence=[line for line in ["第2课设计草图", "上一课完成的设计草图"] if line in raw_text] or ["设计草图"],
                confidence=0.86,
                teacher_review_required=False,
            )
        )
    if has_reused_materials:
        protected_core_claims.append(
            _claim(
                claims,
                text="原文要求使用废旧材料或旧材料完成创作。",
                claim_type="source_fact",
                graph_path="faithful_reconstruction.protected_core.reused_materials",
                source_evidence=["废旧材料" if "废旧材料" in raw_text else "旧材料/废旧"],
                confidence=0.84,
                teacher_review_required=False,
            )
        )
    if has_shoe_observation and not has_reused_materials:
        shoe_evidence = [
            item
            for item in ["足下生辉", "画画鞋", "鞋", "正面", "侧面", "后面", "局部", "写生", "线条", "轮廓"]
            if item in f"{title} {unit} {core_activity} {raw_text}"
        ]
        protected_core_claims.append(
            _claim(
                claims,
                text="原文指向鞋的观察写生：比较角度、外形结构和局部细节，并用线条或画面表达观察发现。",
                claim_type="source_interpretation",
                graph_path="faithful_reconstruction.protected_core.shoe_observation",
                source_evidence=shoe_evidence[:6] or ["鞋的观察写生"],
                confidence=0.78,
                teacher_review_required=True,
            )
        )
    if has_design_story:
        protected_core_claims.append(
            _claim(
                claims,
                text="原文包含设计故事或5句话表达任务。",
                claim_type="source_fact",
                graph_path="faithful_reconstruction.protected_core.design_story",
                source_evidence=[value for value in ["5句话", "设计故事"] if value in raw_text],
                confidence=0.86,
                teacher_review_required=False,
            )
        )
    if has_launch:
        protected_core_claims.append(
            _claim(
                claims,
                text="原文包含发布会或新鞋发布会作为展示/表达情境。",
                claim_type="source_fact",
                graph_path="faithful_reconstruction.protected_core.launch",
                source_evidence=["新鞋发布会" if "新鞋发布会" in raw_text else "发布会"],
                confidence=0.86,
                teacher_review_required=False,
            )
        )

    transformation_parts = []
    if has_shoe_observation and not has_reused_materials:
        transformation_parts = ["观察鞋的角度和外形", "辨认结构与局部细节", "用线条记录观察", "用作品说明观察依据"]
    elif has_prior_design:
        transformation_parts.append("前序设计想法")
    if has_real_making or has_reused_materials:
        transformation_parts.append("材料选择与实体制作")
    if has_design_story:
        transformation_parts.append("设计理由表达")
    if has_launch:
        transformation_parts.append("展示/发布证据")
    if has_gradient:
        transformation_parts = ["观察颜色过渡", "理解渐变规律", "选择工具表现渐变", "比较作品证据"]
    if not transformation_parts:
        episode_titles = [_clean(item.get("title")) for item in episodes if _clean(item.get("title"))]
        transformation_parts = episode_titles[:4] or ["学习任务待教师确认"]
    core_transform_text = "、".join(transformation_parts)
    if has_shoe_observation and not has_reused_materials:
        core_learning_text = "本课的学习重心，是让学生从熟悉的鞋出发，比较不同角度的外形、结构和局部细节，再用线条和画面组织把观察发现表达出来。"
    elif has_prior_design and has_real_making:
        core_learning_text = "本课的学习重心，是让学生带着前序设计进入制作现场，在材料选择、结构处理和作品说明中，把原来的想法做出来、说清楚。"
    elif has_gradient:
        core_learning_text = "本课的学习重心，是让学生先从生活和画面中看见颜色慢慢变化，再选择合适工具试着表现这种过渡，并在交流中说清哪里变得自然。"
    elif core_activity:
        core_learning_text = f"本课的学习重心，是围绕“{_truncate(core_activity, 120)}”，让学生先观察或回忆已有经验，再通过方法尝试和作品表达说明自己的发现。"
    else:
        core_learning_text = f"本课的学习重心，可先顺着{core_transform_text}组织观察、尝试、创作和交流；具体学情与材料条件仍需教师确认。"
    core_learning_transformation = _claim(
        claims,
        text=core_learning_text,
        claim_type="source_interpretation",
        graph_path="core_learning_transformation",
        source_evidence=[core_activity] + [_clean(item.get("title")) for item in episodes[:5] if _clean(item.get("title"))],
        confidence=0.72,
    )

    if has_shoe_observation and not has_reused_materials:
        intent_text = "本课不是色彩渐变或自由装饰，而是通过鞋的角度、结构和局部观察，训练学生把生活物品转化为可说明的线描表达。"
    elif has_prior_design and has_real_making:
        intent_text = "本课不是重新发散设计，而是把已有设计想法推进到可制作、可展示、可说明的学习成果。"
    elif has_gradient:
        intent_text = "本课不是自由涂色，而是通过生活图像、教师示范和学生练习，让学生看见并表现颜色逐步过渡的规律。"
    else:
        intent_text = "本课的原始设计意图需要从目标、活动和证据节点继续确认，不宜套用其他样本的单元任务。"
    original_design_intent = _claim(
        claims,
        text=intent_text,
        claim_type="source_interpretation",
        graph_path="faithful_reconstruction.original_design_intent",
        source_evidence=[core_activity] + [_truncate(item.get("source_content"), 180) for item in episodes[:3]],
        confidence=0.7 if has_prior_design or core_activity else 0.45,
    )

    causal_chain = []
    for index, episode in enumerate(episodes[:8], start=1):
        title_text = _clean(episode.get("title")) or f"环节{index}"
        source = _truncate(episode.get("source_content") or episode.get("goal") or title_text, 220)
        if has_shoe_observation and ("导入" in title_text or "引入" in title_text):
            why_now = "先从真实鞋或鞋的图片进入，让学生说出外形、角度或局部差异，为后面的观察写生建立对象。"
        elif has_shoe_observation and any(token in title_text for token in ["观察", "指导", "发现"]):
            why_now = "在动笔前先确定观察角度和结构位置，避免学生凭概念画一只符号化的鞋。"
        elif has_shoe_observation and any(token in title_text for token in ["写生", "动手", "画", "创作"]):
            why_now = "把刚才确认的角度、轮廓和局部细节转成线条证据，让作品能看出观察依据。"
        elif has_shoe_observation and any(token in title_text for token in ["展示", "交流", "小结", "评价"]):
            why_now = "用学生作品回看观察依据，确认画面中哪些线条、比例或细节来自真实观察。"
        elif has_prior_design and ("回顾" in title_text or "展示" in title_text):
            why_now = "先回到前序设计依据，避免学生脱离原设计随意制作。"
        elif has_gradient and ("导入" in title_text or "引入" in title_text):
            why_now = "先用彩虹或生活经验激活学生对颜色变化的直观感受，为认识渐变概念做铺垫。"
        elif "示范" in title_text or "方法" in title_text:
            if has_gradient and has_tool_choice:
                why_now = "在学生练习前比较不同工具的渐变方法，让学生知道彩铅、油画棒和水彩笔各自怎么形成过渡。"
            else:
                why_now = "在学生动手前提供可选择的制作路径和安全边界。"
        elif "制作" in title_text or "动手" in title_text or "探索" in title_text or "练习" in title_text:
            why_now = "把设计想法放到材料和结构中验证，形成过程证据。"
            if has_gradient:
                why_now = "让学生把“颜色慢慢变化”的理解落实到工具练习中，形成可观察的渐变效果。"
        elif has_design_story and ("故事" in title_text or "表达" in title_text):
            why_now = "在作品形成后整理设计理由，让作品成为可说明的设计成果。"
        elif has_launch and ("小结" in title_text or "预告" in title_text or "展示" in title_text):
            why_now = "把课内成果连接到后续展示情境，明确还需要准备的证据。"
        elif has_gradient and ("认识" in title_text or "观察" in title_text or "发现" in title_text or "概念" in title_text):
            why_now = "先把生活中的颜色变化命名为渐变，帮助学生从感觉好看转向说出过渡规律。"
        elif has_gradient and ("分享" in title_text or "展评" in title_text or "展示" in title_text or "交流" in title_text):
            why_now = "用同伴作品比较不同工具的渐变效果，让评价回到颜色是否逐步变化。"
        else:
            why_now = "该环节的顺序依据来自原文流程，具体因果需要教师确认。"
        causal_claim = _claim(
            claims,
            text=f"{title_text}：{why_now}",
            claim_type="source_interpretation" if why_now.startswith("该环节") is False else "teacher_confirm_required",
            graph_path=f"teaching_causal_chain.{index}",
            source_evidence=[source],
            confidence=0.68 if "需要教师确认" not in why_now else 0.35,
        )
        causal_chain.append(
            {
                "episode_index": index,
                "source_episode_id": episode.get("episode_id"),
                "title": title_text,
                "why_now": why_now,
                "source_evidence": [source],
                "claim_id": causal_claim["claim_id"],
                "claim_type": causal_claim["claim_type"],
            }
        )

    evidence_graph = []
    evidence_sources = evidence_nodes or [_clean(item.get("evidence")) for item in episodes if _clean(item.get("evidence"))]
    evidence_sources.extend(homework)
    for index, evidence in enumerate([item for item in evidence_sources if _clean(item)][:10], start=1):
        target = "判断学生是否理解本课任务并形成可说明的学习成果。"
        if "草图" in evidence:
            target = "证明学生带着前序设计进入制作。"
        elif "过程" in evidence or "半成品" in evidence:
            target = "证明学生在材料选择和制作中推进设计。"
        elif "成品" in evidence or "作品" in evidence:
            target = "证明学生形成可展示的实体成果。"
        elif "故事" in evidence or "陈述" in evidence or "录音" in evidence or "视频" in evidence:
            target = "证明学生能表达设计对象、问题、材料方法和改进。"
        evidence_claim = _claim(
            claims,
            text=f"证据节点：{evidence}；用途：{target}",
            claim_type="source_fact" if evidence in raw_text else "source_interpretation",
            graph_path=f"evidence_graph.{index}",
            source_evidence=[evidence],
            confidence=0.75,
            teacher_review_required=False,
        )
        evidence_graph.append(
            {
                "evidence_id": f"r114a_evidence_{index:02d}",
                "evidence": evidence,
                "supports": target,
                "claim_id": evidence_claim["claim_id"],
                "claim_type": evidence_claim["claim_type"],
            }
        )

    teacher_confirmation_gaps = [
        _claim(
            claims,
            text="教材版本、册次、页码和学校实际进度未在原文中稳定确认。",
            claim_type="teacher_confirm_required",
            graph_path="teacher_confirmation_gaps.textbook_page",
            source_evidence=[],
            confidence=0.9,
        )
    ]
    if has_safety_tools:
        teacher_confirmation_gaps.append(
            _claim(
                claims,
                text="剪刀、胶水或热熔胶等工具的安全与分组管理需要教师确认。",
                claim_type="teacher_confirm_required",
                graph_path="teacher_confirmation_gaps.tool_safety",
                source_evidence=[item for item in ["剪刀", "胶水", "热熔胶"] if item in raw_text],
                confidence=0.82,
            )
        )
    if has_launch and _contains(raw_text, ["待定", "可选", "家长"]):
        teacher_confirmation_gaps.append(
            _claim(
                claims,
                text="发布会时间、家长协助或录音视频安排属于后续确认事项。",
                claim_type="teacher_confirm_required",
                graph_path="teacher_confirmation_gaps.launch_arrangement",
                source_evidence=[item for item in ["待定", "可选", "家长"] if item in raw_text],
                confidence=0.78,
            )
        )
    if not student_prep:
        teacher_confirmation_gaps.append(
            _claim(
                claims,
                text="学生准备未在原文中形成稳定条目，需要教师确认。",
                claim_type="teacher_confirm_required",
                graph_path="teacher_confirmation_gaps.student_preparation",
                source_evidence=[],
                confidence=0.7,
            )
        )

    improvement_opportunities = []
    if has_prior_design:
        improvement_opportunities.append(
            _claim(
                claims,
                text="可在执行地图中增加“对照草图确认今天要实现的部分”的支架。",
                claim_type="improvement_suggestion",
                graph_path="improvement_opportunities.prior_design_scaffold",
                source_evidence=["设计草图"],
                confidence=0.62,
            )
        )
    if has_reused_materials:
        improvement_opportunities.append(
            _claim(
                claims,
                text="可增加“为什么选择这个废旧材料”的追问，避免学生只做装饰堆叠。",
                claim_type="improvement_suggestion",
                graph_path="improvement_opportunities.material_reasoning",
                source_evidence=["废旧材料"],
                confidence=0.64,
            )
        )
    if has_design_story:
        improvement_opportunities.append(
            _claim(
                claims,
                text="可把设计故事的5句话作为评价证据结构，而不是只作为课后说明。",
                claim_type="improvement_suggestion",
                graph_path="improvement_opportunities.design_story_as_evidence",
                source_evidence=["5句话", "设计故事"],
                confidence=0.66,
            )
        )

    faithful_reconstruction = {
        "protected_core_claim_ids": [item["claim_id"] for item in protected_core_claims],
        "original_design_intent_claim_id": original_design_intent["claim_id"],
        "source_evidence_summary": {
            "core_activity": core_activity,
            "student_preparation": student_prep,
            "teacher_preparation": teacher_prep,
            "evidence_nodes": evidence_nodes,
            "differentiation": differentiation,
            "homework": homework,
        },
        "do_not_rewrite_as": [
            "generic_field_extraction",
            "full_lesson_replacement",
            "unverified_textbook_page",
            "sample_specific_template_without_source_evidence",
        ],
    }
    graph = {
        "graph_version": "import_understanding_v2_graph_r114a_v0.1",
        "lesson_identity": lesson_identity,
        "faithful_reconstruction": faithful_reconstruction,
        "core_learning_transformation": core_learning_transformation,
        "teaching_causal_chain": causal_chain,
        "evidence_graph": evidence_graph,
        "student_difficulty_model": {
            "claim_type": "pedagogical_inference",
            "items": [
                "学生可能只画出概念化的鞋，忽略观察角度、比例结构和局部细节。"
                if has_shoe_observation and not has_reused_materials
                else "学生可能把制作理解成自由装饰，而不是实现原有设计意图。"
                if has_prior_design and has_reused_materials
                else "学生可能知道要完成什么作品或练习，却还需要教师帮助他们把观察发现、材料方法和作品效果联系起来。"
            ],
            "teacher_review_required": True,
        },
        "teacher_support_model": {
            "claim_type": "pedagogical_inference",
            "items": [
                "教师支架宜先保护原稿里的核心任务，再用追问、短示范或同伴交流帮助学生说清选择理由。"
            ],
            "teacher_review_required": True,
        },
        "improvement_opportunities": improvement_opportunities,
        "teacher_confirmation_gaps": teacher_confirmation_gaps,
        "field_projection_basis": {
            "status": "not_projected_in_R114A",
            "field_projection_performed": False,
            "projection_stage": "R114C",
            "rule": "R114A only builds the understanding graph; R114C will project fields from graph nodes.",
        },
        "r112_dependency": {
            "stage": (r112_preview or {}).get("stage") if isinstance(r112_preview, dict) else None,
            "status": (r112_preview or {}).get("status") if isinstance(r112_preview, dict) else None,
            "used_as_initial_reading": bool(r112_understanding),
        },
        "claim_registry": claims,
    }
    graph["contamination_guard"] = _contamination_report(raw_text, graph)
    return graph


def _merge_model_graph(deterministic: dict[str, Any], model_payload: dict[str, Any] | None, raw_text: str) -> dict[str, Any]:
    if not isinstance(model_payload, dict):
        return deterministic
    candidate = model_payload.get("graph") if isinstance(model_payload.get("graph"), dict) else model_payload
    if not isinstance(candidate, dict):
        return deterministic
    required = {"lesson_identity", "faithful_reconstruction", "claim_registry"}
    if not required.issubset(candidate):
        return deterministic
    candidate["contamination_guard"] = _contamination_report(raw_text, candidate)
    if candidate["contamination_guard"].get("violations"):
        deterministic.setdefault("model_rejected", []).append(
            {
                "reason": "model_graph_contamination_guard_failed",
                "violations": candidate["contamination_guard"].get("violations"),
            }
        )
        return deterministic
    basis = candidate.setdefault("field_projection_basis", deterministic.get("field_projection_basis"))
    if isinstance(basis, dict):
        basis.setdefault("status", "not_projected_in_R114A")
        basis.setdefault("field_projection_performed", False)
        basis.setdefault("projection_stage", "R114C")
    else:
        candidate["field_projection_basis"] = deterministic.get("field_projection_basis")
    return candidate


def _call_model(session: dict[str, Any], r112_preview: dict[str, Any] | None, deterministic_graph: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
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

    raw_text = str(session.get("raw_text") or "")
    system_prompt = (
        "你是小学美术导入教案理解图构建助手，只输出 JSON。"
        "本轮不是字段映射，也不是优化教案。先忠实重构原教案，再单独列出改进机会。"
        "每个判断必须有 claim_type：source_fact、source_interpretation、pedagogical_inference、"
        "improvement_suggestion 或 teacher_confirm_required。"
        "原文未出现的内容不得写成 source_fact；系统建议必须放入 improvement_opportunities。"
    )
    payload = {
        "task": "build_import_understanding_v2_graph",
        "boundary": {
            "preview_only": True,
            "formal_apply": False,
            "database_written": False,
            "teacher_original_overwritten": False,
            "field_projection_allowed": False,
        },
        "raw_text_excerpt": raw_text[:9000],
        "r112_initial_understanding": r112_preview or {},
        "deterministic_graph": deterministic_graph,
        "required_output": {
            "graph": {
                "lesson_identity": "object",
                "faithful_reconstruction": "object",
                "core_learning_transformation": "claim",
                "teaching_causal_chain": ["nodes"],
                "evidence_graph": ["nodes"],
                "student_difficulty_model": "object",
                "teacher_support_model": "object",
                "improvement_opportunities": ["claims"],
                "teacher_confirmation_gaps": ["claims"],
                "field_projection_basis": "object with status not_projected_in_R114A",
                "claim_registry": ["claims with claim_type/source_evidence/confidence/teacher_review_required"],
            }
        },
    }
    try:
        from . import providers

        log["provider_called"] = True
        log["model_called"] = True
        result = providers.generate_json_patch(
            {"stage": STAGE_ID, "mode": "understanding_v2_graph_preview", "sandbox_only": True},
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
        parser_meta: dict[str, Any] = {}
        if parsed is None:
            try:
                from . import output_parser

                parsed, parser_meta = output_parser.parse_patch_output(raw, provider_meta)
            except Exception as parse_exc:
                parser_meta = {
                    "parser_mode": "fallback_failed",
                    "parse_error_code": str(getattr(parse_exc, "code", "") or "json_parse_error"),
                    "parse_subcode": str(getattr(parse_exc, "parse_subcode", "") or ""),
                }
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
                "parser_meta": parser_meta,
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


def build_import_understanding_v2_graph_preview(
    session: dict[str, Any],
    r112_preview: dict[str, Any] | None = None,
    enable_model: bool = False,
) -> dict[str, Any]:
    deterministic_graph = _build_deterministic_graph(session, r112_preview=r112_preview)
    model_payload: dict[str, Any] | None = None
    model_log: dict[str, Any] = {
        "provider_called": False,
        "model_called": False,
        "status": "disabled",
        "reason_code": "R114A_model_not_enabled",
    }
    if enable_model:
        model_payload, model_log = _call_model(session, r112_preview, deterministic_graph)
    graph = _merge_model_graph(deterministic_graph, model_payload, str(session.get("raw_text") or ""))
    return {
        "stage": STAGE_ID,
        "status": "model_success" if model_payload and graph is not deterministic_graph else ("model_fallback" if enable_model else "deterministic_ready"),
        "model_quality_enabled": bool(enable_model),
        "provider_called": bool(model_log.get("provider_called")),
        "model_called": bool(model_log.get("model_called")),
        "model_log": model_log,
        "graph": graph,
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
        },
    }
