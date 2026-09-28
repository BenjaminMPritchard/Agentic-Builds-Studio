import base64
import json
import os
import subprocess
import tempfile
import unittest
import urllib.error

from lib.github_app import GitHubAppError, app_jwt, installation_token, key_available


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


class FakeResponse:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    """Records requests and returns queued responses (or raises queued exceptions)."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def __call__(self, req, timeout=None):
        self.calls.append(req)
        self.timeout = timeout
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return FakeResponse(item)


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.key_path = os.path.join(cls.tmp, "k.pem")
        cls.pub_path = os.path.join(cls.tmp, "pub.pem")
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048",
             "-out", cls.key_path],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["openssl", "pkey", "-in", cls.key_path, "-pubout", "-out", cls.pub_path],
            check=True, capture_output=True,
        )


class JwtTests(Base):
    def test_jwt_shape_and_claims(self):
        token = app_jwt(123, self.key_path, now=1_700_000_000.0)
        parts = token.split(".")
        self.assertEqual(len(parts), 3)

        header = json.loads(_b64url_decode(parts[0]))
        payload = json.loads(_b64url_decode(parts[1]))

        self.assertEqual(header, {"alg": "RS256", "typ": "JWT"})
        self.assertEqual(payload["iat"], 1_700_000_000 - 60)
        self.assertEqual(payload["exp"], 1_700_000_000 + 540)
        self.assertEqual(payload["iss"], "123")

    def test_jwt_signature_verifies(self):
        token = app_jwt(123, self.key_path, now=1_700_000_000.0)
        header_b64, payload_b64, sig_b64 = token.split(".")
        signing_input = f"{header_b64}.{payload_b64}".encode()
        signature = _b64url_decode(sig_b64)

        sig_path = os.path.join(self.tmp, "sig")
        with open(sig_path, "wb") as f:
            f.write(signature)

        proc = subprocess.run(
            ["openssl", "dgst", "-sha256", "-verify", self.pub_path, "-signature", sig_path],
            input=signing_input, capture_output=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(b"Verified OK", proc.stdout + proc.stderr)

    def test_missing_key_file(self):
        with self.assertRaises(GitHubAppError) as ctx:
            app_jwt(123, os.path.join(self.tmp, "does-not-exist.pem"))
        self.assertNotIn("PRIVATE KEY", str(ctx.exception))

    def test_key_available(self):
        self.assertTrue(key_available(self.key_path))
        self.assertFalse(key_available(os.path.join(self.tmp, "nope.pem")))


class InstallationTokenTests(Base):
    def test_happy_path(self):
        opener = FakeOpener([
            {"id": 999},
            {"token": "ghs_abc123", "repositories": [{"name": "name"}]},
        ])

        token = installation_token("owner/name", 123, self.key_path, opener=opener, now=1_700_000_000.0)

        self.assertEqual(token, "ghs_abc123")
        self.assertEqual(len(opener.calls), 2)

        first, second = opener.calls
        self.assertEqual(first.full_url, "https://api.github.com/repos/owner/name/installation")
        self.assertEqual(first.get_method(), "GET")
        self.assertTrue(first.get_header("Authorization").startswith("Bearer "))

        self.assertEqual(second.full_url, "https://api.github.com/app/installations/999/access_tokens")
        self.assertEqual(second.get_method(), "POST")
        self.assertTrue(second.get_header("Authorization").startswith("Bearer "))
        body = json.loads(second.data)
        self.assertEqual(body, {"repositories": ["name"]})

    def test_missing_key_file(self):
        opener = FakeOpener([])
        with self.assertRaises(GitHubAppError):
            installation_token("owner/name", 123, os.path.join(self.tmp, "nope.pem"), opener=opener)
        self.assertEqual(opener.calls, [])

    def test_installation_lookup_404(self):
        err = urllib.error.HTTPError("url", 404, "Not Found", {}, None)
        opener = FakeOpener([err])

        with self.assertRaises(GitHubAppError) as ctx:
            installation_token("owner/name", 123, self.key_path, opener=opener)
        self.assertIn("404", str(ctx.exception))

    def test_response_missing_token(self):
        opener = FakeOpener([
            {"id": 999},
            {"repositories": [{"name": "name"}]},
        ])
        with self.assertRaises(GitHubAppError):
            installation_token("owner/name", 123, self.key_path, opener=opener)

    def test_token_for_different_repo_rejected(self):
        opener = FakeOpener([
            {"id": 999},
            {"token": "ghs_secretvalue", "repositories": [{"name": "other-repo"}]},
        ])
        with self.assertRaises(GitHubAppError) as ctx:
            installation_token("owner/name", 123, self.key_path, opener=opener)
        self.assertNotIn("ghs_secretvalue", str(ctx.exception))

    def test_exception_text_never_leaks_secrets(self):
        opener = FakeOpener([
            {"id": 999},
            {"repositories": [{"name": "name"}]},
        ])
        with self.assertRaises(GitHubAppError) as ctx:
            installation_token("owner/name", 123, self.key_path, opener=opener)
        text = str(ctx.exception)
        self.assertNotIn("PRIVATE KEY", text)
        self.assertNotIn("ghs_", text)


if __name__ == "__main__":
    unittest.main()
