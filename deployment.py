import os
import shutil
import subprocess
import threading
import time
import zipfile
import logging

import config
from database import *
from security import scan_for_malicious_content
from utils import generate_service_id, get_unused_port

# Global dicts for managing processes and watchdogs
processes = {}  # service_id: subprocess.Popen
watchdogs = {}  # service_id: threading.Thread

def deploy_project(user_id, zip_path, bot, chat_id):
    # Extract ZIP to temp dir
    temp_dir = f'temp_deploy_{user_id}_{time.time()}'
    os.makedirs(temp_dir, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
    except Exception as e:
        bot.send_message(chat_id, f"Error extracting ZIP: {str(e)}")
        shutil.rmtree(temp_dir)
        os.remove(zip_path)
        return

    # Scan for malicious content
    is_malicious, reason = scan_for_malicious_content(temp_dir)
    if is_malicious:
        ban_user(user_id, reason)
        bot.send_message(chat_id, f"You have been banned: {reason}")
        bot.send_message(config.ADMIN_ID, f"User {user_id} banned for malicious upload: {reason}")
        shutil.rmtree(temp_dir)
        os.remove(zip_path)
        return

    # Check deployment limits
    user = add_or_get_user(user_id)
    max_deploys = config.MAX_DEPLOYS_PREMIUM if user['is_premium'] else config.MAX_DEPLOYS_FREE
    if user['deployment_count'] >= max_deploys:
        bot.send_message(chat_id, f"Deployment limit reached ({max_deploys}). Upgrade to premium for more.")
        shutil.rmtree(temp_dir)
        os.remove(zip_path)
        return

    # Setup service
    service_id = generate_service_id()
    user_dir = os.path.join(config.DEPLOYMENTS_DIR, f'user_{user_id}')
    os.makedirs(user_dir, exist_ok=True)
    service_dir = os.path.join(user_dir, service_id)
    shutil.move(temp_dir, service_dir)

    # Detect project type
    if os.path.exists(os.path.join(service_dir, 'app.py')) and os.path.exists(os.path.join(service_dir, 'requirements.txt')):
        project_type = 'flask'
        # Create venv and install requirements
        venv_path = os.path.join(service_dir, 'venv')
        subprocess.run(['python', '-m', 'venv', venv_path], check=True)
        pip_path = os.path.join(venv_path, 'bin', 'pip')
        req_path = os.path.join(service_dir, 'requirements.txt')
        install_process = subprocess.run([pip_path, 'install', '-r', req_path])
        if install_process.returncode != 0:
            bot.send_message(chat_id, "Error installing requirements.txt")
            shutil.rmtree(service_dir)
            os.remove(zip_path)
            return
        cmd = [os.path.join(venv_path, 'bin', 'python'), os.path.join(service_dir, 'app.py')]
        env = os.environ.copy()
        env['PORT'] = ''  # Will set later
    elif os.path.exists(os.path.join(service_dir, 'index.html')):
        project_type = 'static'
        cmd = ['python', '-m', 'http.server', '--directory', service_dir]
        env = None
    else:
        bot.send_message(chat_id, "Unsupported project type. Need app.py + requirements.txt (Flask) or index.html (static).")
        shutil.rmtree(service_dir)
        os.remove(zip_path)
        return

    # Assign port and start
    port = get_unused_port()
    now = datetime.now()
    add_service(service_id, user_id, port, 'running', now, now, project_type, service_dir)
    increment_deployment_count(user_id)

    if project_type == 'static':
        cmd.append(str(port))
    else:
        env['PORT'] = str(port)

    start_process(service_id, cmd, env, project_type)
    if user['is_premium']:
        start_watchdog(service_id)

    link = f"http://{config.SERVER_IP}:{port}"
    bot.send_message(chat_id, f"Deployment successful! Service ID: {service_id}\nLink: {link}\nNote: For Flask, ensure app.py uses port=int(os.environ.get('PORT', 5000)) and host='0.0.0.0'")
    bot.send_message(config.ADMIN_ID, f"New deployment by user {user_id}: {service_id} ({project_type}) on port {port}")
    log_activity(user_id, 'deploy', f"Service {service_id} deployed")
    os.remove(zip_path)

def update_project(user_id, service_id, zip_path, bot, chat_id):
    service = get_service(service_id)
    if not service or service['user_id'] != user_id:
        bot.send_message(chat_id, "Invalid service ID or not yours.")
        os.remove(zip_path)
        return

    # Stop current process if running
    stop_process(service_id)
    update_status(service_id, 'stopped')

    # Extract to temp
    temp_dir = f'temp_update_{user_id}_{time.time()}'
    os.makedirs(temp_dir, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
    except Exception as e:
        bot.send_message(chat_id, f"Error extracting ZIP: {str(e)}")
        shutil.rmtree(temp_dir)
        os.remove(zip_path)
        return

    # Scan
    is_malicious, reason = scan_for_malicious_content(temp_dir)
    if is_malicious:
        ban_user(user_id, reason)
        bot.send_message(chat_id, f"You have been banned: {reason}")
        bot.send_message(config.ADMIN_ID, f"User {user_id} banned for malicious update: {reason}")
        shutil.rmtree(temp_dir)
        os.remove(zip_path)
        return

    # Clear old dir and move new
    shutil.rmtree(service['path'])
    shutil.move(temp_dir, service['path'])

    # Re-setup if flask
    project_type = service['project_type']
    if project_type == 'flask':
        venv_path = os.path.join(service['path'], 'venv')
        subprocess.run(['python', '-m', 'venv', venv_path], check=True)
        pip_path = os.path.join(venv_path, 'bin', 'pip')
        req_path = os.path.join(service['path'], 'requirements.txt')
        install_process = subprocess.run([pip_path, 'install', '-r', req_path])
        if install_process.returncode != 0:
            bot.send_message(chat_id, "Error installing requirements.txt")
            os.remove(zip_path)
            return
        cmd = [os.path.join(venv_path, 'bin', 'python'), os.path.join(service['path'], 'app.py')]
        env = os.environ.copy()
        env['PORT'] = str(service['port'])
    else:
        cmd = ['python', '-m', 'http.server', str(service['port']), '--directory', service['path']]
        env = None

    # Restart
    update_status(service_id, 'running')
    start_process(service_id, cmd, env, project_type)
    user = add_or_get_user(user_id)
    if user['is_premium']:
        start_watchdog(service_id)
    update_last_restart(service_id, datetime.now())

    link = f"http://{config.SERVER_IP}:{service['port']}"
    bot.send_message(chat_id, f"Update successful for {service_id}! Link: {link}")
    bot.send_message(config.ADMIN_ID, f"User {user_id} updated service {service_id}")
    log_activity(user_id, 'update', f"Service {service_id} updated")
    os.remove(zip_path)

def start_process(service_id, cmd, env, project_type):
    # Start the process in background, log to per-service file
    log_file = os.path.join(config.LOGS_DIR, f'{service_id}.log')
    with open(log_file, 'a') as log:
        process = subprocess.Popen(cmd, env=env, stdout=log, stderr=subprocess.STDOUT)
    processes[service_id] = process
    logging.info(f"Started process for {service_id} ({project_type})")

def stop_process(service_id):
    if service_id in processes:
        processes[service_id].terminate()
        try:
            processes[service_id].wait(timeout=5)
        except subprocess.TimeoutExpired:
            processes[service_id].kill()
        del processes[service_id]
        logging.info(f"Stopped process for {service_id}")
    # Watchdog will stop naturally since process is gone

def start_watchdog(service_id):
    if service_id in watchdogs:
        return  # Already running
    thread = threading.Thread(target=watchdog_func, args=(service_id,), daemon=True)
    thread.start()
    watchdogs[service_id] = thread
    logging.info(f"Started watchdog for {service_id}")

def watchdog_func(service_id):
    # Basic watchdog: check every interval if process died, restart if status is running
    while True:
        service = get_service(service_id)
        if not service or service['status'] != 'running':
            break  # Stop watchdog if service deleted or not running
        if service_id not in processes or processes[service_id].poll() is not None:
            logging.warning(f"Process died for {service_id}, restarting")
            project_type = service['project_type']
            path = service['path']
            port = service['port']
            if project_type == 'flask':
                venv_path = os.path.join(path, 'venv')
                cmd = [os.path.join(venv_path, 'bin', 'python'), os.path.join(path, 'app.py')]
                env = os.environ.copy()
                env['PORT'] = str(port)
            else:
                cmd = ['python', '-m', 'http.server', str(port), '--directory', path]
                env = None
            start_process(service_id, cmd, env, project_type)
            update_last_restart(service_id, datetime.now())
            bot.send_message(config.ADMIN_ID, f"Auto-restarted service {service_id} for user {service['user_id']}")
        time.sleep(config.WATCHDOG_INTERVAL)
    if service_id in watchdogs:
        del watchdogs[service_id]
