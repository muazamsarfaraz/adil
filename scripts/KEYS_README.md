# LLM key rotation workflow

One script rotates every LLM API key across every place we use it:
local `.env` files in the monorepo + every Railway service that has it set.

## Bulk workflow (recommended)

1. **Generate new keys** in each provider console:
   - Gemini: https://aistudio.google.com/apikey
   - Anthropic: https://console.anthropic.com/settings/keys
   - OpenAI: https://platform.openai.com/api-keys
   - OpenRouter: https://openrouter.ai/keys
2. **Copy the template** and paste the new values:
   ```powershell
   Copy-Item scripts/keys.template.json scripts/.keys.local.json
   notepad scripts/.keys.local.json
   ```
   `.keys.local.json` is gitignored — never check it in.
3. **Dry-run** to see what would change without writing anything:
   ```powershell
   python scripts/rotate_llm_keys.py --keys-file scripts/.keys.local.json --dry-run
   ```
4. **Apply for real**:
   ```powershell
   python scripts/rotate_llm_keys.py --keys-file scripts/.keys.local.json
   ```
   The script offers to shred `.keys.local.json` at the end so cleartext
   doesn't linger.
5. **Redeploy each Railway service the script touched** (it prints the commands).
6. **Revoke the OLD keys** in each provider console (the script prints the URLs).

## Interactive workflow

If you'd rather paste each key one at a time without a file:
```powershell
python scripts/rotate_llm_keys.py
```
The script masks each prompt and asks for confirmation per key.

## Other flags

- `--skip-railway` — only touch local `.env` files
- `--dry-run` — show plan, write nothing
- `--root <path>` — scan a different monorepo root

## What the script does NOT do

- Generate keys (vendors don't expose that programmatically).
- Revoke old keys (same reason — click revoke yourself in each console).
- Restart Railway services. After rotation, run
  `railway redeploy --service <name>` for each service the script printed.
- Touch local mailbox SMTP creds or any non-LLM secrets.

## Provisioning a NEW key (not rotating)

If a key wasn't previously set anywhere — say you're adding
`OPENROUTER_API_KEY` for the first time — the rotation script won't find
anything to update. Add it directly:
```powershell
railway variables --service adil-rag-api --set OPENROUTER_API_KEY=sk-or-v1-...
```
Then add it to whatever local `.env` you use and re-run rotation next cycle.
