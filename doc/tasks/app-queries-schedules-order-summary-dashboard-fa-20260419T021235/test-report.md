# Test Report

- Task ID: `app-queries-schedules-order-summary-dashboard-fa-20260419T021235`
- Date: `2026-04-19`
- Tester: independent (blind-first-pass)

## Environment Used

- Evaluation mode: blind-first-pass
- Validation surface: real-runtime
- Tools: python, pytest, powershell
- Initial readable artifacts: prd.md, test-plan.md
- Initial withheld artifacts: execution-log.md, task-state.json
- Initial verdict before withheld inspection: yes

## Results

### T1: facade provider delegate wiring

- Result: passed
- Covers: P1-AC2, P2-AC2, P3-AC1
- Command run: `python -m pytest backend/tests/test_schedules_query_facade.py backend/tests/test_order_summary_query_facade.py backend/tests/test_dashboard_query_facade.py`
- Environment proof: `Python 3.12.10` + `pytest 9.0.2` on `platform win32`
- Evidence refs: pytest stdout (6 passed)
- Notes: All 3 facade/provider unit tests passed (6 passed).

### T2: app_queries routing delegates to facades

- Result: passed
- Covers: P1-AC1, P2-AC1, P3-AC1
- Command run: `python -m pytest backend/tests/test_app_queries_schedule_summary_dashboard_facades.py`
- Environment proof: `Python 3.12.10` + `pytest 9.0.2` on `platform win32`
- Evidence refs: pytest stdout (2 passed)
- Notes: Route-layer delegation tests passed (2 passed).

### T3: test-report structure validation

- Result: passed
- Covers: P3-AC2
- Command run: `python C:\Users\BJB110\.codex\skills\spec-driven-delivery\scripts\validate_test_report.py --cwd D:\ProjectPackage\ProductionPlan --task-id app-queries-schedules-order-summary-dashboard-fa-20260419T021235`
- Environment proof: `Python 3.12.10` on Windows PowerShell, repo root `D:\ProjectPackage\ProductionPlan`
- Evidence refs: validate_test_report.py stdout (status: ok)
- Notes: Validator returned `status: ok`. This command reads withheld `task-state.json` as part of validation, and it was only run after Initial Verdict was written.

## Initial Verdict

- Outcome: pending
- Summary: T1/T2 are passing in the real repo runtime; withholding `execution-log.md` and `task-state.json` has been respected so far. Next step is to run T3 structure validation (which will read withheld artifacts via the validator).

## Final Verdict

- Outcome: passed
- Verified acceptance IDs: P1-AC1, P1-AC2, P2-AC1, P2-AC2, P3-AC1, P3-AC2
- Blocking prerequisites:
- Summary: T1/T2 pytest suites passed and T3 report-structure validation returned ok; acceptance criteria covered by the test plan are verified.
