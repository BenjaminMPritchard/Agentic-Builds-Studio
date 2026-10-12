"""What reaches Benjamin's phone, worded for him (Benjamin, 2026-10-12): a PR waiting for his merge, with the work
waiting on it; a decision only he can make; and the Studio being down (bin/studio-watchdog). No task codes.

Pure functions; the Clerk's `tell_benjamin` step reads GitHub and Paperclip and sends with lib/notify.py.
"""
import re

GREEN = {"SUCCESS", "SKIPPED", "NEUTRAL"}
VERDICT_AUTHORS = {"abs-agents", "abs-agents[bot]", "abs-reviewer", "abs-reviewer[bot]"}  # the agents' GitHub identities
READY_LABEL = "ready-for-benjamin"

_CODES = [
    re.compile(r"^\s*review pr #\d+(?: round \d+)?:\s*", re.I),   # "Review PR #90 round 2: ..."
    re.compile(r"\bAGE-\d+\b:?"),                                  # Paperclip identifiers
    re.compile(r"\(\s*\d+[A-Z]+-[A-Z]+\d+(?: step \d+)?\s*\)"),    # "(8L-A1 step 1)"
    re.compile(r"\b\d+[A-Z]+-[A-Z]+\d+(?: step \d+)?\b:?"),         # "8L-H1 step 1:"
    re.compile(r"\b\d+[a-z]?-[a-z]+-\d+\b:?"),                      # "7-sec-2:"
    re.compile(r"^\s*[A-Z]\d+\b:?"),                                # "C4 Morning summary email"
    re.compile(r"\b(\d+)/(\d+)\b"),                                 # "refurb 4/6"
    re.compile(r"\b\d+[A-Z]{1,2}\b"),                                # "Plan 8L: ..."
]


def plain(title):
    """A task or PR title without the Studio's codes: "AGE-31 refurb 4/6: Public form" -> "Refurb: Public form"."""
    t = title or ""
    for rx in _CODES:
        t = rx.sub("", t)
    t = re.sub(r"\s+:", ":", re.sub(r"\s{2,}", " ", t)).strip(" :-,")
    t = re.sub(r"^(\w+):\s*:", r"\1:", t)
    return (t[:1].upper() + t[1:]) if t else (title or "").strip()


def checks_green(pr):
    checks = pr.get("statusCheckRollup") or []
    return bool(checks) and all((c.get("conclusion") or c.get("state") or "") in GREEN for c in checks)


def _verdict(body):
    """'approve', 'changes' or None, from the first line of a reviewer's comment or review."""
    first = next((line for line in (body or "").splitlines() if line.strip()), "").lower()
    if re.search(r"changes requested|request(?:ing)? changes|not approv", first):
        return "changes"
    if re.search(r"\bapprov", first):
        return "approve"
    return None


def approved_at_head(pr):
    """True when the newest verdict naming the PR's head commit approves it. GitHub will not let the agents'
    identity approve its own PR, so the Principal posts its verdict as a comment or COMMENTED review; a real
    APPROVED review at the head counts too."""
    head = pr.get("headRefOid") or ""
    if len(head) < 7:
        return False
    found = []
    for r in pr.get("reviews") or []:
        sha = ((r.get("commit") or {}).get("oid") or "")
        if r.get("state") == "APPROVED" and sha == head:
            found.append((r.get("submittedAt") or "", "approve"))
        elif r.get("state") == "CHANGES_REQUESTED" and sha == head:
            found.append((r.get("submittedAt") or "", "changes"))
    for c in list(pr.get("reviews") or []) + list(pr.get("comments") or []):
        if ((c.get("author") or {}).get("login") or "") not in VERDICT_AUTHORS or head[:7] not in (c.get("body") or ""):
            continue
        v = _verdict(c.get("body"))
        if v:
            found.append((c.get("submittedAt") or c.get("createdAt") or "", v))
    return bool(found) and sorted(found)[-1][1] == "approve"


def ready_for_merge(pr):
    labels = {(l or {}).get("name") for l in pr.get("labels") or []}
    return (not pr.get("isDraft") and checks_green(pr)
            and (READY_LABEL in labels or approved_at_head(pr)))


def merge_notice(number, what, blocked):
    """(title, text) for a PR waiting for Benjamin's merge."""
    lines = [what.rstrip(".") + "."]
    if blocked:
        lines += ["", "Blocked until merged:"] + [f"- {b}" for b in blocked[:6]]
        if len(blocked) > 6:
            lines.append(f"- and {len(blocked) - 6} more")
    return f"PR #{number} is waiting for your merge", "\n".join(lines)


def card_notice(card_title, task_title):
    """(title, text) for a decision only Benjamin can make."""
    text = plain(card_title).rstrip("?.") + "?" if card_title.strip().endswith("?") else plain(card_title)
    return "Decision needed", f"{text}\n\nAnswer it in Paperclip, on: {plain(task_title)}"


def merge_card(card):
    """Cards asking Benjamin to merge duplicate the merge notice, so they are not sent."""
    return bool(re.match(r"\s*merge\b", card.get("title") or "", re.I))


def human_card(card):
    return (card.get("status") == "pending"
            and "human_only" in (card.get("effectiveResolverPolicy"), card.get("resolverPolicy")))


def prs_named(card):
    text = (card.get("title") or "") + " " + str((card.get("payload") or {}).get("prompt") or "")
    return sorted({int(n) for n in re.findall(r"PR #(\d+)", text)})
