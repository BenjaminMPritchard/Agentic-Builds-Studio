"""Fake Paperclip API and fake Ollama for tests. Paths mirror lib/paperclip.py."""
import json
import re
import threading
import http.server


class Server:
    def __init__(self, handler_factory):
        self.srv = http.server.HTTPServer(("127.0.0.1", 0), handler_factory(self))
        self.url = f"http://127.0.0.1:{self.srv.server_port}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def stop(self):
        self.srv.shutdown()
        self.srv.server_close()


class FakePaperclip(Server):
    def __init__(self):
        self.issues, self.docs, self.comments, self.interactions_ = {}, {}, [], {}
        self.agents, self.runs_, self.patches, self.checkouts, self.wakes = [], [], [], [], []
        super().__init__(self._handler)

    def add(self, **i):
        self.issues[i["id"]] = i

    def _handler(self, fake):
        class H(http.server.BaseHTTPRequestHandler):
            def log_message(s, *a): pass

            def send(s, code, obj):
                s.send_response(code); s.end_headers(); s.wfile.write(json.dumps(obj).encode())

            def body(s):
                n = int(s.headers.get("Content-Length") or 0)
                return json.loads(s.rfile.read(n)) if n else {}

            def do_GET(s):
                p = s.path.split("?")[0]
                if re.fullmatch(r"/api/companies/\w+/issues", p): return s.send(200, {"issues": list(fake.issues.values())})
                if re.fullmatch(r"/api/companies/\w+/agents", p): return s.send(200, {"agents": fake.agents})
                if re.fullmatch(r"/api/companies/\w+/heartbeat-runs", p): return s.send(200, {"runs": fake.runs_})
                if re.fullmatch(r"/api/companies/\w+/costs/by-\w+", p): return s.send(200, {"total": 0})
                m = re.fullmatch(r"/api/issues/(\w+)/documents/(\w+)", p)
                if m:
                    d = fake.docs.get((m[1], m[2]))
                    return s.send(200, {"body": d}) if d is not None else s.send(404, {})
                m = re.fullmatch(r"/api/issues/(\w+)/interactions", p)
                if m: return s.send(200, {"interactions": fake.interactions_.get(m[1], [])})
                m = re.fullmatch(r"/api/issues/(\w+)/heartbeat-context", p)
                if m: return s.send(200, fake.issues.get(m[1], {}))
                s.send(404, {})

            def do_PUT(s):
                m = re.fullmatch(r"/api/issues/(\w+)/documents/(\w+)", s.path); b = s.body()
                if b.get("format") != "markdown" or "body" not in b: return s.send(400, {"error": "format+body required"})
                fake.docs[(m[1], m[2])] = b["body"]; s.send(200, {})

            def do_PATCH(s):
                m = re.fullmatch(r"/api/issues/(\w+)", s.path); b = s.body()
                fake.patches.append((m[1], b)); fake.issues[m[1]].update({k: v for k, v in b.items() if k != "comment"})
                s.send(200, {})

            def do_POST(s):
                b = s.body()
                m = re.fullmatch(r"/api/issues/(\w+)/comments", s.path)
                if m: fake.comments.append((m[1], b["body"])); return s.send(200, {})
                m = re.fullmatch(r"/api/issues/(\w+)/checkout", s.path)
                if m:
                    if "agentId" not in b or "expectedStatuses" not in b: return s.send(400, {"error": "agentId+expectedStatuses"})
                    if m[1] in fake.checkouts: return s.send(409, {"error": "taken"})
                    fake.checkouts.append(m[1]); return s.send(200, {})
                m = re.fullmatch(r"/api/agents/(\w+)/wakeup", s.path)
                if m:
                    if "forceFreshSession" not in b: return s.send(400, {"error": "forceFreshSession required"})
                    fake.wakes.append((m[1], b)); return s.send(200, {})
                s.send(404, {})
        return H


class FakeOllama(Server):
    """`answers` is a list of JSON strings returned in order (the last repeats)."""
    def __init__(self, answers):
        self.answers, self.requests = list(answers), []
        super().__init__(self._handler)

    def _handler(self, fake):
        class H(http.server.BaseHTTPRequestHandler):
            def log_message(s, *a): pass

            def do_POST(s):
                n = int(s.headers["Content-Length"]); req = json.loads(s.rfile.read(n)); fake.requests.append(req)
                a = fake.answers.pop(0) if len(fake.answers) > 1 else fake.answers[0]
                s.send_response(200); s.end_headers()
                s.wfile.write(json.dumps({"message": {"content": a}}).encode())
        return H
