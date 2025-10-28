import React from "react";
import { Menu } from "lucide-react";

const Header = ({ isCollapsed, setIsCollapsed }) => {
  return (
    <header className="sticky top-0 z-30 bg-white border-b border-gray-200">
      <div className="px-4 py-4">
        {/* Top bar (menu + profile) */}
        <div className="flex items-center justify-between">
          {/* Mobile Menu Button */}
          <button
            onClick={() => setIsCollapsed(false)}
            className="lg:hidden p-2 hover:bg-gray-100 rounded-lg"
            aria-label="Open sidebar"
          >
            <Menu className="w-5 h-5" />
          </button>

          {/* Spacer for center alignment */}
          <div className="flex-1"></div>

          {/* User Profile (right) */}
          <div className="flex items-center space-x-3">
            <div className="hidden sm:block text-right">
              <div className="text-sm font-medium text-gray-900">
                Ashan Amarathunga
              </div>
              <div className="text-xs text-primary-accent">Subscribed</div>
            </div>
            <div className="w-8 h-8 bg-gray-300 rounded-full flex items-center justify-center">
              <span className="text-sm font-medium text-gray-600">A</span>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
};

export default Header;
