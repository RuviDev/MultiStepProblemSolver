import React, { useState, useEffect } from "react";
import { BRAIN } from "../../../assets";
import AskField from "../../../components/chat/AskField";
import AgentCardsSection from "../../../components/chat/AgentCardsSection";
import MessageList from "./messageList";
import { messages as msgApi } from "../../../lib/api";

const Welcome = ({ chatId }) => {
  const [messages, setMessages] = useState([]);

  // Load history when chatId changes
  useEffect(() => {
    (async () => {
      const history = await msgApi.list(chatId);
      // Normalize to match existing MessageList expectations (content, role)
      const normalized = history.map(m => ({
        role: m.role,
        content: m.content ?? m.content_md ?? "",
      }));
      setMessages(normalized);
    })().catch(console.error);
  }, [chatId]);

  const handleSend = async ({ text }) => {
    if (!text?.trim()) return;
    // optimistic user message
    setMessages(prev => [...prev, { role: "user", content: text }]);
    try {
      const asst = await msgApi.send(chatId, text);
      const normalized = {
        role: asst.role || "assistant",
        content: asst.content ?? asst.content_md ?? "",
      };
      setMessages(prev => [...prev, normalized]);
    } catch (e) {
      console.error(e);
      setMessages(prev => [...prev, { role: "assistant", content: "Something went wrong reaching the server." }]);
    }
  };

  const hasMessages = messages.length > 0;

  return hasMessages ? (
    <div className="h-full relative">
      {/* center column width similar to ChatGPT; full height + scroll */}
      <div className="h-full">
        <div className="mx-auto w-full max-w-3xl md:max-w-4xl h-full overflow-y-auto px-4 pt-4 pb-40">
          <MessageList messages={messages} />
        </div>
      </div>

      {/* input fixed at bottom */}
      <div className="fixed inset-x-0 bottom-0 mx-auto w-full max-w-3xl md:max-w-4xl px-4 pb-4
                      bg-gradient-to-t from-white via-white/80 to-transparent">
        <AskField onSend={handleSend} />
      </div>
    </div>
  ) : (
    <div className="flex flex-col items-center justify-center w/full pt-8">
      <div className="flex items-center space-x-3">
        <img src={BRAIN} alt="Logo" className="h-10 object-contain" loading="eager" />
        <p className="text-2xl font-normal text-gray-900">Hi there, how can we help you ?</p>
      </div>

      <div className="w-full max-w-xl mt-8">
        <AskField onSend={handleSend} />
      </div>

      <div className="mt-10 max-w-2xl text-center">
        <p className="text-gray-500 text-base leading-relaxed">
          Drop your problem; the agents will plan, verify and execute.
        </p>
      </div>

      <AgentCardsSection />
    </div>
  );

  // return hasMessages ? (
  //   <div className="h-full relative">
  //     {/* center column width similar to ChatGPT; full height + scroll */}
  //     <div className="h-full">
  //       <div className="mx-auto w-full max-w-3xl md:max-w-4xl h-full overflow-y-auto px-4 pt-4 pb-40">
  //         <MessageList messages={messages} />
  //       </div>
  //     </div>

  //     {/* input fixed at bottom */}
  //     <div className="fixed inset-x-0 bottom-0 mx-auto w-full max-w-3xl md:max-w-4xl px-4 pb-4
  //                     bg-gradient-to-t from-white via-white/80 to-transparent">
  //       <AskField onSend={handleSend} />
  //     </div>
  //   </div>
  // ) : (
  //   <div className="h-full">
  //     <div className="mx-auto w-full max-w-3xl md:max-w-4xl px-4">
  //       {/* ...leave your empty-state JSX as-is... */}
  //       {/* AskField and AgentCardsSection stay the same */}
  //     </div>
  //   </div>
  // );
};

export default Welcome;