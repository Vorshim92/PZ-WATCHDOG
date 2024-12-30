# Project Zomboid Watchdog Setup

## Instructions

1. Place the script in the Zomboid folder of the server.
2. From an SSH terminal (execute as user AMP, if you are root use the command `su amp`).

### If not already installed on the machine:
```sh
sudo apt update
sudo apt install python3 python3-venv screen
```

### Navigate to the Zomboid folder of the desired instance and follow the commands below (only the first time you initialize the script):
```sh
cd /home/amp/.ampdata/instances/SERVER_NAME/project-zomboid/380870/Zomboid
python3 -m venv pz_venv
screen -S pz_venv
source pz_venv/bin/activate
pip install zomboid-rcon
pip install requests
python3 pzwatchdogbyVorshimAMP-DiscordWebhook.py
```

At this point, the script will start, and you will need to enter the required data in the prompt: amp, timer, IP (leave as 127.0.0.1), RCON port, RCON password, Discord (if any), and webhook URL. The script will then listen to the DebugLog (the Server console).

You can close the SSH window (putty) or detach from the SCREEN by pressing:
`Ctrl + a`, then `d`

### Schedule on AMP
Set the schedule to every 5 minutes or as desired. It is mandatory to send the command `rcon/console "checkModsNeedUpdate"` (as shown in the screenshot). Otherwise, at the start of the script, select NO when asked if you are using AMP scheduling so that the script itself performs this check.

**Note:** The AMP schedule is not mandatory. The script works even if AMP is not used. At the beginning, you will be asked if you are using AMP scheduling. If not, you can set a timer to send the command that checks for updates on the server (all via RCON).

At this point, no further action is required. The script will persist even after a PZ server reboot. However, if the machine is turned off, you will need to restart the script:

### SSH connection:
```sh
cd /home/amp/.ampdata/instances/SERVER_NAME/project-zomboid/380870/Zomboid
screen -S pz_venv
source pz_venv/bin/activate
python3 pzwatchdogbyVorshimAMP-DiscordWebhook.py
```
Re-enter the settings in the prompt as requested.
`Ctrl + a`, then `d` OR close the SSH window.

### To reopen the script session:
```sh
screen -r pz_venv
```

If it does not reopen, try:
```sh
screen -D -r pz_venv
```