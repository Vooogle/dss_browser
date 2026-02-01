import base64
import json
from PyQt6.QtCore import QTimer
from backend.dss_query import detect_icon_ext


def run_js(window, js):
    if hasattr(window, "run_js_signal"):
        window.run_js_signal.emit(js)
        return
    QTimer.singleShot(0, lambda: window.view.page().runJavaScript(js))


def update_server_list(window, servers):
    server_list = []
    for s in servers:
        server_list.append({
            "ip": s["ip"],
            "port": s["port"],
            "name": s.get("name", f"{s['ip']}:{s['port']}"),
            "players": s.get("players", 0),
            "max_players": s.get("max_players", 0),
            "source": s["source"],
            "trusted": bool(s.get("trusted")),
            "important": bool(s.get("important")),
            "website": s.get("website"),
        })

    js = f"if (typeof updateServerList === 'function') {{ updateServerList({json.dumps(server_list)}); }}"
    run_js(window, js)


def display_server_info(window, info):
    name = info.get("name", "Unknown Server")
    server_info = info.get("info", "")
    news = info.get("news", "")
    players = info.get("players", 0)
    max_players = info.get("max_players", 0)

    js = f"""
    var target = document.getElementById('content-body');
    if (target) {{
      target.innerHTML = `
        <h1>{name}</h1>
        <p><strong>Info:</strong> {server_info}</p>
        <p><strong>News:</strong> {news}</p>
        <p><strong>Players:</strong> {players}/{max_players}</p>
      `;
    }}
    """
    run_js(window, js)


def icon_to_data_url(icon_bytes):
    if not icon_bytes:
        return ""
    ext = detect_icon_ext(icon_bytes)
    if ext == "png":
        mime = "image/png"
    elif ext == "jpg":
        mime = "image/jpeg"
    else:
        return ""
    encoded = base64.b64encode(icon_bytes).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def set_server_icon(window, icon_bytes):
    data_url = icon_to_data_url(icon_bytes)
    safe_url = (data_url or "").replace("\\", "\\\\").replace("'", "\\'")
    js = f"if (typeof setServerIcon === 'function') setServerIcon('{safe_url}');"
    run_js(window, js)


def reload_active_style(window):
    js = "if (typeof reloadActiveStyle === 'function') reloadActiveStyle();"
    run_js(window, js)


def set_credentials(window, username, password):
    js = f"""
    var u = document.getElementById('username');
    var p = document.getElementById('password');
    if (u) u.value = '{username}';
    if (p) p.value = '{password}';
    """
    run_js(window, js)


def clear_credentials(window):
    js = """
    var u = document.getElementById('username');
    var p = document.getElementById('password');
    if (u) u.value = '';
    if (p) p.value = '';
    """
    run_js(window, js)
