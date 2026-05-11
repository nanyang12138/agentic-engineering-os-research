# Agentic Engineering OS Research Loop Prompts

主计划文件：

```text
.cursor/plans/agentic-control-plane.plan.md
```

使用原则：

1. 每一轮都先读取主计划。
2. 每一轮只聚焦一个研究主题，避免计划无限膨胀。
3. 每一轮必须产出 Evidence Log、Decision Log、Open Questions 和下一轮建议。
4. 只有在结论足够明确时才修改主计划。

## Prompt 1: 启动一轮完整研究 Sprint

```text
请读取 @.cursor/plans/agentic-control-plane.plan.md。

执行一轮 Agentic Engineering OS Research Sprint。

本轮主题：
[填写主题，例如 Open Source Coverage Mapping / Evidence Graph / Verifier Runtime / CUA Adapter / Intent-to-Spec]

要求：
1. 先总结主计划中与本主题相关的现有内容。
2. 并行启动多个 agent：
   - Open Source Mapping Agent
   - Architecture Agent
   - CUA Adapter Agent
   - Feasibility Critic Agent
   - Research Strategy Agent
3. 每个 agent 必须输出：
   - 核心结论
   - 证据或依据
   - 对主计划的修改建议
   - 风险和 open questions
4. 主 agent 汇总分歧，做 Build vs Integrate 决策。
5. 更新主计划文件：
   - 新增或修订对应章节
   - 追加 Research Sprint Log
   - 追加 Decision Log
   - 追加下一轮研究问题
6. 不要把计划扩大成泛泛的平台愿景，要收敛到可验证 MVP。
```

## Prompt 2: Open Source Coverage Mapping Sprint

```text
请读取 @.cursor/plans/agentic-control-plane.plan.md。

本轮只做 Open Source Coverage Mapping。

请研究并比较以下项目分别覆盖 Agentic Engineering OS 的哪些层：
LangGraph、AutoGen、CrewAI、OpenHands、SWE-agent、Aider、Claude Code、Cursor、Browser-use、trycua/cua、E2B、Devbox、Modal、Replit、Dagger、Temporal。

请输出并更新主计划：
1. Coverage Matrix：项目 -> 覆盖层 -> 成熟度 -> 可借鉴点 -> 缺口。
2. Build vs Integrate：哪些层应该自研，哪些层应该集成。
3. Differentiation：我们的系统与现有项目真正不同在哪里。
4. MVP Implication：第一版应该避开哪些已有项目已经解决的问题。
5. Research Sprint Log：记录本轮证据、结论和下一轮问题。
```

## Prompt 3: CUA Adapter 深挖

```text
请读取 @.cursor/plans/agentic-control-plane.plan.md。

本轮只研究 trycua/cua 与 Agentic Engineering OS 的关系。

请回答：
1. trycua/cua 提供哪些底层能力：sandbox、computer runtime、GUI automation、trajectory recording、benchmark。
2. 它能作为哪些 capability adapter？
3. 它不能承担哪些 OS 级职责？
4. CUA trajectory 如何进入 RunEvent / Observation / Evidence Graph？
5. 最小集成 demo 是什么？

请更新主计划中的 CUA Adapter 章节，并追加 Decision Log。
```

## Prompt 4: Evidence Graph 和 Verifier Runtime Sprint

```text
请读取 @.cursor/plans/agentic-control-plane.plan.md。

本轮只研究 Evidence Graph 和 Verifier Runtime。

请设计：
1. Evidence 节点 schema。
2. Observation -> Evidence -> Artifact 的链接方式。
3. Verifier 类型：test、lint、log check、schema validation、review agent、human approval。
4. Verifier 什么时候自动运行，什么时候需要 human gate。
5. 如何证明一个 artifact 的结论有足够证据。
6. MVP 中最小实现范围。

请更新主计划，并追加一个可执行的本地 demo 流程。
```

## Prompt 5: Feasibility Critic Review

```text
请读取 @.cursor/plans/agentic-control-plane.plan.md。

请以非常严格的反方评审身份审查这份计划。

重点找：
1. 哪些目标太大，第一版不应该做。
2. 哪些概念只是漂亮名词，没有工程落点。
3. 哪些模块之间边界不清。
4. 哪些地方缺少验证实验。
5. 哪些假设需要先用开源项目或小 demo 验证。

请不要只夸计划。请给出明确删减、收敛和重写建议。
最后请生成一个更小的 MVP 定义，并更新主计划的风险和范围控制章节。
```

## Prompt 6: 每周计划维护

```text
请读取 @.cursor/plans/agentic-control-plane.plan.md。

请做一次计划维护，不做大规模研究。

任务：
1. 检查 todos 状态是否和正文一致。
2. 整理 Decision Log。
3. 整理 Open Questions。
4. 把已经明确的研究结论移动到正式章节。
5. 把不再重要的问题移动到 Parking Lot。
6. 给出下一周最重要的 3 个研究任务。
```

## 推荐执行顺序

```text
Sprint 1: Open Source Coverage Mapping
Sprint 2: Feasibility Critic Review
Sprint 3: Intent-to-Spec MVP
Sprint 4: Evidence Graph + Verifier Runtime
Sprint 5: CUA Adapter Integration
Sprint 6: Local Workflow Daemon MVP
Sprint 7: Demo scenario: regression log -> evidence -> email artifact
```
