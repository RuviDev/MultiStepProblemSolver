// src/app/aiChat-Body/chat/InsightBatch.jsx
import React, { useState, useEffect } from "react";
import InsightQuestionCard from "./InsightQuestionCard";
import { insights as insightsApi } from "../../lib/api";

export default function InsightBatch({ chatId, msgId, batch, existingSubmission }) {
  const [answers, setAnswers] = useState({}); // { [insightId]: { answerId? , answerIds? , noteOther? } }
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(!!existingSubmission );

  // console.log("InsightBatch render:", { batch, existingSubmission, submitted });
  // console.log("message ID:", msgId);

  useEffect(() => {
    if (!existingSubmission) return;
    const map = {};
    for (const r of existingSubmission.responses || []) {
      console.log("Response:", r);
      if (Array.isArray(r.answerIds)) map[r.insightId] = { answerIds: r.answerIds.slice() };
      else if (r.answerId) map[r.insightId] = { answerId: r.answerId };
    }
    setAnswers(map);
    setSubmitted(true); // lock inputs + button
  }, [existingSubmission]);

  const updateAnswer = (insightId, payload) => {
    setAnswers((prev) => ({ ...prev, [insightId]: payload }));
  };

  const submit = async () => {
    const responses = Object.entries(answers).map(([insightId, v]) => {
      // send exactly one of answerId XOR answerIds per model schema
      const base = { insightId };
      if (Array.isArray(v.answerIds)) return { ...base, answerIds: v.answerIds };
      if (v.answerId) return { ...base, answerId: v.answerId };
      return null;
    }).filter(Boolean);

    if (!responses.length) return;

    try {
      setSubmitting(true);
      const body = {
        chatId,
        msgId,
        batchId: batch.batchId,
        responses,
        submittedAt: new Date().toISOString(),
      };
      console.log("Submitting insight batch:", body);
      const result = await insightsApi.submit(body);
      console.log("Submission result:", result);
      setSubmitted(true);
      // onSubmitted && onSubmitted(batch.batchId, result);
    } catch (e) {
      console.error(e);
      alert("Failed to submit. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="border rounded-xl p-3 bg-gray-100 dark:bg-[#111]">
      <div className="flex items-center justify-between mb-2">
        <div className="font-semibold">{batch.title}</div>
        {submitted ? (
          <span className="text-green-600 text-sm">Submitted</span>
        ) : (
          <button
            className="px-3 py-1 text-sm rounded-lg bg-blue-600 text-white disabled:opacity-50"
            onClick={submit}
            disabled={submitting}
          >
            {submitting ? "Submitting..." : "Submit"}
          </button>
        )}
      </div>

      {/* horizontally scrollable question cards */}
      <div className="flex gap-3 overflow-x-auto py-1">
        {batch.questions.map((q) => (
          <div key={q.insightId} className="shrink-0 w-[280px]">
            <InsightQuestionCard
              question={q}
              value={answers[q.insightId]}
              onChange={(payload) => updateAnswer(q.insightId, payload)}
              disabled={submitted}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
