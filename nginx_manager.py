import os
import subprocess

NGINX_SITES = '/etc/nginx/sites-available'
NGINX_ENABLED = '/etc/nginx/sites-enabled'

def create_nginx_config(service_id, domain, port):
    config_path = os.path.join(NGINX_SITES, f'deployx_{service_id}')
    content = f"""
server {{
    listen 80;
    server_name {domain} www.{domain};

    location / {{
        proxy_pass http://127.0.0.1:{port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
}}
"""
    with open(config_path, 'w') as f:
        f.write(content)
    
    enabled_path = os.path.join(NGINX_ENABLED, f'deployx_{service_id}')
    if not os.path.exists(enabled_path):
        os.symlink(config_path, enabled_path)
    
    subprocess.run(['sudo', 'nginx', '-t'])
    subprocess.run(['sudo', 'systemctl', 'reload', 'nginx'])

def remove_nginx_config(service_id):
    paths = [
        os.path.join(NGINX_SITES, f'deployx_{service_id}'),
        os.path.join(NGINX_ENABLED, f'deployx_{service_id}')
    ]
    for p in paths:
        if os.path.exists(p):
            os.remove(p)
    subprocess.run(['sudo', 'nginx', '-t'])
    subprocess.run(['sudo', 'systemctl', 'reload', 'nginx'])
