# Shiwei R201H-P1 Teacher Main Cleanup Review

This review package is for GPT/external audit of:

```text
1013R_R201H_P1_TEACHER_MAIN_CLEANUP_AND_MINIMAL_EXTRACTION_REGRESSION
```

## Decision

```text
R201H-P1 = PASS
Scope = freeze-before-cleanup only
Not a template freeze
Not a generation quality enhancement
```

## What Changed

- Removed engineering terminology from teacher-main readability snapshots.
- Added teacher-facing source labels such as `理解整理依据`, `教学推进依据`, and `上传原文依据`.
- Kept internal ownership source types for audit ledgers.
- Added `numbered_sentence_parser` so minimal numbered lessons preserve each simple step.
- Raised the minimal `线条小鱼` regression floor from 1 to 3 episodes.
- Cleaned the default R114A evidence target so teacher assessment text no longer says `需在 R114B 执行地图中细化对应关系`.

## Key PASS Metrics

```text
teacher_main_engineering_term_count = 0
minimal_line_fish_actual_episodes = 3
student_creation_step_not_swallowed = true
downpour_teacher_assessment_engineering_terms = 0
source_gap_as_content = 0
teacher_main_R200A/R200B/R97B_P3 = 0
```

## Boundaries

```text
no full default route switch
no formal apply
no database / Feishu / memory write
no R95
no provider/model call
no large R97B UI redesign
```

## Main Review Files

- `outputs/PREP_ROOM_RENDER_CANVAS_DEEPEN_V1/1013R_R201H_P1_TEACHER_MAIN_CLEANUP_AND_MINIMAL_EXTRACTION_REGRESSION/validate_1013R_R201H_P1_teacher_main_cleanup_and_minimal_extraction_regression_result.json`
- `outputs/PREP_ROOM_RENDER_CANVAS_DEEPEN_V1/1013R_R201H_P1_TEACHER_MAIN_CLEANUP_AND_MINIMAL_EXTRACTION_REGRESSION/r201h_p1_teacher_main_cleanup_report.md`
- `outputs/PREP_ROOM_RENDER_CANVAS_DEEPEN_V1/1013R_R201H_P1_TEACHER_MAIN_CLEANUP_AND_MINIMAL_EXTRACTION_REGRESSION/r201h_p1_minimal_extraction_regression_report.md`
- `outputs/PREP_ROOM_RENDER_CANVAS_DEEPEN_V1/1013R_R201H_P1_TEACHER_MAIN_CLEANUP_AND_MINIMAL_EXTRACTION_REGRESSION/r201h_p1_downpour_teacher_text_cleanup_before_after.md`

## Code Anchors

- `backend/xiaobei_ai/prep_room_lean_readonly_chain_1013R_R201C.py`
- `backend/xiaobei_ai/prep_room_import_understanding_v2_graph_1013R_R114A.py`
- `scripts/validate_1013r_r201h_p1_teacher_main_cleanup_and_minimal_extraction_regression.py`
- `scripts/validate_1013r_r201g_canary_manual_teacher_readability_smoke.py`
- `scripts/validate_1013r_r201d_lean_chain_multi_format_regression.py`

## Validation

The R201H-P1 validator reruns:

```text
R201F validator
R201D validator
R201G validator
R201H validator
py_compile
```

All passed in the local package before upload.
