# Agentic Engineering OS Research

This repository stores the research plan, Cursor rule, skill, prompt templates, and implementation artifacts used by Cursor Cloud Automations to build the Agentic Engineering OS plan phase by phase.

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

Each automation run should do one bounded, verified implementation slice:

```text
read plan -> determine active phase -> select one slice -> implement -> verify -> update plan -> open PR
```

The automation should optimize for working code, deterministic verification, convergence, feasibility, evidence density, and MVP clarity.
