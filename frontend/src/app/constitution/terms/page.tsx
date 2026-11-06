"use client";

import React, { useEffect, useState } from "react";
import { Navbar } from "@/components/layout/Navbar";
import { Sidebar } from "@/components/layout/Sidebar";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { useAuth } from "@/lib/auth";
import {
  listTerms,
  createTerm,
  TermBankItem,
  EntityStatus,
} from "@/lib/api";
import {
  FileText,
  Plus,
  Search,
  Loader2,
  AlertCircle,
  X,
  ArrowRight,
  CheckCircle2,
  XCircle,
} from "lucide-react";

function StatusBadge({ status }: { status: EntityStatus }) {
  const map: Record<EntityStatus, string> = {
    ACTIVE: "bg-emerald-50 text-emerald-700 border-emerald-200",
    PENDING_APPROVAL: "bg-amber-50 text-amber-700 border-amber-200",
    REJECTED: "bg-red-50 text-red-700 border-red-200",
    EXPIRED: "bg-red-100 text-red-800 border-red-300",
    DRAFT: "bg-slate-100 text-slate-600 border-slate-200",
    ARCHIVED: "bg-slate-100 text-slate-500 border-slate-200",
  };
  return (
    <span
      className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${map[status] ?? "bg-slate-100 text-slate-600 border-slate-200"}`}
    >
      {status}
    </span>
  );
}

export default function TermBankPage() {
  const { hasPermission } = useAuth();
  const canManage = hasPermission("manage_constitution");

  const [terms, setTerms] = useState<TermBankItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");

  // Create modal
  const [showModal, setShowModal] = useState(false);
  const [creating, setCreating] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Form fields
  const [termCode, setTermCode] = useState("");
  const [prohibitedTerm, setProhibitedTerm] = useState("");
  const [preferredTerm, setPreferredTerm] = useState("");
  const [usageContext, setUsageContext] = useState("");
  const [isCaseSensitive, setIsCaseSensitive] = useState(false);

  const statusFilters = [
    { label: "All Statuses", value: "ALL" },
    { label: "Active", value: "ACTIVE" },
    { label: "Pending", value: "PENDING_APPROVAL" },
    { label: "Archived", value: "ARCHIVED" },
    { label: "Draft", value: "DRAFT" },
  ];

  const loadTerms = () => {
    setLoading(true);
    listTerms({
      search: search.trim() || undefined,
      status_filter: statusFilter !== "ALL" ? statusFilter : undefined,
    })
      .then((data) => setTerms(data))
      .catch((err) => console.error("Error loading terms:", err))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadTerms();
  }, [statusFilter]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    loadTerms();
  };

  const handleCreateTerm = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    if (!termCode.trim() || !prohibitedTerm.trim() || !preferredTerm.trim()) {
      setErrorMsg("Term Code, Prohibited Term, and Preferred Term are required.");
      return;
    }
    setCreating(true);
    try {
      await createTerm({
        term_code: termCode.trim().toUpperCase(),
        prohibited_term: prohibitedTerm.trim(),
        preferred_term: preferredTerm.trim(),
        usage_context: usageContext.trim() || undefined,
        is_case_sensitive: isCaseSensitive,
        status: "DRAFT",
      });
      setShowModal(false);
      resetForm();
      loadTerms();
    } catch (err: any) {
      setErrorMsg(err.response?.data?.detail || "Failed to create term.");
    } finally {
      setCreating(false);
    }
  };

  const resetForm = () => {
    setTermCode("");
    setProhibitedTerm("");
    setPreferredTerm("");
    setUsageContext("");
    setIsCaseSensitive(false);
    setErrorMsg(null);
  };

  return (
    <ProtectedRoute requiredPermission="manage_constitution">
      <div className="min-h-screen flex flex-col bg-slate-50">
        <Navbar />

        <div className="flex flex-1">
          <Sidebar />

          <main className="flex-1 p-8 max-w-7xl mx-auto space-y-6">
            {/* Top Bar */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div>
                <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight flex items-center gap-2.5">
                  <FileText className="h-6 w-6 text-purple-600" />
                  <span>Term Bank</span>
                </h1>
                <p className="text-xs text-slate-500 mt-1">
                  Manage prohibited terminology and preferred substitutions for brand compliance.
                </p>
              </div>

              {canManage && (
                <button
                  type="button"
                  onClick={() => { resetForm(); setShowModal(true); }}
                  className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-700 text-white text-xs font-semibold shadow-md shadow-purple-500/20 transition-all self-start sm:self-auto"
                >
                  <Plus className="h-4 w-4" />
                  <span>New Term Pair</span>
                </button>
              )}
            </div>

            {/* Filter and Search Bar */}
            <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col md:flex-row gap-4 justify-between items-center">
              {/* Status Filter Tabs */}
              <div className="flex flex-wrap gap-1 w-full md:w-auto">
                {statusFilters.map((sf) => (
                  <button
                    key={sf.value}
                    type="button"
                    onClick={() => setStatusFilter(sf.value)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                      statusFilter === sf.value
                        ? "bg-purple-600 text-white font-semibold"
                        : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                    }`}
                  >
                    {sf.label}
                  </button>
                ))}
              </div>

              {/* Search */}
              <form onSubmit={handleSearchSubmit} className="flex gap-2 w-full md:w-72">
                <div className="relative flex-1">
                  <Search className="h-3.5 w-3.5 text-slate-400 absolute left-3 top-3" />
                  <input
                    type="text"
                    placeholder="Search terms..."
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    className="w-full text-xs pl-8 pr-3 py-2 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  />
                </div>
                <button
                  type="submit"
                  className="px-3 py-2 bg-slate-900 text-white text-xs font-semibold rounded-lg hover:bg-slate-800"
                >
                  Search
                </button>
              </form>
            </div>

            {/* Legend */}
            <div className="flex items-center gap-4 text-xs text-slate-500">
              <div className="flex items-center gap-1.5">
                <XCircle className="h-3.5 w-3.5 text-red-500" />
                <span>Prohibited term</span>
              </div>
              <div className="flex items-center gap-1.5">
                <ArrowRight className="h-3.5 w-3.5 text-slate-400" />
                <span>Preferred substitute</span>
              </div>
              <div className="flex items-center gap-1.5">
                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                <span>Preferred term</span>
              </div>
            </div>

            {/* Terms List */}
            {loading ? (
              <div className="bg-white p-12 rounded-2xl border border-slate-200 text-center space-y-3">
                <Loader2 className="h-6 w-6 animate-spin text-purple-600 mx-auto" />
                <p className="text-xs text-slate-500">Loading term bank...</p>
              </div>
            ) : terms.length === 0 ? (
              <div className="bg-white p-12 rounded-2xl border border-slate-200 text-center space-y-3">
                <FileText className="h-8 w-8 text-slate-300 mx-auto" />
                <h3 className="text-sm font-bold text-slate-800">No Terms Found</h3>
                <p className="text-xs text-slate-500 max-w-sm mx-auto">
                  Click &ldquo;New Term Pair&rdquo; or seed ApexCloud demo data from the Constitution Overview page.
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {terms.map((term) => (
                  <div
                    key={term.id}
                    className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm hover:border-slate-300 transition-all"
                  >
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                      {/* Code + Pair */}
                      <div className="flex flex-col sm:flex-row sm:items-center gap-3 flex-1">
                        <span className="font-mono text-xs font-bold px-2 py-0.5 rounded bg-slate-100 text-slate-800 border border-slate-200 self-start">
                          {term.term_code}
                        </span>

                        <div className="flex items-center gap-2 flex-wrap">
                          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-50 border border-red-200">
                            <XCircle className="h-3 w-3 text-red-500 shrink-0" />
                            <span className={`text-xs font-semibold text-red-800 ${term.is_case_sensitive ? "font-mono" : ""}`}>
                              {term.prohibited_term}
                            </span>
                          </div>

                          <ArrowRight className="h-4 w-4 text-slate-400 shrink-0" />

                          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-50 border border-emerald-200">
                            <CheckCircle2 className="h-3 w-3 text-emerald-500 shrink-0" />
                            <span className="text-xs font-semibold text-emerald-800">{term.preferred_term}</span>
                          </div>
                        </div>

                        {term.is_case_sensitive && (
                          <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-500 border border-slate-200 self-start">
                            Case-Sensitive
                          </span>
                        )}
                      </div>

                      {/* Status */}
                      <StatusBadge status={term.status} />
                    </div>

                    {term.usage_context && (
                      <p className="mt-2.5 text-xs text-slate-500 leading-relaxed pl-1 border-l-2 border-purple-200">
                        {term.usage_context}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </main>
        </div>
      </div>

      {/* Create Term Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-sm">
          <div className="bg-white rounded-2xl max-w-lg w-full p-6 space-y-4 shadow-2xl border border-slate-100">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <FileText className="h-5 w-5 text-purple-600" />
                <span>Add Term Pair</span>
              </h3>
              <button type="button" onClick={() => setShowModal(false)} className="text-slate-400 hover:text-slate-700">
                <X className="h-5 w-5" />
              </button>
            </div>

            {errorMsg && (
              <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700 flex items-center gap-2">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span>{errorMsg}</span>
              </div>
            )}

            <form onSubmit={handleCreateTerm} className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Term Code</label>
                <input
                  type="text"
                  placeholder="e.g. TERM-01"
                  value={termCode}
                  onChange={(e) => setTermCode(e.target.value.toUpperCase())}
                  className="w-full text-xs px-3 py-2 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-purple-500 font-mono"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    <span className="text-red-600">✗</span> Prohibited Term
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. cutting-edge"
                    value={prohibitedTerm}
                    onChange={(e) => setProhibitedTerm(e.target.value)}
                    className="w-full text-xs px-3 py-2 rounded-lg border border-red-200 focus:outline-none focus:ring-2 focus:ring-red-400"
                    required
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    <span className="text-emerald-600">✓</span> Preferred Term
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. purpose-built"
                    value={preferredTerm}
                    onChange={(e) => setPreferredTerm(e.target.value)}
                    className="w-full text-xs px-3 py-2 rounded-lg border border-emerald-200 focus:outline-none focus:ring-2 focus:ring-emerald-400"
                    required
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Usage Context (optional)</label>
                <textarea
                  rows={2}
                  placeholder="Explain when and why this term is prohibited..."
                  value={usageContext}
                  onChange={(e) => setUsageContext(e.target.value)}
                  className="w-full text-xs px-3 py-2 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>

              <div className="flex items-center gap-2">
                <input
                  id="caseSensitive"
                  type="checkbox"
                  checked={isCaseSensitive}
                  onChange={(e) => setIsCaseSensitive(e.target.checked)}
                  className="h-4 w-4 rounded border-slate-300 text-purple-600 focus:ring-purple-500"
                />
                <label htmlFor="caseSensitive" className="text-xs font-semibold text-slate-700">
                  Case-sensitive matching
                </label>
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-lg"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creating}
                  className="px-4 py-2 text-xs font-semibold bg-purple-600 hover:bg-purple-700 text-white rounded-lg shadow-sm flex items-center gap-1.5 disabled:opacity-70"
                >
                  {creating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Save Term Pair"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </ProtectedRoute>
  );
}

