import os
import json
import webbrowser
import platform

from PyQt6.QtWidgets import QFileDialog
from PyQt6.QtCore import Qt
from backend.ui_manager import HTMLWindow

# Default settings file location
SETTINGS_FILE = os.path.join(os.path.expanduser("~"), ".dssb_server_browser", "settings.json")


# -----------------------------
# Storage helpers
# -----------------------------
def get_settings() -> dict:
    if not os.path.exists(SETTINGS_FILE):
        return {}
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception as e:
        print("[SETTINGS] Failed to read settings:", e)
        return {}


def save_settings_update(update: dict) -> None:
    """
    Merge update into existing settings and write back.
    This prevents wiping keys like 'launcher' accidentally.
    """
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    current = get_settings()
    current.update(update)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2)


def get_game_folder() -> str:
    return get_settings().get("game_folder", "")


def is_system_linux() -> bool:
    return platform.system().lower() == "linux"




# -----------------------------
# Dialog creation
# -----------------------------
def create_settings_dialog():
    # Resolve paths
    current_dir = os.path.dirname(os.path.abspath(__file__))  # backend/ui
    backend_dir = os.path.dirname(current_dir)                # backend
    project_root = os.path.dirname(backend_dir)               # project root
    html_path = os.path.join(project_root, "frontend", "settings.html")

    if not os.path.exists(html_path):
        raise FileNotFoundError(f"HTML file not found: {html_path}")

    callbacks = {
            # close
            "close": lambda _: dialog.close(),

            # ---- BROWSE aliases ----
            # Frontend might emit "browse" or "browseGameFolder"
            "browse": lambda _: handle_browse_game_folder(dialog),
            "browseGameFolder": lambda _: handle_browse_game_folder(dialog),

            # Optional extra browse events
            "browseSteamExe": lambda _: handle_browse_steam_exe(dialog),
            "browseLauncherExe": lambda _: handle_browse_launcher_exe(dialog),

            # ---- SAVE aliases ----
            # Frontend currently emits "save" -> this fixes your WARN
            "save": lambda data: handle_save_settings(data, dialog),
            "saveSettings": lambda data: handle_save_settings(data, dialog),

            # external links
            "openGithub": lambda _: open_github(),
            "openDiscord": lambda _: open_discord(),
            "openAdmin": lambda _: handle_open_admin(),
            "openUpdate": lambda _: handle_open_update(),
        }

    dialog = HTMLWindow(
        html_path=html_path,
        size=(600, 420),
        enable_drag=False,
        callbacks=callbacks
    )

    callbacks["dragMove"] = dialog._handle_drag_move


    dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
    dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
    dialog.activateWindow()
    dialog.view.loadFinished.connect(lambda: load_settings_into_ui(dialog))
    return dialog




def load_settings_into_ui(dialog):
    """
    Push current settings into the page if the JS helper functions exist.
    """
    s = get_settings()

    def esc(v: str) -> str:
        return (v or "").replace("\\", "\\\\").replace("'", "\\'")

    # These functions will be defined in frontend/settings.js below.
    if s.get("game_folder"):
        dialog.view.page().runJavaScript(
            f"if (typeof setFolderPath === 'function') setFolderPath('{esc(s['game_folder'])}');"
        )

    dialog.view.page().runJavaScript(
        f"if (typeof setLauncher === 'function') setLauncher('{esc(s.get('launcher','steam'))}');"
    )

    if s.get("list_url"):
        dialog.view.page().runJavaScript(
            f"if (typeof setListUrl === 'function') setListUrl('{esc(s.get('list_url'))}');"
        )
    else:
        dialog.view.page().runJavaScript(
            "if (typeof setListUrl === 'function') setListUrl('');"
        )
    only_filters = s.get("only_filters") or {"important": True, "trusted": True, "others": True}
    dialog.view.page().runJavaScript(
        f"if (typeof setOnlyFilters === 'function') setOnlyFilters({json.dumps(only_filters)});"
    )

    if s.get("steam_exe"):
        dialog.view.page().runJavaScript(
            f"if (typeof setSteamExe === 'function') setSteamExe('{esc(s['steam_exe'])}');"
        )

    if s.get("launcher_exe"):
        dialog.view.page().runJavaScript(
            f"if (typeof setLauncherExe === 'function') setLauncherExe('{esc(s['launcher_exe'])}');"
        )

    dialog.view.page().runJavaScript(
        f"if (typeof setLinux === 'function') setLinux({str(bool(s.get('is_linux', False))).lower()});"
    )
    dialog.view.page().runJavaScript(
        f"if (typeof setUriMode === 'function') setUriMode({str(bool(s.get('steam_uri_mode', False))).lower()});"
    )
    dialog.view.page().runJavaScript(
        f"if (typeof setSystemLinux === 'function') setSystemLinux({str(is_system_linux()).lower()});"
    )


# -----------------------------
# Browse handlers
# -----------------------------
def handle_browse_game_folder(dialog):
    current_folder = get_game_folder()

    folder = QFileDialog.getExistingDirectory(
        dialog,
        "Select Bully: Scholarship Edition Installation Folder",
        current_folder or ""
    )

    if folder:
        print(f"[SETTINGS] Selected game folder: {folder}")
        folder_js = folder.replace("\\", "\\\\").replace("'", "\\'")
        dialog.view.page().runJavaScript(
            f"var el=document.getElementById('folder-input'); if(el) el.value='{folder_js}';"
        )


