#!/usr/bin/env python3

import time
import os
import glob
import re
import requests
from zomboid_rcon import ZomboidRCON

# For Discord webhook notification
# DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/eccecc"
# DISCORD_LOGSWEBHOOK_URL = "https://discord.com/api/webhooks/eccecc"
# If the user decides NOT to use Discord, then USE_DISCORD=False

USE_DISCORD = False
DISCORD_LOGSWEBHOOK_URL = None
DISCORD_WEBHOOK_URL = None

# RCON parameters (will be set by ask_user_for_params if you want)
SERVER_IP = "127.0.0.1"
RCON_PORT = 27015
RCON_PASSWORD = "..."

COOLDOWN_RESTART = 5

LOGS_DIR = "Logs"
PATTERN = "*_DebugLog-server.txt"
logfile = None
def init_logging():
    """
    Creates the Logs/PZWatchdogLogs folder (if it doesn't exist)
    and opens a log file with a timestamp in the name,
    returning the open stream.
    """
    log_dir = "Logs/PZWatchdogLogs"
    os.makedirs(log_dir, exist_ok=True)

    # Create a timestamp for the filename: e.g. '2023-12-25_11-03-00_PZWDLog.txt'
    time_str = time.strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{time_str}_PZWDLog.txt"
    fullpath = os.path.join(log_dir, filename)

    # Open the file in write mode
    logfile = open(fullpath, "w", encoding="utf-8")
    return logfile

def log_print(message, also_print=True):
    """
    Prints and/or writes the message to the file.
    - logfile: open stream in write mode
    - message: string to log
    - also_print: if True, also print to the screen, default is always True
    """
    # Prepare a timestamp for the line
    time_str = time.strftime("[%Y-%m-%d %H:%M:%S]")
    line = f"{time_str} {message}"

    if also_print:
        print(line)
    # Write the line to the file and flush
    logfile.write(line + "\n")
    logfile.flush()

def ask_user_for_params():
    """
    Asks the user for the RCON IP, port, and password.
    If the user presses enter, use default values.
    Returns (ip, port, password).
    """
    default_ip = "127.0.0.1"
    default_port = "27015"
    default_cooldown = 5

    ip = input(f"Enter the server IP (press enter for '{default_ip}'): ")
    if not ip.strip():
        ip = default_ip

    port_str = input(f"Enter the RCON port (press enter for '{default_port}'): ")
    if not port_str.strip():
        port_str = default_port
    try:
        port = int(port_str)
    except ValueError:
        log_print(f"Invalid port, using default {default_port}.")
        port = int(default_port)

    password = ""
    while not password.strip():
        password = input("Enter the RCON password (mandatory): ")
        if not password.strip():
            log_print("Password cannot be empty.")

    cooldown_str = input(f"Enter the cooldown time (in minutes) before restarting (press enter for '{default_cooldown}'): ")
    if not cooldown_str.strip():
        cooldown_str = default_cooldown
    try:
        cooldown = int(cooldown_str)
    except ValueError:
        log_print(f"Invalid cooldown, using default {default_cooldown}.")
        cooldown = int(default_cooldown)

    return ip, port, password, cooldown

def ask_user_for_discord():
    """
    Asks the user if they want to enable Discord.
    If yes, asks for the webhook URLs for the server and logs.
    If no, sets USE_DISCORD=False.
    """
    global USE_DISCORD, DISCORD_WEBHOOK_URL, DISCORD_LOGSWEBHOOK_URL

    choice = input("Do you want to enable Discord notifications? (y/n): ").lower().strip()
    if choice in ["y", "yes"]:
        logchoice = input("Do you want to enable Discord log notifications? (y/n): ").lower().strip()
        if logchoice in ["y", "yes"]:
            logwebhook = input("Enter your Discord webhook URL for logs: ").strip()
            if logwebhook:
                DISCORD_LOGSWEBHOOK_URL = logwebhook
            else:
                log_print("No webhook entered, disabling Discord log notifications.")
        
        webhook = input("Enter your Discord webhook URL for server notifications: ").strip()
        if webhook:
            DISCORD_WEBHOOK_URL = webhook
        else:
            log_print("No webhook entered, disabling Discord server notifications.")
        
        if DISCORD_LOGSWEBHOOK_URL or DISCORD_WEBHOOK_URL:
            log_print("Discord notifications enabled.")
            USE_DISCORD = True
    else:
        log_print("Discord notifications disabled.")
        USE_DISCORD = False

