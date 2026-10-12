import json, os, tempfile, unittest
from tests.fakes import FakePaperclip
from lib.paperclip import Paperclip
from lib.clerk import Clerk
from lib import clerk as clerk_mod, notify, phone

REPO = "o/site"
HEAD = "a5ee36c0123456789abcdef0123456789abcdef0"


def pr(number=92, head=HEAD, checks=("SUCCESS",), comments=(), reviews=(), labels=(), title="Add a gate"):
    return {"number": number, "title": title, "headRefOid": head, "isDraft": False, "url": f"https://github.com/{REPO}/pull/{number}",
            "statusCheckRollup": [{"conclusion": c} for c in checks],
            "labels": [{"name": n} for n in labels], "reviews": list(reviews), "comments": list(comments)}


def said(body, login="abs-agents", at="2026-10-11T09:00:00Z"):
    return {"author": {"login": login}, "body": body, "createdAt": at}


class Plain(unittest.TestCase):
    def test_codes_are_removed(self):
        for raw, want in [("AGE-31 refurb 4/6: Public form and release evidence", "Refurb: Public form and release evidence"),
                          ("8L-H1 step 1: backend 1-hour hold, hard close", "Backend 1-hour hold, hard close"),
                          ("C4 Morning summary email", "Morning summary email"),
                          ("Add delivery approval and insurance gate (8L-A1 step 1)", "Add delivery approval and insurance gate"),
                          ("Review PR #95: IT support error emails", "IT support error emails"),
                          ("Plan 8L: legal compliance", "Plan: legal compliance")]:
            self.assertEqual(phone.plain(raw), want)


class Ready(unittest.TestCase):
    def test_an_approval_comment_naming_the_head_counts(self):
        # 2026-10-11: #92 and #89 were approved this way and Benjamin was never told.
        self.assertTrue(phone.ready_for_merge(pr(comments=[said(f"**Principal review: approved** at `{HEAD[:7]}`.")])))
        self.assertTrue(phone.ready_for_merge(pr(reviews=[{**said(f"Review round 1: approve. No blocking findings at `{HEAD}`."),
                                                           "state": "COMMENTED", "submittedAt": "2026-10-11T09:00:00Z"}])))

    def test_not_ready(self):
        ok = [said(f"Principal review: approved at {HEAD[:7]}")]
        self.assertFalse(phone.ready_for_merge(pr(comments=ok, checks=("FAILURE",))))
        self.assertFalse(phone.ready_for_merge(pr(comments=ok, checks=())))
        self.assertFalse(phone.ready_for_merge(pr(comments=[said("Principal review: approved at 1234567")])))  # old head
        self.assertFalse(phone.ready_for_merge(pr(comments=[said(f"Principal review: approved at {HEAD[:7]}", login="someone")])))
        later = said(f"Round 2: changes requested at {HEAD[:7]}", at="2026-10-11T10:00:00Z")
        self.assertFalse(phone.ready_for_merge(pr(comments=ok + [later])))

    def test_the_merge_gate_label_counts(self):
        self.assertTrue(phone.ready_for_merge(pr(labels=["ready-for-benjamin"])))


