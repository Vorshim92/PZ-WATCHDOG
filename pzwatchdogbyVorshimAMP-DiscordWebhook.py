#!/usr/bin/env python3

import time
import os
import glob
import re
import requests
from zomboid_rcon import ZomboidRCON

# Per la notifica Discord webhook
# DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/eccecc"
# DISCORD_LOGSWEBHOOK_URL = "https://discord.com/api/webhooks/eccecc"
# Se l'utente decide di NON usare Discord, mettiamo USE_DISCORD=False

USE_DISCORD = False
DISCORD_LOGSWEBHOOK_URL = None
DISCORD_WEBHOOK_URL = None

# Parametri RCON (saranno impostati da ask_user_for_params se vuoi)
SERVER_IP = "127.0.0.1"
RCON_PORT = 27015
RCON_PASSWORD = "..."

LOGS_DIR = "Logs"
PATTERN = "*_DebugLog-server.txt"
logfile = None
def init_logging():
    """
    Crea la cartella Logs/PZWatchdogLogs (se non esiste)
    e apre un file log con timestamp nel nome,
    restituendo lo stream aperto.
    """
    log_dir = "Logs/PZWatchdogLogs"
    os.makedirs(log_dir, exist_ok=True)

    # Creiamo un timestamp per il nome file: es. '2023-12-25_11-03-00_PZWDLog.txt'
    time_str = time.strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{time_str}_PZWDLog.txt"
    fullpath = os.path.join(log_dir, filename)

    # Apriamo il file in scrittura
    logfile = open(fullpath, "w", encoding="utf-8")
    return logfile

def log_print(message, also_print=True):
    """
    Stampa e/o scrive su file il messaggio.
    - logfile: stream aperto in scrittura
    - message: stringa da loggare
    - also_print: se True, stampa anche a video, non passandolo sarà sempre True di base
    """
    # Prepara un timestamp per la riga
    time_str = time.strftime("[%Y-%m-%d %H:%M:%S]")
    line = f"{time_str} {message}"

    if also_print:
        print(line)
    # Scriviamo la riga su file e facciamo flush
    logfile.write(line + "\n")
    logfile.flush()

def ask_user_for_params():
    """
    Chiede a utente IP, porta e password RCON.
    Se l'utente preme invio, usa valori di default.
    Ritorna (ip, port, password).
    """
    default_ip = "127.0.0.1"
    default_port = "27015"

    ip = input(f"Inserisci l'IP del server (invio per '{default_ip}'): ")
    if not ip.strip():
        ip = default_ip

    port_str = input(f"Inserisci la porta RCON (invio per '{default_port}'): ")
    if not port_str.strip():
        port_str = default_port
    try:
        port = int(port_str)
    except ValueError:
        log_print(f"Porta non valida, uso default {default_port}.")
        port = int(default_port)

    password = ""
    while not password.strip():
        password = input("Inserisci la password RCON (obbligatoria): ")
        if not password.strip():
            log_print("La password non può essere vuota.")

    return ip, port, password

def ask_user_for_discord():
    """
    Chiede all'utente se vuole abilitare Discord.
    Se sì, chiede i webhook URLs per il server e per i log.
    Se no, imposta USE_DISCORD=False.
    """
    global USE_DISCORD, DISCORD_WEBHOOK_URL, DISCORD_LOGSWEBHOOK_URL

    choice = input("Vuoi abilitare le notifiche su Discord? (s/n): ").lower().strip()
    if choice in ["s", "si", "y"]:
        logchoice = input("Vuoi abilitare le notifiche dei log su Discord? (s/n): ").lower().strip()
        if logchoice in ["s", "si", "y"]:
            logwebhook = input("Inserisci l'URL del tuo webhook Discord per i log: ").strip()
            if logwebhook:
                DISCORD_LOGSWEBHOOK_URL = logwebhook
            else:
                log_print("Nessun webhook inserito, disabilito le notifiche dei log su Discord.")
        
        webhook = input("Inserisci l'URL del tuo webhook Discord per le notifiche del server: ").strip()
        if webhook:
            DISCORD_WEBHOOK_URL = webhook
        else:
            log_print("Nessun webhook inserito, disabilito le notifiche del server su Discord.")
        
        if DISCORD_LOGSWEBHOOK_URL or DISCORD_WEBHOOK_URL:
            log_print("Notifiche Discord abilitate.")
            USE_DISCORD = True
    else:
        log_print("Notifiche Discord disabilitate.")
        USE_DISCORD = False

