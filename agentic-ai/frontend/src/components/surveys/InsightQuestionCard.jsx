// src/app/aiChat-Body/chat/InsightQuestionCard.jsx
import React, { useState, useEffect } from "react";

/**
 * Props:
 * - question: {
 *     insightId, uiQuestion, type: "single"|"multi",
 *     options: [{answerId,label}], includeOther, noteOtherLabel
 *   }
 * - value: { answerId? , answerIds? , noteOther? }
 * - onChange: (payload) => void
 */
export default function InsightQuestionCard({ question, value, onChange, disabled }) {
  const isMulti = question.type === "multi";
  const [local, setLocal] = useState(value || {});

  useEffect(() => {
    setLocal(value || {});
  }, [value?.answerId, value?.answerIds, value?.noteOther]);

  const toggleMulti = (id) => {
    const set = new Set(local.answerIds || []);
    if (set.has(id)) set.delete(id); else set.add(id);
    const next = { ...local, answerIds: Array.from(set) };
    setLocal(next);
    onChange && onChange(next);
  };

  const chooseSingle = (id) => {
    const next = { answerId: id };
    setLocal(next);
    onChange && onChange(next);
  };

  const changeOther = (e) => {
    const next = { ...local, noteOther: e.target.value };
    setLocal(next);
    onChange && onChange(next);
  };

  return (
    <div className="h-full border rounded-lg p-3 bg-white dark:bg-[#0f0f0f]">
      <div className="text-sm font-medium mb-2">{question.uiQuestion}</div>

      {/* options */}
      <div className="space-y-2">
        {question.options.map((opt) => (
          <label key={opt.answerId} className="flex items-center gap-2 text-sm">
            {isMulti ? (
              <input
                type="checkbox"
                checked={Array.isArray(local.answerIds) && local.answerIds.includes(opt.answerId)}
                onChange={() => !disabled && toggleMulti(opt.answerId)}
              />
            ) : (
              <input
                type="radio"
                name={question.insightId}
                checked={local.answerId === opt.answerId}
                onChange={() => !disabled && chooseSingle(opt.answerId)}
              />
            )}
            <span>{opt.label}</span>
          </label>
        ))}
      </div>

      {/* "Other" input (note: backend currently doesn't persist the note) */}
      {/* {question.includeOther && (
        <div className="mt-3">
          <div className="text-xs text-gray-500 mb-1">{question.noteOtherLabel || "Other"}</div>
          <input
            type="text"
            className="w-full border rounded px-2 py-1 text-sm bg-white dark:bg-[#0f0f0f]"
            value={local.noteOther || ""}
            onChange={changeOther}
            placeholder="Type your note (optional)"
          />
          <div className="text-[11px] text-gray-400 mt-1">
            Tip: select the “Other” option too (if present) so it’s recorded.
          </div>
        </div>
      )} */}
    </div>
  );
}
