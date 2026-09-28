"""GitHub App installation-token helper.

Turns a GitHub App private key into a short-lived installation token scoped to a single
repository, using only the Python stdlib plus the `openssl` CLI (no pip packages). The
private key never touches argv or exception text; it is always passed to `openssl` on
stdin.
"""
import base64
import json
import os
import subprocess
import time
import urllib.error
import urllib.request

API = "https://api.github.com"
USER_AGENT = "studio-merge-gate"


class GitHubAppError(Exception):
    pass


def key_available(key_path):
    return os.path.isfile(key_path) and os.access(key_path, os.R_OK)


def _b64url(data: bytes) -> bytes:
    return base64.urlsafe_b64encode(data).rstrip(b"=")


def app_jwt(app_id: int, key_path: str, now: float | None = None) -> str:
    if not key_available(key_path):
        raise GitHubAppError("GitHub App private key is missing or unreadable")

    ts = time.time() if now is None else now
    header = {"alg": "RS256", "typ": "JWT"}
    payload = {"iat": int(ts) - 60, "exp": int(ts) + 540, "iss": str(app_id)}

    header_b64 = _b64url(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = header_b64 + b"." + payload_b64

    try:
        proc = subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", key_path],
            input=signing_input,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise GitHubAppError(f"failed to invoke openssl: {e}") from None

    if proc.returncode != 0:
        raise GitHubAppError("openssl failed to sign the JWT")

    signature_b64 = _b64url(proc.stdout)
    return (signing_input + b"." + signature_b64).decode("ascii")


def _request(url, opener, *, method="GET", headers=None, data=None):
    req = urllib.request.Request(url, method=method, data=data, headers=headers or {})
    try:
        with opener(req, timeout=15) as resp:
            body = resp.read()
    except urllib.error.HTTPError as e:
        raise GitHubAppError(f"GitHub API request to {url} failed with HTTP {e.code}") from None
    except urllib.error.URLError as e:
        raise GitHubAppError(f"GitHub API request to {url} failed: {e.reason}") from None

    try:
        return json.loads(body)
    except (ValueError, TypeError):
        raise GitHubAppError(f"GitHub API response from {url} was not valid JSON") from None


def installation_token(repo: str, app_id: int, key_path: str, opener=None, now: float | None = None) -> str:
    if opener is None:
        opener = urllib.request.urlopen

    if "/" not in repo:
        raise GitHubAppError("repo must be in 'owner/name' form")
    name = repo.split("/", 1)[1]

    jwt = app_jwt(app_id, key_path, now=now)

    common_headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": USER_AGENT,
    }

    install_headers = dict(common_headers)
    install_headers["Authorization"] = f"Bearer {jwt}"
    install = _request(f"{API}/repos/{repo}/installation", opener, headers=install_headers)

    if not isinstance(install, dict) or not install.get("id"):
        raise GitHubAppError("GitHub installation lookup response was missing 'id'")
    installation_id = install["id"]

    token_headers = dict(common_headers)
    token_headers["Authorization"] = f"Bearer {jwt}"
    token_headers["Content-Type"] = "application/json"
    body = json.dumps({"repositories": [name]}).encode()

    result = _request(
        f"{API}/app/installations/{installation_id}/access_tokens",
        opener,
        method="POST",
        headers=token_headers,
        data=body,
    )

    if not isinstance(result, dict) or not result.get("token"):
        raise GitHubAppError("GitHub access-token response was missing 'token'")

    repositories = result.get("repositories")
    if isinstance(repositories, list):
        names = {r.get("name") for r in repositories if isinstance(r, dict)}
        if names and name not in names:
            raise GitHubAppError("GitHub issued a token that does not cover the requested repository")

    return result["token"]


def account_installation_token(owner: str, app_id: int, key_path: str, opener=None, now: float | None = None) -> str:
    """Token for every repository of `owner`'s installation (a user or an organisation). Used for the
    agents' own App, whose token replaces any personal token in an agent run."""
    if opener is None:
        opener = urllib.request.urlopen
    if not owner or "/" in owner:
        raise GitHubAppError("owner must be a GitHub user or organisation name")
    jwt = app_jwt(app_id, key_path, now=now)
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
               "User-Agent": USER_AGENT, "Authorization": f"Bearer {jwt}"}
    install = _request(f"{API}/users/{owner}/installation", opener, headers=headers)
    if not isinstance(install, dict) or not install.get("id"):
        raise GitHubAppError("GitHub installation lookup response was missing 'id'")
    result = _request(f"{API}/app/installations/{install['id']}/access_tokens", opener, method="POST",
                      headers={**headers, "Content-Type": "application/json"}, data=b"{}")
    if not isinstance(result, dict) or not result.get("token"):
        raise GitHubAppError("GitHub access-token response was missing 'token'")
    return result["token"]