def discord_message_sync(text, is_log=False):
    """
    Se USE_DISCORD è True e abbiamo un webhook, invia il messaggio al channel Discord per notifiche stato Server;
    altrimenti esce subito.
    se is_log=True, invia il messaggio anche al channel per i log.
    """
    if not USE_DISCORD:
        return  # Non fare nulla

    data = {"content": text}
    if DISCORD_WEBHOOK_URL:
        resp = requests.post(DISCORD_WEBHOOK_URL, json=data)
        if resp.status_code == 204:
            log_print("[DISCORD] Messaggio inviato con successo.")
        else:
            log_print(f"[DISCORD] Errore nell'invio, status={resp.status_code}, resp={resp.text}")
    
    if is_log and DISCORD_LOGSWEBHOOK_URL:
        resp = requests.post(DISCORD_LOGSWEBHOOK_URL, json=data)
        if resp.status_code == 204:
            log_print("[DISCORD] Messaggio di log inviato con successo.")
        else:
            log_print(f"[DISCORD] Errore nell'invio del log, status={resp.status_code}, resp={resp.text}")


def tail_f(log_file):
    """Legge in stile 'tail -f': parte dalla fine e yield-a ogni nuova riga."""
    with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
        f.seek(0, os.SEEK_END)
        while True:
            line = f.readline()
            if not line:
                time.sleep(1.0)
                continue
            yield line

def get_players(rcon_client):
    """Restituisce il numero di giocatori connessi, estraendo dalla risposta di 'players'."""
    resp = rcon_client.command("players")
    text_output = resp.response  # la stringa vera e propria
    match = re.search(r'\((\d+)\)', text_output)
    if match:
        return int(match.group(1))
    return 0

def broadcast_message(rcon_client, message):
    """Invia messaggio globale in-game con 'servermsg'."""
    cmd = f'servermsg "{message}"'
    rcon_client.command(cmd)

def is_server_online_rcon():
    """
    Restituisce True se la risposta RCON contiene "Players connected",
    False se la risposta contiene "Connection refused" o se c'è un'eccezione.
    (Puoi personalizzare in base ai tuoi casi d'uso.)
    """
    try:
        rcon = ZomboidRCON(ip=SERVER_IP, port=RCON_PORT, password=RCON_PASSWORD)
        resp = rcon.command("players")
        text = resp.response

        log_print(f"[DEBUG] Risposta RCON: {repr(text)}")

        if "Players connected" in text:
            return True
        if "Connection refused" in text:
            return False

        # Qualsiasi altra stringa inattesa => consideriamo offline (o decidi tu)
        return False

    except ConnectionRefusedError:
        log_print("[DEBUG] RCON: Connection refused, server offline")
        return False
    except Exception as e:
        log_print("[DEBUG] Altro errore RCON:", e)
        return False

def wait_for_server_offline_rcon(timeout=180, check_interval=5):
    """
    Controlla ogni 'check_interval' secondi se il server è online via RCON.
    Appena is_server_online_rcon() restituisce False => OFFLINE => return True.
    Se passano 'timeout' secondi e non diventa mai offline => return False.
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        if not is_server_online_rcon():
            # signica server_online = False => server offline
            return True
        time.sleep(check_interval)
    return False

def wait_for_server_online_rcon(timeout=300, check_interval=5):
    """
    Controlla ogni 'check_interval' secondi se il server risulta online via RCON.
    Appena is_server_online_rcon() restituisce True => ONLINE => return True.
    Se passano 'timeout' secondi e non diventa mai online => return False.
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        if is_server_online_rcon():
            return True
        time.sleep(check_interval)
    return False

