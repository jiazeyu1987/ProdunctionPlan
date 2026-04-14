# PRD

- Task ID: `excel-xlsx-20260413T195434`
- Created: `2026-04-13T19:54:34`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `Extend reporting to import the real workbook format, add strict resource mapping, support xlsx preview/commit, and keep same-day capacity compare working without fallback.`

## Goal

Enable the system to import real production reporting data from the provided multi-sheet `.xlsx` workbook instead of relying on the current simplified manual reporting model. The new flow must parse the workbook, validate each row strictly against existing master data and explicit resource mappings, persist the real business fields on `work_reports`, and keep the existing same-day capacity compare feature working through exact `report_local_date + workshop_code + line_code + process_code` matching.

## Scope

- Extend backend reporting storage so `work_reports` can persist the real workbook fields that are required by the business and UI.
- Add a strict resource mapping master-data table to map workbook `resource_group_name + resource_name + source_process_code` into the system `company_code + workshop_code + line_code + process_code`.
- Add `.xlsx` preview and commit APIs that parse multiple sheets, return row-level validation results, and only commit rows that pass strict validation.
- Upgrade the frontend reporting import flow from text-only import to workbook preview/commit with explicit row-level errors.
- Upgrade the reporting records table to display real workbook-backed fields instead of placeholder filler values while retaining the `当日产能` compare column.
- Cover the new backend and browser flows with targeted automated tests.

## Non-Goals

- Auto-create missing production orders, products, processes, or line master data from imported workbook rows.
- Guess workshop, line, process, or calendar date when mapping data is missing or ambiguous.
- Add fuzzy matching, heuristic mapping, or cross-line/cross-date fallback behavior.
- Backfill historical `work_reports` rows with the new fields.
- Add a large general-purpose resource mapping maintenance console beyond the minimum endpoints or fixtures needed for this task.
- Redesign the existing same-day capacity compare interaction beyond keeping it compatible with imported rows.

## Preconditions

- The repository remains readable and writable in `D:\ProjectPackage\ProductionPlan`.
- The backend SQLite schema can be updated through the repository init SQL and database bootstrap path.
- Python can read `.xlsx` files using available dependencies; if the parser dependency is missing, the task must stop and report it.
- The sample workbook [棘突 造影导管(1).xlsx](D:/ProjectPackage/%E6%A3%98%E7%AA%81%20%E9%80%A0%E5%BD%B1%E5%AF%BC%E7%AE%A1(1).xlsx) is available for inspection and test fixture extraction.
- The repo test harness can seed the minimum orders, products, processes, and mappings needed for success and failure-path validation.
- Existing same-day capacity compare behavior must remain strict and must not introduce fallback behavior.

## Impacted Areas

- `backend/app/db.py`
- `backend/sqlite/001_init.sql`
- `backend/app/services/app_service.py`
- `backend/app/api/routes/app_queries.py`
- `backend/app/api/routes/commands.py`
- `backend/app/services/job_dispatcher.py`
- `backend/tests/**`
- `fronted/src/legacy/features/execution-wip/**`
- `fronted/src/legacy/features/order-execution/**`
- `fronted/src/legacy/styles/**`
- `fronted/tests/e2e/**`

## Phase Plan

### P1: Extend reporting domain model and strict resource mapping

- Objective: Extend `work_reports` to persist the real workbook reporting fields and add a strict resource mapping table that resolves workbook resource information into workshop, line, and process scope.
- Owned paths: `backend/app/db.py`, `backend/sqlite/001_init.sql`, `backend/app/services/app_service.py`, `backend/app/api/routes/app_queries.py`, `backend/app/api/routes/commands.py`, `backend/app/services/job_dispatcher.py`, `backend/tests/`
- Dependencies: existing reporting command/query flow, existing line topology and capacity compare logic
- Deliverables: schema updates for `work_reports`, schema for reporting resource mappings, strict mapping helpers, reporting query response updates, backend tests for persistence and mapping behavior

### P2: Build xlsx preview and commit import pipeline

