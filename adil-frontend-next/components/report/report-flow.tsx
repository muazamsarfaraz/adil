"use client";

import { useState } from "react";
import ReportTargetPicker from "./report-target-picker";
import ReportModal from "./report-modal";

export interface ReportState {
  targetId: string;
  first_name: string;
  surname: string;
  email: string;
  phone?: string;
  dob_day?: string;
  dob_month?: string;
  dob_year?: string;
  gender?: string;
  address?: string;
  details: string;
  date_time?: string;
  location?: string;
}

type Step = "pick_target" | "collect_details" | "review";

const inputBase: React.CSSProperties = {
  width: "100%",
  marginTop: 6,
  padding: "10px 12px",
  borderRadius: 10,
  border: "1px solid rgba(15,62,41,0.20)",
  background: "var(--color-paper)",
  color: "var(--color-ink)",
  fontFamily: "var(--font-body)",
  fontSize: 14,
  outline: "none",
};

function FieldLabel({ children, optional }: { children: React.ReactNode; optional?: boolean }) {
  return (
    <span
      className="font-ui text-[10px] uppercase"
      style={{ letterSpacing: "0.22em", color: "var(--color-emerald)" }}
    >
      {children}
      {optional && <span style={{ color: "var(--color-ink-faded)", marginLeft: 6, letterSpacing: 0 }}>(optional)</span>}
    </span>
  );
}

function focusBlur(e: React.FocusEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>, focused: boolean) {
  e.currentTarget.style.borderColor = focused ? "var(--color-gold)" : "rgba(15,62,41,0.20)";
}

