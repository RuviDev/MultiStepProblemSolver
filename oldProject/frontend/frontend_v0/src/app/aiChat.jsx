import React, { useState } from "react";
import SideBar from "../components/common/SideBar";
import Header from "../components/common/Header";
import Home from "./aiChat-Body/home";

const AiChat = ({ chatId }) => {
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);

  // Keep content aligned with the fixed sidebar on ALL screen sizes
  const contentMargin = isSidebarCollapsed ? "ml-22" : "ml-full";

  return (
    <div className="bg-white h-screen flex">
      {/* fixed sidebar stays the same */}
      <SideBar
        isCollapsed={isSidebarCollapsed}
        setIsCollapsed={setIsSidebarCollapsed}
      />

      {/* content column must be a flex column with min-h-0 */}
      <div className={`flex flex-col flex-1 ${contentMargin} min-h-0`}>
        <Header
          isCollapsed={isSidebarCollapsed}
          setIsCollapsed={setIsSidebarCollapsed}
          chatId={chatId}
        />
        {/* this main now grows and allows its children to scroll */}
        <main className="flex-1 min-h-0">
          <Home chatId={chatId} />
        </main>
      </div>
    </div>
  );
};

export default AiChat;
