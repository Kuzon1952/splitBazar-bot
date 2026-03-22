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
                personal_amount, split_type, description, receipt_file_id=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO expenses (group_id, paid_by, total_amount, shared_amount,
                              personal_amount, split_type, description, receipt_file_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (group_id, paid_by, total_amount, shared_amount,
          personal_amount, split_type, description, receipt_file_id))
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