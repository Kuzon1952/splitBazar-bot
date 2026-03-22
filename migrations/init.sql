-- Users table
CREATE TABLE IF NOT EXISTS users (
    id BIGINT PRIMARY KEY,
    username VARCHAR(255),
    first_name VARCHAR(255) NOT NULL,
    last_name VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Groups table
CREATE TABLE IF NOT EXISTS groups (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    currency VARCHAR(10) DEFAULT 'RUB',
    invite_code VARCHAR(10) UNIQUE NOT NULL,
    admin_id BIGINT REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Group members table
CREATE TABLE IF NOT EXISTS group_members (
    id SERIAL PRIMARY KEY,
    group_id INTEGER REFERENCES groups(id),
    user_id BIGINT REFERENCES users(id),
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    left_at TIMESTAMP DEFAULT NULL,
    UNIQUE(group_id, user_id)
);

-- Expenses table
CREATE TABLE IF NOT EXISTS expenses (
    id SERIAL PRIMARY KEY,
    group_id INTEGER REFERENCES groups(id),
    paid_by BIGINT REFERENCES users(id),
    total_amount DECIMAL(10,2) NOT NULL,
    shared_amount DECIMAL(10,2) NOT NULL,
    personal_amount DECIMAL(10,2) DEFAULT 0,
    split_type VARCHAR(20) DEFAULT 'equal',
    description VARCHAR(255),
    receipt_file_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Expense splits table
CREATE TABLE IF NOT EXISTS expense_splits (
    id SERIAL PRIMARY KEY,
    expense_id INTEGER REFERENCES expenses(id),
    user_id BIGINT REFERENCES users(id),
    amount DECIMAL(10,2) NOT NULL,
    percentage DECIMAL(5,2),
    is_paid BOOLEAN DEFAULT FALSE
);

-- Budget targets table
CREATE TABLE IF NOT EXISTS budget_targets (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(id),
    group_id INTEGER REFERENCES groups(id),
    target_amount DECIMAL(10,2) NOT NULL,
    month INTEGER NOT NULL,
    year INTEGER NOT NULL,
    UNIQUE(user_id, group_id, month, year)
);