# R201F Fallback And Rollback Policy

Lean preview must fall back to legacy or fail closed when source extraction is unsafe.

Fallback reasons include:

- `lean_source_extraction_low_confidence`
- `lean_selected_extraction_empty`
- `lean_single_lesson_template_empty`
- `lean_teacher_main_forbidden_source`
- `lean_source_gap_as_content`
- `lean_route_exception:<type>`

Rollback is immediate: set `XIAOBEI_UPLOAD_PREVIEW_DEFAULT_ENGINE=legacy` or send `preview_engine=legacy`.

Fallback does not grant R200A/R200B/R97B_P3 teacher-main ownership.
