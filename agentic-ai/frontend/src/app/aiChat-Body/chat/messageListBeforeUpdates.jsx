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

const MessageList = ({ messages = [], chatId, onSubmitEmployment, onSubmitSkills }) => {
  const bottomRef = useRef(null);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  return (
    <div className="w-full max-w-2xl md:max-w-3xl mx-auto flex flex-col gap-4 py-8">
      {messages.map((msg, idx) => {
        const isUser = msg.role === "user";
        const isSurvey = msg.type === "survey";
        const isInsightSurvey = msg.type === "insight-survey";
        const isProgress = msg.type === "progress";
        const raw = typeof msg.content === "string" ? msg.content : "";
        const contentForRender = isJson(raw) ? prettyJsonAsMarkdown(raw) : raw;
        const survey = msg.survey;
        const surveyKind = isSurvey ? (survey?.employment_category_id ? "skills" : "ec") : null;

        console.log("Rendering message:", msg);

        return (
          <div key={idx} className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
            {/* <div className={`px-4 py-2 rounded-xl max-w-[80%] break-words ${
              isUser ? "bg-blue-500 text-white" : "bg-gray-100 dark:bg-[#111] text-gray-900 dark:text-gray-100"
            }`}> */}
            <div
              className={
                isInsightSurvey
                  ? [
                      // FULL-WIDTH bubble for insight surveys
                      "w-full max-w-none",
                      "bg-transparent border-0 p-0",      // <-- no bubble chrome
                    ].join(" ")
                  : [
                      // regular bubbles
                      isUser ? "bg-blue-500 text-white" : "bg-gray-100 dark:bg-[#111]",
                      "border rounded-2xl px-3 py-2",
                      "max-w-[75%]",                      // keep normal constraint for others
                    ].join(" ")
              }
            >

              {/* {!isSurvey && !isProgress && (
                <MarkdownMessage content={contentForRender} compact={isUser} />
              )} */}

              {!isSurvey && !isProgress && !isInsightSurvey && (
                <MarkdownMessage content={contentForRender} compact={isUser} />
              )}

              {isProgress && (
                <AssistantProgress
                  status={msg.progress?.status || "running"}
                  currentLabel={msg.progress?.currentLabel || "Processing"}
                />
              )}

              {isSurvey && surveyKind === "ec" && (
                <EmploymentSurvey
                  survey={survey}
                  chatId={chatId}
                  onSubmit={onSubmitEmployment}
                />
              )}

              {isSurvey && surveyKind === "skills" && (
                <SkillsSurvey
                  survey={survey}
                  onSubmit={onSubmitSkills}
                />
              )}

              {isInsightSurvey && (
                <InsightSurvey
                  survey={msg.survey}     // the envelope {batches:[...]}
                  chatId={chatId}
                />
              )}

            </div>
          </div>
        );
      })}
      <div ref={bottomRef} />
    </div>
  );
};
export default MessageList;
