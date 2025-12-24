import sqlite3
from datetime import datetime
import config

# ---------------------------
# Database Initialization
# ---------------------------
def init_db():
    conn = sqlite3.connect(config.DB_FILE)
    cursor = conn.cursor()

    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            is_premium BOOLEAN DEFAULT FALSE,
            deployment_count INTEGER DEFAULT 0
        )
    ''')

    # Services table (base columns)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS services (
            service_id TEXT PRIMARY KEY,
            user_id INTEGER,
            port INTEGER,
            status TEXT,
            created_at DATETIME,
            last_restart DATETIME,
            project_type TEXT,
            path TEXT,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
    ''')

    # Bans table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bans (
            user_id INTEGER PRIMARY KEY,
            reason TEXT,
            banned_at DATETIME
        )
    ''')

    # Activity logs table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS activity_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT,
            details TEXT,
            timestamp DATETIME
        )
    ''')

    conn.commit()
    conn.close()


# ---------------------------
# DB Connection Helper
# ---------------------------
def get_conn():
    return sqlite3.connect(config.DB_FILE)


# ---------------------------
# Migration (ADD NEW COLUMNS)
# ---------------------------
def migrate_services_table():
    conn = get_conn()
    cursor = conn.cursor()

    migrations = [
        ("custom_domain", "TEXT"),
        ("verification_token", "TEXT"),
        ("domain_verified", "BOOLEAN DEFAULT FALSE")
    ]

    for column, col_type in migrations:
        try:
            cursor.execute(
                f"ALTER TABLE services ADD COLUMN {column} {col_type}"
            )
        except sqlite3.OperationalError:
            # Column already exists
            pass

    conn.commit()
    conn.close()


# ---------------------------
# User Functions
# ---------------------------
def add_or_get_user(user_id):
    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()

    if not user:
        cursor.execute(
            "INSERT INTO users (user_id) VALUES (?)",
            (user_id,)
        )
        conn.commit()
        user = (user_id, False, 0)

    conn.close()
    return {
        "user_id": user[0],
        "is_premium": user[1],
        "deployment_count": user[2]
    }


def update_premium(user_id, is_premium):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET is_premium = ? WHERE user_id = ?",
        (is_premium, user_id)
    )
    conn.commit()
    conn.close()


def get_deployment_count(user_id):
    user = add_or_get_user(user_id)
    return user["deployment_count"]


def increment_deployment_count(user_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET deployment_count = deployment_count + 1 WHERE user_id = ?",
        (user_id,)
    )
    conn.commit()
    conn.close()


def decrement_deployment_count(user_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET deployment_count = deployment_count - 1 WHERE user_id = ?",
        (user_id,)
    )
    conn.commit()
    conn.close()


# ---------------------------
# Service Functions
# ---------------------------
def add_service(service_id, user_id, port, status, created_at,
                last_restart, project_type, path,
                custom_domain=None, verification_token=None, domain_verified=False):

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO services (
            service_id, user_id, port, status,
            created_at, last_restart,
            project_type, path,
            custom_domain, verification_token, domain_verified
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        service_id, user_id, port, status,
        created_at, last_restart,
        project_type, path,
        custom_domain, verification_token, domain_verified
    ))

    conn.commit()
    conn.close()


def get_service(service_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM services WHERE service_id = ?",
        (service_id,)
    )
    service = cursor.fetchone()
    conn.close()

    if not service:
        return None

    return {
        "service_id": service[0],
        "user_id": service[1],
        "port": service[2],
        "status": service[3],
        "created_at": service[4],
        "last_restart": service[5],
        "project_type": service[6],
        "path": service[7],
        "custom_domain": service[8],
        "verification_token": service[9],
        "domain_verified": service[10]
    }


def update_status(service_id, status):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE services SET status = ? WHERE service_id = ?",
        (status, service_id)
    )
    conn.commit()
    conn.close()


def update_last_restart(service_id, last_restart):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE services SET last_restart = ? WHERE service_id = ?",
        (last_restart, service_id)
    )
    conn.commit()
    conn.close()


def verify_domain(service_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE services SET domain_verified = TRUE WHERE service_id = ?",
        (service_id,)
    )
    conn.commit()
    conn.close()


def get_services_for_user(user_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT service_id FROM services WHERE user_id = ?",
        (user_id,)
    )
    services = cursor.fetchall()
    conn.close()
    return [s[0] for s in services]


def get_running_services():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        'SELECT * FROM services WHERE status = "running"'
    )
    services = cursor.fetchall()
    conn.close()

    return [{
        "service_id": s[0],
        "user_id": s[1],
        "port": s[2],
        "status": s[3],
        "created_at": s[4],
        "last_restart": s[5],
        "project_type": s[6],
        "path": s[7],
        "custom_domain": s[8],
        "verification_token": s[9],
        "domain_verified": s[10]
    } for s in services]


def delete_service(service_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM services WHERE service_id = ?",
        (service_id,)
    )
    conn.commit()
    conn.close()


# ---------------------------
# Ban Functions
# ---------------------------
def ban_user(user_id, reason):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO bans (user_id, reason, banned_at) VALUES (?, ?, ?)",
        (user_id, reason, datetime.now())
    )
    conn.commit()
    conn.close()


def unban_user(user_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM bans WHERE user_id = ?",
        (user_id,)
    )
    conn.commit()
    conn.close()


def get_ban(user_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM bans WHERE user_id = ?",
        (user_id,)
    )
    ban = cursor.fetchone()
    conn.close()
    return ban


# ---------------------------
# Activity Logs
# ---------------------------
def log_activity(user_id, action, details):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO activity_logs (user_id, action, details, timestamp) VALUES (?, ?, ?, ?)",
        (user_id, action, details, datetime.now())
    )
    conn.commit()
    conn.close()
