// src/components/common/SideBar.jsx
import React, { useState, useEffect, useCallback } from "react";
import {
  MessageSquare,
  Plus,
  MoreHorizontal,
  FolderOpen,
  Settings as SettingsIcon,
  X,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { LOGO, LOGO_TRANSPARENT_CENTER, NEWCHAT, SETTINGS } from "../../assets";
import { useNavigate } from "react-router-dom";
import { chats } from "../../lib/api";

const SideBar = ({ isCollapsed, setIsCollapsed }) => {
  const navigate = useNavigate();

  // widths used both here and in the page layout
  const EXPANDED_W = "w-72";
  const COLLAPSED_W = "w-20";

  const [items, setItems] = useState([]);
  const [menuOpenId, setMenuOpenId] = useState(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [darkMode, setDarkMode] = useState(() => localStorage.getItem("theme") === "dark");

  // --- NEW: centralized refresher ---
  const refresh = useCallback(() => {
    chats
      .list()
      .then((list) => setItems(list.filter((c) => !c.archived)))
      .catch(console.error);
  }, []);

  // initial load
  useEffect(() => {
    refresh();
  }, [refresh]);

  // 🔔 Listen for 'chats:refresh' (e.g., first prompt created a chat in Welcome.jsx)
  useEffect(() => {
    const onRefresh = (e) => {
      // If the event includes a created chat, optimistically add it before full refresh
      const created = e?.detail?.chat;
      if (created?.id) {
        setItems((prev) => (prev.some((x) => x.id === created.id) ? prev : [created, ...prev]));
      }
      // then re-fetch to stay in sync
      refresh();
    };
    window.addEventListener("chats:refresh", onRefresh);
    return () => window.removeEventListener("chats:refresh", onRefresh);
  }, [refresh]);

  useEffect(() => {
    // apply persisted dark mode on mount
    document.documentElement.classList.toggle("dark", darkMode);
  }, [darkMode]);

  const newChat = async () => {
    try {
      const c = await chats.create();
      // Optimistically insert so it appears immediately
      setItems((prev) => (prev.some((x) => x.id === c.id) ? prev : [c, ...prev]));
      navigate(`/${c.id}`);
      // Optional: also fire a global refresh for other components if needed
      window.dispatchEvent(new CustomEvent("chats:refresh", { detail: { chat: c } }));
    } catch (e) {
      console.error(e);
    }
  };

  const renameChat = async (id, currentTitle) => {
    const next = window.prompt("Rename chat", currentTitle || "Untitled chat");
    if (!next) return;
    try {
      const updated = await chats.patch(id, { title: next });
      setItems((prev) => prev.map((c) => (c.id === id ? { ...c, title: updated.title } : c)));
    } catch (e) {
      console.error(e);
    }
  };

  const deleteChat = async (id) => {
    if (!window.confirm("Delete this chat? This cannot be undone.")) return;
    try {
      await chats.remove(id);
      setItems((prev) => prev.filter((c) => c.id !== id));
      // If currently on this chat, you can navigate("/") if desired
      navigate("/");
    } catch (e) {
      console.error(e);
    }
  };

  const toggleSettings = () => setSettingsOpen((v) => !v);

  const toggleDark = () => {
    setDarkMode((d) => {
      const next = !d;
      localStorage.setItem("theme", next ? "dark" : "light");
      document.documentElement.classList.toggle("dark", next);
      return next;
    });
  };

  const logout = async () => {
    if (!window.confirm("Are you sure you want to log out?")) return;
    try {
      const { auth, clearTokens } = await import("../../lib/api");
      try {
        await auth.logout();
      } catch {}
      clearTokens();
      navigate("/login", { replace: true });
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <>
      {/* Mobile overlay ONLY when expanded (so user can tap outside to close) */}
      {!isCollapsed && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={() => setIsCollapsed(true)}
        />
      )}

      {/* Sidebar */}
      <div
        className={`fixed left-0 top-0 h-full bg-light-ash dark:bg-[#0f0f0f] border-gray-200 z-50 transition-all duration-300 ease-in-out
        ${isCollapsed ? COLLAPSED_W : EXPANDED_W}
        lg:translate-x-0`}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4">
          {!isCollapsed && (
            <>
              <div className="flex items-center space-x-3">
                <img
                  src={LOGO_TRANSPARENT_CENTER}
                  alt="Logo"
                  className="h-10 object-contain shrink-0 select-none"
                  loading="eager"
                />
                <span className="text-lg font-semibold text-gray-900 dark:text-gray-100">Relativity AI</span>
              </div>
              {/* collapse button removed per your last version */}
            </>
          )}

          {isCollapsed && (
            <div className="w-full flex justify-center">
              <img
                src={LOGO_TRANSPARENT_CENTER}
                alt="Logo"
                className="h-10 object-contain shrink-0 select-none"
                loading="eager"
              />
            </div>
          )}
        </div>

        {/* New chat */}
        <div className="p-4">
          <button
            className={`w-full flex items-center space-x-3 p-3 text-gray-700 hover:bg-ash rounded-lg transition-colors ${
              isCollapsed ? "justify-center" : "justify-start"
            }`}
            onClick={newChat}
          >
            <img
              src={NEWCHAT}
              alt="New Chat"
              className="h-6 object-contain shrink-0 select-none"
              loading="eager"
            />
            {!isCollapsed && <span className="font-medium">New Chat</span>}
          </button>
        </div>

        {/* Chats */}
        {!isCollapsed && (
          <div className="px-4">
            <h3 className="text-sm font-bold text-gray-500 tracking-wide mb-3">Chats</h3>
            <div className="space-y-1">
              {items.map((c) => (
                <div
                  key={c.id}
                  onClick={() => navigate(`/${c.id}`)}
                  className="group flex items-center justify-between p-3 hover:bg-ash rounded-lg cursor-pointer"
                >
                  <span className="text-gray-700 dark:text-gray-200 text-sm truncate flex-1">
                    {c.title || "Untitled chat"}
                  </span>

                  {/* 3-dots menu */}
                  <div className="relative">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setMenuOpenId(menuOpenId === c.id ? null : c.id);
                      }}
                      className="opacity-0 group-hover:opacity-100 p-1 hover:bg-ash rounded transition-opacity"
                    >
                      <MoreHorizontal className="w-4 h-4 text-gray-500" />
                    </button>
                    {menuOpenId === c.id && (
                      <div className="absolute right-0 mt-2 w-36 bg-white dark:bg-[#111] border rounded shadow-lg z-50">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setMenuOpenId(null);
                            renameChat(c.id, c.title);
                          }}
                          className="w-full text-left px-3 py-2 hover:bg-ash text-sm dark:text-gray-100"
                        >
                          Rename
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            setMenuOpenId(null);
                            deleteChat(c.id);
                          }}
                          className="w-full text-left px-3 py-2 hover:bg-ash text-sm text-red-600"
                        >
                          Delete
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Settings bottom */}
        <div className="absolute bottom-0 left-0 right-0 p-4 border-t border-gray-200">
          <button
            className={`w-full flex items-center space-x-3 p-3 text-gray-700 hover:bg-ash rounded-lg transition-colors ${
              isCollapsed ? "justify-center" : "justify-start"
            }`}
            onClick={() => setSettingsOpen((v) => !v)}
          >
            <img
              src={SETTINGS}
              alt="Settings"
              className="h-6 object-contain shrink-0 select-none"
              loading="eager"
            />
            {!isCollapsed && <span className="font-medium">Settings</span>}
          </button>

          {/* Settings popover */}
          {settingsOpen && (
            <div className="absolute bottom-16 left-4 right-4 bg-white dark:bg-[#111] border rounded-lg shadow z-50 p-2">
              <button
                onClick={logout}
                className="w-full text-left px-2 py-2 text-sm text-red-600 hover:bg-ash rounded"
              >
                Log out
              </button>
            </div>
          )}
        </div>

        {/* Collapse handle */}
        <button
          onClick={() => setIsCollapsed((v) => !v)}
          className={`
            absolute top-1/2
            -right-3
            h-10 w-6
            rounded-full bg-ash shadow
            flex items-center justify-center
            hover:bg-ash transition
          `}
          style={{ zIndex: 60 }}
        >
          {isCollapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
        </button>
      </div>
    </>
  );
};

export default SideBar;
