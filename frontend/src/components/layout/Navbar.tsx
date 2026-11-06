"use client";

import React, { useState } from "react";
import { useAuth } from "@/lib/auth";
import {
  ShieldCheck,
  Bell,
  Activity,
  LogOut,
  User as UserIcon,
  ChevronDown,
} from "lucide-react";

interface NavbarProps {
  systemStatus?: "healthy" | "degraded" | "loading";
}

export const Navbar: React.FC<NavbarProps> = ({ systemStatus = "healthy" }) => {
  const { user, logout } = useAuth();
  const [dropdownOpen, setDropdownOpen] = useState(false);

  // Generate initials from user name
  const getInitials = (name?: string) => {
    if (!name) return "BG";
    const parts = name.trim().split(" ");
    if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
    return name.slice(0, 2).toUpperCase();
  };

  return (
    <header className="h-16 border-b border-slate-200 bg-white sticky top-0 z-30 flex items-center justify-between px-6">
      <div className="flex items-center gap-3">
        <div className="h-10 w-10 rounded-xl bg-gradient-to-tr from-blue-700 to-indigo-600 flex items-center justify-center text-white shadow-md shadow-blue-500/20">
          <ShieldCheck className="h-6 w-6" />
        </div>
        <div>
          <span className="text-xl font-bold tracking-tight text-slate-900">BrandGuard</span>
          <span className="ml-2 text-xs font-semibold px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200">
            Enterprise
          </span>
        </div>
      </div>

      <div className="flex items-center gap-4">
        {/* Backend API Health Status */}
        <div className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-50 border border-slate-200 text-xs text-slate-600">
          <Activity className="h-3.5 w-3.5 text-blue-600" />
          <span>API: </span>
          {systemStatus === "healthy" ? (
            <span className="font-semibold text-emerald-600">Connected (pgvector active)</span>
          ) : systemStatus === "loading" ? (
            <span className="text-slate-400">Checking...</span>
          ) : (
            <span className="font-semibold text-amber-600">Offline</span>
          )}
        </div>

        {/* User Info & Actions */}
        {user ? (
          <div className="relative">
            <button
              type="button"
              onClick={() => setDropdownOpen(!dropdownOpen)}
              className="flex items-center gap-2.5 p-1.5 rounded-xl hover:bg-slate-100 transition-colors"
            >
              <div className="h-9 w-9 rounded-full bg-gradient-to-tr from-slate-900 to-slate-700 text-white font-semibold text-xs flex items-center justify-center shadow-sm">
                {getInitials(user.full_name)}
              </div>
              <div className="hidden md:block text-left text-xs">
                <div className="font-bold text-slate-800 leading-tight">{user.full_name}</div>
                <div className="text-[11px] text-blue-600 font-medium">{user.role}</div>
              </div>
              <ChevronDown className="h-3.5 w-3.5 text-slate-400" />
            </button>

            {dropdownOpen && (
              <div className="absolute right-0 mt-2 w-56 rounded-xl bg-white shadow-xl border border-slate-200 py-2 z-50">
                <div className="px-4 py-2 border-b border-slate-100">
                  <p className="text-xs font-bold text-slate-900">{user.full_name}</p>
                  <p className="text-[11px] text-slate-500 truncate">{user.email}</p>
                  <span className="mt-1 inline-block text-[10px] font-semibold px-2 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200">
                    {user.role}
                  </span>
                </div>
                <div className="px-4 py-2 text-[11px] text-slate-500 border-b border-slate-100">
                  <span>Permissions: </span>
                  <span className="font-semibold text-slate-700">
                    {user.permissions?.length || 0} active
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setDropdownOpen(false);
                    logout();
                  }}
                  className="w-full text-left px-4 py-2 text-xs text-red-600 hover:bg-red-50 flex items-center gap-2 transition-colors font-medium"
                >
                  <LogOut className="h-3.5 w-3.5" />
                  <span>Sign Out</span>
                </button>
              </div>
            )}
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <a
              href="/login"
              className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-colors"
            >
              Sign In
            </a>
          </div>
        )}
      </div>
    </header>
  );
};
