# Agentic Coding for Humans

This document is a practical guide for humans working in our agentic coding workflow. It is partly an onboarding guide and partly a team standards document. An "agent harness" refers to a tool like Claude and Copilot, which have LLMs that can write code, but also have a larger set of tools that allow them to interact with the filesystem, the internet, and other tooling. This is what powers our agentic coding setups.

Core ideas are:

- **Skills**, **prompts**, **MCP servers**, and **/docs** are the core tools that we use to guide our agents. They are:
  - A way to ensure that *my* agent and *your* agent behave the same way on the same repo, even if we are using different tools (Claude vs Copilot, or VSCode vs Zed)
  - The shared memory of a project
  - Guidance for agents' behavior (ex: don't commit or push autonomously)
  - Guardrails that align agents to our desired coding patterns & preferences
  - Hallucination mitigation
  - Extra superpowers via MCP servers
- When we start a new agent chat session, the agent should be able to recover the most important (shared) context from the repo itself, **not from a previous chat on our individual machine**.
- We support multiple agentic stacks, since developers have different preferences and constraints. We optimize around a repeatable working style, with this project's `.ai/` harness as the portable source of truth for instructions, skills, prompts, and MCP configuration. That lets the team move between GitHub Copilot, Claude, Antigravity CLI, Codex, `.pi`, and locally-hosted setups while providing consistent behavior and shared context for (almost) any agentic coding workflow.

## The bare minimum agent setup for a project:

If you don't need the full weight of this sync tool, you can still get a lot of value from a few simple files:

- /AGENTS.md - project-specific instructions for agents, including coding preferences, tools, resources, concepts, and examples. This file should be recognized by most agents, and is the single source of truth for project-specific instructions.
- /CLAUDE.md - the file contents should be `@AGENTS.md`, which points Claude to the instructions in AGENTS.md. This is like a micro implementation of this larger sync and docs tool, in case you don't need the full system.

After that, you can also add /docs for a more durable memory layer. These /docs should be linked to from AGENTS.md. Beyond this vanilla setup, if you use skills, prompts, and mcp servers, you should use the harness sync tool to better manage these features, so that all agents see the same configuration.

This looks like:

```
docs/
AGENTS.md
CLAUDE.md (points to AGENTS.md)
```

## Using this .ai/ sync tool for a more robust agentic setup

### Getting started

To begin using this sync tool in your project


### What to edit in your project

This repository's tooling is intended to make our agent/harness setups portable across projects and teammates. Here are the primary files that should be *edited* in your coding project, and maintained over time:

- `.ai/AGENTS.md` carries project-specific instructions for agents, and links to the following files. Equivalent to the vanilla /AGENTS.md or /CLAUDE.md. We keep it in `/.ai` so that we don't need to manage multiple copies for different agents (Claude in particular doesn't yet look for AGENTS.md in the root). This AGENTS.md file is automatically combined with `.ai/_base.md` to provide a complete set of instructions and context for agents to understand how this sync tooling works within a project.
- `.ai/skills/*` holds reusable domain knowledge and workflow guidance. We should maintain libraries of common skills that can be shared across projects, organized by technology or domain.
- `.ai/prompts/*` holds explicit slash commands for common tasks, including setup, validation, and review. These simply save us from repeatedly writing the same instructions and ensure consistency across agents.
- `.ai/mcp-servers.json` is the single source of truth for MCP servers so that all agents have a consistent view of available external tools and integrations. There are slight differences in running MCP servers across different agents, but this file ensures a unified configuration.
- `docs/*` is where project-specific *human and agent* documentation should live when a project has enough complexity to justify it.

## How it works (problems this tool solves)

This tool's primary purpose is to create **symlinks** from the single source of truth in `.ai/` to the locations that each agent expects. This ensures that all agents see the same instructions, skills, prompts, and MCP servers, even if they have different expectations for where those files should live. We only support a limited set of agents, but the same principles apply to any agent that could be added later. Over time, we expect and hope that more agents will support standardized file locations, and this tool will become less necessary.

