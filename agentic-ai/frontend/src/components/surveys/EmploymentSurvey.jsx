import React, { useState } from "react";

/**
 * Props:
 * - survey: { type:"single-select", options:[{id,label,desc}], vault_version }
 * - chatId: string
 * - onSubmit: async ({ employment_category_id, vault_version }) => void
 * - disabled?: boolean
 */
export default function EmploymentSurvey({ survey, chatId, onSubmit, msgId, disabled }) {
  const [selected, setSelected] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const canSubmit = !!selected && !submitting && !disabled;

  return (
    <div className="mt-3">
      <div className="font-semibold">{survey.title || "Choose your employment category"}</div>
      {survey.help && <div className="text-sm text-gray-500 mt-1">{survey.help}</div>}

      <div className="mt-3 space-y-2">
        {survey.options?.map(opt => (
          <label key={opt.id} className="flex items-start gap-2 cursor-pointer">
            <input
              type="radio"
              name="ec"
              className="mt-1"
              value={opt.id}
              checked={selected === opt.id}
              onChange={() => setSelected(opt.id)}
              disabled={disabled || submitting}
            />
            <div>
              <div className="font-medium">{opt.label}</div>
              {opt.desc && <div className="text-xs text-gray-500">{opt.desc}</div>}
            </div>
          </label>
        ))}
      </div>

      <button
        className="mt-3 px-3 py-1.5 rounded bg-blue-600 text-white disabled:opacity-50"
        disabled={!canSubmit}
        onClick={async () => {
          try {
            setSubmitting(true);
            await onSubmit({ employment_category_id: selected, vault_version: survey.vault_version });
          } finally {
            setSubmitting(false);
          }
        }}
      >
        {submitting ? "Submitting..." : "Submit"}
      </button>
    </div>
  );
}
