import os
import re
import shutil
import threading
import requests
from pathlib import Path
from PyQt6.QtCore import QTimer
from backend.ui_manager import HTMLWindow
from backend.ui.cache import (
    get_cache_entry,
    update_cache_entry,
    update_cache_entry_key,
    is_cache_fresh,
    decode_cached_icon,
)
from backend.ui.ui_helpers import (
    run_js,
    update_server_list,
    display_server_info,
    set_server_icon,
    reload_active_style,
    set_credentials,
    clear_credentials,
)

def create_main_window(dssb_manager):
    """
    Create the main UI window.
    
    Args:
        dssb_manager: Instance of DSSBManager to handle backend operations
    
    Returns:
        HTMLWindow instance
    """
    # Resolve paths
    current_dir = os.path.dirname(os.path.abspath(__file__))  # backend/ui
    backend_dir = os.path.dirname(current_dir)                 # backend
    project_root = os.path.dirname(backend_dir)                # project root
    html_path = os.path.join(project_root, "frontend", "main.html")

    active_style_path = reset_active_style(project_root)
    
    print(f"Loading HTML: {html_path}")
    
    # Verify HTML exists
    if not os.path.exists(html_path):
        raise FileNotFoundError(f"HTML file not found: {html_path}")
    
    # Track selected server
    selected_server = {"ip": None, "port": None}
    
    # Create window with callbacks
    window = HTMLWindow(
        html_path=html_path,
        size=(1280, 820),
        callbacks={
            # Window controls
            "close": lambda _: window.close(),
            "minimize": lambda _: window.showMinimized(),
            "maximize": lambda _: (
                window.showNormal() if window.isMaximized() 
                else window.showMaximized()
            ),
            
            # Drag (handled automatically but needs callback to avoid warning)
            "startDrag": lambda _: None,
            
            # Server management
            "search": lambda query: handle_search(dssb_manager, window, query),
            "add": lambda _: handle_add_server(dssb_manager, window),
            "refresh": lambda _: handle_refresh(dssb_manager, window),
            "selectServer": lambda data: handle_select_server(dssb_manager, window, selected_server, data),
            "toggleFavorite": lambda data: handle_toggle_favorite(dssb_manager, window, data),
            "toggleMenu": lambda _: None,  # Handled in HTML
            
            # Credentials
            "username": lambda username: handle_username_change(dssb_manager, selected_server, username),
            "password": lambda password: handle_password_change(dssb_manager, selected_server, password),
            
            # Actions
            "play": lambda _: handle_play(dssb_manager, selected_server),
            "settings": lambda _: handle_settings(window),
        }
    )
    window._project_root = project_root
    window._active_style_path = active_style_path
    if active_style_path and os.path.abspath(active_style_path) != os.path.abspath(
        os.path.join(project_root, "frontend", "assets", "styles", "active_base_style.css")
    ):
        window.view.loadFinished.connect(
            lambda _: _set_active_style_link(window, active_style_path)
        )
    
    return window


# ========== Event Handlers ==========

def handle_search(dssb_manager, window, query):
    """Handle search input."""
    if not query.strip():
        servers = dssb_manager.get_server_list()
    else:
        servers = dssb_manager.search_servers(query)
    
    update_server_list(window, servers)


def handle_add_server(dssb_manager, window):
    """Open add server dialog."""
    from backend.ui.add_server import create_add_server_dialog
    
    def on_added():
        print("Server added, refreshing list...")
        # The main window will be updated when the server is added
    
    dialog = create_add_server_dialog(dssb_manager, on_added)
    set_controller_enabled(window, False)
    window.setEnabled(False)
    dialog.closed.connect(lambda: _restore_main_input(window))
    dialog.show()


def handle_refresh(dssb_manager, window):
    """Refresh all servers."""
    print("Refreshing server list...")
    
    # Just reload the list from database, don't query anything
    servers = dssb_manager.get_server_list()
    print(f"Loaded {len(servers)} servers from database")
    update_server_list(window, servers)
    dssb_manager.refresh_dynamic_servers()


