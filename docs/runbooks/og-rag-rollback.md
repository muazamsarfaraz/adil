# OG-RAG → FST Emergency Rollback

**Owner:** rag-api on-call
**Mean time to rollback:** ~2 minutes
**Last verified:** P11 standby cutover (2026-05-19)

This runbook reverts production `adil-rag-api` from the OG-RAG (pgvector) retrieval
backend to the legacy Gemini File Search Tool (FST) backend. It is intended for the
P11 hot-standby week and for any future incident in which OG-RAG retrieval quality,
latency, or availability regresses.

The cutover is governed by a **single environment variable**: `RAG_BACKEND`.
`rag_service.py` reads it on every query (see commit 2973f48); no code change or
schema migration is required to switch.

| `RAG_BACKEND` value | Backend used |
| ------------------- | ------------ |
| `fst` (default, also when unset) | Gemini File Search Tool — legacy path |
| `ograg`             | pgvector + ontology retrieval (`ograg.backend.answer`) |

During P11, **FST is kept warm**: the `upload_pending` arq task in
`adil-document-uploader-worker` continues dual-writing newly ingested judgments to
the FST store, so the FST corpus stays current. This is what makes a sub-2-minute
rollback safe — FST is not a stale snapshot.

---

## When to roll back

Roll back immediately if **any** of the following is observed during the standby
week (or afterwards):

1. **Harmfulness veto fires** on the daily eval (any answer that materially
   misleads on UK discrimination law).
2. **Quality complaint surfaced via MSentry** that reproduces and points at a
   retrieval/grounding failure, not a generation glitch.
3. **P95 query latency** sustained > 2× FST baseline
   (`adil-rag-api/evals/fst_baseline.json`) for > 15 minutes.
4. **Error rate** on `/api/chat` > 1% sustained for > 5 minutes and traced to
   the `ograg.backend.answer` path.
5. **Eval pass rate** drops below 8/10 on the daily 10-query lighter eval.

When in doubt, **roll back first, debug second**. The FST path is the known-good
baseline; recovering quality matters more than diagnosing live.

---

## Rollback procedure

### One-command rollback

```bash
railway variables --service adil-rag-api --set RAG_BACKEND=fst \
  && railway redeploy --service adil-rag-api --yes
```

Run from the repo root (`E:\dev\AskAdil\adil` on the maintainer's machine, or any
machine linked to Railway project `3b3ce312-40a1-4fba-9367-6e2939ce4404`).

### Step-by-step (if the one-liner fails)

1. **Confirm Railway link** — should already be linked, but verify:
   ```bash
   railway status
   ```
   Expected project: `_mcb_project-adil` (id
   `3b3ce312-40a1-4fba-9367-6e2939ce4404`). If not linked:
   ```bash
   railway link --project 3b3ce312-40a1-4fba-9367-6e2939ce4404
   ```

2. **Flip the variable:**
   ```bash
   railway variables --service adil-rag-api --set RAG_BACKEND=fst
   ```

3. **Trigger a redeploy** (the variable change alone does not restart the
   running container):
   ```bash
   railway redeploy --service adil-rag-api --yes
   ```
   Service id: `2f4a5050-3d4f-46ca-9b0f-29802d04abe3`.

4. **Verify the active backend.** Hit the health/diag endpoint or any chat
   query; check the response metadata or container logs for the FST code path.
   The first user-facing query under `RAG_BACKEND=fst` should not hit
   `ograg.backend.answer`.

5. **Announce in MSentry** that production is back on FST and OG-RAG is paused
   pending RCA.

### Acceptance — rollback is complete when

- [ ] `railway variables --service adil-rag-api | grep RAG_BACKEND` shows `fst`.
- [ ] New deployment is `SUCCESS` in Railway dashboard.
- [ ] A live `/api/chat` query returns a coherent answer with FST citations.
- [ ] MSentry posted with rollback timestamp + suspected cause.

---

## After rollback

1. **Leave FST running** — do not re-enable `RAG_BACKEND=ograg` until root cause
   is understood and an eval re-run passes 8/10 against the failing query set.
2. **Capture the failing inputs.** Pull the offending queries from
   `adil-rag-api` logs and add them to
   `adil-rag-api/evals/queries_seed.jsonl` so the next eval pass catches the
   same regression.
3. **Do not roll forward by toggling back.** Treat the next OG-RAG enable as a
   fresh cutover: re-run the full P9 eval gate, then return to P10 standby
   semantics (this runbook is the safety net for that retry, too).
4. **Update the P11 standby clock.** The 7-day clean window resets on any
   rollback.

---

## Why this works in ~2 minutes

- **No data migration.** Both backends read from datastores that are populated
  independently and continuously — FST via the existing `upload_pending` arq
  task in `adil-document-uploader-worker`, OG-RAG via the ontology tables in
  `adil-rag-api`'s Postgres.
- **No schema change.** `RAG_BACKEND` is read at query time
  (`rag_service.py:950`); flipping it is a pure dispatch change.
- **Single service, single var.** Only `adil-rag-api` needs to restart. The
  frontend, the report bridge, and the uploader worker are untouched.

The bottleneck is the Railway deploy itself (~60–90 s for container restart),
not anything OG-RAG-specific. If Railway is degraded, see escalation below.

---

## Escalation

- **Railway control plane is down → cannot redeploy:**
  Use the Railway dashboard to set `RAG_BACKEND=fst` and trigger a manual
  restart. If that also fails, scale `adil-rag-api` to 0 replicas to take it
  offline; the frontend will show its standard chat-unavailable state, which is
  preferable to serving regressed answers.
- **FST store is also unhealthy:** unlikely (it has been read-only stable since
  long before OG-RAG work began), but if so, page on `FILE_SEARCH_STORE_ID` —
  it lives on Google's side, not Railway.
- **Cannot reach the on-call:** flip via Railway dashboard, then notify in
  MSentry. The runbook is intentionally one-step so anyone with Railway access
  can execute it.

---

## Related

- Migration design: [`docs/superpowers/specs/2026-05-19-og-rag-migration-design.md`](../superpowers/specs/2026-05-19-og-rag-migration-design.md)
- Foundation plan: [`docs/superpowers/plans/2026-05-19-og-rag-foundation.md`](../superpowers/plans/2026-05-19-og-rag-foundation.md)
- Parent ClickUp (full phase plan): [869dbq5bk](https://app.clickup.com/t/869dbq5bk)
- P11 task (this runbook): [869dbqa7k](https://app.clickup.com/t/869dbqa7k)
- P12 (FST teardown — *do not run while this runbook is needed*): see parent
  ClickUp; FST writes must stop only after P11 is declared clean.
