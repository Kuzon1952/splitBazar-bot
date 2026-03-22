from datetime import datetime
import random
import string
from bot.database.connection import get_connection


def generate_invite_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


# ─── USER QUERIES ───────────────────────────────────────

def save_user(user_id, username, first_name, last_name):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (id, username, first_name, last_name)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE
        SET username = %s, first_name = %s, last_name = %s
    """, (user_id, username, first_name, last_name,
          username, first_name, last_name))
    conn.commit()
    cursor.close()
    conn.close()


def get_user(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    return user


# ─── GROUP QUERIES ───────────────────────────────────────

def create_group(name, currency, admin_id):
    conn = get_connection()
    cursor = conn.cursor()
    invite_code = generate_invite_code()
    cursor.execute("""
        INSERT INTO groups (name, currency, invite_code, admin_id)
        VALUES (%s, %s, %s, %s)
        RETURNING id, invite_code
    """, (name, currency, invite_code, admin_id))
    result = cursor.fetchone()
    conn.commit()
    cursor.close()
    conn.close()
    return result


def join_group(invite_code, user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name FROM groups WHERE invite_code = %s
    """, (invite_code,))
    group = cursor.fetchone()
    if not group:
        cursor.close()
        conn.close()
        return None
    cursor.execute("""
        INSERT INTO group_members (group_id, user_id)
        VALUES (%s, %s)
        ON CONFLICT (group_id, user_id) DO NOTHING
        RETURNING id
    """, (group[0], user_id))
    conn.commit()
    cursor.close()
    conn.close()
    return group


def get_user_groups(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT g.id, g.name, g.currency, g.invite_code,
               g.admin_id, g.created_at
        FROM groups g
        JOIN group_members gm ON g.id = gm.group_id
        WHERE gm.user_id = %s AND gm.is_active = TRUE
    """, (user_id,))
    groups = cursor.fetchall()
    cursor.close()
    conn.close()
    return groups


def get_group_members(group_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.id, u.first_name, u.username, gm.joined_at
        FROM users u
        JOIN group_members gm ON u.id = gm.user_id
        WHERE gm.group_id = %s AND gm.is_active = TRUE
    """, (group_id,))
    members = cursor.fetchall()
    cursor.close()
    conn.close()
    return members

# ─── REPORT QUERIES ──────────────────────────────────────

def get_balances(group_id, start_date, end_date):
    conn = get_connection()
    cursor = conn.cursor()

    # Get all expenses in period
    cursor.execute("""
        SELECT e.id, e.paid_by, e.shared_amount, e.created_at, u.first_name
        FROM expenses e
        JOIN users u ON e.paid_by = u.id
        WHERE e.group_id = %s
        AND e.created_at BETWEEN %s AND %s
        AND e.shared_amount > 0
        ORDER BY e.created_at
    """, (group_id, start_date, end_date))
    expenses = cursor.fetchall()

    # Get all splits in period
    cursor.execute("""
        SELECT es.expense_id, es.user_id, es.amount, u.first_name
        FROM expense_splits es
        JOIN users u ON es.user_id = u.id
        JOIN expenses e ON es.expense_id = e.id
        WHERE e.group_id = %s
        AND e.created_at BETWEEN %s AND %s
    """, (group_id, start_date, end_date))
    splits = cursor.fetchall()

    cursor.close()
    conn.close()
    return expenses, splits


def get_member_spending(group_id, start_date, end_date):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.id, u.first_name,
               COALESCE(SUM(e.shared_amount), 0) as total_paid,
               COALESCE(SUM(es.amount), 0) as fair_share
        FROM users u
        JOIN group_members gm ON u.id = gm.user_id
        LEFT JOIN expenses e ON e.paid_by = u.id
            AND e.group_id = %s
            AND e.created_at BETWEEN %s AND %s
        LEFT JOIN expense_splits es ON es.user_id = u.id
            JOIN expenses e2 ON es.expense_id = e2.id
            AND e2.group_id = %s
            AND e2.created_at BETWEEN %s AND %s
        WHERE gm.group_id = %s
        AND gm.is_active = TRUE
        GROUP BY u.id, u.first_name
    """, (group_id, start_date, end_date,
          group_id, start_date, end_date,
          group_id))
    result = cursor.fetchall()
    cursor.close()
    conn.close()
    return result


def get_group_by_id(group_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, currency, invite_code, admin_id
        FROM groups WHERE id = %s
    """, (group_id,))
    group = cursor.fetchone()
    cursor.close()
    conn.close()
    return group

