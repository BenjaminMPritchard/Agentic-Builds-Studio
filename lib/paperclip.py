"""Small Paperclip API client (stdlib only). Every endpoint used by the Studio scripts lives here.

Paths were checked against the live instance's /api/openapi.json (v2026.916.1) on 2026-09-26.
Response shapes are not in the spec; ones marked TODO(check) still need a live look. Verify them against the running instance, fix the
path here, and nothing else needs to change. The tests use fake_paperclip.py, which mirrors
these paths.
"""
import json
import os
import subprocess
import urllib.error
import urllib.request


class ApiError(Exception):
    def __init__(self, status, body):
        super().__init__(f"HTTP {status}: {body[:200]}")
        self.status = status


class Paperclip:
    def __init__(self, base=None, key=None, run_id=None, cli="paperclipai"):
        self.base = (base or os.environ.get("PAPERCLIP_API_URL", "http://localhost:3100")).rstrip("/")
        self.key = key or os.environ.get("PAPERCLIP_API_KEY", "")
        self.run_id = run_id or os.environ.get("PAPERCLIP_RUN_ID", "")
        self.cli = cli

    def call(self, method, path, body=None):
        headers = {"Content-Type": "application/json"}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        if self.run_id:
            headers["X-Paperclip-Run-Id"] = self.run_id
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            raise ApiError(e.code, e.read().decode(errors="replace"))

    # --- documented in the guide -------------------------------------------------
    def heartbeat_context(self, issue_id):
        return self.call("GET", f"/api/issues/{issue_id}/heartbeat-context")

    def checkout(self, issue_id, agent_id=None, expected=None):
        # A 409 means someone else has it: never retry.
        return self.call("POST", f"/api/issues/{issue_id}/checkout",
                         {"agentId": agent_id or os.environ.get("PAPERCLIP_AGENT_ID"),
                          "expectedStatuses": expected or ["backlog", "todo", "in_progress", "in_review", "blocked"]})

    def patch_issue(self, issue_id, **fields):
        return self.call("PATCH", f"/api/issues/{issue_id}", fields)

    def costs_by_agent(self, company_id):
        return self.call("GET", f"/api/companies/{company_id}/costs/by-agent")

    def costs_by_project(self, company_id):
        return self.call("GET", f"/api/companies/{company_id}/costs/by-project")

    # --- paths confirmed in OpenAPI; TODO(check) response shapes ---------------------
    def list_issues(self, company_id, status=None):
        q = f"?status={status}" if status else ""
        r = self.call("GET", f"/api/companies/{company_id}/issues{q}")
        return r.get("issues", r) if isinstance(r, dict) else r

    def get_document(self, issue_id, key):
        try:
            return self.call("GET", f"/api/issues/{issue_id}/documents/{key}")
        except ApiError as e:
            if e.status == 404:
                return None
            raise

    def put_document(self, issue_id, key, body):
        return self.call("PUT", f"/api/issues/{issue_id}/documents/{key}", {"format": "markdown", "body": body})

    def comment(self, issue_id, text):
        return self.call("POST", f"/api/issues/{issue_id}/comments", {"body": text})

    def list_agents(self, company_id):
        r = self.call("GET", f"/api/companies/{company_id}/agents")
        return r.get("agents", r) if isinstance(r, dict) else r

    def runs(self, company_id, limit=50):
        r = self.call("GET", f"/api/companies/{company_id}/heartbeat-runs?limit={limit}")
        return r.get("runs", r) if isinstance(r, dict) else r

    def quota_windows(self, company_id):
        return self.call("GET", f"/api/companies/{company_id}/costs/quota-windows")

    def pause_agent(self, agent_id):
        return self.call("POST", f"/api/agents/{agent_id}/pause")

    def resume_agent(self, agent_id):
        return self.call("POST", f"/api/agents/{agent_id}/resume")

    # --- CLI wrappers (documented) --------------------------------------------------
    def wake_agent(self, agent_id, fresh=True, reason="clerk"):
        """POST /api/agents/{id}/wakeup (in the live OpenAPI spec). Returns True on success."""
        try:
            self.call("POST", f"/api/agents/{agent_id}/wakeup", {
                "source": "automation", "triggerDetail": "system", "reason": reason, "forceFreshSession": fresh})
            return True
        except ApiError:
            return False

    def export_company(self, company_id, out):
        return subprocess.run([self.cli, "company", "export", company_id, "--out", out],
                              capture_output=True, text=True, timeout=300).returncode == 0

    def interactions(self, issue_id):
        # TODO(check): same path the guard uses.
        r = self.call("GET", f"/api/issues/{issue_id}/interactions")
        return r.get("interactions", r) if isinstance(r, dict) else r
