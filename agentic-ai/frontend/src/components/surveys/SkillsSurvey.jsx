import React, { useMemo, useState } from "react";

/**
 * Props:
 * - survey: { type:"multi-select-with-limit", options:[{id,label,desc}], max, let_system_decide, employment_category_id, vault_version }
 * - onSubmit: async ({ let_system_decide:boolean, skills_selected?:string[], employment_category_id, vault_version }) => void
 * - disabled?: boolean
 */
export default function SkillsSurvey({ survey, msgId, onSubmit, disabled }) {
  const max = survey.max || 4;
  const [picks, setPicks] = useState([]);
  const [systemDecide, setSystemDecide] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const canSubmit = useMemo(() => {
    if (disabled || submitting) return false;
    if (systemDecide) return true;
    return picks.length >= 1 && picks.length <= max;
  }, [disabled, submitting, systemDecide, picks.length, max]);

  function togglePick(id) {
    if (systemDecide) return;
    setPicks(prev => {
      const exists = prev.includes(id);
      if (exists) return prev.filter(x => x !== id);
      if (prev.length >= max) return prev;
      return [...prev, id];
    });
  }

  return (
    <div className="mt-3">
      <div className="font-semibold">{survey.title || `Pick up to ${max} skills to focus on`}</div>
      {survey.help && <div className="text-sm text-gray-500 mt-1">{survey.help}</div>}

      <div className="mt-3">
        {survey.let_system_decide && (
          <label className="inline-flex items-center gap-2 mb-3 cursor-pointer">
            <input
              type="checkbox"
              checked={systemDecide}
              onChange={(e) => {
                setSystemDecide(e.target.checked);
                if (e.target.checked) setPicks([]);
              }}
              disabled={disabled || submitting}
            />
            <span className="text-sm">Let the system decide</span>
          </label>
        )}

        <div className={`grid grid-cols-1 gap-2 ${systemDecide ? "opacity-50 pointer-events-none" : ""}`}>
          {survey.options?.map((opt) => {
            const active = picks.includes(opt.id);
            return (
              <button
                key={opt.id}
                onClick={() => togglePick(opt.id)}
                className={`text-left p-2 rounded border ${active ? "border-blue-600" : "border-gray-300"}`}
              >
                <div className="font-medium">{opt.label}</div>
                {opt.desc && <div className="text-xs text-gray-500">{opt.desc}</div>}
              </button>
            );
          })}
        </div>
      </div>

      <div className="mt-3 text-xs text-gray-500">
        {systemDecide ? "System will choose an appropriate set for you." :
          `Selected ${picks.length}/${max}`}
      </div>

      <button
        className="mt-3 px-3 py-1.5 rounded bg-blue-600 text-white disabled:opacity-50"
        disabled={!canSubmit}
        onClick={async () => {
          try {
            setSubmitting(true);
            await onSubmit({
              let_system_decide: systemDecide,
              skills_selected: systemDecide ? undefined : picks,
              employment_category_id: survey.employment_category_id,
              vault_version: survey.vault_version,
            });
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
