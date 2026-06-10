"""Soak v2: fresh campaign, distinct subject, replay-safe.

Differences from v1:
  - Subject embeds a slug suffix so ScriptedLLM treats it as a fresh
    thread (the per-(self,peer,subject_root) counter resets).
  - Wipes outreach@askadil.test INBOX before launching so stale
    bridge state can't contaminate.
"""

from __future__ import annotations

import asyncio
import os
import ssl
import time
from collections import Counter

import aioimaplib
import httpx

ROOT = os.path.dirname(__file__)
API_URL = "http://localhost:8001"
API_KEY = next(
    (
        line.split("=", 1)[1].strip()
        for line in open(os.path.join(ROOT, "..", ".env"), encoding="utf-8").read().splitlines()
        if line.startswith("API_KEY=")
    ),
    "",
)
SLUG = f"mailbox-soak-v2-{int(time.time())}"

CONTACTS = [
    ("partner-aisha", "interested"),
    ("partner-eshaan", "question"),
    ("partner-saira", "decline"),
    ("partner-tariq", "hostile"),
    ("partner-ghulam", "silent"),
    ("partner-ghost-soak2", "bounce"),
]

CAMPAIGN = {
    "name": "Mailbox soak v2",
    "slug": SLUG,
    "goal": "signup",
    "templates": {
        "initial": {
            "subject": f"[{SLUG}] AskAdil Directory invitation",
            "body": (
                "Assalamu Alaikum {{contact_name}},\n\n"
                "MCB AskAdil refers public-interest cases to UK Muslim "
                "solicitors. Reply if {{firm_name}} is interested in being listed.\n\n"
                "Thanks,\nAskAdil Team"
            ),
        }
    },
    "cadence": [{"day": 0, "action": "send_initial"}, {"day": 14, "action": "close"}],
    "llm_config": {
        "research": {"provider": "gemini", "model": "gemini-2.5-flash"},
        "compose": {"provider": "anthropic", "model": "claude-sonnet-4-6"},
        "classify": {"provider": "gemini", "model": "gemini-2.5-flash"},
    },
    "research_instructions": "skip",
    "compose_instructions": "use template as-is",
    "classify_instructions": (
        "Classify the reply as one of: interested (wants to learn more), "
        "declined (not interested or unsubscribe demand), question (asking for "
        "more info), out_of_office, bounce."
    ),
    "conversion_config": {"type": "signup", "signup_fields": []},
    "auto_send": False,
    "sender_name": "AskAdil Team",
    "sender_email": "outreach@askadil.test",
    "reply_to": "outreach@askadil.test",
}


async def wipe_inbox():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    imap = aioimaplib.IMAP4_SSL("localhost", 993, ssl_context=ctx)
    await imap.wait_hello_from_server()
    await imap.login("outreach@askadil.test", "agentpass")
    await imap.select("INBOX")
    status, data = await imap.search("ALL")
    if status == "OK" and data and data[0]:
        for uid in data[0].split():
            await imap.store(uid.decode(), "+FLAGS", "\\Deleted")
        await imap.expunge()
    await imap.logout()


def main() -> int:
    print(f"== mailbox full-loop v2 ==  slug={SLUG}")
    print("wiping outreach@askadil.test INBOX...")
    asyncio.run(wipe_inbox())

    with httpx.Client(
        base_url=API_URL, headers={"X-API-Key": API_KEY, "Content-Type": "application/json"}, timeout=30
    ) as c:
        r = c.post("/api/v1/outreach/campaigns", json=CAMPAIGN)
        r.raise_for_status()
        cid = r.json()["id"]
        print(f"  campaign {cid}")

        body = {
            "contacts": [
                {
                    "name": local.replace("partner-", "").title(),
                    "email": f"{local}@solicitors.test",
                    "firm_name": f"{local.replace('partner-','').title()} Solicitors",
                    "metadata": {"persona_kind": kind},
                }
                for local, kind in CONTACTS
            ]
        }
        c.post(f"/api/v1/outreach/campaigns/{cid}/contacts/bulk", json=body).raise_for_status()
        print(f"  added {len(CONTACTS)} contacts")

        r = c.post(f"/api/v1/outreach/campaigns/{cid}/launch")
        r.raise_for_status()
        print(f"  launched: {r.json().get('status')}")

        # Wait for drafts to be composed
        deadline = time.time() + 90
        while time.time() < deadline:
            time.sleep(5)
            cs = c.get(f"/api/v1/outreach/campaigns/{cid}/contacts?limit=100").json().get("items", [])
            if all(x["status"] == "draft_pending" for x in cs):
                print("  all 6 drafts composed")
                break

        for x in cs:
            c.post(f"/api/v1/outreach/contacts/{x['id']}/approve-draft").raise_for_status()
        print("  6 drafts approved -> sends enqueued")

        # Poll for terminal state
        last = ""
        for i in range(20):  # 2 min budget
            time.sleep(6)
            cs = c.get(f"/api/v1/outreach/campaigns/{cid}/contacts?limit=100").json().get("items", [])
            d = dict(Counter(x["status"] for x in cs))
            s = " ".join(f"{k}={v}" for k, v in sorted(d.items()))
            if s != last:
                print(f"  +{(i+1)*6}s  {s}")
                last = s
            terminal = {"replied", "converted", "declined", "bounced", "unresponsive"}
            if all(x["status"] in terminal for x in cs):
                print("  all contacts terminal")
                break

        print()
        print("=" * 64)
        print("FINAL STATE")
        print("=" * 64)
        for x in sorted(cs, key=lambda r: r["email"]):
            md = x.get("metadata") or {}
            print(f"  {x['email']:42s} kind={md.get('persona_kind','?'):10s} status={x['status']}")
        ctr = Counter(x["status"] for x in cs)
        print(f"\nstatus distribution: {dict(ctr)}")
        print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
