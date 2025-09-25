// src/components/chat/ProblemStatementCard.jsx
import React from "react";

const Row = ({ k, v }) => (
  <div className="grid grid-cols-3 gap-3 text-sm">
    <div className="text-gray-500">{k}</div>
    <div className="col-span-2 break-words">
      {Array.isArray(v) ? (
        <ul className="list-disc ml-4 space-y-1">
          {v.map((item, i) => (
            <li key={i}>{String(item)}</li>
          ))}
        </ul>
      ) : typeof v === "object" && v !== null ? (
        <pre className="whitespace-pre-wrap break-words text-xs bg-gray-50 rounded p-2">
          {JSON.stringify(v, null, 2)}
        </pre>
      ) : (
        <span>{String(v)}</span>
      )}
    </div>
  </div>
);

const ProblemStatementCard = ({ data, onGenerate }) => {
  if (!data) return null;

  // Show well-known fields first if they exist; fall back to generic render
  const preferredOrder = [
    "title",
    "summary",
    "description",
    "context",
    "goals",
    "requirements",
    "constraints",
    "assumptions",
    "timeline",
    "metrics",
    "owner",
    "stakeholders",
  ];

  const keys = [
    ...preferredOrder.filter((k) => Object.prototype.hasOwnProperty.call(data, k)),
    ...Object.keys(data).filter((k) => !preferredOrder.includes(k)),
  ];

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between mb-2">
        <h3 className="font-semibold">Problem Statement</h3>
        <button
          onClick={onGenerate}
          className="text-sm rounded-lg px-3 py-1.5 bg-blue-600 text-white hover:bg-blue-700"
        >
          Generate Plan
        </button>
      </div>

      <div className="space-y-2">
        {keys.map((k) => (
          <Row key={k} k={k} v={data[k]} />
        ))}
      </div>
    </div>
  );
};

export default ProblemStatementCard;
