"use client";

import React, { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  CheckCircle2,
  Clock,
  AlertTriangle,
  FileText,
  UserCheck,
  Send,
  MessageSquare,
  History,
  GitCompare,
  ShieldCheck,
  ShieldAlert,
  Lock,
  ThumbsUp,
  XCircle,
  HelpCircle,
  Sparkles,
  RefreshCw,
  CornerDownRight,
  User,
  Scale
} from "lucide-react";
import {
  getReviewDetail,
  transitionReview,
  recordFindingDecision,
  listReviewComments,
  addReviewComment,
  compareDocumentVersions,
  getRunFindings,
  listDocumentAnalysisRuns,
  getDocumentDetails,
  listDocumentVersions,
  ReviewItem,
  FindingItem,
  ReviewCommentItem,
  DocumentVersionComparison,
  DocumentItem,
  DocumentVersionItem,
  ReviewWorkflowStatus,
  FindingDecisionType
} from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function ReviewDetailPage() {
  const params = useParams();
  const router = useRouter();
  const { user } = useAuth();
  const reviewId = params?.id as string;

  const [review, setReview] = useState<ReviewItem | null>(null);
  const [docDetail, setDocDetail] = useState<DocumentItem | null>(null);
  const [docVersions, setDocVersions] = useState<DocumentVersionItem[]>([]);
  const [findings, setFindings] = useState<FindingItem[]>([]);
  const [comments, setComments] = useState<ReviewCommentItem[]>([]);
  const [diffComparison, setDiffComparison] = useState<DocumentVersionComparison | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"findings" | "diff" | "comments" | "timeline">("findings");

  // Decision Modal State
  const [decisionModalOpen, setDecisionModalOpen] = useState<boolean>(false);
  const [targetFindingId, setTargetFindingId] = useState<string | null>(null);
  const [targetDecision, setTargetDecision] = useState<FindingDecisionType>("ACCEPTED");
  const [decisionReason, setDecisionReason] = useState<string>("");
  const [decisionCorrection, setDecisionCorrection] = useState<string>("");
  const [decisionSubmitting, setDecisionSubmitting] = useState<boolean>(false);
  const [decisionError, setDecisionError] = useState<string | null>(null);

  // Transition Modal State
  const [transitionModalOpen, setTransitionModalOpen] = useState<boolean>(false);
  const [pendingAction, setPendingAction] = useState<string>("");
  const [actionTitle, setActionTitle] = useState<string>("");
  const [transitionNotes, setTransitionNotes] = useState<string>("");
  const [resubmitVersionId, setResubmitVersionId] = useState<string>("");
  const [transitionSubmitting, setTransitionSubmitting] = useState<boolean>(false);
  const [transitionError, setTransitionError] = useState<string | null>(null);

  // Comment Input State
  const [newCommentText, setNewCommentText] = useState<string>("");
  const [replyParentId, setReplyParentId] = useState<string | null>(null);
  const [replyText, setReplyText] = useState<string>("");
  const [commentSubmitting, setCommentSubmitting] = useState<boolean>(false);

  const fetchAllData = async () => {
    setLoading(true);
    setError(null);
    try {
      const rev = await getReviewDetail(reviewId);
      setReview(rev);

      // Load document detail and versions
      if (rev.document_id) {
        try {
          const doc = await getDocumentDetails(rev.document_id);
          setDocDetail(doc);
          const vers = await listDocumentVersions(rev.document_id);
          setDocVersions(vers);

          // If there is more than 1 version, load diff between v1 and current
          if (vers && vers.length > 1) {
            const v1 = vers[vers.length - 1]; // oldest
            const vLatest = vers[0]; // newest
            if (v1.id !== vLatest.id) {
              const diff = await compareDocumentVersions(doc.id, v1.id, vLatest.id);
              setDiffComparison(diff);
            }
          }
        } catch (e) {
          console.error("Error loading document detail", e);
        }
      }

      // Load findings for this review version
      try {
        const runs = await listDocumentAnalysisRuns(rev.document_id);
        const versionRun = runs.find((r) => r.version_id === rev.version_id) || runs[0];
        if (versionRun) {
          const fList = await getRunFindings(versionRun.id);
          setFindings(fList);
        }
      } catch (e) {
        console.error("Error loading findings", e);
      }

      // Load threaded comments
      try {
        const cList = await listReviewComments(reviewId);
        setComments(cList);
      } catch (e) {
        console.error("Error loading comments", e);
      }
    } catch (err: any) {
      setError(err?.response?.data?.error?.message || err?.message || "Failed to load review workspace.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (reviewId) {
      fetchAllData();
    }
  }, [reviewId]);

  // Open Transition Modal
  const openTransitionModal = (action: string, title: string) => {
    setPendingAction(action);
    setActionTitle(title);
    setTransitionNotes("");
    setTransitionError(null);
    if (action === "RESUBMIT" && docVersions.length > 0) {
      const otherVersions = docVersions.filter((v) => v.id !== review?.version_id);
      if (otherVersions.length > 0) {
        setResubmitVersionId(otherVersions[0].id);
      }
    }
    setTransitionModalOpen(true);
  };

  const handleExecuteTransition = async (e: React.FormEvent) => {
    e.preventDefault();
    setTransitionSubmitting(true);
    setTransitionError(null);
    try {
      const updated = await transitionReview(reviewId, {
        action: pendingAction,
        notes: transitionNotes.trim() || undefined,
        new_version_id: pendingAction === "RESUBMIT" ? resubmitVersionId : undefined,
      });
      setReview(updated);
      setTransitionModalOpen(false);
      fetchAllData();
    } catch (err: any) {
      setTransitionError(err?.response?.data?.error?.message || err?.message || "Transition failed.");
    } finally {
      setTransitionSubmitting(false);
    }
  };

  // Open Finding Decision Modal
  const openDecisionModal = (findingId: string, decision: FindingDecisionType) => {
    setTargetFindingId(findingId);
    setTargetDecision(decision);
    setDecisionReason("");
    setDecisionCorrection("");
    setDecisionError(null);
    setDecisionModalOpen(true);
  };

  const handleRecordDecision = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!targetFindingId) return;
    setDecisionSubmitting(true);
    setDecisionError(null);
    try {
      await recordFindingDecision(reviewId, targetFindingId, {
        decision: targetDecision,
        reason: decisionReason.trim() || undefined,
        suggested_correction: decisionCorrection.trim() || undefined,
      });
      setDecisionModalOpen(false);
      fetchAllData();
    } catch (err: any) {
      setDecisionError(err?.response?.data?.error?.message || err?.message || "Decision submission failed.");
    } finally {
      setDecisionSubmitting(false);
    }
  };

  // Add Comment
  const handleAddComment = async (e: React.FormEvent, parentId?: string) => {
    e.preventDefault();
    const content = parentId ? replyText : newCommentText;
    if (!content.trim()) return;

    setCommentSubmitting(true);
    try {
      await addReviewComment(reviewId, {
        content: content.trim(),
        parent_comment_id: parentId,
      });
      if (parentId) {
        setReplyText("");
        setReplyParentId(null);
      } else {
        setNewCommentText("");
      }
      const cList = await listReviewComments(reviewId);
      setComments(cList);
    } catch (err: any) {
      alert(err?.response?.data?.error?.message || err?.message || "Failed to post comment.");
    } finally {
      setCommentSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="p-16 text-center text-slate-500">
        <RefreshCw className="w-8 h-8 animate-spin mx-auto mb-3 text-indigo-600" />
        Loading review workspace...
      </div>
    );
  }

  if (error || !review) {
    return (
      <div className="p-10 text-center text-red-600 space-y-4">
        <AlertTriangle className="w-10 h-10 mx-auto" />
        <p className="font-semibold">{error || "Review not found"}</p>
        <Link
          href="/reviews"
          className="inline-flex items-center gap-1.5 px-4 py-2 bg-slate-100 text-slate-700 rounded-lg text-sm hover:bg-slate-200"
        >
          <ArrowLeft className="w-4 h-4" /> Back to Queue
        </Link>
      </div>
    );
  }

  const isCreator = user?.id === review.creator_id;
  const isReviewer = user?.id === review.assigned_reviewer_id || user?.role === "REVIEWER" || user?.role === "ADMIN";
  const isBrandManager = user?.role === "BRAND_MANAGER" || user?.role === "ADMIN";
  const isLegal = user?.role === "LEGAL_REVIEWER" || user?.role === "ADMIN";

  return (
    <div className="space-y-6">
      {/* Back Link & Header */}
      <div className="space-y-4 pb-4 border-b border-slate-200">
        <Link
          href="/reviews"
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-slate-800 transition"
        >
          <ArrowLeft className="w-3.5 h-3.5" /> Back to Review Queue
        </Link>

        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
                {review.document_title || "Document Review"}
              </h1>
              <span className="px-2 py-0.5 rounded bg-slate-100 border border-slate-200 text-xs font-semibold text-slate-700">
                v{review.version_number || 1}
              </span>
              <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-indigo-100 text-indigo-800 border border-indigo-200">
                {review.status}
              </span>
              <span className="px-2 py-0.5 rounded text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
                {review.priority} PRIORITY
              </span>
              {review.brand_health_score !== undefined && (
                <span className={`px-2.5 py-0.5 rounded-full text-xs font-bold ${
                  review.brand_health_score >= 80
                    ? "bg-emerald-100 text-emerald-800 border border-emerald-200"
                    : "bg-amber-100 text-amber-800 border border-amber-200"
                }`}>
                  Health: {review.brand_health_score.toFixed(0)}%
                </span>
              )}
            </div>
            <p className="text-xs text-slate-500">
              Submitted by <span className="font-medium text-slate-700">{review.creator_name}</span> &bull; Assigned to{" "}
              <span className="font-medium text-indigo-700">{review.reviewer_name || "Unassigned"}</span> &bull; Created{" "}
              {new Date(review.created_at).toLocaleString()}
            </p>
          </div>

          {/* Workflow Action Bar */}
          <div className="flex flex-wrap items-center gap-2">
            {/* SUBMITTED -> START_REVIEW */}
            {review.status === "SUBMITTED" && isReviewer && (
              <button
                onClick={() => openTransitionModal("START_REVIEW", "Start Formal Review")}
                className="px-3.5 py-1.5 bg-purple-600 text-white rounded-lg text-xs font-semibold hover:bg-purple-700 shadow-sm transition"
              >
                Start Review
              </button>
            )}

            {/* UNDER_REVIEW or RESUBMITTED actions */}
            {(review.status === "UNDER_REVIEW" || review.status === "RESUBMITTED") && isReviewer && (
              <>
                <button
                  onClick={() => openTransitionModal("REQUEST_CHANGES", "Request Changes from Creator")}
                  className="px-3.5 py-1.5 bg-amber-500 text-white rounded-lg text-xs font-semibold hover:bg-amber-600 shadow-sm transition"
                >
                  Request Changes
                </button>
                <button
                  onClick={() => openTransitionModal("FORWARD_FOR_APPROVAL", "Forward for Brand Approval")}
                  className="px-3.5 py-1.5 bg-teal-600 text-white rounded-lg text-xs font-semibold hover:bg-teal-700 shadow-sm transition"
                >
                  Forward to Brand Sign-off
                </button>
                <button
                  onClick={() => openTransitionModal("REQUEST_LEGAL", "Request Legal Review")}
                  className="px-3.5 py-1.5 bg-slate-700 text-white rounded-lg text-xs font-semibold hover:bg-slate-800 shadow-sm transition"
                >
                  Request Legal Review
                </button>
              </>
            )}

            {/* PENDING_LEGAL_APPROVAL actions */}
            {review.status === "PENDING_LEGAL_APPROVAL" && isLegal && (
              <>
                <button
                  onClick={() => openTransitionModal("APPROVE_LEGAL", "Grant Legal Clearance")}
                  className="px-3.5 py-1.5 bg-indigo-600 text-white rounded-lg text-xs font-semibold hover:bg-indigo-700 shadow-sm transition"
                >
                  Approve Legal Sign-off
                </button>
                <button
                  onClick={() => openTransitionModal("REJECT_LEGAL", "Reject Legal Clearance")}
                  className="px-3.5 py-1.5 bg-rose-600 text-white rounded-lg text-xs font-semibold hover:bg-rose-700 shadow-sm transition"
                >
                  Reject Legal
                </button>
              </>
            )}

            {/* PENDING_BRAND_APPROVAL actions */}
            {review.status === "PENDING_BRAND_APPROVAL" && isBrandManager && (
              <>
                <button
                  onClick={() => openTransitionModal("APPROVE", "Approve & Lock Content Version")}
                  className="px-4 py-1.5 bg-emerald-600 text-white rounded-lg text-xs font-bold hover:bg-emerald-700 shadow-sm flex items-center gap-1.5 transition"
                >
                  <Lock className="w-3.5 h-3.5" /> Approve & Lock Version
                </button>
                <button
                  onClick={() => openTransitionModal("REJECT", "Reject Document Submission")}
                  className="px-3.5 py-1.5 bg-red-600 text-white rounded-lg text-xs font-semibold hover:bg-red-700 shadow-sm transition"
                >
                  Reject
                </button>
              </>
            )}

            {/* CHANGES_REQUESTED -> RESUBMIT */}
            {review.status === "CHANGES_REQUESTED" && isCreator && (
              <button
                onClick={() => openTransitionModal("RESUBMIT", "Resubmit Revised Document Version")}
                className="px-4 py-1.5 bg-indigo-600 text-white rounded-lg text-xs font-bold hover:bg-indigo-700 shadow-sm transition"
              >
                Resubmit Revised Version
              </button>
            )}

            {/* APPROVED Banner */}
            {review.status === "APPROVED" && (
              <span className="px-3 py-1.5 bg-emerald-50 border border-emerald-300 text-emerald-800 rounded-lg text-xs font-bold flex items-center gap-1.5">
                <Lock className="w-3.5 h-3.5 text-emerald-600" />
                Version Locked & Approved
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Tabs Navigation */}
      <div className="flex border-b border-slate-200 gap-6 text-sm font-semibold text-slate-500">
        <button
          onClick={() => setActiveTab("findings")}
          className={`pb-3 flex items-center gap-2 border-b-2 transition ${
            activeTab === "findings"
              ? "border-indigo-600 text-indigo-600"
              : "border-transparent hover:text-slate-900"
          }`}
        >
          <ShieldAlert className="w-4 h-4" />
          Findings & Decisions ({findings.length})
        </button>
        <button
          onClick={() => setActiveTab("diff")}
          className={`pb-3 flex items-center gap-2 border-b-2 transition ${
            activeTab === "diff"
              ? "border-indigo-600 text-indigo-600"
              : "border-transparent hover:text-slate-900"
          }`}
        >
          <GitCompare className="w-4 h-4" />
          Version Diff & Delta
        </button>
        <button
          onClick={() => setActiveTab("comments")}
          className={`pb-3 flex items-center gap-2 border-b-2 transition ${
            activeTab === "comments"
              ? "border-indigo-600 text-indigo-600"
              : "border-transparent hover:text-slate-900"
          }`}
        >
          <MessageSquare className="w-4 h-4" />
          Collaboration & Notes ({comments.length})
        </button>
        <button
          onClick={() => setActiveTab("timeline")}
          className={`pb-3 flex items-center gap-2 border-b-2 transition ${
            activeTab === "timeline"
              ? "border-indigo-600 text-indigo-600"
              : "border-transparent hover:text-slate-900"
          }`}
        >
          <History className="w-4 h-4" />
          Audit Timeline ({review.history?.length || 0})
        </button>
      </div>

      {/* Tab 1: Findings & Decisions */}
      {activeTab === "findings" && (
        <div className="space-y-4">
          <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 flex flex-col md:flex-row md:items-center justify-between gap-3">
            <div>
              <h3 className="font-bold text-slate-800 text-sm">Findings Resolution Matrix</h3>
              <p className="text-xs text-slate-500">
                Reviewers and Managers can ACCEPT, DISMISS (with required justification), DISPUTE, or RESOLVE individual findings.
              </p>
            </div>
          </div>

          {findings.length === 0 ? (
            <div className="bg-white rounded-xl border border-slate-200 p-12 text-center text-slate-500 space-y-2">
              <CheckCircle2 className="w-10 h-10 text-emerald-500 mx-auto" />
              <p className="font-semibold text-slate-800">No brand violations detected</p>
              <p className="text-xs text-slate-400">This document version satisfies all active Constitution rules.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4">
              {findings.map((f) => {
                const decision = review.finding_decisions?.find((d) => d.finding_id === f.id);
                return (
                  <div
                    key={f.id}
                    className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm hover:border-slate-300 transition space-y-3"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold px-2 py-0.5 rounded bg-slate-100 text-slate-700 uppercase">
                          {f.category}
                        </span>
                        <span
                          className={`text-xs font-bold px-2 py-0.5 rounded ${
                            f.severity === "CRITICAL"
                              ? "bg-red-100 text-red-800"
                              : f.severity === "HIGH"
                              ? "bg-amber-100 text-amber-800"
                              : "bg-blue-100 text-blue-800"
                          }`}
                        >
                          {f.severity}
                        </span>
                        <span className="text-xs text-slate-400 font-mono">
                          {f.cited_code || "RULE"}
                        </span>
                      </div>

                      {/* Decision status if recorded */}
                      {decision ? (
                        <div className="flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full bg-slate-100 border border-slate-200">
                          <span className="text-slate-500">Decision:</span>
                          <span
                            className={
                              decision.decision === "ACCEPTED"
                                ? "text-emerald-700"
                                : decision.decision === "DISMISSED"
                                ? "text-amber-700"
                                : decision.decision === "DISPUTED"
                                ? "text-purple-700"
                                : "text-blue-700"
                            }
                          >
                            {decision.decision}
                          </span>
                          {decision.reason && (
                            <span className="text-slate-400 text-xs italic">
                              ("{decision.reason}")
                            </span>
                          )}
                        </div>
                      ) : (
                        <span className="text-xs text-amber-600 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded font-medium">
                          Pending Decision
                        </span>
                      )}
                    </div>

                    <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 text-xs space-y-1">
                      <div className="flex items-start gap-2">
                        <span className="font-semibold text-slate-500 uppercase tracking-wider text-[10px]">
                          Flagged Text:
                        </span>
                        <span className="font-mono bg-red-50 text-red-700 px-1.5 py-0.5 rounded border border-red-200">
                          "{f.flagged_snippet}"
                        </span>
                      </div>
                      <p className="text-slate-700">{f.explanation}</p>
                      {f.suggested_correction && (
                        <div className="flex items-center gap-2 pt-1 text-emerald-700 font-medium">
                          <span>Suggested Correction:</span>
                          <span className="font-mono bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-200">
                            {f.suggested_correction}
                          </span>
                        </div>
                      )}
                    </div>

                    {/* Action buttons for reviewer */}
                    {isReviewer && review.status !== "APPROVED" && (
                      <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-slate-100">
                        <button
                          onClick={() => openDecisionModal(f.id, "ACCEPTED")}
                          className="px-2.5 py-1 text-xs font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 rounded hover:bg-emerald-100 transition flex items-center gap-1"
                        >
                          <ThumbsUp className="w-3 h-3" /> Accept Finding
                        </button>
                        <button
                          onClick={() => openDecisionModal(f.id, "DISMISSED")}
                          className="px-2.5 py-1 text-xs font-medium text-amber-700 bg-amber-50 border border-amber-200 rounded hover:bg-amber-100 transition flex items-center gap-1"
                        >
                          <XCircle className="w-3 h-3" /> Dismiss (Justify)
                        </button>
                        <button
                          onClick={() => openDecisionModal(f.id, "DISPUTED")}
                          className="px-2.5 py-1 text-xs font-medium text-purple-700 bg-purple-50 border border-purple-200 rounded hover:bg-purple-100 transition flex items-center gap-1"
                        >
                          <HelpCircle className="w-3 h-3" /> Dispute
                        </button>
                        <button
                          onClick={() => openDecisionModal(f.id, "RESOLVED")}
                          className="px-2.5 py-1 text-xs font-medium text-blue-700 bg-blue-50 border border-blue-200 rounded hover:bg-blue-100 transition flex items-center gap-1"
                        >
                          <CheckCircle2 className="w-3 h-3" /> Mark Resolved
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Tab 2: Version Diff & Delta */}
      {activeTab === "diff" && (
        <div className="space-y-4">
          {diffComparison ? (
            <div className="space-y-4">
              {/* Diff summary stats */}
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                <div className="bg-white p-3 rounded-xl border border-slate-200 shadow-sm">
                  <span className="text-xs text-slate-500 uppercase font-medium">Versions Compared</span>
                  <p className="text-base font-bold text-slate-800">
                    v{diffComparison.v1_version_number} vs v{diffComparison.v2_version_number}
                  </p>
                </div>
                <div className="bg-white p-3 rounded-xl border border-slate-200 shadow-sm">
                  <span className="text-xs text-slate-500 uppercase font-medium">Score Delta</span>
                  <p className={`text-base font-bold ${
                    (diffComparison.score_delta || 0) >= 0 ? "text-emerald-600" : "text-red-600"
                  }`}>
                    {(diffComparison.score_delta || 0) > 0 ? "+" : ""}
                    {(diffComparison.score_delta || 0).toFixed(1)} pts
                  </p>
                </div>
                <div className="bg-white p-3 rounded-xl border border-emerald-200 bg-emerald-50/20 shadow-sm">
                  <span className="text-xs text-emerald-700 uppercase font-medium">Resolved Findings</span>
                  <p className="text-base font-bold text-emerald-800">
                    {diffComparison.findings_summary?.resolved_findings_count || 0}
                  </p>
                </div>
                <div className="bg-white p-3 rounded-xl border border-red-200 bg-red-50/20 shadow-sm">
                  <span className="text-xs text-red-700 uppercase font-medium">New Findings</span>
                  <p className="text-base font-bold text-red-800">
                    {diffComparison.findings_summary?.new_findings_count || 0}
                  </p>
                </div>
                <div className="bg-white p-3 rounded-xl border border-slate-200 shadow-sm">
                  <span className="text-xs text-slate-500 uppercase font-medium">Lines Modified</span>
                  <p className="text-base font-bold text-slate-800">
                    +{diffComparison.text_summary?.added_lines_count || 0} / -{diffComparison.text_summary?.removed_lines_count || 0}
                  </p>
                </div>
              </div>

              {/* Text Diff View */}
              <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
                <div className="bg-slate-50 px-4 py-2 border-b border-slate-200 flex items-center justify-between">
                  <span className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                    Line-by-Line Content Diff
                  </span>
                  <span className="text-xs text-slate-500 font-mono">
                    Red: Removed in v{diffComparison.v2_version_number} &bull; Green: Added in v{diffComparison.v2_version_number}
                  </span>
                </div>
                <div className="p-4 font-mono text-xs space-y-1 overflow-x-auto max-h-[500px]">
                  {diffComparison.diff_lines.map((line, idx) => (
                    <div
                      key={idx}
                      className={`px-2 py-1 rounded flex items-start gap-3 ${
                        line.type === "ADD"
                          ? "bg-emerald-50 text-emerald-900 border-l-4 border-emerald-500"
                          : line.type === "REMOVE"
                          ? "bg-red-50 text-red-900 border-l-4 border-red-500"
                          : "text-slate-700 hover:bg-slate-50"
                      }`}
                    >
                      <span className="text-slate-400 select-none w-6 text-right font-semibold">
                        {line.type === "ADD" ? "+" : line.type === "REMOVE" ? "-" : " "}
                      </span>
                      <span className="whitespace-pre-wrap flex-1">{line.text}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="bg-white rounded-xl border border-slate-200 p-12 text-center text-slate-500 space-y-2">
              <FileText className="w-10 h-10 text-slate-300 mx-auto" />
              <p className="font-semibold text-slate-800">Only 1 version exists for this document</p>
              <p className="text-xs text-slate-400">
                Upload a revised version to unlock automated line-by-line diffing, score delta tracking, and finding resolution comparison.
              </p>
            </div>
          )}
        </div>
      )}

      {/* Tab 3: Collaboration & Threaded Comments */}
      {activeTab === "comments" && (
        <div className="space-y-6">
          {/* Post New Comment Box */}
          <form
            onSubmit={(e) => handleAddComment(e)}
            className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm space-y-3"
          >
            <div className="flex items-center gap-2">
              <MessageSquare className="w-4 h-4 text-indigo-600" />
              <span className="text-xs font-bold text-slate-700 uppercase">
                Add Review Comment or Instruction
              </span>
            </div>
            <textarea
              value={newCommentText}
              onChange={(e) => setNewCommentText(e.target.value)}
              placeholder="Leave feedback on brand alignment, tone, or pricing corrections..."
              rows={3}
              className="w-full p-2.5 border border-slate-300 rounded-lg text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
            <div className="flex justify-end">
              <button
                type="submit"
                disabled={commentSubmitting || !newCommentText.trim()}
                className="flex items-center gap-1.5 px-4 py-1.5 bg-indigo-600 text-white rounded-lg text-xs font-semibold hover:bg-indigo-700 disabled:opacity-50 transition"
              >
                <Send className="w-3.5 h-3.5" /> Post Comment
              </button>
            </div>
          </form>

          {/* Comments List */}
          <div className="space-y-4">
            {comments.length === 0 ? (
              <div className="bg-white rounded-xl border border-slate-200 p-8 text-center text-slate-500">
                <MessageSquare className="w-8 h-8 text-slate-300 mx-auto mb-1" />
                <p className="text-xs">No comments recorded yet. Start the conversation above.</p>
              </div>
            ) : (
              comments.map((c) => (
                <div
                  key={c.id}
                  className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm space-y-3"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className="w-7 h-7 rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center font-bold text-xs">
                        {c.user_name ? c.user_name[0].toUpperCase() : "U"}
                      </div>
                      <div>
                        <span className="text-xs font-bold text-slate-900">{c.user_name}</span>
                        {c.user_role && (
                          <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200 uppercase font-semibold">
                            {c.user_role}
                          </span>
                        )}
                      </div>
                    </div>
                    <span className="text-[11px] text-slate-400">
                      {new Date(c.created_at).toLocaleString()}
                    </span>
                  </div>

                  <p className="text-xs text-slate-800 whitespace-pre-wrap">{c.content}</p>

                  {/* Replies */}
                  {c.replies && c.replies.length > 0 && (
                    <div className="pl-6 border-l-2 border-slate-100 space-y-2 mt-2">
                      {c.replies.map((rep) => (
                        <div key={rep.id} className="bg-slate-50 rounded-lg p-2.5 space-y-1">
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-semibold text-slate-800">
                              {rep.user_name}
                            </span>
                            <span className="text-[10px] text-slate-400">
                              {new Date(rep.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                            </span>
                          </div>
                          <p className="text-xs text-slate-700">{rep.content}</p>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Reply Button / Box */}
                  {replyParentId === c.id ? (
                    <div className="pt-2 space-y-2 border-t border-slate-100">
                      <textarea
                        value={replyText}
                        onChange={(e) => setReplyText(e.target.value)}
                        placeholder="Write a reply..."
                        rows={2}
                        className="w-full p-2 border border-slate-300 rounded text-xs focus:ring-1 focus:ring-indigo-500"
                      />
                      <div className="flex justify-end gap-2">
                        <button
                          type="button"
                          onClick={() => setReplyParentId(null)}
                          className="px-2.5 py-1 text-xs text-slate-500 hover:text-slate-700"
                        >
                          Cancel
                        </button>
                        <button
                          type="button"
                          onClick={(e) => handleAddComment(e, c.id)}
                          className="px-3 py-1 bg-indigo-600 text-white rounded text-xs font-medium hover:bg-indigo-700"
                        >
                          Reply
                        </button>
                      </div>
                    </div>
                  ) : (
                    <button
                      onClick={() => {
                        setReplyParentId(c.id);
                        setReplyText("");
                      }}
                      className="text-xs text-indigo-600 hover:text-indigo-800 font-medium flex items-center gap-1 pt-1"
                    >
                      <CornerDownRight className="w-3 h-3" /> Reply
                    </button>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* Tab 4: Audit Timeline */}
      {activeTab === "timeline" && (
        <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
          <h3 className="text-sm font-bold text-slate-900 mb-4 flex items-center gap-2">
            <History className="w-4 h-4 text-indigo-600" />
            Immutable Review History & State Transitions
          </h3>

          <div className="relative pl-6 border-l-2 border-slate-200 space-y-6">
            {review.history?.map((h) => (
              <div key={h.id} className="relative group">
                <div className="absolute -left-[31px] top-0 w-4 h-4 rounded-full bg-white border-2 border-indigo-600 group-hover:bg-indigo-600 transition" />
                <div className="space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs font-bold px-2 py-0.5 rounded bg-indigo-50 text-indigo-700 border border-indigo-200">
                      {h.action}
                    </span>
                    <span className="text-xs font-semibold text-slate-800">
                      {h.actor_name || "System"}
                    </span>
                    {h.actor_role && (
                      <span className="text-[10px] px-1.5 py-0.2 rounded bg-slate-100 text-slate-500 uppercase">
                        {h.actor_role}
                      </span>
                    )}
                    <span className="text-xs text-slate-400">
                      {new Date(h.created_at).toLocaleString()}
                    </span>
                  </div>
                  {h.notes && (
                    <p className="text-xs text-slate-600 bg-slate-50 p-2.5 rounded-lg border border-slate-200 mt-1">
                      "{h.notes}"
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Decision Modal */}
      {decisionModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6 space-y-4 border border-slate-200">
            <div className="flex items-center justify-between pb-2 border-b border-slate-200">
              <h3 className="text-base font-bold text-slate-900">
                Record Finding Decision: {targetDecision}
              </h3>
              <button
                onClick={() => setDecisionModalOpen(false)}
                className="text-slate-400 hover:text-slate-600 font-bold"
              >
                &times;
              </button>
            </div>

            {decisionError && (
              <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-600">
                {decisionError}
              </div>
            )}

            <form onSubmit={handleRecordDecision} className="space-y-3">
              {(targetDecision === "DISMISSED" || targetDecision === "DISPUTED") && (
                <div>
                  <label className="block text-xs font-semibold text-slate-700 uppercase mb-1">
                    Justification / Reason (Mandatory)
                  </label>
                  <textarea
                    value={decisionReason}
                    onChange={(e) => setDecisionReason(e.target.value)}
                    placeholder="Provide mandatory explanation why this finding is dismissed or disputed..."
                    rows={3}
                    required
                    className="w-full p-2 border border-slate-300 rounded text-xs focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
              )}

              {targetDecision === "ACCEPTED" && (
                <div>
                  <label className="block text-xs font-semibold text-slate-700 uppercase mb-1">
                    Suggested Correction (Optional)
                  </label>
                  <input
                    type="text"
                    value={decisionCorrection}
                    onChange={(e) => setDecisionCorrection(e.target.value)}
                    placeholder="Enter recommended replacement copy..."
                    className="w-full p-2 border border-slate-300 rounded text-xs focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
              )}

              <div className="flex justify-end gap-2 pt-2 border-t border-slate-200">
                <button
                  type="button"
                  onClick={() => setDecisionModalOpen(false)}
                  className="px-3 py-1.5 border border-slate-300 rounded text-xs text-slate-600 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={decisionSubmitting}
                  className="px-4 py-1.5 bg-indigo-600 text-white rounded text-xs font-semibold hover:bg-indigo-700 disabled:opacity-50"
                >
                  {decisionSubmitting ? "Submitting..." : "Confirm Decision"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Transition Modal */}
      {transitionModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6 space-y-4 border border-slate-200">
            <div className="flex items-center justify-between pb-2 border-b border-slate-200">
              <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <CheckCircle2 className="w-5 h-5 text-indigo-600" />
                {actionTitle}
              </h3>
              <button
                onClick={() => setTransitionModalOpen(false)}
                className="text-slate-400 hover:text-slate-600 font-bold"
              >
                &times;
              </button>
            </div>

            {transitionError && (
              <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-600">
                {transitionError}
              </div>
            )}

            <form onSubmit={handleExecuteTransition} className="space-y-3">
              {pendingAction === "RESUBMIT" && docVersions.length > 0 && (
                <div>
                  <label className="block text-xs font-semibold text-slate-700 uppercase mb-1">
                    Select Revised Document Version
                  </label>
                  <select
                    value={resubmitVersionId}
                    onChange={(e) => setResubmitVersionId(e.target.value)}
                    className="w-full p-2 border border-slate-300 rounded text-xs focus:ring-2 focus:ring-indigo-500"
                    required
                  >
                    {docVersions.map((v) => (
                      <option key={v.id} value={v.id}>
                        Version {v.version_number} (Score: {v.brand_health_score ?? "N/A"})
                      </option>
                    ))}
                  </select>
                </div>
              )}

              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase mb-1">
                  Transition Notes{" "}
                  {pendingAction === "REQUEST_CHANGES" || pendingAction === "REJECT"
                    ? "(Mandatory)"
                    : "(Optional)"}
                </label>
                <textarea
                  value={transitionNotes}
                  onChange={(e) => setTransitionNotes(e.target.value)}
                  placeholder="Provide context, required changes, or sign-off remarks..."
                  rows={3}
                  required={
                    pendingAction === "REQUEST_CHANGES" || pendingAction === "REJECT"
                  }
                  className="w-full p-2 border border-slate-300 rounded text-xs focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              {pendingAction === "APPROVE" && (
                <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-xs text-emerald-800 space-y-1">
                  <p className="font-bold flex items-center gap-1">
                    <Lock className="w-3.5 h-3.5" /> Version Locking Guarantee
                  </p>
                  <p>
                    Approving will lock Version {review.version_number} as IMMUTABLE. No further edits or extractions can alter this version.
                  </p>
                </div>
              )}

              <div className="flex justify-end gap-2 pt-2 border-t border-slate-200">
                <button
                  type="button"
                  onClick={() => setTransitionModalOpen(false)}
                  className="px-3 py-1.5 border border-slate-300 rounded text-xs text-slate-600 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={transitionSubmitting}
                  className="px-4 py-1.5 bg-indigo-600 text-white rounded text-xs font-semibold hover:bg-indigo-700 disabled:opacity-50"
                >
                  {transitionSubmitting ? "Executing..." : "Confirm"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