### Documentation and skills as Memory

In agentic development, documentation is operational memory for future sessions. This memory should be stored (and maintained) as markdown files in the repo. Agents otherwise lose chat context between sessions, and have to rebuild their understanding of a project and developer preferences each time. This costs time and tokens. The concept of a durable memory layer is the repository itself, especially `.ai/AGENTS.md`, `.ai/skills/`, and `docs/`. This ensures that both humans and agents across the team can access the same knowledge consistently.

As code is built, the team should capture learnings, patterns, and workflows in skills and docs. This is how we ensure that future agent chat sessions can recover context quickly, and generally **be smarter**. When an agent finishes a difficult task, or spent a lot of time debugging a tricky problem, it should summarize the change and update relevant docs/skills/prompts in the same commit. You, the human, need to ask it to do so. This ensures that future agents can solve a similar problem with less churn. We have a specific pattern for this in `/docs/learnings/`, called out in `.ai/_base.md`. This should be updated whenever a non-obvious problem is solved. 

It can be tricky to know where to put new learnings. The general rule is that if it is a repeatable pattern, it should be captured as a skill. If it is a one-off lesson, it should be captured in `/docs/learnings/`. If it is a project-specific preference, it should be captured in `.ai/AGENTS.md`.

#### Extra tooling

`.ai/prompts` are a set of slash commands that can be used to trigger specific workflows, including setup, validation, and review. These prompts are designed to be reusable and can be invoked by any agent that supports them.

`.ai/mcp-servers.json` is the single source of truth for MCP servers, which provide structured tool access beyond the base chat experience. This allows agents to interact with external systems and tools in a controlled and repeatable manner.

### When to create `docs/` as harness docs

Once a codebase is significant enough, `docs/` should be created and maintained as part of engineering work, not as optional cleanup. A larger codebase is when we move from encoding info in AGENTS.md to encoding it in a more durable memory layer. 

When the threshold is met, you can bootstrap docs structure with the premade prompt ([.ai/prompts/harness-docs-setup.md](.ai/prompts/harness-docs-setup.md)) and keep it current as part of ongoing maintenance during a project lifecycle.

If `docs/` is missing, sparse, or not organized for agent retrieval, you can explicitly run the setup prompt (`/harness-docs-setup`) instead of inventing a new structure. For smaller codebases, the full docs structure may be overkill, and a smattering of ad hoc markdown files may be sufficient. The key is that the docs should be discoverable and useful to both humans and agents.



### When and how to use AGENTS.md
### When and how to use skills
### When and how to use prompts/commands
### When and how to use mcp servers
### How to run the sync script
### How to maintain your agent files over time

To keep memory useful:

1. Update skills/prompts/docs when behavior changes, new preferences or patterns emerge, or new lessons are learned.
2. Run [.ai/prompts/update-docs.md](.ai/prompts/update-docs.md) after meaningful code or workflow changes.
3. As an agent finishes a task - especially a difficult task - ask it to summarize the change and update relevant docs/learnings/skills/prompts in the same commit.
4. Re-run sync so generated harness files pick up new context. Running the watcher is a good way to ensure that the harness is always up to date.
5. Validate discoverability in a fresh session using [.ai/docs/test-instructions.md](.ai/docs/test-instructions.md).

If the maintenance loop reveals major documentation gaps, run [.ai/prompts/harness-docs-setup.md](.ai/prompts/harness-docs-setup.md) again and reconcile the resulting structure with current project reality.

This turns documentation from passive reference into active runtime context for every new agent session.

#### Update skills and docs while doing the work

Do not treat documentation and skill updates as end-of-project cleanup. In this workflow, they are part of implementation.

- When a new pattern becomes repeatable, capture it as a skill or prompt.
- When a command, workflow, or architecture decision changes, update the relevant doc in the same change.
- When a debugging lesson or migration pitfall appears, write it down where future sessions can load it quickly.

This is how preferences and team learnings survive session boundaries. A new chat session should recover project context from files, not from memory of a previous conversation.

