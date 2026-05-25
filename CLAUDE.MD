# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

<!-- Fill in: what this project does, key entry points, deployment target -->

---

## Behavioral Guidelines

These four principles apply to every task, regardless of stack or scope.

### 1. Think Before Coding
- State your assumptions explicitly before implementing anything non-trivial.
- If a request has multiple valid interpretations, list them and ask which one applies.
- Surface tradeoffs (performance vs. readability, flexibility vs. simplicity) instead of picking silently.
- If something is unclear or contradictory, halt and ask. Do not guess.

### 2. Simplicity First
- Write the minimum code that satisfies the success criteria.
- No speculative abstractions, no "just in case" parameters, no premature generalization.
- Prefer 100 lines of clear code over 1000 lines of flexible code.
- If you find yourself adding a config option "for the future," delete it.

### 3. Surgical Changes
- Touch only what the task requires.
- No opportunistic refactors, drive-by renames, or unrelated cleanups inside a feature change.
- Do not modify or remove comments and code you do not fully understand, even if they look unused.
- If a refactor is needed, propose it as a separate task.

### 4. Goal-Driven Execution
- Before writing code, define explicit success criteria (what must be true for this to be done).
- Loop: implement → verify against criteria → fix gaps → repeat until all criteria pass.
- Do not declare a task complete based on "looks right." Verify.

---

## Standard Workflow

1. Read the relevant files in the codebase to understand context.
2. Produce a plan that includes:
   - A todo list of concrete steps
   - Explicit assumptions you are making
   - Tradeoffs you considered
   - Success criteria for the task
3. Wait for my approval of the plan before writing any code.
4. Work through the todo items, marking them complete as you go.
5. After each step, give me a high-level summary of what changed (no code dumps unless asked).
6. Verify against success criteria before declaring done.

---

## Project Conventions

### Language
- Python is the default language unless I explicitly specify another.
- For web apps: vanilla HTML5 and CSS. No JS frameworks (React, Vue, Svelte, etc.) unless I ask.

### Naming
- Use `PascalCase` for all new files, variables, classes, functions, and methods.
- Do not use `snake_case`, even where PEP 8 would recommend it.
- Constants: `UPPER_SNAKE_CASE`.

### Class Design
- One class per file when the class is meant to be reusable across programs.
- Every class gets a `#` comment block immediately above its definition describing:
  - What it does
  - Its main entry points (public methods)
  - Any external dependencies (DB, API, hardware)
- Methods and functions get a `#` comment block of 3 lines max immediately above the definition, not docstrings.

### Code Reuse
- Prefer utility classes and helper functions over duplicating logic.
- If the same block appears twice, extract it on the second occurrence (not the first — see Simplicity First).

---

## Code Quality

### Resource Management
- Always close database connections, cursors, files, and sockets via:
  - Context managers (`with` blocks) — preferred
  - Or `try` / `except` / `finally` when context managers are not available
- Never rely on garbage collection to release resources.

### Logging
- Use the `logging` module, not `print`.
- Structured logs with levels: `INFO` for normal flow, `WARNING` for recoverable issues, `ERROR` for failures.
- Include timestamps and module name in the log format.

### Error Handling
- Catch specific exceptions, not bare `except:`.
- Error messages must explain what failed and what state the system is in.
- Do not swallow exceptions silently — log or re-raise.

### Performance
- For database operations: batch queries when possible, avoid N+1 patterns, use indexes.
- Do not optimize prematurely — profile first if performance is in question.

---

## Output Style

- No emojis.
- No checkmarks, decorative arrows, or non-standard graphical characters.
- Plain ASCII for code comments and log messages.

## Communication Style

- Do not use filler phrases that imply honesty is a special mode: "to be honest", "honestly", "being frank", "in truth", "siendo honesto", "para serte franco", and equivalents in any language. They suggest dishonesty is the default, which weakens every other statement.
- Be direct. State conclusions and reasoning without preamble that announces what you are about to do ("let me explain", "I'll walk you through").
- Push back when you disagree with a decision. Do not soften technical objections with deference.

---

## Maintenance

Update this file when significant architectural changes are made (new major dependencies, structural reorganization, changes to entry points).
