# Test Report

- Task ID: task-61cb339d1c-20260419T011916
- Date (local): 2026-04-19
- Tester mode: blind-first-pass
- Withheld artifacts not inspected before initial verdict: execution-log.md, task-state.json

## Environment Used

- Evaluation mode: blind-first-pass
- Validation surface: real-runtime
- Tools: pytest, npm
- Initial readable artifacts: prd.md, test-plan.md
- Initial withheld artifacts: execution-log.md, task-state.json
- Initial verdict before withheld inspection: yes

- OS: Windows (win32)
- Shell: PowerShell 5.1.26100.3624
- Repo root (cwd): D:\ProjectPackage\ProductionPlan
- Python: 3.12.10
- pytest: 9.0.2
- Node.js: v24.12.0
- npm: 11.6.2
- git: 2.51.2.windows.1

- Preconditions:
  - fronted/node_modules present
  - Command run: `Test-Path "D:\ProjectPackage\ProductionPlan\fronted\node_modules"`
  - Evidence refs: inline (PowerShell output `True` recorded during test execution)

## Initial Verdict (Blind First Pass)

PASS (T1-T4 all PASS so far; withheld artifacts not inspected.)

## Results

### T1: Backend provider/runtime Entry Regression

- Covers: P1-AC1, P1-AC2, P1-AC3
- Result: passed
- Command run: `python -m pytest backend/tests/test_app_service_provider.py`
- Environment proof: Ran in repo root `D:\ProjectPackage\ProductionPlan` with Python 3.12.10 (win32).
- Evidence refs: inline (pytest output in this report; `2 passed`)
- Notes: Exit code 0.

### T2: Backend Legacy Query Entry Regression

- Covers: P3-AC1
- Result: passed
- Command run: `python -m pytest backend/tests/test_app_service_process_timeline.py backend/tests/test_app_service_schedule_trust.py`
- Environment proof: Ran in repo root `D:\ProjectPackage\ProductionPlan` with Python 3.12.10 (win32).
- Evidence refs: inline (pytest output in this report; `14 passed`)
- Notes: Exit code 0.

### T3: Backend Dispatch Path Regression

- Covers: P1-AC1, P3-AC1
- Result: passed
- Command run: `python -m pytest backend/tests/test_app_service_batch_dispatch.py`
- Environment proof: Ran in repo root `D:\ProjectPackage\ProductionPlan` with Python 3.12.10 (win32).
- Evidence refs: inline (pytest output in this report; `8 passed`)
- Notes: Exit code 0.

### T4: Frontend Legacy App Shell Static Validation (Lint)

- Covers: P2-AC1, P2-AC2, P2-AC3, P3-AC2
- Result: passed
- Command run: `npm run lint` (cwd: `D:\ProjectPackage\ProductionPlan\fronted`)
- Environment proof: Ran in `D:\ProjectPackage\ProductionPlan\fronted` with Node.js v24.12.0 and npm 11.6.2.
- Evidence refs: inline (eslint completed with exit code 0)
- Notes: Output included `> fronted@0.1.0 lint` and `> eslint`.

### T5: Test Report Structure Validation

- Covers: P3-AC3
- Result: passed
- Command run: `python C:\Users\BJB110\.codex\skills\spec-driven-delivery\scripts\validate_test_report.py --cwd D:\ProjectPackage\ProductionPlan --task-id task-61cb339d1c-20260419T011916`
- Environment proof: Ran in repo root `D:\ProjectPackage\ProductionPlan` with Python 3.12.10 (win32). Note: validator reads `task-state.json` as part of its workflow; this was executed after the initial verdict.
- Evidence refs: inline (validator output: `status: ok`)
- Notes: Exit code 0. Validation was re-run after updating this report; the final run printed `status: ok`.

## Final Verdict

- Outcome: passed
- Verified acceptance ids: P1-AC1, P1-AC2, P1-AC3, P2-AC1, P2-AC2, P2-AC3, P3-AC1, P3-AC2, P3-AC3
- Blocking prerequisites:
- Summary: All planned tests (T1-T5) passed on real-runtime. Backend pytest suites passed (2 + 14 + 8 tests) and frontend `npm run lint` exited 0. Report structure validated by `validate_test_report.py` with `status: ok`.