The practical rule is simple: if you had to explain it twice, it should probably become a skill, prompt, or doc update.


## Team Defaults

Our institutional default is paid, supported tools first.

- GitHub Copilot and Claude are the primary tools we expect teammates to use day to day.
- Antigravity CLI, Codex, `.pi`, and even local-model setups are supported because the harness is meant to stay vendor-agnostic.
- Open source and local models, including `.pi` wired to local backends such as Gemma, are useful for experimentation, privacy-sensitive workflows, offline work, and cost control, but they should inherit the same instructions and operating standards where possible. See [.ai/docs/local-llm-hosting.md](.ai/docs/local-llm-hosting.md) for local hosting notes in this repo.

Standardization matters more than tool loyalty. A teammate should be able to enter a repo, run the harness sync, and get the same baseline behavior regardless of interface.





## Future Enhancements

Potential additions to our stack:
- https://github.com/TencentCloud/TencentDB-Agent-Memory/



---
---
---
---
---
---
---
---
---
---
---
---
---
---
---
---

















## Setting Up Your Tooling

For a new machine or a new repository, the goal is not to perfect every tool on day one. The goal is to get onto the team standard quickly.

1. Install and sign into GitHub Copilot in VS Code.
2. Ensure Claude access is available in the approved interface your team uses.
3. In any repository using this harness, run the sync so generated agent targets exist for your tools.
4. Verify prompts, skills, and MCP visibility using the checks in [.ai/docs/test-instructions.md](.ai/docs/test-instructions.md).
5. If you use Antigravity CLI, Codex, `.pi`, or a local-model stack, connect them to the same synced repo configuration instead of creating a separate instruction system. For harness-specific behavior, use [.ai/docs/harness-support.md](.ai/docs/harness-support.md).

The important setup principle is shared context. Tool choice can vary; baseline instructions and integrations should not.


## General Workflow Rules

These are team standards, not suggestions.

### Humans own the outcome

Agents can draft, refactor, search, summarize, and automate. 

Humans still own the results, stability, and understanding of the system. The code review burden is higher with agent-written code because the human likely has less line-by-line situational awareness than when writing the code directly.

**A human is responsible for:**

- Reviewing the code with *more* scrutiny than they would give to code they wrote manually.
- Running or requesting appropriate validation. Agents can quickly build test harnesses, but humans must decide what to validate and when.
- Guiding software design patterns and challenging the agent's recommendations.

### Agents should not be trusted with irreversible source-control actions by default

Our default stance is conservative.

- Agents should not commit unless explicitly asked.
- Agents should not push to GitHub.
- Agents should not open or merge pull requests autonomously.
- Agents should not perform destructive git operations unless a human has clearly approved them.

This is partly a safety rule and partly a discipline rule. Review should happen before the repository state becomes harder to reason about.

### Keep requests scoped and testable

Agent performance improves when the task has a clear surface area.

- Prefer a concrete file, failing test, error, behavior, or command.
- Prefer one problem per prompt when possible.
- Ask for validation, not just edits.
- Ask for cleanup after a feature has been verified.
- If the task is exploratory, say that explicitly so the agent does not force premature code changes.

### Update skills and docs while doing the work

Do not treat documentation and skill updates as end-of-project cleanup. In this workflow, they are part of implementation.

- When a new pattern becomes repeatable, capture it as a skill or prompt.
- When a command, workflow, or architecture decision changes, update the relevant doc in the same change.
- When a debugging lesson or migration pitfall appears, write it down where future sessions can load it quickly.

This is how preferences and team learnings survive session boundaries. A new chat session should recover project context from files, not from memory of a previous conversation.

Good things to capture as you build:

- preferred patterns and anti-patterns for this codebase
- known failure modes and their fastest diagnostics
- validation commands and what each one proves
- tradeoffs or constraints that affect design decisions
- migration notes and compatibility gotchas
- review expectations specific to this project

