import React, { useState } from "react";
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
import { v4 as uuidv4 } from "uuid";


const SideBar = ({ isCollapsed, setIsCollapsed }) => {
  const [items, setItems] = React.useState([]);
  const navigate = useNavigate();

  // widths used both here and in the page layout
  const EXPANDED_W = "w-80";
  const COLLAPSED_W = "w-20";

  React.useEffect(() => {
    let mounted = true;
    import("../../lib/api").then(({ chats }) => {
      chats.list().then((list) => {
        if (mounted) setItems(list.filter(c => !c.archived));
      }).catch(console.error);
    });
    return () => { mounted = false; };
  }, []);

  const newChat = async () => {
    const { chats } = await import("../../lib/api");
    const c = await chats.create();
    setItems(prev => [c, ...prev]);
    navigate(`/${c.id}`);
  };

  return (
    <>
      {/* Dim overlay on mobile ONLY when expanded (so user can tap outside to close) */}
      {!isCollapsed && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={() => setIsCollapsed(true)}
        />
      )}

      {/* Sidebar */}
      <div
        className={`fixed left-0 top-0 h-full bg-light-ash border-gray-200 z-50 transition-all duration-300 ease-in-out
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
                <img
                  src={LOGO}
                  alt="Logo"
                  className="h-10 object-contain shrink-0 select-none"
                  loading="eager"
                />
              </div>
              {/* Close only shows on mobile */}
              <button
                onClick={() => setIsCollapsed(true)}
                className="lg:hidden p-1 hover:bg-ash rounded"
                aria-label="Collapse"
              >
                <X className="w-5 h-5" />
              </button>
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
            <h3 className="text-sm font-bold text-gray-500 tracking-wide mb-3">
              Chats
            </h3>
            <div className="space-y-1">
              {items.map((c) => (
                <div
                  key={c.id}
                  onClick={() => navigate(`/${c.id}`)}
                  className="group flex items-center justify-between p-3 hover:bg-ash rounded-lg cursor-pointer"
                >
                  <span className="text-gray-700 text-sm truncate flex-1">
                    {c.title || "Untitled chat"}
                  </span>
                  {/* {c.hasMenu && (
                    <button className="opacity-0 group-hover:opacity-100 p-1 hover:bg-ash rounded transition-opacity">
                      <MoreHorizontal className="w-4 h-4 text-gray-500" />
                    </button>
                  )} */}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Chats list */}
        {/* <div className="px-4">
          {!isCollapsed && (
            <h3 className="text-sm font-bold text-gray-500 tracking-wide mb-3">Chats</h3>
          )}
          <div className="space-y-1">
            {items.map((c) => (
              <div
                key={c.id}
                onClick={() => navigate(`/${c.id}`)}
                className="group flex items-center justify-between p-3 hover:bg-ash rounded-lg cursor-pointer"
              >
                <span className="text-gray-700 text-sm truncate flex-1">{c.title || "Untitled chat"}</span>
              </div>
            ))}
          </div>
        </div> */}

        {/* Settings bottom */}
        <div className="absolute bottom-0 left-0 right-0 p-4 border-t border-gray-200">
          <button
            className={`w-full flex items-center space-x-3 p-3 text-gray-700 hover:bg-ash rounded-lg transition-colors ${
              isCollapsed ? "justify-center" : "justify-start"
            }`}
          >
            <img
              src={SETTINGS}
              alt="Settings"
              className="h-6 object-contain shrink-0 select-none"
              loading="eager"
            />
            {!isCollapsed && <span className="font-medium">Settings</span>}
          </button>
        </div>

        {/* ==== Edge Collapse Handle (always visible) ==== */}
        <button
          onClick={() => setIsCollapsed((v) => !v)}
          aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          className={`
            absolute top-1/2 -translate-y-1/2
            -right-3
            h-10 w-6
            rounded-full bg-ash shadow
            flex items-center justify-center
            hover:bg-ash transition
          `}
          // make sure it sits above content but below overlay
          style={{ zIndex: 60 }}
        >
          {isCollapsed ? (
            <ChevronRight className="h-4 w-4" />
          ) : (
            <ChevronLeft className="h-4 w-4" />
          )}
        </button>


      </div>
    </>
  );
};

export default SideBar;

