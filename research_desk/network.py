"""Public-web fetcher. Pin validated DNS addresses while retaining TLS hostname checks."""

import http.client
import ipaddress
import socket
import ssl
from urllib.parse import urljoin, urlsplit

MAX_FETCH_BYTES = 16 * 1024 * 1024


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, address, port):
        super().__init__(host, port=port, timeout=20, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        self.sock = socket.create_connection((self.address, self.port), self.timeout)
        self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)


def public_target(url):
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        raise ValueError("Use a public HTTP or HTTPS URL without embedded credentials")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    if port not in (80, 443):
        raise ValueError("Only standard web ports are supported")
    addresses = {answer[4][0] for answer in socket.getaddrinfo(parts.hostname, port, type=socket.SOCK_STREAM)}
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ValueError("Private, local and reserved network addresses are blocked")
    return parts, port, sorted(addresses)[0]


def fetch_public(url, max_bytes=MAX_FETCH_BYTES, headers=None):
    credential_host = urlsplit(url).hostname if headers else None
    for _ in range(6):
        parts, port, address = public_target(url)
        if credential_host and (parts.hostname != credential_host or parts.scheme != "https"):
            raise ValueError("A credentialed request requires HTTPS on its original host")
        if parts.scheme == "https":
            conn = PinnedHTTPS(parts.hostname, address, port)
        else:
            conn = http.client.HTTPConnection(address, port, timeout=20)
        path = (parts.path or "/") + ("?" + parts.query if parts.query else "")
        try:
            conn.request("GET", path, headers={"Host": parts.hostname, "User-Agent": "ResearchDesk/1.0 (personal research)",
                                              "Accept-Encoding": "identity", **(headers or {})})
            response = conn.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader("Location")
                if not location:
                    raise ValueError("Redirect has no destination")
                url = urljoin(url, location)
                continue
            if response.status != 200:
                raise ValueError("Source returned HTTP " + str(response.status))
            chunks, size = [], 0
            while chunk := response.read(65536):
                size += len(chunk)
                if size > max_bytes:
                    raise ValueError("Source exceeds the download limit")
                chunks.append(chunk)
            return b"".join(chunks), response.getheader("Content-Type", ""), url
        finally:
            conn.close()
    raise ValueError("Too many source redirects")
