"use client";

import React, { useEffect, useState } from "react";
import { Navbar } from "@/components/layout/Navbar";
import { Sidebar } from "@/components/layout/Sidebar";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { useAuth } from "@/lib/auth";
import {
  listBrandRules,
  createBrandRule,
  submitBrandRule,
  approveBrandRule,
  rejectBrandRule,
  BrandRule,
  RuleCategory,
  EntityStatus,
} from "@/lib/api";
import {
  BookOpen,
  Plus,
  Search,
  Filter,
  CheckCircle,
  XCircle,
  Send,
  Loader2,
  AlertCircle,
  Check,
  ChevronRight,
  ShieldAlert,
} from "lucide-react";

export default function BrandRulesPage() {
  const { user, hasPermission } = useAuth();
  const [rules, setRules] = useState<BrandRule[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [search, setSearch] = useState<string>("");
  const [selectedCategory, setSelectedCategory] = useState<string>("ALL");
  const [selectedStatus, setSelectedStatus] = useState<string>("ALL");

  // Create Modal State
  const [showModal, setShowModal] = useState<boolean>(false);
  const [ruleCode, setRuleCode] = useState<string>("");
  const [category, setCategory] = useState<RuleCategory>("TONE_VOICE");
  const [title, setTitle] = useState<string>("");
  const [description, setDescription] = useState<string>("");
  const [positiveExample, setPositiveExample] = useState<string>("");
  const [negativeExample, setNegativeExample] = useState<string>("");
  const [creating, setCreating] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const canApprove = hasPermission("manage_constitution");

  const loadRules = () => {
    setLoading(true);
    listBrandRules({
      category: selectedCategory !== "ALL" ? selectedCategory : undefined,
      status_filter: selectedStatus !== "ALL" ? selectedStatus : undefined,
      search: search.trim() || undefined,
    })
      .then((data) => setRules(data))
      .catch((err) => console.error("Error loading rules:", err))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadRules();
  }, [selectedCategory, selectedStatus]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    loadRules();
  };

  const handleCreateRule = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    if (!ruleCode.trim() || !title.trim() || !description.trim()) {
      setErrorMsg("Rule Code, Title, and Description are required.");
      return;
    }

    setCreating(true);
    try {
      await createBrandRule({
        rule_code: ruleCode.trim().toUpperCase(),
        category,
        title: title.trim(),
        description: description.trim(),
        examples_positive: positiveExample.trim() ? [positiveExample.trim()] : [],
        examples_negative: negativeExample.trim() ? [negativeExample.trim()] : [],
        status: "DRAFT",
      });
      setShowModal(false);
      setRuleCode("");
      setTitle("");
      setDescription("");
      setPositiveExample("");
      setNegativeExample("");
      loadRules();
    } catch (err: any) {
      setErrorMsg(err.response?.data?.detail || "Failed to create brand rule.");
    } finally {
      setCreating(false);
    }
  };

  const handleSubmitForReview = async (id: string) => {
    try {
      await submitBrandRule(id);
      loadRules();
    } catch (err) {
      console.error(err);
    }
  };

  const handleApprove = async (id: string) => {
    try {
      await approveBrandRule(id);
      loadRules();
    } catch (err) {
      console.error(err);
    }
  };

  const handleReject = async (id: string) => {
    try {
      await rejectBrandRule(id);
      loadRules();
    } catch (err) {
      console.error(err);
    }
  };

  const categories: { label: string; value: string }[] = [
    { label: "All Categories", value: "ALL" },
    { label: "Tone & Voice", value: "TONE_VOICE" },
    { label: "Writing Style", value: "WRITING_STYLE" },
    { label: "Messaging Pillar", value: "MESSAGING_PILLAR" },
    { label: "Visual Identity", value: "VISUAL" },
    { label: "Accessibility", value: "ACCESSIBILITY" },
  ];

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
                  <BookOpen className="h-6 w-6 text-blue-600" />
                  <span>Brand Rules Management</span>
                </h1>
                <p className="text-xs text-slate-500 mt-1">
                  Active rules are evaluated during document and marketing copy ingestion.
                </p>
              </div>

              <button
                type="button"
                onClick={() => {
                  setErrorMsg(null);
                  setShowModal(true);
                }}
                className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold shadow-md shadow-blue-500/20 transition-all self-start sm:self-auto"
              >
                <Plus className="h-4 w-4" />
                <span>New Brand Rule</span>
              </button>
            </div>

            {/* Filter and Search Bar */}
            <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col md:flex-row gap-4 justify-between items-center">
              {/* Category tabs */}
              <div className="flex flex-wrap gap-1 w-full md:w-auto">
                {categories.map((c) => (
                  <button
                    key={c.value}
                    type="button"
                    onClick={() => setSelectedCategory(c.value)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                      selectedCategory === c.value
                        ? "bg-blue-600 text-white font-semibold"
                        : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                    }`}
                  >
                    {c.label}
                  </button>
                ))}
              </div>

              {/* Search Box */}
              <form onSubmit={handleSearchSubmit} className="flex gap-2 w-full md:w-72">
                <div className="relative flex-1">
                  <Search className="h-3.5 w-3.5 text-slate-400 absolute left-3 top-3" />
                  <input
                    type="text"
                    placeholder="Search rules..."
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    className="w-full text-xs pl-8 pr-3 py-2 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500"
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

            {/* Rules List Table/Grid */}
            {loading ? (
              <div className="bg-white p-12 rounded-2xl border border-slate-200 text-center space-y-3">
                <Loader2 className="h-6 w-6 animate-spin text-blue-600 mx-auto" />
                <p className="text-xs text-slate-500">Loading brand rules...</p>
              </div>
            ) : rules.length === 0 ? (
              <div className="bg-white p-12 rounded-2xl border border-slate-200 text-center space-y-3">
                <BookOpen className="h-8 w-8 text-slate-300 mx-auto" />
                <h3 className="text-sm font-bold text-slate-800">No Brand Rules Found</h3>
                <p className="text-xs text-slate-500 max-w-sm mx-auto">
                  Click &ldquo;New Brand Rule&rdquo; or seed ApexCloud demo data from the Constitution Overview page.
                </p>
              </div>
            ) : (
              <div className="space-y-4">
                {rules.map((rule) => (
                  <div
                    key={rule.id}
                    className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm hover:border-slate-300 transition-all space-y-3"
                  >
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                      <div className="flex items-center gap-2.5">
                        <span className="font-mono text-xs font-bold px-2 py-0.5 rounded bg-slate-100 text-slate-800 border border-slate-200">
                          {rule.rule_code}
                        </span>
                        <h2 className="text-sm font-bold text-slate-900">{rule.title}</h2>
                        <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-blue-50 text-blue-700">
                          {rule.category}
                        </span>
                      </div>

                      {/* Status and Action Buttons */}
                      <div className="flex items-center gap-2 self-end sm:self-auto">
                        <span
                          className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${
                            rule.status === "ACTIVE"
                              ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                              : rule.status === "PENDING_APPROVAL"
                              ? "bg-amber-50 text-amber-700 border-amber-200"
                              : rule.status === "REJECTED"
                              ? "bg-red-50 text-red-700 border-red-200"
                              : "bg-slate-100 text-slate-600 border-slate-200"
                          }`}
                        >
                          {rule.status}
                        </span>

                        {rule.status === "DRAFT" && (
                          <button
                            type="button"
                            onClick={() => handleSubmitForReview(rule.id)}
                            className="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-semibold text-blue-700 bg-blue-50 hover:bg-blue-100 rounded-lg transition-colors border border-blue-200"
                          >
                            <Send className="h-3 w-3" />
                            <span>Submit</span>
                          </button>
                        )}

                        {canApprove && (rule.status === "PENDING_APPROVAL" || rule.status === "DRAFT") && (
                          <>
                            <button
                              type="button"
                              onClick={() => handleApprove(rule.id)}
                              className="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-semibold text-emerald-700 bg-emerald-50 hover:bg-emerald-100 rounded-lg transition-colors border border-emerald-200"
                            >
                              <Check className="h-3 w-3" />
                              <span>Approve</span>
                            </button>
                            <button
                              type="button"
                              onClick={() => handleReject(rule.id)}
                              className="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-semibold text-red-700 bg-red-50 hover:bg-red-100 rounded-lg transition-colors border border-red-200"
                            >
                              <XCircle className="h-3 w-3" />
                              <span>Reject</span>
                            </button>
                          </>
                        )}
                      </div>
                    </div>

                    <p className="text-xs text-slate-600 leading-relaxed">{rule.description}</p>

                    {/* Positive / Negative Examples */}
                    {(rule.examples_positive?.length || rule.examples_negative?.length) ? (
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-2 border-t border-slate-100">
                        {rule.examples_positive?.length ? (
                          <div className="p-2.5 rounded-lg bg-emerald-50/50 border border-emerald-100 space-y-1">
                            <span className="text-[10px] font-bold text-emerald-800 uppercase flex items-center gap-1">
                              <CheckCircle className="h-3 w-3 text-emerald-600" />
                              Compliant Example
                            </span>
                            <p className="text-[11px] text-emerald-900 italic">
                              &ldquo;{rule.examples_positive[0]}&rdquo;
                            </p>
                          </div>
                        ) : null}

                        {rule.examples_negative?.length ? (
                          <div className="p-2.5 rounded-lg bg-red-50/50 border border-red-100 space-y-1">
                            <span className="text-[10px] font-bold text-red-800 uppercase flex items-center gap-1">
                              <XCircle className="h-3 w-3 text-red-600" />
                              Violation Example
                            </span>
                            <p className="text-[11px] text-red-900 italic">
                              &ldquo;{rule.examples_negative[0]}&rdquo;
                            </p>
                          </div>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            )}

            {/* Create Rule Modal */}
            {showModal && (
              <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-sm">
                <div className="bg-white rounded-2xl max-w-lg w-full p-6 space-y-4 shadow-2xl border border-slate-100 animate-in fade-in zoom-in duration-150">
                  <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                    <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                      <BookOpen className="h-5 w-5 text-blue-600" />
                      <span>Create Draft Brand Rule</span>
                    </h3>
                    <button
                      type="button"
                      onClick={() => setShowModal(false)}
                      className="text-slate-400 hover:text-slate-700"
                    >
                      ✕
                    </button>
                  </div>

                  {errorMsg && (
                    <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700 flex items-center gap-2">
                      <AlertCircle className="h-4 w-4 shrink-0" />
                      <span>{errorMsg}</span>
                    </div>
                  )}

                  <form onSubmit={handleCreateRule} className="space-y-3">
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="block text-xs font-semibold text-slate-700 mb-1">Rule Code</label>
                        <input
                          type="text"
                          placeholder="e.g. TONE-01"
                          value={ruleCode}
                          onChange={(e) => setRuleCode(e.target.value.toUpperCase())}
                          className="w-full text-xs px-3 py-2 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono"
                          required
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-semibold text-slate-700 mb-1">Category</label>
                        <select
                          value={category}
                          onChange={(e) => setCategory(e.target.value as RuleCategory)}
                          className="w-full text-xs px-3 py-2 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
                        >
                          <option value="TONE_VOICE">Tone & Voice</option>
                          <option value="WRITING_STYLE">Writing Style</option>
                          <option value="MESSAGING_PILLAR">Messaging Pillar</option>
                          <option value="VISUAL">Visual Identity</option>
                          <option value="ACCESSIBILITY">Accessibility</option>
                        </select>
                      </div>
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-slate-700 mb-1">Title</label>
                      <input
                        type="text"
                        placeholder="e.g. Active Voice in Product Descriptions"
                        value={title}
                        onChange={(e) => setTitle(e.target.value)}
                        className="w-full text-xs px-3 py-2 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500"
                        required
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-slate-700 mb-1">Description & Guidelines</label>
                      <textarea
                        rows={3}
                        placeholder="Clearly explain the brand requirement and forbidden practices..."
                        value={description}
                        onChange={(e) => setDescription(e.target.value)}
                        className="w-full text-xs px-3 py-2 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500"
                        required
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-slate-700 mb-1">Compliant Example (Positive)</label>
                      <input
                        type="text"
                        placeholder="Approved copywriting example..."
                        value={positiveExample}
                        onChange={(e) => setPositiveExample(e.target.value)}
                        className="w-full text-xs px-3 py-2 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-semibold text-slate-700 mb-1">Violation Example (Negative)</label>
                      <input
                        type="text"
                        placeholder="Forbidden wording or style example..."
                        value={negativeExample}
                        onChange={(e) => setNegativeExample(e.target.value)}
                        className="w-full text-xs px-3 py-2 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500"
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
                        className="px-4 py-2 text-xs font-semibold bg-blue-600 hover:bg-blue-700 text-white rounded-lg shadow-sm flex items-center gap-1.5"
                      >
                        {creating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Save Draft"}
                      </button>
                    </div>
                  </form>
                </div>
              </div>
            )}
          </main>
        </div>
      </div>
    </ProtectedRoute>
  );
}

