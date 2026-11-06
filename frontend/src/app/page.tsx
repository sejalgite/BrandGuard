"use client";

import React, { useEffect, useState } from "react";
import { Navbar } from "@/components/layout/Navbar";
import { Sidebar } from "@/components/layout/Sidebar";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { useAuth } from "@/lib/auth";
import { fetchHealth, SystemHealth, apiListAuditLogs, AuditLogItem } from "@/lib/api";
import {
  ShieldCheck,
  Database,
  Layers,
  CheckCircle,
  Clock,
  Sparkles,
  ArrowRight,
  Server,
  Terminal,
  Lock,
  UserCheck,
  History,
  KeyRound,
} from "lucide-react";

export default function Home() {
  const { user, hasPermission } = useAuth();
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [auditLogs, setAuditLogs] = useState<AuditLogItem[]>([]);
  const [loadingLogs, setLoadingLogs] = useState<boolean>(false);

  useEffect(() => {
    fetchHealth()
      .then((data) => {
        setHealth(data);
        setLoading(false);
      })
      .catch((err) => {
        console.error("Health fetch error:", err);
        setError("Could not connect to FastAPI backend at http://localhost:8000/api/v1");
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    if (user && hasPermission("view_audit_logs")) {
      setLoadingLogs(true);
      apiListAuditLogs(5)
        .then((logs) => setAuditLogs(logs))
        .catch((e) => console.warn("Failed to load audit logs:", e))
        .finally(() => setLoadingLogs(false));
    }
  }, [user, hasPermission]);

  const roadmapPhases = [
    { id: "Phase 0", title: "PRD & SQL Integrity Architecture", status: "COMPLETED", date: "Verified" },
    { id: "Phase 1", title: "Project Foundation & Database Core", status: "COMPLETED", date: "Active" },
    { id: "Phase 2", title: "Authentication & 7-Role RBAC", status: "COMPLETED", date: "Active" },
    { id: "Phase 3", title: "Brand Constitution & Fact Registry", status: "PENDING", date: "Upcoming" },
    { id: "Phase 4", title: "Multi-Format Ingestion & OCR", status: "PENDING", date: "Upcoming" },
    { id: "Phase 5", title: "6-Category Engine & Verifier Gate", status: "PENDING", date: "Upcoming" },
    { id: "Phase 6", title: "Intent Lock & Diff Corrections", status: "PENDING", date: "Upcoming" },
    { id: "Phase 7", title: "Review Workflow & Version Locking", status: "PENDING", date: "Upcoming" },
    { id: "Phase 8", title: "Governance Dashboard & Clarity Report", status: "PENDING", date: "Upcoming" },
    { id: "Phase 9", title: "40-Document Benchmark & Demo", status: "PENDING", date: "Upcoming" },
  ];

  return (
    <ProtectedRoute>
      <div className="min-h-screen flex flex-col bg-slate-50">
        <Navbar systemStatus={loading ? "loading" : health ? "healthy" : "degraded"} />

        <div className="flex flex-1">
          <Sidebar />

          <main className="flex-1 p-8 max-w-7xl mx-auto space-y-8">
            {/* Welcome Banner */}
            <div className="rounded-2xl bg-gradient-to-r from-blue-900 via-indigo-900 to-slate-900 p-8 text-white shadow-xl relative overflow-hidden">
              <div className="relative z-10 max-w-3xl space-y-3">
                <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-500/20 text-blue-300 text-xs font-semibold backdrop-blur-sm border border-blue-400/20">
                  <Sparkles className="h-3.5 w-3.5 text-blue-300" />
                  <span>Phase 2 RBAC & Auth Active</span>
                </div>
                <h1 className="text-3xl font-extrabold tracking-tight">
                  BrandGuard Governance Platform
                </h1>
                <p className="text-slate-300 text-sm leading-relaxed">
                  Pre-publication brand governance grounded in a structured, citable Brand Constitution.
                  Authenticated under organisation ID:{" "}
                  <span className="font-mono text-blue-300 bg-blue-950/60 px-2 py-0.5 rounded text-xs">
                    {user?.organization_id}
                  </span>
                </p>
              </div>
              <div className="absolute right-0 bottom-0 translate-x-10 translate-y-10 opacity-10 pointer-events-none">
                <ShieldCheck className="h-96 w-96 text-white" />
              </div>
            </div>

            {/* Authenticated User & RBAC Status Grid */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {/* User Profile Card */}
              <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm space-y-3">
                <div className="flex items-center justify-between">
                  <div className="h-10 w-10 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center">
                    <UserCheck className="h-5 w-5" />
                  </div>
                  <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200">
                    {user?.role}
                  </span>
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-900">{user?.full_name}</h3>
                  <p className="text-xs text-slate-500">{user?.email}</p>
                </div>
                <div className="pt-2 border-t border-slate-100 text-xs text-slate-600 space-y-1">
                  <div className="flex justify-between">
                    <span>Account Status:</span>
                    <span className="text-emerald-600 font-semibold">Active</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Password Hash:</span>
                    <span className="font-mono text-slate-700">Argon2id</span>
                  </div>
                </div>
              </div>

              {/* RBAC Permissions Card */}
              <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm space-y-3">
                <div className="flex items-center justify-between">
                  <div className="h-10 w-10 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center">
                    <KeyRound className="h-5 w-5" />
                  </div>
                  <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200">
                    {user?.permissions?.length || 0} Permissions
                  </span>
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-900">Role Capabilities</h3>
                  <p className="text-xs text-slate-500">FastAPI dependency guards</p>
                </div>
                <div className="pt-2 border-t border-slate-100 flex flex-wrap gap-1">
                  {user?.permissions?.slice(0, 4).map((p) => (
                    <span
                      key={p}
                      className="text-[10px] bg-slate-100 text-slate-700 px-1.5 py-0.5 rounded font-mono"
                    >
                      {p}
                    </span>
                  ))}
                  {(user?.permissions?.length || 0) > 4 && (
                    <span className="text-[10px] text-slate-400 self-center">
                      +{(user?.permissions?.length || 0) - 4} more
                    </span>
                  )}
                </div>
              </div>

              {/* Database & Security Card */}
              <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm space-y-3">
                <div className="flex items-center justify-between">
                  <div className="h-10 w-10 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center">
                    <Database className="h-5 w-5" />
                  </div>
                  <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
                    PostgreSQL 18
                  </span>
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-900">Tenant Isolation</h3>
                  <p className="text-xs text-slate-500">Composite foreign keys & triggers</p>
                </div>
                <div className="pt-2 border-t border-slate-100 text-xs text-slate-600 space-y-1">
                  <div className="flex justify-between">
                    <span>Audit Immutability:</span>
                    <span className="font-semibold text-emerald-600">Trigger Enforced</span>
                  </div>
                  <div className="flex justify-between">
                    <span>pgvector:</span>
                    <span className="font-mono text-slate-700">v0.8.6 Active</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Audit Trail Section for Authorized Users */}
            {hasPermission("view_audit_logs") && (
              <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <History className="h-5 w-5 text-indigo-600" />
                    <h3 className="text-sm font-bold text-slate-900">
                      Recent Audit Trail (Tenant-Scoped)
                    </h3>
                  </div>
                  <span className="text-xs text-slate-400">Append-Only Immutability Active</span>
                </div>

                {loadingLogs ? (
                  <p className="text-xs text-slate-400">Loading audit trail...</p>
                ) : auditLogs.length === 0 ? (
                  <p className="text-xs text-slate-400">No audit events recorded yet.</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs">
                      <thead>
                        <tr className="border-b border-slate-100 text-slate-400 uppercase text-[10px]">
                          <th className="py-2">Timestamp</th>
                          <th className="py-2">Action</th>
                          <th className="py-2">Target Entity</th>
                          <th className="py-2">Actor ID</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100 font-mono text-[11px]">
                        {auditLogs.map((log) => (
                          <tr key={log.id} className="hover:bg-slate-50">
                            <td className="py-2 text-slate-500">
                              {new Date(log.timestamp).toLocaleString()}
                            </td>
                            <td className="py-2 font-bold text-blue-700">{log.action}</td>
                            <td className="py-2 text-slate-700">{log.target_entity}</td>
                            <td className="py-2 text-slate-400 truncate max-w-[120px]">
                              {log.actor_id || "SYSTEM"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}

            {/* Engineering Roadmap Section */}
            <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-base font-bold text-slate-900">9-Phase Engineering Delivery</h2>
                  <p className="text-xs text-slate-500">National-level hackathon SaaS milestones</p>
                </div>
                <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-blue-50 text-blue-700 border border-blue-200">
                  Phase 2 Active
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-3 pt-2">
                {roadmapPhases.map((phase) => (
                  <div
                    key={phase.id}
                    className={`p-3 rounded-lg border text-xs space-y-2 transition-all ${
                      phase.status === "COMPLETED"
                        ? "border-emerald-200 bg-emerald-50/50"
                        : "border-slate-200 bg-slate-50"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-slate-900">{phase.id}</span>
                      {phase.status === "COMPLETED" ? (
                        <CheckCircle className="h-4 w-4 text-emerald-600" />
                      ) : (
                        <Clock className="h-4 w-4 text-slate-400" />
                      )}
                    </div>
                    <p className="text-[11px] text-slate-600 font-medium leading-tight line-clamp-2">
                      {phase.title}
                    </p>
                    <span
                      className={`inline-block text-[10px] font-semibold px-1.5 py-0.5 rounded ${
                        phase.status === "COMPLETED"
                          ? "bg-emerald-100 text-emerald-800"
                          : "bg-slate-200 text-slate-600"
                      }`}
                    >
                      {phase.date}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </main>
        </div>
      </div>
    </ProtectedRoute>
  );
}
