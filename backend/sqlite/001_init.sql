PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS production_orders (
    production_order_no TEXT PRIMARY KEY,
    material_code TEXT NOT NULL,
    material_name TEXT NOT NULL,
    material_specification TEXT,
    production_qty REAL NOT NULL,
    status TEXT NOT NULL,
    planned_start_date TEXT,
    planned_end_date TEXT,
    source_bill_no TEXT,
    material_list_no TEXT,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_production_orders_status_start
    ON production_orders (status, planned_start_date);

CREATE INDEX IF NOT EXISTS idx_production_orders_material_code
    ON production_orders (material_code);

CREATE TABLE IF NOT EXISTS material_issue_items (
    production_order_no TEXT NOT NULL,
    child_material_code TEXT NOT NULL,
    child_material_name TEXT NOT NULL,
    spec_model TEXT,
    issue_qty REAL,
    supply_type_code TEXT,
    supply_type_name TEXT,
    inventory_qty REAL,
    inventory_status TEXT NOT NULL DEFAULT 'UNKNOWN',
    usage_numerator REAL,
    usage_denominator REAL,
    child_unit TEXT,
    expandable INTEGER NOT NULL DEFAULT 0,
    display_order INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (production_order_no, child_material_code),
    FOREIGN KEY (production_order_no) REFERENCES production_orders (production_order_no) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_material_issue_items_order_no
    ON material_issue_items (production_order_no, display_order);

CREATE INDEX IF NOT EXISTS idx_material_issue_items_child_material
    ON material_issue_items (child_material_code);

CREATE TABLE IF NOT EXISTS bom_children (
    parent_material_code TEXT NOT NULL,
    child_material_code TEXT NOT NULL,
    child_material_name TEXT NOT NULL,
    child_specification TEXT,
    usage_numerator REAL,
    usage_denominator REAL,
    child_unit TEXT,
    supply_type_code TEXT,
    supply_type_name TEXT,
    inventory_qty REAL,
    inventory_status TEXT NOT NULL DEFAULT 'UNKNOWN',
    expandable INTEGER NOT NULL DEFAULT 0,
    display_order INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (parent_material_code, child_material_code)
);

CREATE INDEX IF NOT EXISTS idx_bom_children_parent_material
    ON bom_children (parent_material_code, display_order);

CREATE TABLE IF NOT EXISTS inventory_cache (
    material_code TEXT PRIMARY KEY,
    inventory_qty REAL,
    inventory_status TEXT NOT NULL,
    snapshot_time TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_inventory_cache_status_time
    ON inventory_cache (inventory_status, snapshot_time);

CREATE TABLE IF NOT EXISTS material_supply_cache (
    material_code TEXT PRIMARY KEY,
    supply_type_code TEXT NOT NULL,
    supply_type_name TEXT NOT NULL,
    snapshot_time TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS work_reports (
    report_id TEXT PRIMARY KEY,
    production_order_no TEXT NOT NULL,
    process_code TEXT,
    process_name TEXT,
    workshop_code TEXT,
    workshop_name TEXT,
    line_code TEXT,
    line_name TEXT,
    report_qty REAL NOT NULL,
    report_time TEXT NOT NULL,
    operator_name TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (production_order_no) REFERENCES production_orders (production_order_no) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_work_reports_order_no
    ON work_reports (production_order_no, report_time DESC);

CREATE TABLE IF NOT EXISTS capacity_bindings (
    production_order_no TEXT NOT NULL,
    process_code TEXT NOT NULL,
    workshop_code TEXT NOT NULL,
    line_code TEXT NOT NULL,
    process_name TEXT,
    workshop_name TEXT,
    line_name TEXT,
    capacity_qty REAL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (production_order_no, process_code, workshop_code, line_code),
    FOREIGN KEY (production_order_no) REFERENCES production_orders (production_order_no) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_capacity_bindings_order_no
    ON capacity_bindings (production_order_no);

CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_key TEXT NOT NULL,
    request_id TEXT UNIQUE,
    status TEXT NOT NULL,
    progress INTEGER NOT NULL DEFAULT 0,
    payload_json TEXT NOT NULL,
    result_json TEXT,
    error_code TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_status_created
    ON jobs (status, created_at);

CREATE INDEX IF NOT EXISTS idx_jobs_target
    ON jobs (target_type, target_key, created_at DESC);

CREATE TABLE IF NOT EXISTS order_pool_state (
    production_order_no TEXT PRIMARY KEY,
    promised_due_date TEXT,
    expected_start_date TEXT,
    expected_start_time TEXT,
    expected_finish_time TEXT,
    priority_level INTEGER NOT NULL DEFAULT 5,
    urgent_flag INTEGER NOT NULL DEFAULT 0,
    lock_flag INTEGER NOT NULL DEFAULT 0,
    frozen_flag INTEGER NOT NULL DEFAULT 0,
    status TEXT,
    order_status TEXT,
    completed_qty REAL,
    remaining_qty REAL,
    progress_rate REAL,
    production_batch_no TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (production_order_no) REFERENCES production_orders (production_order_no) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_order_pool_state_status
    ON order_pool_state (status, expected_start_date);

CREATE TABLE IF NOT EXISTS schedule_versions (
    version_no TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    status_name_cn TEXT NOT NULL,
    strategy_code TEXT NOT NULL,
    created_at TEXT NOT NULL,
    published_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_schedule_versions_status_created
    ON schedule_versions (status, created_at);

CREATE TABLE IF NOT EXISTS schedule_tasks (
    version_no TEXT NOT NULL,
    task_no INTEGER NOT NULL,
    production_order_no TEXT NOT NULL,
    process_code TEXT NOT NULL,
    process_name_cn TEXT,
    calendar_date TEXT NOT NULL,
    shift_code TEXT NOT NULL,
    plan_qty REAL NOT NULL,
    plan_start_time TEXT,
    PRIMARY KEY (version_no, task_no),
    FOREIGN KEY (version_no) REFERENCES schedule_versions (version_no) ON DELETE CASCADE,
    FOREIGN KEY (production_order_no) REFERENCES production_orders (production_order_no) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_schedule_tasks_date_process
    ON schedule_tasks (calendar_date, process_code);

CREATE INDEX IF NOT EXISTS idx_schedule_tasks_order_no
    ON schedule_tasks (production_order_no, calendar_date);

CREATE TABLE IF NOT EXISTS schedule_calendar_rules (
    singleton_key TEXT PRIMARY KEY,
    horizon_start_date TEXT,
    horizon_days INTEGER NOT NULL,
    skip_statutory_holidays INTEGER NOT NULL DEFAULT 0,
    weekend_rest_mode TEXT NOT NULL,
    date_shift_mode_by_date_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

INSERT OR IGNORE INTO schedule_calendar_rules (
    singleton_key,
    horizon_start_date,
    horizon_days,
    skip_statutory_holidays,
    weekend_rest_mode,
    date_shift_mode_by_date_json,
    updated_at
) VALUES (
    'default',
    date('now', 'localtime'),
    31,
    0,
    'DOUBLE',
    '{}',
    datetime('now')
);

CREATE TABLE IF NOT EXISTS simulation_state (
    singleton_key TEXT PRIMARY KEY,
    current_date TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

INSERT OR IGNORE INTO simulation_state (
    singleton_key,
    current_date,
    updated_at
) VALUES (
    'default',
    date('now', 'localtime'),
    datetime('now')
);

CREATE TABLE IF NOT EXISTS masterdata_process_routes (
    product_code TEXT NOT NULL,
    sequence_no INTEGER NOT NULL,
    process_code TEXT NOT NULL,
    process_name_cn TEXT,
    dependency_type TEXT,
    route_no TEXT NOT NULL,
    route_name_cn TEXT NOT NULL,
    product_name_cn TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (product_code, sequence_no)
);

CREATE INDEX IF NOT EXISTS idx_masterdata_process_routes_product
    ON masterdata_process_routes (product_code, sequence_no);

CREATE TABLE IF NOT EXISTS masterdata_line_topology (
    company_code TEXT NOT NULL,
    workshop_code TEXT NOT NULL,
    workshop_name TEXT,
    line_code TEXT NOT NULL,
    line_name TEXT,
    process_code TEXT NOT NULL,
    capacity_per_shift REAL NOT NULL,
    required_workers INTEGER NOT NULL,
    required_machines INTEGER NOT NULL,
    enabled_flag INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (company_code, workshop_code, line_code, process_code)
);

CREATE INDEX IF NOT EXISTS idx_masterdata_line_topology_process
    ON masterdata_line_topology (process_code, enabled_flag);

CREATE TABLE IF NOT EXISTS dispatch_commands (
    command_id TEXT PRIMARY KEY,
    target_order_no TEXT NOT NULL,
    command_type TEXT NOT NULL,
    status TEXT NOT NULL,
    effective_time TEXT,
    reason TEXT,
    created_by TEXT,
    approver TEXT,
    decision TEXT,
    decision_reason TEXT,
    decision_time TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (target_order_no) REFERENCES production_orders (production_order_no) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_dispatch_commands_order_created
    ON dispatch_commands (target_order_no, created_at DESC);

CREATE TABLE IF NOT EXISTS app_users (
    user_id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    password_salt TEXT NOT NULL,
    role_code TEXT NOT NULL,
    enabled_flag INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_app_users_role
    ON app_users (role_code, enabled_flag);

CREATE TABLE IF NOT EXISTS app_sessions (
    session_token TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    FOREIGN KEY (user_id) REFERENCES app_users (user_id)
);

CREATE INDEX IF NOT EXISTS idx_app_sessions_user
    ON app_sessions (user_id, revoked_at, expires_at);

CREATE TABLE IF NOT EXISTS daily_line_capacity_plan (
    calendar_date TEXT NOT NULL,
    company_code TEXT NOT NULL,
    workshop_code TEXT NOT NULL,
    line_code TEXT NOT NULL,
    process_code TEXT NOT NULL,
    planned_capacity_qty REAL NOT NULL,
    worker_count INTEGER,
    machine_count INTEGER,
    source_note TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (calendar_date, company_code, workshop_code, line_code, process_code)
);

CREATE INDEX IF NOT EXISTS idx_daily_line_capacity_plan_date
    ON daily_line_capacity_plan (calendar_date, workshop_code, line_code, process_code);

CREATE TABLE IF NOT EXISTS daily_line_capacity_actual (
    calendar_date TEXT NOT NULL,
    company_code TEXT NOT NULL,
    workshop_code TEXT NOT NULL,
    line_code TEXT NOT NULL,
    process_code TEXT NOT NULL,
    actual_capacity_qty REAL NOT NULL,
    report_count INTEGER NOT NULL DEFAULT 0,
    last_report_time TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (calendar_date, company_code, workshop_code, line_code, process_code)
);

CREATE INDEX IF NOT EXISTS idx_daily_line_capacity_actual_date
    ON daily_line_capacity_actual (calendar_date, workshop_code, line_code, process_code);

CREATE TABLE IF NOT EXISTS daily_line_capacity_plan_audit (
    audit_id TEXT PRIMARY KEY,
    calendar_date TEXT NOT NULL,
    company_code TEXT NOT NULL,
    workshop_code TEXT NOT NULL,
    line_code TEXT NOT NULL,
    process_code TEXT NOT NULL,
    old_planned_capacity_qty REAL,
    new_planned_capacity_qty REAL,
    old_worker_count INTEGER,
    new_worker_count INTEGER,
    old_machine_count INTEGER,
    new_machine_count INTEGER,
    operator_user_id TEXT,
    operator_username TEXT,
    operator_display_name TEXT,
    changed_at TEXT NOT NULL,
    FOREIGN KEY (operator_user_id) REFERENCES app_users(user_id)
);

CREATE INDEX IF NOT EXISTS idx_daily_line_capacity_plan_audit_date
    ON daily_line_capacity_plan_audit (calendar_date, changed_at DESC);

CREATE INDEX IF NOT EXISTS idx_daily_line_capacity_plan_audit_line
    ON daily_line_capacity_plan_audit (workshop_code, line_code, process_code, changed_at DESC);
