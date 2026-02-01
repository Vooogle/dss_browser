import os
import json
import subprocess
import time
import psutil

# =========================
# Settings file location
# =========================
SETTINGS_FILE = os.path.join(
    os.path.expanduser("~"),
    ".dssb_server_browser",
    "settings.json"
)

# =========================
# Settings helpers
# =========================
def get_settings():
    if not os.path.exists(SETTINGS_FILE):
        return {}

    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print("[SETTINGS] Failed to read settings:", e)
        return {}


def get_game_folder():
    return get_settings().get("game_folder", "")


def get_launcher():
    return get_settings().get("launcher", "steam")


def is_linux_enabled():
    return bool(get_settings().get("is_linux", False))


def is_steam_uri_mode():
    return bool(get_settings().get("steam_uri_mode", False))


def get_game_executable():
    folder = get_game_folder()
    if not folder:
        return None

    candidates = [
        os.path.join(folder, "Bully.exe"),
        os.path.join(folder, "bin", "Bully.exe"),
        os.path.join(folder, "Bin", "Bully.exe"),
    ]

    for exe in candidates:
        if os.path.exists(exe):
            return exe

    return None


def is_game_configured():
    launcher = get_launcher()
    if launcher == "steam":
        return find_steam_exe() is not None
    exe = get_game_executable()
    return exe is not None and os.path.exists(exe)

# =========================
# Launcher discovery
# =========================
def find_steam_exe():
    settings = get_settings()
    custom = settings.get("steam_exe", "")

    if custom and os.path.exists(custom):
        return custom

    if is_linux_enabled():
        home = os.path.expanduser("~")
        linux_candidates = [
            os.path.join(home, ".steam", "steam"),
            os.path.join(home, ".steam", "root", "steam"),
            os.path.join(home, ".steam", "steam.sh"),
            os.path.join(home, ".local", "share", "Steam", "steam.sh"),
        ]
        for path in linux_candidates:
            if os.path.exists(path):
                return path

    common = [
        r"C:\Program Files (x86)\Steam\steam.exe",
        r"C:\Program Files\Steam\steam.exe",
    ]

    for path in common:
        if os.path.exists(path):
            return path

    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\WOW6432Node\Valve\Steam"
        )
        install_path = winreg.QueryValueEx(key, "InstallPath")[0]
        winreg.CloseKey(key)

        steam_exe = os.path.join(install_path, "steam.exe")
        if os.path.exists(steam_exe):
            return steam_exe
    except Exception:
        pass

    return None


def find_rockstar_launcher():
    settings = get_settings()
    custom = settings.get("launcher_exe", "")

    if custom and os.path.exists(custom):
        return custom

    common = [
        r"C:\Program Files\Rockstar Games\Launcher\Launcher.exe",
        r"C:\Program Files (x86)\Rockstar Games\Launcher\Launcher.exe",
    ]

    for path in common:
        if os.path.exists(path):
            return path

    return None

# =========================
# Rockstar handling
# =========================
def kill_rockstar_launcher():
    killed = False

    for proc in psutil.process_iter(["name", "exe"]):
        try:
            name = proc.info["name"] or ""
            exe = proc.info["exe"] or ""

            if "rockstar" in exe.lower() and "launcher" in name.lower():
                print(f"[ROCKSTAR] Killing {name}")
                proc.kill()
                killed = True

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    if killed:
        time.sleep(2)

    return killed

# =========================
# Game launch entry point
# =========================
def launch_game(ip, port, username, password):
    game_folder = get_game_folder()
    launcher = get_launcher()

    print(f"[LAUNCH] Launcher = {launcher}")

    if launcher == "steam":
        return launch_via_steam(ip, port, username, password)

    if launcher == "rockstar":
        if not game_folder:
            print("ERROR: Game folder not configured.")
            return False
        return launch_via_rockstar(ip, port, username, password)

    print(f"ERROR: Unknown launcher '{launcher}'")
    return False

# =========================
# Steam launch
# =========================
def launch_via_steam(ip, port, username, password):
    steam_exe = find_steam_exe()
    if not steam_exe:
        print("ERROR: Steam executable not found")
        return False

    STEAM_APP_ID = "12200"

    args = [
        "--joinServerASAP",
        f"{ip}:{port}",
        "--username",
        username,
        "--password",
        password
    ]

    if is_steam_uri_mode():
        import webbrowser
        import urllib.parse
        arg_str = " ".join(args)
        encoded = urllib.parse.quote(arg_str)
        uri = f"steam://run/{STEAM_APP_ID}//{encoded}"
        try:
            print("[STEAM] Launching via Steam URI")
            webbrowser.open(uri)
            return True
        except Exception as e:
            print("ERROR: Steam URI launch failed:", e)
            return False

    cmd = [
        steam_exe,
        "-applaunch",
        STEAM_APP_ID,
        *args
    ]

    try:
        print("[STEAM] Launching DSS via Steam")
        if is_linux_enabled():
            subprocess.Popen(cmd)
        else:
            subprocess.Popen(cmd, start_new_session=True)
        return True
    except Exception as e:
        print("ERROR: Steam launch failed:", e)
        return False

# =========================
# Rockstar launch
# =========================
def launch_via_rockstar(ip, port, username, password):
    launcher_exe = find_rockstar_launcher()
    if not launcher_exe:
        print("ERROR: Rockstar Launcher not found")
        return False

    game_folder = get_game_folder()

    print("[ROCKSTAR] Closing launcher first")
    kill_rockstar_launcher()

    cmd = [
        launcher_exe,
        "-launchTitleInFolder",
        game_folder,
        "--skipMoviesASAP",
        "--joinServerASAP",
        f"{ip}:{port}",
        "--username",
        username,
        "--password",
        password
    ]

    try:
        print("[ROCKSTAR] Launching DSS via Rockstar Launcher")
        subprocess.Popen(cmd, start_new_session=True)
        return True
    except Exception as e:
        print("ERROR: Rockstar launch failed:", e)
        return False
