"""A bare webhook route (no ``/p/<profile>/`` prefix) is served by the DEFAULT profile, so it must
enter that profile's route scope — not a no-op (#67277 follow-up).

Without a scope, a ``--script`` route's ``build_subprocess_env()`` hits ``get_secret``'s fail-closed
path under the multiplexed gateway and raises ``UnscopedSecretError``, so every script filter dies
even though delivery and signature validation succeeded.
"""
import pytest

# Import now: ``_profile_scope`` imports gateway.run lazily, and the suite's home-IO guard treats an
# import-time read of the real install as forbidden I/O. Warming it at collection keeps the test
# hermetic.
import gateway.run  # noqa: F401
from gateway.config import PlatformConfig
from gateway.platforms.webhook import WebhookAdapter


def _adapter() -> WebhookAdapter:
    return WebhookAdapter(PlatformConfig(enabled=True, extra={"host": "127.0.0.1", "port": 0, "routes": {}}))


@pytest.fixture
def default_home(tmp_path, monkeypatch):
    """An isolated default HERMES_HOME holding GH_TOKEN, so scope binding has a secret to find."""
    home = tmp_path / ".hermes"
    home.mkdir()
    (home / ".env").write_text("GH_TOKEN=default-token\n")
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr("hermes_cli.profiles._get_default_hermes_home", lambda: home)
    monkeypatch.setattr("hermes_cli.profiles._get_profiles_root", lambda: home / "profiles")
    return home


def test_bare_route_scope_binds_default_profile_secrets(default_home, monkeypatch):
    from agent import secret_scope

    monkeypatch.setattr(secret_scope, "_MULTIPLEX_ACTIVE", True)
    adapter = _adapter()

    assert secret_scope.current_secret_scope() is None
    with adapter._profile_scope(None):
        scope = secret_scope.current_secret_scope()
        assert scope is not None and scope.get("GH_TOKEN") == "default-token"
    assert secret_scope.current_secret_scope() is None  # restored on exit


def test_routed_route_scope_still_binds_named_profile(default_home, monkeypatch):
    """The ``/p/<profile>/`` path is unchanged: it binds the NAMED profile, not the default."""
    from agent import secret_scope

    sec = default_home / "profiles" / "sec"
    sec.mkdir(parents=True)
    (sec / ".env").write_text("GH_TOKEN=sec-token\n")
    monkeypatch.setattr(secret_scope, "_MULTIPLEX_ACTIVE", True)
    adapter = _adapter()

    with adapter._profile_scope("sec"):
        scope = secret_scope.current_secret_scope()
        assert scope is not None and scope.get("GH_TOKEN") == "sec-token"