def handle_select_server(dssb_manager, window, selected_server, data):
    """Handle server selection."""
    import json
    
    try:
        server_data = json.loads(data)
        ip = server_data["ip"]
        port = int(server_data["port"])
        
        selected_server["ip"] = ip
        selected_server["port"] = port
        
        print(f"Selected: {ip}:{port}")
        
        # Load credentials
        creds = dssb_manager.get_credentials(ip, port)
        if creds:
            set_credentials(window, creds["username"], creds["password"])
        else:
            clear_credentials(window)

        # Show website if available
        server_record = dssb_manager.get_server(ip, port)
        website = server_record.get("website") if server_record else None
        normalized = normalize_website(website, ip)
        print(f"[WEBSITE] Displaying website: {normalized or '(none)'}")
        set_server_icon(window, server_record.get("icon") if server_record else None)
        cache_entry = get_cache_entry(ip, port)
        cached_url = None
        used_cache = False
        if cache_entry and is_cache_fresh(cache_entry):
            print("[CACHE] Using cached view")
            cached_url = cache_entry.get("url")
            cached_vars = cache_entry.get("css_vars") or {}
            cached_icon = decode_cached_icon(cache_entry.get("icon_b64"))
            if cached_vars:
                if update_active_style_from_vars(window._active_style_path, cached_vars):
                    reload_active_style(window)
            else:
                old_path = window._active_style_path
                window._active_style_path = reset_active_style(
                    window._project_root, window._active_style_path
                )
                if window._active_style_path != old_path:
                    _set_active_style_link(window, window._active_style_path)
                reload_active_style(window)
            if cached_icon:
                set_server_icon(window, cached_icon)
            if cached_url:
                set_website(window, cached_url)
                used_cache = True
        window._website_request_id = getattr(window, "_website_request_id", 0) + 1
        request_id = window._website_request_id
        if not used_cache:
            resolve_website_url(window, website, ip, port, request_id, cached_url)

        def query_and_update():
            info = dssb_manager.query_server(ip, port)
            if getattr(window, "_website_request_id", 0) != request_id:
                return
            if info:
                if not website:
                    display_server_info(window, info)
                if info.get("icon"):
                    set_server_icon(window, info.get("icon"))
                update_cache_entry(ip, port, icon_bytes=info.get("icon"))

        threading.Thread(target=query_and_update, daemon=True).start()
            
    except Exception as e:
        print(f"Error selecting server: {e}")


def handle_toggle_favorite(dssb_manager, window, data):
    """Toggle favorite status; remove manual servers if unfavorited."""
    import json

    try:
        payload = json.loads(data)
        ip = payload.get("ip")
        port = int(payload.get("port"))
        is_favorite = bool(payload.get("is_favorite"))

        server = dssb_manager.get_server(ip, port)
        if not server:
            return

        if not is_favorite and server.get("source") == "manual":
            dssb_manager.remove_server(ip, port)
        else:
            dssb_manager.servers.set_favorite(ip, port, is_favorite)

        update_server_list(window, dssb_manager.get_server_list())
    except Exception as e:
        print(f"Error toggling favorite: {e}")


def handle_username_change(dssb_manager, selected_server, username):
    """Handle username input change."""
    if not selected_server["ip"]:
        return
    
    creds = dssb_manager.get_credentials(selected_server["ip"], selected_server["port"]) or {}
    password = creds.get("password", "")
    
    dssb_manager.save_credentials(selected_server["ip"], selected_server["port"], username, password)


def handle_password_change(dssb_manager, selected_server, password):
    """Handle password input change."""
    if not selected_server["ip"]:
        return
    
    creds = dssb_manager.get_credentials(selected_server["ip"], selected_server["port"]) or {}
    username = creds.get("username", "")
    
    dssb_manager.save_credentials(selected_server["ip"], selected_server["port"], username, password)


def handle_play(dssb_manager, selected_server):
    """Launch the game."""
    from backend.game.game_manager import launch_game, is_game_configured
    
    if not selected_server["ip"]:
        print("ERROR: No server selected")
        return
    
    # Check if game is configured
    if not is_game_configured():
        print("ERROR: Game not configured. Please set the game folder in Settings.")
        return
    
    # Get credentials
    creds = dssb_manager.get_credentials(selected_server["ip"], selected_server["port"])
    
    if not creds:
        print("ERROR: No credentials set for this server")
        return
    
    # Launch the game
    print(f"Launching game to connect to {selected_server['ip']}:{selected_server['port']}")
    success = launch_game(
        selected_server["ip"],
        selected_server["port"],
        creds["username"],
        creds["password"]
    )
    
    if success:
        print("Game launched successfully!")
    else:
        print("Failed to launch game. Check console for details.")


def handle_settings(window):
    """Open settings dialog."""
    from backend.ui.settings import create_settings_dialog
    
    dialog = create_settings_dialog()
    set_controller_enabled(window, False)
    window.setEnabled(False)
    dialog.closed.connect(lambda: _restore_main_input(window))
    dialog.show()


