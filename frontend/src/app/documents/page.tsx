"use client";

import React, { useEffect, useState, useRef } from "react";
import Link from "next/link";
import { Navbar } from "@/components/layout/Navbar";
import { Sidebar } from "@/components/layout/Sidebar";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { useAuth } from "@/lib/auth";
import {
  listDocuments,
  uploadDocument,
  downloadDocumentFile,
  DocumentItem,
} from "@/lib/api";
import {
  UploadCloud,
  FileText,
  FileCode,
  Image as ImageIcon,
  Search,
  Plus,
  Loader2,
  AlertCircle,
  CheckCircle2,
  Download,
  Eye,
  FileCheck,
  AlertTriangle,
  X,
  Clock,
  Layers,
} from "lucide-react";

function ContentTypeIcon({ type }: { type: string }) {
  switch (type) {
    case "PDF":
      return <FileText className="h-4 w-4 text-rose-500" />;
    case "DOCX":
      return <FileCode className="h-4 w-4 text-blue-500" />;
    case "IMAGE":
      return <ImageIcon className="h-4 w-4 text-amber-500" />;
    default:
      return <FileText className="h-4 w-4 text-slate-500" />;
  }
}

function ExtractionStatusBadge({ status }: { status: string }) {
  switch (status) {
    case "COMPLETED":
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
          <CheckCircle2 className="h-3 w-3" />
          EXTRACTED
        </span>
      );
    case "OCR_UNAVAILABLE":
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-50 text-amber-700 border border-amber-200" title="Tesseract not installed on server">
          <AlertTriangle className="h-3 w-3" />
          OCR REQUIRED
        </span>
      );
    case "EMPTY":
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-600 border border-slate-200">
          EMPTY
        </span>
      );
    case "FAILED":
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-50 text-rose-700 border border-rose-200">
          <AlertCircle className="h-3 w-3" />
          FAILED
        </span>
      );
    default:
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-50 text-blue-700 border border-blue-200">
          <Clock className="h-3 w-3" />
          {status}
        </span>
      );
  }
}

