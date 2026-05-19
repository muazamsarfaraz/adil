"""Rotate LLM API keys everywhere they're used.

Tracked vendors: Gemini, Anthropic, OpenAI, OpenRouter (used for DeepSeek
and other open models).

Usage:
    # Interactive — masked-paste each key when prompted
    python scripts/rotate_llm_keys.py

    # Bulk — drop every new key into a JSON file and run
    python scripts/rotate_llm_keys.py --keys-file scripts/.keys.local.json

    # Plan-only — show what would happen, write nothing
    python scripts/rotate_llm_keys.py --dry-run

    # Local-only — update .env files but skip Railway entirely
    python scripts/rotate_llm_keys.py --skip-railway

The `--keys-file` JSON shape — see `scripts/keys.template.json`:

    {
      "GEMINI_API_KEY":     "AIza...",
      "ANTHROPIC_API_KEY":  "sk-ant-...",
      "OPENAI_API_KEY":     "sk-proj-...",
      "OPENROUTER_API_KEY": "sk-or-v1-..."
    }

Keys present in the file skip the interactive prompt. Missing ones fall
back to masked prompts. After a successful rotation the script offers to
shred the file so the cleartext doesn't sit on disk.

What this DOES:
  - Scans the monorepo for .env files that reference any tracked LLM var.
  - Enumerates Railway services in the linked project and checks each
    for the same vars.
  - Loads new values from --keys-file (if provided) plus interactive
    masked prompts for any that weren't in the file.
  - Applies new values to every local .env and every Railway service
    that had the variable.
  - Prints a final "revoke OLD keys" checklist with provider console URLs.

What this does NOT do:
  - Generate keys (vendors don't expose that programmatically).
  - Revoke old keys (same reason — click revoke yourself in each console).
  - Restart Railway services (run `railway redeploy --service <name>`).
  - Touch local mailbox SMTP creds or any non-LLM secrets.

Pre-flight:
  - `railway login` and `railway link` to the right project.
  - You must be at the monorepo root or pass --root.

Safety:
  - .keys.local.json is in .gitignore — never commit it.
  - The script masks all key values in any printed output (fingerprint only).
  - After rotation, the script offers to shred the keys file.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

ROTATE_VARS = (
    "GEMINI_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
)

CONSOLE_URLS = {
    "GEMINI_API_KEY": "https://aistudio.google.com/apikey",
    "ANTHROPIC_API_KEY": "https://console.anthropic.com/settings/keys",
    "OPENAI_API_KEY": "https://platform.openai.com/api-keys",
    "OPENROUTER_API_KEY": "https://openrouter.ai/keys",
}


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


@dataclass
class EnvFileMatch:
    path: Path
    matched_vars: list[str] = field(default_factory=list)


def find_local_env_files(root: Path) -> list[EnvFileMatch]:
    """Walk `root` looking for any .env (NOT .env.example) that contains one
    of the rotate vars. Skips node_modules, .git, .venv, dist, build."""
    skip_dirs = {
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "dist",
        "build",
        "__pycache__",
        ".next",
        ".pytest_cache",
        "data",
    }
    matches: list[EnvFileMatch] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for fn in filenames:
            if fn != ".env":
                continue
            p = Path(dirpath) / fn
            try:
                text = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, PermissionError):
                continue
            matched = [v for v in ROTATE_VARS if re.search(rf"^{v}=", text, re.M)]
            if matched:
                matches.append(EnvFileMatch(path=p, matched_vars=matched))
    return matches


# ---------------------------------------------------------------------------
# Railway helpers
# ---------------------------------------------------------------------------


def railway_available() -> bool:
    return shutil.which("railway") is not None


def railway_list_services() -> list[str]:
    """Return service names from the currently linked Railway project.

    Uses `railway status --json`; falls back to empty list if it fails.
    """
    try:
        out = subprocess.run(
            ["railway", "status", "--json"],
            capture_output=True,
            text=True,
            check=True,
            timeout=20,
        ).stdout
        data = json.loads(out)
    except (subprocess.SubprocessError, json.JSONDecodeError, FileNotFoundError):
        return []
    # Railway's status JSON shape: { "name": str, "services": [...] }
    services = []
    for s in data.get("services", data.get("project", {}).get("services", [])):
        if isinstance(s, str):
            services.append(s)
        elif isinstance(s, dict) and s.get("name"):
            services.append(s["name"])
    return services


def railway_service_vars(service: str) -> dict[str, str]:
    """Return the env vars set on a Railway service. Empty on any failure."""
    try:
        out = subprocess.run(
            ["railway", "variables", "--service", service, "--kv"],
            capture_output=True,
            text=True,
            check=True,
            timeout=20,
        ).stdout
    except subprocess.SubprocessError:
        return {}
    pairs: dict[str, str] = {}
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            pairs[k.strip()] = v.strip()
    return pairs


def railway_set_var(service: str, key: str, value: str, dry_run: bool) -> bool:
    """Set a single var on a single service. Returns True on success."""
    cmd = ["railway", "variables", "--service", service, "--set", f"{key}={value}"]
    if dry_run:
        print(f"  [dry-run] {' '.join(cmd[:-1])} {key}=<NEW>")
        return True
    try:
        subprocess.run(cmd, check=True, timeout=30, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ERROR: railway set failed for {service}/{key}: {e.stderr.strip()[:200]}")
        return False


# ---------------------------------------------------------------------------
# .env file rewriting
# ---------------------------------------------------------------------------


def rewrite_env_file(path: Path, updates: dict[str, str], dry_run: bool) -> int:
    """Replace KEY=... lines in-place. Returns count of lines replaced."""
    text = path.read_text(encoding="utf-8")
    n = 0
    for key, val in updates.items():
        pattern = re.compile(rf"^{re.escape(key)}=.*$", re.M)
        new_text, count = pattern.subn(f"{key}={val}", text)
        if count:
            n += count
            text = new_text
    if n and not dry_run:
        path.write_text(text, encoding="utf-8")
    return n


# ---------------------------------------------------------------------------
# Key prompt
# ---------------------------------------------------------------------------


def fingerprint(value: str) -> str:
    """Safe representation of a secret — first 6 + last 4 chars only."""
    if not value:
        return "(empty)"
    if len(value) <= 12:
        return "(short)"
    return f"{value[:6]}…{value[-4:]}  (len={len(value)})"


def load_keys_file(path: Path) -> dict[str, str]:
    """Load a {VAR: value} JSON file. Drops empty / placeholder values."""
    if not path.exists():
        raise FileNotFoundError(f"keys file not found: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise SystemExit(f"{path} must be a JSON object, got {type(raw).__name__}")
    out: dict[str, str] = {}
    for k, v in raw.items():
        if k not in ROTATE_VARS:
            print(f"  WARN: ignoring unknown key {k} in {path}")
            continue
        if not isinstance(v, str):
            continue
        # Drop placeholders that look like templates.
        if not v.strip() or v.strip().startswith(("<", "PASTE", "TODO", "REPLACE")):
            continue
        out[k] = v.strip()
    return out


def prompt_for_new_keys(keys_needed: list[str], preloaded: dict[str, str] | None = None) -> dict[str, str]:
    """Interactive masked prompt for new values. Returns {var: value}.

    Keys already present in ``preloaded`` skip the prompt — useful with
    --keys-file. A fingerprint is shown for each preloaded value so you
    can sanity-check before applying.
    """
    preloaded = dict(preloaded or {})
    print()
    if preloaded:
        print(f"Loaded {len(preloaded)} key(s) from --keys-file:")
        for k in sorted(preloaded):
            print(f"  {k}: {fingerprint(preloaded[k])}")
        print()

    missing = [k for k in keys_needed if k not in preloaded]
    if not missing:
        return preloaded

    print("Generate new keys in each provider console FIRST, then paste here.")
    print("Input is masked — nothing will be echoed.\n")
    for k in missing:
        print(f"  {k}:  {CONSOLE_URLS[k]}")
    print()
    new_values: dict[str, str] = dict(preloaded)
    for k in missing:
        while True:
            v = getpass.getpass(f"New value for {k} (paste, then Enter): ").strip()
            if not v:
                print("  empty — try again")
                continue
            confirm = getpass.getpass(f"Confirm {k} (paste again): ").strip()
            if v != confirm:
                print("  mismatch — try again")
                continue
            new_values[k] = v
            print(f"  captured: {fingerprint(v)}")
            break
    return new_values


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Monorepo root to scan for .env files (default: parent of scripts/)",
    )
    ap.add_argument("--dry-run", action="store_true", help="Show plan but don't write anywhere")
    ap.add_argument("--skip-railway", action="store_true", help="Only update local .env files (skip Railway entirely)")
    ap.add_argument(
        "--keys-file",
        type=Path,
        default=None,
        help="JSON file with {VAR: value} for bulk rotation " "(skips the masked prompt for keys present in the file).",
    )
    args = ap.parse_args(argv)

    print(f"== rotate-llm-keys ==  root={args.root}  dry-run={args.dry_run}")

    # 1) Inventory: local .env
    print("\n[1/4] Scanning local .env files...")
    env_matches = find_local_env_files(args.root)
    for m in env_matches:
        rel = m.path.relative_to(args.root)
        print(f"  {rel}  -> {', '.join(m.matched_vars)}")
    if not env_matches:
        print("  (none found)")

    # 2) Inventory: Railway
    railway_targets: list[tuple[str, list[str]]] = []  # (service, [vars])
    if args.skip_railway:
        print("\n[2/4] Skipping Railway (--skip-railway)")
    elif not railway_available():
        print("\n[2/4] Railway CLI not on PATH — will skip Railway updates")
    else:
        print("\n[2/4] Querying Railway services...")
        services = railway_list_services()
        if not services:
            print("  ! could not enumerate Railway services. Run `railway link` first,")
            print("    or rerun with --skip-railway to do local-only.")
            return 2
        for svc in services:
            vars_set = railway_service_vars(svc)
            present = [v for v in ROTATE_VARS if v in vars_set]
            if present:
                railway_targets.append((svc, present))
                print(f"  {svc}: {', '.join(present)}")
            else:
                print(f"  {svc}: (no LLM vars)")

    # Determine which keys actually need rotating
    keys_needed = sorted(
        {v for m in env_matches for v in m.matched_vars} | {v for _, vs in railway_targets for v in vs}
    )
    if not keys_needed:
        print("\nNothing to rotate. Exiting.")
        return 0

    preloaded: dict[str, str] = {}
    if args.keys_file:
        preloaded = load_keys_file(args.keys_file)

    print(f"\n[3/4] Will rotate: {', '.join(keys_needed)}")
    if preloaded:
        print(f"      Preloaded from {args.keys_file}: {', '.join(sorted(preloaded))}")
    proceed = input("Proceed? (yes/no): ").strip().lower()
    if proceed not in {"yes", "y"}:
        print("Aborted.")
        return 1

    new_values = prompt_for_new_keys(keys_needed, preloaded=preloaded)

    # 4) Apply
    print("\n[4/4] Applying...")
    total_env_replacements = 0
    for m in env_matches:
        updates = {k: new_values[k] for k in m.matched_vars}
        n = rewrite_env_file(m.path, updates, args.dry_run)
        total_env_replacements += n
        print(f"  {m.path.relative_to(args.root)}: {n} line(s) {'would be ' if args.dry_run else ''}updated")

    railway_failures: list[tuple[str, str]] = []
    for svc, present_vars in railway_targets:
        for k in present_vars:
            ok = railway_set_var(svc, k, new_values[k], args.dry_run)
            if not ok:
                railway_failures.append((svc, k))
        print(f"  railway/{svc}: {len(present_vars)} var(s) {'would be ' if args.dry_run else ''}set")

    # 5) Revoke checklist
    print()
    print("=" * 70)
    print("REVOKE OLD KEYS — these vendors don't expose programmatic revoke:")
    print("=" * 70)
    for k in keys_needed:
        print(f"  [ ] {k}  ->  {CONSOLE_URLS[k]}")
        print(f"        new key fingerprint: {fingerprint(new_values[k])}")
    print()
    if railway_targets and not args.dry_run:
        print("After verifying new keys work, redeploy each affected service:")
        for svc, _ in railway_targets:
            print(f"  railway redeploy --service {svc}")
    if railway_failures:
        print()
        print(f"!! {len(railway_failures)} Railway update(s) failed — fix manually:")
        for svc, k in railway_failures:
            print(f"   railway variables --service {svc} --set {k}=<NEW>")
        return 1

    # Offer to shred the keys file so cleartext doesn't linger on disk.
    if args.keys_file and args.keys_file.exists() and not args.dry_run and not railway_failures:
        print()
        ans = input(f"Shred {args.keys_file}? (yes/no): ").strip().lower()
        if ans in {"yes", "y"}:
            # Overwrite with random bytes then unlink — best-effort shred on a
            # journalled filesystem. Good enough for a 5KB JSON.
            size = args.keys_file.stat().st_size
            args.keys_file.write_bytes(os.urandom(max(size, 64)))
            args.keys_file.unlink()
            print(f"  shredded {args.keys_file}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
