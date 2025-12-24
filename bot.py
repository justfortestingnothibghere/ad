import os
import threading
import time
from collections import deque

import telebot
from telebot.types import Message

import config
from database import *
from deployment import *
from utils import *

# Setup logging
os.makedirs(config.LOGS_DIR, exist_ok=True)
logging.basicConfig(filename=os.path.join(config.LOGS_DIR, 'system.log'), level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize DB
init_db()

# Bot instance
bot = telebot.TeleBot(config.BOT_TOKEN)

# States for file uploads (per user)
user_states = {}  # user_id: 'waiting_deploy' or 'waiting_update_{service_id}'

# Rate limiting
rate_limits = {}  # user_id: deque of timestamps

def check_rate_limit(user_id):
    now = time.time()
    if user_id not in rate_limits:
        rate_limits[user_id] = deque()
    queue = rate_limits[user_id]
    # Remove old timestamps
    while queue and queue[0] < now - 60:
        queue.popleft()
    if len(queue) >= config.RATE_LIMIT_COMMANDS:
        return False
    queue.append(now)
    return True

# Decorator for command handlers: check ban, rate limit
def command_handler(func):
    def wrapper(message: Message):
        user_id = message.from_user.id
        if get_ban(user_id):
            bot.reply_to(message, "You are banned from using this bot.")
            return
        if not check_rate_limit(user_id):
            bot.reply_to(message, "Rate limit exceeded. Please slow down.")
            return
        try:
            func(message)
        except Exception as e:
            logging.error(f"Error in handler: {str(e)}")
            bot.reply_to(message, "An error occurred. Please try again.")
    return wrapper

# Document handler for uploads
@bot.message_handler(content_types=['document'])
def handle_document(message: Message):
    user_id = message.from_user.id
    if user_id not in user_states:
        bot.reply_to(message, "Unexpected file. Use a command first (e.g., /deploy).")
        return
    
    # Check if it's a ZIP file
    if not message.document.file_name.lower().endswith('.zip'):
        bot.reply_to(message, "Please upload a .zip file only.")
        del user_states[user_id]
        return

    state = user_states[user_id]
    file_info = bot.get_file(message.document.file_id)
    
    # Download file as bytes (new correct way)
    try:
        downloaded_file = bot.download_file(file_info.file_path)
    except Exception as e:
        bot.reply_to(message, f"Failed to download file: {str(e)}")
        del user_states[user_id]
        return
    
    # Save to temporary ZIP path
    zip_path = f'temp_{user_id}_{int(time.time())}.zip'
    try:
        with open(zip_path, 'wb') as f:
            f.write(downloaded_file)
    except Exception as e:
        bot.reply_to(message, f"Failed to save file: {str(e)}")
        del user_states[user_id]
        return
    
    bot.reply_to(message, "File received! Processing your deployment..." if 'deploy' in state else "File received! Updating your project...")
    
    if state == 'waiting_deploy':
        threading.Thread(target=deploy_project, args=(user_id, zip_path, bot, message.chat.id)).start()
    elif state.startswith('waiting_update_'):
        service_id = state.split('_')[2]
        threading.Thread(target=update_project, args=(user_id, service_id, zip_path, bot, message.chat.id)).start()
    
    del user_states[user_id]

# User commands
@bot.message_handler(commands=['deploy'])
@command_handler
def handle_deploy(message: Message):
    user_id = message.from_user.id
    add_or_get_user(user_id)  # Ensure user in DB
    user_states[user_id] = 'waiting_deploy'
    bot.reply_to(message, "Please upload your project ZIP file (contains index.html for static or app.py + requirements.txt for Flask).")

@bot.message_handler(commands=['update'])
@command_handler
def handle_update(message: Message):
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "Usage: /update SERVICE_ID")
        return
    service_id = parts[1]
    user_id = message.from_user.id
    service = get_service(service_id)
    if not service or service['user_id'] != user_id:
        bot.reply_to(message, "Invalid service ID or not yours.")
        return
    user_states[user_id] = f'waiting_update_{service_id}'
    bot.reply_to(message, f"Please upload the updated ZIP file for {service_id}.")

