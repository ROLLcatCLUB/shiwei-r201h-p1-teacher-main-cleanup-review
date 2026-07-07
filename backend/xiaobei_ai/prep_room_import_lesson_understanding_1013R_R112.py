from __future__ import annotations

import json
import re
import time
from typing import Any


STAGE_ID = "1013R_R112_IMPORT_DOCUMENT_LESSON_UNDERSTANDING_PACKET"


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
    return text[: limit - 1].rstrip() + "…"


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
        "教学准备|差异化任务|作业|评价要点|评价方式|学习评价|教学过程|教学流程|教学环节表|"
        "学习单|PPT素材说明|PPT页面清单|给小美|教学反思"
    )
    end = len(lines)
    for index in range(start, len(lines)):
        clean = _clean_markdown(re.sub(r"^[#\s]*", "", lines[index]))
        clean = re.sub(r"^[0-9]+(?:\.[0-9]+)*\s*", "", clean)
        if index > start and re.match(rf"^(?:{stop})(?:\\s|$|[：:（(])", clean):
            end = index
            break
    return "\n".join(line for line in lines[start:end] if line).strip()


def _section_items(raw_text: str, headings: list[str], limit: int = 8) -> list[str]:
    section = _section_between_any(raw_text, headings)
    items: list[str] = []
    for line in section.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        cleaned = _clean_markdown(re.sub(r"^[-*+0-9.、\s]+", "", line))
        if cleaned and not re.fullmatch(r"[-|:\s]+", cleaned):
            items.append(cleaned)
    return items[:limit]


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


