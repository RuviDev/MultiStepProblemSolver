// src/components/MessageList.jsx
import React, { useRef, useEffect } from "react";
import MarkdownMessage from "./MarkdownMessage";
import EmploymentSurvey from "../../../components/surveys/EmploymentSurvey";
import SkillsSurvey from "../../../components/surveys/SkillsSurvey";
import InsightSurvey from "../../../components/surveys/InsightSurvey";
import AssistantProgress from "./AssistantProgress";

const isJson = (txt) => {
  if (typeof txt !== "string") return false;
  const s = txt.trim();
  if (!s) return false;
  if (!(s.startsWith("{") || s.startsWith("["))) return false;
  try { JSON.parse(s); return true; } catch { return false; }
};

const prettyJsonAsMarkdown = (txt) => {
  try {
    const obj = JSON.parse(txt);
    const pretty = JSON.stringify(obj, null, 2);
    return "```json\n" + pretty + "\n```";
  } catch {
    return txt;
  }
};

// helper
const trunc = (s, n = 20) => (s && s.length > n ? s.slice(0, n - 1) + "…" : s || "");
const srcName = (s) => (s?.breadcrumb?.trim() || s?.chunk_id || "").trim();

const SourcesStrip = ({ sources = [] }) => {
  if (!sources.length) return null;
  return (
    <div className="mt-2 mb-1">
      <div
        className="
          overflow-x-auto whitespace-nowrap no-scrollbar
          -mx-1 px-2 py-2
        "
      >
        {sources.map((s, i) => {
          const full = srcName(s);
          const short = trunc(full, 20);
          return (
            <span
              key={s.chunk_id || i}
              title={full}
              className="
                inline-flex items-center
                bg-gray-100 text-gray-800 hover:bg-gray-200
                dark:bg-gray-800 dark:text-gray-100
                text-xs rounded-full px-3 py-2 mr-2 mb-1
                select-none
              "
            >
              {short || "Source"}
            </span>
          );
        })}
      </div>
    </div>
  );
};


const MessageList = ({ messages = [], chatId, onSubmitEmployment, onSubmitSkills }) => {
  const bottomRef = useRef(null);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  return (
    <div className="w-full max-w-2xl md:max-w-3xl mx-auto flex flex-col gap-4 py-8 overflow-x-hidden">
      {messages.map((msg, idx) => {
        console.log("Rendering message:", msg);
        const isUser = msg.role === "user";
        const isProgress = msg.type === "progress"; // only progress uses type
        const raw = typeof msg.content === "string" ? msg.content : "";
        const contentForRender = isJson(raw) ? prettyJsonAsMarkdown(raw) : raw;

        // NEW: survey detection based on surveyType (not msg.type)
        // Back-compat: legacy 'insight-survey' messages
        const legacyInsight = msg.type === "insight-survey";
        const surveyType = msg.surveyType || (legacyInsight ? "insight_survey" : null);
        const hasSurvey = !!surveyType && !!msg.survey;

        const hasContent = !!contentForRender?.trim();
        const hasEnc = !!(msg.enc_question && msg.enc_question.trim());

        // bubble chrome helpers
        // const clsUser = "bg-blue-500 text-white border rounded-2xl px-3 py-2 max-w-[75%]";
        // const clsAsst = "bg-gray-100 dark:bg-[#111] border rounded-2xl px-3 py-2 max-w-[75%]";
        // const clsEnc  = "border rounded-2xl px-3 py-2 max-w-[75%] border-amber-300/60 bg-amber-50 dark:bg-amber-900/20 text-amber-900 dark:text-amber-100";
        // const clsFull = "w-full max-w-none bg-transparent border-0 p-0"; // full-width for insight survey

        const baseFit = "inline-block w-fit break-words [overflow-wrap:anywhere] align-top"; // shrink to content
        const clampContent = "max-w-[98%]";   // main text & enc question
        const clampSurvey  = "max-w-[90%] md:max-w-[75%]"; // EC/Skills surveys (forms are a bit wider)

        const clsUser = `${baseFit} ${clampContent} mt-2 bg-gray-100 text-black border rounded-2xl px-3 py-2`;
        const clsAsst = `${baseFit} ${clampContent} bg-white-100 rounded-2xl px-3 py-2`;
        const clsEnc  = `${baseFit} ${clampContent} border rounded-2xl px-3 py-2 border-amber-300/60 bg-amber-50 dark:bg-amber-900/20 text-amber-900 dark:text-amber-100`;

        // EC/Skills survey bubbles shrink to content; Insight surveys remain full-width
        const clsSurveyFit = `${baseFit} ${clampSurvey} mt-4 mb-4 bg-gray-100 dark:bg-[#111] border rounded-2xl px-3 py-2`;
        const clsInsightSurvey = "mt-4 mb-4 w-full bg-transparent border-0 p-0 overflow-x-hidden";

        return (
          <div key={idx} className={`flex ${isUser ? "justify-end" : "justify-start"} min-w-0`}>
            {/* USER / PROGRESS SIMPLE PATHS */}
            {isUser && (
              <div className={clsUser}>
                <div className="overflow-x-auto">
                  <MarkdownMessage content={contentForRender} compact />
                </div>
              </div>
            )}

            {!isUser && isProgress && (
              <div className={clsAsst}>
                <AssistantProgress
                  status={msg.progress?.status || "running"}
                  currentLabel={msg.progress?.currentLabel || "Processing"}
                />
              </div>
            )}

            {/* ASSISTANT: STACK UP TO THREE BUBBLES (content → survey → enc) */}
            {!isUser && !isProgress && (
              <div className="flex flex-col gap-1 min-w-0">
                {/* 1) CONTENT bubble (if any) */}
                {hasContent && (
                  <div className={clsAsst}>
                    <div className="overflow-x-auto">
                      <MarkdownMessage content={contentForRender} />
                    </div>
                  </div>
                )}
                {hasContent && (
                  <SourcesStrip sources={msg.sources} />
                )}

                <hr></hr>

                {/* 2) SURVEY bubble (at most one) */}
                {hasSurvey && (
                  <>
                  <div className={surveyType === "insight_survey" ? clsInsightSurvey  : clsSurveyFit}>

                    {surveyType === "ec_survey" && (
                      <EmploymentSurvey
                        survey={msg.survey}
                        chatId={chatId}
                        msgId={msg.id}
                        onSubmit={onSubmitEmployment}
                      />
                    )}

                    {surveyType === "skills_survey" && (
                      <SkillsSurvey
                        survey={msg.survey}
                        msgId={msg.id}
                        onSubmit={onSubmitSkills}
                      />
                    )}

                    {(surveyType === "insight_survey") && (
                      <div className="max-w-full overflow-x-auto overscroll-x-contain">
                        <InsightSurvey
                          survey={msg.survey}
                          chatId={chatId}
                          msgId={msg.id}
                        />
                      </div>
                    )}
                  </div>
                  <hr></hr>
                  </>
                )}

                {/* 3) ENCOURAGEMENT bubble (if any) */}
                {hasEnc && (
                  <>
                    <div className="mt-4 ml-3 text-base uppercase tracking-wide text-gray-500">
                      Quick Question
                    </div>
                    <div className={clsAsst}>
                      {msg.enc_question}
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
};

export default MessageList;
