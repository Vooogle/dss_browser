#!/usr/bin/env python3
"""
launch.py - Main entry point for DSSB Server Browser
"""

import sys
import traceback
import os
import json

def main():
    """Launch the DSSB Server Browser application."""
    # CRITICAL: Import QtWebEngineWidgets BEFORE creating QApplication
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWidgets import QApplication
    
    # Create QApplication
    app = QApplication(sys.argv)
    app.setApplicationName("DSSB Server Browser")
    app.setOrganizationName("DSSB")

    # Set taskbar/window icon
    try:
        from PyQt6.QtGui import QIcon
        import os
        icon_path = os.path.join(os.path.dirname(__file__), "frontend", "assets", "images", "icon.ico")
        if not os.path.exists(icon_path):
            icon_path = os.path.join(os.path.dirname(__file__), "frontend", "assets", "images", "icon.png")
        if os.path.exists(icon_path):
            app.setWindowIcon(QIcon(icon_path))
    except Exception:
        pass
    
    print("QApplication created")
    
    try:
        # Initialize backend manager
        from backend.dssb_manager import DSSBManager
        cred_storage, cred_password = configure_credential_storage(app)
        print("Initializing backend...")
        dssb = DSSBManager(cred_storage=cred_storage, cred_password=cred_password)
        
        # DON'T start auto-refresh yet - it's causing the crash
        # bsb.start_auto_refresh(interval_minutes=30)
        
        # Create UI
        from backend.ui.main import create_main_window
        print("Creating window...")
        window = create_main_window(dssb)
        
        if window is None:
            print("ERROR: Window creation failed")
            return 1
        
        # Keep references to prevent garbage collection
        app.dssb_manager = dssb
        app.main_window = window
        
        # Show window
        window.show()
        print("Window shown")
        
        # Load initial server list
        print("Loading servers...")
        servers = dssb.get_server_list()
        print(f"Found {len(servers)} servers")
        
        from backend.ui.main import update_server_list
        update_server_list(window, servers)

        # One-time refresh to populate from remote list on startup.
        def _on_server_list_updated():
            try:
                update_server_list(window, dssb.get_server_list())
            except Exception as exc:
                print(f"Failed to refresh server list: {exc}")

        dssb.set_ui_callback("server_list_updated", _on_server_list_updated)
        dssb.refresh_dynamic_servers()
        
    except Exception as e:
        print(f"ERROR during initialization: {e}")
        traceback.print_exc()
        return 1
    
    # Start the Qt event loop
    print("Starting event loop...")
    result = app.exec()
    print(f"Event loop exited with code: {result}")
    return result


def _load_settings():
    settings_path = os.path.join(os.path.expanduser("~"), ".dssb_server_browser", "settings.json")
    if not os.path.exists(settings_path):
        return {}, settings_path
    try:
        with open(settings_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return (data if isinstance(data, dict) else {}), settings_path
    except Exception:
        return {}, settings_path


def _save_settings(settings: dict, settings_path: str) -> None:
    os.makedirs(os.path.dirname(settings_path), exist_ok=True)
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)


def _is_steamos() -> bool:
    try:
        with open("/etc/os-release", "r", encoding="utf-8") as f:
            data = f.read().lower()
        return "steamos" in data or "holo" in data
    except Exception:
        return False


def _is_gaming_mode() -> bool:
    env = os.environ
    if env.get("STEAM_GAMEPADUI") == "1":
        return True
    desk = (env.get("XDG_CURRENT_DESKTOP") or "").lower()
    if "gamescope" in desk:
        return True
    return False


def configure_credential_storage(app):
    """
    Decide credential storage on SteamOS gaming mode.
    Returns (storage_mode, password).
    """
    settings, settings_path = _load_settings()
    choice = settings.get("cred_storage", "")
    force_choice = choice in ("plaintext", "encrypted")

    if sys.platform != "linux" or not _is_steamos():
        if not force_choice:
            return "keyring", None

    from PyQt6.QtWidgets import QMessageBox, QInputDialog, QLineEdit
    from backend.storage.logins import FileCredentialStore

    while True:
        if choice not in ("plaintext", "encrypted"):
            if force_choice:
                return "keyring", None
            msg = QMessageBox()
            msg.setWindowTitle("Credential Storage")
            msg.setText(
                "SteamOS Gaming Mode doesn't provide a system keyring.\n\n"
                "Choose how to store credentials:"
            )
            plaintext = msg.addButton("Plaintext file (less secure)", QMessageBox.ButtonRole.AcceptRole)
            encrypted = msg.addButton("Encrypted file (ask each start)", QMessageBox.ButtonRole.AcceptRole)
            msg.addButton("Don't save credentials", QMessageBox.ButtonRole.RejectRole)
            msg.exec()
            clicked = msg.clickedButton()
            if clicked == plaintext:
                choice = "plaintext"
            elif clicked == encrypted:
                choice = "encrypted"
            else:
                choice = "keyring"
            settings["cred_storage"] = choice
            _save_settings(settings, settings_path)

        if choice == "plaintext":
            return "plaintext", None
        if choice == "encrypted":
            password, ok = QInputDialog.getText(
                None,
                "Credential Password",
                "Enter a password to unlock credentials:",
                QLineEdit.EchoMode.Password
            )
            if not ok or not password:
                choice = ""
                continue
            # Verify password if file exists.
            app_dir = os.path.join(os.path.expanduser("~"), ".dssb_server_browser")
            path = os.path.join(app_dir, "credentials.enc")
            try:
                FileCredentialStore(path, encrypted=True, password=password)
            except ValueError:
                QMessageBox.warning(None, "Invalid Password", "Incorrect password for encrypted credentials.")
                choice = "encrypted"
                continue
            except Exception as exc:
                QMessageBox.warning(None, "Encrypted Storage Error", str(exc))
                choice = ""
                continue
            return "encrypted", password
        return "keyring", None


if __name__ == "__main__":
    sys.exit(main())
