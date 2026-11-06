"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ShieldAlert,
  ArrowLeft,
  RefreshCw,
  Play,
  CheckCircle2,
  AlertTriangle,
  AlertOctagon,
  HelpCircle,
  FileText,
  Clock,
  Filter,
  Check,
  X,
  Sparkles,
  ExternalLink,
  Tag,
  Quote,
  Eye,
  ChevronRight
} from "lucide-react";
import {
  getDocumentDetails,
  listDocumentAnalysisRuns,
  getRunFindings,
  updateFindingStatus,
  startDocumentAnalysis,
  DocumentItem,
  AnalysisRunItem,
  FindingItem
} from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function DocumentAnalysisPage() {
  const params = useParams();
  const docId = params.id as string;
  const { user, hasPermission } = useAuth();

  const [document, setDocument] = useState<DocumentItem | null>(null);
  const [runs, setRuns] = useState<AnalysisRunItem[]>([]);
  const [activeRun, setActiveRun] = useState<AnalysisRunItem | null>(null);
  const [findings, setFindings] = useState<FindingItem[]>([]);
  const [selectedFinding, setSelectedFinding] = useState<FindingItem | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [analyzing, setAnalyzing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [categoryFilter, setCategoryFilter] = useState<string>("ALL");
  const [severityFilter, setSeverityFilter] = useState<string>("ALL");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const doc = await getDocumentDetails(docId);
      setDocument(doc);

      const runList = await listDocumentAnalysisRuns(docId);
      setRuns(runList);

      if (runList.length > 0) {
        const latest = runList[0];
        setActiveRun(latest);
        const fList = await getRunFindings(latest.id);
        setFindings(fList);
        if (fList.length > 0) {
          setSelectedFinding(fList[0]);
        }
      }
    } catch (err: any) {
      setError(err?.response?.data?.error?.message || err?.message || "Failed to load document analysis.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (docId) {
      loadData();
    }
  }, [docId]);

  const handleSelectRun = async (run: AnalysisRunItem) => {
    setActiveRun(run);
    try {
      const fList = await getRunFindings(run.id);
      setFindings(fList);
      setSelectedFinding(fList.length > 0 ? fList[0] : null);
    } catch (err: any) {
      setError("Could not load findings for this run.");
    }
  };

  const handleTriggerAnalysis = async () => {
    if (!document) return;
    setAnalyzing(true);
    setError(null);
    try {
      const newRun = await startDocumentAnalysis(docId, document.latest_version?.id);
      await loadData();
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.response?.data?.error?.message || "Analysis failed to execute.");
    } finally {
      setAnalyzing(false);
    }
  };

  const handleStatusChange = async (findingId: string, newStatus: string) => {
    try {
      const updated = await updateFindingStatus(findingId, newStatus);
      setFindings((prev) => prev.map((f) => (f.id === findingId ? updated : f)));
      if (selectedFinding?.id === findingId) {
        setSelectedFinding(updated);
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Failed to update finding status.");
    }
  };

  // Filtered findings
  const filteredFindings = findings.filter((f) => {
    if (categoryFilter !== "ALL" && f.category !== categoryFilter) return false;
    if (severityFilter !== "ALL" && f.severity !== severityFilter) return false;
    if (statusFilter !== "ALL" && f.status !== statusFilter) return false;
    return true;
  });

  // Health score calculation
  const healthScore = activeRun?.execution_metadata?.brand_health_score ?? document?.latest_version?.brand_health_score;

  // Counts by severity
  const criticalCount = findings.filter((f) => f.severity === "CRITICAL").length;
  const highCount = findings.filter((f) => f.severity === "HIGH").length;
  const mediumCount = findings.filter((f) => f.severity === "MEDIUM").length;
  const lowCount = findings.filter((f) => f.severity === "LOW").length;

  return (
    <div className="space-y-6">
      {/* Breadcrumb & Navigation */}
      <div className="flex items-center justify-between pb-4 border-b border-gray-200">
        <Link
          href="/analysis"
          className="inline-flex items-center gap-2 text-sm font-semibold text-gray-600 hover:text-gray-900 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Analysis Hub
        </Link>

        <div className="flex items-center gap-3">
          <button
            onClick={handleTriggerAnalysis}
            disabled={analyzing}
            className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-xl text-sm font-semibold hover:bg-blue-700 disabled:opacity-50 transition-colors shadow-sm"
          >
            {analyzing ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                Analyzing Document...
              </>
            ) : (
              <>
                <Play className="w-4 h-4" />
                Re-Run Analysis
              </>
            )}
          </button>
        </div>
      </div>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-800 text-sm flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" />
          <div>{error}</div>
        </div>
      )}

      {/* Main Document & Run Banner */}
      {document && (
        <div className="bg-white border border-gray-200 rounded-2xl p-6 shadow-sm">
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
            <div className="space-y-2">
              <div className="flex items-center gap-3">
                <h1 className="text-2xl font-bold text-gray-900">{document.title}</h1>
                <span className="px-2.5 py-0.5 text-xs font-semibold rounded-md bg-gray-100 text-gray-700 border border-gray-200">
                  {document.content_type}
                </span>
                {document.latest_version && (
                  <span className="text-xs font-mono font-semibold px-2 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200">
                    v{document.latest_version.version_number}
                  </span>
                )}
              </div>

              <div className="flex flex-wrap items-center gap-4 text-xs text-gray-500">
                <span>File: {document.latest_version?.original_filename || "N/A"}</span>
                <span>•</span>
                <span>{document.latest_version?.word_count || 0} words</span>
                <span>•</span>
                <span>{document.latest_version?.character_count || 0} characters</span>
                {activeRun && (
                  <>
                    <span>•</span>
                    <span className="text-gray-700 font-medium">
                      Run ID: <span className="font-mono text-gray-500">{activeRun.id.slice(0, 8)}</span>
                    </span>
                    <span>•</span>
                    <span>{new Date(activeRun.started_at).toLocaleString()}</span>
                  </>
                )}
              </div>
            </div>

            {/* Health Score Pill */}
            {healthScore !== undefined && healthScore !== null ? (
              <div className="flex items-center gap-4 p-4 rounded-2xl bg-gray-50 border border-gray-200 self-start lg:self-auto">
                <div className="text-right">
                  <div className="text-xs font-bold uppercase tracking-wider text-gray-400">Brand Health</div>
                  <div className="text-2xl font-extrabold text-gray-900">
                    <span className={healthScore >= 90 ? "text-emerald-600" : healthScore >= 70 ? "text-amber-600" : "text-red-600"}>
                      {healthScore}
                    </span>
                    <span className="text-sm text-gray-400">/100</span>
                  </div>
                </div>
                <div className="h-10 w-px bg-gray-200" />
                <div className="text-xs text-gray-500 space-y-0.5">
                  <div className="text-red-600 font-semibold">{criticalCount} Critical</div>
                  <div className="text-amber-600 font-semibold">{highCount} High</div>
                  <div className="text-blue-600 font-semibold">{mediumCount + lowCount} Minor</div>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      )}

      {/* Analysis Workspace: Split View */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Panel: Findings List & Filters (5 cols) */}
        <div className="lg:col-span-5 space-y-4">
          {/* Filter Bar */}
          <div className="bg-white p-4 border border-gray-200 rounded-2xl shadow-sm space-y-3">
            <div className="flex items-center justify-between text-xs font-semibold text-gray-500 uppercase tracking-wider">
              <span className="flex items-center gap-1.5">
                <Filter className="w-3.5 h-3.5" />
                Filter Findings ({filteredFindings.length})
              </span>
              {(categoryFilter !== "ALL" || severityFilter !== "ALL" || statusFilter !== "ALL") && (
                <button
                  onClick={() => {
                    setCategoryFilter("ALL");
                    setSeverityFilter("ALL");
                    setStatusFilter("ALL");
                  }}
                  className="text-blue-600 hover:text-blue-700 capitalize text-xs"
                >
                  Reset
                </button>
              )}
            </div>

            <div className="grid grid-cols-3 gap-2">
              <select
                value={categoryFilter}
                onChange={(e) => setCategoryFilter(e.target.value)}
                className="w-full text-xs py-1.5 px-2 bg-gray-50 border border-gray-200 rounded-xl focus:outline-none focus:border-blue-500"
              >
                <option value="ALL">All Categories</option>
                <option value="TONE">Tone</option>
                <option value="TERMINOLOGY">Terminology</option>
                <option value="MESSAGING">Messaging</option>
                <option value="VISUAL">Visual</option>
                <option value="ACCESSIBILITY">Accessibility</option>
                <option value="CLAIMS">Claims & Facts</option>
              </select>

              <select
                value={severityFilter}
                onChange={(e) => setSeverityFilter(e.target.value)}
                className="w-full text-xs py-1.5 px-2 bg-gray-50 border border-gray-200 rounded-xl focus:outline-none focus:border-blue-500"
              >
                <option value="ALL">All Severity</option>
                <option value="CRITICAL">Critical</option>
                <option value="HIGH">High</option>
                <option value="MEDIUM">Medium</option>
                <option value="LOW">Low</option>
                <option value="INFO">Info</option>
              </select>

              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="w-full text-xs py-1.5 px-2 bg-gray-50 border border-gray-200 rounded-xl focus:outline-none focus:border-blue-500"
              >
                <option value="ALL">All Status</option>
                <option value="OPEN">Open</option>
                <option value="NEEDS_REVIEW">Needs Review</option>
                <option value="ACCEPTED">Accepted</option>
                <option value="DISMISSED">Dismissed</option>
                <option value="DISPUTED">Disputed</option>
              </select>
            </div>
          </div>

          {/* Findings List */}
          <div className="bg-white border border-gray-200 rounded-2xl shadow-sm overflow-hidden divide-y divide-gray-100 max-h-[700px] overflow-y-auto">
            {loading ? (
              <div className="p-8 text-center text-sm text-gray-500">Loading findings...</div>
            ) : filteredFindings.length === 0 ? (
              <div className="p-8 text-center">
                <CheckCircle2 className="w-10 h-10 text-emerald-500 mx-auto mb-2" />
                <h4 className="text-sm font-semibold text-gray-800">No findings matching criteria</h4>
                <p className="text-xs text-gray-500 mt-1">Content meets all approved brand rules in this view.</p>
              </div>
            ) : (
              filteredFindings.map((finding) => {
                const isSelected = selectedFinding?.id === finding.id;
                const isCritical = finding.severity === "CRITICAL";
                const isHigh = finding.severity === "HIGH";

                return (
                  <div
                    key={finding.id}
                    onClick={() => setSelectedFinding(finding)}
                    className={`p-4 cursor-pointer transition-colors ${
                      isSelected
                        ? "bg-blue-50/80 border-l-4 border-blue-600"
                        : "hover:bg-gray-50/80 border-l-4 border-transparent"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="space-y-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span
                            className={`px-2 py-0.5 text-[10px] font-bold rounded ${
                              isCritical
                                ? "bg-red-100 text-red-800"
                                : isHigh
                                ? "bg-amber-100 text-amber-800"
                                : "bg-blue-100 text-blue-800"
                            }`}
                          >
                            {finding.severity}
                          </span>
                          <span className="text-xs font-semibold text-gray-700 font-mono">
                            {finding.cited_code}
                          </span>
                          <span className="text-[10px] uppercase font-bold text-gray-400">
                            {finding.category}
                          </span>
                        </div>

                        <div className="text-sm font-medium text-gray-900 truncate">
                          &ldquo;{finding.flagged_snippet}&rdquo;
                        </div>

                        <p className="text-xs text-gray-500 line-clamp-2">
                          {finding.explanation}
                        </p>
                      </div>

                      <div className="flex flex-col items-end gap-1 flex-shrink-0">
                        <span className="text-[10px] font-mono font-semibold text-gray-400">
                          {Math.round(finding.confidence * 100)}% conf
                        </span>
                        {finding.status === "NEEDS_REVIEW" && (
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-purple-100 text-purple-700">
                            Needs Review
                          </span>
                        )}
                        {finding.status === "ACCEPTED" && (
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-700">
                            Accepted
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Right Panel: Finding Deep-Dive Evidence Inspector (7 cols) */}
        <div className="lg:col-span-7">
          {selectedFinding ? (
            <div className="bg-white border border-gray-200 rounded-2xl shadow-sm p-6 space-y-6">
              {/* Finding Header */}
              <div className="flex items-start justify-between gap-4 pb-4 border-b border-gray-100">
                <div>
                  <div className="flex items-center gap-2">
                    <span
                      className={`px-2.5 py-1 text-xs font-bold rounded-lg ${
                        selectedFinding.severity === "CRITICAL"
                          ? "bg-red-100 text-red-800 border border-red-200"
                          : selectedFinding.severity === "HIGH"
                          ? "bg-amber-100 text-amber-800 border border-amber-200"
                          : "bg-blue-100 text-blue-800 border border-blue-200"
                      }`}
                    >
                      {selectedFinding.severity} Severity
                    </span>
                    <span className="px-2.5 py-1 text-xs font-semibold rounded-lg bg-gray-100 text-gray-700 border border-gray-200">
                      Category: {selectedFinding.category}
                    </span>
                    <span className="px-2 py-0.5 text-xs font-mono text-gray-500">
                      {selectedFinding.cited_code}
                    </span>
                  </div>
                  <h3 className="text-lg font-bold text-gray-900 mt-2">Finding Evidence & Traceability</h3>
                </div>

                {/* Status Badges */}
                <div className="text-right">
                  <span className="text-xs text-gray-400 block mb-1">Status</span>
                  <span
                    className={`px-2.5 py-1 text-xs font-bold rounded-md ${
                      selectedFinding.status === "OPEN"
                        ? "bg-amber-50 text-amber-700 border border-amber-200"
                        : selectedFinding.status === "NEEDS_REVIEW"
                        ? "bg-purple-50 text-purple-700 border border-purple-200"
                        : selectedFinding.status === "ACCEPTED"
                        ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                        : "bg-gray-100 text-gray-600 border border-gray-200"
                    }`}
                  >
                    {selectedFinding.status}
                  </span>
                </div>
              </div>

              {/* Exact Flagged Evidence Excerpt */}
              <div className="space-y-2">
                <span className="text-xs font-bold uppercase tracking-wider text-gray-500 flex items-center gap-1.5">
                  <Quote className="w-3.5 h-3.5" />
                  Exact Flagged Text Excerpt
                </span>
                <div className="p-4 bg-red-50/60 border border-red-200/80 rounded-xl text-gray-900 text-sm font-medium">
                  &ldquo;{selectedFinding.flagged_snippet}&rdquo;
                </div>
                <div className="flex items-center gap-4 text-xs text-gray-400 font-mono">
                  {selectedFinding.segment_id && <span>Segment: {selectedFinding.segment_id}</span>}
                  {selectedFinding.char_offset_start !== undefined && (
                    <span>
                      Char Offsets: [{selectedFinding.char_offset_start} - {selectedFinding.char_offset_end}]
                    </span>
                  )}
                  <span>Detection: {selectedFinding.source}</span>
                  <span>Confidence: {Math.round(selectedFinding.confidence * 100)}%</span>
                </div>
              </div>

              {/* Explanation */}
              <div className="space-y-2">
                <span className="text-xs font-bold uppercase tracking-wider text-gray-500">Explanation</span>
                <p className="text-sm text-gray-700 leading-relaxed bg-gray-50 p-3.5 rounded-xl border border-gray-200">
                  {selectedFinding.explanation}
                </p>
              </div>

              {/* Constitution Ground Truth Reference Card */}
              {selectedFinding.evidence_reference && (
                <div className="space-y-2">
                  <span className="text-xs font-bold uppercase tracking-wider text-gray-500 flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5 text-blue-600" />
                    Approved Constitution Ground Truth Reference
                  </span>
                  <div className="p-4 bg-blue-50/50 border border-blue-200 rounded-xl space-y-2 text-xs">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-blue-900 font-mono">
                        {selectedFinding.cited_code} ({selectedFinding.evidence_type})
                      </span>
                      {selectedFinding.evidence_reference.category && (
                        <span className="text-blue-700 font-semibold">
                          {selectedFinding.evidence_reference.category}
                        </span>
                      )}
                    </div>

                    {selectedFinding.evidence_reference.title && (
                      <div className="text-gray-900 font-semibold text-sm">
                        {selectedFinding.evidence_reference.title}
                      </div>
                    )}

                    {selectedFinding.evidence_reference.statement && (
                      <div className="text-gray-700">
                        <span className="font-semibold">Statement:</span> {selectedFinding.evidence_reference.statement}
                      </div>
                    )}

                    {selectedFinding.evidence_reference.source && (
                      <div className="text-gray-500">
                        <span className="font-semibold">Certified Source:</span> {selectedFinding.evidence_reference.source}
                      </div>
                    )}

                    {selectedFinding.evidence_reference.preferred && (
                      <div className="text-gray-700">
                        <span className="font-semibold">Approved Term:</span>{" "}
                        <span className="text-emerald-700 font-bold">{selectedFinding.evidence_reference.preferred}</span>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Suggested Correction */}
              {selectedFinding.suggested_correction && (
                <div className="space-y-2">
                  <span className="text-xs font-bold uppercase tracking-wider text-gray-500">
                    Suggested Standard Correction
                  </span>
                  <div className="p-3.5 bg-emerald-50 border border-emerald-200 rounded-xl flex items-start gap-3">
                    <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0 mt-0.5" />
                    <div className="space-y-1">
                      <div className="text-sm font-semibold text-emerald-900">
                        {selectedFinding.suggested_correction}
                      </div>
                      <p className="text-[11px] text-emerald-700">
                        Recommendation only — the original document text is never modified automatically.
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* Status Action Buttons */}
              <div className="pt-4 border-t border-gray-100 flex flex-wrap items-center justify-between gap-3">
                <span className="text-xs text-gray-400">Reviewer Actions:</span>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleStatusChange(selectedFinding.id, "ACCEPTED")}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-xl bg-emerald-600 text-white hover:bg-emerald-700 transition-colors shadow-sm"
                  >
                    <Check className="w-3.5 h-3.5" />
                    Accept Finding
                  </button>

                  <button
                    onClick={() => handleStatusChange(selectedFinding.id, "DISMISSED")}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-xl border border-gray-200 text-gray-700 hover:bg-gray-100 transition-colors"
                  >
                    <X className="w-3.5 h-3.5" />
                    Dismiss
                  </button>

                  <button
                    onClick={() => handleStatusChange(selectedFinding.id, "NEEDS_REVIEW")}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-xl border border-purple-200 text-purple-700 bg-purple-50 hover:bg-purple-100 transition-colors"
                  >
                    <HelpCircle className="w-3.5 h-3.5" />
                    Mark Needs Review
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <div className="bg-white border border-gray-200 rounded-2xl p-12 text-center text-gray-400">
              Select a finding on the left to inspect evidence traceability.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

