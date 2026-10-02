"""Small Paperclip API client (stdlib only).

The response contracts here are checked against the installed 2026.916.1 server
package. They still require a read-only check against the running instance before
deployment; a local fake alone is not evidence of the live contract.
"""
import json
import os
import subprocess
import urllib.error
import urllib.request
from urllib.parse import urlencode


class ApiError(Exception):
    def __init__(self, status, body):
        super().__init__(f"HTTP {status}: {body[:200]}")
        self.status = status


BOARD_KEY_FILE = os.path.join(os.path.expanduser("~"), ".config", "studio", "paperclip-board-key")


def board_key(path=None):
    """The Board API key for human tools (studio-stop, checks), from a file only its owner can read.

    Used only when no key is given or in PAPERCLIP_API_KEY: agent runs always have their own key. Returns ""
    when there is no file. A file others could read is refused rather than used.
    """
    path = path or os.environ.get("STUDIO_BOARD_KEY_FILE") or BOARD_KEY_FILE
    try:
        st = os.stat(path)
    except FileNotFoundError:
        return ""
    if st.st_uid != os.geteuid() or st.st_mode & 0o077:
        raise PermissionError(f"{path} must belong to you with mode 0600; not using it")
    with open(path) as f:
        return f.read().strip()


class Paperclip:
    def __init__(self, base=None, key=None, run_id=None, cli="paperclipai"):
        self.base = (base or os.environ.get("PAPERCLIP_API_URL", "http://localhost:3100")).rstrip("/")
        self.key = key or os.environ.get("PAPERCLIP_API_KEY", "") or board_key()
        # run_id=False: a user key (the Clerk's service user) is not a run, so no run header is sent.
        self.run_id = "" if run_id is False else (run_id or os.environ.get("PAPERCLIP_RUN_ID", ""))
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
        # The server returns a bare array, capped by limit, with offset paging.
        # Request blockers explicitly; the default list omits that projection.
        issues, offset, limit = [], 0, 200
        while True:
            query = {"limit": limit, "offset": offset, "includeBlockedBy": "true"}
            if status:
                query["status"] = status
            page = self.call("GET", f"/api/companies/{company_id}/issues?{urlencode(query)}")
            if not isinstance(page, list) or any(not isinstance(i, dict) or "id" not in i for i in page):
                raise ValueError("Paperclip issue list contract changed")
            issues.extend(page)
            if len(page) < limit:
                return issues
            offset += len(page)

    def get_issue(self, issue_id):
        issue = self.call("GET", f"/api/issues/{issue_id}")  # an id or an identifier such as AGE-6
        if not isinstance(issue, dict) or issue_id not in (issue.get("id"), issue.get("identifier")):
            raise ValueError("Paperclip issue detail contract changed")
        return issue

    def get_document(self, issue_id, key):
        try:
            return self.call("GET", f"/api/issues/{issue_id}/documents/{key}")
        except ApiError as e:
            if e.status == 404:
                return None
            raise

    def put_document(self, issue_id, key, body):
        """Create or replace an issue document. Replacing one needs the revision it replaces (Paperclip refuses
        an update without baseRevisionId), so the current one is read first."""
        payload = {"format": "markdown", "body": body}
        try:
            payload["baseRevisionId"] = self.call("GET", f"/api/issues/{issue_id}/documents/{key}")["latestRevisionId"]
        except ApiError as e:
            if e.status != 404:
                raise
        return self.call("PUT", f"/api/issues/{issue_id}/documents/{key}", payload)

    def work_products(self, issue_id):
        return self.call("GET", f"/api/issues/{issue_id}/work-products")

    def update_work_product(self, product_id, **fields):
        return self.call("PATCH", f"/api/work-products/{product_id}", fields)

    def comment(self, issue_id, text):
        return self.call("POST", f"/api/issues/{issue_id}/comments", {"body": text})

    def list_agents(self, company_id):
        r = self.call("GET", f"/api/companies/{company_id}/agents")
        if not isinstance(r, list):
            raise ValueError("Paperclip agent list contract changed")
        return r

    def runs(self, company_id, limit=50):
        r = self.call("GET", f"/api/companies/{company_id}/heartbeat-runs?limit={limit}")
        if not isinstance(r, list):
            raise ValueError("Paperclip run list contract changed")
        return r

    def rescan_skills(self, company_id, project_id):
        """Re-read skills from a project's workspace (imports new ones, updates changed ones)."""
        return self.call("POST", f"/api/companies/{company_id}/skills/scan-projects",
                         {"projectIds": [project_id], "mode": "import"})

    def quota_windows(self, company_id):
        return self.call("GET", f"/api/companies/{company_id}/costs/quota-windows")

    def pause_agent(self, agent_id):
        return self.call("POST", f"/api/agents/{agent_id}/pause")

    def resume_agent(self, agent_id):
        return self.call("POST", f"/api/agents/{agent_id}/resume")

    # --- CLI wrappers (documented) --------------------------------------------------
    def wake_agent(self, agent_id, fresh=True, reason="clerk", issue_id=None):
        """POST /api/agents/{id}/wakeup (in the live OpenAPI spec). Returns True on success. With issue_id the
        agent is woken on that issue, as Paperclip does for an assignment."""
        body = {"source": "automation", "triggerDetail": "system", "reason": reason, "forceFreshSession": fresh}
        if issue_id:
            body.update(source="assignment", payload={"issueId": issue_id})
        try:
            self.call("POST", f"/api/agents/{agent_id}/wakeup", body)
            return True
        except ApiError:
            return False

    def export_company(self, company_id, out):
        return subprocess.run([self.cli, "company", "export", company_id, "--out", out],
                              capture_output=True, text=True, timeout=300).returncode == 0

    def issue_activity(self, issue_id):
        r = self.call("GET", f"/api/issues/{issue_id}/activity")
        if not isinstance(r, list):
            raise ValueError("Paperclip issue activity contract changed")
        return r

    def interactions(self, issue_id):
        r = self.call("GET", f"/api/issues/{issue_id}/interactions")
        if not isinstance(r, list):
            raise ValueError("Paperclip interaction list contract changed")
        return r
