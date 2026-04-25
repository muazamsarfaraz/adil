"use client";

import { useEffect, useRef, useState } from "react";
import type { ReportState } from "./report-flow";
import { submitReport } from "@/lib/api";

declare global {
  interface Window {
    turnstile?: {
      render: (
        el: HTMLElement,
        opts: { sitekey: string; callback: (t: string) => void; "error-callback"?: () => void; theme?: "light" | "dark" }
      ) => string;
      reset: (id: string) => void;
    };
  }
}

const TARGET_LABELS: Record<string, string> = {
  bmt: "British Muslim Trust",
  "police-uk": "Police UK",
  "police-scot": "Police Scotland",
  iru: "IRU — Islamophobia Response Unit",
  islamophobiaUK: "Islamophobia UK",
  eass: "EASS",
  "stop-hate-uk": "Stop Hate UK",
  tellmama: "Tell MAMA",
};

export default function ReportModal({
  state,
  onCancel,
  onSubmitted,
}: {
  state: ReportState;
  onCancel: () => void;
  onSubmitted: (reference: string) => void;
}) {
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
        theme: "light",
      });
    }
    const existing = document.querySelector<HTMLScriptElement>("#turnstile-script");
    if (existing) {
      render();
      return;
    }
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
        target: state.targetId,
        consent_confirmed: true,
        reporter: {
          first_name: state.first_name,
          surname: state.surname,
          email: state.email,
          phone: state.phone,
          address: state.address,
          gender: state.gender ?? "prefer_not_to_say",
          dob: {
            day: Number(state.dob_day ?? 0),
            month: Number(state.dob_month ?? 0),
            year: Number(state.dob_year ?? 0),
          },
        },
        incident: {
          details: state.details,
          location: state.location ?? "",
          date_time: state.date_time ?? "",
          role: "victim",
        },
        evidence_urls: [],
        turnstile_token: token,
      });
      const ref = result.reference_number ?? "(no reference returned)";
      onSubmitted(ref);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Submission failed");
      if (widgetId.current && window.turnstile) window.turnstile.reset(widgetId.current);
      setToken(null);
    } finally {
      setSubmitting(false);
    }
  };

  const targetLabel = TARGET_LABELS[state.targetId] ?? state.targetId;
  const canSubmit = consent && token && !submitting;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(15,62,41,0.55)", backdropFilter: "blur(4px)" }}
    >
      <div
        className="paper-card max-w-lg w-full p-7"
        style={{ background: "var(--color-paper)" }}
      >
        <div className="flex items-center gap-3 mb-4">
          <span
            className="font-ui text-[11px] uppercase"
            style={{ letterSpacing: "0.24em", color: "var(--color-gold)" }}
          >
            ❃ Review &amp; submit
          </span>
          <div
            className="flex-1 h-px"
            style={{
              background: "linear-gradient(to right, var(--color-gold) 0%, transparent 70%)",
              opacity: 0.5,
            }}
          />
        </div>

        <dl className="space-y-2 mb-5">
          {(
            [
              ["Target", targetLabel],
              ["Name", `${state.first_name} ${state.surname}`.trim()],
              ["Email", state.email],
              ...(state.location ? [["Where", state.location]] : []),
              ...(state.date_time ? [["When", state.date_time.replace("T", " ")]] : []),
            ] as [string, string][]
          ).map(([k, v]) => (
            <div key={k} className="flex gap-3">
              <dt
                className="font-ui text-[10px] uppercase"
                style={{ letterSpacing: "0.22em", color: "var(--color-emerald)", minWidth: 64, paddingTop: 4 }}
              >
                {k}
              </dt>
              <dd className="font-body" style={{ fontSize: 14, color: "var(--color-ink)" }}>
                {v}
              </dd>
            </div>
          ))}
          <div>
            <dt
              className="font-ui text-[10px] uppercase mb-1"
              style={{ letterSpacing: "0.22em", color: "var(--color-emerald)" }}
            >
              Incident
            </dt>
            <dd
              className="font-body whitespace-pre-wrap"
              style={{ fontSize: 14, lineHeight: 1.65, color: "var(--color-ink-soft)" }}
            >
              {state.details}
            </dd>
          </div>
        </dl>

        <label className="flex items-start gap-3 mb-4">
          <input
            type="checkbox"
            checked={consent}
            onChange={(e) => setConsent(e.target.checked)}
            style={{ marginTop: 4, accentColor: "var(--color-emerald)" }}
          />
          <span className="font-body" style={{ fontSize: 12, lineHeight: 1.55, color: "var(--color-ink-soft)" }}>
            I confirm the details above are accurate and I consent to sharing them with the selected organisation.
          </span>
        </label>

        <div ref={widgetRef} className="mb-3" />

        {err && (
          <div
            className="rounded-2xl px-3 py-2 mb-3 font-ui text-[12px]"
            style={{ background: "rgba(183,74,56,0.08)", border: "1px solid rgba(183,74,56,0.25)", color: "var(--color-rust)" }}
          >
            {err}
          </div>
        )}

        <div className="flex justify-end gap-3 pt-2">
          <button
            onClick={onCancel}
            disabled={submitting}
            className="font-ui transition-all"
            style={{
              padding: "9px 18px",
              borderRadius: 999,
              fontSize: 12,
              letterSpacing: "0.04em",
              background: "transparent",
              color: "var(--color-ink-soft)",
              border: "1px solid rgba(15,62,41,0.30)",
              cursor: submitting ? "not-allowed" : "pointer",
            }}
          >
            Cancel
          </button>
          <button
            onClick={submit}
            disabled={!canSubmit}
            className="font-ui transition-all"
            style={{
              padding: "9px 22px",
              borderRadius: 999,
              fontSize: 12,
              letterSpacing: "0.04em",
              fontWeight: 500,
              background: canSubmit ? "var(--color-ink)" : "rgba(15,62,41,0.2)",
              color: canSubmit ? "var(--color-paper)" : "rgba(244,238,220,0.6)",
              border: `1px solid ${canSubmit ? "var(--color-ink)" : "rgba(15,62,41,0.2)"}`,
              cursor: canSubmit ? "pointer" : "not-allowed",
            }}
            onMouseEnter={(e) => {
              if (canSubmit) {
                e.currentTarget.style.background = "var(--color-emerald)";
                e.currentTarget.style.borderColor = "var(--color-emerald)";
              }
            }}
            onMouseLeave={(e) => {
              if (canSubmit) {
                e.currentTarget.style.background = "var(--color-ink)";
                e.currentTarget.style.borderColor = "var(--color-ink)";
              }
            }}
          >
            {submitting ? "Submitting…" : "Submit report"}
          </button>
        </div>
      </div>
    </div>
  );
}