The practical rule is simple: if you had to explain it twice, it should probably become a skill, prompt, or doc update.

### Ask for evidence, not confidence

When using agents for implementation or debugging, useful outputs include:

- the file or symbol where behavior is controlled
- the smallest plausible change
- the specific validation run afterward
- the known risks or untested paths

The standard is not “does the answer sound smart?” The standard is “can we inspect the reasoning, change, and verification path?”

### Prefer iterative work over giant one-shot generations

Large monolithic prompts often produce polished but brittle output. In most engineering work, smaller loops are better.

- establish the target
- inspect the controlling code path
- make one focused change
- run one focused validation
- iterate only if needed

This is slower per prompt and faster per finished change.

## Use AI to Improve Quality and DX

Velocity is useful, but it is not the main point. A strong agent workflow should improve the quality of the codebase and the quality of the engineering experience around it.

### Use AI to build leverage, not just features

Some of the best agent-assisted work does not ship directly to production. It improves the system around the work.

- build reproduction harnesses for tricky bugs
- generate debugging scripts and inspection commands
- create smoke-test flows for high-risk behaviors
- add temporary instrumentation to expose system behavior
- draft fixtures, sample data, or replay inputs for interesting edge cases
- improve docs and command discoverability so future work gets easier

This is often a better use of AI than asking for a large feature implementation with weak observability.

### Test harnesses matter more than cargo-cult TDD

AI is especially good at helping us create focused validation tooling around the most interesting or failure-prone parts of a system.

- For a flaky workflow, build a targeted repro harness.
- For a brittle integration, build a repeatable smoke test.
- For a performance question, build a profiling or measurement script.
- For a migration or refactor, build comparison checks that reveal behavior drift.

These are often more valuable than forcing traditional unit tests onto code that does not benefit from them. The point is to increase signal, not to satisfy a ritual.

### Use AI as a review and audit assistant

Agents are useful before a change, during a change, and after a change.

- Before: ask the agent to identify the controlling code path and likely risks.
- During: ask it to keep changes narrow and validation-focused.
- After: ask it to review the delta for logic, safety, performance, and maintainability.

This repo already includes a reusable review prompt at [.ai/prompts/code-review.md](.ai/prompts/code-review.md). Use that when you want a structured second pass that emphasizes bugs, risks, regressions, and missing tests.

### Use AI to improve the documentation surface

Developer experience improves when the next person can understand the repo quickly, including the next future version of you.

- Create better architecture notes.
- Capture commands, workflows, and caveats in docs.
- Turn repeated chat instructions into reusable skills or prompts.
- Keep docs synchronized with code changes.

The harness already provides a docs setup prompt at [.ai/prompts/harness-docs-setup.md](.ai/prompts/harness-docs-setup.md) and a docs maintenance prompt at [.ai/prompts/update-docs.md](.ai/prompts/update-docs.md). Use them to turn one-off knowledge into shared infrastructure.

For team continuity, prefer updating these artifacts during implementation instead of batching them at the end. Session resets are normal; durable project context should not depend on chat history.

### Better DX is a first-class outcome

If AI only increases output speed while making the codebase harder to reason about, it is failing.

Good outcomes include:

- faster debugging because the repo has better observability
- faster onboarding because the docs and harness are clearer
- safer changes because validation tools exist for risky flows
- better reviews because more of the mechanical inspection work is covered
- less repeated explanation because project knowledge lives in skills, prompts, MCP servers, and docs

### Other useful AI-assisted coding patterns

The basics are mostly covered in this guide, but a few additional patterns are worth calling out explicitly.

- use agents to explain unfamiliar code paths before changing them
- use agents to inventory risks before a refactor or migration
- use agents to draft upgrade plans, rollout checklists, or validation plans
- use agents to compare competing implementations and identify tradeoffs
- use agents to summarize large diffs or pull request stacks before review
- use agents to turn repeated debugging or review behavior into reusable prompts and skills

## Using Skills

Skills are not generic documentation blobs. They are targeted instructions that help an agent recognize when to apply a specialized pattern or workflow.

