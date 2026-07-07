from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


STAGE_ID = "1013R_R107A_MARKITDOWN_DOCUMENT_TEXT_EXTRACTOR"
SUPPORTED_TEXT_EXTENSIONS = {".txt", ".md"}
SUPPORTED_MARKITDOWN_EXTENSIONS = {".docx", ".pdf"}
METADATA_ONLY_EXTENSIONS = {".doc"}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _read_text_file(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _normalize_text(text: str) -> str:
    lines = [line.rstrip() for line in str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return "\n".join(lines).strip()


def _looks_garbled(text: str) -> bool:
    compact = "".join(ch for ch in str(text or "") if not ch.isspace())
    if len(compact) < 20:
        return False
    question_ratio = compact.count("?") / max(len(compact), 1)
    return question_ratio > 0.25


def boundary_flags() -> dict[str, bool]:
    return {
        "stage": STAGE_ID,
        "readonly_text_extraction": True,
        "provider_called": False,
        "model_called": False,
        "ocr_model_called": False,
        "database_written": False,
        "feishu_written": False,
        "memory_written": False,
        "formal_apply_performed": False,
        "teacher_original_overwritten": False,
        "R21_modified": False,
        "R36_modified": False,
    }


def extract_document_text(
    file_path: str | Path,
    *,
    original_filename: str = "",
    enable_model_ocr: bool = False,
) -> dict[str, Any]:
    """Extract readable lesson text for readonly upload-preview.

    MarkItDown is the primary adapter for DOCX/PDF. Text and Markdown files are
    read directly so the import path stays usable if MarkItDown is unavailable.
    Scanned PDF OCR is intentionally not automatic in this stage; the caller gets
    a clear NEEDS_OCR_MODEL status instead of a fake success.
    """

    path = Path(file_path)
    ext = path.suffix.lower()
    display_name = original_filename or path.name
    result: dict[str, Any] = {
        "ok": False,
        "stage": STAGE_ID,
        "file_name": display_name,
        "extension": ext,
        "parser": None,
        "status": "ERROR",
        "text": "",
        "text_length": 0,
        "warnings": [],
        "teacher_visible_message": "",
        "boundary": boundary_flags(),
    }
    if not path.exists() or not path.is_file():
        result.update(
            {
                "status": "FILE_NOT_FOUND",
                "teacher_visible_message": "未找到上传文件，无法进入只读解析预览。",
            }
        )
        return result

    data = path.read_bytes()
    result["file_sha256"] = _sha256_bytes(data)
    result["file_size_bytes"] = len(data)

    if ext in METADATA_ONLY_EXTENSIONS:
        result.update(
            {
                "status": "UNSUPPORTED_LEGACY_DOC",
                "parser": "metadata_only",
                "teacher_visible_message": "旧版 .doc 暂不直接解析，请先另存为 .docx 后再上传。",
            }
        )
        return result

    try:
        if ext in SUPPORTED_TEXT_EXTENSIONS:
            text = _normalize_text(_read_text_file(path))
            result.update(
                {
                    "ok": bool(text),
                    "status": "PASS" if text else "EMPTY_TEXT",
                    "parser": "direct_text_reader",
                    "text": text,
                    "text_length": len(text),
                    "teacher_visible_message": "文本已读取，可生成只读字段预览。" if text else "文本为空，请检查文件内容。",
                }
            )
            return result

        if ext in SUPPORTED_MARKITDOWN_EXTENSIONS:
            try:
                from markitdown import MarkItDown
            except Exception as exc:  # pragma: no cover - environment guard
                result.update(
                    {
                        "status": "MARKITDOWN_NOT_AVAILABLE",
                        "parser": "markitdown",
                        "teacher_visible_message": "MarkItDown 未安装或不可用，暂不能解析 Word/PDF。",
                        "error": str(exc),
                    }
                )
                return result

            converter = MarkItDown()
            converted = converter.convert(path)
            text = _normalize_text(
                getattr(converted, "text_content", "")
                or getattr(converted, "markdown", "")
                or str(converted)
            )
            if ext == ".pdf" and _looks_garbled(text):
                result.update(
                    {
                        "status": "PDF_TEXT_GARBLED_NEEDS_OCR",
                        "parser": "markitdown",
                        "text": "",
                        "text_length": 0,
                        "warnings": ["PDF text layer was extracted as garbled text; OCR/model fallback is required."],
                        "teacher_visible_message": "PDF 文本层解析成乱码，需 OCR/模型识别后再生成字段预览。",
                    }
                )
                return result
            if ext == ".pdf" and len(text) < 80:
                result.update(
                    {
                        "status": "NEEDS_OCR_MODEL" if enable_model_ocr else "PDF_TEXT_TOO_SPARSE",
                        "parser": "markitdown",
                        "text": text,
                        "text_length": len(text),
                        "teacher_visible_message": (
                            "PDF 文本过少，可能是扫描件；需要 OCR/模型识别后再解析。"
                        ),
                    }
                )
                return result
            result.update(
                {
                    "ok": bool(text),
                    "status": "PASS" if text else "EMPTY_TEXT",
                    "parser": "markitdown",
                    "text": text,
                    "text_length": len(text),
                    "teacher_visible_message": "文档已解析，可生成只读字段预览。" if text else "文档未抽出正文，请检查文件。",
                }
            )
            return result

        result.update(
            {
                "status": "UNSUPPORTED_EXTENSION",
                "parser": "none",
                "teacher_visible_message": f"暂不支持 {ext or '未知格式'}，请上传 docx/pdf/txt/md。",
            }
        )
        return result
    except Exception as exc:
        result.update(
            {
                "status": "EXTRACT_ERROR",
                "teacher_visible_message": "文档解析失败，请改用粘贴正文或换一个文件重试。",
                "error": str(exc),
            }
        )
        return result
