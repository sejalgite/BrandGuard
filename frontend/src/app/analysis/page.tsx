"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import {
  ShieldAlert,
  Search,
  RefreshCw,
  Play,
  ArrowRight,
  CheckCircle2,
  AlertTriangle,
  FileText,
  Clock,
  Layers,
  Sparkles,
  Info
} from "lucide-react";
import { listDocuments, startDocumentAnalysis, getDocumentAnalysisSummary, DocumentItem, DocumentAnalysisSummaryItem } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function AnalysisHubPage() {
  const { user, hasPermission } = useAuth();
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [summaries, setSummaries] = useState<Record<string, DocumentAnalysisSummaryItem>>({});
  const [loading, setLoading] = useState<boolean>(true);
  const [search, setSearch] = useState<string>("");
  const [analyzingId, setAnalyzingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchOverview = async () => {
    setLoading(true);
    setError(null);
    try {
      const docs = await listDocuments({ search: search.trim() || undefined });
      setDocuments(docs);

      // Load summaries for documents
      const summaryMap: Record<string, DocumentAnalysisSummaryItem> = {};
      await Promise.all(
        docs.slice(0, 15).map(async (d) => {
          try {
            const sum = await getDocumentAnalysisSummary(d.id);
            summaryMap[d.id] = sum;
          } catch {
            // Document may have no runs yet
          }
        })
      );
      setSummaries(summaryMap);
    } catch (err: any) {
      setError(err?.response?.data?.error?.message || err?.message || "Failed to load analysis hub.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOverview();
  }, [search]);

  const handleStartAnalysis = async (docId: string, versionId?: string) => {
    setAnalyzingId(docId);
    setError(null);
    try {
      await startDocumentAnalysis(docId, versionId);
      await fetchOverview();
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.response?.data?.error?.message || "Analysis failed to start.");
    } finally {
      setAnalyzingId(null);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-gray-200">
        <div>
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-blue-50 text-blue-700 rounded-xl">
              <ShieldAlert className="w-6 h-6" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-gray-900 tracking-tight">Brand Analysis Engine</h1>
              <p className="text-sm text-gray-500">
                Multi-category compliance engine: Tone, Terminology, Messaging, Visuals, Accessibility, and Fact Registry claims.
              </p>
            </div>
          </div>
        </div>

        <button
          onClick={fetchOverview}
          className="inline-flex items-center gap-2 px-3.5 py-2 border border-gray-200 text-gray-700 rounded-xl text-sm font-medium hover:bg-gray-50 transition-colors shadow-sm self-start sm:self-auto"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      {/* Error alert */}
      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-800 text-sm flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
          <div>{error}</div>
        </div>
      )}

      {/* Metric Cards Banner */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="p-5 bg-white border border-gray-200 rounded-2xl shadow-sm">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Monitored Documents</span>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-3xl font-extrabold text-gray-900">{documents.length}</span>
            <span className="text-xs text-gray-500">in repository</span>
          </div>
        </div>

        <div className="p-5 bg-white border border-gray-200 rounded-2xl shadow-sm">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Analysis Categories</span>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-3xl font-extrabold text-blue-600">6</span>
            <span className="text-xs text-gray-500">Tone, Terms, Messaging, Visual, a11y, Claims</span>
          </div>
        </div>

        <div className="p-5 bg-white border border-gray-200 rounded-2xl shadow-sm">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Engine Mode</span>
          <div className="mt-2 flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
              <CheckCircle2 className="w-3.5 h-3.5" />
              Hybrid Deterministic
            </span>
          </div>
        </div>

        <div className="p-5 bg-white border border-gray-200 rounded-2xl shadow-sm">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Active Constitution</span>
          <div className="mt-2 flex items-center gap-2">
            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-purple-50 text-purple-700 border border-purple-200">
              <Sparkles className="w-3.5 h-3.5" />
              Traceable Ground Truth
            </span>
          </div>
        </div>
      </div>

      {/* Search and Filters Bar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 bg-white p-3.5 border border-gray-200 rounded-2xl shadow-sm">
        <div className="relative flex-1">
          <Search className="w-4 h-4 text-gray-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            placeholder="Search documents by title or filename..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
          />
        </div>
      </div>

      {/* Documents Table */}
      <div className="bg-white border border-gray-200 rounded-2xl shadow-sm overflow-hidden">
        {loading ? (
          <div className="py-20 text-center">
            <div className="inline-block animate-spin w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full" />
            <p className="mt-3 text-sm text-gray-500">Loading documents and compliance records...</p>
          </div>
        ) : documents.length === 0 ? (
          <div className="py-20 text-center">
            <FileText className="w-12 h-12 text-gray-300 mx-auto mb-3" />
            <h3 className="text-base font-semibold text-gray-800">No documents found</h3>
            <p className="text-sm text-gray-500 mt-1 max-w-sm mx-auto">
              Upload marketing briefs or copy in Document Ingestion to run brand analysis.
            </p>
            <Link
              href="/documents"
              className="mt-4 inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-xl text-sm font-medium hover:bg-blue-700 transition-colors shadow-sm"
            >
              Go to Document Ingestion
            </Link>
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {documents.map((doc) => {
              const summary = summaries[doc.id];
              const latestRun = summary?.latest_run;
              const healthScore = summary?.brand_health_score;
              const isAnalyzing = analyzingId === doc.id;

              return (
                <div key={doc.id} className="p-5 flex flex-col md:flex-row md:items-center justify-between gap-4 hover:bg-gray-50/70 transition-colors">
                  <div className="space-y-1.5 flex-1 min-w-0">
                    <div className="flex items-center gap-3">
                      <Link
                        href={`/analysis/${doc.id}`}
                        className="text-base font-semibold text-gray-900 hover:text-blue-600 transition-colors truncate"
                      >
                        {doc.title}
                      </Link>
                      <span className="px-2 py-0.5 text-xs font-medium rounded-md bg-gray-100 text-gray-600 border border-gray-200">
                        {doc.content_type}
                      </span>
                      {doc.latest_version && (
                        <span className="text-xs text-gray-400 font-mono">
                          v{doc.latest_version.version_number}
                        </span>
                      )}
                    </div>

                    <div className="flex items-center gap-4 text-xs text-gray-500">
                      <span>{doc.latest_version?.word_count || 0} words</span>
                      <span>•</span>
                      <span>{doc.latest_version?.original_filename || "N/A"}</span>
                      {latestRun && (
                        <>
                          <span>•</span>
                          <span className="flex items-center gap-1 text-gray-500">
                            <Clock className="w-3.5 h-3.5" />
                            Analyzed {new Date(latestRun.started_at).toLocaleDateString()}
                          </span>
                        </>
                      )}
                    </div>
                  </div>

                  {/* Compliance Status and Actions */}
                  <div className="flex items-center gap-4 flex-shrink-0">
                    {/* Brand Health Score */}
                    {healthScore !== undefined && healthScore !== null ? (
                      <div className="text-right">
                        <div className="text-xs font-semibold uppercase tracking-wider text-gray-400">Health Score</div>
                        <div className="flex items-baseline gap-1 justify-end">
                          <span className={`text-xl font-extrabold ${healthScore >= 90 ? "text-emerald-600" : healthScore >= 70 ? "text-amber-600" : "text-red-600"}`}>
                            {healthScore}
                          </span>
                          <span className="text-xs text-gray-400">/100</span>
                        </div>
                      </div>
                    ) : (
                      <div className="text-right text-xs text-gray-400 italic">Not Analyzed</div>
                    )}

                    {/* Findings Counter */}
                    {summary?.total_findings !== undefined && summary.total_findings > 0 ? (
                      <span className="px-2.5 py-1 text-xs font-bold rounded-lg bg-red-50 text-red-700 border border-red-200">
                        {summary.total_findings} Findings
                      </span>
                    ) : summary?.latest_run?.status === "COMPLETED" ? (
                      <span className="px-2.5 py-1 text-xs font-semibold rounded-lg bg-emerald-50 text-emerald-700 border border-emerald-200 flex items-center gap-1">
                        <CheckCircle2 className="w-3.5 h-3.5" /> Clean
                      </span>
                    ) : null}

                    {/* Action Buttons */}
                    <button
                      onClick={() => handleStartAnalysis(doc.id, doc.latest_version?.id)}
                      disabled={isAnalyzing}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-xl text-xs font-semibold transition-colors shadow-sm"
                    >
                      {isAnalyzing ? (
                        <>
                          <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                          Running...
                        </>
                      ) : (
                        <>
                          <Play className="w-3.5 h-3.5" />
                          {latestRun ? "Re-Run" : "Analyze"}
                        </>
                      )}
                    </button>

                    <Link
                      href={`/analysis/${doc.id}`}
                      className="inline-flex items-center gap-1 px-3 py-1.5 border border-gray-200 text-gray-700 rounded-xl text-xs font-semibold hover:bg-gray-100 transition-colors"
                    >
                      Inspect
                      <ArrowRight className="w-3.5 h-3.5 text-gray-400" />
                    </Link>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

