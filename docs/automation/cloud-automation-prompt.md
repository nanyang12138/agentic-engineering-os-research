# Cursor Cloud Automation Prompt

Use this prompt in Cursor Automations with a scheduled trigger.

```text
Use the agentic-plan-optimizer skill.

Read .cursor/plans/agentic-control-plane.plan.md.

Run one bounded Agentic Engineering OS Plan Optimizer Loop.

Requirements:
1. Score the current plan across the required dimensions.
2. Identify the lowest 1-2 dimensions.
3. Select exactly one sprint type.
4. Improve the plan only if there is a material improvement.
5. Update Decision Log, Open Questions, Research Backlog, and Research Sprint Log.
6. Keep the plan converging toward a feasible MVP.
7. Do not modify product code.
8. Do not expand generic vision unless it improves MVP clarity or Build vs Integrate decisions.
9. Open a PR only when the plan file or related research files are materially improved.

If no useful improvement is found, append a short Research Sprint Log entry explaining why and what evidence is still missing.
```

Recommended cadence:

```text
Daily at first. Increase frequency only after PR quality is consistently good.
```

Recommended Cloud Automation settings:

```text
Trigger: Scheduled
Repo: agentic-engineering-os-research
Base branch: main
Tools: allow file edits and pull request creation
Scope: only .cursor/plans, .cursor/skills, .cursor/rules, .cursor/prompts, docs
```