def discord_message_sync(text, is_log=False):
    """
    If USE_DISCORD is True and we have a webhook, sends the message to the Discord channel for server status notifications;
    otherwise, exits immediately.
    if is_log=True, sends the message also to the log channel.
    """
    if not USE_DISCORD:
        return  # Do nothing

    data = {"content": text}
    
    if DISCORD_LOGSWEBHOOK_URL:
        resp = requests.post(DISCORD_LOGSWEBHOOK_URL, json=data)
        if not resp.status_code == 204:
            log_print(f"[DISCORD] Error sending log, status={resp.status_code}, resp={resp.text}")

    if is_log and DISCORD_WEBHOOK_URL:
        resp = requests.post(DISCORD_WEBHOOK_URL, json=data)
        if not resp.status_code == 204:
            log_print(f"[DISCORD] Error sending, status={resp.status_code}, resp={resp.text}")

def tail_f(log_file, timeout=1.0):
    """Reads in 'tail -f' style: starts from the end and yields each new line with a timeout."""
    try:
        with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
            f.seek(0, os.SEEK_END)
            while True:
                line = f.readline()
                if line:
                    yield line
                else:
                    time.sleep(timeout)
                    yield None
    except Exception as e:
        log_print(f"[ERROR] Error in tail_f function: {e}")

def get_players(rcon_client):
    """Returns the number of connected players, extracting from the 'players' response."""
    resp = rcon_client.command("players")
    text_output = resp.response  # the actual string
    match = re.search(r'\((\d+)\)', text_output)
    if match:
        return int(match.group(1))
    return 0

def broadcast_message(rcon_client, message):
    """Sends a global in-game message with 'servermsg'."""
    cmd = f'servermsg "{message}"'
    rcon_client.command(cmd)

def is_server_online_rcon():
    """
    Returns True if the RCON response contains "Players connected",
    False if the response contains "Connection refused" or if there is an exception.
    (You can customize based on your use cases.)
    """
    try:
        rcon = ZomboidRCON(ip=SERVER_IP, port=RCON_PORT, password=RCON_PASSWORD)
        resp = rcon.command("players")
        text = resp.response

        log_print(f"[DEBUG] RCON response: {repr(text)}")

        if "Players connected" in text:
            return True
        if "Connection refused" in text:
            return False

        # Any other unexpected string => consider offline (or decide yourself)
        return False

    except ConnectionRefusedError:
        log_print("[DEBUG] RCON: Connection refused, server offline")
        return False
    except Exception as e:
        log_print("[DEBUG] Other RCON error:", e)
        return False

def wait_for_server_offline_rcon(timeout=180, check_interval=5):
    """
    Checks every 'check_interval' seconds if the server is online via RCON.
    As soon as is_server_online_rcon() returns False => OFFLINE => return True.
    If 'timeout' seconds pass and it never goes offline => return False.
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        if not is_server_online_rcon():
            # means server_online = False => server offline
            return True
        time.sleep(check_interval)
    return False

def wait_for_server_online_rcon(timeout=300, check_interval=5):
    """
    Checks every 'check_interval' seconds if the server is online via RCON.
    As soon as is_server_online_rcon() returns True => ONLINE => return True.
    If 'timeout' seconds pass and it never goes online => return False.
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        if is_server_online_rcon():
            return True
        time.sleep(check_interval)
    return False

def handle_mods_update():
    minutes_left = COOLDOWN_RESTART
    log_print("[INFO] Mod update found. Starting restart procedure...")
    discord_message_sync(f"**Mod update detected!** Starting restart procedure in: {minutes_left}", is_log=True)
    rcon = ZomboidRCON(ip=SERVER_IP, port=RCON_PORT, password=RCON_PASSWORD)
    try:
        players_online = get_players(rcon)
        log_print(f"[INFO] Players online: {players_online}")
        discord_message_sync(f"Players online: {players_online}")

        if players_online > 0:
            while minutes_left > 0:
                msg = f"RESTART in {minutes_left} minutes!"
                broadcast_message(rcon, msg)
                discord_message_sync(msg)
                log_print(f"[INFO] Countdown warning: {minutes_left} minutes...")
                time.sleep(60)

                players_online = get_players(rcon)
                log_print(f"[INFO] Players online: {players_online}")
                discord_message_sync(f"Players online: {players_online}")
                if players_online == 0:
                    log_print("[INFO] No players online, skipping countdown and restarting immediately.")
                    discord_message_sync("No players online, restarting immediately.")
                    break
                minutes_left -= 1

        broadcast_message(rcon, "RESTART in 10 seconds!")
        discord_message_sync("**RESTART in 10 seconds!**")
        time.sleep(10)

        log_print("[INFO] Sending 'quit' command via RCON. AMP will handle the restart.")
        discord_message_sync("Sending 'quit' command via RCON. Waiting for the restart...")
        rcon.command("quit")

    except Exception as e:
        log_print(f"[ERROR] Error in handle_mods_update: {e}")
        discord_message_sync(f"**Error in handle_mods_update:** {e}")

    log_print("[INFO] End of mod update procedure (quit sent).")
    discord_message_sync("End of mod update procedure (quit sent).")

