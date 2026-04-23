"use client";

import { useEffect, useRef, useState } from "react";
import type { ReportState } from "./report-flow";
import { submitReport } from "@/lib/api";

declare global {
  interface Window {
    turnstile?: {
      render: (el: HTMLElement, opts: { sitekey: string; callback: (t: string) => void; "error-callback"?: () => void }) => string;
      reset: (id: string) => void;
    };
  }
}

export default function ReportModal({
  state, onCancel, onSubmitted,
}: { state: ReportState; onCancel: () => void; onSubmitted: (reference: string) => void }) {
  const [consent, setConsent] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const widgetRef = useRef<HTMLDivElement>(null);
  const widgetId = useRef<string | null>(null);

  useEffect(() => {
    function render() {
      if (!widgetRef.current || !window.turnstile) return;
      widgetId.current = window.turnstile.render(widgetRef.current, {
        sitekey: process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY ?? "",
        callback: (t) => setToken(t),
        "error-callback": () => setErr("Turnstile verification failed"),
      });
    }
    const existing = document.querySelector<HTMLScriptElement>("#turnstile-script");
    if (existing) { render(); return; }
    const s = document.createElement("script");
    s.id = "turnstile-script";
    s.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
    s.async = true;
    s.onload = render;
    document.head.appendChild(s);
  }, []);

  const submit = async () => {
    if (!consent || !token) return;
    setSubmitting(true);
    setErr(null);
    try {
      const result = await submitReport({
        reporter: { name: state.name, email: state.email, phone: state.phone, dob: state.dob, address: state.address },
        incident: { target_org: state.targetId, summary: state.summary, date: state.date, location: state.location },
        turnstile_token: token,
      });
      onSubmitted(result.reference);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Submission failed");
      if (widgetId.current && window.turnstile) window.turnstile.reset(widgetId.current);
      setToken(null);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-lg max-w-lg w-full p-6 space-y-3">
        <h2 className="text-lg font-semibold">Review and submit</h2>
        <dl className="text-sm space-y-1">
          <div><dt className="inline font-medium">Target:</dt> <dd className="inline">{state.targetId}</dd></div>
          <div><dt className="inline font-medium">Name:</dt> <dd className="inline">{state.name}</dd></div>
          <div><dt className="inline font-medium">Email:</dt> <dd className="inline">{state.email}</dd></div>
          {state.date && <div><dt className="inline font-medium">Date:</dt> <dd className="inline">{state.date}</dd></div>}
          <div><dt className="font-medium">Incident:</dt><dd className="whitespace-pre-wrap mt-1">{state.summary}</dd></div>
        </dl>
        <label className="flex items-start gap-2 text-xs">
          <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
          <span>I confirm the details above are accurate and I consent to sharing them with the selected organisation.</span>
        </label>
        <div ref={widgetRef} />
        {err && <div className="text-xs text-red-700">{err}</div>}
        <div className="flex justify-end gap-2 pt-2">
          <button className="px-3 py-1.5 text-sm text-gray-700" onClick={onCancel} disabled={submitting}>Cancel</button>
          <button className="px-3 py-1.5 text-sm bg-brand-900 text-white rounded disabled:opacity-50"
                  disabled={!consent || !token || submitting} onClick={submit}>
            {submitting ? "Submitting…" : "Submit report"}
          </button>
        </div>
      </div>
    </div>
  );
}
