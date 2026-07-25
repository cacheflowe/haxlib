---
name: assess-progress
description: Analyze current unstaged git changes to assess progress, intent, and provide guidance on completing in-flight features.
---

# Task: Assess In-Flight Development Progress

Your goal is to act as a high-level technical partner. You will analyze the current unstaged changes in this repository to help the developer understand their own progress and plan their next steps.

## Execution Steps

1.  **Context Discovery**: Search for a roadmap, TODO list, or project plan (e.g., `TODO.md`, `ROADMAP.md`, `PLAN.md`, or sections in `README.md`). If found, use this to ground your assessment of progress and intent.
2.  **Examine the Delta**: Run `git diff` to see all unstaged changes. If the changes are large, examine them file by file to maintain clarity.
3.  **Infer Intent**: Based on the code being modified, what is the developer's primary objective? Are they implementing a new feature, fixing a bug, refactoring existing logic, or performing maintenance?
4.  **Determine Progress State**: Where does this work sit on the spectrum of "just started" to "ready to commit"?
    *   *Drafting/Experimental*: Scattered changes, no clear structure yet.
    *   *Implementation*: Core logic being written.
    *   *Refinement*: Logic is there, but being polished or cleaned up.
    *   *Testing/Verification*: Changes are focused on tests or edge cases for existing logic.
5.  **Analyze "How" and "Whether"**:
    *   **How to finish**: Provide a concrete, prioritized list of next steps. This should include code-level suggestions (e.g., "implement error handling in `service.ts`") and workflow suggestions (e.g., "run the test suite," "update `AGENTS.md`").
    *   **Whether to finish**: Provide a "gut check." Does this work look like it's moving in a healthy direction? Or does it look like it might introduce technical debt, break existing patterns, or is it a tangent that should perhaps be reverted?

## Output Format

Please provide your assessment using the following structure:

### 🎯 Detected Intent
*A concise 1-2 sentence description of what the developer appears to be working on.*

### 📊 Current Status
*A summary of where the work stands (e.g., "Mid-refactor of the auth module"). If a roadmap or TODO was identified, note how these changes align with it.*

### 🔍 Deep Dive
*A brief analysis of the key changes and their implications.*

### 🚀 Roadmap to Completion (The "How")
*A bulleted list of immediate next steps.*

### ⚖️ Strategic Advice (The "Whether")
*A "Go / No-Go / Caution" recommendation with a brief justification (e.g., "Caution: This approach might make testing difficult later; consider an interface-based approach instead").*
