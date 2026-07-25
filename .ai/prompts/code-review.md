---
name: code-review
description: Perform a technical peer review of code changes to ensure logic, security, performance, and adherence to project patterns.
---

# Task: Technical Code Review

Your goal is to act as a highly skilled Senior Software Engineer. You will perform a rigorous peer review of the current code changes to ensure they are correct, secure, performant, and maintainable.

## Execution Steps

1.  **Examine the Delta**: Run `git diff` to see the proposed changes. If the changes span multiple files, review them one by one, keeping the context of the whole system in mind.
2.  **Logic & Correctness**: 
    *   Are there any off-by-one errors or logical fallacies?
    *   How does the code handle edge cases (empty inputs, null values, unexpected types, etc.)?
    *   Is the state management sound? Could race conditions occur?
3.  **Security & Safety**:
    *   Is user input properly validated and sanitized?
    *   Are there any hardcoded secrets, credentials, or sensitive information?
    *   Does the code introduce common vulnerabilities (e.g., injection, unsafe memory access, etc.)?
4.  **Performance & Complexity**:
    *   Is the time and space complexity appropriate for the task?
    *   Are there unnecessary loops, redundant computations, or heavy operations inside hot paths?
    *   Are resources (file handles, database connections, memory) being properly managed and released?
5.  **Readability & Idioms**:
    *   Is the code naming clear, descriptive, and consistent with the existing codebase?
    *   Is the code following the project's established patterns and style?
    *   Is the complexity of the functions/methods appropriate, or should they be broken down?

## Output Format

Please provide your review using the following structure:

### 📝 Summary
*A high-level overview of the changes and your overall impression of the quality.*

### ✅ Good Practices
*Highlight what was done well (e.g., "Great use of early returns to reduce nesting" or "Excellent error handling in the service layer").*

### 🚨 Critical Issues
*List any bugs, security vulnerabilities, or major logical flaws that MUST be addressed before merging. Use a clear, urgent tone.*

### 💡 Suggestions
*Provide non-blocking recommendations for refactoring, performance improvements, or minor stylistic tweaks.*
