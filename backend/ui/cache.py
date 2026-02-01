import os
import json
import time
import base64
import threading

CACHE_TTL_SECONDS = 600
CACHE_PATH = os.path.join(os.path.expanduser("~"), ".dssb_server_browser", "cache.json")
_cache_lock = threading.Lock()


def load_cache():
    if not os.path.exists(CACHE_PATH):
        return {"servers": {}}
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "servers" not in data or not isinstance(data["servers"], dict):
            return {"servers": {}}
        return data
    except Exception:
        return {"servers": {}}


def save_cache(data):
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f)


def get_cache_entry(ip, port):
    key = f"{ip}:{port}"
    with _cache_lock:
        data = load_cache()
        return data.get("servers", {}).get(key)


def update_cache_entry(ip, port, url=None, css_vars=None, icon_bytes=None):
    key = f"{ip}:{port}"
    update_cache_entry_key(key, url=url, css_vars=css_vars, icon_bytes=icon_bytes)


def update_cache_entry_key(key, url=None, css_vars=None, icon_bytes=None):
    with _cache_lock:
        data = load_cache()
        entry = data.setdefault("servers", {}).get(key, {})
        if url is not None:
            entry["url"] = url
        if css_vars is not None:
            entry["css_vars"] = css_vars
        if icon_bytes is not None:
            entry["icon_b64"] = encode_cached_icon(icon_bytes)
        entry["ts"] = int(time.time())
        data["servers"][key] = entry
        save_cache(data)


def is_cache_fresh(entry):
    ts = entry.get("ts", 0)
    if not isinstance(ts, int):
        return False
    return (int(time.time()) - ts) <= CACHE_TTL_SECONDS


def encode_cached_icon(icon_bytes):
    if not icon_bytes:
        return ""
    return base64.b64encode(icon_bytes).decode("ascii")


def decode_cached_icon(icon_b64):
    if not icon_b64:
        return b""
    try:
        return base64.b64decode(icon_b64)
    except Exception:
        return b""