def handle_browse_steam_exe(dialog):
    s = get_settings()
    current = s.get("steam_exe") or r"C:\Program Files (x86)\Steam\steam.exe"

    if is_system_linux():
        exe, _ = QFileDialog.getOpenFileName(
            dialog,
            "Select Steam file",
            current,
            "All Files (*)"
        )
    else:
        exe, _ = QFileDialog.getOpenFileName(
            dialog,
            "Select steam.exe",
            current,
            "Executable Files (*.exe)"
        )

    if exe:
        print(f"[SETTINGS] Selected Steam exe: {exe}")
        exe_js = exe.replace("\\", "\\\\").replace("'", "\\'")
        dialog.view.page().runJavaScript(
            f"var el=document.getElementById('steam-exe-input'); if(el) el.value='{exe_js}';"
        )


def handle_browse_launcher_exe(dialog):
    s = get_settings()
    current = s.get("launcher_exe") or r"C:\Program Files\Rockstar Games\Launcher\Launcher.exe"

    exe, _ = QFileDialog.getOpenFileName(
        dialog,
        "Select Rockstar Games Launcher (Launcher.exe)",
        current,
        "Executable Files (*.exe)"
    )

    if exe:
        print(f"[SETTINGS] Selected Rockstar Launcher exe: {exe}")
        exe_js = exe.replace("\\", "\\\\").replace("'", "\\'")
        dialog.view.page().runJavaScript(
            f"var el=document.getElementById('launcher-exe-input'); if(el) el.value='{exe_js}';"
        )


# -----------------------------
# Save handler (ONE ONLY)
# -----------------------------
def handle_save_settings(data, dialog):
    """
    Expects data as JSON string from frontend:
      {"folder":"...","launcher":"steam|rockstar","steamExe":"...","launcherExe":"...","isLinux":false}
    """
    try:
        payload = json.loads(data) if isinstance(data, str) else (data or {})
        if not isinstance(payload, dict):
            show_error(dialog, "Invalid settings payload")
            return

        folder = (payload.get("folder") or "").strip()
        launcher = (payload.get("launcher") or "steam").strip()
        steam_exe = (payload.get("steamExe") or "").strip()
        launcher_exe = (payload.get("launcherExe") or "").strip()
        is_linux = bool(payload.get("isLinux", False))
        list_url = (payload.get("listUrl") or "").strip()
        uri_mode = bool(payload.get("uriMode", False))
        only_filters = {
            "important": bool(payload.get("onlyImportant", True)),
            "trusted": bool(payload.get("onlyTrusted", True)),
            "others": bool(payload.get("onlyOthers", True)),
        }

        if is_system_linux():
            launcher = "steam"
            is_linux = True

        if launcher == "rockstar" and not folder:
            folder = r"C:\Program Files\Rockstar Games\Bully Scholarship Edition"

        if launcher != "steam":
            if not folder:
                show_error(dialog, "Please select a game folder")
                return

            if not os.path.isdir(folder):
                show_error(dialog, "Invalid folder path")
                return

        # Merge-save (prevents wiping launcher)
        save_settings_update({
            "game_folder": folder,
            "launcher": launcher,
            "steam_exe": steam_exe,
            "launcher_exe": launcher_exe,
            "is_linux": is_linux,
            "steam_uri_mode": uri_mode,
            "list_url": list_url,
            "only_filters": only_filters
        })

        print("[SETTINGS] Saved:",
              f"folder={folder}, launcher={launcher}, steam_exe={steam_exe or '(auto)'}, "
              f"launcher_exe={launcher_exe or '(auto)'}, is_linux={is_linux}, "
              f"list_url={list_url or '(default)'}, only_filters={only_filters}")

        dialog.close()

    except Exception as e:
        print("[SETTINGS] Save error:", e)
        show_error(dialog, f"Failed to save: {e}")


# -----------------------------
# Links
# -----------------------------
def open_github():
    webbrowser.open("https://github.com/Vooogle/dss_browser")


def open_discord():
    webbrowser.open("https://discord.gg/RHrsCx2acS")


def handle_open_admin():
    from backend.ui.admin import create_admin_dialog
    admin = create_admin_dialog()
    admin.show()


def handle_open_update():
    from backend.ui.update import create_update_dialog
    dialog = create_update_dialog()
    dialog.show()


# -----------------------------
# UI error display
# -----------------------------
def show_error(dialog, message: str):
    msg = (message or "").replace("\\", "\\\\").replace("'", "\\'")
    js = f"""
    var errorDiv = document.getElementById('error-message');
    if (!errorDiv) {{
        errorDiv = document.createElement('div');
        errorDiv.id = 'error-message';
        errorDiv.style.color = '#ff4444';
        errorDiv.style.padding = '10px';
        errorDiv.style.textAlign = 'center';
        errorDiv.style.marginTop = '10px';
        var content = document.getElementById('content') || document.body;
        content.appendChild(errorDiv);
    }}
    errorDiv.textContent = '{msg}';
    setTimeout(() => {{ errorDiv.textContent = ''; }}, 3000);
    """
    dialog.view.page().runJavaScript(js)
