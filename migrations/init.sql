CREATE TABLE IF NOT EXISTS users (
    id BIGINT PRIMARY KEY,
    username VARCHAR(255),
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    inactivity_reminder BOOLEAN DEFAULT TRUE,
    large_expense_alert BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS groups (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    currency VARCHAR(10) NOT NULL,
    invite_code VARCHAR(10) UNIQUE NOT NULL,
    admin_id BIGINT REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_reset TIMESTAMP,
    is_locked BOOLEAN DEFAULT FALSE,
    reset_password VARCHAR(255),
    password_hint VARCHAR(255),
    group_name_lower VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS group_members (
    id SERIAL PRIMARY KEY,
    group_id INTEGER REFERENCES groups(id),
    user_id BIGINT REFERENCES users(id),
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    left_at TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS expenses (
    id SERIAL PRIMARY KEY,
    group_id INTEGER REFERENCES groups(id),
    paid_by BIGINT REFERENCES users(id),
    total_amount DECIMAL(10,2) NOT NULL,
    shared_amount DECIMAL(10,2) DEFAULT 0,
    personal_amount DECIMAL(10,2) DEFAULT 0,
    split_type VARCHAR(20) DEFAULT 'equal',
    description TEXT,
    receipt_file_id VARCHAR(255),
    expense_date DATE DEFAULT CURRENT_DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_by BIGINT REFERENCES users(id),
    deleted_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS expense_splits (
    id SERIAL PRIMARY KEY,
    expense_id INTEGER REFERENCES expenses(id),
    user_id BIGINT REFERENCES users(id),
    amount DECIMAL(10,2) NOT NULL,
    percentage DECIMAL(5,2),
    is_paid BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS budget_targets (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id),
    group_id INTEGER REFERENCES groups(id),
    target_amount DECIMAL(10,2) NOT NULL,
    month INTEGER NOT NULL,
    year INTEGER NOT NULL,
    UNIQUE(user_id, group_id, month, year)
);

CREATE TABLE IF NOT EXISTS edit_requests (
    id SERIAL PRIMARY KEY,
    expense_id INTEGER REFERENCES expenses(id),
    requested_by BIGINT REFERENCES users(id),
    group_id INTEGER REFERENCES groups(id),
    status VARCHAR(20) DEFAULT 'pending',
    requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    responded_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS todo_items (
    id SERIAL PRIMARY KEY,
    group_id INTEGER REFERENCES groups(id),
    added_by BIGINT REFERENCES users(id),
    item_name VARCHAR(255) NOT NULL,
    quantity VARCHAR(50),
    is_done BOOLEAN DEFAULT FALSE,
    done_by BIGINT REFERENCES users(id),
    done_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS group_messages (
    id SERIAL PRIMARY KEY,
    group_id INTEGER REFERENCES groups(id),
    user_id BIGINT REFERENCES users(id),
    message TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);