class TellBenjamin(unittest.TestCase):
    def setUp(self):
        self.fp = FakePaperclip()
        self.tmp = tempfile.TemporaryDirectory()
        self.pc = Paperclip(self.fp.url, "k")
        self._ledger, self._qdir = clerk_mod.QUOTA_LEDGER, clerk_mod.QUOTA_DIR
        clerk_mod.QUOTA_LEDGER = os.path.join(self.tmp.name, "none.json")
        self.pushed = []
        self._send = notify.send
        notify.send = lambda d, text, now=None, phone=False, title=None, click=None: self.pushed.append((title, text, click))
        self.prs = []

    def tearDown(self):
        notify.send = self._send
        clerk_mod.QUOTA_LEDGER = self._ledger
        self.fp.stop(); self.tmp.cleanup()

    def tick(self):
        c = Clerk(self.pc, "co", self.tmp.name, gh=lambda a: self.prs if a[:2] == ["pr", "list"] else None,
                  merge_policy=lambda: {"projects": {"p": {"repo": REPO}}}, now=lambda: 1_791_700_000)
        c.tell_benjamin(list(self.fp.issues.values()), dict(self.fp.issues))
        c.save()

    def test_merge_notice_names_the_work_and_what_waits_on_it_once_per_head(self):
        self.fp.add(id="gate", identifier="AGE-74", title="8L-A1 step 1: delivery-approval and insurance gate", status="done")
        self.fp.add(id="next", identifier="AGE-75", title="8L-A1 step 2: enforce the gate in checkout", status="blocked",
                    blockedByIssueIds=["gate"])
        self.fp.add(id="other", identifier="AGE-9", title="Unrelated", status="blocked")
        self.fp.products["gate"] = [{"type": "pull_request", "url": f"https://github.com/{REPO}/pull/92"}]
        self.prs = [pr(comments=[said(f"Principal review: approved at {HEAD[:7]}")]), pr(number=93)]
        self.tick(); self.tick()
        self.assertEqual(self.pushed, [("PR #92 is waiting for your merge",
                                        "Delivery-approval and insurance gate.\n\nBlocked until merged:\n- Enforce the gate in checkout",
                                        f"https://github.com/{REPO}/pull/92")])
        self.prs = [pr(head="b" * 40, comments=[said("Principal review: approved at bbbbbbb")])]
        self.tick()
        self.assertEqual(len(self.pushed), 2)  # a new head is a new notice

    def test_only_human_cards_that_are_not_merges_or_about_closed_prs(self):
        self.fp.add(id="t", identifier="AGE-44", title="Plan 8L: legal compliance", status="blocked")
        card = {"kind": "request_confirmation", "status": "pending", "resolverPolicy": "human_only", "payload": {}}
        self.fp.interactions_["t"] = [
            {**card, "id": "c1", "title": "Is the insurance policy number ready to enter?"},
            {**card, "id": "c2", "title": "Merge PR #92 (AGE-74 step 1) into main"},
            {**card, "id": "c3", "title": "AGE-51: resolve stuck review stage", "resolverPolicy": "anyone"},
            {**card, "id": "c4", "title": "Decide what follows PR #92"},
            {**card, "id": "c5", "title": "Old question", "status": "accepted"},
        ]
        self.tick(); self.tick()
        self.assertEqual([p[:2] for p in self.pushed], [
            ("Decision needed", "Is the insurance policy number ready to enter?\n\nAnswer it in Paperclip, on: Plan: legal compliance")])


class Notify(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = os.path.join(self.tmp.name, "notify.json")
        json.dump({"ntfy_url": "https://example.invalid/t", "paperclip_url": "http://host:3100/"}, open(self.cfg, "w"))
        self.pushed = []

    def tearDown(self):
        self.tmp.cleanup()

    def push(self, cfg, text, title, click):
        self.pushed.append((title, text, click))
        return True

    def test_only_phone_notices_are_pushed_at_once_even_at_night(self):
        d = self.tmp.name
        night = 1_791_770_400  # 2026-10-12 03:00 BST
        self.assertEqual(notify.send(d, "cap paused", night, self.cfg, self.push), "logged")
        self.assertEqual(notify.send(d, "body", night, self.cfg, self.push, phone=True, title="T", click="u"), "sent")
        self.assertEqual(self.pushed, [("T", "body", "u")])
        self.assertEqual(len(open(os.path.join(d, "log", "notify.jsonl")).readlines()), 2)

    def test_a_failed_phone_notice_is_retried(self):
        d = self.tmp.name

        def broken(*a):
            raise OSError("down")
        self.assertEqual(notify.send(d, "b", 0, self.cfg, broken, phone=True, title="T"), "failed")
        self.assertFalse(notify.flush(d, 0, self.cfg, broken))
        self.assertTrue(notify.flush(d, 0, self.cfg, self.push))
        self.assertEqual(self.pushed, [("T", "b", None)])
        self.assertTrue(notify.flush(d, 0, self.cfg, self.push))
        self.assertEqual(len(self.pushed), 1)

    def test_paperclip_link(self):
        self.assertEqual(notify.link("/AGE/issues/AGE-1", self.cfg), "http://host:3100/AGE/issues/AGE-1")
        self.assertIsNone(notify.link("/x", os.path.join(self.tmp.name, "none.json")))
