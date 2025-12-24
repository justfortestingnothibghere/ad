import sqlite3
from datetime import datetime

import config

# Initialize the database and create tables if they don't exist
def init_db():
    conn = sqlite3.connect(config.DB_FILE)
    cursor = conn.cursor()
    
    # Users table: tracks premium status and deployment count
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            is_premium BOOLEAN DEFAULT FALSE,
            deployment_count INTEGER DEFAULT 0
        )
    ''')
    
    # Services table: tracks each deployment
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS services (
            service_id TEXT PRIMARY KEY,
            user_id INTEGER,
            port INTEGER,
            status TEXT,  -- running, stopped, maintenance, suspended
            created_at DATETIME,
            last_restart DATETIME,
            project_type TEXT,  -- static or flask
            path TEXT,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
    ''')
    
    # Bans table: tracks banned users
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bans (
            user_id INTEGER PRIMARY KEY,
            reason TEXT,
            banned_at DATETIME
        )
    ''')
    
    # Activity logs table: logs actions for auditing
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

# Helper to get a connection
def get_conn():
    return sqlite3.connect(config.DB_FILE)

# User functions
def add_or_get_user(user_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    if not user:
        cursor.execute('INSERT INTO users (user_id) VALUES (?)', (user_id,))
        conn.commit()
        user = (user_id, False, 0)
    conn.close()
    return {'user_id': user[0], 'is_premium': user[1], 'deployment_count': user[2]}

def update_premium(user_id, is_premium):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_premium = ? WHERE user_id = ?', (is_premium, user_id))
    conn.commit()
    conn.close()

def get_deployment_count(user_id):
    user = add_or_get_user(user_id)
    return user['deployment_count']

def increment_deployment_count(user_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET deployment_count = deployment_count + 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def decrement_deployment_count(user_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET deployment_count = deployment_count - 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

# Service functions
def add_service(service_id, user_id, port, status, created_at, last_restart, project_type, path):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO services (service_id, user_id, port, status, created_at, last_restart, project_type, path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (service_id, user_id, port, status, created_at, last_restart, project_type, path))
    conn.commit()
    conn.close()

def get_service(service_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM services WHERE service_id = ?', (service_id,))
    service = cursor.fetchone()
    conn.close()
    if service:
        return {
            'service_id': service[0], 'user_id': service[1], 'port': service[2], 'status': service[3],
            'created_at': service[4], 'last_restart': service[5], 'project_type': service[6], 'path': service[7]
        }
    return None

def update_status(service_id, status):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('UPDATE services SET status = ? WHERE service_id = ?', (status, service_id))
    conn.commit()
    conn.close()

def update_last_restart(service_id, last_restart):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('UPDATE services SET last_restart = ? WHERE service_id = ?', (last_restart, service_id))
    conn.commit()
    conn.close()

def get_services_for_user(user_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT service_id FROM services WHERE user_id = ?', (user_id,))
    services = cursor.fetchall()
    conn.close()
    return [s[0] for s in services]

def get_running_services():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM services WHERE status = "running"')
    services = cursor.fetchall()
    conn.close()
    return [{
        'service_id': s[0], 'user_id': s[1], 'port': s[2], 'status': s[3],
        'created_at': s[4], 'last_restart': s[5], 'project_type': s[6], 'path': s[7]
    } for s in services]

def delete_service(service_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM services WHERE service_id = ?', (service_id,))
    conn.commit()
    conn.close()

# Ban functions
def ban_user(user_id, reason):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('INSERT OR REPLACE INTO bans (user_id, reason, banned_at) VALUES (?, ?, ?)',
                   (user_id, reason, datetime.now()))
    conn.commit()
    conn.close()

def unban_user(user_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM bans WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def get_ban(user_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM bans WHERE user_id = ?', (user_id,))
    ban = cursor.fetchone()
    conn.close()
    return ban

# Activity log
def log_activity(user_id, action, details):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO activity_logs (user_id, action, details, timestamp) VALUES (?, ?, ?, ?)',
                   (user_id, action, details, datetime.now()))
    conn.commit()
    conn.close()