# ─── EXPENSE QUERIES ─────────────────────────────────────

def add_expense(group_id, paid_by, total_amount, shared_amount,
                personal_amount, split_type, description,
                receipt_file_id=None, expense_date=None):
    conn = get_connection()
    cursor = conn.cursor()
    if expense_date is None:
        expense_date = datetime.now().date()
    cursor.execute("""
        INSERT INTO expenses (group_id, paid_by, total_amount,
                              shared_amount, personal_amount,
                              split_type, description,
                              receipt_file_id, expense_date)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (group_id, paid_by, total_amount, shared_amount,
          personal_amount, split_type, description,
          receipt_file_id, expense_date))
    expense_id = cursor.fetchone()[0]
    conn.commit()
    cursor.close()
    conn.close()
    return expense_id

def add_expense_split(expense_id, user_id, amount, percentage=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO expense_splits (expense_id, user_id, amount, percentage)
        VALUES (%s, %s, %s, %s)
    """, (expense_id, user_id, amount, percentage))
    conn.commit()
    cursor.close()
    conn.close()


def get_active_members_at_date(group_id, date):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.id, u.first_name
        FROM users u
        JOIN group_members gm ON u.id = gm.user_id
        WHERE gm.group_id = %s
        AND gm.joined_at <= %s
        AND (gm.left_at IS NULL OR gm.left_at > %s)
        AND gm.is_active = TRUE
    """, (group_id, date, date))
    members = cursor.fetchall()
    cursor.close()
    conn.close()
    return members


# ─── REPORT QUERIES ──────────────────────────────────────

def get_balances(group_id, start_date, end_date):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT e.id, e.paid_by, e.shared_amount, e.created_at, u.first_name
        FROM expenses e
        JOIN users u ON e.paid_by = u.id
        WHERE e.group_id = %s
        AND e.created_at BETWEEN %s AND %s
        AND e.shared_amount > 0
        ORDER BY e.created_at
    """, (group_id, start_date, end_date))
    expenses = cursor.fetchall()

    cursor.execute("""
        SELECT es.expense_id, es.user_id, es.amount, u.first_name
        FROM expense_splits es
        JOIN users u ON es.user_id = u.id
        JOIN expenses e ON es.expense_id = e.id
        WHERE e.group_id = %s
        AND e.created_at BETWEEN %s AND %s
    """, (group_id, start_date, end_date))
    splits = cursor.fetchall()

    cursor.close()
    conn.close()
    return expenses, splits


def get_group_by_id(group_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, currency, invite_code, admin_id
        FROM groups WHERE id = %s
    """, (group_id,))
    group = cursor.fetchone()
    cursor.close()
    conn.close()
    return group

def get_first_expense_date(group_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT MIN(created_at) FROM expenses
        WHERE group_id = %s
    """, (group_id,))
    result = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    return result

# ─── EDIT & DELETE QUERIES ───────────────────────────────

def get_expenses_by_date(group_id, date):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT e.id, e.paid_by, e.total_amount, e.shared_amount,
               e.personal_amount, e.split_type, e.description,
               e.expense_date, u.first_name
        FROM expenses e
        JOIN users u ON e.paid_by = u.id
        WHERE e.group_id = %s
        AND e.expense_date = %s
        AND e.is_deleted = FALSE
        ORDER BY e.created_at
    """, (group_id, date))
    expenses = cursor.fetchall()
    cursor.close()
    conn.close()
    return expenses


def get_expense_by_id(expense_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT e.id, e.paid_by, e.total_amount, e.shared_amount,
               e.personal_amount, e.split_type, e.description,
               e.expense_date, u.first_name, e.group_id
        FROM expenses e
        JOIN users u ON e.paid_by = u.id
        WHERE e.id = %s
    """, (expense_id,))
    expense = cursor.fetchone()
    cursor.close()
    conn.close()
    return expense


