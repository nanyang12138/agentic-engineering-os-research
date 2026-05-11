---
name: agentic-plan-optimizer
description: Optimizes an Agentic Engineering OS research plan through repeated scoring, sprint selection, multi-perspective review, plan updates, and research logs. Use when the user asks to optimize, continue, review, improve, iterate, or loop on the Agentic Engineering OS plan.
---

# Agentic Plan Optimizer

## Default Plan

Use this plan unless the user provides another path:

```text
.cursor/plans/agentic-control-plane.plan.md
```

Also use the prompt library when useful:

```text
.cursor/prompts/agentic-engineering-os/research-loop-prompts.md
```

## Goal

Continuously improve the plan into a feasible, evidence-backed Agentic Engineering OS roadmap. Optimize for convergence, not length.

Prefer:
- Clear MVP scope.
- Strong Build vs Integrate decisions.
- Evidence-backed open-source comparison.
- Concrete verifier and evidence graph design.
- Explicit first demo and non-goals.

Avoid:
- Repeating prior conclusions.
- Expanding generic platform vision.
- Adding concepts that do not improve the MVP.
- Updating chat only without writing back to the plan.

## Required Loop

When invoked, run one bounded optimization sprint:

1. Read the latest plan file.
2. Score the plan from 1-5 on:
   - Vision clarity.
   - MVP executability.
   - Open-source mapping completeness.
   - Build vs Integrate clarity.
   - Evidence Graph maturity.
   - Verifier Runtime maturity.
   - CUA Adapter boundary clarity.
   - Risk control and scope convergence.
3. Identify the lowest 1-2 dimensions.
4. Select exactly one sprint type:
   - `Open Source Coverage Mapping` when ecosystem comparison is weak.
   - `Feasibility Critic Review` when scope is too large or vague.
   - `Evidence Graph / Verifier Runtime` when evidence and validation are weak.
   - `CUA Adapter` when trycua/cua boundaries are unclear.
   - `Local Workflow Daemon MVP` when implementation path is unclear.
   - `Plan Maintenance` when the plan is repetitive or fragmented.
5. Review through these perspectives:
   - Open Source Mapping Agent.
   - Architecture Agent.
   - CUA Adapter Agent.
   - Feasibility Critic Agent.
   - Research Strategy Agent.
6. Update the plan file directly.
7. Report what changed, current scores, and the next recommended sprint.

## Plan Update Contract

Every sprint must update at least one of these sections:

- Formal design sections.
- Research Backlog.
- Decision Log.
- Open Questions.
- Research Sprint Log.
- Parking Lot, if content should be deferred.

If the sprint produces no material improvement, do not force edits. Instead, append a short Research Sprint Log entry explaining why no change was made and what evidence is still missing.

## Quality Gate

Before finishing, verify:

- The plan became more actionable or more constrained.
- At least one decision, open question, risk, or MVP detail improved.
- New content is tied to evidence, feasibility, or Build vs Integrate.
- The next sprint recommendation is specific.
- The final response includes a continuation prompt.

## Final Response Template

Use this structure:

```text
本轮已完成：[sprint type]

主要改动：
- ...

当前评分：
- Vision 清晰度：x/5
- MVP 可执行性：x/5
- Open Source Mapping 完整度：x/5
- Build vs Integrate 清晰度：x/5
- Evidence Graph 设计成熟度：x/5
- Verifier Runtime 设计成熟度：x/5
- CUA Adapter 边界清晰度：x/5
- 风险控制和范围收敛度：x/5

下一轮建议：[next sprint type]

Continuation prompt:
继续使用 agentic-plan-optimizer skill，读取最新 plan，基于上一轮 Research Sprint Log 和当前最低分维度，执行下一轮优化并写回文件。
```
