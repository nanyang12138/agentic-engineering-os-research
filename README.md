# Agentic Engineering OS Research

This repository stores the research plan, Cursor rule, skill, and prompt templates used by Cursor Cloud Automations to continuously improve the Agentic Engineering OS plan.

## Source Of Truth

```text
.cursor/plans/agentic-control-plane.plan.md
```

## Cursor Assets

- `.cursor/rules/agentic-engineering-os-research.mdc`: persistent research direction.
- `.cursor/skills/agentic-plan-optimizer/SKILL.md`: reusable plan optimizer loop.
- `.cursor/prompts/agentic-engineering-os/research-loop-prompts.md`: manual sprint prompt library.
- `docs/automation/cloud-automation-prompt.md`: prompt to paste into Cursor Automations.

## Automation Goal

Each automation run should do one bounded improvement:

```text
read plan -> score plan -> select one sprint -> update plan -> append logs -> open PR
```

The automation should optimize for convergence, feasibility, evidence density, and MVP clarity.
