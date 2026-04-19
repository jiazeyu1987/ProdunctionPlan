# PRD Template

- Task ID: `appservice-query-service-reporting-masterdata-sc-20260419T031941`
- Created: `2026-04-19T03:19:41`
- Workspace: `D:\ProjectPackage\ProductionPlan`
- User Request: `继续模块化重构：清理 AppService 中已委托到 query service 的不可达旧实现体，移除 reporting、masterdata、schedules、order-summary、dashboard 查询域的死代码并保持现有测试通过`

## Goal

Describe the intended outcome in behavior or product terms.

## Scope

List the modules, systems, user flows, or files that are explicitly in scope.

## Non-Goals

List work that must not be silently pulled into this task.

## Preconditions

List required services, credentials, fixtures, feature flags, environment variables, tools, or schemas.

If any item is missing, stop and record it in `task-state.json.blocking_prereqs`.

## Impacted Areas

List the likely entry points, callers, downstream consumers, tests, contracts, configs, or docs that may need changes.

## Phase Plan

Use stable phase ids. Do not renumber ids after execution has started.

### P1: [title]

- Objective:
- Owned paths:
- Dependencies:
- Deliverables:

Add one subsection per phase. Keep each phase reviewable and independently verifiable.

## Phase Acceptance Criteria

List criteria under the matching phase id. Every criterion must use a stable acceptance id.

### P1

- P1-AC1:
- P1-AC2:
- Evidence expectation:

Repeat for every phase in the same order used in `## Phase Plan`.

## Done Definition

List the conditions that must be true for the full task to count as complete.

At minimum, completion requires all phases completed and evidence for each acceptance id in `execution-log.md` or `test-report.md`.

## Blocking Conditions

List the conditions that must stop execution instead of triggering fallback, mock behavior, or silent downgrade.
