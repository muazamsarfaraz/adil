"use client";

import { useState } from "react";

const INPUT =
  "w-full font-body bg-[color:var(--color-paper)] border border-[color:var(--color-ink)]/25 rounded-lg px-3 py-2 text-[color:var(--color-ink)]";
const LABEL =
  "font-ui text-[12px] uppercase text-[color:var(--color-ink-faded)] block mb-1.5";

interface EditFields {
  telephone: string;
  contact_email: string;
  languages: string;
  areas: string;
  note: string;
}

export default function EditListingForm({ slug, email }: { slug: string; email: string }) {
  const [state, setState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [form, setForm] = useState<EditFields>({
    telephone: "",
    contact_email: "",
    languages: "",
    areas: "",
    note: "",
  });

  function set<K extends keyof EditFields>(k: K, v: string) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setState("saving");
    try {
      const r = await fetch("/api/listing/edit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sra_id: slug, ...form }),
      });
      setState(r.ok ? "saved" : "error");
    } catch {
      setState("error");
    }
  }

  return (
    <div className="space-y-6">
      <div className="paper-card p-4 flex items-center justify-between gap-3 flex-wrap">
        <span className="font-ui text-sm text-[color:var(--color-ink-soft)]">
          Signed in as <strong>{email}</strong> · SRA ID <strong>{slug}</strong>
        </span>
        <form action="/api/listing/logout" method="post">
          <button type="submit" className="btn-secondary text-sm">
            Sign out
          </button>
        </form>
      </div>

      {state === "saved" ? (
        <div className="paper-card p-6">
          <p className="font-body text-[color:var(--color-ink-soft)]">
            Thank you — your changes have been submitted to the AskAdil team for review and will appear on
            your listing once approved.
          </p>
        </div>
      ) : (
        <form onSubmit={submit} className="paper-card p-6 space-y-4">
          <p className="font-body text-[color:var(--color-ink-soft)]">
            Update your details below. Leave a field blank to keep it unchanged. Every change is reviewed by
            the AskAdil team before it goes live.
          </p>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block">
              <span className={LABEL}>Telephone</span>
              <input className={INPUT} value={form.telephone} onChange={(e) => set("telephone", e.target.value)} />
            </label>
            <label className="block">
              <span className={LABEL}>Contact email</span>
              <input className={INPUT} type="email" value={form.contact_email} onChange={(e) => set("contact_email", e.target.value)} />
            </label>
          </div>
          <label className="block">
            <span className={LABEL}>Languages spoken (comma-separated)</span>
            <input className={INPUT} value={form.languages} onChange={(e) => set("languages", e.target.value)} placeholder="Urdu, Arabic, Bengali" />
          </label>
          <label className="block">
            <span className={LABEL}>Practice areas (comma-separated)</span>
            <input className={INPUT} value={form.areas} onChange={(e) => set("areas", e.target.value)} placeholder="Immigration, Family, Employment" />
          </label>
          <label className="block">
            <span className={LABEL}>Note to the AskAdil team (optional)</span>
            <textarea className={INPUT} rows={3} value={form.note} onChange={(e) => set("note", e.target.value)} />
          </label>
          <button type="submit" className="btn-primary" disabled={state === "saving"}>
            {state === "saving" ? "Submitting…" : "Submit for review"}
          </button>
          {state === "error" && (
            <p className="font-body text-[color:var(--color-rust)]" role="alert">
              Couldn't submit. Please try again.
            </p>
          )}
        </form>
      )}
    </div>
  );
}
