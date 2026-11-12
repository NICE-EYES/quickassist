import http.client
import json

import pytest

from quickassist.bridge.server import BridgeServer, RequestRejected, check_headers, parse_context

TOKEN = "secret-token"
PORT = 48999


def headers(**over):
    h = {"Host": f"127.0.0.1:{PORT}", "Origin": "chrome-extension://abcdef", "Authorization": f"Bearer {TOKEN}"}
    h.update(over)
    return {k: v for k, v in h.items() if v is not None}


def test_valid_headers():
    check_headers(headers(), TOKEN, PORT)
    check_headers(headers(Origin=None), TOKEN, PORT)          # не-браузерный клиент с токеном
    check_headers(headers(), TOKEN, PORT, "abcdef")


@pytest.mark.parametrize("over,status", [
    ({"Authorization": "Bearer wrong"}, 401),
    ({"Authorization": None}, 401),
    ({"Origin": "https://evil.example"}, 403),
    ({"Host": "evil.example:48999"}, 421),
    ({"Host": "127.0.0.1:1"}, 421),
])
def test_rejected_headers(over, status):
    with pytest.raises(RequestRejected) as e:
        check_headers(headers(**over), TOKEN, PORT)
    assert e.value.status == status


def test_extension_id_pinning():
    with pytest.raises(RequestRejected):
        check_headers(headers(Origin="chrome-extension://other"), TOKEN, PORT, "abcdef")
    with pytest.raises(RequestRejected):
        check_headers(headers(Origin=None), TOKEN, PORT, "abcdef")


def test_parse_context():
    ctx = parse_context(json.dumps({"version": 1, "kind": "selection", "url": "https://a", "title": "T", "text": "hi"}).encode())
    assert ctx.text == "hi" and ctx.kind == "selection"
    for bad in [b"[]", b"{", json.dumps({"version": 1, "kind": "exec"}).encode(),
                json.dumps({"version": 1, "kind": "selection", "text": ""}).encode(),
                json.dumps({"version": 1, "kind": "tab", "url": 5}).encode()]:
        with pytest.raises(RequestRejected):
            parse_context(bad)
    big = parse_context(json.dumps({"version": 1, "kind": "page", "text": "x" * 300_000}).encode())
    assert big.truncated and len(big.text) == 200_000


def test_live_server_loopback_only():
    from PySide6.QtCore import QCoreApplication
    QCoreApplication.instance() or QCoreApplication([])
    received = []
    server = BridgeServer(lambda: TOKEN)
    server.contextReceived.connect(received.append)
    assert server.start(PORT)
    try:
        assert server._server.server_address[0] == "127.0.0.1"
        body = json.dumps({"version": 1, "kind": "tab", "url": "https://x", "title": "X"})
        conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=3)
        conn.request("POST", "/v1/context", body, headers(**{"Content-Type": "application/json"}))
        assert conn.getresponse().status == 200
        conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=3)
        conn.request("POST", "/v1/context", body, headers(**{"Content-Type": "application/json", "Authorization": "Bearer no"}))
        assert conn.getresponse().status == 401
        conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=3)
        conn.request("OPTIONS", "/v1/context", headers=headers())
        r = conn.getresponse()
        assert r.status == 403 and r.getheader("Access-Control-Allow-Origin") is None
        conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=3)
        conn.request("POST", "/v1/ping", "{}", headers(**{"Content-Type": "application/json"}))
        assert json.loads(conn.getresponse().read())["ok"] is True
        QCoreApplication.processEvents()
    finally:
        server.stop()
    assert len(received) == 1 and received[0].url == "https://x"
