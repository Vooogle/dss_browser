import socket
import ssl
import struct
import argparse
import sys
import os
import subprocess
import platform

LISTING_USERNAME = "__dsslist"

NET_MSG_LISTING = 0
NET_SVM_WHATS_UP = 1
NET_SVM_LIST_SERVER = 2
NET_SI_USE_SSL = 1


def recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Connection closed")
        buf += chunk
    return buf


def recv_packet(sock):
    header = recv_exact(sock, 4)
    size = struct.unpack("<I", header)[0]
    return header + recv_exact(sock, size - 4)


def parse_whats_up(pkt):
    msg = pkt[4:]
    if msg[0] != NET_SVM_WHATS_UP:
        raise ValueError("Expected WHATS_UP")

    flags = msg[1]
    version = struct.unpack_from("<I", msg, 2)[0]
    netver = msg[6:].decode(errors="ignore")

    return flags, version, netver


def build_listing_request(version, netver):
    payload = bytearray()
    payload.append(NET_MSG_LISTING)
    payload += struct.pack("<I", version)
    payload += netver.encode() + b"\x00"
    payload.append(1)
    payload += LISTING_USERNAME.encode()

    return struct.pack("<I", 4 + len(payload)) + payload


def read_cstring(buf, off):
    end = buf.index(0, off)
    return buf[off:end].decode(errors="ignore"), end + 1


def parse_list_server(pkt):
    buf = pkt[5:]
    off = 0

    name, off = read_cstring(buf, off)
    info, off = read_cstring(buf, off)
    news, off = read_cstring(buf, off)

    icon_size = struct.unpack_from("<I", buf, off)[0]
    off += 4
    icon = buf[off:off + icon_size]
    off += icon_size

    players, max_players = struct.unpack_from("<HH", buf, off)

    return {
        "name": name,
        "info": info,
        "news": news,
        "players": players,
        "max_players": max_players,
        "icon": icon,
    }


def detect_icon_ext(data):
    if data.startswith(b"\x89PNG"):
        return "png"
    if data.startswith(b"\xff\xd8"):
        return "jpg"
    return "bin"


def open_file(path):
    system = platform.system()
    if system == "Windows":
        os.startfile(path)
    elif system == "Darwin":
        subprocess.run(["open", path], check=False)
    else:
        subprocess.run(["xdg-open", path], check=False)


def query_dss(host, port, timeout=3):
    sock = socket.create_connection((host, port), timeout=timeout)

    pkt = recv_packet(sock)
    flags, version, netver = parse_whats_up(pkt)

    if flags & NET_SI_USE_SSL:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        sock = ctx.wrap_socket(sock, server_hostname=host)

    sock.sendall(build_listing_request(version, netver))
    pkt = recv_packet(sock)

    return parse_list_server(pkt)


def main():
    ap = argparse.ArgumentParser(description="DSS server query tool")
    ap.add_argument("target", help="ip:port")

    ap.add_argument("-name", action="store_true")
    ap.add_argument("-info", action="store_true")
    ap.add_argument("-news", action="store_true")
    ap.add_argument("-players", action="store_true")
    ap.add_argument("-max_players", action="store_true")

    ap.add_argument("-icon", nargs="?", const="icons", metavar="DIR",
                    help="Download icon (default folder: ./icons)")
    ap.add_argument("-icon-open", action="store_true",
                    help="Download icon and open it")

    args = ap.parse_args()

    if ":" not in args.target:
        print("Target must be ip:port", file=sys.stderr)
        sys.exit(1)

    host, port = args.target.rsplit(":", 1)
    port = int(port)

    try:
        info = query_dss(host, port)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    requested_fields = any([
        args.name,
        args.info,
        args.news,
        args.players,
        args.max_players,
    ])

    def show_all():
        print(f"Name:        {info['name']}")
        print(f"Info:        {info['info']}")
        print(f"News:        {info['news']}")
        print(f"Players:     {info['players']}")
        print(f"Max Players: {info['max_players']}")

    if not requested_fields:
        show_all()
    else:
        if args.name:
            print(info["name"])
        if args.info:
            print(info["info"])
        if args.news:
            print(info["news"])
        if args.players:
            print(info["players"])
        if args.max_players:
            print(info["max_players"])

    if args.icon or args.icon_open:
        folder = args.icon if args.icon else "icons"
        os.makedirs(folder, exist_ok=True)

        ext = detect_icon_ext(info["icon"])
        filename = f"dss_{host}_{port}.{ext}"
        path = os.path.join(folder, filename)

        with open(path, "wb") as f:
            f.write(info["icon"])

        print(f"Icon saved to {path}")

        if args.icon_open:
            open_file(path)

if __name__ == "__main__":
    main()
