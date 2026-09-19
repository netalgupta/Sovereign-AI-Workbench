"""The sovereignty claim, enforced rather than assumed.

CLAUDE.md hard constraint #1 is "No outbound network calls, anywhere,
ever." Before this, OLLAMA_HOST was read from the environment unchecked:
one variable away from sending every model call in the product off the
premises, silently, with no code change and no warning.

The claim was resting on the default value of an environment variable.
"""

import pytest

from backend.utils.loopback import NonLocalEndpoint, is_loopback, require_loopback


@pytest.mark.parametrize("url", [
    "http://localhost:11434",
    "http://127.0.0.1:11434",
    "http://127.0.0.5:11434",   # all of 127.0.0.0/8 is loopback
    "http://[::1]:11434",       # IPv6 loopback
])
def test_local_endpoints_are_allowed(url):
    assert require_loopback(url) == url


@pytest.mark.parametrize("url", [
    "http://10.2.4.9:11434",
    "http://192.168.1.50:11434",
    "http://0.0.0.0:11434",
])
def test_remote_endpoints_are_refused(url):
    with pytest.raises(NonLocalEndpoint):
        require_loopback(url)


def test_a_hostname_that_merely_starts_with_localhost_is_refused():
    """A substring check for "localhost" passes
    http://localhost.attacker.example — a real technique, not a
    hypothetical. The host is resolved and every address it yields must
    be loopback."""
    with pytest.raises(NonLocalEndpoint):
        require_loopback("http://localhost.attacker.example")


def test_an_unresolvable_host_fails_closed():
    """Failing closed is the only safe direction for a check whose job
    is to prevent egress."""
    assert is_loopback("this-host-does-not-exist.invalid") is False


def test_the_error_names_what_it_resolved_to():
    """"The URL is wrong" is not actionable. "ollama.internal resolved
    to 10.2.4.9" is."""
    with pytest.raises(NonLocalEndpoint) as exc:
        require_loopback("http://10.2.4.9:11434", what="OLLAMA_HOST")
    message = str(exc.value)
    assert "10.2.4.9" in message
    assert "OLLAMA_HOST" in message


def test_the_shipped_model_host_passes_its_own_check():
    """The guard has to be satisfied by the real default, or it would
    have been quietly disabled the first time it fired."""
    from backend.models.ollama_client import OLLAMA_HOST

    assert require_loopback(OLLAMA_HOST) == OLLAMA_HOST
