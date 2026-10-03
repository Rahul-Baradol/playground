# Agent guide: code-playground

This repo holds **practice codebases** for the user to improve as a software
engineer. Each top-level folder is one self-contained challenge: a realistic,
working Python project with 2–3 deliberately planted **efficiency bugs**. The
user finds them, fixes them, and proves the fix with a benchmark.

## Creating a new challenge

### 1. Ask before building
Use AskUserQuestion. Put a recommended default first. Ask about:
- **Domain:** backend service, CLI tool, LLM-interfacing service, job queue, etc.
- **Level:** beginner, intermediate (1–3 yrs), or senior. This sets how subtle the bugs are.
- **Answer delivery:** hints + sealed solutions (default), no hints, or review-only.
- **Tooling:** tests + benchmark (default), tests only, or neither.
- **Bug mix:** say up front whether any fix lives in the schema or config (e.g.
  an index) rather than in Python logic. The user asked about this after the
  fact on `linkly`, so confirm it early.

Skip any question already answered below under *User profile*, unless the user
wants to change it.

### 2. Project rules
- One folder per challenge at the repo root, with a short lowercase name.
  Add a row for it to the root `README.md` table.
- Python, modern idioms (3.10+), and a `requirements.txt`. It must **run fully
  offline** with no API keys. LLM projects ship a mock client that a real
  client can be swapped in for.
- Create a `.venv` inside the challenge folder and install dependencies there.
  Add a `.gitignore` (venv, `__pycache__`, `*.db`, caches).
- The code should look like clean, competent production code: clear layout,
  type hints, a sensible layering of routes → services → repository.
- **Never leave hints in the code.** No comments, names or TODOs that point at
  a bug.

### 3. Bug rules
- Plant 2–3 bugs. They are **efficiency bugs, not correctness bugs**: the full
  test suite must pass with every bug in place.
- Each bug sits in a different file and maps to exactly one symptom or incident.
- Each bug must be something a real engineer could plausibly write and have
  pass code review.
- Each bug must show **superlinear growth** in the benchmark as data or
  uptime grows.
- Mix the categories, and avoid repeating ones already used (see *Challenge log*):
  query patterns, database schema or indexes, algorithmic complexity,
  in-process state or memory growth, concurrency or blocking I/O, caching,
  serialization.
- Include at least one healthy fast path as a **control** (growth ≈ 1×), so the
  user learns what *not* to optimize.
- Bugs can compound, e.g. a missing index that makes an N+1 pattern much worse.
  That's a good teaching point. Explain it in the solutions.

### 4. Files every challenge ships
- `README.md`: what the app does, its endpoints or commands, setup, run, test,
  benchmark, and layout. Ends by pointing to `CHALLENGE.md`.
- `CHALLENGE.md` contains:
  - Ground rules: measure first (`--save before.json`), keep tests green,
    prove the fix (`--compare`), write a regression test per bug, and write
    up each bug.
  - One **incident report per bug**, describing symptoms only, the way a user
    or on-call engineer would write it.
  - A general "tools worth knowing" hint, then **3 progressive hints per bug**
    in `<details>` blocks, from vague to nearly the answer.
  - Stretch goals: open-ended design questions, not more planted bugs.
- `SOLUTIONS.md`:
  - A spoiler warning followed by blank-line padding.
  - A table of reference before/after numbers.
  - For each bug: location, root cause, fix code, a regression test, and a one-line lesson.
  - A "Things that were *not* bugs" section.
- `tests/`: a pytest suite. It runs against a temp DB, uses fake clocks for
  time-based logic, and passes with the bugs in place.
- `scripts/seed.py`: generates realistic fake data with a fixed RNG seed.
- `scripts/benchmark.py`:
  - Runs each scenario at SMALL and LARGE scale.
  - Prints a median-ms table with a `growth` column.
  - Supports `--quick`, `--save FILE` and `--compare FILE`.

### 5. Verify before handing over
Don't skip any of these steps.
1. `pytest -q` passes on the buggy code.
2. The benchmark shows clear superlinear growth for each bug and ≈1× for the control.
3. Copy the project to the scratchpad and apply the reference fixes **there**.
   Never apply them in the challenge folder. Confirm the tests still pass and
   the speedup is real.
4. Each regression test in `SOLUTIONS.md` **fails on the buggy code and passes
   on the fixed copy**.
5. The numbers in `SOLUTIONS.md` come from these real runs. Never estimate them.

### 6. Handing over
Report the measured baseline table and what was verified, and **don't name the
bugs**. Offer to review the user's fixes later.

## Reviewing the user's attempts
- Run `pytest -q` and the benchmark (`--compare` if a baseline exists) against
  their changes, and report the results as they are.
- Give hints, not answers. Point to the symptom or the line ("what does
  `mapping.get(id)` return for a link with no clicks?") rather than writing the fix.
- Also point out design issues, e.g. a method placed in the wrong repository
  class, and say clearly that it isn't a bug.
- Don't edit the user's challenge code unless they ask.

## User profile
- Intermediate level (1–3 yrs).
- Prefers incident-style symptoms, progressive hints and a sealed solutions file.
- Wants tests + a benchmark included.
- Enjoys this format. Keep it consistent.

## Challenge log
Update this table whenever a challenge is added.

| Folder | Domain | Level | Bug categories used |
|---|---|---|---|
| `linkly` | URL shortener + analytics (FastAPI, SQLite) | Intermediate | N+1 queries; index on the wrong column (schema); unbounded in-memory state in the rate limiter |