# ========== UI Update Functions ==========

def normalize_website(url, ip):
    trimmed = (url or "").strip()
    if trimmed:
        if trimmed.startswith("http://") or trimmed.startswith("https://"):
            return trimmed
        return f"https://{trimmed}"
    if ip:
        return f"https://{ip}"
    return ""


def set_website(window, url):
    """Show or hide the website view."""
    def apply():
        if url:
            window.show_website(url)
        else:
            window.hide_website()
    QTimer.singleShot(0, apply)


def set_controller_enabled(window, enabled):
    value = "true" if enabled else "false"
    js = f"if (typeof setControllerEnabled === 'function') setControllerEnabled({value});"
    run_js(window, js)


def _restore_main_input(window):
    window.setEnabled(True)
    window.activateWindow()
    set_controller_enabled(window, True)


def _get_user_active_style_path():
    user_dir = os.path.join(os.path.expanduser("~"), ".dssb_server_browser", "styles")
    os.makedirs(user_dir, exist_ok=True)
    return os.path.join(user_dir, "active_base_style.css")


def _set_active_style_link(window, active_style_path):
    try:
        href = Path(active_style_path).resolve().as_uri()
    except Exception:
        return
    js = f"""
    const links = document.querySelectorAll('link[href*="active_base_style.css"]');
    links.forEach(link => {{ link.href = '{href}'; }});
    """
    run_js(window, js)


def reset_active_style(project_root, active_style_path=None):
    styles_dir = os.path.join(project_root, "frontend", "assets", "styles")
    base_style = os.path.join(styles_dir, "base_style.css")
    default_active_style = os.path.join(styles_dir, "active_base_style.css")
    target = active_style_path or default_active_style
    if not os.path.exists(base_style):
        return target
    try:
        shutil.copyfile(base_style, target)
        return target
    except OSError:
        # Fall back to a user-writable path (AppImage and other read-only installs).
        user_active = _get_user_active_style_path()
        shutil.copyfile(base_style, user_active)
        return user_active


def refresh_active_style(window, url):
    thread = threading.Thread(
        target=_refresh_active_style_worker,
        args=(window, url, None, None),
        daemon=True
    )
    thread.start()


def refresh_active_style_cached(window, url, ip, port, request_id):
    thread = threading.Thread(
        target=_refresh_active_style_worker,
        args=(window, url, f"{ip}:{port}", request_id),
        daemon=True
    )
    thread.start()


def resolve_website_url(window, website, ip, port, request_id, preferred_url=None):
    thread = threading.Thread(
        target=_resolve_website_worker,
        args=(window, website, ip, port, request_id, preferred_url),
        daemon=True
    )
    thread.start()


def _resolve_website_worker(window, website, ip, port, request_id, preferred_url):
    candidates = get_candidate_urls(website, ip, preferred_url)
    if getattr(window, "_website_request_id", 0) != request_id:
        return
    if not candidates:
        print("[WEBSITE] No reachable URL found")
        set_website(window, "")
        return

    # Optimistic load for faster UI response.
    set_website(window, candidates[0])

    results = {}
    lock = threading.Lock()

    def probe(candidate):
        if getattr(window, "_website_request_id", 0) != request_id:
            return
        print(f"[WEBSITE] Checking {candidate}")
        ok = check_url(candidate)
        with lock:
            results[candidate] = ok
        print(f"[WEBSITE] {'Using' if ok else 'Failed'} {candidate}")

    threads = [threading.Thread(target=probe, args=(c,), daemon=True) for c in candidates]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    if getattr(window, "_website_request_id", 0) != request_id:
        return

    preferred = next((c for c in candidates if c.startswith("https://")), None)
    chosen = None
    if preferred and results.get(preferred):
        chosen = preferred
    else:
        for candidate in candidates:
            if results.get(candidate):
                chosen = candidate
                break

    if chosen:
        if chosen != candidates[0]:
            set_website(window, chosen)
        update_cache_entry(ip, port, url=chosen)
        refresh_active_style_cached(window, chosen, ip, port, request_id)
        return

    print("[WEBSITE] No reachable URL found")
    set_website(window, "")


