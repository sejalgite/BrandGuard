"use client";

import React, { useEffect, useState, useRef } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { Navbar } from "@/components/layout/Navbar";
import { Sidebar } from "@/components/layout/Sidebar";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { useAuth } from "@/lib/auth";
import {
  getDocumentDetails,
  listDocumentVersions,
  getVersionDetails,
  uploadNewVersion,
  downloadDocumentFile,
  retryExtraction,
  deleteDocument,
  DocumentItem,
  DocumentVersionItem,
  TextSegment,
} from "@/lib/api";
import {
  ArrowLeft,
  UploadCloud,
  FileText,
  Download,
  RotateCcw,
  CheckCircle2,
  AlertTriangle,
  AlertCircle,
  Clock,
  Layers,
  Hash,
  BookOpen,
  Calendar,
  Loader2,
  Copy,
  Check,
  Plus,
  Trash2,
  X,
  FileCheck,
} from "lucide-react";

export default function DocumentDetailsPage() {
  const params = useParams();
  const router = useRouter();
  const documentId = params.id as string;

  const { hasPermission } = useAuth();
  const canUpload = hasPermission("upload_docs");

  const [document, setDocument] = useState<DocumentItem | null>(null);
  const [versions, setVersions] = useState<DocumentVersionItem[]>([]);
  const [selectedVersion, setSelectedVersion] = useState<DocumentVersionItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<"segments" | "raw" | "metadata" | "history">("segments");
  const [copied, setCopied] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  // New version modal
  const [showVersionModal, setShowVersionModal] = useState(false);
  const [versionFile, setVersionFile] = useState<File | null>(null);
  const [uploadingVersion, setUploadingVersion] = useState(false);
  const [versionError, setVersionError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadData = async (targetVersionId?: string) => {
    setLoading(true);
    try {
      const doc = await getDocumentDetails(documentId);
      setDocument(doc);

      const vers = await listDocumentVersions(documentId);
      setVersions(vers);

      if (targetVersionId) {
        const fullVer = await getVersionDetails(documentId, targetVersionId);
        setSelectedVersion(fullVer);
      } else if (doc.latest_version) {
        const fullVer = await getVersionDetails(documentId, doc.latest_version.id);
        setSelectedVersion(fullVer);
      }
    } catch (err) {
      console.error("Failed to load document:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (documentId) {
      loadData();
    }
  }, [documentId]);

  const handleSelectVersion = async (versionId: string) => {
    try {
      const ver = await getVersionDetails(documentId, versionId);
      setSelectedVersion(ver);
    } catch (err) {
      console.error("Failed to fetch version details:", err);
    }
  };

  const handleCopyText = () => {
    if (!selectedVersion?.extracted_text) return;
    navigator.clipboard.writeText(selectedVersion.extracted_text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = async () => {
    if (!document || !selectedVersion) return;
    try {
      await downloadDocumentFile(
        document.id,
        selectedVersion.id,
        selectedVersion.original_filename || `${document.title}.bin`
      );
    } catch (err) {
      console.error("Download failed:", err);
    }
  };

  const handleRetry = async () => {
    if (!document || !selectedVersion) return;
    setRetrying(true);
    setMessage(null);
    try {
      const updated = await retryExtraction(document.id, selectedVersion.id);
      setSelectedVersion(updated);
      setMessage(`Extraction retried. New status: ${updated.extraction_status}.`);
      loadData(updated.id);
    } catch (err: any) {
      setMessage("Failed to retry extraction.");
    } finally {
      setRetrying(false);
    }
  };

  const handleUploadVersionSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!versionFile) {
      setVersionError("Please select a file to upload.");
      return;
    }
    setUploadingVersion(true);
    setVersionError(null);
    try {
      const formData = new FormData();
      formData.append("file", versionFile);
      const res = await uploadNewVersion(documentId, formData);
      setShowVersionModal(false);
      setVersionFile(null);
      setMessage(`Version ${res.version.version_number} uploaded successfully.`);
      await loadData(res.version.id);
    } catch (err: any) {
      const msg = err.response?.data?.detail || err.response?.data?.error?.message || "Version upload failed.";
      setVersionError(msg);
    } finally {
      setUploadingVersion(false);
    }
  };

  const handleDeleteDocument = async () => {
    if (!window.confirm("Are you sure you want to permanently delete this document and all its versions?")) {
      return;
    }
    try {
      await deleteDocument(documentId);
      router.push("/documents");
    } catch (err) {
      console.error("Delete failed:", err);
    }
  };

  if (loading && !document) {
    return (
      <ProtectedRoute requiredPermission="upload_docs">
        <div className="min-h-screen flex flex-col bg-slate-50">
          <Navbar />
          <div className="flex flex-1">
            <Sidebar />
            <main className="flex-1 p-12 text-center">
              <Loader2 className="h-8 w-8 animate-spin text-blue-600 mx-auto" />
              <p className="text-xs text-slate-500 mt-2">Loading document details...</p>
            </main>
          </div>
        </div>
      </ProtectedRoute>
    );
  }

  if (!document) {
    return (
      <ProtectedRoute requiredPermission="upload_docs">
        <div className="min-h-screen flex flex-col bg-slate-50">
          <Navbar />
          <div className="flex flex-1">
            <Sidebar />
            <main className="flex-1 p-12 text-center space-y-3">
              <AlertCircle className="h-8 w-8 text-rose-500 mx-auto" />
              <h2 className="text-base font-bold text-slate-800">Document Not Found</h2>
              <Link href="/documents" className="text-xs text-blue-600 font-semibold hover:underline">
                Return to Documents List
              </Link>
            </main>
          </div>
        </div>
      </ProtectedRoute>
    );
  }

  const structured = selectedVersion?.structured_content;
  const segments = structured?.segments || [];
  const headings = structured?.headings || [];

  return (
    <ProtectedRoute requiredPermission="upload_docs">
      <div className="min-h-screen flex flex-col bg-slate-50">
        <Navbar />

        <div className="flex flex-1">
          <Sidebar />

          <main className="flex-1 p-8 max-w-7xl mx-auto space-y-6">
            {/* Breadcrumb & Navigation */}
            <div className="flex items-center justify-between">
              <Link
                href="/documents"
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-600 hover:text-slate-900 transition-colors"
              >
                <ArrowLeft className="h-4 w-4" />
                <span>Back to Documents</span>
              </Link>

              <div className="flex items-center gap-2">
                {canUpload && (
                  <button
                    type="button"
                    onClick={() => {
                      setVersionError(null);
                      setVersionFile(null);
                      setShowVersionModal(true);
                    }}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold shadow-sm transition-all"
                  >
                    <Plus className="h-3.5 w-3.5" />
                    <span>Upload New Version</span>
                  </button>
                )}

                {selectedVersion && (
                  <button
                    type="button"
                    onClick={handleDownload}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 text-xs font-semibold shadow-sm transition-all"
                  >
                    <Download className="h-3.5 w-3.5 text-slate-500" />
                    <span>Download File</span>
                  </button>
                )}

                <button
                  type="button"
                  onClick={handleDeleteDocument}
                  className="inline-flex items-center p-1.5 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors"
                  title="Delete Document"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </div>

            {/* Document Header Banner */}
            <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="space-y-1">
                  <div className="flex items-center gap-2.5">
                    <span className="font-mono text-[10px] font-bold px-2 py-0.5 rounded bg-slate-100 text-slate-700">
                      {document.content_type}
                    </span>
                    <h1 className="text-xl font-extrabold text-slate-900 tracking-tight">
                      {document.title}
                    </h1>
                  </div>
                  <p className="text-xs text-slate-500">
                    File: <span className="font-mono">{selectedVersion?.original_filename || "N/A"}</span> · Uploaded on {new Date(document.created_at).toLocaleDateString()}
                  </p>
                </div>

                {/* Version Selector */}
                {versions.length > 1 && (
                  <div className="flex items-center gap-2 self-start sm:self-auto">
                    <span className="text-xs font-semibold text-slate-500">Version:</span>
                    <select
                      value={selectedVersion?.id}
                      onChange={(e) => handleSelectVersion(e.target.value)}
                      className="text-xs font-mono font-bold px-3 py-1.5 rounded-lg border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                    >
                      {versions.map((v) => (
                        <option key={v.id} value={v.id}>
                          v{v.version_number} ({new Date(v.created_at).toLocaleDateString()}) - {v.extraction_status}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
              </div>

              {message && (
                <div className="p-3 bg-blue-50 border border-blue-200 rounded-xl text-xs text-blue-800 flex items-center justify-between">
                  <span>{message}</span>
                  <button onClick={() => setMessage(null)} className="text-blue-600 font-bold hover:underline">
                    Dismiss
                  </button>
                </div>
              )}

              {/* Status & Metrics Bar */}
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3 pt-3 border-t border-slate-100 text-xs">
                <div className="p-3 rounded-xl bg-slate-50 border border-slate-100 space-y-0.5">
                  <div className="text-[10px] font-bold uppercase text-slate-400">Extraction</div>
                  <div className="font-bold text-slate-800">
                    {selectedVersion?.extraction_status || "PENDING"}
                  </div>
                </div>

                <div className="p-3 rounded-xl bg-slate-50 border border-slate-100 space-y-0.5">
                  <div className="text-[10px] font-bold uppercase text-slate-400">Word Count</div>
                  <div className="font-bold text-slate-800">
                    {selectedVersion?.word_count.toLocaleString() || 0}
                  </div>
                </div>

                <div className="p-3 rounded-xl bg-slate-50 border border-slate-100 space-y-0.5">
                  <div className="text-[10px] font-bold uppercase text-slate-400">Characters</div>
                  <div className="font-bold text-slate-800">
                    {selectedVersion?.character_count.toLocaleString() || 0}
                  </div>
                </div>

                <div className="p-3 rounded-xl bg-slate-50 border border-slate-100 space-y-0.5">
                  <div className="text-[10px] font-bold uppercase text-slate-400">Pages</div>
                  <div className="font-bold text-slate-800">
                    {structured?.total_pages || 1}
                  </div>
                </div>

                <div className="p-3 rounded-xl bg-slate-50 border border-slate-100 space-y-0.5">
                  <div className="text-[10px] font-bold uppercase text-slate-400">Segments</div>
                  <div className="font-bold text-slate-800">
                    {structured?.total_segments || 0}
                  </div>
                </div>

                <div className="p-3 rounded-xl bg-slate-50 border border-slate-100 space-y-0.5">
                  <div className="text-[10px] font-bold uppercase text-slate-400">File Size</div>
                  <div className="font-bold text-slate-800">
                    {selectedVersion?.file_size_bytes
                      ? `${(selectedVersion.file_size_bytes / 1024).toFixed(1)} KB`
                      : "—"}
                  </div>
                </div>
              </div>
            </div>

            {/* OCR Notice Banner if Tesseract unavailable */}
            {selectedVersion?.extraction_status === "OCR_UNAVAILABLE" && (
              <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 text-xs text-amber-900 space-y-1">
                <div className="flex items-center gap-2 font-bold text-amber-800">
                  <AlertTriangle className="h-4 w-4" />
                  <span>Optical Character Recognition (OCR) Engine Required</span>
                </div>
                <p>
                  {selectedVersion.extraction_metadata?.instructions ||
                    "This image or scanned PDF has no native text layer. Install Tesseract-OCR and ensure it is on system PATH to enable optical character extraction."}
                </p>
                <div className="pt-2">
                  <button
                    type="button"
                    onClick={handleRetry}
                    disabled={retrying}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-700 text-white font-semibold shadow-sm transition-all"
                  >
                    {retrying ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="h-3.5 w-3.5" />}
                    <span>Retry Extraction</span>
                  </button>
                </div>
              </div>
            )}

            {/* Content Tabs */}
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
              {/* Tab Bar */}
              <div className="flex items-center justify-between border-b border-slate-200 px-6 pt-3">
                <div className="flex gap-4">
                  <button
                    type="button"
                    onClick={() => setActiveTab("segments")}
                    className={`pb-3 text-xs font-semibold border-b-2 transition-colors ${
                      activeTab === "segments"
                        ? "border-blue-600 text-blue-600"
                        : "border-transparent text-slate-500 hover:text-slate-800"
                    }`}
                  >
                    Structured Text Segments ({segments.length})
                  </button>

                  <button
                    type="button"
                    onClick={() => setActiveTab("raw")}
                    className={`pb-3 text-xs font-semibold border-b-2 transition-colors ${
                      activeTab === "raw"
                        ? "border-blue-600 text-blue-600"
                        : "border-transparent text-slate-500 hover:text-slate-800"
                    }`}
                  >
                    Raw Extracted Text
                  </button>

                  <button
                    type="button"
                    onClick={() => setActiveTab("metadata")}
                    className={`pb-3 text-xs font-semibold border-b-2 transition-colors ${
                      activeTab === "metadata"
                        ? "border-blue-600 text-blue-600"
                        : "border-transparent text-slate-500 hover:text-slate-800"
                    }`}
                  >
                    Extraction Metadata
                  </button>

                  <button
                    type="button"
                    onClick={() => setActiveTab("history")}
                    className={`pb-3 text-xs font-semibold border-b-2 transition-colors ${
                      activeTab === "history"
                        ? "border-blue-600 text-blue-600"
                        : "border-transparent text-slate-500 hover:text-slate-800"
                    }`}
                  >
                    Version History ({versions.length})
                  </button>
                </div>

                {activeTab === "raw" && selectedVersion?.extracted_text && (
                  <button
                    type="button"
                    onClick={handleCopyText}
                    className="inline-flex items-center gap-1 text-xs font-semibold text-slate-600 hover:text-slate-900 pb-3"
                  >
                    {copied ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
                    <span>{copied ? "Copied" : "Copy Text"}</span>
                  </button>
                )}
              </div>

              {/* Tab Contents */}
              <div className="p-6">
                {/* 1. Structured Segments Tab */}
                {activeTab === "segments" && (
                  <div className="space-y-4">
                    {headings.length > 0 && (
                      <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-2">
                        <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                          Detected Headings & Sections
                        </span>
                        <div className="flex flex-wrap gap-2">
                          {headings.map((h, idx) => (
                            <span
                              key={idx}
                              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-bold bg-white text-blue-700 border border-blue-200 shadow-xs"
                            >
                              <BookOpen className="h-3 w-3 text-blue-500" />
                              {h.text}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {segments.length === 0 ? (
                      <div className="text-center py-12 text-slate-400 space-y-2">
                        <FileText className="h-8 w-8 mx-auto text-slate-300" />
                        <p className="text-xs font-medium">No structured segments generated yet.</p>
                      </div>
                    ) : (
                      <div className="space-y-2">
                        {segments.map((seg, idx) => (
                          <div
                            key={seg.segment_id || idx}
                            className="p-3.5 rounded-xl border border-slate-200 bg-white hover:border-blue-300 hover:shadow-xs transition-all space-y-1.5"
                          >
                            <div className="flex items-center justify-between text-[10px] text-slate-400 font-mono">
                              <div className="flex items-center gap-2">
                                <span className="font-bold text-slate-700 bg-slate-100 px-1.5 py-0.5 rounded">
                                  {seg.segment_id}
                                </span>
                                <span>Page {seg.page_number}</span>
                                <span>· Para {seg.paragraph_index}</span>
                                <span>· Offset [{seg.char_start}..{seg.char_end}]</span>
                              </div>
                              {seg.heading_context && (
                                <span className="text-blue-600 font-sans font-semibold truncate max-w-xs">
                                  Section: {seg.heading_context}
                                </span>
                              )}
                            </div>
                            <p className="text-xs text-slate-800 leading-relaxed font-sans">
                              {seg.text}
                            </p>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* 2. Raw Extracted Text Tab */}
                {activeTab === "raw" && (
                  <div className="bg-slate-50 rounded-xl p-6 border border-slate-200">
                    {selectedVersion?.extracted_text ? (
                      <pre className="text-xs text-slate-800 font-mono whitespace-pre-wrap leading-relaxed">
                        {selectedVersion.extracted_text}
                      </pre>
                    ) : (
                      <p className="text-xs text-slate-400 italic text-center py-8">
                        No text content extracted for this version.
                      </p>
                    )}
                  </div>
                )}

                {/* 3. Extraction Metadata Tab */}
                {activeTab === "metadata" && (
                  <div className="space-y-4">
                    <div className="bg-slate-900 rounded-xl p-5 text-emerald-400 font-mono text-xs overflow-x-auto shadow-inner">
                      <pre>
                        {JSON.stringify(
                          {
                            document_id: document.id,
                            version_number: selectedVersion?.version_number,
                            content_type: document.content_type,
                            original_filename: selectedVersion?.original_filename,
                            mime_type: selectedVersion?.mime_type,
                            file_size_bytes: selectedVersion?.file_size_bytes,
                            extraction_status: selectedVersion?.extraction_status,
                            word_count: selectedVersion?.word_count,
                            character_count: selectedVersion?.character_count,
                            metadata: selectedVersion?.extraction_metadata,
                          },
                          null,
                          2
                        )}
                      </pre>
                    </div>
                  </div>
                )}

                {/* 4. Version History Tab */}
                {activeTab === "history" && (
                  <div className="border border-slate-200 rounded-xl overflow-hidden">
                    <table className="w-full text-xs">
                      <thead className="bg-slate-50 border-b border-slate-200">
                        <tr>
                          <th className="text-left px-4 py-3 text-slate-500 font-semibold w-24">Version</th>
                          <th className="text-left px-4 py-3 text-slate-500 font-semibold">Filename</th>
                          <th className="text-left px-4 py-3 text-slate-500 font-semibold w-28">Status</th>
                          <th className="text-left px-4 py-3 text-slate-500 font-semibold w-24">Words</th>
                          <th className="text-left px-4 py-3 text-slate-500 font-semibold w-36">Created</th>
                          <th className="text-right px-4 py-3 text-slate-500 font-semibold w-28">Action</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {versions.map((v) => (
                          <tr
                            key={v.id}
                            className={`hover:bg-slate-50 transition-colors ${
                              v.id === selectedVersion?.id ? "bg-blue-50/40" : ""
                            }`}
                          >
                            <td className="px-4 py-3 font-mono font-bold text-slate-800">
                              v{v.version_number}
                            </td>
                            <td className="px-4 py-3 font-medium text-slate-700">
                              {v.original_filename || "N/A"}
                            </td>
                            <td className="px-4 py-3 font-semibold text-slate-600">
                              {v.extraction_status}
                            </td>
                            <td className="px-4 py-3 text-slate-600">
                              {v.word_count.toLocaleString()}
                            </td>
                            <td className="px-4 py-3 text-slate-500">
                              {new Date(v.created_at).toLocaleString()}
                            </td>
                            <td className="px-4 py-3 text-right">
                              <button
                                type="button"
                                onClick={() => handleSelectVersion(v.id)}
                                className="text-xs font-semibold text-blue-600 hover:underline"
                              >
                                View
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          </main>
        </div>
      </div>

      {/* Upload New Version Modal */}
      {showVersionModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-sm">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 space-y-4 shadow-2xl border border-slate-100">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <UploadCloud className="h-5 w-5 text-blue-600" />
                <span>Upload New Version</span>
              </h3>
              <button
                type="button"
                onClick={() => setShowVersionModal(false)}
                className="text-slate-400 hover:text-slate-700"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {versionError && (
              <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700 flex items-center gap-2">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span>{versionError}</span>
              </div>
            )}

            <form onSubmit={handleUploadVersionSubmit} className="space-y-4">
              <div
                onClick={() => fileInputRef.current?.click()}
                className="border-2 border-dashed border-slate-300 hover:border-slate-400 rounded-xl p-8 text-center cursor-pointer hover:bg-slate-50 transition-all space-y-2"
              >
                {versionFile ? (
                  <div>
                    <FileCheck className="h-8 w-8 text-emerald-600 mx-auto" />
                    <p className="text-xs font-bold text-slate-800 mt-1">{versionFile.name}</p>
                    <p className="text-[10px] text-slate-400">
                      {(versionFile.size / 1024).toFixed(1)} KB
                    </p>
                  </div>
                ) : (
                  <div>
                    <UploadCloud className="h-8 w-8 text-slate-400 mx-auto" />
                    <p className="text-xs font-semibold text-slate-700 mt-1">
                      Select new version file
                    </p>
                    <p className="text-[10px] text-slate-400">TXT, DOCX, PDF, PNG, JPG (Max 25 MB)</p>
                  </div>
                )}
              </div>

              <input
                ref={fileInputRef}
                type="file"
                accept=".txt,.docx,.pdf,.png,.jpg,.jpeg"
                className="hidden"
                onChange={(e) => {
                  if (e.target.files && e.target.files[0]) {
                    setVersionFile(e.target.files[0]);
                  }
                }}
              />

              <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowVersionModal(false)}
                  className="px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-lg"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={uploadingVersion || !versionFile}
                  className="px-4 py-2 text-xs font-semibold bg-blue-600 hover:bg-blue-700 text-white rounded-lg shadow-sm flex items-center gap-1.5 disabled:opacity-60"
                >
                  {uploadingVersion ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      <span>Ingesting Version...</span>
                    </>
                  ) : (
                    <span>Save Version</span>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </ProtectedRoute>
  );
}

