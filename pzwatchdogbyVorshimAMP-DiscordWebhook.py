#!/usr/bin/env python3

import time
import os
import glob
import re
import requests
from zomboid_rcon import ZomboidRCON
import threading

# For Discord webhook notification
# DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/eccecc"
# DISCORD_LOGSWEBHOOK_URL = "https://discord.com/api/webhooks/eccecc"
# If the user decides NOT to use Discord, then USE_DISCORD=False

IS_AMP = True
CHECK_MODS_TIMER = 300

USE_DISCORD = False
DISCORD_LOGSWEBHOOK_URL = None
DISCORD_WEBHOOK_URL = None

# RCON parameters (will be set by ask_user_for_params)
SERVER_IP = "127.0.0.1"
RCON_PORT = 27015
RCON_PASSWORD = "..."
rcon = None

COOLDOWN_RESTART = 5

LOGS_DIR = "Logs"
PATTERN = "*_DebugLog-server.txt"
logfile = None

def init_logging():
    """
    Creates the Logs/PZWatchdogLogs folder (if it doesn't exist)
    and opens a log file with a timestamp in the filename,
    returning the open stream.
    """
    log_dir = "Logs/PZWatchdogLogs"
    os.makedirs(log_dir, exist_ok=True)

    time_str = time.strftime("%d-%m-%y_%H-%M-%S")
    filename = f"{time_str}_PZWDLog.txt"
    fullpath = os.path.join(log_dir, filename)

    lf = open(fullpath, "w", encoding="utf-8")
    return lf

def log_print(message, also_print=True, also_discord=False, is_log=False):
    """
    Prints and/or writes the message to the log file.
    If also_discord=True and USE_DISCORD=True, sends the message to Discord as well.
    If is_log=True, it will also send the message to the main (server) webhook, if available.
    """
    time_str = time.strftime("[%Y-%m-%d %H:%M:%S]")
    line = f"{time_str} {message}"

    if also_print:
        print(line)
    logfile.write(line + "\n")
    logfile.flush()

    if also_discord:
        discord_message_sync(message, is_log)

def ask_user_for_params():
    """
    Asks the user for the RCON IP, port, and password.
    If the user presses Enter, the default values are used.
    Returns (ip, port, password, cooldown, default_amp, timer).
    """
    default_ip = "127.0.0.1"
    default_port = "27015"
    default_cooldown = 5
    default_amp = True
    default_timer = 300

    amp = input("Are you using AMP Schedule for CheckModsNeedUpdate? (y/n): ").strip().lower()
    if amp in ["n", "no"]:
        default_amp = False
        timer_str = input(f"Enter the timer for checking mods (in seconds, press Enter for '{default_timer}'): ")
        if not timer_str.strip():
            timer_str = str(default_timer)
        try:
            timer = int(timer_str)
        except ValueError:
            log_print(f"Invalid timer, using default {default_timer}.")
            timer = default_timer

    ip = input(f"Enter the server IP (press Enter for '{default_ip}'): ")
    if not ip.strip():
        ip = default_ip

    port_str = input(f"Enter the RCON port (press Enter for '{default_port}'): ")
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

    cooldown_str = input(f"Enter the cooldown time (in minutes) before restarting (press Enter for '{default_cooldown}'): ")
    if not cooldown_str.strip():
        cooldown_str = str(default_cooldown)
    try:
        cooldown = int(cooldown_str)
    except ValueError:
        log_print(f"Invalid cooldown, using default {default_cooldown}.")
        cooldown = default_cooldown

    return ip, port, password, cooldown, default_amp, timer

def ask_user_for_discord():
    """
    Asks the user if they want to enable Discord notifications.
    If yes, asks for the webhook URLs (server and logs).
    """
    global USE_DISCORD, DISCORD_WEBHOOK_URL, DISCORD_LOGSWEBHOOK_URL

    choice = input("Do you want to enable Discord notifications? (y/n): ").strip().lower()
    if choice in ["y", "yes"]:
        logchoice = input("Do you want to enable Discord log notifications? (y/n): ").strip().lower()
        if logchoice in ["y", "yes"]:
            logwebhook = input("Enter your Discord webhook URL for logs: ").strip()
            if logwebhook:
                DISCORD_LOGSWEBHOOK_URL = logwebhook
            else:
                log_print("No log webhook entered, disabling Discord log notifications.")

        webhook = input("Enter your Discord webhook URL for server notifications: ").strip()
        if webhook:
            DISCORD_WEBHOOK_URL = webhook
        else:
            log_print("No server webhook entered, disabling Discord server notifications.")

        if DISCORD_LOGSWEBHOOK_URL or DISCORD_WEBHOOK_URL:
            log_print("Discord notifications enabled.")
            USE_DISCORD = True
    else:
        log_print("Discord notifications disabled.")
        USE_DISCORD = False

