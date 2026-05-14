# Cursor Cloud Automation Prompt

Use this prompt in Cursor Automations with a scheduled trigger. The automation should make one bounded, reviewable improvement per run and keep running on future schedules until the plan reaches the completion criteria below.

## Production Prompt

```text
You are running unattended in Cursor Automation for:
https://github.com/nanyang12138/agentic-engineering-os-research

Repository:
nanyang12138/agentic-engineering-os-research

Base branch:
main

Primary goal:
Execute the entire Agentic Engineering OS plan phase by phase as working, tested code.

First required gate:
Implement Phase 1a before advancing to later phases; Phase 1a is necessary but not sufficient for the whole plan.

Source of truth:
.cursor/plans/agentic-control-plane.plan.md

Important override:
This automation supersedes the previous research-only automation. It is allowed to create implementation code, tests, fixtures, validation scripts, GitHub Actions workflows, documentation, local runners, adapters, and other artifacts needed to complete the plan.

The previous instruction "Do not modify product code" does not apply to this automation.

Core operating principle:
The user will not manually review or test every PR. Automated tests, deterministic validation, GitHub checks, and the Definition of Done are the review gate.

Use PRs as machine-verifiable safety boundaries, not manual review gates.

Execution strategy:
- Read the full plan every run.
- Determine the current active phase from the plan state, completed artifacts, tests, logs, and repository contents.
- Select the earliest incomplete phase or phase slice whose prerequisites are satisfied.
- Complete one verified slice per run.
- Continue this loop until every phase is implemented, verified, or explicitly removed from scope by a recorded plan decision.

Product boundary guardrail:
Agentic Engineering OS is a workload-independent OS kernel, not a regression/email automation tool.

The system must converge on:

```text
Agentic Engineering OS Kernel
  -> workload-independent primitives
  -> supports many engineering workload types
  -> first workload: Read-only Regression Evidence Demo
  -> coordination layer: delegation / creator-verifier / direct communication / negotiation / broadcast