@bot.message_handler(commands=['getlink'])
@command_handler
def handle_getlink(message: Message):
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "Usage: /getlink SERVICE_ID")
        return
    service_id = parts[1]
    user_id = message.from_user.id
    service = get_service(service_id)
    if not service or service['user_id'] != user_id:
        bot.reply_to(message, "Invalid service ID or not yours.")
        return
    link = f"http://{config.SERVER_IP}:{service['port']}"
    bot.reply_to(message, f"Link for {service_id}: {link}")

@bot.message_handler(commands=['stop'])
@command_handler
def handle_stop(message: Message):
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "Usage: /stop SERVICE_ID")
        return
    service_id = parts[1]
    user_id = message.from_user.id
    service = get_service(service_id)
    if not service or service['user_id'] != user_id:
        bot.reply_to(message, "Invalid service ID or not yours.")
        return
    stop_process(service_id)
    update_status(service_id, 'stopped')
    bot.reply_to(message, f"Stopped {service_id}")
    bot.send_message(config.ADMIN_ID, f"User {user_id} stopped {service_id}")
    log_activity(user_id, 'stop', service_id)

@bot.message_handler(commands=['redeploy'])
@command_handler
def handle_redeploy(message: Message):
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "Usage: /redeploy SERVICE_ID")
        return
    service_id = parts[1]
    user_id = message.from_user.id
    service = get_service(service_id)
    if not service or service['user_id'] != user_id:
        bot.reply_to(message, "Invalid service ID or not yours.")
        return
    if service['status'] != 'stopped':
        stop_process(service_id)
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
    user = add_or_get_user(user_id)
    if user['is_premium']:
        start_watchdog(service_id)
    update_status(service_id, 'running')
    update_last_restart(service_id, datetime.now())
    bot.reply_to(message, f"Redeployed {service_id}")
    bot.send_message(config.ADMIN_ID, f"User {user_id} redeployed {service_id}")
    log_activity(user_id, 'redeploy', service_id)

@bot.message_handler(commands=['delete'])
@command_handler
def handle_delete(message: Message):
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "Usage: /delete SERVICE_ID")
        return
    service_id = parts[1]
    user_id = message.from_user.id
    service = get_service(service_id)
    if not service or service['user_id'] != user_id:
        bot.reply_to(message, "Invalid service ID or not yours.")
        return
    stop_process(service_id)
    shutil.rmtree(service['path'], ignore_errors=True)
    delete_service(service_id)
    decrement_deployment_count(user_id)
    bot.reply_to(message, f"Deleted {service_id}")
    bot.send_message(config.ADMIN_ID, f"User {user_id} deleted {service_id}")
    log_activity(user_id, 'delete', service_id)

@bot.message_handler(commands=['maintenance'])
@command_handler
def handle_maintenance(message: Message):
    parts = message.text.split()
    if len(parts) < 3:
        bot.reply_to(message, "Usage: /maintenance SERVICE_ID ON/OFF")
        return
    service_id = parts[1]
    mode = parts[2].upper()
    if mode not in ['ON', 'OFF']:
        bot.reply_to(message, "Invalid mode: ON or OFF")
        return
    user_id = message.from_user.id
    service = get_service(service_id)
    if not service or service['user_id'] != user_id:
        bot.reply_to(message, "Invalid service ID or not yours.")
        return
    if mode == 'ON':
        stop_process(service_id)
        update_status(service_id, 'maintenance')
        bot.reply_to(message, f"Maintenance mode ON for {service_id}. Access will fail.")
    else:
        # Restart as in redeploy
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
        user = add_or_get_user(user_id)
        if user['is_premium']:
            start_watchdog(service_id)
        update_status(service_id, 'running')
        update_last_restart(service_id, datetime.now())
        bot.reply_to(message, f"Maintenance mode OFF for {service_id}")
    bot.send_message(config.ADMIN_ID, f"User {user_id} set maintenance {mode} for {service_id}")
    log_activity(user_id, 'maintenance', f"{service_id} {mode}")