def update_expense(expense_id, field, value):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(f"""
        UPDATE expenses SET {field} = %s
        WHERE id = %s
    """, (value, expense_id))
    conn.commit()
    cursor.close()
    conn.close()


def soft_delete_expense(expense_id, deleted_by):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE expenses
        SET is_deleted = TRUE,
            deleted_by = %s,
            deleted_at = CURRENT_TIMESTAMP
        WHERE id = %s
    """, (deleted_by, expense_id))
    conn.commit()
    cursor.close()
    conn.close()


def get_deleted_expenses(group_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT e.id, e.paid_by, e.total_amount, e.shared_amount,
               e.personal_amount, e.description, e.expense_date,
               e.deleted_at, u.first_name,
               u2.first_name as deleted_by_name
        FROM expenses e
        JOIN users u ON e.paid_by = u.id
        LEFT JOIN users u2 ON e.deleted_by = u2.id
        WHERE e.group_id = %s
        AND e.is_deleted = TRUE
        AND e.deleted_at > CURRENT_TIMESTAMP - INTERVAL '3 months'
        ORDER BY e.deleted_at DESC
    """, (group_id,))
    expenses = cursor.fetchall()
    cursor.close()
    conn.close()
    return expenses


def restore_expense(expense_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE expenses
        SET is_deleted = FALSE,
            deleted_by = NULL,
            deleted_at = NULL
        WHERE id = %s
    """, (expense_id,))
    conn.commit()
    cursor.close()
    conn.close()


def get_group_admin(group_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT admin_id FROM groups WHERE id = %s
    """, (group_id,))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result[0] if result else None


def create_edit_request(expense_id, requested_by, group_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO edit_requests
        (expense_id, requested_by, group_id)
        VALUES (%s, %s, %s)
        RETURNING id
    """, (expense_id, requested_by, group_id))
    request_id = cursor.fetchone()[0]
    conn.commit()
    cursor.close()
    conn.close()
    return request_id


def update_edit_request(request_id, status):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE edit_requests
        SET status = %s, responded_at = CURRENT_TIMESTAMP
        WHERE id = %s
    """, (status, request_id))
    conn.commit()
    cursor.close()
    conn.close()


def get_edit_request(request_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT er.id, er.expense_id, er.requested_by,
               er.group_id, er.status, u.first_name
        FROM edit_requests er
        JOIN users u ON er.requested_by = u.id
        WHERE er.id = %s
    """, (request_id,))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result


def get_member_join_date(group_id, user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT joined_at FROM group_members
        WHERE group_id = %s AND user_id = %s
    """, (group_id, user_id))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result[0] if result else None


# ─── BUDGET TARGET QUERIES ───────────────────────────────

def set_budget_target(user_id, group_id, amount, month, year):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO budget_targets
        (user_id, group_id, target_amount, month, year)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (user_id, group_id, month, year)
        DO UPDATE SET target_amount = %s
    """, (user_id, group_id, amount, month, year, amount))
    conn.commit()
    cursor.close()
    conn.close()


def get_budget_target(user_id, group_id, month, year):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT target_amount FROM budget_targets
        WHERE user_id = %s AND group_id = %s
        AND month = %s AND year = %s
    """, (user_id, group_id, month, year))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result[0] if result else None


def get_user_spending_this_month(user_id, group_id, month, year):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COALESCE(SUM(shared_amount), 0)
        FROM expenses
        WHERE paid_by = %s
        AND group_id = %s
        AND EXTRACT(MONTH FROM expense_date) = %s
        AND EXTRACT(YEAR FROM expense_date) = %s
        AND is_deleted = FALSE
    """, (user_id, group_id, month, year))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return float(result[0]) if result else 0.0