# R201H Projection Semantics Repair

R201H separates teacher-main episode semantics:

- `episode_goal`: student learning change or observable evidence target
- `teacher_organization`: concrete teacher classroom action
- `student_learning`: concrete student action
- `evidence`: observable source evidence

A topic guard now checks R114B/R114C generated text against the current uploaded source episode. If a generated move contains terms absent from the current source, the template uses the uploaded source episode field instead.

This fixed the formal `下雨啰` sample, where a deterministic execution-map branch had injected old-shoe language into a rain lesson.
