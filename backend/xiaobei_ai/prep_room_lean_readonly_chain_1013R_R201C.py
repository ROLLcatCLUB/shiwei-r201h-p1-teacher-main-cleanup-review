from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from . import prep_room_graph_field_projection_1013R_R114C as r114c
from . import prep_room_import_lesson_understanding_1013R_R112 as r112
from . import prep_room_import_understanding_v2_graph_1013R_R114A as r114a
from . import prep_room_real_upload_entry_preview_1013R_R103 as r103
from . import prep_room_teacher_execution_map_1013R_R114B as r114b
from . import prep_room_uploaded_lesson_readonly_preview_1013R_R101A as readonly_preview


STAGE_ID = "1013R_R201C_READONLY_ROUTE_SWITCH_TO_LEAN_CHAIN"

ALLOWED_MAIN_SOURCES = {
    "uploaded_source",
    "R114_graph",
    "R114_execution_map",
    "R114_field_projection",
    "teacher_accepted_provisional_candidate",
}

FORBIDDEN_MAIN_SOURCES = {
    "R200A_kernel",
    "R200B_candidate",
    "R97B_P3_derivation_spine",
    "deterministic_fallback",
    "legacy_shell",
    "unknown",
    "source_gap",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


GENERIC_FRONT_MATTER_PATTERNS = [
    "围绕本课任务",
    "具体学情与材料条件仍需教师确认",
    "上传教案单元待确认",
    "材料、工具、大屏资源和安全安排需教师根据本班条件确认",
    "可先顺着材料选择与实体制作组织观察、尝试、创作和交流",
    "学生能围绕本课任务完成一次有目标的观察、尝试或表达",
    "学生能说出自己的学习发现、方法选择或作品特点",
    "学生能在交流中用课堂证据说明自己的学习成果",
    "重点：围绕本课任务形成清楚的观察、方法尝试和作品表达",
    "难点：让学生说清方法选择和学习成果之间的关系",
]

TOPIC_GUARD_TERMS = [
    "鞋",
    "旧鞋",
    "新鞋",
    "鞋面",
    "鞋底",
    "鞋带",
    "鞋头",
    "鞋跟",
    "草图",
    "发布会",
    "经纬",
    "编织",
    "青绿",
    "石青",
    "石绿",
    "海洋",
    "渐变",
]


def _is_generic_front_matter(value: Any) -> bool:
    text = _clean(value)
    return bool(text) and any(pattern in text for pattern in GENERIC_FRONT_MATTER_PATTERNS)


def _off_topic_terms(value: Any, source_corpus: str) -> list[str]:
    text = _clean(value)
    if not text:
        return []
    return [term for term in TOPIC_GUARD_TERMS if term in text and term not in source_corpus]


def _is_off_topic_for_source(value: Any, source_corpus: str) -> bool:
    return bool(_off_topic_terms(value, source_corpus))


def _naturalize_table_row(cells: list[str]) -> str:
    clean_cells = [_clean(cell).strip("* ") for cell in cells if _clean(cell).strip("* ")]
    if not clean_cells:
        return ""
    title = clean_cells[0]
    if re.fullmatch(r"\d+", title) and len(clean_cells) > 1:
        title = clean_cells[1]
        clean_cells = clean_cells[1:]
    labels = ["环节", "教师活动", "学生活动", "设计意图", "材料", "证据", "评价"]
    parts = []
    for idx, cell in enumerate(clean_cells):
        label = labels[idx] if idx < len(labels) else f"信息{idx + 1}"
        if idx == 0:
            parts.append(f"{label}：{cell}")
        else:
            parts.append(f"{label}：{cell}")
    return "；".join(parts)


def _sanitize_teacher_visible_text(value: Any) -> str:
    text = _clean(value)
    if "|" in text:
        cells = [_clean(cell) for cell in re.split(r"\|", text) if _clean(cell)]
        text = _naturalize_table_row(cells) or text.replace("|", " ")
    text = re.sub(r"\s*\|\s*", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _teacher_visible_source_label(source_status: Any) -> str:
    labels = {
        "uploaded_source": "上传原文依据",
        "R114_graph": "理解图依据",
        "R114_execution_map": "教学推进依据",
        "R114_field_projection": "理解整理依据",
        "teacher_accepted_provisional_candidate": "教师确认候选",
        "source_gap": "待教师补充",
    }
    return labels.get(_clean(source_status), "来源待确认")


def _sanitize_title(value: Any, fallback: str) -> str:
    text = _clean(value)
    text = text.strip("* ")
    text = re.sub(r"^\d+[\.、]\s*", "", text)
    text = re.sub(r"[（(]?\d+\s*分钟[）)]?", "", text)
    text = re.split(r"[:：。；;]", text)[0]
    return (text or fallback)[:28]


def _source_span(raw_text: str, needle: str, start_at: int = 0) -> dict[str, int | None]:
    text = _clean(needle)
    if not text:
        return {"start": None, "end": None}
    idx = raw_text.find(text, max(0, start_at))
    if idx < 0:
        idx = raw_text.find(text[:48], max(0, start_at)) if len(text) > 48 else -1
    if idx < 0:
        return {"start": None, "end": None}
    return {"start": idx, "end": idx + len(text)}


def _excerpt(raw_text: str, span: dict[str, int | None], fallback: str = "") -> str:
    start = span.get("start")
    end = span.get("end")
    if isinstance(start, int) and isinstance(end, int) and start >= 0 and end > start:
        return _clean(raw_text[start : min(len(raw_text), end + 80)])[:260]
    return _clean(fallback)[:260]


def _extract_process_text(raw_text: str) -> str:
    match = re.search(r"(?:教学过程|教学流程|教学环节|课堂过程)[:：]?\s*(.*)", raw_text, flags=re.S)
    process_text = match.group(1) if match else raw_text
    stop = re.search(r"\n\s*(?:评价证据|评价方式|作业|板书设计|教学反思|课后反思)[:：]", process_text)
    if stop:
        process_text = process_text[: stop.start()]
    return process_text


def _normalize_episode(
    *,
    raw_text: str,
    parser_id: str,
    index: int,
    title: str,
    source_content: str,
    duration_min: int | None = None,
    cursor: int = 0,
    span_needle: str | None = None,
) -> dict[str, Any]:
    clean_title = _sanitize_title(title, f"环节{index}")
    content = _clean(source_content)
    needle = _clean(span_needle) or content or clean_title
    span = _source_span(raw_text, needle, cursor)
    source_excerpt = _excerpt(raw_text, span, needle)
    confidence = 0.82 if content and span.get("start") is not None else 0.48
    return {
        "index": index,
        "title": clean_title,
        "duration_min": duration_min,
        "source_content": content,
        "goal": content,
        "teacher_action": content,
        "student_action": "",
        "material": "",
        "screen_or_tech": "",
        "evidence": "",
        "question": "",
        "feedback": "",
        "episode_id": f"r201c_{parser_id}_{index:02d}",
        "episode_type": "lean_source_extraction",
        "source_status": "uploaded_source",
        "source_gap_note": [],
        "provisional_scaffolds": [],
        "screen_material_suggestions": [],
        "teacher_talk_suggestions": [],
        "metadata_slots": {"raw_duration": duration_min},
        "teacher_review_required": True,
        "preview_only": True,
        "formal_apply": False,
        "provenance": {
            "parser_id": parser_id,
            "source_span": span,
            "source_text_excerpt": source_excerpt,
            "confidence": confidence,
            "selection_reason": "",
        },
    }


def _legacy_r103_parser(raw_text: str, file_name: str) -> list[dict[str, Any]]:
    session = r103.build_upload_session(raw_text, file_name)
    episodes = []
    cursor = 0
    for idx, item in enumerate(session.get("episodes") or [], start=1):
        if not isinstance(item, dict):
            continue
        normalized = deepcopy(item)
        normalized["index"] = idx
        normalized["title"] = _sanitize_title(item.get("title"), f"环节{idx}")
        normalized.setdefault("source_status", "uploaded_source")
        content = _clean(item.get("source_content") or item.get("goal") or item.get("teacher_action") or normalized["title"])
        span = _source_span(raw_text, content or normalized["title"], cursor)
        if span.get("start") is None:
            span = _source_span(raw_text, normalized["title"], cursor)
        if isinstance(span.get("end"), int):
            cursor = int(span["end"])
        normalized["source_content"] = content
        normalized["provenance"] = {
            "parser_id": "legacy_r103_parser",
            "source_span": span,
            "source_text_excerpt": _excerpt(raw_text, span, content or normalized["title"]),
            "confidence": 0.78 if span.get("start") is not None else 0.52,
            "selection_reason": "",
        }
        episodes.append(normalized)
    return episodes


def _numbered_colon_parser(raw_text: str, _file_name: str) -> list[dict[str, Any]]:
    process_text = _extract_process_text(raw_text)
    pattern = re.compile(
        r"(?:^|\n)\s*(\d+)[\.、]\s*([^\n:：。；;]{2,44}?)(?:\s+(\d+)\s*分钟)?\s*[:：]\s*(.*?)(?=\n\s*\d+[\.、]\s*[^\n:：。；;]{2,44}?(?:\s+\d+\s*分钟)?\s*[:：]|\Z)",
        flags=re.S,
    )
    episodes: list[dict[str, Any]] = []
    cursor = 0
    for match in pattern.finditer(process_text):
        index = int(match.group(1))
        duration = int(match.group(3)) if match.group(3) else None
        episode = _normalize_episode(
            raw_text=raw_text,
            parser_id="numbered_colon_parser",
            index=index,
            title=match.group(2),
            duration_min=duration,
            source_content=match.group(4),
            cursor=cursor,
        )
        end = episode["provenance"]["source_span"].get("end")
        if isinstance(end, int):
            cursor = end
        if episode.get("title") and episode.get("source_content"):
            episodes.append(episode)
    return episodes


def _numbered_sentence_parser(raw_text: str, _file_name: str) -> list[dict[str, Any]]:
    process_text = _extract_process_text(raw_text)
    pattern = re.compile(
        r"(?:^|\n)\s*(\d+)[\.．、]\s*(?!分钟\b)([^。\n]{4,80}。?)(?=\n\s*\d+[\.．、]\s*|\s*\Z)",
        flags=re.S,
    )
    episodes: list[dict[str, Any]] = []
    cursor = 0
    for match in pattern.finditer(process_text):
        index = int(match.group(1))
        sentence = _clean(match.group(2))
        if not sentence:
            continue
        episode = _normalize_episode(
            raw_text=raw_text,
            parser_id="numbered_sentence_parser",
            index=index,
            title=sentence,
            source_content=sentence,
            cursor=cursor,
        )
        end = episode["provenance"]["source_span"].get("end")
        if isinstance(end, int):
            cursor = end
        episodes.append(episode)
    return episodes


def _markdown_heading_parser(raw_text: str, _file_name: str) -> list[dict[str, Any]]:
    process_text = _extract_process_text(raw_text)
    pattern = re.compile(
        r"(?:^|\n)\s*(?:#{2,4}\s*|[一二三四五六七八九十]+[、.．])\s*([^\n]{2,36})\s*\n(.*?)(?=\n\s*(?:#{2,4}\s*|[一二三四五六七八九十]+[、.．])\s*[^\n]{2,36}\s*\n|\Z)",
        flags=re.S,
    )
    episodes = []
    cursor = 0
    for idx, match in enumerate(pattern.finditer(process_text), start=1):
        episode = _normalize_episode(
            raw_text=raw_text,
            parser_id="markdown_heading_parser",
            index=idx,
            title=match.group(1),
            source_content=match.group(2),
            cursor=cursor,
        )
        end = episode["provenance"]["source_span"].get("end")
        if isinstance(end, int):
            cursor = end
        if episode.get("source_content"):
            episodes.append(episode)
    return episodes


def _table_or_structured_parser(raw_text: str, _file_name: str) -> list[dict[str, Any]]:
    if "|" not in raw_text and "\t" not in raw_text:
        return []
    rows = [line for line in raw_text.splitlines() if "|" in line or "\t" in line]
    episodes = []
    for idx, row in enumerate(rows, start=1):
        cells = [_clean(cell) for cell in re.split(r"\||\t", row) if _clean(cell)]
        if len(cells) < 2 or re.fullmatch(r"[-:：\s]+", "".join(cells)):
            continue
        first = cells[0].strip("* ")
        second = cells[1].strip("* ") if len(cells) > 1 else ""
        metadata_titles = {
            "字段名",
            "所属大单元",
            "所属子课时",
            "教学的步骤",
            "步骤顺序",
            "步骤名称",
            "步骤时长",
            "步骤目标",
            "教师话术",
            "学生任务",
            "材料需求",
            "技术支持",
            "成功标准",
            "引导问题",
            "反馈要点",
            "备注",
            "人员",
            "步骤",
            "教学环节",
        }
        if first in metadata_titles or first.startswith("**"):
            continue
        if len(cells) < 3 and not any(term in "".join(cells) for term in ["教师", "学生", "活动", "过程", "环节"]):
            continue
        step_match = re.match(r"^步骤\s*\d+\s+(.+)$", first)
        if step_match:
            title = step_match.group(1)
        elif re.fullmatch(r"\d+", first) and second:
            title = second
        else:
            title = first
        clean_title = _sanitize_title(title, "")
        if (
            not clean_title
            or clean_title in metadata_titles
            or re.fullmatch(r"\d+", clean_title)
            or re.fullmatch(r"第[一二三四五六七八九十\d]+单元", clean_title)
        ):
            continue
        content = _naturalize_table_row(cells)
        episodes.append(
            _normalize_episode(
                raw_text=raw_text,
                parser_id="table_or_structured_parser",
                index=idx,
                title=clean_title,
                source_content=content,
                span_needle=row,
            )
        )
    return episodes


def _long_section_parser(raw_text: str, _file_name: str) -> list[dict[str, Any]]:
    process_text = _extract_process_text(raw_text)
    chunks = [_clean(chunk) for chunk in re.split(r"\n\s*\n|(?<=。)\s*(?=教师|学生|随后|接着|最后)", process_text) if _clean(chunk)]
    if len(chunks) < 2:
        return []
    episodes = []
    for idx, chunk in enumerate(chunks[:8], start=1):
        title = re.split(r"[:：。；;]", chunk)[0][:20] or f"长段落环节{idx}"
        episodes.append(
            _normalize_episode(
                raw_text=raw_text,
                parser_id="long_section_parser",
                index=idx,
                title=title,
                source_content=chunk,
            )
        )
    return episodes


PARSERS = {
    "legacy_r103_parser": _legacy_r103_parser,
    "numbered_colon_parser": _numbered_colon_parser,
    "numbered_sentence_parser": _numbered_sentence_parser,
    "markdown_heading_parser": _markdown_heading_parser,
    "table_or_structured_parser": _table_or_structured_parser,
    "long_section_parser": _long_section_parser,
}


def _metadata_pollution_count(episodes: list[dict[str, Any]]) -> int:
    count = 0
    metadata_titles = {
        "字段名",
        "所属大单元",
        "所属子课时",
        "教学的步骤",
        "步骤顺序",
        "步骤名称",
        "步骤时长",
        "步骤目标",
        "教师话术",
        "学生任务",
        "材料需求",
        "技术支持",
        "成功标准",
        "引导问题",
        "反馈要点",
        "备注",
        "人员",
        "步骤",
        "教学环节",
    }
    for episode in episodes:
        title = _clean(episode.get("title")).strip("* ")
        if (
            len(title) > 28
            or re.search(r"\d+\s*分钟", title)
            or any(mark in title for mark in ["：", ":", "。", "；"])
            or title in metadata_titles
            or re.fullmatch(r"\d+", title)
            or re.fullmatch(r"第[一二三四五六七八九十\d]+单元", title)
        ):
            count += 1
    return count


def _source_span_coverage(raw_text: str, episodes: list[dict[str, Any]]) -> float:
    spans = []
    for episode in episodes:
        span = ((episode.get("provenance") or {}).get("source_span") or {})
        start, end = span.get("start"), span.get("end")
        if isinstance(start, int) and isinstance(end, int) and end > start:
            spans.append((start, end))
    if not spans or not raw_text:
        return 0.0
    spans.sort()
    merged: list[tuple[int, int]] = []
    for start, end in spans:
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    covered = sum(end - start for start, end in merged)
    return round(min(1.0, covered / max(1, len(raw_text))), 4)


def _preservation_score(raw_text: str, episodes: list[dict[str, Any]]) -> float:
    expected_terms = [term for term in ["展示", "发布会", "评价", "作业", "故事", "小结"] if term in raw_text]
    if not expected_terms:
        return 0.75
    text = "\n".join(_clean(ep.get("title")) + "\n" + _clean(ep.get("source_content")) for ep in episodes)
    kept = sum(1 for term in expected_terms if term in text)
    return round(kept / len(expected_terms), 4)


def _candidate(raw_text: str, parser_id: str, episodes: list[dict[str, Any]]) -> dict[str, Any]:
    episode_count = len(episodes)
    episode_titles = [_clean(item.get("title")) for item in episodes]
    empty_count = sum(1 for item in episodes if not _clean(item.get("source_content")))
    metadata_count = _metadata_pollution_count(episodes)
    title_cleanliness = 0.0 if not episodes else round((episode_count - metadata_count) / episode_count, 4)
    evidence_coverage = 0.0 if not episodes else round(
        sum(1 for item in episodes if _clean(item.get("source_content")) and ((item.get("provenance") or {}).get("source_span") or {}).get("start") is not None)
        / episode_count,
        4,
    )
    count_score = 0.0 if episode_count == 0 else max(0.2, 1.0 - abs(episode_count - 5) * 0.12)
    if episode_count > 12:
        count_score = 0.1
    span_coverage = _source_span_coverage(raw_text, episodes)
    preserve = _preservation_score(raw_text, episodes)
    score = (
        count_score * 0.18
        + title_cleanliness * 0.2
        + evidence_coverage * 0.2
        + min(1.0, span_coverage * 3.0) * 0.18
        + preserve * 0.14
        - metadata_count * 0.08
        - empty_count * 0.12
    )
    if episode_count == 0:
        score = 0.0
    failure = ""
    if episode_count == 0:
        failure = "parser_returned_zero_episode"
    elif empty_count:
        failure = "parser_returned_empty_episode"
    elif metadata_count:
        failure = "episode_title_metadata_pollution"
    return {
        "parser_id": parser_id,
        "episode_count": episode_count,
        "episode_titles": episode_titles,
        "source_span_coverage": span_coverage,
        "evidence_coverage_score": evidence_coverage,
        "title_cleanliness_score": title_cleanliness,
        "metadata_pollution_count": metadata_count,
        "empty_episode_count": empty_count,
        "preservation_score": preserve,
        "selection_score": round(max(0.0, min(1.0, score)), 4),
        "failure_reason_if_rejected": failure,
        "episodes": episodes,
    }


def build_source_extraction_orchestrator_contract() -> dict[str, Any]:
    return {
        "stage": STAGE_ID,
        "contract_name": "SourceExtractionOrchestrator",
        "version": "r201c_v0.1",
        "input": ["raw_text", "file_name"],
        "candidate_parsers": list(PARSERS.keys()),
        "selection_policy": {
            "not_episode_count_only": True,
            "score_dimensions": [
                "reasonable_episode_count",
                "title_cleanliness",
                "source_span_coverage",
                "evidence_coverage",
                "preserves_display_homework_evaluation_episode",
                "metadata_pollution_count",
                "empty_episode_count",
            ],
            "low_confidence_policy": "return source_gap and teacher_confirmation_needed; do not synthesize full process",
        },
        "episode_provenance_required": [
            "parser_id",
            "source_span",
            "source_text_excerpt",
            "confidence",
            "selection_reason",
        ],
        "boundary": {
            "readonly_only": True,
            "formal_apply": False,
            "database_written": False,
            "feishu_written": False,
            "memory_written": False,
            "provider_called": False,
            "model_called": False,
            "R95_executed": False,
        },
    }


def orchestrate_source_extraction(raw_text: str, file_name: str = "") -> dict[str, Any]:
    raw_sha = hashlib.sha256(raw_text.encode("utf-8")).hexdigest().upper()
    candidates = []
    for parser_id, parser in PARSERS.items():
        try:
            episodes = parser(raw_text, file_name)
            candidates.append(_candidate(raw_text, parser_id, episodes))
        except Exception as exc:  # pragma: no cover - diagnostics path.
            candidates.append(
                {
                    "parser_id": parser_id,
                    "episode_count": 0,
                    "episode_titles": [],
                    "source_span_coverage": 0.0,
                    "evidence_coverage_score": 0.0,
                    "title_cleanliness_score": 0.0,
                    "metadata_pollution_count": 0,
                    "empty_episode_count": 0,
                    "preservation_score": 0.0,
                    "selection_score": 0.0,
                    "failure_reason_if_rejected": f"parser_exception:{type(exc).__name__}",
                    "episodes": [],
                }
            )
    selected = max(candidates, key=lambda item: item.get("selection_score", 0.0)) if candidates else None
    legacy = next((item for item in candidates if item.get("parser_id") == "legacy_r103_parser"), None)
    table = next((item for item in candidates if item.get("parser_id") == "table_or_structured_parser"), None)
    if selected is table and isinstance(legacy, dict) and isinstance(table, dict):
        legacy_titles = [_clean(title) for title in legacy.get("episode_titles") or []]
        table_titles = [_clean(title) for title in table.get("episode_titles") or []]
        if (
            legacy_titles
            and legacy_titles == table_titles
            and float(legacy.get("selection_score") or 0.0) >= 0.7
            and float(table.get("selection_score") or 0.0) - float(legacy.get("selection_score") or 0.0) < 0.12
        ):
            selected = legacy
    confidence = float((selected or {}).get("selection_score") or 0.0)
    selected_parser_id = str((selected or {}).get("parser_id") or "")
    selection_reason = (
        f"selected_by_multimetric_score:{confidence:.4f}; "
        "episode_count/title_cleanliness/source_span/evidence/preservation all considered"
    )
    for candidate in candidates:
        if candidate is selected:
            candidate["failure_reason_if_rejected"] = ""
        elif not candidate.get("failure_reason_if_rejected"):
            candidate["failure_reason_if_rejected"] = (
                f"lower_selection_score_than_{selected_parser_id}:{candidate.get('selection_score')}<{confidence:.4f}"
            )
    episodes = deepcopy((selected or {}).get("episodes") or [])
    low_confidence = confidence < 0.35 or not episodes
    for episode in episodes:
        provenance = episode.setdefault("provenance", {})
        provenance["selection_reason"] = selection_reason
        provenance["confidence"] = min(1.0, float(provenance.get("confidence") or confidence))
    return {
        "stage": STAGE_ID,
        "orchestrator_called": True,
        "raw_sha256": raw_sha,
        "file_name": file_name,
        "selected_parser_id": "" if low_confidence else selected_parser_id,
        "selection_reason": "" if low_confidence else selection_reason,
        "confidence": confidence,
        "low_confidence": low_confidence,
        "teacher_confirmation_needed": low_confidence,
        "source_gap": {
            "active": low_confidence,
            "reason": "all_parser_candidates_low_confidence_or_empty" if low_confidence else "",
            "display_policy": "status_only_not_teacher_main_content",
        },
        "parser_candidates": [
            {key: value for key, value in candidate.items() if key != "episodes"}
            for candidate in candidates
        ],
        "episodes": [] if low_confidence else episodes,
        "episode_count": 0 if low_confidence else len(episodes),
        "episode_titles": [] if low_confidence else [_clean(item.get("title")) for item in episodes],
        "boundary": {
            "readonly_only": True,
            "model_called": False,
            "provider_called": False,
            "formal_apply": False,
            "database_written": False,
            "feishu_written": False,
            "memory_written": False,
            "R95_executed": False,
        },
    }


def _strip_wrapping_title(title: str) -> str:
    text = _clean(title).replace("课题：", "").replace("年级：", "").replace("单元：", "")
    if text.startswith("《") and text.endswith("》"):
        text = text[1:-1]
    return _clean(text)


def _field_items(field_projection: dict[str, Any], section_id: str, source_corpus: str) -> list[str]:
    candidates = field_projection.get("field_candidates") if isinstance(field_projection.get("field_candidates"), dict) else {}
    candidate = candidates.get(section_id) if isinstance(candidates.get(section_id), dict) else {}
    items = candidate.get("items")
    if isinstance(items, list):
        out = []
        for item in items:
            text = _sanitize_teacher_visible_text(item)
            if text and not _is_generic_front_matter(text) and not _is_off_topic_for_source(text, source_corpus):
                out.append(text)
        return out
    return []


def _template_section(field_projection: dict[str, Any], section_id: str, title: str, source_corpus: str) -> list[dict[str, Any]]:
    candidates = field_projection.get("field_candidates") if isinstance(field_projection.get("field_candidates"), dict) else {}
    candidate = candidates.get(section_id) if isinstance(candidates.get(section_id), dict) else {}
    body = _field_items(field_projection, section_id, source_corpus)
    if not body:
        body = ["上传原文未明确提供，需教师补充。"]
    return [
        {
            "section_id": section_id,
            "title": title,
            "body": body,
            "source_status": "R114_field_projection",
            "teacher_visible_source_label": _teacher_visible_source_label("R114_field_projection"),
            "projection_basis": {
                "classification": candidate.get("classification") or "R114_field_projection",
                "source_capsules": candidate.get("source_capsules") or [],
                "graph_basis": candidate.get("graph_basis") or [],
                "teacher_review_required": bool(candidate.get("teacher_review_required", True)),
            },
            "teacher_review_required": True,
            "preview_only": True,
        }
    ]


def _evidence_text(items: Any) -> list[str]:
    out = []
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                text = _sanitize_teacher_visible_text(item.get("evidence") or item.get("proves"))
            else:
                text = _sanitize_teacher_visible_text(item)
            if text:
                out.append(text)
    return out


def _source_episode_corpus(source_episode: dict[str, Any]) -> str:
    return "\n".join(
        _clean(source_episode.get(key))
        for key in ["title", "goal", "teacher_action", "student_action", "source_content", "evidence", "question", "feedback"]
        if _clean(source_episode.get(key))
    )


def _trusted_item_text(item: dict[str, Any], source_episode: dict[str, Any], item_key: str, source_key: str, fallback: str = "") -> str:
    source_corpus = _source_episode_corpus(source_episode)
    item_text = _sanitize_teacher_visible_text(item.get(item_key))
    source_text = _sanitize_teacher_visible_text(source_episode.get(source_key))
    if _is_off_topic_for_source(item_text, source_corpus) and source_text:
        return source_text
    if item_text:
        return item_text
    return source_text or fallback


def _trusted_support_text(item: dict[str, Any], source_episode: dict[str, Any], item_key: str, fallback: str) -> str:
    source_corpus = _source_episode_corpus(source_episode)
    item_text = _sanitize_teacher_visible_text(item.get(item_key))
    if _is_off_topic_for_source(item_text, source_corpus):
        return fallback
    return item_text or fallback


def _episode_goal_from_item(item: dict[str, Any], title: str, source_episode: dict[str, Any], student_action: str) -> str:
    student_action = _sanitize_teacher_visible_text(student_action)
    source_corpus = _source_episode_corpus(source_episode)
    if _is_off_topic_for_source(student_action, source_corpus):
        student_action = _sanitize_teacher_visible_text(source_episode.get("student_action"))
    evidence = _evidence_text(item.get("evidence_to_watch"))
    if evidence and any(_is_off_topic_for_source(text, source_corpus) for text in evidence):
        evidence = []
    source_evidence = _sanitize_teacher_visible_text(source_episode.get("evidence"))
    source_content = _sanitize_teacher_visible_text(source_episode.get("source_content"))
    if student_action:
        return f"学生能{student_action.rstrip('。')}"
    if evidence:
        return f"学生能用课堂证据说明：{evidence[0].rstrip('。')}"
    if source_evidence:
        return f"学生能达到原文评价证据：{source_evidence.rstrip('。')}"
    if source_content:
        return f"学生能完成“{title}”中的观察、尝试或表达任务"
    return f"学生能在“{title}”环节形成可观察的学习成果"


def _process_episodes(field_projection: dict[str, Any], selected_episodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    process = field_projection.get("process_projection") if isinstance(field_projection.get("process_projection"), dict) else {}
    items = process.get("items") if isinstance(process.get("items"), list) else []
    episodes = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        source_episode = selected_episodes[index] if index < len(selected_episodes) else {}
        provenance = source_episode.get("provenance") if isinstance(source_episode.get("provenance"), dict) else {}
        title = _sanitize_title(item.get("title") or source_episode.get("title"), f"环节{index + 1}")
        evidence = _evidence_text(item.get("evidence_to_watch"))
        source_corpus = _source_episode_corpus(source_episode)
        if evidence and any(_is_off_topic_for_source(text, source_corpus) for text in evidence):
            evidence = []
        source_evidence = _sanitize_teacher_visible_text(source_episode.get("evidence"))
        teacher_move = _trusted_item_text(item, source_episode, "teacher_move", "teacher_action")
        student_action = _trusted_item_text(item, source_episode, "student_action", "student_action")
        likely_stuck = _trusted_support_text(item, source_episode, "likely_stuck_point", "需教师根据学生现场表现确认支架。")
        xiaojiao_support = _trusted_support_text(item, source_episode, "xiaojiao_support", "小教只提示教师追问原文任务，不替学生生成答案。")
        episode_goal = _episode_goal_from_item(item, title, source_episode, student_action)
        micro = {
            "step_id": f"{item.get('step_id') or f'TEACHER_EXEC_{index + 1:02d}'}-M01",
            "step_name": title,
            "teacher_action": teacher_move,
            "student_action": student_action,
            "screen_or_materials": "",
            "scaffolds": likely_stuck,
            "evidence": evidence[0] if evidence else (source_evidence or _sanitize_teacher_visible_text(source_episode.get("source_content"))),
            "source_status": "R114_execution_map",
            "teacher_visible_source_label": _teacher_visible_source_label("R114_execution_map"),
            "source_extraction_provenance": provenance,
            "teacher_review_required": bool(item.get("teacher_review_required", True)),
            "preview_only": True,
        }
        episodes.append(
            {
                "route": "uploaded_lesson_entry_preview_lean",
                "episode_id": item.get("step_id") or f"TEACHER_EXEC_{index + 1:02d}",
                "episode_index": index + 1,
                "episode_title": title,
                "episode_goal": episode_goal,
                "teacher_organization": [teacher_move] if teacher_move else [],
                "student_learning": student_action,
                "key_teacher_talk": "",
                "xiaojiao_hint": xiaojiao_support,
                "micro_steps": [micro],
                "evidence": evidence,
                "source_status": "R114_execution_map",
                "teacher_visible_source_label": _teacher_visible_source_label("R114_execution_map"),
                "source_extraction_provenance": provenance,
                "teacher_review_required": bool(item.get("teacher_review_required", True)),
                "preview_only": True,
            }
        )
    return episodes


def _raw_assessment_sections(raw_text: str) -> list[dict[str, Any]]:
    items = []
    for label in ["评价证据", "评价方式", "作业"]:
        match = re.search(rf"{label}[:：]\s*([^\n]+)", raw_text)
        if not match:
            continue
        body = _sanitize_teacher_visible_text(match.group(1))
        if body:
            items.append(
                {
                    "section_id": "assessment_raw_source",
                    "title": f"七、{label}",
                    "body": [f"{label}：{body}"],
                    "source_status": "uploaded_source",
                    "teacher_visible_source_label": _teacher_visible_source_label("uploaded_source"),
                    "projection_basis": {
                        "classification": "uploaded_source",
                        "source_capsules": [label],
                        "graph_basis": [],
                        "teacher_review_required": True,
                    },
                    "teacher_review_required": True,
                    "preview_only": True,
                }
            )
    return items


def _build_single_lesson_template(
    *,
    session: dict[str, Any],
    selected_extraction: dict[str, Any],
    graph_preview: dict[str, Any],
    projection_preview: dict[str, Any],
) -> dict[str, Any]:
    graph = graph_preview.get("graph") if isinstance(graph_preview.get("graph"), dict) else {}
    identity = graph.get("lesson_identity") if isinstance(graph.get("lesson_identity"), dict) else {}
    field_projection = projection_preview.get("field_projection") if isinstance(projection_preview.get("field_projection"), dict) else {}

    def claim_text(key: str, default: str = "") -> str:
        claim = identity.get(key) if isinstance(identity.get(key), dict) else {}
        text = _strip_wrapping_title(str(claim.get("text") or default))
        if text == "上传教案单元待确认":
            return "单元待确认"
        return text

    selected_episodes = selected_extraction.get("episodes") if isinstance(selected_extraction.get("episodes"), list) else []
    source_corpus = "\n".join(_source_episode_corpus(ep) for ep in selected_episodes)
    assessment_sections = _template_section(field_projection, "assessment", "七、学习单与评价", source_corpus)
    assessment_sections.extend(_raw_assessment_sections(str(session.get("raw_text") or "")))
    return {
        "stage": STAGE_ID,
        "template_id": f"r201c_lean_readonly::{session.get('session_id')}",
        "template_type": "single_lesson_template",
        "route": "uploaded_lesson_entry_preview_lean",
        "lesson_header": {
            "lesson_title": claim_text("title", (session.get("meta") or {}).get("title") or ""),
            "unit_title": claim_text("unit", (session.get("meta") or {}).get("unit") or "单元待确认"),
            "grade": claim_text("grade", (session.get("meta") or {}).get("grade") or "年级待确认"),
            "lesson_code": session.get("file_name") or session.get("session_id"),
            "status": "lean readonly preview only",
            "source_status": "uploaded_source",
            "teacher_visible_source_label": _teacher_visible_source_label("uploaded_source"),
        },
        "basis": _template_section(field_projection, "basis", "一、本课依据", source_corpus),
        "student_analysis": _template_section(field_projection, "analysis", "二、学情分析", source_corpus),
        "objectives": _template_section(field_projection, "goals", "三、教学目标", source_corpus),
        "key_difficult_points": _template_section(field_projection, "keypoints", "四、教学重难点", source_corpus),
        "preparation": _template_section(field_projection, "preparation", "五、教学准备", source_corpus),
        "process_episodes": _process_episodes(field_projection, selected_episodes),
        "assessment_or_homework": assessment_sections,
        "reflection_or_notes": _template_section(field_projection, "reflection", "八、课堂后记", source_corpus),
        "source_extraction": {
            "selected_parser_id": selected_extraction.get("selected_parser_id"),
            "selection_reason": selected_extraction.get("selection_reason"),
            "confidence": selected_extraction.get("confidence"),
            "episode_titles": selected_extraction.get("episode_titles") or [],
        },
        "candidate_patches": [],
        "renderer_policy": {
            "backend_provides_template_object": True,
            "frontend_renders_only": True,
            "renderer_must_not_infer_pedagogy": True,
            "source_gap_as_status_not_content": True,
        },
        "boundary": {
            "readonly_only": True,
            "preview_only": True,
            "model_called": False,
            "provider_called": False,
            "formal_apply": False,
            "database_written": False,
            "feishu_written": False,
            "memory_written": False,
            "R95_executed": False,
            "R200A_used_for_teacher_main": False,
            "R200B_used_for_teacher_main": False,
            "R97B_P3_used_for_teacher_main": False,
        },
    }


def _items(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_clean(item) for item in value if _clean(item)]
    text = _clean(value)
    return [text] if text else []


def teacher_main_entries(template: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []

    def add(path: str, text: Any, source: str, role: str) -> None:
        for item in _items(text):
            entries.append({"path": path, "text": item, "source_type": source or "unknown", "role": role})

    header = template.get("lesson_header") or {}
    add("lesson_header.lesson_title", header.get("lesson_title"), header.get("source_status") or "uploaded_source", "header")
    for section_key in ["basis", "student_analysis", "objectives", "key_difficult_points", "preparation", "assessment_or_homework", "reflection_or_notes"]:
        for sidx, section in enumerate(template.get(section_key) or []):
            if not isinstance(section, dict):
                continue
            for bidx, body in enumerate(_items(section.get("body"))):
                add(f"{section_key}[{sidx}].body[{bidx}]", body, section.get("source_status") or "unknown", section_key)
    for eidx, episode in enumerate(template.get("process_episodes") or []):
        if not isinstance(episode, dict):
            continue
        source = episode.get("source_status") or "unknown"
        for key in ["episode_title", "episode_goal", "teacher_organization", "student_learning", "key_teacher_talk", "xiaojiao_hint", "evidence"]:
            add(f"process_episodes[{eidx}].{key}", episode.get(key), source, f"episode.{key}")
        for midx, micro in enumerate(episode.get("micro_steps") or []):
            if not isinstance(micro, dict):
                continue
            for key in ["step_name", "teacher_action", "student_action", "screen_or_materials", "scaffolds", "evidence"]:
                add(f"process_episodes[{eidx}].micro_steps[{midx}].{key}", micro.get(key), micro.get("source_status") or source, f"micro.{key}")
    return entries


def build_ownership_ledger(template: dict[str, Any]) -> dict[str, Any]:
    entries = teacher_main_entries(template)
    counts: dict[str, int] = {}
    for entry in entries:
        source = str(entry.get("source_type") or "unknown")
        counts[source] = counts.get(source, 0) + 1
    return {
        "stage": STAGE_ID,
        "teacher_main_entry_count": len(entries),
        "teacher_main_source_counts": dict(sorted(counts.items())),
        "forbidden_source_hits": [
            entry for entry in entries if entry.get("source_type") in FORBIDDEN_MAIN_SOURCES or entry.get("source_type") not in ALLOWED_MAIN_SOURCES
        ],
        "source_gap_as_content_hits": [entry for entry in entries if entry.get("source_type") == "source_gap"],
        "entries": entries,
    }


def build_lean_readonly_viewmodel_from_raw_text(raw_text: str, file_name: str = "") -> dict[str, Any]:
    base_session = r103.build_upload_session(raw_text, file_name)
    selected_extraction = orchestrate_source_extraction(raw_text, file_name)
    session = deepcopy(base_session)
    session["r201c_source_extraction_orchestrator"] = selected_extraction
    if not selected_extraction.get("low_confidence"):
        session["episodes"] = deepcopy(selected_extraction.get("episodes") or [])
        session["fields"] = r103.build_fields(raw_text, session.get("meta") or {}, session["episodes"])
    r112_preview = r112.build_import_lesson_understanding_preview(session, enable_model=False)
    graph_preview = r114a.build_import_understanding_v2_graph_preview(session, r112_preview=r112_preview, enable_model=False)
    execution_preview = r114b.build_teacher_execution_map_preview(graph_preview, enable_model=False)
    projection_preview = r114c.build_graph_field_projection_preview(graph_preview, execution_preview, enable_model=False)
    single_lesson_template = _build_single_lesson_template(
        session=session,
        selected_extraction=selected_extraction,
        graph_preview=graph_preview,
        projection_preview=projection_preview,
    )
    ownership_ledger = build_ownership_ledger(single_lesson_template)
    steps = readonly_preview.build_process_steps(session.get("episodes") or [])
    context = r103.sample_context_from_meta(session["session_id"], session.get("meta") or {})
    return {
        "ok": True,
        "stage": STAGE_ID,
        "viewmodel_type": "prep_room_real_upload_entry_preview_lean",
        "viewmodel_id": session["session_id"],
        "generated_at": _now(),
        "upload_session": {
            "session_id": session["session_id"],
            "raw_sha256": session["raw_sha256"],
            "file_name": file_name,
            "raw_preserved": True,
            "raw_excerpt": session.get("raw_excerpt"),
            "persisted": False,
            "teacher_original_overwritten": False,
        },
        "source_round": "R201C lean readonly route from request payload",
        "render_contract": {
            "target_shell": "existing_prep_room_shell",
            "target_state": "uploaded_lesson_entry_preview_lean",
            "target_slot": "prep_notebook.current_lesson",
            "single_lesson_template_slot": "single_lesson_template",
            "renderer_must_not": ["infer_pedagogy", "write_database_or_memory", "formal_apply"],
        },
        "source_extraction_orchestrator": {
            key: value for key, value in selected_extraction.items() if key != "episodes"
        },
        "selected_source_extraction": selected_extraction,
        "import_lesson_understanding_preview": r112_preview,
        "import_understanding_v2_graph_preview": graph_preview,
        "import_teacher_execution_map_preview": execution_preview,
        "import_graph_field_projection_preview": projection_preview,
        "single_lesson_template": single_lesson_template,
        "ownership_ledger": ownership_ledger,
        "prep_view_patch": {
            "active_view": "prepNotebook",
            "active_node_id": context["node_id"],
            "unit_title": context["unit_title"],
            "lesson_tree": context["tree"],
            "current_lesson": {
                "id": context["node_id"],
                "title": single_lesson_template["lesson_header"]["lesson_title"],
                "lesson_title": single_lesson_template["lesson_header"]["lesson_title"],
                "eyebrow": single_lesson_template["lesson_header"]["unit_title"],
                "grade": single_lesson_template["lesson_header"]["grade"],
                "term": "真实上传入口 lean 只读预览",
                "status": "lean preview only",
                "badges": ["R201C lean chain", "临时 session", "只读渲染", "不保存"],
                "sections": [],
                "process_steps": steps,
                "single_lesson_template": single_lesson_template,
            },
            "single_lesson_template": single_lesson_template,
        },
        "courseware_screen_patch": readonly_preview.build_courseware_screens(steps),
        "right_rail_patch": {
            "mode": "uploaded_lesson_entry_preview_lean",
            "screen_ids": [f"U{i:02d}" for i in range(1, len(steps) + 1)],
            "session_id": session["session_id"],
            "must_not_show": ["R200A_kernel", "R200B_candidate", "R97B_P3_derivation_spine"],
        },
        "boundary": {
            "readonly_only": True,
            "preview_only": True,
            "real_R103_parser_deleted": False,
            "formal_apply": False,
            "database_written": False,
            "feishu_written": False,
            "memory_written": False,
            "pptx_pdf_docx_generated": False,
            "R21_modified": False,
            "R36_modified": False,
            "R95_executed": False,
            "provider_called": False,
            "model_called": False,
            "R200A_used_for_teacher_main": False,
            "R200B_used_for_teacher_main": False,
            "R97B_P3_used_for_teacher_main": False,
        },
        "runtime_actions": readonly_preview.runtime_actions(),
        "teacher_review_required": True,
        "formal_apply": False,
    }


def handle_upload_entry_preview_lean(payload: Any) -> tuple[dict[str, Any], int]:
    if not isinstance(payload, dict):
        payload = {}
    raw_text = str(payload.get("raw_text") or payload.get("text") or "").strip()
    if not raw_text:
        return {
            "ok": False,
            "stage": STAGE_ID,
            "error_code": "UPLOAD_PREVIEW_RAW_TEXT_REQUIRED",
            "teacher_visible_message": "请先粘贴一份教案原文，再进入 lean 只读预览。",
            "boundary": {"readonly_only": True, "formal_apply": False},
        }, 400
    return build_lean_readonly_viewmodel_from_raw_text(raw_text, str(payload.get("file_name") or "")), 200