- Objective: Add fail-fast `.xlsx` preview and commit APIs that parse multiple workbook sheets, validate each row with explicit failure reasons, and persist only rows that pass strict validation.
- Owned paths: `backend/app/services/app_service.py`, `backend/app/api/routes/app_queries.py`, `backend/app/api/routes/commands.py`, `backend/app/services/job_dispatcher.py`, `backend/tests/`
- Dependencies: P1 schema and mapping helpers, available `.xlsx` parser dependency
- Deliverables: workbook preview API, workbook commit API/job flow, row-level validation results, explicit error handling for missing order or mapping and ambiguous mapping, backend tests for preview and commit

### P3: Upgrade frontend import and reporting UI to real workbook fields

- Objective: Replace the current text import flow with `.xlsx` preview/commit UX and update the reporting records table to display the real workbook fields while preserving the same-day capacity compare experience.
- Owned paths: `fronted/src/legacy/features/execution-wip/**`, `fronted/src/legacy/features/order-execution/**`, `fronted/src/legacy/styles/**`, `fronted/tests/e2e/**`
- Dependencies: P2 preview and commit APIs
- Deliverables: `.xlsx` file selection, preview and commit UI, row-level error display, reporting records table field updates, browser tests for success and failure paths, regression coverage for `当日产能` compare on imported rows

## Phase Acceptance Criteria

### P1

- P1-AC1: `work_reports` persists the required workbook business fields, including operator code and name, section leader name, dispatch number, product code, product name, product specification, resource group name, resource name, department name, and source workbook metadata, without breaking report queries.
- P1-AC2: A strict resource mapping table resolves `resource_group_name + resource_name + source_process_code` to exactly one `company_code + workshop_code + line_code + process_code`, and missing or ambiguous mappings produce explicit errors.
- P1-AC3: Reporting query responses expose the new persisted fields so the frontend no longer depends on placeholder filler or section-leader values.
- P1-AC4: Existing same-day capacity compare selection continues to rely on stored `report_local_date + workshop_code + line_code + process_code` values without fallback behavior.
- Evidence expectation: schema inspection or migration-backed assertions, backend unit tests for persistence and mapping, and code references showing query and compare compatibility

### P2

- P2-AC1: The backend preview flow parses the provided `.xlsx` workbook format across multiple sheets and preserves sheet name plus source row number in preview results.
- P2-AC2: Preview returns row-level validation results with explicit reasons for missing order, missing mapping, ambiguous mapping, invalid required fields, or other strict validation failures.
- P2-AC3: Commit persists only rows that passed preview validation and writes the mapped reporting fields plus workbook provenance into `work_reports`.
- P2-AC4: Commit does not invent default workshop, line, process, or master-data values when required data is missing; it fails explicitly instead.
- Evidence expectation: backend API or service tests for preview and commit, assertions on row-level validation payloads, and query assertions proving persisted source metadata and mapped keys

### P3

- P3-AC1: The frontend import flow accepts `.xlsx`, shows a preview before commit, and surfaces backend row-level validation results clearly to the user.
- P3-AC2: The reporting records table displays real report fields such as order number, dispatch number, product code, process code and name, resource, operator, section leader, quantity, and `当日产能`.
- P3-AC3: After importing rows with valid mappings, blank compare cells on imported reports still open the existing compare modal and keep the same strict same-day compare rules.
- P3-AC4: Browser validation covers one successful workbook import path and one explicit failure path from the real UI.
- Evidence expectation: frontend build output, Playwright evidence for preview and commit, and browser assertions showing imported rows still participate in capacity compare

## Done Definition

- All three phases are marked completed and every acceptance id has execution or test evidence.
- Backend schema and service tests pass for the extended reporting model, strict mapping logic, and workbook import flow.
- Frontend build passes with the upgraded import flow and records table.
- Browser validation demonstrates workbook preview, explicit row-level failures, successful commit, and post-import capacity compare compatibility.
- No fallback, silent default mapping, or silent master-data downgrade exists in the new import path.

## Blocking Conditions

- If `.xlsx` parsing dependencies are unavailable, stop and report the missing prerequisite.
- If a workbook row cannot resolve to exactly one mapping target, fail that row explicitly and do not commit it.
- If a referenced production order, product, or process prerequisite required by the strict import flow is missing, fail explicitly and do not auto-create it.
- If imported workbook fields conflict with the mapped scope or required master data, fail explicitly and do not commit the row.
- If real-browser validation cannot run, do not claim completion for the frontend phase.