def _deterministic_understanding(session: dict[str, Any]) -> dict[str, Any]:
    raw_text = str(session.get("raw_text") or "")
    meta = session.get("meta") or {}
    episodes = session.get("episodes") or []
    title = _clean(meta.get("title")) or "未命名上传教案"
    unit = _clean(meta.get("unit")) or "上传教案单元待确认"
    grade = _clean(meta.get("grade")) or "年级待确认"
    period = _clean(meta.get("period")) or "课时待确认"
    theme = _table_label_value(raw_text, "主题")
    core_activity = _truncate(meta.get("core_activity") or _section_between_any(raw_text, ["核心活动"]), 260)
    student_prep = _section_items(raw_text, ["学生准备"], limit=10)
    teacher_prep = _section_items(raw_text, ["教师准备", "老师准备"], limit=10)
    evidence_nodes = _section_items(raw_text, ["证据节点"], limit=8)
    differentiation = _section_items(raw_text, ["差异化任务"], limit=8)
    homework = _section_items(raw_text, ["作业"], limit=6)
    episode_titles = [_clean(item.get("title")) for item in episodes if _clean(item.get("title"))]

    facts = [
        f"课题：{title}",
        f"年级：{grade}",
        f"单元：{unit}",
        f"课时位置：{period}",
    ]
    if theme:
        facts.append(f"主题：{theme}")
    if core_activity:
        facts.append(f"核心活动：{core_activity}")

    raw_for_signal = f"{title} {unit} {core_activity} {raw_text}"
    has_shoe_observation_task = (
        any(token in raw_for_signal for token in ["足下生辉", "画画鞋", "鞋", "靴"])
        and any(token in raw_for_signal for token in ["观察", "写生", "正面", "侧面", "后面", "局部", "线条", "轮廓"])
    )
    has_old_shoe_task = (
        any(token in raw_for_signal for token in ["旧鞋", "新鞋", "鞋作品", "足下生辉", "设计故事"])
        and any(token in raw_for_signal for token in ["废旧材料", "第2课设计草图", "上一课完成的设计草图", "发布会"])
    )
    has_gradient_task = (not has_shoe_observation_task) and any(
        token in raw_for_signal for token in ["渐变", "彩虹", "明度", "色阶", "颜色慢慢", "由深到浅", "颜色过渡"]
    )
    has_tool_choice = any(token in raw_for_signal for token in ["彩铅", "油画棒", "水彩笔"])

    if has_shoe_observation_task and not has_old_shoe_task:
        design_reading = {
            "one_sentence": f"本课是“{unit}”中的《{title}》，引导学生观察真实鞋或鞋的图片，从角度、外形结构和局部细节进入线描表达。",
            "core_learning_move": "从生活物品观察，到角度和结构辨认，再把可见细节转化为线条、形状和画面说明。",
            "not_a_generic_task": "不能理解成色彩渐变或自由装饰；关键是观察鞋的正面、侧面、局部结构，并用线条留下观察证据。",
            "lesson_position": f"第{period}课，承担从生活观察进入造型表现的功能；具体教材页码需教师确认。",
        }
        principles = [
            "尊重原稿中的鞋类观察、写生和交流流程，不把色彩渐变或其他样本任务套入本课。",
            "字段补齐必须区分原文事实、系统推断和教师需确认项。",
            "过程改写要围绕学生是否看见角度、结构、局部细节，以及能否把观察转成线条证据来组织。",
            "评价应关注观察角度、外形比例、结构细节和学生能否说明画面依据。",
        ]
    elif has_old_shoe_task:
        prior_anchor = "第2课设计草图" if "第2课设计草图" in raw_text or "上一课完成的设计草图" in raw_text else "前序设计经验"
        public_show = "新鞋发布会" if "新鞋发布会" in raw_text else "作品展示"
        design_reading = {
            "one_sentence": f"本课是“{unit}”中的《{title}》，把{prior_anchor}转化为真实鞋作品，并用设计故事为{public_show}做表达准备。",
            "core_learning_move": "从设计想法到实体作品，再从作品回到设计理由表达。",
            "not_a_generic_task": "不能理解成单纯装饰旧鞋或材料手工课；关键是废旧材料再利用、设计意图落地和口头说明理由。",
            "lesson_position": f"第{period}课，承担单元收束和成果展示前准备的功能。",
        }
        principles = [
            "尊重原稿中的制作任务、设计故事和发布会证据链，不把它改写成无关主题。",
            "字段补齐必须区分原文事实、系统推断和教师需确认项。",
            "过程改写要解释每个环节的学习意图，不逐句搬运教师话术。",
            "评价应围绕材料再利用、设计草图落实、作品效果和设计理由，不写分数。",
        ]
    elif has_gradient_task:
        tool_phrase = "彩铅、油画棒或水彩笔" if has_tool_choice else "合适的色彩工具"
        activity_phrase = core_activity or f"观察并表现《{title}》中的色彩变化"
        design_reading = {
            "one_sentence": f"本课围绕“{_truncate(activity_phrase, 120)}”展开，引导学生从生活和画面中的颜色过渡进入，用{tool_phrase}完成一次渐变表现。",
            "core_learning_move": "从看见颜色慢慢变化，到说出渐变规律，再选择工具把变化画出来。",
            "not_a_generic_task": "不能理解成自由涂色或单纯填色；关键是观察颜色过渡、比较工具差异，并用作品证明显度或色相的渐变效果。",
            "lesson_position": f"第{period}课，承担单元起始、概念建立和工具初试的功能。",
        }
        principles = [
            "尊重原稿中的观察、示范、练习和展评流程，不把其他课的制作任务套入本课。",
            "字段补齐必须区分原文事实、系统推断和教师需确认项。",
            "过程改写要围绕学生是否看见渐变、说清规律、画出过渡效果来组织。",
            "评价应关注颜色是否逐步变化、工具方法是否合适、学生是否能说出自己的表现方法。",
        ]
    else:
        activity_phrase = core_activity or "上传教案中的核心活动"
        design_reading = {
            "one_sentence": f"本课是“{unit}”中的《{title}》，围绕“{_truncate(activity_phrase, 120)}”展开，让学生从已有经验、材料观察或作品感受进入，再把发现落实到一次练习、制作或表达中。",
            "core_learning_move": "先唤醒学生的直观经验和观察发现，再围绕材料、方法或形象特征展开尝试，最后用作品、语言或学习单说清自己的发现和选择。",
            "not_a_generic_task": "不能套用旧鞋、渐变或其他样本模板；只能顺着原文中的目标、材料、活动和评价要求做有限教学理解。",
            "lesson_position": f"第{period}课，具体单元功能需教师结合教材进度确认。",
        }
        principles = [
            "尊重原稿中的课题、核心活动和教学流程，不把其他样本的任务迁移进来。",
            "字段补齐必须区分原文事实、系统推断和教师需确认项。",
            "过程改写要说清学生先看见什么、尝试什么、怎样把想法做出来或说出来。",
            "评价应围绕原稿中的作品效果、表达理由、练习痕迹或交流反馈展开。",
        ]
    risks = [
        "教材版本、册次和页码未稳定出现，不能编造。",
        "工具、材料、安全和分组方式需要教师结合本班条件确认。",
    ]
    if has_shoe_observation_task and not has_old_shoe_task:
        risks.append("真实鞋、图片角度、学生线描基础和观察支架需要教师结合班级情况确认。")
    if has_old_shoe_task:
        risks.append("课外发布会时间和家长协助录音/视频为待确认安排。")
    if has_gradient_task and has_tool_choice:
        risks.append("学生三选一工具的携带情况、替代材料和水彩笔色阶支架需要课前确认。")
    if not student_prep:
        risks.append("学生准备未识别到稳定条目。")
    if not teacher_prep:
        risks.append("教师准备未识别到稳定条目。")

    episode_understanding = []
    for episode in episodes[:8]:
        title_text = _clean(episode.get("title")) or f"环节{len(episode_understanding) + 1}"
        source = _truncate(episode.get("source_content") or episode.get("goal") or title_text, 220)
        combined = f"{title_text} {source}"
        if has_shoe_observation_task and ("导入" in title_text or "引入" in title_text):
            role = "从真实鞋或图片打开观察对象，让学生先说出可见差异，而不是直接评价好不好看。"
            student_task = "观察鞋的外形、角度或局部细节，说出一个看得见的发现。"
        elif has_shoe_observation_task and any(token in title_text for token in ["观察", "指导", "发现"]):
            role = "把鞋的角度、结构和局部细节拆成学生可观察、可描述的对象。"
            student_task = "确定观察角度，指出鞋面、鞋底、鞋带、鞋口或纹样等具体位置。"
        elif has_shoe_observation_task and any(token in title_text for token in ["写生", "动手", "画", "创作"]):
            role = "把观察发现转成线条和画面证据，检查学生是否依据真实观察调整比例和细节。"
            student_task = "用线条画出鞋的轮廓、结构和至少一处局部细节。"
        elif has_shoe_observation_task and any(token in title_text for token in ["展示", "交流", "小结", "评价"]):
            role = "用学生作品回看观察依据，帮助学生说明自己抓住了哪个角度或细节。"
            student_task = "指着作品说出一个来自观察的画面证据，并听取一条调整建议。"
        elif has_old_shoe_task and ("展示" in title_text or "回顾" in title_text):
            role = "承接上一课设计草图，激活“把想法变成作品”的任务意识。"
            student_task = "回看优秀草图，明确今天要把设计做出来。"
        elif has_old_shoe_task and ("示范" in title_text or "方法" in title_text):
            role = "把制作路径和安全注意转化为可操作支架。"
            student_task = "理解纸鞋法、材料装饰法和工具使用要求。"
        elif has_old_shoe_task and ("制作" in title_text or "动手" in title_text):
            role = "核心创作时间，观察学生是否按草图推进并合理利用废旧材料。"
            student_task = "依据草图选择材料、制作或调整鞋作品。"
        elif has_old_shoe_task and "故事" in title_text:
            role = "把作品转化为设计理由表达，为发布会准备证据。"
            student_task = "完成5句话设计故事，说明对象、问题、材料、亮点和改进。"
        elif "导入" in title_text or "引入" in title_text:
            role = "用学生熟悉的生活或图像经验打开本课核心问题，让学生先说出自己已经看见的变化。"
            student_task = "调动已有经验，尝试用自己的话说出本课要观察或解决的问题。"
        elif any(token in title_text for token in ["认识", "观察", "发现", "概念"]):
            role = "把直观感受收束成可命名的概念或规律，避免学生只停留在好看、喜欢。"
            student_task = "观察材料或图片，说出变化规律、关键特征或判断理由。"
        elif "示范" in title_text or "方法" in title_text:
            role = "把教师方法演示转化为学生可模仿、可选择、可检查的操作步骤。"
            student_task = "看清工具使用方法，比较不同方法的效果差异。"
        elif any(token in title_text for token in ["探索", "练习", "尝试", "制作", "创作"]):
            role = "给学生足够的操作时间，把刚形成的概念或方法转化为作品证据。"
            student_task = "选择材料或工具完成练习/作品，并在过程中调整表现方法。"
        elif any(token in title_text for token in ["分享", "展评", "展示", "交流", "评价"]):
            role = "通过同伴作品比较，把作品效果、方法选择和评价语言连接起来。"
            student_task = "展示作品或练习，说出自己看到的效果和可以改进的地方。"
        elif "小结" in title_text or "总结" in title_text:
            role = "收束本课关键词和证据，帮助学生知道自己学会了什么、下一步怎么用。"
            student_task = "回顾本课方法或概念，确认自己的作品证据和后续任务。"
        elif has_gradient_task and any(token in combined for token in ["彩虹", "颜色", "渐变", "过渡"]):
            role = "把颜色变化的观察结果和渐变概念建立联系。"
            student_task = "指出颜色如何慢慢变化，并尝试用渐变语言描述。"
        else:
            role = "依据原文流程推进课堂任务，具体教学意图需要教师结合本班情况确认。"
            student_task = "完成本环节对应的观察、表达、练习或交流任务。"
        episode_understanding.append(
            {
                "source_episode_id": episode.get("episode_id"),
                "title": title_text,
                "source_excerpt": source,
                "learning_role": role,
                "teacher_intent": role,
                "student_task": student_task,
                "evidence_to_watch": episode.get("evidence") or "学生有可观察的作品、过程或表达证据。",
                "support_or_risk": "支架需根据学生材料、工具安全和完成进度即时调整。",
            }
        )

    return {
        "facts": facts,
        "source_evidence": {
            "core_activity": core_activity,
            "student_preparation": student_prep,
            "teacher_preparation": teacher_prep,
            "evidence_nodes": evidence_nodes,
            "differentiation": differentiation,
            "homework": homework,
            "episode_titles": episode_titles,
        },
        "design_reading": design_reading,
        "principles": principles,
        "risks": risks,
        "field_strategy": {
            "basis": "只写原稿确认的课题、单元、课时位置和核心活动；教材页码保持待确认。",
            "analysis": "从上一课草图、材料准备、三年级操作与表达难点推断，不编造班级真实数据。",
            "goals": "保留原目标，必要时按“制作、表达、展示证据”轻度规范。",
            "preparation": "合并学生准备和教师准备，分清材料、工具、安全和展示资源。",
            "assessment": "用证据节点和设计故事组织评价，不写分数。",
            "process": "按环节学习功能重述，不逐句搬原文。",
        },
        "episode_understanding": episode_understanding,
    }


