# Global Coding Policy (Strict No-Fallback by Default)

Scope: This file defines global behavior for the entire repository unless a user explicitly overrides it.

This is a Windows computer.

## 1. No fallback by default
- Do not introduce fallback, graceful degradation, or compatibility shims unless the user explicitly asks for them.
- Do not proactively add backup branches "just in case".

## 2. Fail fast on missing prerequisites
- If required inputs, services, schema, or dependencies are missing, stop and report clearly.
- Surface the exact missing precondition and the impact.

## 3. No silent downgrade
- Do not swallow exceptions.
- Do not silently switch data source, model, API, or algorithm.
- Do not return mock, placeholder, or default-success values to hide failures.

## 4. Ask before ambiguity-driven fallback
- If a fallback path is possible but not explicitly required, ask the user first.
- Keep the question concise and action-oriented.

## 5. If fallback is explicitly requested
- Implement the minimal fallback only within the requested scope.
- Mark fallback paths clearly in code and logs.
- State trigger conditions, risk, and rollback or removal strategy.

## 6. Refactor and review guidance
- Prefer removing implicit fallback branches during refactor unless they are required by explicit requirements, compliance, or SLO policy.
- If keeping a fallback is necessary, document why it must exist.

## Test server deployment
- The current deployment target is the test server, even though the helper script filename still says "production".
- Preferred entrypoint: `python tool\deploy\publish_to_server.py` from the repository root.
- Convenience wrapper: `一键发布到生产排期服务器.bat`, which only changes to the repo root and runs the Python deploy script.
- Deployment config lives in `tool\deploy\deploy-config.json`.
- Do not write credentials into docs, commits, or logs.
- The deploy script packages the current workspace and excludes `.git`, `.codex`, `node_modules`, `.next`, `_tmp`, `logs`, `.logs`, `__pycache__`, `.pytest_cache`, and `productionplan_deploy.tar.gz`.
- Because the archive is built from the current workspace, uncommitted local changes are also deployed if they exist.
- The script uploads the archive to the remote deployment directory configured in `tool\deploy\deploy-config.json`, recreates the remote app directory, extracts the archive, and runs `docker compose -f docker-compose.prod.yml up -d --build --remove-orphans`.
- After deployment, the script checks backend health at `http://127.0.0.1:8000/api/health` and frontend health at `http://127.0.0.1:2798`, then lists `productionplan` containers.
- If packaging, upload, remote compose, or either health check fails, stop immediately and report the exact failing step. Do not add fallback deployment logic.
