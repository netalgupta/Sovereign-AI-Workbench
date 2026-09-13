"""Refuse any model endpoint that is not on this machine.

THE HOLE THIS CLOSES.

`OLLAMA_HOST` was read straight from the environment:

    OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

Set it to a remote address and every model call in the product leaves
the premises -- silently, with no code change, no warning, and no way
for a user to tell. The network monitor would show the connection, but
a connection to a plausible internal-looking host is exactly the one
nobody questions.

The sovereignty claim was resting on the default value of an
environment variable. That is a convention, not a control, and CLAUDE.md
hard constraint #1 is stated as a design law: "No outbound network
calls, anywhere, ever."

So the address is CHECKED at the point it is constructed, and a
non-loopback host raises rather than being used. A deployment that
genuinely wants a model server on another machine has to change code and
say so in the diff, which is the point -- it becomes a decision somebody
made, not a variable somebody set.

WHY A RESOLVER AND NOT A STRING MATCH. "localhost" is not the only way
to write this and "127.0.0.1" is not the only loopback address:
127.0.0.0/8 is ALL loopback, ::1 is the IPv6 form, and a hostname can
resolve to anything. A substring check for "localhost" passes
`http://localhost.attacker.example` -- a real technique, not a
hypothetical. The host is resolved and every address it yields must be
a loopback address; one that is not fails the whole check.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class NonLocalEndpoint(RuntimeError):
    """A model or service endpoint that is not on this machine."""


def is_loopback(host: str) -> bool:
    """True only if every address `host` resolves to is loopback.

    A hostname with several A records must have ALL of them loopback:
    one public address among them is enough to send traffic off the box.
    """
    if not host:
        return False

    # A literal address needs no DNS.
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        pass

    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        # Unresolvable is not local. Failing closed is the only safe
        # direction for a check whose job is to prevent egress.
        return False

    addresses = {info[4][0] for info in infos}
    if not addresses:
        return False

    for address in addresses:
        try:
            if not ipaddress.ip_address(address).is_loopback:
                return False
        except ValueError:
            return False
    return True


def require_loopback(url: str, *, what: str = "endpoint") -> str:
    """Return `url` unchanged, or raise if it points off this machine.

    Raises:
        NonLocalEndpoint: with the resolved host named, because "the URL
            is wrong" is not actionable and "ollama.internal resolved to
            10.2.4.9" is.
    """
    parsed = urlparse(url)
    host = parsed.hostname

    if host is None:
        raise NonLocalEndpoint(
            f"{what} {url!r} has no host. This build only talks to this "
            f"machine (CLAUDE.md hard constraint #1)."
        )

    if not is_loopback(host):
        resolved = ""
        try:
            resolved = ", ".join(sorted({i[4][0] for i in socket.getaddrinfo(host, None)}))
        except socket.gaierror:
            resolved = "did not resolve"
        raise NonLocalEndpoint(
            f"{what} {url!r} is not on this machine: {host!r} -> {resolved}.\n"
            f"This workbench makes no outbound network calls -- that is the "
            f"whole claim it exists to support, and it is a design law rather "
            f"than a setting (CLAUDE.md hard constraint #1). Point it at "
            f"localhost, or change the code deliberately so the decision "
            f"appears in a diff."
        )
    return url