### When to use a skill

Use a skill when the task has repeatable rules that an agent would otherwise have to rediscover every time.

Good skill candidates include:

- project-specific architecture conventions
- migration or upgrade workflows
- code review rules
- debugging playbooks
- documentation update procedures
- setup or verification routines

### Why skills matter

Skills reduce repeated prompting and reduce variance between teammates.

- They encode institutional memory.
- They keep multi-step workflows consistent.
- They improve the odds that different tools behave similarly.
- They let the harness carry team standards into any supported agent surface.

### How to write a good skill

Good skills are short, specific, and triggerable.

- Front-load when the skill should be used.
- Include anti-triggers describing when not to use it.
- Describe the workflow or decision rule, not just background information.
- Keep it stable enough to reuse, but concrete enough to change behavior.

In practice, “Use when X. Do not use for Y.” is often more valuable than a long reference page.

### How humans should invoke skills

There are two valid modes.

- Implicit invocation: describe the task clearly enough that the agent selects the skill on its own.
- Explicit invocation: use the harness-specific skill or prompt mechanism when you know exactly which workflow you want.

If a task is important enough to standardize, it is important enough to document as a skill instead of re-explaining it in every chat.

For per-harness skill behavior and invocation details, see [.ai/docs/harness-support.md](.ai/docs/harness-support.md).

## Using MCP Servers

MCP servers are how agents get structured tool access beyond the base chat experience. They are not just integrations; they are part of the execution environment.

### When MCP is worth adding

Add MCP when the team repeatedly needs live access to systems or tools such as:

- issue trackers
- documentation systems
- design files
- cloud resources
- databases
- internal APIs
- browser automation
- repo-aware utilities

If a workflow depends on external state and the agent keeps relying on pasted screenshots or copied snippets, that is often a sign an MCP integration would pay off.

### Why MCP matters

Well-chosen MCP servers can reduce hallucination and manual glue work.

- The agent can inspect live state instead of guessing.
- Humans spend less time copying context into chat.
- Workflows become repeatable across tools because the same server definitions sync into each harness-specific format.

### How to treat MCP safely

More tool power means more review responsibility.

- Prefer least-privilege credentials.
- Be explicit about read-only versus mutating tools.
- Test new MCP servers in a low-risk environment first.
- Document what each server is for so teammates know when to reach for it.
- Do not assume a connected tool is safe to let an agent drive autonomously.

The right standard is “connected, understandable, and bounded.”

For MCP format and harness-specific wiring details, see [.ai/docs/harness-support.md](.ai/docs/harness-support.md). For verification steps, use [.ai/docs/test-instructions.md](.ai/docs/test-instructions.md).

## VS Code Setup Notes

Because the team standardizes on VS Code, a few editor settings and behaviors are worth documenting explicitly.

### Copilot instruction and prompt settings

Two settings matter for this harness to work reliably in VS Code.

- `github.copilot.chat.codeGeneration.useInstructionFiles` should be enabled so Copilot uses [.github/copilot-instructions.md](.github/copilot-instructions.md).
- `chat.promptFiles` should be enabled so prompt files under [.github/prompts](.github/prompts) appear and behave correctly.

If either setting is wrong, the harness may look correctly synced on disk while Copilot behaves as if the repo has no custom setup.

### Inline completion should be part of the default workflow

For everyday use, developers should confirm that Copilot inline completions are active and not accidentally disabled at the editor or language level. The chat workflow matters, but the small completion loop is still the highest-frequency AI touchpoint in VS Code.

### Restart behavior matters

After syncing `.ai/` changes, do not assume every surface reloads immediately.

- Copilot may need a window reload or a fresh chat session before new prompts and instruction files are picked up.
- Claude surfaces often index skills and context at session start, so a fresh session is the safe default after sync.

If a skill, prompt, or instruction appears to be missing, restart the session before concluding the sync is broken.

### MCP startup behaves differently across tools

This is one of the biggest practical differences between Claude and Copilot.