export default function DocumentsPage() {
  const { hasPermission } = useAuth();
  const canUpload = hasPermission("upload_docs");

  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [selectedType, setSelectedType] = useState("ALL");

  // Upload modal state
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadTitle, setUploadTitle] = useState("");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const contentTypes = [
    { label: "All Formats", value: "ALL" },
    { label: "Plain Text (.txt)", value: "TEXT" },
    { label: "Word (.docx)", value: "DOCX" },
    { label: "PDF (.pdf)", value: "PDF" },
    { label: "Images (PNG/JPG)", value: "IMAGE" },
  ];

  const loadDocuments = () => {
    setLoading(true);
    listDocuments({
      content_type: selectedType !== "ALL" ? selectedType : undefined,
      search: search.trim() || undefined,
    })
      .then((data) => setDocuments(data))
      .catch((err) => console.error("Error loading documents:", err))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadDocuments();
  }, [selectedType]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    loadDocuments();
  };

  const handleFileDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileSelected(e.dataTransfer.files[0]);
    }
  };

  const handleFileSelected = (file: File) => {
    setUploadError(null);
    setUploadSuccess(null);
    const ext = file.name.split(".").pop()?.toLowerCase();
    const allowed = ["txt", "docx", "pdf", "png", "jpg", "jpeg"];
    if (!ext || !allowed.includes(ext)) {
      setUploadError(`Unsupported format '.${ext}'. Supported formats: TXT, DOCX, PDF, PNG, JPG, JPEG.`);
      return;
    }
    if (file.size > 25 * 1024 * 1024) {
      setUploadError("File size exceeds 25 MB limit.");
      return;
    }
    setUploadFile(file);
    if (!uploadTitle) {
      setUploadTitle(file.name.replace(/\.[^/.]+$/, ""));
    }
  };

  const handleUploadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!uploadFile) {
      setUploadError("Please select a file to upload.");
      return;
    }

    setUploading(true);
    setUploadError(null);
    try {
      const formData = new FormData();
      formData.append("file", uploadFile);
      if (uploadTitle.trim()) {
        formData.append("title", uploadTitle.trim());
      }

      const res = await uploadDocument(formData);
      setUploadSuccess(res.message);
      setUploadFile(null);
      setUploadTitle("");
      if (fileInputRef.current) fileInputRef.current.value = "";
      loadDocuments();
      setTimeout(() => {
        setShowUploadModal(false);
        setUploadSuccess(null);
      }, 1500);
    } catch (err: any) {
      const msg = err.response?.data?.detail || err.response?.data?.error?.message || "File upload failed.";
      setUploadError(msg);
    } finally {
      setUploading(false);
    }
  };

  const handleDownload = async (doc: DocumentItem) => {
    if (!doc.latest_version) return;
    try {
      await downloadDocumentFile(
        doc.id,
        doc.latest_version.id,
        doc.latest_version.original_filename || `${doc.title}.bin`
      );
    } catch (err) {
      console.error("Download failed:", err);
    }
  };

  return (
    <ProtectedRoute requiredPermission="upload_docs">
      <div className="min-h-screen flex flex-col bg-slate-50">
        <Navbar />

        <div className="flex flex-1">
          <Sidebar />

          <main className="flex-1 p-8 max-w-7xl mx-auto space-y-6">
            {/* Top Bar */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div>
                <h1 className="text-2xl font-extrabold text-slate-900 tracking-tight flex items-center gap-2.5">
                  <UploadCloud className="h-6 w-6 text-blue-600" />
                  <span>Content Ingestion & Documents</span>
                </h1>
                <p className="text-xs text-slate-500 mt-1">
                  Upload, extract, and inspect marketing collateral, campaign copy, and brand assets.
                </p>
              </div>

              {canUpload && (
                <button
                  type="button"
                  onClick={() => {
                    setUploadError(null);
                    setUploadSuccess(null);
                    setUploadFile(null);
                    setUploadTitle("");
                    setShowUploadModal(true);
                  }}
                  className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold shadow-md shadow-blue-500/20 transition-all self-start sm:self-auto"
                >
                  <Plus className="h-4 w-4" />
                  <span>Upload Document</span>
                </button>
              )}
            </div>

            {/* Filter and Search Bar */}
            <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col md:flex-row gap-4 justify-between items-center">
              {/* Type tabs */}
              <div className="flex flex-wrap gap-1 w-full md:w-auto">
                {contentTypes.map((t) => (
                  <button
                    key={t.value}
                    type="button"
                    onClick={() => setSelectedType(t.value)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                      selectedType === t.value
                        ? "bg-blue-600 text-white font-semibold"
                        : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>

              {/* Search Box */}
              <form onSubmit={handleSearchSubmit} className="flex gap-2 w-full md:w-72">
                <div className="relative flex-1">
                  <Search className="h-3.5 w-3.5 text-slate-400 absolute left-3 top-3" />
                  <input
                    type="text"
                    placeholder="Search documents by title..."
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

            {/* Documents List */}
            {loading ? (
              <div className="bg-white p-12 rounded-2xl border border-slate-200 text-center space-y-3">
                <Loader2 className="h-6 w-6 animate-spin text-blue-600 mx-auto" />
                <p className="text-xs text-slate-500">Loading documents...</p>
              </div>
            ) : documents.length === 0 ? (
              <div className="bg-white p-12 rounded-2xl border border-slate-200 text-center space-y-3">
                <FileCheck className="h-8 w-8 text-slate-300 mx-auto" />
                <h3 className="text-sm font-bold text-slate-800">No Ingested Documents Found</h3>
                <p className="text-xs text-slate-500 max-w-sm mx-auto">
                  Upload a marketing document (.txt, .docx, .pdf, or image) to extract structured text and paragraphs.
                </p>
              </div>
            ) : (
              <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
                <table className="w-full text-xs">
                  <thead className="bg-slate-50 border-b border-slate-200">
                    <tr>
                      <th className="text-left px-5 py-3 text-slate-500 font-semibold">Document Title</th>
                      <th className="text-left px-4 py-3 text-slate-500 font-semibold w-24">Type</th>
                      <th className="text-left px-4 py-3 text-slate-500 font-semibold w-20">Version</th>
                      <th className="text-left px-4 py-3 text-slate-500 font-semibold w-32">Status</th>
                      <th className="text-left px-4 py-3 text-slate-500 font-semibold w-28">Words</th>
                      <th className="text-left px-4 py-3 text-slate-500 font-semibold w-36">Uploaded</th>
                      <th className="text-right px-5 py-3 text-slate-500 font-semibold w-32">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {documents.map((doc) => {
                      const ver = doc.latest_version;
                      return (
                        <tr key={doc.id} className="hover:bg-slate-50 transition-colors">
                          <td className="px-5 py-3.5">
                            <div className="flex items-center gap-2.5">
                              <div className="p-1.5 rounded-lg bg-slate-100">
                                <ContentTypeIcon type={doc.content_type} />
                              </div>
                              <div>
                                <Link
                                  href={`/documents/${doc.id}`}
                                  className="font-bold text-slate-900 hover:text-blue-600 transition-colors"
                                >
                                  {doc.title}
                                </Link>
                                <div className="text-[11px] text-slate-400">
                                  {ver?.original_filename || "Original file"}
                                </div>
                              </div>
                            </div>
                          </td>
                          <td className="px-4 py-3.5">
                            <span className="font-mono text-[10px] font-semibold px-2 py-0.5 rounded bg-slate-100 text-slate-700">
                              {doc.content_type}
                            </span>
                          </td>
                          <td className="px-4 py-3.5">
                            <span className="font-mono text-xs font-bold text-slate-800">
                              v{ver?.version_number || 1}
                            </span>
                          </td>
                          <td className="px-4 py-3.5">
                            <ExtractionStatusBadge status={ver?.extraction_status || "PENDING"} />
                          </td>
                          <td className="px-4 py-3.5 text-slate-600 font-medium">
                            {ver ? `${ver.word_count.toLocaleString()} words` : "—"}
                          </td>
                          <td className="px-4 py-3.5 text-slate-500">
                            {new Date(doc.created_at).toLocaleDateString()}
                          </td>
                          <td className="px-5 py-3.5 text-right">
                            <div className="flex items-center justify-end gap-1.5">
                              <Link
                                href={`/documents/${doc.id}`}
                                className="inline-flex items-center gap-1 px-2.5 py-1 text-[11px] font-semibold text-blue-700 bg-blue-50 hover:bg-blue-100 rounded-lg transition-colors border border-blue-200"
                                title="Inspect Extracted Content"
                              >
                                <Eye className="h-3 w-3" />
                                <span>Inspect</span>
                              </Link>
                              {ver && (
                                <button
                                  type="button"
                                  onClick={() => handleDownload(doc)}
                                  className="inline-flex items-center p-1.5 text-slate-500 hover:text-slate-800 hover:bg-slate-100 rounded-lg transition-colors border border-slate-200"
                                  title="Download Original File"
                                >
                                  <Download className="h-3.5 w-3.5" />
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </main>
        </div>
      </div>

      {/* Upload Document Modal */}
      {showUploadModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-sm">
          <div className="bg-white rounded-2xl max-w-lg w-full p-6 space-y-4 shadow-2xl border border-slate-100">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <UploadCloud className="h-5 w-5 text-blue-600" />
                <span>Upload Content Document</span>
              </h3>
              <button
                type="button"
                onClick={() => setShowUploadModal(false)}
                className="text-slate-400 hover:text-slate-700"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {uploadError && (
              <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700 flex items-center gap-2">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span>{uploadError}</span>
              </div>
            )}

            {uploadSuccess && (
              <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-xs text-emerald-800 flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 shrink-0" />
                <span>{uploadSuccess}</span>
              </div>
            )}

            <form onSubmit={handleUploadSubmit} className="space-y-4">
              {/* Drag and drop zone */}
              <div
                onDragOver={(e) => {
                  e.preventDefault();
                  setIsDragOver(true);
                }}
                onDragLeave={() => setIsDragOver(false)}
                onDrop={handleFileDrop}
                onClick={() => fileInputRef.current?.click()}
                className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all ${
                  isDragOver
                    ? "border-blue-500 bg-blue-50"
                    : "border-slate-300 hover:border-slate-400 hover:bg-slate-50"
                }`}
              >
                {uploadFile ? (
                  <div className="space-y-1.5">
                    <FileCheck className="h-8 w-8 text-emerald-600 mx-auto" />
                    <p className="text-xs font-bold text-slate-800">{uploadFile.name}</p>
                    <p className="text-[10px] text-slate-400">
                      {(uploadFile.size / 1024).toFixed(1)} KB · Ready to ingest
                    </p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <UploadCloud className="h-8 w-8 text-slate-400 mx-auto" />
                    <div>
                      <p className="text-xs font-semibold text-slate-700">
                        Click to browse or drag and drop your file here
                      </p>
                      <p className="text-[10px] text-slate-400 mt-1">
                        Supported: TXT, DOCX, PDF, PNG, JPG, JPEG (Max 25 MB)
                      </p>
                    </div>
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
                    handleFileSelected(e.target.files[0]);
                  }
                }}
              />

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Document Title (optional)
                </label>
                <input
                  type="text"
                  placeholder="e.g. Q4 2026 Cloud Migration Campaign"
                  value={uploadTitle}
                  onChange={(e) => setUploadTitle(e.target.value)}
                  className="w-full text-xs px-3 py-2 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowUploadModal(false)}
                  className="px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-lg"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={uploading || !uploadFile}
                  className="px-4 py-2 text-xs font-semibold bg-blue-600 hover:bg-blue-700 text-white rounded-lg shadow-sm flex items-center gap-1.5 disabled:opacity-60"
                >
                  {uploading ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      <span>Ingesting & Extracting...</span>
                    </>
                  ) : (
                    <span>Upload & Extract</span>
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