def get_candidate_urls(website, ip, preferred_url=None):
    trimmed = (website or "").strip()
    candidates = []
    if trimmed:
        if trimmed.startswith("http://"):
            alt = "https://" + trimmed[len("http://"):]
            candidates = [trimmed, alt]
        elif trimmed.startswith("https://"):
            alt = "http://" + trimmed[len("https://"):]
            candidates = [trimmed, alt]
        else:
            candidates = [f"http://{trimmed}", f"https://{trimmed}"]
    elif ip:
        candidates = [f"http://{ip}", f"https://{ip}"]
    if preferred_url:
        candidates = [preferred_url] + candidates
    seen = set()
    ordered = []
    for candidate in candidates:
        if candidate and candidate not in seen:
            ordered.append(candidate)
            seen.add(candidate)
    return ordered


def check_url(url):
    try:
        response = requests.get(url, timeout=(1, 1), stream=True)
        if response.status_code >= 400:
            response.close()
            return False
        chunk = response.raw.read(256)
        response.close()
        return bool(chunk)
    except Exception:
        return False


def _refresh_active_style_worker(window, url, cache_key, request_id):
    if request_id is not None and getattr(window, "_website_request_id", 0) != request_id:
        return
    updated, found_vars, css_vars = update_active_style_from_website(
        url, active_style_path=getattr(window, "_active_style_path", None)
    )
    if request_id is not None and getattr(window, "_website_request_id", 0) != request_id:
        return
    if updated:
        reload_active_style(window)
        if cache_key:
            update_cache_entry_key(cache_key, css_vars=css_vars or {})
        return
    if found_vars is False:
        if request_id is not None and getattr(window, "_website_request_id", 0) != request_id:
            return
        project_root = getattr(window, "_project_root", None)
        active_style_path = getattr(window, "_active_style_path", None)
        if project_root:
            new_path = reset_active_style(project_root, active_style_path)
            if new_path and new_path != active_style_path:
                window._active_style_path = new_path
                _set_active_style_link(window, new_path)
        reload_active_style(window)
        if cache_key:
            update_cache_entry_key(cache_key, css_vars={})


def update_active_style_from_website(url, active_style_path=None, project_root=None):
    if not url:
        return False, None, None

    def extract_css_vars(text):
        return dict(re.findall(r"(--bsb-[a-z0-9-]+)\s*:\s*([^;]+);", text, re.I))

    try:
        response = requests.get(url, timeout=3)
        response.raise_for_status()
    except Exception:
        return False, None, None

    html = response.text
    css_vars = extract_css_vars(html)

    if not css_vars:
        stylesheet_tags = re.findall(r"<link[^>]+rel=[\"']?stylesheet[\"']?[^>]*>", html, re.I)
        for tag in stylesheet_tags:
            href_match = re.search(r"href=[\"']([^\"']+)[\"']", tag, re.I)
            if not href_match:
                continue
            stylesheet_url = requests.compat.urljoin(url, href_match.group(1))
            try:
                css_response = requests.get(stylesheet_url, timeout=3)
                css_response.raise_for_status()
            except Exception:
                continue
            css_vars.update(extract_css_vars(css_response.text))

    if not css_vars:
        print(f"[THEME] No CSS variables found at {url}")
        return False, False, None

    if not active_style_path:
        if not project_root:
            current_dir = os.path.dirname(os.path.abspath(__file__))  # backend/ui
            backend_dir = os.path.dirname(current_dir)                 # backend
            project_root = os.path.dirname(backend_dir)                # project root
        styles_dir = os.path.join(project_root, "frontend", "assets", "styles")
        active_style_path = os.path.join(styles_dir, "active_base_style.css")
    if not os.path.exists(active_style_path):
        return False, None, None

    with open(active_style_path, "r", encoding="utf-8") as f:
        content = f.read()

    def replace_var(match):
        name = match.group(1)
        value = match.group(2)
        return f"{name}: {css_vars.get(name, value)};"

    content = re.sub(r"(--bsb-[a-z0-9-]+)\s*:\s*([^;]+);", replace_var, content, flags=re.I)
    with open(active_style_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[THEME] Updated {len(css_vars)} variables from {url}")
    return True, True, css_vars


def update_active_style_from_vars(active_style_path, css_vars):
    if not css_vars:
        return False
    if not active_style_path:
        return False
    if not os.path.exists(active_style_path):
        return False
    with open(active_style_path, "r", encoding="utf-8") as f:
        content = f.read()

    def replace_var(match):
        name = match.group(1)
        value = match.group(2)
        return f"{name}: {css_vars.get(name, value)};"

    content = re.sub(r"(--bsb-[a-z0-9-]+)\s*:\s*([^;]+);", replace_var, content, flags=re.I)
    with open(active_style_path, "w", encoding="utf-8") as f:
        f.write(content)
    return True






