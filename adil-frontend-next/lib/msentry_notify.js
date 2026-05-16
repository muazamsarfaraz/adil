/**
 * MSentry feedback helper — drop into any Node project (Node 18+).
 *
 * Usage:
 *   const { notify } = require('./msentry_notify');
 *   notify('info',  'deploy', 'v1.2.3 deployed', { commit: 'abc123' });
 *   notify('error', 'alert',  `DB failed: ${err.message}`);
 *
 * Required env vars:
 *   MSENTRY_FEEDBACK_URL     e.g. https://cc-monitor-production.up.railway.app/feedback
 *   MSENTRY_FEEDBACK_SECRET  shared secret
 *   MSENTRY_PROJECT          project slug (defaults to basename of cwd)
 *
 * Never blocks the caller. Never throws.
 */
const path = require('node:path');

const VALID = new Set(['info', 'warn', 'error', 'critical']);
const TIMEOUT_MS = parseInt(process.env.MSENTRY_TIMEOUT_MS || '3000', 10);

function _config() {
  const url = process.env.MSENTRY_FEEDBACK_URL;
  const secret = process.env.MSENTRY_FEEDBACK_SECRET;
  const project = process.env.MSENTRY_PROJECT || path.basename(process.cwd());
  if (!url || !secret) return null;
  return { url, secret, project };
}

function notify(severity, kind, message, context = {}) {
  if (!VALID.has(severity)) {
    console.warn(`[msentry] invalid severity: ${severity}`);
    return;
  }
  const cfg = _config();
  if (!cfg) return;          // silently no-op when unconfigured

  const cleanCtx = {};
  for (const [k, v] of Object.entries(context)) {
    if (v !== null && v !== undefined) cleanCtx[k] = v;
  }

  const payload = {
    secret: cfg.secret,
    project: cfg.project,
    severity,
    kind,
    message: String(message).slice(0, 2000),
    context: cleanCtx,
  };

  // Fire-and-forget. AbortController for timeout. Errors swallowed.
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);

  fetch(cfg.url, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload),
    signal: ctrl.signal,
  })
    .catch(err => console.warn(`[msentry] feedback failed: ${err.message}`))
    .finally(() => clearTimeout(timer));
}

module.exports = { notify };
