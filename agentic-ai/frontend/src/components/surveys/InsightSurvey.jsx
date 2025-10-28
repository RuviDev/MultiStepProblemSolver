import React from "react";
import InsightBatch from "./InsightBatch";

export default function InsightSurvey({ survey, chatId, msgId }) {
  const batches = survey?.batches || [];
  const submittedBatches = survey?.submittedBatches || {};

  // console.log("InsightSurvey render:", { survey, msgId, submittedBatches });

  if (!batches.length) {
    return <div className="text-sm text-gray-500">No questions right now.</div>;
  }

  return (
    <div className="space-y-6">
      {batches.map((batch) => (
        <InsightBatch
          key={batch.batchId}
          chatId={chatId}
          msgId={msgId}
          batch={batch}
          existingSubmission={submittedBatches[batch.batchId]}
        />
      ))}
    </div>
  );
}
