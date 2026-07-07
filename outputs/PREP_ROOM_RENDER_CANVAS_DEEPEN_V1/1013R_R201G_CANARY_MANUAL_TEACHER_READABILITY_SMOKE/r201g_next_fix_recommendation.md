# R201G Next Fix Recommendation

- blocking_issue_count: 0
- non_blocking_issue_count: 0

## Decision

R201G can be accepted as a teacher-readability smoke package. The next stage should be a small readability fix loop only if the user wants to polish the non-blocking issues.

## Routing

- extraction issues: return to SourceExtractionOrchestrator/parser rules.
- graph issues: adjust R114A/B execution-map semantics, not R200A.
- projection issues: adjust R114C/single_lesson_template projection.
- template issues: fix single_lesson_template contract and ownership ledger.
- rendering issues: fix renderer placement/demotion only; do not generate pedagogy in renderer.

## Boundaries Kept

- no full default route switch
- no formal apply
- no database/Feishu/memory writes
- no R95 export
- no provider/model call
- no Xiaojiao real edit wiring
- no large UI redesign
