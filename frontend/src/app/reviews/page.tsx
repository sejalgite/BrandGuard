"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import {
  CheckCircle2,
  Clock,
  AlertCircle,
  FileText,
  Search,
  RefreshCw,
  Plus,
  ArrowRight,
  ShieldAlert,
  UserCheck,
  Filter,
  CheckCircle,
  XCircle,
  RotateCcw,
  Sparkles
} from "lucide-react";
import {
  listReviews,
  getReviewQueueStats,
  createReview,
  listDocuments,
  ReviewItem,
  ReviewQueueStats,
  DocumentItem,
  ReviewWorkflowStatus
} from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function ReviewsQueuePage() {
  const { user } = useAuth();
  const [reviews, setReviews] = useState<ReviewItem[]>([]);
  const [stats, setStats] = useState<ReviewQueueStats | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [selectedStatus, setSelectedStatus] = useState<string>("ALL");
  const [search, setSearch] = useState<string>("");
  const [assignedToMe, setAssignedToMe] = useState<boolean>(false);

  // Submission Modal state
  const [showSubmitModal, setShowSubmitModal] = useState<boolean>(false);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [selectedDocId, setSelectedDocId] = useState<string>("");
  const [submissionPriority, setSubmissionPriority] = useState<string>("MEDIUM");
  const [submissionNotes, setSubmissionNotes] = useState<string>("");
  const [dueDate, setDueDate] = useState<string>("");
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const fetchReviewsAndStats = async () => {
    setLoading(true);
    setError(null);
    try {
      const [revs, st] = await Promise.all([
        listReviews({
          status: selectedStatus !== "ALL" ? selectedStatus : undefined,
          assigned_to_me: assignedToMe ? true : undefined,
        }),
        getReviewQueueStats(),
      ]);
      setReviews(revs);
      setStats(st);
    } catch (err: any) {
      setError(
        err?.response?.data?.error?.message ||
          err?.message ||
          "Failed to load reviews and queue statistics."
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReviewsAndStats();
  }, [selectedStatus, assignedToMe]);

  const openSubmitModal = async () => {
    setShowSubmitModal(true);
    setSubmitError(null);
    try {
      const docs = await listDocuments();
      setDocuments(docs);
      if (docs.length > 0) {
        setSelectedDocId(docs[0].id);
      }
    } catch (err: any) {
      setSubmitError("Could not load documents for submission.");
    }
  };

  const handleCreateReview = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedDocId) {
      setSubmitError("Please select a document to submit for review.");
      return;
    }
    setSubmitting(true);
    setSubmitError(null);
    try {
      await createReview({
        document_id: selectedDocId,
        priority: submissionPriority,
        submission_notes: submissionNotes.trim() || undefined,
        due_date: dueDate || undefined,
      });
      setShowSubmitModal(false);
      setSubmissionNotes("");
      fetchReviewsAndStats();
    } catch (err: any) {
      setSubmitError(
        err?.response?.data?.error?.message ||
          err?.message ||
          "Failed to submit document for review."
      );
    } finally {
      setSubmitting(false);
    }
  };

  const filteredReviews = reviews.filter((r) => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return (
      (r.document_title && r.document_title.toLowerCase().includes(q)) ||
      (r.creator_name && r.creator_name.toLowerCase().includes(q)) ||
      (r.reviewer_name && r.reviewer_name.toLowerCase().includes(q)) ||
      r.status.toLowerCase().includes(q)
    );
  });

  const getStatusBadge = (status: ReviewWorkflowStatus) => {
    switch (status) {
      case "DRAFT":
        return <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-700 border border-slate-300">Draft</span>;
      case "SUBMITTED":
        return <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800 border border-blue-200">Submitted</span>;
      case "UNDER_REVIEW":
        return <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-purple-100 text-purple-800 border border-purple-200">Under Review</span>;
      case "CHANGES_REQUESTED":
        return <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-800 border border-amber-200">Changes Requested</span>;
      case "RESUBMITTED":
        return <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-indigo-100 text-indigo-800 border border-indigo-200">Resubmitted</span>;
      case "PENDING_BRAND_APPROVAL":
        return <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-teal-100 text-teal-800 border border-teal-200">Pending Brand Approval</span>;
      case "PENDING_LEGAL_APPROVAL":
        return <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-rose-100 text-rose-800 border border-rose-200">Pending Legal Approval</span>;
      case "APPROVED":
        return <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-800 border border-emerald-200 flex items-center gap-1 w-fit"><CheckCircle className="w-3 h-3" /> Approved</span>;
      case "REJECTED":
        return <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800 border border-red-200 flex items-center gap-1 w-fit"><XCircle className="w-3 h-3" /> Rejected</span>;
      case "WITHDRAWN":
        return <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-700 border border-gray-300">Withdrawn</span>;
      default:
        return <span className="px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-800">{status}</span>;
    }
  };

  const getPriorityBadge = (priority: string) => {
    switch (priority) {
      case "CRITICAL":
        return <span className="text-xs font-bold text-red-600 bg-red-50 border border-red-200 px-2 py-0.5 rounded">CRITICAL</span>;
      case "HIGH":
        return <span className="text-xs font-semibold text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded">HIGH</span>;
      case "MEDIUM":
        return <span className="text-xs font-medium text-slate-600 bg-slate-50 border border-slate-200 px-2 py-0.5 rounded">MEDIUM</span>;
      default:
        return <span className="text-xs text-slate-500">{priority}</span>;
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-slate-200">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 flex items-center gap-2">
            <CheckCircle2 className="w-7 h-7 text-indigo-600" />
            Human Review & Approval Workflow
          </h1>
          <p className="text-slate-500 text-sm mt-1">
            Governance queue, reviewer collaboration, finding resolution, and immutable version sign-off.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={fetchReviewsAndStats}
            className="p-2 border border-slate-300 rounded-lg text-slate-600 hover:bg-slate-50 transition"
            title="Refresh Queue"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
          <button
            onClick={openSubmitModal}
            className="flex items-center gap-1.5 px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 shadow-sm transition"
          >
            <Plus className="w-4 h-4" /> Submit for Review
          </button>
        </div>
      </div>

      {/* KPI Cards */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
          <div className="bg-white p-3.5 rounded-xl border border-slate-200 shadow-sm">
            <span className="text-xs font-medium text-slate-500 uppercase tracking-wider">Total</span>
            <p className="text-xl font-bold text-slate-800 mt-0.5">{stats.total}</p>
          </div>
          <div className="bg-white p-3.5 rounded-xl border border-blue-200 bg-blue-50/20 shadow-sm">
            <span className="text-xs font-medium text-blue-600 uppercase tracking-wider">Submitted</span>
            <p className="text-xl font-bold text-blue-700 mt-0.5">{stats.submitted}</p>
          </div>
          <div className="bg-white p-3.5 rounded-xl border border-purple-200 bg-purple-50/20 shadow-sm">
            <span className="text-xs font-medium text-purple-600 uppercase tracking-wider">In Review</span>
            <p className="text-xl font-bold text-purple-700 mt-0.5">{stats.under_review}</p>
          </div>
          <div className="bg-white p-3.5 rounded-xl border border-amber-200 bg-amber-50/20 shadow-sm">
            <span className="text-xs font-medium text-amber-600 uppercase tracking-wider">Changes Req.</span>
            <p className="text-xl font-bold text-amber-700 mt-0.5">{stats.changes_requested}</p>
          </div>
          <div className="bg-white p-3.5 rounded-xl border border-teal-200 bg-teal-50/20 shadow-sm">
            <span className="text-xs font-medium text-teal-600 uppercase tracking-wider">Pending Sign-off</span>
            <p className="text-xl font-bold text-teal-700 mt-0.5">{stats.pending_approval}</p>
          </div>
          <div className="bg-white p-3.5 rounded-xl border border-emerald-200 bg-emerald-50/20 shadow-sm">
            <span className="text-xs font-medium text-emerald-600 uppercase tracking-wider">Approved</span>
            <p className="text-xl font-bold text-emerald-700 mt-0.5">{stats.approved}</p>
          </div>
          <div className="bg-white p-3.5 rounded-xl border border-indigo-200 bg-indigo-50/20 shadow-sm">
            <span className="text-xs font-medium text-indigo-600 uppercase tracking-wider">My Queue</span>
            <p className="text-xl font-bold text-indigo-700 mt-0.5">{stats.assigned_to_current_user}</p>
          </div>
        </div>
      )}

      {/* Filter Tabs & Search Bar */}
      <div className="bg-white rounded-xl border border-slate-200 p-4 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          {/* Status Tabs */}
          <div className="flex flex-wrap gap-1 bg-slate-100 p-1 rounded-lg">
            {[
              { id: "ALL", label: "All Reviews" },
              { id: "SUBMITTED", label: "Submitted" },
              { id: "UNDER_REVIEW", label: "Under Review" },
              { id: "CHANGES_REQUESTED", label: "Changes Requested" },
              { id: "PENDING_BRAND_APPROVAL", label: "Brand Approval" },
              { id: "APPROVED", label: "Approved" },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setSelectedStatus(tab.id)}
                className={`px-3 py-1.5 rounded-md text-xs font-medium transition ${
                  selectedStatus === tab.id
                    ? "bg-white text-indigo-700 shadow-sm"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Assigned to me toggle */}
          <label className="flex items-center gap-2 cursor-pointer text-xs font-medium text-slate-700 bg-slate-50 border border-slate-200 px-3 py-1.5 rounded-lg hover:bg-slate-100">
            <input
              type="checkbox"
              checked={assignedToMe}
              onChange={(e) => setAssignedToMe(e.target.checked)}
              className="rounded text-indigo-600 focus:ring-indigo-500"
            />
            <UserCheck className="w-3.5 h-3.5 text-indigo-600" /> Assigned to Me
          </label>
        </div>

        {/* Search Bar */}
        <div className="relative">
          <Search className="w-4 h-4 absolute left-3 top-3 text-slate-400" />
          <input
            type="text"
            placeholder="Search reviews by document title, submitter, reviewer..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>
      </div>

      {/* Review Queue Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        {loading ? (
          <div className="p-12 text-center text-slate-500">
            <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-indigo-600" />
            Loading review queue...
          </div>
        ) : error ? (
          <div className="p-6 text-center text-red-600">
            <AlertCircle className="w-6 h-6 mx-auto mb-2" />
            {error}
          </div>
        ) : filteredReviews.length === 0 ? (
          <div className="p-12 text-center text-slate-500 space-y-3">
            <FileText className="w-10 h-10 mx-auto text-slate-300" />
            <p className="text-base font-semibold text-slate-700">No reviews found</p>
            <p className="text-xs text-slate-400 max-w-sm mx-auto">
              There are no documents matching your current filter criteria. Submit a document or clear filters.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 border-b border-slate-200 text-xs font-semibold text-slate-500 uppercase tracking-wider">
                <tr>
                  <th className="px-5 py-3">Document & Version</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Priority</th>
                  <th className="px-4 py-3">Brand Score</th>
                  <th className="px-4 py-3">Submitter</th>
                  <th className="px-4 py-3">Assigned Reviewer</th>
                  <th className="px-4 py-3">Created</th>
                  <th className="px-5 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredReviews.map((r) => (
                  <tr key={r.id} className="hover:bg-slate-50/80 transition">
                    <td className="px-5 py-3.5">
                      <div className="font-semibold text-slate-900 flex items-center gap-2">
                        {r.document_title || "Untitled Document"}
                        <span className="text-xs px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200">
                          v{r.version_number || 1}
                        </span>
                      </div>
                      {r.submission_notes && (
                        <p className="text-xs text-slate-500 truncate max-w-xs mt-0.5">
                          "{r.submission_notes}"
                        </p>
                      )}
                    </td>
                    <td className="px-4 py-3.5 whitespace-nowrap">
                      {getStatusBadge(r.status)}
                    </td>
                    <td className="px-4 py-3.5 whitespace-nowrap">
                      {getPriorityBadge(r.priority)}
                    </td>
                    <td className="px-4 py-3.5 whitespace-nowrap">
                      {r.brand_health_score !== undefined && r.brand_health_score !== null ? (
                        <span
                          className={`text-xs font-bold px-2 py-0.5 rounded-full ${
                            r.brand_health_score >= 80
                              ? "bg-emerald-100 text-emerald-800"
                              : r.brand_health_score >= 60
                              ? "bg-amber-100 text-amber-800"
                              : "bg-red-100 text-red-800"
                          }`}
                        >
                          {r.brand_health_score.toFixed(0)}%
                        </span>
                      ) : (
                        <span className="text-xs text-slate-400">N/A</span>
                      )}
                    </td>
                    <td className="px-4 py-3.5 whitespace-nowrap text-slate-700 text-xs">
                      {r.creator_name || "Unknown"}
                    </td>
                    <td className="px-4 py-3.5 whitespace-nowrap text-slate-700 text-xs">
                      {r.reviewer_name ? (
                        <span className="flex items-center gap-1 text-indigo-700 font-medium">
                          <UserCheck className="w-3.5 h-3.5" />
                          {r.reviewer_name}
                        </span>
                      ) : (
                        <span className="text-slate-400 italic">Unassigned</span>
                      )}
                    </td>
                    <td className="px-4 py-3.5 whitespace-nowrap text-xs text-slate-500">
                      {new Date(r.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-5 py-3.5 text-right whitespace-nowrap">
                      <Link
                        href={`/reviews/${r.id}`}
                        className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-indigo-600 bg-indigo-50 border border-indigo-200 rounded-lg hover:bg-indigo-100 transition"
                      >
                        Workspace <ArrowRight className="w-3 h-3" />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Submit for Review Modal */}
      {showSubmitModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6 space-y-4 border border-slate-200">
            <div className="flex items-center justify-between pb-2 border-b border-slate-200">
              <h3 className="text-lg font-bold text-slate-900 flex items-center gap-2">
                <CheckCircle2 className="w-5 h-5 text-indigo-600" />
                Submit Document for Review
              </h3>
              <button
                onClick={() => setShowSubmitModal(false)}
                className="text-slate-400 hover:text-slate-600 text-lg font-bold"
              >
                &times;
              </button>
            </div>

            {submitError && (
              <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-600">
                {submitError}
              </div>
            )}

            <form onSubmit={handleCreateReview} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase mb-1">
                  Select Ingested Document
                </label>
                <select
                  value={selectedDocId}
                  onChange={(e) => setSelectedDocId(e.target.value)}
                  className="w-full p-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500"
                  required
                >
                  {documents.length === 0 ? (
                    <option value="">No documents available</option>
                  ) : (
                    documents.map((doc) => (
                      <option key={doc.id} value={doc.id}>
                        {doc.title} ({doc.content_type})
                      </option>
                    ))
                  )}
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase mb-1">
                  Review Priority
                </label>
                <select
                  value={submissionPriority}
                  onChange={(e) => setSubmissionPriority(e.target.value)}
                  className="w-full p-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500"
                >
                  <option value="LOW">Low</option>
                  <option value="MEDIUM">Medium</option>
                  <option value="HIGH">High</option>
                  <option value="CRITICAL">Critical</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase mb-1">
                  Target Due Date (Optional)
                </label>
                <input
                  type="date"
                  value={dueDate}
                  onChange={(e) => setDueDate(e.target.value)}
                  className="w-full p-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase mb-1">
                  Submission Notes / Context
                </label>
                <textarea
                  value={submissionNotes}
                  onChange={(e) => setSubmissionNotes(e.target.value)}
                  placeholder="E.g., Q4 Enterprise campaign copy ready for reviewer sign-off..."
                  rows={3}
                  className="w-full p-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-slate-200">
                <button
                  type="button"
                  onClick={() => setShowSubmitModal(false)}
                  className="px-4 py-2 border border-slate-300 rounded-lg text-sm text-slate-600 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting || !selectedDocId}
                  className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
                >
                  {submitting ? "Submitting..." : "Submit Review"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

