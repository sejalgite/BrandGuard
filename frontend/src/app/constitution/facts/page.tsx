"use client";

import React, { useEffect, useState } from "react";
import { Navbar } from "@/components/layout/Navbar";
import { Sidebar } from "@/components/layout/Sidebar";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { useAuth } from "@/lib/auth";
import {
  listFacts,
  createFact,
  approveFact,
  detectFactConflicts,
  FactRegistryItem,
  FactConflict,
  EntityStatus,
} from "@/lib/api";
import {
  FileCheck2,
  Plus,
  Search,
  Check,
  Loader2,
  AlertCircle,
  AlertTriangle,
  X,
  ShieldAlert,
  RefreshCw,
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

export default function FactRegistryPage() {
  const { hasPermission } = useAuth();
  const canApprove = hasPermission("manage_constitution");

  const [facts, setFacts] = useState<FactRegistryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [claimTypeFilter, setClaimTypeFilter] = useState("ALL");
  const [statusFilter, setStatusFilter] = useState("ALL");

  // Conflict detection
  const [conflicts, setConflicts] = useState<FactConflict[]>([]);
  const [showConflicts, setShowConflicts] = useState(false);
  const [detectingConflicts, setDetectingConflicts] = useState(false);

  // Create modal
  const [showModal, setShowModal] = useState(false);
  const [creating, setCreating] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Form fields
  const [factCode, setFactCode] = useState("");
  const [claimType, setClaimType] = useState("PERFORMANCE");
  const [statement, setStatement] = useState("");
  const [numericalValue, setNumericalValue] = useState("");
  const [unit, setUnit] = useState("");
  const [sourceReference, setSourceReference] = useState("");
  const [factOwner, setFactOwner] = useState("");
  const [expiryDate, setExpiryDate] = useState("");

  const claimTypes = [
    { label: "All Claim Types", value: "ALL" },
    { label: "Performance", value: "PERFORMANCE" },
    { label: "Pricing", value: "PRICING" },
    { label: "SLA / Uptime", value: "SLA" },
    { label: "Compliance", value: "COMPLIANCE" },
    { label: "Statistic", value: "STATISTIC" },
  ];

  const statusFilters = [
    { label: "All Statuses", value: "ALL" },
    { label: "Active", value: "ACTIVE" },
    { label: "Pending", value: "PENDING_APPROVAL" },
    { label: "Expired", value: "EXPIRED" },
    { label: "Draft", value: "DRAFT" },
  ];

  const loadFacts = () => {
    setLoading(true);
    listFacts({
      claim_type: claimTypeFilter !== "ALL" ? claimTypeFilter : undefined,
      status_filter: statusFilter !== "ALL" ? statusFilter : undefined,
      search: search.trim() || undefined,
    })
      .then((data) => setFacts(data))
      .catch((err) => console.error("Error loading facts:", err))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadFacts();
  }, [claimTypeFilter, statusFilter]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    loadFacts();
  };

  const handleApprove = async (id: string) => {
    try {
      await approveFact(id);
      loadFacts();
    } catch (err) {
      console.error(err);
    }
  };

  const handleDetectConflicts = async () => {
    setDetectingConflicts(true);
    try {
      const data = await detectFactConflicts();
      setConflicts(data);
      setShowConflicts(true);
    } catch (err) {
      console.error(err);
    } finally {
      setDetectingConflicts(false);
    }
  };

  const handleCreateFact = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    if (!factCode.trim() || !statement.trim() || !sourceReference.trim() || !factOwner.trim() || !expiryDate) {
      setErrorMsg("Fact Code, Statement, Source, Owner, and Expiry Date are required.");
      return;
    }
    setCreating(true);
    try {
      await createFact({
        fact_code: factCode.trim().toUpperCase(),
        claim_type: claimType,
        statement: statement.trim(),
        numerical_value: numericalValue ? parseFloat(numericalValue) : undefined,
        unit: unit.trim() || undefined,
        source_reference: sourceReference.trim(),
        fact_owner: factOwner.trim(),
        expiry_date: expiryDate,
        status: "DRAFT",
      });
      setShowModal(false);
      resetForm();
      loadFacts();
    } catch (err: any) {
      setErrorMsg(err.response?.data?.detail || "Failed to create fact.");
    } finally {
      setCreating(false);
    }
  };

  const resetForm = () => {
    setFactCode("");
    setClaimType("PERFORMANCE");
    setStatement("");
    setNumericalValue("");
    setUnit("");
    setSourceReference("");
    setFactOwner("");
    setExpiryDate("");
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
                  <FileCheck2 className="h-6 w-6 text-emerald-600" />
                  <span>Fact Registry</span>
                </h1>
                <p className="text-xs text-slate-500 mt-1">
                  Verified claims and statistics that govern compliant marketing content.
                </p>
              </div>

              <div className="flex items-center gap-2 self-start sm:self-auto">
                <button
                  type="button"
                  onClick={handleDetectConflicts}
                  disabled={detectingConflicts}
                  className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-amber-50 hover:bg-amber-100 text-amber-800 text-xs font-semibold border border-amber-200 transition-all disabled:opacity-70"
                >
                  {detectingConflicts ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <AlertTriangle className="h-4 w-4" />
                  )}
                  <span>Detect Conflicts</span>
                </button>
                <button
                  type="button"
                  onClick={() => { resetForm(); setShowModal(true); }}
                  className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold shadow-md shadow-emerald-500/20 transition-all"
                >
                  <Plus className="h-4 w-4" />
                  <span>New Fact</span>
                </button>
              </div>
            </div>

            {/* Filter and Search Bar */}
            <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col md:flex-row gap-4 justify-between items-center">
              {/* Claim Type Tabs */}
              <div className="flex flex-wrap gap-1 w-full md:w-auto">
                {claimTypes.map((ct) => (
                  <button
                    key={ct.value}
                    type="button"
                    onClick={() => setClaimTypeFilter(ct.value)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                      claimTypeFilter === ct.value
                        ? "bg-emerald-600 text-white font-semibold"
                        : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                    }`}
                  >
                    {ct.label}
                  </button>
                ))}
              </div>

              <div className="flex gap-2 w-full md:w-auto">
                {/* Status Filter */}
                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  className="text-xs px-3 py-2 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-emerald-500 bg-white"
                >
                  {statusFilters.map((sf) => (
                    <option key={sf.value} value={sf.value}>{sf.label}</option>
                  ))}
                </select>

                {/* Search */}
                <form onSubmit={handleSearchSubmit} className="flex gap-2 md:w-64">
                  <div className="relative flex-1">
                    <Search className="h-3.5 w-3.5 text-slate-400 absolute left-3 top-3" />
                    <input
                      type="text"
                      placeholder="Search facts..."
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                      className="w-full text-xs pl-8 pr-3 py-2 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-emerald-500"
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
            </div>

            {/* Facts Table */}
            {loading ? (
              <div className="bg-white p-12 rounded-2xl border border-slate-200 text-center space-y-3">
                <Loader2 className="h-6 w-6 animate-spin text-emerald-600 mx-auto" />
                <p className="text-xs text-slate-500">Loading fact registry...</p>
              </div>
            ) : facts.length === 0 ? (
              <div className="bg-white p-12 rounded-2xl border border-slate-200 text-center space-y-3">
                <FileCheck2 className="h-8 w-8 text-slate-300 mx-auto" />
                <h3 className="text-sm font-bold text-slate-800">No Facts Found</h3>
                <p className="text-xs text-slate-500 max-w-sm mx-auto">
                  Click &ldquo;New Fact&rdquo; or seed ApexCloud demo data from the Constitution Overview page.
                </p>
              </div>
            ) : (
              <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
                <table className="w-full text-xs">
                  <thead className="bg-slate-50 border-b border-slate-200">
                    <tr>
                      <th className="text-left px-4 py-3 text-slate-500 font-semibold w-28">Code</th>
                      <th className="text-left px-4 py-3 text-slate-500 font-semibold w-28">Type</th>
                      <th className="text-left px-4 py-3 text-slate-500 font-semibold">Statement</th>
                      <th className="text-left px-4 py-3 text-slate-500 font-semibold w-28">Value</th>
                      <th className="text-left px-4 py-3 text-slate-500 font-semibold w-28">Expiry</th>
                      <th className="text-left px-4 py-3 text-slate-500 font-semibold w-28">Status</th>
                      {canApprove && (
                        <th className="text-left px-4 py-3 text-slate-500 font-semibold w-24">Actions</th>
                      )}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {facts.map((fact) => (
                      <tr
                        key={fact.id}
                        className={`hover:bg-slate-50 transition-colors ${fact.is_expired ? "bg-red-50/30" : ""}`}
                      >
                        <td className="px-4 py-3">
                          <span className="font-mono font-bold text-slate-800 bg-slate-100 px-1.5 py-0.5 rounded">
                            {fact.fact_code}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span className="text-slate-600 font-medium">{fact.claim_type}</span>
                        </td>
                        <td className="px-4 py-3">
                          <div className="text-slate-800 leading-relaxed line-clamp-2">{fact.statement}</div>
                          <div className="text-slate-400 mt-0.5">Source: {fact.source_reference}</div>
                        </td>
                        <td className="px-4 py-3 text-slate-700">
                          {fact.numerical_value != null
                            ? `${fact.numerical_value}${fact.unit ? " " + fact.unit : ""}`
                            : "—"}
                        </td>
                        <td className="px-4 py-3">
                          <span className={fact.is_expired ? "text-red-700 font-semibold" : "text-slate-600"}>
                            {fact.expiry_date ? new Date(fact.expiry_date).toLocaleDateString() : "—"}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <StatusBadge status={fact.status} />
                        </td>
                        {canApprove && (
                          <td className="px-4 py-3">
                            {(fact.status === "PENDING_APPROVAL" || fact.status === "DRAFT") && !fact.is_expired && (
                              <button
                                type="button"
                                onClick={() => handleApprove(fact.id)}
                                className="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-semibold text-emerald-700 bg-emerald-50 hover:bg-emerald-100 rounded-lg transition-colors border border-emerald-200"
                              >
                                <Check className="h-3 w-3" />
                                Approve
                              </button>
                            )}
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </main>
        </div>
      </div>

      {/* Conflict Detection Dialog */}
      {showConflicts && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-sm">
          <div className="bg-white rounded-2xl max-w-2xl w-full p-6 space-y-4 shadow-2xl border border-slate-100 max-h-[80vh] flex flex-col">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <ShieldAlert className="h-5 w-5 text-amber-500" />
                <span>Conflict Detection Results</span>
              </h3>
              <button type="button" onClick={() => setShowConflicts(false)} className="text-slate-400 hover:text-slate-700">
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="overflow-y-auto flex-1 space-y-3">
              {conflicts.length === 0 ? (
                <div className="text-center py-8 space-y-2">
                  <Check className="h-8 w-8 text-emerald-500 mx-auto" />
                  <p className="text-sm font-semibold text-slate-700">No conflicts detected</p>
                  <p className="text-xs text-slate-500">All active facts are internally consistent.</p>
                </div>
              ) : (
                conflicts.map((conflict, idx) => (
                  <div key={idx} className="p-4 rounded-xl border border-amber-200 bg-amber-50 space-y-2">
                    <div className="flex items-center gap-2">
                      <AlertTriangle className="h-4 w-4 text-amber-600 shrink-0" />
                      <span className="text-xs font-bold text-amber-800">
                        {conflict.claim_type}: {conflict.conflict_reason}
                      </span>
                    </div>
                    <div className="space-y-1">
                      {conflict.conflicting_facts.map((f) => (
                        <div key={f.id} className="text-xs text-slate-700 pl-6">
                          <span className="font-mono font-bold">{f.fact_code}</span>: {f.statement}
                        </div>
                      ))}
                    </div>
                  </div>
                ))
              )}
            </div>
            <div className="pt-3 border-t border-slate-100 flex justify-end">
              <button
                type="button"
                onClick={() => setShowConflicts(false)}
                className="px-4 py-2 text-xs font-semibold bg-slate-900 text-white rounded-lg hover:bg-slate-800"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Create Fact Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-sm">
          <div className="bg-white rounded-2xl max-w-lg w-full p-6 space-y-4 shadow-2xl border border-slate-100">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <FileCheck2 className="h-5 w-5 text-emerald-600" />
                <span>Register New Fact</span>
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

            <form onSubmit={handleCreateFact} className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Fact Code</label>
                  <input
                    type="text"
                    placeholder="e.g. PERF-01"
                    value={factCode}
                    onChange={(e) => setFactCode(e.target.value.toUpperCase())}
                    className="w-full text-xs px-3 py-2 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-emerald-500 font-mono"
                    required
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Claim Type</label>
                  <select
                    value={claimType}
                    onChange={(e) => setClaimType(e.target.value)}
                    className="w-full text-xs px-3 py-2 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-emerald-500 bg-white"
                  >
                    <option value="PERFORMANCE">Performance</option>
                    <option value="PRICING">Pricing</option>
                    <option value="SLA">SLA / Uptime</option>
                    <option value="COMPLIANCE">Compliance</option>
                    <option value="STATISTIC">Statistic</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Statement</label>
                <textarea
                  rows={3}
                  placeholder="The verified claim or statistic..."
                  value={statement}
                  onChange={(e) => setStatement(e.target.value)}
                  className="w-full text-xs px-3 py-2 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Numerical Value (optional)</label>
                  <input
                    type="number"
                    step="any"
                    placeholder="e.g. 99.99"
                    value={numericalValue}
                    onChange={(e) => setNumericalValue(e.target.value)}
                    className="w-full text-xs px-3 py-2 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Unit (optional)</label>
                  <input
                    type="text"
                    placeholder="e.g. %, ms, GB"
                    value={unit}
                    onChange={(e) => setUnit(e.target.value)}
                    className="w-full text-xs px-3 py-2 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Source Reference</label>
                  <input
                    type="text"
                    placeholder="e.g. Q4 2024 Benchmark Report"
                    value={sourceReference}
                    onChange={(e) => setSourceReference(e.target.value)}
                    className="w-full text-xs px-3 py-2 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                    required
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Fact Owner</label>
                  <input
                    type="text"
                    placeholder="e.g. Product Marketing"
                    value={factOwner}
                    onChange={(e) => setFactOwner(e.target.value)}
                    className="w-full text-xs px-3 py-2 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                    required
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Expiry Date</label>
                <input
                  type="date"
                  value={expiryDate}
                  onChange={(e) => setExpiryDate(e.target.value)}
                  className="w-full text-xs px-3 py-2 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  required
                />
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
                  className="px-4 py-2 text-xs font-semibold bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg shadow-sm flex items-center gap-1.5 disabled:opacity-70"
                >
                  {creating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Register Fact"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </ProtectedRoute>
  );
}

