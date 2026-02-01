import json
import webbrowser
import requests

from PyQt6.QtCore import Qt

from backend.ui_manager import HTMLWindow
from backend.version import __version__

LATEST_URL = "https://raw.githubusercontent.com/Vooogle/dss_browser/main/latest.json"
RELEASES_URL = "https://github.com/Vooogle/dss_browser/releases/latest"


def create_update_dialog():
    import os
    current_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.dirname(current_dir)
    project_root = os.path.dirname(backend_dir)
    html_path = os.path.join(project_root, "frontend", "update.html")

    callbacks = {}

    dialog = HTMLWindow(
        html_path=html_path,
        size=(520, 300),
        enable_drag=True,
        callbacks=callbacks,
    )

    callbacks.update({
        "close": lambda _: dialog.close(),
        "check": lambda _: handle_check(dialog),
        "openReleases": lambda _: open_releases(),
    })

    dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
    dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
    dialog.activateWindow()
    dialog.view.loadFinished.connect(lambda: load_update_state(dialog))
    return dialog


def load_update_state(dialog):
    dialog.view.page().runJavaScript(
        f"if (typeof setCurrentVersion === 'function') setCurrentVersion('{__version__}');"
    )
    dialog.view.page().runJavaScript(
        "if (typeof setStatus === 'function') setStatus('Ready to check.');"
    )


def parse_version(value: str):
    parts = (value or "").strip().lstrip("v").split(".")
    nums = []
    for part in parts:
        try:
            nums.append(int(part))
        except ValueError:
            nums.append(0)
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums[:3])


def handle_check(dialog):
    dialog.view.page().runJavaScript(
        "if (typeof setStatus === 'function') setStatus('Checking for updates...');"
    )
    try:
        response = requests.get(LATEST_URL, timeout=5)
        if response.status_code >= 400:
            raise RuntimeError(f"HTTP {response.status_code}")
        payload = response.json()
    except Exception as exc:
        dialog.view.page().runJavaScript(
            f"if (typeof setStatus === 'function') setStatus('Update check failed: {str(exc)}');"
        )
        return

    latest = str(payload.get("version", "")).strip()
    if not latest:
        dialog.view.page().runJavaScript(
            "if (typeof setStatus === 'function') setStatus('Update check failed: missing version.');"
        )
        return

    current_tuple = parse_version(__version__)
    latest_tuple = parse_version(latest)

    if latest_tuple > current_tuple:
        dialog.view.page().runJavaScript(
            f"if (typeof setLatestVersion === 'function') setLatestVersion('{latest}');"
        )
        dialog.view.page().runJavaScript(
            "if (typeof setStatus === 'function') setStatus('Update available!');"
        )
        dialog.view.page().runJavaScript(
            "if (typeof setUpdateAvailable === 'function') setUpdateAvailable(true);"
        )
    else:
        dialog.view.page().runJavaScript(
            f"if (typeof setLatestVersion === 'function') setLatestVersion('{latest}');"
        )
        dialog.view.page().runJavaScript(
            "if (typeof setStatus === 'function') setStatus('You are up to date.');"
        )
        dialog.view.page().runJavaScript(
            "if (typeof setUpdateAvailable === 'function') setUpdateAvailable(false);"
        )


def open_releases():
    webbrowser.open(RELEASES_URL)