def _call_model(session: dict[str, Any], deterministic: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
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
        "你是小学美术备课设计理解助手，只输出 JSON。"
        "先理解上传教案，不要急着拆字段。"
        "必须区分事实层、原文依据层、设计意图层、原则判断层和风险缺口层。"
        "不得编造教材页码、班级真实学情、学校安排；无法确认的内容写入 risks。"
    )
    payload = {
        "task": "build_lesson_understanding_packet_before_field_mapping",
        "boundary": {
            "preview_only": True,
            "formal_apply": False,
            "database_written": False,
            "teacher_original_overwritten": False,
        },
        "raw_text_excerpt": raw_text[:9000],
        "meta": session.get("meta") or {},
        "fields": session.get("fields") or {},
        "episodes": session.get("episodes") or [],
        "deterministic_understanding": deterministic,
        "output_schema": {
            "facts": ["string"],
            "source_evidence": {
                "core_activity": "string",
                "student_preparation": ["string"],
                "teacher_preparation": ["string"],
                "evidence_nodes": ["string"],
                "differentiation": ["string"],
            },
            "design_reading": {
                "one_sentence": "string",
                "core_learning_move": "string",
                "not_a_generic_task": "string",
                "lesson_position": "string",
            },
            "principles": ["string"],
            "risks": ["string"],
            "field_strategy": "object",
            "episode_understanding": [
                {
                    "source_episode_id": "string",
                    "title": "string",
                    "learning_role": "string",
                    "teacher_intent": "string",
                    "student_task": "string",
                    "evidence_to_watch": "string",
                    "support_or_risk": "string",
                }
            ],
        },
    }
    try:
        from . import providers

        log["provider_called"] = True
        log["model_called"] = True
        result = providers.generate_json_patch(
            {"stage": STAGE_ID, "mode": "lesson_understanding_preview", "sandbox_only": True},
            {"system_prompt": system_prompt, "user_prompt": json.dumps(payload, ensure_ascii=False)},
            {
                "provider": provider_status.get("provider") or "openai_compatible",
                "model": provider_status.get("model") or "MiniMax-M3",
                "response_format": "json_object",
                "temperature": 0.08,
                "max_tokens": 3200,
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


def _merge_understanding(deterministic: dict[str, Any], model_payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(model_payload, dict):
        return deterministic
    allowed = {
        "facts",
        "source_evidence",
        "design_reading",
        "principles",
        "risks",
        "field_strategy",
        "episode_understanding",
    }
    merged = dict(deterministic)
    for key in allowed:
        value = model_payload.get(key)
        if value:
            merged[key] = value
    return merged


def build_import_lesson_understanding_preview(session: dict[str, Any], enable_model: bool = False) -> dict[str, Any]:
    deterministic = _deterministic_understanding(session)
    model_payload: dict[str, Any] | None = None
    model_log: dict[str, Any] = {
        "provider_called": False,
        "model_called": False,
        "status": "disabled",
        "reason_code": "R112_model_not_enabled",
    }
    if enable_model:
        model_payload, model_log = _call_model(session, deterministic)
    understanding = _merge_understanding(deterministic, model_payload)
    return {
        "stage": STAGE_ID,
        "status": "model_success" if model_payload else ("model_fallback" if enable_model else "deterministic_ready"),
        "model_quality_enabled": bool(enable_model),
        "provider_called": bool(model_log.get("provider_called")),
        "model_called": bool(model_log.get("model_called")),
        "model_log": model_log,
        "understanding": understanding,
        "boundary": {
            "preview_only": True,
            "write_allowed": False,
            "database_written": False,
            "memory_written": False,
            "feishu_written": False,
            "formal_apply_performed": False,
            "teacher_original_overwritten": False,
            "old_generation_chain_modified": False,
        },
    }
