# Test Plan Template

- Task ID: `task-5197e39be0-20260412T114914`
- Created: `2026-04-12T11:49:14`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `Remove frontend garbled text, English copy, and informal descriptions; unify to formal Chinese copy.`

## Test Scope
- Validate that the sidebar navigation, layout metadata, scheduler dashboard, daily capacity page, test tools page, and the rendered schedule calendar page heading all render the formal Chinese copy introduced in P1.
- Out of scope: backend API correctness, data seeding apart from what Playwright already bootstraps, and non-user-facing constants that are never shown in the UI.

## Environment
- Start from a clean workspace with `npm install` executed inside `fronted` and Playwright browsers installed via `npx playwright install`.
- The backend must be reachable via the configured `PRODUCTION_PLAN_E2E_DB_PATH` (or the default SQLite DB) since Playwright’s config boots `uvicorn` before the browser tests.
- Tests run on the `fronted` project using Node.js 20+.

## Accounts and Fixtures
- The built-in scheduler and workshop-manager accounts defined in `fronted/tests/e2e/support/constants.ts` (e.g., `ACCOUNTS.scheduler`, `ACCOUNTS.manager`) provide authentication for the relevant flows.
- Existing seeded data for dashboard metrics, daily capacity, and order pools is relied on and must exist in the E2E SQLite database prior to running the copy verification spec.
- If any required account or seed data is missing, fail fast and note the missing prerequisite in `test-report.md` before continuing.

## Commands
1. `cd fronted && npm install` (once per machine; ensures Next.js and Playwright dependencies are ready).
2. `cd fronted && npx playwright install` (installs Chromium for the real-browser validation).
3. `cd fronted && node .\scripts\run-e2e-browser.mjs tests/e2e/copy-verification.spec.ts` (seeds a deterministic runtime database, launches the real backend + frontend through `playwright.config.ts`, and captures screenshot/trace evidence for the copy verification spec).

## Test Cases
### T1: Sidebar, dashboard, and metadata copy check
- Covers: P1-AC1
- Level: e2e
- Command: `cd fronted && node .\scripts\run-e2e-browser.mjs tests/e2e/copy-verification.spec.ts --grep "T1 "`
- Expected: Every sidebar link, the HTML `<title>`/`<meta description>`, and the scheduler dashboard headings render the agreed-upon formal Chinese copy; Playwright captures screenshot/trace evidence under `fronted/test-results/e2e`.

### T2: Daily capacity, test tools, and calendar page heading copy check
- Covers: P2-AC1
- Level: e2e
- Command: `cd fronted && node .\scripts\run-e2e-browser.mjs tests/e2e/copy-verification.spec.ts --grep "T2 "`
- Expected: The daily capacity controls, reporting hints, test-tools tabs/buttons, and the rendered schedule calendar heading `月历视图` are all formal Chinese without English/transliteration; artifacts (video/screenshot) are captured and referenced in `test-report.md`.

### T3: Execution log copy mapping documented
- Covers: P1-AC2
- Level: manual
- Command: `cd doc/tasks/task-5197e39be0-20260412T114914 && cat execution-log.md`
- Expected: The execution log contains a table showing each replaced string (old vs. new) so reviewers can verify the documented copy decisions; record the check in `test-report.md`.

## Coverage Matrix
| Case ID | Area | Scenario | Level | Acceptance IDs | Evidence |
| --- | --- | --- | --- | --- | --- |
| T1 | Sidebar + dashboard | Rendered navigation, metadata, and scheduler dashboard copy | e2e | P1-AC1 | `test-report.md`, screenshot/trace under `fronted/test-results/e2e` |
| T2 | Daily capacity + test tools + calendar page heading | Rendered copy on the daily capacity, test tools, and schedule calendar page flows | e2e | P2-AC1 | `test-report.md`, Playwright screenshot/trace |
| T3 | Execution log | Documentation of old vs. new strings | manual | P1-AC2 | `test-report.md`, execution-log.md entry |

## Evaluator Independence
- Mode: blind-first-pass
- Validation surface: real-browser
- Required tools: playwright
- First-pass readable artifacts: prd.md, test-plan.md
- Withheld artifacts: execution-log.md, task-state.json
- Real environment expectation: Launch the real Playwright runtime defined in `fronted/playwright.config.ts` so the tester observes copy on the live UI instead of in a mocked frame.
- Escalation rule: Do not inspect withheld artifacts until an initial verdict is produced or the main agent explicitly requests reconsideration.

## Pass / Fail Criteria
- Pass when every inspected UI element renders formal Chinese copy (no English/garbled text) and the Playwright command from the `Commands` section succeeds with screenshots/videos attached to `test-report.md`.
- Fail when any targeted element still shows English, mojibake, or an informal phrase, or if the Playwright command errors out (missing services, auth failure, or the copy assertions fail).

## Regression Scope
- Sidebar links and metadata (layout.tsx).
- Scheduler dashboard metrics and Top N filter.
- Daily capacity page hints, buttons, and reporting actions.
- Test tools tabs, controls, and result table headings.
- Schedule calendar header button text/labels.

## Reporting Notes
- Record the Playwright run outcomes in `test-report.md`, including the command, user account used, observed URLs, and embedded references to any generated screenshots/traces under `fronted/test-results/e2e`.
