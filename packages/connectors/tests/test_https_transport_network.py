"""Real TLS in a disposable, network-isolated Linux namespace (no merchant traffic)."""

import os
import ssl
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest
from ragcommerce_connectors.https_transport import SafeHttpsResolver
from ragcommerce_connectors.security import SafeLinkPolicy
from ragcommerce_connectors.spi import ConnectorError

pytestmark = pytest.mark.integration
ADDRESSES = ("93.184.216.34", "93.184.216.35")
POLICY = SafeLinkPolicy(frozenset({"shop.qa.test", "next.qa.test", "wrong.qa.test"}))


@pytest.fixture(scope="session")
def tls_addresses():
    if os.environ.get("PINNED_TLS_NETWORK") != "1":
        pytest.skip("isolated Linux namespace with NET_ADMIN required")
    for address in ADDRESSES:
        subprocess.run(
            ["ip", "address", "add", address + "/32", "dev", "lo"], check=True, capture_output=True
        )


@pytest.fixture
def tls_network(tmp_path, tls_addresses):
    cert, key = tmp_path / "qa.crt", tmp_path / "qa.key"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(key),
            "-out",
            str(cert),
            "-days",
            "1",
            "-subj",
            "/CN=shop.qa.test",
            "-addext",
            "subjectAltName=DNS:shop.qa.test,DNS:next.qa.test",
        ],
        check=True,
        capture_output=True,
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    sni, requests = [], []
    context.set_servername_callback(lambda sock, name, ctx: sni.append(name))

    class Handler(BaseHTTPRequestHandler):
        def do_HEAD(self):
            requests.append((self.path, self.connection.getsockname()[0], self.headers))
            destination = {
                "/start": "https://next.qa.test/done",
                "/rebind": "/done",
                "/loop": "/loop",
                "/unsafe": "https://evil.qa.test/item",
            }.get(self.path)
            self.send_response(302 if destination else 200)
            if destination:
                self.send_header("Location", destination)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):
            pass

    servers = []
    for address in ADDRESSES:
        server = ThreadingHTTPServer((address, 443), Handler)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        servers.append(server)
        Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
    client_context = ssl.create_default_context(cafile=str(cert))
    try:
        yield client_context, requests, sni
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()


def test_real_tls_peer_sni_redirect_and_no_second_hostname_dns(tls_network, monkeypatch):
    context, requests, sni = tls_network
    queries = []

    def dns(host):
        queries.append(host)
        return (ADDRESSES[0 if host == "shop.qa.test" else 1],)

    def unexpected_dns(*args, **kwargs):
        pytest.fail("socket attempted hostname resolution after address validation")

    monkeypatch.setattr("socket.getaddrinfo", unexpected_dns)
    assert (
        SafeHttpsResolver(POLICY, resolver=dns, context=context).resolve(
            "https://shop.qa.test/start"
        )
        == "https://next.qa.test/done"
    )
    assert queries == ["shop.qa.test", "next.qa.test"]
    assert sni == queries
    assert [r[1] for r in requests] == list(ADDRESSES)
    assert [r[2]["Host"] for r in requests] == queries
    assert all(r[2].get("Authorization") is None and r[2].get("Cookie") is None for r in requests)


def test_real_tls_then_rebinding_to_private_denied(tls_network):
    context, requests, _ = tls_network
    values = iter([(ADDRESSES[0],), ("127.0.0.1",)])
    with pytest.raises(ConnectorError):
        SafeHttpsResolver(POLICY, resolver=lambda _: next(values), context=context).resolve(
            "https://shop.qa.test/rebind"
        )
    assert len(requests) == 1


@pytest.mark.parametrize("host,trust", [("wrong.qa.test", True), ("shop.qa.test", False)])
def test_real_tls_rejects_hostname_mismatch_and_unknown_ca(tls_network, host, trust):
    context, requests, _ = tls_network
    with pytest.raises(ConnectorError):
        SafeHttpsResolver(
            POLICY, resolver=lambda _: (ADDRESSES[0],), context=context if trust else None
        ).resolve(f"https://{host}/done")
    assert not requests


def test_real_tls_redirect_authority_denied_before_dns(tls_network):
    context, requests, _ = tls_network
    queries = []

    def dns(host):
        queries.append(host)
        return (ADDRESSES[0],)

    with pytest.raises(ConnectorError):
        SafeHttpsResolver(POLICY, resolver=dns, context=context).resolve(
            "https://shop.qa.test/unsafe"
        )
    assert queries == ["shop.qa.test"] and len(requests) == 1


def test_real_tls_loop_has_bounded_connections(tls_network):
    context, requests, _ = tls_network
    with pytest.raises(ConnectorError):
        SafeHttpsResolver(POLICY, resolver=lambda _: (ADDRESSES[0],), context=context).resolve(
            "https://shop.qa.test/loop"
        )
    assert len(requests) == 4
