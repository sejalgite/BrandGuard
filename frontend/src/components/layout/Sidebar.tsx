"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth";
import {
  LayoutDashboard,
  BookOpen,
  FileCheck2,
  FileText,
  UploadCloud,
  CheckCircle2,
  BarChart3,
  Lightbulb,
  History,
  Lock,
  LucideIcon,
  ShieldAlert,
  Palette,
  Compass,
} from "lucide-react";

interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
  badge?: string;
  requiredPermission?: string;
}

interface NavSection {
  label: string;
  requiredPermission?: string;
  items: NavItem[];
}

export const Sidebar: React.FC = () => {
  const { user, hasPermission } = useAuth();
  const pathname = usePathname();

  const navSections: NavSection[] = [
    {
      label: "Overview",
      items: [
        { label: "Executive Dashboard", href: "/", icon: LayoutDashboard },
      ],
    },
    {
      label: "Brand Constitution",
      requiredPermission: "manage_constitution",
      items: [
        { label: "Constitution Hub", href: "/constitution", icon: Compass, badge: "P0", requiredPermission: "manage_constitution" },
        { label: "Brand Rules", href: "/constitution/rules", icon: BookOpen, badge: "P0", requiredPermission: "manage_constitution" },
        { label: "Fact Registry", href: "/constitution/facts", icon: FileCheck2, badge: "P0", requiredPermission: "manage_constitution" },
        { label: "Term Bank", href: "/constitution/terms", icon: FileText, badge: "P0", requiredPermission: "manage_constitution" },
        { label: "Brand Assets", href: "/constitution/assets", icon: Palette, badge: "P0", requiredPermission: "manage_constitution" },
      ],
    },
    {
      label: "Content Review",
      items: [
        { label: "Document Ingestion", href: "/documents", icon: UploadCloud, badge: "Active", requiredPermission: "upload_docs" },
        { label: "Brand Analysis", href: "/analysis", icon: ShieldAlert, badge: "Active", requiredPermission: "run_analysis" },
        { label: "Review & Approvals", href: "/reviews", icon: CheckCircle2, badge: "Active", requiredPermission: "run_analysis" },
      ],
    },
    {
      label: "Governance Insights",
      requiredPermission: "view_analytics",
      items: [
        { label: "Governance Analytics", href: "#", icon: BarChart3, badge: "Phase 8", requiredPermission: "view_analytics" },
        { label: "Guideline Clarity Report", href: "#", icon: Lightbulb, badge: "Phase 8", requiredPermission: "view_analytics" },
      ],
    },
    {
      label: "Audit & Transparency",
      requiredPermission: "view_audit_logs",
      items: [
        { label: "Immutable Audit Trail", href: "#", icon: History, badge: "Active", requiredPermission: "view_audit_logs" },
        { label: "AI Disclosure Logs", href: "#", icon: Lock, badge: "SHA-256", requiredPermission: "view_audit_logs" },
      ],
    },
  ];

  return (
    <aside className="w-64 border-r border-slate-200 bg-white flex flex-col justify-between p-4 min-h-[calc(100vh-4rem)]">
      <div className="space-y-6">
        {navSections.map((sec, idx) => {
          if (sec.requiredPermission && !hasPermission(sec.requiredPermission)) {
            return null;
          }

          const visibleItems = sec.items.filter(
            (item) => !item.requiredPermission || hasPermission(item.requiredPermission)
          );

          if (visibleItems.length === 0) return null;

          return (
            <div key={idx}>
              <div className="px-3 mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                {sec.label}
              </div>
              <ul className="space-y-1">
                {visibleItems.map((item, itemIdx) => {
                  const Icon = item.icon;
                  const isActive = pathname === item.href;
                  return (
                    <li key={itemIdx}>
                      <Link
                        href={item.href}
                        className={`flex items-center justify-between px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                          isActive
                            ? "bg-blue-50 text-blue-700 font-semibold"
                            : "text-slate-600 hover:text-slate-900 hover:bg-slate-50"
                        }`}
                      >
                        <div className="flex items-center gap-2.5">
                          <Icon className={`h-4 w-4 ${isActive ? "text-blue-700" : "text-slate-400"}`} />
                          <span>{item.label}</span>
                        </div>
                        {item.badge && (
                          <span
                            className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${
                              item.badge === "Active"
                                ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                                : item.badge === "SHA-256"
                                ? "bg-purple-50 text-purple-700 border border-purple-200"
                                : "bg-slate-100 text-slate-600"
                            }`}
                          >
                            {item.badge}
                          </span>
                        )}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
      </div>

      <div className="p-3 bg-slate-50 rounded-xl border border-slate-200 space-y-2">
        <div className="flex items-center gap-2">
          <ShieldAlert className="h-4 w-4 text-blue-600 shrink-0" />
          <span className="text-xs font-bold text-slate-800">RBAC Enforced</span>
        </div>
        <div className="text-[11px] text-slate-500 space-y-0.5">
          <div className="flex justify-between">
            <span>Active Role:</span>
            <span className="font-semibold text-slate-700 font-mono text-[10px]">
              {user?.role || "GUEST"}
            </span>
          </div>
          <div className="flex justify-between">
            <span>Isolation:</span>
            <span className="text-emerald-700 font-semibold">Tenant-Scoped</span>
          </div>
        </div>
      </div>
    </aside>
  );
};