```

First workload:
Read-only Regression Evidence Demo.

The first workload should implement the Phase 1a fixture runner described in:
.cursor/plans/agentic-control-plane.plan.md

The end-state is:
synthetic fixture logs
  -> template RegressionTaskSpecV1
  -> read_log
  -> rule-based extract_regression_result
  -> run.json + events.jsonl
  -> evidence.json + regression_result.json + email_draft.md
  -> verifier_report.json

Expected CLI shape:
fixture-runner --fixture-dir <fixtures/regression> --out-dir <artifacts/runs>

Expected fixtures:
- all_passed
- failed_tests
- incomplete_jobs
- passed_with_warning_or_waiver
- ambiguous_summary

Regression boundary rule:
- Regression Evidence Demo is the first deterministic workload and kernel smoke test, not the product boundary.
- After Phase 1a-9 contract-only MVP completion, do not keep adding regression/email-specific post-MVP artifacts unless they clearly generalize a workload-independent OS kernel primitive, coordination protocol, verifier invariant, or policy invariant.
- Do not select a slice that only deepens `all_passed`, `email_draft`, `regression_result`, `send_email`, approval lifecycle, or delivery unlock behavior unless the implementation is explicitly reusable across non-regression workloads.
- Prefer slices whose contracts can also apply to test execution, code patch generation, PR review, issue triage, documentation update, release readiness, incident analysis, IDE-assisted coding, or CUA/computer-runtime observation tasks.

Post-MVP slice selection priority:
After the contract-only Read-only Regression Evidence Demo is complete, select the next slice in this order:

1. Generalize a workload-independent kernel primitive (`TaskSpecV1`, `ArtifactV1`, `VerifierResultV1`, `CapabilityV1`, `RunEventV1`, `PolicyV1`, `DeliveryV1`).
2. Add or prepare a second workload, preferably Test Execution / Failure Triage, using the same kernel contracts.
3. Add an Agent Coordination Layer protocol (`DelegationManifestV1`, `CreatorVerifierPairingV1`, `AgentMessageV1`, `NegotiationRecordV1`, `CoordinationEventV1` / broadcast event bus).
4. Strengthen a verifier, evidence, policy, or delivery invariant that is workload-independent.
5. Only then extend the first regression/email workload.

Slice rejection rule:
Reject or rewrite a candidate slice if it cannot answer:

- Which OS kernel primitive does this advance?
- Which non-regression workload could reuse it?
- Which coordination protocol or creator-verifier invariant does it clarify?
- Why is this not merely another regression/email fixture?

Branch and merge policy:
- Start each run from the latest main branch.
- Create a new temporary branch for this run.
- Open a PR targeting main.
- Use squash merge.
- Do not run `gh pr merge --auto --squash` from Cursor Automation.
- Do not directly merge to main.
- Auto-merge is delegated to `.github/workflows/auto-merge-cursor-pr.yml` after `validate` succeeds.
- Never merge directly to main without a PR.

Run procedure:

1. Inspect the repository
Read:
- README.md
- .cursor/plans/agentic-control-plane.plan.md
- docs/automation files if present
- .cursor/rules files if present
- .cursor/skills files if present
- .cursor/prompts files if present
- .github/workflows files if present
- package/config/test files if present

Before editing:
- Check git status.
- Understand the current Phase 1a state.
- Identify the next useful implementation slice.

2. Determine active phase
Choose the earliest phase or phase slice that:
- is not yet complete
- has prerequisites satisfied
- has enough plan detail to implement
- can be completed and verified in this run

Do not skip earlier phase gates to work on later phases.

3. Bootstrap validation if needed
If the repository has no useful GitHub Actions workflow or deterministic validation gate, the selected slice should be:

"Add the minimal validation workflow and local validation command so future PRs have a real merge gate."

This first slice may add:
- .github/workflows/validate.yml
- a lightweight validation script
- package/config files only if needed
- fixture or plan validation checks only if they are deterministic

Do not pretend checks exist if they do not.

4. Select exactly one completed slice
Choose exactly one implementation slice.

The selected slice must:
- advance the active phase
- be completable in this automation run
- have clear acceptance criteria
- be verifiable with tests/checks/scripts
- produce a completed useful result, not partial scaffolding

The slice must be describable in one sentence:
"Add/fix/finish <one thing> so that <one verification> passes."

Before editing, write an implementation note with:
- selected slice
- why this is the right next step
- acceptance criteria
- expected files to change
- verification command

5. Definition of Done
A run is complete only when all are true:
- The selected slice has been fully implemented.
- All acceptance criteria written before editing are satisfied.
- Relevant tests/checks pass.
- Verification commands were actually run.
- The implementation is not a placeholder, stub, TODO-only change, or plan-only change unless the selected slice was explicitly a planning slice.
- The PR description clearly explains what is now working.
- The next recommended slice builds on completed work.

Do not mark complete if:
- core behavior is missing
- tests are skipped instead of fixed
- implementation only adds unused scaffolding
- verification was not run
- verification fails
- important behavior depends on unimplemented future work

If the selected slice cannot be completed:
- reduce scope to the smallest independently useful complete sub-slice
- finish that sub-slice fully
- update the plan to say the larger task remains incomplete
- do not enable auto-merge unless the completed sub-slice independently satisfies this Definition of Done

6. Implement
Make the smallest coherent change that fully completes the selected slice.

Guidelines:
- Prefer runnable code, validation scripts, tests, workflows, fixtures, and artifact checks over pure prose.
- Follow existing repository style.
- Do not introduce major dependencies unless necessary.
- Do not perform broad rewrites.
- Do not touch secrets, credentials, deployment settings, billing settings, or destructive data operations.
- Do not send emails or create external side effects.
- Do not integrate CUA, browser automation, desktop control, Temporal, LangGraph, or database infrastructure until the relevant phase gate is active.
- Do not leave known broken behavior behind and call the task complete.

7. Verify
Run the strongest reasonable validation available.

Use relevant commands such as:
- lint
- typecheck
- tests
- build
- formatting check
- smoke test
- validation script
- fixture-runner validation

If no test framework exists, create a lightweight deterministic validation script only if it directly supports the selected slice.

8. Self-repair loop
If any verification fails:
- inspect the failure
- identify the root cause
- fix the issue
- rerun verification

Repeat up to 3 repair attempts.

If checks still fail after 3 attempts:
- leave the PR open
- do not enable auto-merge
- clearly summarize what failed, what was attempted, and what remains

Do not skip, delete, or weaken tests just to make checks pass.

9. Update plan and logs
If implementation changes project state, update:
.cursor/plans/agentic-control-plane.plan.md

Append or update an automation log entry with:
- date/time
- selected slice
- implementation summary
- verification commands run
- verification result
- remaining risks
- recommended next slice

The plan must accurately reflect what is complete and what remains incomplete.

10. Commit and open PR
Create a branch for this run.

Commit message format:
<type>: <short description>

Examples:
- feat: add validation workflow
- feat: add fixture runner scaffold
- test: add regression fixture validation
- fix: repair verifier grounding check

Open a PR targeting main.

PR title:
<type>: <short description>

PR body:

## Summary
- What changed
- Why this slice was selected
- What is now working

## Definition of Done
- Acceptance criteria
- Whether each criterion was satisfied

## Verification
- Commands run
- Result of each command

## Automation Notes
- Remaining risks
- Suggested next slice

11. Auto-merge delegation
After opening the PR, do not attempt to mark it ready, enable auto-merge, or merge it from Cursor Automation.

Auto-merge is delegated to:

```text
.github/workflows/auto-merge-cursor-pr.yml
```

The PR body must state:
- Cursor Automation did not run auto-merge.
- Auto-merge is delegated to `.github/workflows/auto-merge-cursor-pr.yml`.
- After `validate` succeeds, that workflow should mark the PR ready if needed and enable squash auto-merge.

If the auto-merge workflow is missing or failing, report it as an infrastructure blocker. Do not spend a product implementation run recreating it unless explicitly instructed.

12. Final response
At the end of the run, report:
- selected slice
- branch name
- PR URL
- what is now complete
- verification result
- whether auto-merge was enabled
- if auto-merge was not enabled, why
- next recommended slice
- whether the full plan is complete or still in progress
```

## Recommended Cadence

```text
Trigger: Scheduled
Repo: agentic-engineering-os-research
Base branch: main
Tools: allow file edits, shell commands, and pull request creation
Scope: repository-wide for Phase 1a implementation, but avoid secrets, deployment settings, billing settings, and destructive operations
```
