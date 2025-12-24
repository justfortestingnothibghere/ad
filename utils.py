import random
import uuid
import socket

import config
from database import get_conn

def generate_service_id():
    # Generate a short unique ID using UUID
    return uuid.uuid4().hex[:8]

def get_unused_port():
    # Get used ports from DB
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('SELECT port FROM services')
    used_ports = {row[0] for row in cursor.fetchall()}
    conn.close()
    
    # Find random unused port in range
    while True:
        port = random.randint(config.PORT_RANGE[0], config.PORT_RANGE[1])
        if port not in used_ports:
            # Double-check if port is free by trying to bind
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(('0.0.0.0', port))
                    return port
                except OSError:
                    continue