# Admin commands
@bot.message_handler(commands=['ban'])
@command_handler
def handle_ban(message: Message):
    if message.from_user.id != config.ADMIN_ID:
        bot.reply_to(message, "Admin only.")
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        bot.reply_to(message, "Usage: /ban USER_ID REASON")
        return
    try:
        user_id = int(parts[1])
        reason = parts[2]
    except ValueError:
        bot.reply_to(message, "Invalid USER_ID.")
        return
    ban_user(user_id, reason)
    bot.reply_to(message, f"Banned user {user_id}: {reason}")
    bot.send_message(user_id, f"You have been banned: {reason}")
    log_activity(user_id, 'ban', reason)

@bot.message_handler(commands=['unban'])
@command_handler
def handle_unban(message: Message):
    if message.from_user.id != config.ADMIN_ID:
        bot.reply_to(message, "Admin only.")
        return
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "Usage: /unban USER_ID")
        return
    try:
        user_id = int(parts[1])
    except ValueError:
        bot.reply_to(message, "Invalid USER_ID.")
        return
    unban_user(user_id)
    bot.reply_to(message, f"Unbanned user {user_id}")
    bot.send_message(user_id, "You have been unbanned.")
    log_activity(user_id, 'unban', '')

@bot.message_handler(commands=['suspend'])
@command_handler
def handle_suspend(message: Message):
    if message.from_user.id != config.ADMIN_ID:
        bot.reply_to(message, "Admin only.")
        return
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "Usage: /suspend SERVICE_ID")
        return
    service_id = parts[1]
    service = get_service(service_id)
    if not service:
        bot.reply_to(message, "Invalid service ID.")
        return
    stop_process(service_id)
    update_status(service_id, 'suspended')
    bot.reply_to(message, f"Suspended {service_id}")
    bot.send_message(service['user_id'], f"Your service {service_id} has been suspended by admin.")
    log_activity(service['user_id'], 'suspend', service_id)

@bot.message_handler(commands=['unsuspend'])
@command_handler
def handle_unsuspend(message: Message):
    if message.from_user.id != config.ADMIN_ID:
        bot.reply_to(message, "Admin only.")
        return
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "Usage: /unsuspend SERVICE_ID")
        return
    service_id = parts[1]
    service = get_service(service_id)
    if not service:
        bot.reply_to(message, "Invalid service ID.")
        return
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
    user = add_or_get_user(service['user_id'])
    if user['is_premium']:
        start_watchdog(service_id)
    update_status(service_id, 'running')
    update_last_restart(service_id, datetime.now())
    bot.reply_to(message, f"Unsuspended {service_id}")
    bot.send_message(service['user_id'], f"Your service {service_id} has been unsuspended.")
    log_activity(service['user_id'], 'unsuspend', service_id)

@bot.message_handler(commands=['addpremium'])
@command_handler
def handle_addpremium(message: Message):
    if message.from_user.id != config.ADMIN_ID:
        bot.reply_to(message, "Admin only.")
        return
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "Usage: /addpremium USER_ID")
        return
    try:
        user_id = int(parts[1])
    except ValueError:
        bot.reply_to(message, "Invalid USER_ID.")
        return
    update_premium(user_id, True)
    bot.reply_to(message, f"Added premium to {user_id}")
    bot.send_message(user_id, "You are now a premium user!")
    log_activity(user_id, 'addpremium', '')

@bot.message_handler(commands=['removepremium'])
@command_handler
def handle_removepremium(message: Message):
    if message.from_user.id != config.ADMIN_ID:
        bot.reply_to(message, "Admin only.")
        return
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "Usage: /removepremium USER_ID")
        return
    try:
        user_id = int(parts[1])
    except ValueError:
        bot.reply_to(message, "Invalid USER_ID.")
        return
    update_premium(user_id, False)
    bot.reply_to(message, f"Removed premium from {user_id}")
    bot.send_message(user_id, "Your premium status has been removed.")
    log_activity(user_id, 'removepremium', '')

# Restart running services on bot start
running_services = get_running_services()
for service in running_services:
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
    start_process(service['service_id'], cmd, env, project_type)
    user = add_or_get_user(service['user_id'])
    if user['is_premium']:
        start_watchdog(service['service_id'])
    logging.info(f"Restarted service {service['service_id']} on bot start")

# Start polling
if __name__ == '__main__':
    os.makedirs(config.DEPLOYMENTS_DIR, exist_ok=True)
    logging.info("Bot started")
    bot.polling(none_stop=True)
