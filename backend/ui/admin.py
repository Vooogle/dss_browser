import os
import json
import keyring
from PyQt6.QtCore import Qt
from backend.ui_manager import HTMLWindow

SETTINGS_FILE = os.path.join(os.path.expanduser("~"), ".dssb_server_browser", "settings.json")
ADMIN_TOKEN_KEY = "admin_token"
KEYRING_SERVICE = "DSSBServerBrowser"


def _get_list_url():
    if not os.path.exists(SETTINGS_FILE):
        return ""
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data.get("list_url") or ""
    except Exception:
        return ""
    return ""


def _get_admin_token() -> str:
    try:
        return keyring.get_password(KEYRING_SERVICE, ADMIN_TOKEN_KEY) or ""
    except Exception:
        return ""


def _set_admin_token(token: str) -> None:
    try:
        if token:
            keyring.set_password(KEYRING_SERVICE, ADMIN_TOKEN_KEY, token)
        else:
            keyring.delete_password(KEYRING_SERVICE, ADMIN_TOKEN_KEY)
    except Exception:
        pass


def create_admin_dialog():
    current_dir = os.path.dirname(os.path.abspath(__file__))  # backend/ui
    backend_dir = os.path.dirname(current_dir)                # backend
    project_root = os.path.dirname(backend_dir)               # project root
    html_path = os.path.join(project_root, "frontend", "admin.html")

    if not os.path.exists(html_path):
        raise FileNotFoundError(f"HTML file not found: {html_path}")

    dialog = HTMLWindow(
        html_path=html_path,
        size=(720, 520),
        enable_drag=False,
        callbacks={
            "close": lambda _: dialog.close(),
            "saveAdminToken": lambda token: _set_admin_token(token),
        }
    )
    dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
    dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
    dialog.activateWindow()

    list_url = _get_list_url()

    def load_url():
        safe = (list_url or "").replace("\\", "\\\\").replace("'", "\\'")
        dialog.view.page().runJavaScript(
            f"if (typeof setListUrl === 'function') setListUrl('{safe}');"
        )
        token = _get_admin_token().replace("\\", "\\\\").replace("'", "\\'")
        dialog.view.page().runJavaScript(
            f"if (typeof setAdminToken === 'function') setAdminToken('{token}');"
        )

    dialog.view.loadFinished.connect(load_url)
    return dialog
