import React, { useState } from "react";
import { MessageSquare, FileText } from "lucide-react";
import ChatWelcome from "./chat/welcome";
import Summary from "./summary/summary";

const Home = ({ chatId }) => {
  const [tab, setTab] = useState("chat");

  return (
    <div className="flex flex-col items-center justify-center max-w-4xl mx-auto mt-6">
      {/* Chat/Summary Tabs (desktop only) */}
      <div className="hidden sm:flex justify-center mb-6 w-full">
        <div className="flex gap-8">
          <button
            className={`flex flex-col items-center px-2 focus:outline-none`}
            onClick={() => setTab("chat")}
          >
            <span
              className={`flex items-center text-base font-medium ${tab === "chat" ? "text-primary-accent" : "text-gray-800"
                }`}
            >
              <MessageSquare className="w-5 h-5 mr-2" />
              Chat
            </span>
            {tab === "chat" && (
              <span className="block w-7 h-0.5 bg-primary-accent mt-1 rounded"></span>
            )}
          </button>
          <button
            className={`flex flex-col items-center px-2 focus:outline-none`}
            onClick={() => setTab("summary")}
          >
            <span
              className={`flex items-center text-base font-medium ${tab === "summary" ? "text-primary-accent" : "text-gray-800"
                }`}
            >
              <FileText className="w-5 h-5 mr-2" />
              summary
            </span>
            {tab === "summary" && (
              <span className="block w-12 h-0.5 bg-primary-accent mt-1 rounded"></span>
            )}
          </button>
        </div>
      </div>

      {/* Mobile Chat/Summary toggle */}
      <div className="flex justify-center mt-4 sm:hidden">
        <div className="flex gap-8">
          <button
            className={`flex flex-col items-center px-2 focus:outline-none`}
            onClick={() => setTab("chat")}
          >
            <span
              className={`flex items-center text-base font-medium ${tab === "chat" ? "text-primary-accent" : "text-gray-800"
                }`}
            >
              <MessageSquare className="w-5 h-5 mr-2" />
              Chat
            </span>
            {tab === "chat" && (
              <span className="block w-7 h-0.5 bg-primary-accent mt-1 rounded"></span>
            )}
          </button>
          <button
            className={`flex flex-col items-center px-2 focus:outline-none`}
            onClick={() => setTab("summary")}
          >
            <span
              className={`flex items-center text-base font-medium ${tab === "summary" ? "text-primary-accent" : "text-gray-800"
                }`}
            >
              <FileText className="w-5 h-5 mr-2" />
              summary
            </span>
            {tab === "summary" && (
              <span className="block w-12 h-0.5 bg-primary-accent mt-1 rounded"></span>
            )}
          </button>
        </div>
      </div>

      {/* Tab Content */}
      <div className="w-full">
        {tab === "chat" && <ChatWelcome chatId={chatId} />}
        {tab === "summary" && <Summary />}
      </div>
    </div>
  );
};

export default Home;
