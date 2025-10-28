// src/app/aiChat-Body/chat/welcome.jsx
import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { BRAIN } from "../../../assets";
import AskField from "../../../components/chat/AskField";
import AgentCardsSection from "../../../components/chat/AgentCardsSection";
import MessageList from "./messageList";
import { messages as msgApi, chats, uia as uiaApi, getTokens } from "../../../lib/api";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

const Welcome = ({ chatId }) => {
  const navigate = useNavigate();
  const [messages, setMessages] = useState([]);

  // Load history only when we have a chatId
  useEffect(() => {
    if (!chatId) return;
    (async () => {
      const history = await msgApi.list(chatId);
      // Preserve type & survey so the MessageList can render surveys
      const normalized = history.map((m) => ({
        id: m.id,
        role: m.role,
        type: m.type || "text",
        content: m.content_md ?? m.content ?? "",
        survey: m.survey,
        surveyType: m.surveyType || null,
        enc_question: m.enc_question || "",
        sources: m.sources || [],
      }));
      setMessages(normalized);
    })().catch(console.error);
  }, [chatId]);

  const append = (...rows) => setMessages((prev) => [...prev, ...rows]);

  // helper: update a specific temp progress bubble by _tempId
  const updateProgress = (tempId, updater) => {
    setMessages((prev) =>
      prev.map((m) => (m._tempId === tempId ? updater(m) : m))
    );
  };

  // helper: remove temp bubble
  const removeByTempId = (tempId) => {
    setMessages((prev) => prev.filter((m) => m._tempId !== tempId));
  };

const safeUUID = () => {
  try { return crypto?.randomUUID?.() || null; } catch { return null; }
};

const handleSend = async ({ text }) => {
  if (!text?.trim()) return;

  // optimistic user message
  append({ role: "user", type: "text", content: text });

  // ensure only one loader at a time
  setMessages((prev) => prev.filter((m) => m.type !== "progress"));

  // prepare request id and initial loader
  const requestId = safeUUID() || (Date.now() + "-" + Math.random().toString(36).slice(2));
  const tempId = `__progress__${requestId}`;
  append({
    _tempId: tempId,
    role: "assistant",
    type: "progress",
    progress: { currentLabel: "Queuing request", status: "running" },
  });

  let es;
  try {
    let targetChatId = chatId;

    // create a chat if needed
    if (!targetChatId) {
      const title = text.slice(0, 40);
      const created = await chats.create(title);
      targetChatId = created.id;
      window.dispatchEvent(new CustomEvent("chats:refresh", { detail: { chat: created } }));
    }

    // open SSE (server-driven labels)
    const { access_token } = getTokens() || {};
    const streamUrl =
      `${API_BASE}/messages/${targetChatId}/progress` +
      `?request_id=${encodeURIComponent(requestId)}` +
      `&access_token=${encodeURIComponent(access_token || "")}`;

    try {
      es = new EventSource(streamUrl);
    } catch (openErr) {
      console.error("SSE open error:", openErr);
      // fall back to a static label
      setMessages((prev) =>
        prev.map((m) =>
          m._tempId === tempId
            ? { ...m, progress: { ...m.progress, currentLabel: "Processing request" } }
            : m
        )
      );
    }

    if (es) {
      es.onmessage = (evt) => {
        if (!evt?.data) return;
        try {
          const data = JSON.parse(evt.data);
          if (data.type === "step") {
            const label = data.label || "Processing";
            setMessages((prev) =>
              prev.map((m) =>
                m._tempId === tempId
                  ? { ...m, progress: { ...m.progress, currentLabel: label } }
                  : m
              )
            );
          } else if (data.type === "done") {
            setMessages((prev) =>
              prev.map((m) =>
                m._tempId === tempId
                  ? { ...m, progress: { ...m.progress, status: "done", currentLabel: "Response ready" } }
                  : m
              )
            );
            es.close();
          } else if (data.type === "error") {
            setMessages((prev) =>
              prev.map((m) =>
                m._tempId === tempId
                  ? { ...m, progress: { ...m.progress, status: "error", currentLabel: data.message || "Server error" } }
                  : m
              )
            );
            es.close();
          }
        } catch (parseErr) {
          console.warn("SSE parse error:", parseErr);
        }
      };

      es.onerror = (e) => {
        console.warn("SSE error:", e);
        // don't crash UI; keep the minimal loader
        try { es.close(); } catch {}
      };
    }

    // final request to send the message
    const asst = await msgApi.send(targetChatId, text, requestId);

    // remove loader and append final assistant message
    setMessages((prev) => prev.filter((m) => m._tempId !== tempId));
    append({
      id: asst.id,
      role: asst.role || "assistant",
      type: asst.type || (asst.surveyType ? "survey" : "text"),
      content: asst.content ?? asst.content_md ?? "",
      survey: asst.survey,
      surveyType: asst.surveyType || null,
      enc_question: asst.enc_question || "",
      blocks: asst.blocks, // future-proof if you add composite
      sources: asst.sources || [],
    });

    if (!chatId) navigate(`/${targetChatId}`, { replace: true });
  } catch (e) {
    console.error(e);
    // flip loader to error instead of crashing the page
    setMessages((prev) =>
      prev.map((m) =>
        m._tempId === tempId
          ? { ...m, progress: { ...m.progress, status: "error", currentLabel: "Network or server error" } }
          : m
      )
    );
    append({ role: "assistant", type: "text", content: "Something went wrong reaching the server." });
  } finally {
    try { es && es.close(); } catch {}
  }
};

  // === Survey submit handlers (Phase C) ===
  const handleSubmitEmployment = async ({ employment_category_id, vault_version }) => {
    try {
      const empSubmit = await uiaApi.submitEmployment({
        chat_id: chatId, // important for per-chat UIA state
        employment_category_id,
        vault_version,
      });
      append({
        role: "assistant",
        type: "text",
        content: `We have recorded your employment category.`,
        // content: `Got it — employment category set to **${employment_category_id}**.`,
        // content: empSubmit.action,
      });
    } catch (e) {
      append({
        role: "assistant",
        type: "text",
        content: `Couldn't save employment category: ${e?.message || "unknown error"}`,
      });
    }
  };

  const handleSubmitSkills = async ({ let_system_decide, skills_selected, employment_category_id, vault_version }) => {
    try {
      const res = await uiaApi.submitSkills({
        chat_id: chatId,
        employment_category_id,
        vault_version,
        let_system_decide,
        skills_selected,
      });

      append({
        role: "assistant",
        type: "text",
        content:
          res.mode === "system_decide"
            ? "Ok then relativity AI will decide you a perfect skill development plan and you don't have to worry where you need to start!"
            : `Great, So now we know what skills you want to improve.`,
            // : `Nice — saved ${res.skills_count} skill(s).`,
      });
    } catch (e) {
      append({
        role: "assistant",
        type: "text",
        content: `Couldn't save skills: ${e?.message || "unknown error"}`,
      });
    }
  };

  const hasMessages = messages.length > 0;

  return hasMessages ? (
    <div className="h-full relative">
      <div className="h-full">
        <div className="mx-auto w-full max-w-3xl md:max-w-4xl h-full overflow-y-auto px-4 pt-4 pb-40">
          <MessageList
            messages={messages}
            chatId={chatId}
            onSubmitEmployment={handleSubmitEmployment}
            onSubmitSkills={handleSubmitSkills}
          />
        </div>
      </div>

      {/* Fixed input that offsets from sidebar width using CSS var */}
      <div className="fixed bottom-0 right-0" style={{ left: "var(--sbw, 0px)" }}>
        <div
          className="mx-auto w-full max-w-3xl md:max-w-4xl px-4 pb-6
                     bg-gradient-to-t from-white via-white/80 to-transparent
                     dark:from-[#0b0b0b] dark:via-[#0b0b0b]/80 dark:to-transparent"
        >
          <AskField onSend={handleSend} />
        </div>
      </div>
    </div>
  ) : (
    
    <div className="flex flex-col items-center justify-center w-full pt-8">
      <div className="flex items-center space-x-3">
        <img src={BRAIN} alt="Logo" className="h-10 object-contain" loading="eager" />
        <p className="text-2xl font-normal text-gray-900 dark:text-gray-100">
          Hi there, how can we help you ?
        </p>
      </div>

      <div className="w-full max-w-xl mt-8">
        <AskField onSend={handleSend} />
      </div>

      <div className="mt-10 max-w-2xl text-center">
        <p className="text-gray-500 dark:text-gray-400 text-base leading-relaxed">
          Drop your problem; the agents will plan, verify and execute.
        </p>
      </div>

      <AgentCardsSection />
    </div>
  );
};

export default Welcome;