export default function ReportFlow({ onComplete }: { onComplete: (reference: string) => void }) {
  const [step, setStep] = useState<Step>("pick_target");
  const [state, setState] = useState<ReportState>({
    targetId: "",
    first_name: "",
    surname: "",
    email: "",
    details: "",
  });

  const set = <K extends keyof ReportState>(key: K, value: ReportState[K]) =>
    setState((prev) => ({ ...prev, [key]: value }));

  if (step === "pick_target") {
    return (
      <div className="paper-card p-6 my-6 max-w-3xl mx-auto">
        <div className="flex items-center gap-3 mb-4">
          <span
            className="font-ui text-[11px] uppercase"
            style={{ letterSpacing: "0.24em", color: "var(--color-gold)" }}
          >
            ❃ Submit a report
          </span>
          <div
            className="flex-1 h-px"
            style={{ background: "linear-gradient(to right, var(--color-gold) 0%, transparent 70%)", opacity: 0.5 }}
          />
        </div>
        <p
          className="font-body mb-1"
          style={{ fontSize: 15, lineHeight: 1.6, color: "var(--color-ink-soft)" }}
        >
          Where would you like to submit your report?
        </p>
        <ReportTargetPicker
          onSelect={(id) => {
            set("targetId", id);
            setStep("collect_details");
          }}
        />
      </div>
    );
  }

  if (step === "collect_details") {
    const dobValid =
      state.dob_day &&
      state.dob_month &&
      state.dob_year &&
      Number(state.dob_day) >= 1 &&
      Number(state.dob_day) <= 31 &&
      Number(state.dob_month) >= 1 &&
      Number(state.dob_month) <= 12;
    const canContinue =
      state.first_name &&
      state.surname &&
      state.email &&
      state.gender &&
      dobValid &&
      state.location &&
      state.date_time &&
      state.details.length >= 10;

    return (
      <div className="paper-card p-6 md:p-7 my-6 max-w-3xl mx-auto">
        <div className="flex items-center gap-3 mb-4">
          <span
            className="font-ui text-[11px] uppercase"
            style={{ letterSpacing: "0.24em", color: "var(--color-gold)" }}
          >
            ❃ Incident details
          </span>
          <div
            className="flex-1 h-px"
            style={{ background: "linear-gradient(to right, var(--color-gold) 0%, transparent 70%)", opacity: 0.5 }}
          />
        </div>
        <p
          className="font-body italic mb-5"
          style={{ fontSize: 13, color: "var(--color-ink-faded)" }}
        >
          Kept private — never sent to the AI assistant. Required by the receiving organisation's intake form.
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-5 gap-y-4">
          <label className="block">
            <FieldLabel>First name</FieldLabel>
            <input style={inputBase} value={state.first_name} onChange={(e) => set("first_name", e.target.value)} onFocus={(e) => focusBlur(e, true)} onBlur={(e) => focusBlur(e, false)} />
          </label>
          <label className="block">
            <FieldLabel>Surname</FieldLabel>
            <input style={inputBase} value={state.surname} onChange={(e) => set("surname", e.target.value)} onFocus={(e) => focusBlur(e, true)} onBlur={(e) => focusBlur(e, false)} />
          </label>

          <div className="block">
            <FieldLabel>Date of birth</FieldLabel>
            <div className="grid grid-cols-3 gap-2 mt-1.5">
              <input placeholder="DD" inputMode="numeric" maxLength={2} style={inputBase} value={state.dob_day ?? ""} onChange={(e) => set("dob_day", e.target.value)} onFocus={(e) => focusBlur(e, true)} onBlur={(e) => focusBlur(e, false)} />
              <input placeholder="MM" inputMode="numeric" maxLength={2} style={inputBase} value={state.dob_month ?? ""} onChange={(e) => set("dob_month", e.target.value)} onFocus={(e) => focusBlur(e, true)} onBlur={(e) => focusBlur(e, false)} />
              <input placeholder="YYYY" inputMode="numeric" maxLength={4} style={inputBase} value={state.dob_year ?? ""} onChange={(e) => set("dob_year", e.target.value)} onFocus={(e) => focusBlur(e, true)} onBlur={(e) => focusBlur(e, false)} />
            </div>
          </div>
          <label className="block">
            <FieldLabel>Gender</FieldLabel>
            <select style={{ ...inputBase, marginTop: 6 }} value={state.gender ?? ""} onChange={(e) => set("gender", e.target.value)} onFocus={(e) => focusBlur(e, true)} onBlur={(e) => focusBlur(e, false)}>
              <option value="">Select…</option>
              <option value="female">Female</option>
              <option value="male">Male</option>
              <option value="non_binary">Non-binary</option>
              <option value="prefer_not_to_say">Prefer not to say</option>
            </select>
          </label>

          <label className="block sm:col-span-2">
            <FieldLabel>Email</FieldLabel>
            <input type="email" style={inputBase} value={state.email} onChange={(e) => set("email", e.target.value)} onFocus={(e) => focusBlur(e, true)} onBlur={(e) => focusBlur(e, false)} />
          </label>

          <label className="block">
            <FieldLabel>Phone</FieldLabel>
            <input type="tel" style={inputBase} value={state.phone ?? ""} onChange={(e) => set("phone", e.target.value)} onFocus={(e) => focusBlur(e, true)} onBlur={(e) => focusBlur(e, false)} />
          </label>
          <label className="block">
            <FieldLabel>Postcode / address</FieldLabel>
            <input style={inputBase} value={state.address ?? ""} onChange={(e) => set("address", e.target.value)} onFocus={(e) => focusBlur(e, true)} onBlur={(e) => focusBlur(e, false)} />
          </label>

          <label className="block sm:col-span-2">
            <FieldLabel>Where did the incident take place?</FieldLabel>
            <input placeholder="e.g. Camden High Street, London NW1 / online — Twitter" style={inputBase} value={state.location ?? ""} onChange={(e) => set("location", e.target.value)} onFocus={(e) => focusBlur(e, true)} onBlur={(e) => focusBlur(e, false)} />
          </label>

          <label className="block sm:col-span-2">
            <FieldLabel>When did it happen?</FieldLabel>
            <input type="datetime-local" style={inputBase} value={state.date_time ?? ""} onChange={(e) => set("date_time", e.target.value)} onFocus={(e) => focusBlur(e, true)} onBlur={(e) => focusBlur(e, false)} />
          </label>

          <label className="block sm:col-span-2">
            <FieldLabel>What happened?</FieldLabel>
            <textarea
              rows={5}
              style={{ ...inputBase, resize: "vertical", lineHeight: 1.6 }}
              value={state.details}
              onChange={(e) => set("details", e.target.value)}
              onFocus={(e) => focusBlur(e, true)}
              onBlur={(e) => focusBlur(e, false)}
            />
          </label>
        </div>

        <div className="flex justify-end mt-6">
          <button
            disabled={!canContinue}
            onClick={() => setStep("review")}
            className="font-ui transition-all"
            style={{
              padding: "10px 22px",
              borderRadius: 999,
              fontSize: 13,
              letterSpacing: "0.04em",
              fontWeight: 500,
              background: canContinue ? "var(--color-ink)" : "rgba(15,62,41,0.2)",
              color: canContinue ? "var(--color-paper)" : "rgba(244,238,220,0.6)",
              border: `1px solid ${canContinue ? "var(--color-ink)" : "rgba(15,62,41,0.2)"}`,
              cursor: canContinue ? "pointer" : "not-allowed",
            }}
            onMouseEnter={(e) => {
              if (canContinue) {
                e.currentTarget.style.background = "var(--color-emerald)";
                e.currentTarget.style.borderColor = "var(--color-emerald)";
              }
            }}
            onMouseLeave={(e) => {
              if (canContinue) {
                e.currentTarget.style.background = "var(--color-ink)";
                e.currentTarget.style.borderColor = "var(--color-ink)";
              }
            }}
          >
            Review &amp; submit →
          </button>
        </div>
      </div>
    );
  }

  return (
    <ReportModal
      state={state}
      onCancel={() => setStep("collect_details")}
      onSubmitted={(ref) => {
        setStep("pick_target");
        onComplete(ref);
      }}
    />
  );
}
