import httpx
import pytest
from docagent.github import GitHub, GitHubError


def test_github_resolves_refs_and_sends_token_only_in_header():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"sha": "b" * 40})

    with GitHub("sensitive-test-value", transport=httpx.MockTransport(handler)) as github:
        assert github.resolve("owner/repo", "feature/test") == "b" * 40
    assert requests[0].headers["Authorization"] == "Bearer sensitive-test-value"
    assert "sensitive-test-value" not in str(requests[0].url)
    assert requests[0].url.host == "api.github.com"


def test_untrusted_archive_redirect_is_rejected(tmp_path):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(302, headers={"location": "https://attacker.test/archive"})
    )
    with GitHub("test-token", transport=transport) as github:
        with pytest.raises(GitHubError, match="Unexpected archive host"):
            github.download("owner/repo", "a" * 40, tmp_path)


def test_errors_do_not_echo_provider_response():
    transport = httpx.MockTransport(lambda request: httpx.Response(401, json={"message": "secret-token"}))
    with GitHub("secret-token", transport=transport) as github:
        with pytest.raises(GitHubError) as exc:
            github.user()
        assert "secret-token" not in str(exc.value)


def test_private_consent_prevents_job_creation(client, monkeypatch):
    import docagent.api as api

    monkeypatch.setattr(api.GitHub, "repository", lambda self, name: {"private": True})
    response = client.post(
        "/api/jobs",
        json={"repository": "owner/repo", "providers": [{"provider": "openai", "model": "model"}]},
    )
    assert response.status_code == 422
    assert client.get("/api/jobs").json() == []


def test_pat_login_rotates_session_and_encrypts_token(client, monkeypatch):
    import docagent.api as api
    from docagent.db import UserSession, session_factory
    from docagent.security import decrypt, token_hash

    monkeypatch.setattr(api.GitHub, "user", lambda self: {"id": 1234, "login": "reviewer"})
    old_cookie = client.cookies["docagent_session"]
    response = client.post("/api/auth/pat", json={"token": "test-pat-credential"})
    assert response.status_code == 200
    assert client.cookies["docagent_session"] != old_cookie
    with session_factory()() as db:
        assert db.get(UserSession, token_hash(old_cookie)) is None
        user = db.get(UserSession, token_hash(client.cookies["docagent_session"]))
        assert user.owner == "github:1234"
        assert user.token != "test-pat-credential"
        assert decrypt(user.token) == "test-pat-credential"


def test_oauth_state_is_single_use_and_expires(client):
    from docagent.config import settings

    cfg = settings()
    cfg.github_client_id = "test-client-id"
    response = client.get("/api/auth/github/start", follow_redirects=False)
    assert response.status_code == 307
    assert "code_challenge_method=S256" in response.headers["location"]
    response = client.get("/api/auth/github/callback?code=fake&state=incorrect")
    assert response.status_code == 403