def discord_message_sync(text, is_log=False):
    """
    If USE_DISCORD=True, sends the text to Discord.
    If is_log=True, also sends to the main server webhook (if configured),
    otherwise only to the log webhook.
    Adjust as needed for your own webhook logic.
    """
    if not USE_DISCORD:
        return

    data = {"content": text}

    # Send to the logs webhook if available
    if DISCORD_LOGSWEBHOOK_URL:
        resp = requests.post(DISCORD_LOGSWEBHOOK_URL, json=data)
        if resp.status_code != 204:
            log_print(f"[DISCORD] Error sending to log webhook, status={resp.status_code}, resp={resp.text}")

    # If is_log=True, also send to the main server webhook if available
    if is_log and DISCORD_WEBHOOK_URL:
        resp = requests.post(DISCORD_WEBHOOK_URL, json=data)
        if resp.status_code != 204:
            log_print(f"[DISCORD] Error sending to server webhook, status={resp.status_code}, resp={resp.text}")

def tail_f(log_file, timeout=1.0):
    """
    Reads lines from the log file in a 'tail -f' style: 
    starts at the end and yields each new line with a timeout.
    """
    try:
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            f.seek(0, os.SEEK_END)
            while True:
                line = f.readline()
                if line:
                    yield line
                else:
                    time.sleep(timeout)
                    yield None
    except Exception as e:
        log_print(f"[ERROR] Error in tail_f: {e}", also_discord=True)

def get_players():
    """
    Returns the number of connected players, extracted from the 'players' RCON response.
    """
    try:
        resp = rcon.players()
        text_output = resp.response
        match = re.search(r"\((\d+)\)", text_output)
        if match:
            return int(match.group(1))
        return 0
    except ConnectionRefusedError:
        log_print("[DEBUG] RCON: Connection refused, server offline")
        return False
    except Exception as e:
        log_print(("[DEBUG] Other RCON error:", e))
        return False

def broadcast_message(message):
    """
    Sends a global in-game message via 'servermsg' using RCON.
    """
    try:
        rcon.servermsg(message)
    except ConnectionRefusedError:
        log_print("[DEBUG] RCON: Connection refused, server offline")
        return False
    except Exception as e:
        log_print(("[DEBUG] Other RCON error:", e))
        return False

def is_server_online_rcon():
    """
    Returns True if the RCON response contains "Players connected".
    Returns False if the response indicates "Connection refused" or if an exception occurs.
    """
    try:
        resp = rcon.players()
        text = resp.response

        log_print(f"[DEBUG] RCON response: {repr(text)}")

        if "Players connected" in text:
            return True
        if "Connection refused" in text:
            return False

        return False
    except ConnectionRefusedError:
        log_print("[DEBUG] RCON: Connection refused, server offline")
        return False
    except Exception as e:
        log_print(("[DEBUG] Other RCON error:", e))
        return False

def wait_for_server_offline_rcon(timeout=180, check_interval=5):
    """
    Checks every 'check_interval' seconds if the server is offline via RCON.
    Returns True as soon as it's offline, or False if 'timeout' is exceeded.
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        if not is_server_online_rcon():
            return True
        time.sleep(check_interval)
    return False

def wait_for_server_online_rcon(timeout=300, check_interval=5):
    """
    Checks every 'check_interval' seconds if the server is online via RCON.
    Returns True as soon as it's online, or False if 'timeout' is exceeded.
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        if is_server_online_rcon():
            return True
        time.sleep(check_interval)
    return False

def handle_mods_update():
    """
    Handles the mod update event by warning players, counting down, 
    and sending the 'quit' command to RCON so that AMP (if used) restarts the server.
    """
    minutes_left = COOLDOWN_RESTART
    log_print(
        f"[INFO] Mod update detected! Starting restart procedure in: {minutes_left} minute(s).",
        also_discord=True,
        is_log=True
    )
    try:
        players_online = get_players()
        log_print(f"[INFO] Players online: {players_online}", also_discord=True)

        if players_online > 0:
            while minutes_left > 0:
                msg = f"RESTART in {minutes_left} minute(s)!"
                broadcast_message(msg)
                log_print(msg, also_discord=True)
                time.sleep(60)

                players_online = get_players()
                log_print(f"[INFO] Players online: {players_online}", also_discord=True)
                if players_online == 0:
                    log_print("[INFO] No players online, skipping countdown and restarting immediately.", also_discord=True)
                    break
                minutes_left -= 1

        broadcast_message("RESTART in 10 seconds!")
        log_print("RESTART in 10 seconds!", also_discord=True)
        time.sleep(10)

        log_print("[INFO] Sending 'quit' command via RCON. AMP will handle the restart.", also_discord=True)
        rcon.quit()
    except Exception as e:
        log_print(f"[ERROR] Error in handle_mods_update: {e}", also_discord=True)

    log_print("[INFO] End of mod update procedure (quit sent).", also_discord=True)