def handle_mods_update():
    log_print("[INFO] Trovato aggiornamento mod. Avvio procedura di riavvio...")
    discord_message_sync("**Aggiornamento mod rilevato!** Avvio procedura di riavvio...", is_log=True)

    rcon = ZomboidRCON(ip=SERVER_IP, port=RCON_PORT, password=RCON_PASSWORD)
    try:
        players_online = get_players(rcon)
        log_print(f"[INFO] Giocatori online: {players_online}")

        if players_online > 0:
            minutes_left = 5
            while minutes_left > 0:
                msg = f"RIAVVIO tra {minutes_left} minuti!"
                broadcast_message(rcon, msg)
                discord_message_sync(msg)
                log_print(f"[INFO] Avviso countdown: {minutes_left} minuti...")
                time.sleep(60)

                players_online = get_players(rcon)
                if players_online == 0:
                    log_print("[INFO] Nessun giocatore online, skip countdown e riavvio subito.")
                    discord_message_sync("Nessun giocatore online, riavvio immediato.")
                    break
                minutes_left -= 1

        broadcast_message(rcon, "RIAVVIO tra 10 secondi!")
        discord_message_sync("**RIAVVIO tra 10 secondi!**")
        time.sleep(10)

        log_print("[INFO] Invio comando 'quit' via RCON. AMP gestirà il riavvio.")
        discord_message_sync("Invio comando 'quit' via RCON. Attendo il riavvio...")
        rcon.command("quit")

    except Exception as e:
        log_print(f"[ERROR] Errore in handle_mods_update: {e}")
        discord_message_sync(f"**Errore in handle_mods_update:** {e}")

    log_print("[INFO] Fine procedura update mod (quit inviato).")
    discord_message_sync("Fine procedura update mod (quit inviato).")

def main():
    global logfile
    logfile = init_logging()

    # Chiedi parametri RCON all'utente
    global SERVER_IP, RCON_PORT, RCON_PASSWORD
    SERVER_IP, RCON_PORT, RCON_PASSWORD = ask_user_for_params()

    # Chiedi se abilitare Discord e, se sì, quale webhook
    ask_user_for_discord()

    # Se l'utente ha abilitato Discord
    if USE_DISCORD:
        discord_message_sync("**PZ Watchdog avviato.**")
    else:
        log_print("[INFO] PZ Watchdog avviato (senza notifiche Discord).")

    while True:
        search_path = os.path.join(LOGS_DIR, PATTERN)
        files = glob.glob(search_path)
        if not files:
            log_print("[ERROR] Nessun file log trovato. Riprovo tra 10s...")
            discord_message_sync("Nessun file di log trovato, riprovo tra 10s...")
            time.sleep(10)
            continue

        log_file = max(files, key=os.path.getmtime)
        log_print(f"[INFO] Monitoro il file: {log_file}")
        discord_message_sync(f"Monitoro il file di log: `{log_file}`")

        for line in tail_f(log_file):
            if "CheckModsNeedUpdate: Mods need update" in line:
            # if "CheckModsNeedUpdate: Mods updated" in line:    # MODS UPDATED for DEBUG ONLY
                log_print("[ALERT] Trovato aggiornamento mod nel log!")
                discord_message_sync("**Mods updated rilevato nel log!** Procedo al riavvio.")
                handle_mods_update()

                log_print("[INFO] Attendo che il server si spenga...")
                discord_message_sync("Attendo che il server si spenga...")
                offline_ok = wait_for_server_offline_rcon(timeout=180, check_interval=5)
                if offline_ok:
                    log_print("[INFO] Server offline confermato.")
                    discord_message_sync("**Server offline confermato.**")
                else:
                    log_print("[WARNING] Il server non è andato offline entro 180s.")
                    discord_message_sync("**ATTENZIONE:** il server non si è spento entro 180s.")

                log_print("[INFO] Attendo che il server torni online...")
                discord_message_sync("Attendo che il server torni online...")
                online_ok = wait_for_server_online_rcon(timeout=300, check_interval=5)
                if online_ok:
                    log_print("[INFO] Server online rilevato!")
                    discord_message_sync("**Server di nuovo online!**")
                else:
                    log_print("[WARNING] Il server non è tornato online entro 300s.")
                    discord_message_sync("**ATTENZIONE:** il server non è tornato online entro 300s.")

                log_print("[INFO] Riavvio concluso. Ricerco eventuale nuovo file di log...")
                discord_message_sync("Riavvio concluso, ricerco un eventuale nuovo file di log.")
                break

        time.sleep(2)

if __name__ == "__main__":
    main()
