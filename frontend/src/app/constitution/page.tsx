"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { Navbar } from "@/components/layout/Navbar";
import { Sidebar } from "@/components/layout/Sidebar";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { useAuth } from "@/lib/auth";
import {
  fetchConstitutionOverview,
  seedDemoConstitution,
  ConstitutionOverview,
} from "@/lib/api";
import {
  Compass,
  BookOpen,
  FileCheck2,
  FileText,
  Palette,
  Sparkles,
  ArrowRight,
  ShieldCheck,
  CheckCircle2,
  Clock,
  AlertTriangle,
  Loader2,
  RefreshCw,
} from "lucide-react";

export default function ConstitutionOverviewPage() {
  const { hasPermission } = useAuth();
  const [overview, setOverview] = useState<ConstitutionOverview | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [seeding, setSeeding] = useState<boolean>(false);
  const [message, setMessage] = useState<string | null>(null);

  const loadData = () => {
    setLoading(true);
    fetchConstitutionOverview()
      .then((data) => setOverview(data))
      .catch((err) => console.error("Error loading constitution overview:", err))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleSeedDemo = async () => {
    setSeeding(true);
    setMessage(null);
    try {
      const res = await seedDemoConstitution();
      setMessage(res.message);
      loadData();
    } catch (err: any) {
      setMessage("Failed to seed demo data.");
    } finally {
      setSeeding(false);
    }
  };

  return (
    <ProtectedRoute requiredPermission="manage_constitution">
      <div className="min-h-screen flex flex-col bg-slate-50">
        <Navbar />

        <div className="flex flex-1">
          <Sidebar />

          <main className="flex-1 p-8 max-w-7xl mx-auto space-y-8">
            {/* Header Banner */}
            <div className="rounded-2xl bg-gradient-to-r from-blue-900 via-indigo-900 to-slate-900 p-8 text-white shadow-xl relative overflow-hidden flex flex-col md:flex-row md:items-center justify-between gap-6">
              <div className="max-w-2xl space-y-3 z-10">
                <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-500/20 text-blue-300 text-xs font-semibold backdrop-blur-sm border border-blue-400/20">
                  <Compass className="h-3.5 w-3.5" />
                  <span>Phase 3: Brand Constitution Hub</span>
                </div>
                <h1 className="text-3xl font-extrabold tracking-tight">
                  Brand Constitution & Fact Registry
                </h1>
                <p className="text-slate-300 text-sm leading-relaxed">
                  The verified, human-governed source of truth for ApexCloud Technologies.
                  Governs all marketing copy, claim verification, preferred terminology, and visual tokens.
                </p>
              </div>

              {/* Seed ApexCloud Demo Action */}
              <div className="z-10 shrink-0">
                <button
                  type="button"
                  onClick={handleSeedDemo}
                  disabled={seeding}
                  className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold shadow-lg shadow-blue-600/30 transition-all disabled:opacity-70"
                >
                  {seeding ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      <span>Seeding ApexCloud Data...</span>
                    </>
                  ) : (
                    <>
                      <Sparkles className="h-4 w-4 text-amber-300" />
                      <span>Seed ApexCloud Demo Data</span>
                    </>
                  )}
                </button>
              </div>
            </div>

            {message && (
              <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-xs text-emerald-800 flex items-center justify-between">
                <span>{message}</span>
                <button
                  onClick={() => setMessage(null)}
                  className="text-emerald-600 font-bold hover:underline"
                >
                  Dismiss
                </button>
              </div>
            )}

            {/* Metrics Grid */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
              {/* Brand Rules Card */}
              <Link
                href="/constitution/rules"
                className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm hover:shadow-md hover:border-blue-300 transition-all space-y-3 group"
              >
                <div className="flex items-center justify-between">
                  <div className="h-10 w-10 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center">
                    <BookOpen className="h-5 w-5" />
                  </div>
                  <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-blue-50 text-blue-700">
                    {overview?.approved_rules || 0} Active
                  </span>
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-900 group-hover:text-blue-600 transition-colors">
                    Brand Rules
                  </h3>
                  <p className="text-xs text-slate-500">Tone, writing style, accessibility</p>
                </div>
                <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-xs text-slate-600">
                  <span>{overview?.total_rules || 0} Total Rules</span>
                  <ArrowRight className="h-3.5 w-3.5 text-slate-400 group-hover:translate-x-1 transition-transform" />
                </div>
              </Link>

              {/* Fact Registry Card */}
              <Link
                href="/constitution/facts"
                className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm hover:shadow-md hover:border-emerald-300 transition-all space-y-3 group"
              >
                <div className="flex items-center justify-between">
                  <div className="h-10 w-10 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center">
                    <FileCheck2 className="h-5 w-5" />
                  </div>
                  <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700">
                    {overview?.approved_facts || 0} Valid
                  </span>
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-900 group-hover:text-emerald-600 transition-colors">
                    Fact Registry
                  </h3>
                  <p className="text-xs text-slate-500">Specifications, pricing & SLAs</p>
                </div>
                <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-xs text-slate-600">
                  <span>{overview?.total_facts || 0} Facts ({overview?.expired_facts || 0} Expired)</span>
                  <ArrowRight className="h-3.5 w-3.5 text-slate-400 group-hover:translate-x-1 transition-transform" />
                </div>
              </Link>

              {/* Term Bank Card */}
              <Link
                href="/constitution/terms"
                className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm hover:shadow-md hover:border-purple-300 transition-all space-y-3 group"
              >
                <div className="flex items-center justify-between">
                  <div className="h-10 w-10 rounded-xl bg-purple-50 text-purple-600 flex items-center justify-center">
                    <FileText className="h-5 w-5" />
                  </div>
                  <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-purple-50 text-purple-700">
                    {overview?.prohibited_terms || 0} Prohibited
                  </span>
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-900 group-hover:text-purple-600 transition-colors">
                    Term Bank
                  </h3>
                  <p className="text-xs text-slate-500">Preferred vs prohibited terms</p>
                </div>
                <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-xs text-slate-600">
                  <span>{overview?.total_terms || 0} Glossary Terms</span>
                  <ArrowRight className="h-3.5 w-3.5 text-slate-400 group-hover:translate-x-1 transition-transform" />
                </div>
              </Link>

              {/* Brand Assets Card */}
              <Link
                href="/constitution/assets"
                className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm hover:shadow-md hover:border-amber-300 transition-all space-y-3 group"
              >
                <div className="flex items-center justify-between">
                  <div className="h-10 w-10 rounded-xl bg-amber-50 text-amber-600 flex items-center justify-center">
                    <Palette className="h-5 w-5" />
                  </div>
                  <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-amber-50 text-amber-700">
                    {overview?.total_assets || 0} Assets
                  </span>
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-900 group-hover:text-amber-600 transition-colors">
                    Asset Library
                  </h3>
                  <p className="text-xs text-slate-500">Brand colors, logos, graphics</p>
                </div>
                <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-xs text-slate-600">
                  <span>HEX Colors & Logos</span>
                  <ArrowRight className="h-3.5 w-3.5 text-slate-400 group-hover:translate-x-1 transition-transform" />
                </div>
              </Link>
            </div>

            {/* Constitution Integrity Statement */}
            <div className="bg-white rounded-2xl border border-slate-200 p-6 space-y-4">
              <div className="flex items-center gap-2">
                <ShieldCheck className="h-5 w-5 text-blue-600" />
                <h2 className="text-base font-bold text-slate-900">
                  Governance Source of Truth Principles
                </h2>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs text-slate-600">
                <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-1.5">
                  <span className="font-bold text-slate-800">1. Strict Human Approval Gate</span>
                  <p className="leading-relaxed">
                    AI analysis engines can suggest rules, but no rule becomes active without explicit sign-off by a Brand Manager or Admin.
                  </p>
                </div>
                <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-1.5">
                  <span className="font-bold text-slate-800">2. Real-Time Expiration Isolation</span>
                  <p className="leading-relaxed">
                    Expired facts cannot support outgoing claims as current evidence, preventing outdated pricing or deprecated statistics.
                  </p>
                </div>
                <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-1.5">
                  <span className="font-bold text-slate-800">3. Conflict Surfacing Overwrites</span>
                  <p className="leading-relaxed">
                    Contradictory facts on matching claim types are surfaced in the conflict queue rather than silently overwriting past records.
                  </p>
                </div>
              </div>
            </div>
          </main>
        </div>
      </div>
    </ProtectedRoute>
  );
}

