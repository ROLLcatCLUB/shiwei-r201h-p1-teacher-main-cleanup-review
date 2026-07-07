# 线条小鱼 legacy vs lean teacher readability comparison

- sample_id: `minimal_line_fish`
- format_type: `minimal`
- lean_status_code: 200
- legacy_status_code: 200
- lean_engine: `lean`
- lean_selected_parser: `legacy_r103_parser`
- lean_episode_count: 2
- legacy_episode_count: 2

## Lean Episode Titles

- 看鱼图片，说一说鱼身上有什么线条
- 教师示范用波浪线、折线、点线装饰鱼

## Legacy Episode Titles

- 看鱼图片，说一说鱼身上有什么线条。
- 教师示范用波浪线、折线、点线装饰鱼。

## Smoke Judgment

Lean teacher view has blocking readability smoke issues for this sample.

## Issues

- [blocker] extraction / episode_count_too_low: 环节数 2 低于预期 3。
- [major] projection / episode_goal_duplicates_teacher_organization: 2 个环节的环节意图与教师组织完全重复。
- [major] projection / generic_front_matter_wording: 前置依据/学情/目标仍有泛化措辞：['围绕本课任务', '具体学情与材料条件仍需教师确认', '上传教案单元待确认', '材料、工具、大屏资源和安全安排需教师根据本班条件确认']
