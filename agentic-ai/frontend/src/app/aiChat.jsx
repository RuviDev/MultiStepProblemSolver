// src/app/aiChat.jsx
import React, { useState, useEffect } from "react";
import SideBar from "../components/common/SideBar";
import Header from "../components/common/Header";
import Home from "./aiChat-Body/home";

const AiChat = ({ chatId }) => {
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);

  // Keep a CSS var in sync with the sidebar width so fixed elements can offset from the left
  useEffect(() => {
    const apply = () => {
      const isLg = window.matchMedia("(min-width: 1024px)").matches; // Tailwind lg breakpoint
      // Tailwind: w-80 = 20rem, w-20 = 5rem
      const val = isLg ? (isSidebarCollapsed ? "5rem" : "20rem") : "0px";
      document.documentElement.style.setProperty("--sbw", val);
    };
    apply();
    window.addEventListener("resize", apply);
    return () => window.removeEventListener("resize", apply);
  }, [isSidebarCollapsed]);

  return (
    <div className="bg-white dark:bg-[#0b0b0b] dark:text-gray-100 h-screen flex">
      {/* Sidebar (fixed) */}
      <SideBar
        isCollapsed={isSidebarCollapsed}
        setIsCollapsed={setIsSidebarCollapsed}
      />

      {/* Right pane shifts with sidebar width on lg screens */}
      <div className={`flex-1 min-h-0 w-full ${isSidebarCollapsed ? "lg:pl-20" : "lg:pl-80"}`}>
        <Header
          isCollapsed={isSidebarCollapsed}
          setIsCollapsed={setIsSidebarCollapsed}
        />
        {/* Main content */}
        <main className="flex-1 min-h-0">
          <Home chatId={chatId} />
        </main>
      </div>
    </div>
  );
};

export default AiChat;
