# CLAUDE.md

Project-specific instructions for Claude Code sessions.

<!-- mailbox:claude-snippet:begin -->
## Email testing â€” `mailbox` service

A local docker-mailserver stack is available at `E:\dev\experiments\mailbox`
for integration testing of outbound engines and AI email conversations.
**Use it instead of mocks, MailHog, or hitting real SMTP providers** when
you need realistic SMTP+IMAP behaviour, multi-domain routing, or scale tests.

**Service manifest:** `E:\dev\.services\mailbox.json` (or repo-local
`E:\dev\experiments\mailbox\mailbox.service.json`)

**Endpoints (all `localhost`, self-signed cert â€” accept it in dev):**

| What | Port | TLS | Notes |
|---|---|---|---|
| SMTP submission (send) | 587 | STARTTLS | `<agent>@<domain>` / `agentpass` |
| IMAPS (read) | 993 | implicit | same creds |

**Default credentials:** one shared password `agentpass`, usernames are
`<agent_id>@<domain>` from `E:\dev\experiments\mailbox\sim.yaml`.
Add agents to `sim.yaml`, then run
`python E:\dev\experiments\mailbox\scripts\provision.py` and
`docker compose -f E:\dev\experiments\mailbox\compose.yml restart mailserver`.

**Before using:** verify the stack is up:
```powershell
docker inspect -f "{{.State.Health.Status}}" mailserver
# expected: healthy
```

**Watch conversations live:**
```powershell
python -m tui   # run from E:\dev\experiments\mailbox
```

**Full docs:**
- `E:\dev\experiments\mailbox\USAGE.md` â€” language/framework recipes
- `E:\dev\experiments\mailbox\SIMULATION.md` â€” multi-agent LangGraph harness

**Do not commit `agentpass` or any `<agent>@<domain>` address into prod
config.** This stack is local-only and routes nothing to the real internet.
<!-- mailbox:claude-snippet:end -->
