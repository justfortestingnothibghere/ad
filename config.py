# Configuration file for the bot
# Edit these values before running the bot

BOT_TOKEN = '7913272382:AAGnvD29s4bu_jmsejNmT5eWbl7HZnGy_OM'  # Obtain from BotFather
ADMIN_ID = 8163739723  # Your Telegram user ID as admin
SERVER_IP = '51.20.116.229'  # Public IP of the EC2 instance
PORT_RANGE = (8000, 9000)  # Range for assigning random ports
DB_FILE = 'bot.db'  # SQLite database file
DEPLOYMENTS_DIR = 'deployments'  # Base dir for user projects
LOGS_DIR = 'logs'  # Dir for logs
RATE_LIMIT_COMMANDS = 10  # Max commands per minute per user
MAX_DEPLOYS_FREE = 1  # Max deployments for free users
MAX_DEPLOYS_PREMIUM = 5  # Max for premium
WATCHDOG_INTERVAL = 10  # Seconds between process checks in watchdog