def monitor_loop():
    current_log_file = None

    while True:
        search_path = os.path.join(LOGS_DIR, PATTERN)
        files = glob.glob(search_path)
        if not files:
            log_print("[ERROR] No log file found. Retrying in 10s...")
            discord_message_sync("No log file found, retrying in 10s...")
            time.sleep(10)
            continue

        # If we are not already monitoring a file, select the most recent one
        if current_log_file is None or not os.path.exists(current_log_file):
            current_log_file = max(files, key=os.path.getmtime)
            log_print(f"[INFO] Monitoring file: {current_log_file}")
            discord_message_sync(f"Monitoring log file: `{current_log_file}`")

        for line in tail_f(current_log_file):
            if line:
                if "CheckModsNeedUpdate: Mods need update" in line:
                # if "CheckModsNeedUpdate: Mods updated" in line:    # MODS UPDATED for DEBUG ONLY
                    log_print("[ALERT] Mod update found in log!")
                    discord_message_sync("**Mods updated detected in log!** Proceeding with restart.")
                    handle_mods_update()

                    log_print("[INFO] Waiting for the server to shut down...")
                    discord_message_sync("Waiting for the server to shut down...")
                    offline_ok = wait_for_server_offline_rcon(timeout=180, check_interval=5)
                    if offline_ok:
                        log_print("[INFO] Server offline confirmed.")
                        discord_message_sync("**Server offline confirmed.**", is_log=True)
                    else:
                        log_print("[WARNING] The server did not go offline within 180s.")
                        discord_message_sync("**WARNING:** the server did not shut down within 180s.")

                    log_print("[INFO] Waiting for the server to come back online...")
                    discord_message_sync("Waiting for the server to come back online...")
                    online_ok = wait_for_server_online_rcon(timeout=300, check_interval=5)
                    if online_ok:
                        log_print("[INFO] Server online detected!")
                        discord_message_sync("**Server back online!**", is_log=True)
                    else:
                        log_print("[WARNING] The server did not come back online within 300s.")
                        discord_message_sync("**WARNING:** the server did not come back online within 300s.")

                    log_print("[INFO] Restart completed. Searching for a new log file...")
                    discord_message_sync("Restart completed, searching for a new log file.")
                    break
            else:
                # Periodic check for a new log file
                files = glob.glob(search_path)
                # log_print(f"[DEBUG] Found {len(files)} log files.")
                latest_log_file = max(files, key=os.path.getmtime)
                # log_print(f"[DEBUG] Latest log file: {latest_log_file}")
                if latest_log_file != current_log_file:
                    log_print(f"[INFO] New log file found: {latest_log_file}. Switching to monitor it.")
                    discord_message_sync(f"New log file detected: `{latest_log_file}`. Switching to monitor it.")
                    current_log_file = latest_log_file
                    break  # Exit the loop to select the new file

        time.sleep(2)

def main():
    global logfile
    logfile = init_logging()

    # Ask the user for RCON parameters
    global SERVER_IP, RCON_PORT, RCON_PASSWORD, COOLDOWN_RESTART
    SERVER_IP, RCON_PORT, RCON_PASSWORD, COOLDOWN_RESTART = ask_user_for_params()

    # Ask if they want to enable Discord and, if so, which webhook
    ask_user_for_discord()

    # If the user has enabled Discord
    if USE_DISCORD:
        discord_message_sync("**PZ Watchdog started.**")
        log_print("[INFO] PZ Watchdog started (with Discord notifications).")
    else:
        log_print("[INFO] PZ Watchdog started (without Discord notifications).")

    # Start monitoring the logs
    monitor_loop()
    time.sleep(2)

if __name__ == "__main__":
    main()