- Claude commonly treats project-scoped MCP servers in [.mcp.json](.mcp.json) as available after approval, with first use often triggering a one-time trust or approval prompt.
- Copilot in VS Code exposes MCP more through the tools UI. The server should appear in the Copilot tools picker, and `MCP: List Servers` in the command palette is the clearest way to inspect status and logs.
- In both cases, the source of truth in this repo is still [.ai/mcp-servers.json](.ai/mcp-servers.json), but the operational check is different.

That difference is important for onboarding. In Claude, the question is often “did the session load and get approval?” In Copilot, the question is often “does VS Code show the server and tools as connected?”

### Recommended VS Code verification loop

When onboarding a developer or debugging the setup in VS Code, use this sequence.

1. Run the sync.
2. Confirm the generated targets exist.
3. Start a fresh chat session.
4. Verify prompts and instructions using [.ai/docs/test-instructions.md](.ai/docs/test-instructions.md).
5. Verify MCP connection state in the Copilot tools picker or with `MCP: List Servers`.

For harness-specific details, use [.ai/docs/harness-support.md](.ai/docs/harness-support.md) and [.ai/docs/test-instructions.md](.ai/docs/test-instructions.md).

## A Practical Day-to-Day Workflow

For most coding tasks, the workflow should look something like this.

1. Start in your editor with Copilot available for inline completion and quick local chat.
2. Use the synced harness so the agent sees the same project instructions, skills, prompts, and MCP definitions as the rest of the team.
3. Frame the task around a concrete behavior, file, test, or error.
4. Let the agent inspect narrowly before editing.
5. Require a focused validation step after the first real change.
6. Review the diff carefully, with extra attention to assumptions, deleted logic, and test coverage.
7. Run the relevant tests, checks, or manual verification before considering the work complete.

This should feel closer to pair programming with a very fast but uneven collaborator than to handing work off to an autonomous engineer.

## Routing Comes Last

Routing is useful, but it should sit on top of the workflow above, not replace it.

The real optimization is not “pick the smartest model every time.” The real optimization is to send each task to a tool that matches the task shape, while preserving context quality and minimizing unnecessary model switching.

### Our routing rule of thumb

Use Copilot as the default daily driver for in-editor work and lightweight chat. Route to Claude when the task needs stronger long-range reasoning, broader context handling, or more careful synthesis across many files.

When switching to a different target model for substantive work, prefer starting a fresh chat instead of carrying over a long thread that was optimized for a different tool.

### Good default split

- Use Copilot for inline completion, small edits, quick commands, lightweight documentation work, and narrow code questions.
- Use Claude for architectural reasoning, multi-file refactors, ambiguous debugging, longer planning sessions, and situations where you need the model to hold more context at once.

### Routing mistakes to avoid

- Do not escalate every task to the biggest model by habit.
- Do not keep switching models inside one long conversation unless the value clearly exceeds the context reset cost.
- Do not use routing as a substitute for better task framing.
- Do not assume a slower or more expensive model is automatically more correct.

### Why routing is still worth teaching

Done well, routing improves speed and cost efficiency.

- fast models handle high-volume local work cheaply
- stronger models stay available for the tasks that actually need them
- developers spend less time deciding from scratch which interface to use

But routing only helps after the team has a shared harness, shared standards, and shared expectations about review and validation.

## What Success Looks Like

We should consider this workflow successful when the following are true.

- A new developer can join a project and get the same baseline agent behavior quickly.
- The team can switch between Copilot, Claude, and other supported tools without rewriting its practices.
- Skills and MCP servers capture reusable team knowledge instead of leaving it trapped in individual chat histories.
- Significant codebases maintain `docs/` and [docs/learnings](docs/learnings) as active memory, so new sessions recover context quickly.
- Humans stay firmly accountable for review, validation, and repository safety.
- Routing improves cost and speed without degrading engineering judgment.

That is the point of this harness. It is not just a sync script. It is infrastructure for a repeatable way of working with coding agents.