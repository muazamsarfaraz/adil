"use client";

import { useState } from "react";
import ReportTargetPicker from "./report-target-picker";
import ReportModal from "./report-modal";

export interface ReportState {
  targetId: string;
  name: string;
  email: string;
  phone?: string;
  dob?: string;
  address?: string;
  summary: string;
  date?: string;
  location?: string;
}

type Step = "pick_target" | "collect_details" | "review";

export default function ReportFlow({ onComplete }: { onComplete: (reference: string) => void }) {
  const [step, setStep] = useState<Step>("pick_target");
  const [state, setState] = useState<ReportState>({
    targetId: "", name: "", email: "", summary: "",
  });

  if (step === "pick_target") {
    return (
      <div className="my-3">
        <div className="text-sm text-gray-700 mb-2">Where would you like to submit your report?</div>
        <ReportTargetPicker onSelect={(id) => { setState({ ...state, targetId: id }); setStep("collect_details"); }} />
      </div>
    );
  }

  if (step === "collect_details") {
    return (
      <div className="my-3 p-4 border border-brand-200 bg-brand-50 rounded-lg space-y-2">
        <div className="text-sm font-semibold">Incident details (kept private — not sent to AI)</div>
        <label className="block text-xs">
          Name
          <input className="block w-full mt-1 p-2 border border-gray-300 rounded text-sm"
                 value={state.name} onChange={(e) => setState({ ...state, name: e.target.value })} />
        </label>
        <label className="block text-xs">
          Email
          <input className="block w-full mt-1 p-2 border border-gray-300 rounded text-sm"
                 type="email" value={state.email} onChange={(e) => setState({ ...state, email: e.target.value })} />
        </label>
        <label className="block text-xs">
          What happened?
          <textarea className="block w-full mt-1 p-2 border border-gray-300 rounded text-sm"
                    rows={4} value={state.summary} onChange={(e) => setState({ ...state, summary: e.target.value })} />
        </label>
        <label className="block text-xs">
          Date (optional)
          <input type="date" className="block w-full mt-1 p-2 border border-gray-300 rounded text-sm"
                 value={state.date ?? ""} onChange={(e) => setState({ ...state, date: e.target.value })} />
        </label>
        <button className="mt-2 px-4 py-2 bg-brand-900 text-white rounded hover:bg-brand-700 text-sm disabled:opacity-50"
                disabled={!state.name || !state.email || state.summary.length < 10}
                onClick={() => setStep("review")}>
          Review &amp; submit
        </button>
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