def check_mods_update():
    """
    If IS_AMP is False, call RCON's checkModsNeedUpdate 
    (depending on how your server logic is set up).
    """
    try:
        rcon.checkModsNeedUpdate()
        log_print("[INFO] Checking for mod updates...", also_discord=True)
    except ConnectionRefusedError:
        log_print("[DEBUG] RCON: Connection refused, server offline")
        return False
    except Exception as e:
        log_print(("[DEBUG] Other RCON error:", e))
        return False

def monitor_loop():
    """
    Main monitoring loop: selects the latest server log file, tails it,
    and looks for lines that indicate a mod update. 
    When a mod update is detected, calls handle_mods_update and 
    waits for the server to restart.
    """
    current_log_file = None
    if not IS_AMP:
        log_print(f"[INFO] AMP Schedule is not used, will check for mod updates every {CHECK_MODS_TIMER/60} minute(s).", also_discord=True)
        last_check_time = time.time()

    while True:
        search_path = os.path.join(LOGS_DIR, PATTERN)
        files = glob.glob(search_path)
        if not files:
            log_print("[ERROR] No log file found. Retrying in 10 seconds...", also_discord=True)
            time.sleep(10)
            continue

        # If we're not currently monitoring a file, or that file doesn't exist, pick the newest
        if current_log_file is None or not os.path.exists(current_log_file):
            current_log_file = max(files, key=os.path.getmtime)
            log_print(f"[INFO] Monitoring file: {current_log_file}", also_discord=True)

        for line in tail_f(current_log_file):
            if line:
                # Example check for mod update lines
                if "CheckModsNeedUpdate: Mods need update" in line:
                # if "CheckModsNeedUpdate: Mods updated" in line:    # "Mods updated" for DEBUG ONLY
                    log_print("[ALERT] Mod update found in the log!", also_discord=True)
                    handle_mods_update()

                    log_print("[INFO] Waiting for the server to shut down...", also_discord=True)
                    offline_ok = wait_for_server_offline_rcon(timeout=180, check_interval=5)
                    if offline_ok:
                        log_print("[INFO] Server offline confirmed.", also_discord=True, is_log=True)
                    else:
                        log_print("[WARNING] The server did not go offline within 180 seconds.", also_discord=True)

                    log_print("[INFO] Waiting for the server to come back online...", also_discord=True)
                    online_ok = wait_for_server_online_rcon(timeout=300, check_interval=5)
                    if online_ok:
                        log_print("[INFO] Server online detected!", also_discord=True, is_log=True)
                    else:
                        log_print("[WARNING] The server did not come back online within 300 seconds.", also_discord=True)

                    log_print("[INFO] Restart completed. Searching for a new log file...", also_discord=True)
                    break
            else:
                # Check if 60 seconds have passed since the last check if we're not using AMP
                if not IS_AMP and time.time() - last_check_time > CHECK_MODS_TIMER:
                    check_mods_update()
                    last_check_time = time.time()

                # Periodically check if a new log file has appeared
                files = glob.glob(search_path)
                latest_log_file = max(files, key=os.path.getmtime)
                if latest_log_file != current_log_file:
                    log_print(f"[INFO] New log file detected: {latest_log_file}. Switching to monitor it.", also_discord=True)
                    current_log_file = latest_log_file
                    break

        time.sleep(2)

def main():
    global logfile
    logfile = init_logging()

    global SERVER_IP, RCON_PORT, RCON_PASSWORD, COOLDOWN_RESTART, IS_AMP, CHECK_MODS_TIMER
    SERVER_IP, RCON_PORT, RCON_PASSWORD, COOLDOWN_RESTART, IS_AMP, CHECK_MODS_TIMER = ask_user_for_params()

    global rcon
    rcon = ZomboidRCON(ip=SERVER_IP, port=RCON_PORT, password=RCON_PASSWORD)

    ask_user_for_discord()

    if USE_DISCORD:
        log_print("PZ Watchdog started (with Discord notifications).", also_discord=True)
    else:
        log_print("PZ Watchdog started (without Discord notifications).")

    monitor_loop()
    time.sleep(2)

if __name__ == "__main__":
    main()