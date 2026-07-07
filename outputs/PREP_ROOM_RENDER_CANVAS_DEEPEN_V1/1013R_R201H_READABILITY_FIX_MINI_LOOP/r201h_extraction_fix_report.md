# R201H Extraction Fix Report

The R201H extraction-side change keeps table teacher text naturalized while preserving source spans against the original raw table row.

- table_rain_umbrella selected_parser: `table_or_structured_parser`
- table_rain_umbrella every_episode_has_source_span: `True`
- table_rain_umbrella downstream_showcase_or_homework_not_swallowed: `True`
- real_qinglv_docx selected_parser after regression: `table_or_structured_parser`

The toy `minimal_line_fish` fixture is no longer used as the R201G teacher readability sample. R201G now uses a formal local lesson: `kb_art_g4_lesson_case_1_132144fe0b_课时1_下雨啰_教案.docx`.
