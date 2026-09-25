"""Run a Worker job on Ollama, check the answer, retry once, cache the result."""
import hashlib
import json
import os
import urllib.request

from lib.schema import validate
from qwen.jobs import load_all

MAX_CTX = 8192


def ollama_chat(url, model, system, user, schema, num_ctx):
    body = {"model": model, "stream": False, "think": False, "format": schema,
            "options": {"temperature": 0, "num_ctx": num_ctx},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    req = urllib.request.Request(url.rstrip("/") + "/api/chat", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.load(r)["message"]["content"]


def cache_key(job, version, inp):
    return hashlib.sha256(json.dumps([job, version, inp], sort_keys=True).encode()).hexdigest()


def run_job(doc, url, model, cache_dir=None, enabled=None, jobs=None):
    """doc = {job, version?, input, requester?}. Returns {"status": "ok"|"needs_human", ...}.

    Fails safe: anything unexpected becomes needs_human, never a guess.
    """
    jobs = jobs or load_all()
    name, inp = doc.get("job"), doc.get("input")
    mod = jobs.get(name)
    if mod is None:
        return {"status": "needs_human", "errors": [f"unknown job {name!r}"]}
    if enabled is not None and name not in enabled:
        return {"status": "needs_human", "errors": [f"job {name} is not enabled (no passing golden set)"]}
    text = json.dumps(inp, ensure_ascii=False)
    if len(text) > mod.MAX_INPUT_CHARS:
        return {"status": "needs_human", "errors": [f"input is {len(text)} chars, max {mod.MAX_INPUT_CHARS}"]}
    key = cache_key(name, mod.VERSION, inp)
    path = os.path.join(cache_dir, key + ".json") if cache_dir else None
    if path and os.path.exists(path):
        with open(path) as f:
            return {**json.load(f), "cached": True}
    num_ctx = min(MAX_CTX, max(4096, (len(text) + len(mod.SYSTEM)) // 3 + 1024))
    errors, user = [], text
    for attempt in range(2):  # one retry, with the check errors
        if attempt:
            user = text + "\n\nYour previous answer failed these checks; fix them:\n- " + "\n- ".join(errors)
        try:
            raw = ollama_chat(url, model, mod.SYSTEM, user, mod.SCHEMA, num_ctx)
            out = json.loads(raw)
        except Exception as e:
            errors = [f"model call/parse failed: {e}"]
            continue
        errors = validate(out, mod.SCHEMA) or mod.check(inp if isinstance(inp, (dict, list)) else {"text": inp}, out)
        if not errors:
            res = {"status": "ok", "job": name, "version": mod.VERSION, "output": out}
            if path:
                os.makedirs(cache_dir, exist_ok=True)
                with open(path, "w") as f:
                    json.dump(res, f)
            return res
    return {"status": "needs_human", "job": name, "errors": errors}
