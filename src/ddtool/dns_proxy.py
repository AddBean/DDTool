from __future__ import annotations

import json
import socket
import ssl
import struct
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Iterable


QTYPE_A = 1
QTYPE_AAAA = 28
QTYPE_HTTPS = 65

_DOH_ENDPOINTS = (
    ("https://223.5.5.5/resolve", "dns.alidns.com"),
    ("https://223.6.6.6/resolve", "dns.alidns.com"),
)

_UDP_UPSTREAMS = ("223.5.5.5", "223.6.6.6", "119.29.29.29")


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl._create_unverified_context()
    ctx.check_hostname = False
    return ctx


def _encode_name(name: str) -> bytes:
    out = bytearray()
    for label in name.rstrip(".").split("."):
        raw = label.encode("idna")
        out.append(len(raw))
        out.extend(raw)
    out.append(0)
    return bytes(out)


def _parse_question(data: bytes) -> tuple[str, int, int]:
    if len(data) < 12:
        raise ValueError("short dns packet")
    offset = 12
    labels: list[str] = []
    while True:
        if offset >= len(data):
            raise ValueError("truncated qname")
        length = data[offset]
        if length == 0:
            offset += 1
            break
        if length & 0xC0:
            raise ValueError("compressed qname")
        offset += 1
        labels.append(data[offset : offset + length].decode("idna", "replace"))
        offset += length
    if offset + 4 > len(data):
        raise ValueError("truncated question")
    qtype, qclass = struct.unpack("!HH", data[offset : offset + 4])
    return ".".join(labels), qtype, qclass


def _nodata(request: bytes) -> bytes:
    txid, flags, qdcount, _, _, _ = struct.unpack("!HHHHHH", request[:12])
    flags = (flags & 0x7800) | 0x8180
    header = struct.pack("!HHHHHH", txid, flags, qdcount, 0, 0, 0)
    return header + request[12:]


def _answer_a(request: bytes, name: str, ips: list[str], ttl: int = 30) -> bytes:
    txid, flags, _, _, _, _ = struct.unpack("!HHHHHH", request[:12])
    flags = (flags & 0x7800) | 0x8180
    question = _encode_name(name) + struct.pack("!HH", QTYPE_A, 1)
    answers = bytearray()
    for ip in ips:
        answers.extend(b"\xc0\x0c")
        answers.extend(struct.pack("!HHIH", QTYPE_A, 1, ttl, 4))
        answers.extend(socket.inet_aton(ip))
    header = struct.pack("!HHHHHH", txid, flags, 1, len(ips), 0, 0)
    return header + question + bytes(answers)


def _doh_a(name: str) -> list[str]:
    ctx = _ssl_context()
    query = urllib.parse.urlencode({"name": name, "type": "A"})
    for base, host in _DOH_ENDPOINTS:
        req = urllib.request.Request(
            f"{base}?{query}",
            headers={
                "accept": "application/dns-json",
                "Host": host,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=3, context=ctx) as resp:
                payload = json.loads(resp.read().decode("utf-8", "replace"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            continue
        if payload.get("Status") not in (0, "0", None):
            continue
        ips = [
            item["data"]
            for item in payload.get("Answer") or []
            if item.get("type") == 1 and isinstance(item.get("data"), str)
        ]
        if ips:
            return ips
    return []


def _udp_a(name: str) -> list[str]:
    question = _encode_name(name) + struct.pack("!HH", QTYPE_A, 1)
    packet = struct.pack("!HHHHHH", 0x1234, 0x0100, 1, 0, 0, 0) + question
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(2)
    try:
        for server in _UDP_UPSTREAMS:
            try:
                sock.sendto(packet, (server, 53))
                data, _ = sock.recvfrom(4096)
            except OSError:
                continue
            ips = _extract_a_records(data)
            if ips:
                return ips
    finally:
        sock.close()
    return []


def _extract_a_records(data: bytes) -> list[str]:
    if len(data) < 12:
        return []
    _, _, qdcount, ancount, _, _ = struct.unpack("!HHHHHH", data[:12])
    offset = 12
    try:
        for _ in range(qdcount):
            offset = _skip_name(data, offset) + 4
        ips: list[str] = []
        for _ in range(ancount):
            offset = _skip_name(data, offset)
            rtype, _, _, rdlength = struct.unpack("!HHIH", data[offset : offset + 10])
            offset += 10
            rdata = data[offset : offset + rdlength]
            offset += rdlength
            if rtype == QTYPE_A and rdlength == 4:
                ips.append(socket.inet_ntoa(rdata))
        return ips
    except (struct.error, IndexError, ValueError):
        return []


def _skip_name(data: bytes, offset: int) -> int:
    while True:
        length = data[offset]
        if length == 0:
            return offset + 1
        if length & 0xC0:
            return offset + 2
        offset += 1 + length


def resolve_ipv4(name: str) -> list[str]:
    return _doh_a(name) or _udp_a(name)


def build_response(request: bytes) -> bytes | None:
    try:
        name, qtype, qclass = _parse_question(request)
    except ValueError:
        return None
    if qclass != 1:
        return _nodata(request)
    if qtype in (QTYPE_AAAA, QTYPE_HTTPS):
        return _nodata(request)
    if qtype != QTYPE_A:
        return _nodata(request)
    ips = resolve_ipv4(name)
    if not ips:
        return _nodata(request)
    return _answer_a(request, name, ips)


class DnsProxy:
    def __init__(self, host: str = "127.0.0.1", port: int = 53) -> None:
        self.host = host
        self.port = port
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.host, self.port))
        sock.settimeout(0.5)
        self._sock = sock
        self._stop.clear()
        self._thread = threading.Thread(target=self._serve, name="ddtool-dns", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        sock = self._sock
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        self._sock = None
        thread = self._thread
        if thread is not None:
            thread.join(timeout=1.5)
        self._thread = None

    def _serve(self) -> None:
        sock = self._sock
        if sock is None:
            return
        while not self._stop.is_set():
            try:
                data, addr = sock.recvfrom(4096)
            except TimeoutError:
                continue
            except OSError:
                break
            response = build_response(data)
            if not response:
                continue
            try:
                sock.sendto(response, addr)
            except OSError:
                continue


def iter_upstream_names() -> Iterable[str]:
    return _UDP_UPSTREAMS


if __name__ == "__main__":
    proxy = DnsProxy()
    proxy.start()
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        proxy.stop()

