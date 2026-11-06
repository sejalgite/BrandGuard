"use client";

import React, { useEffect, useState, useRef } from "react";
import { Navbar } from "@/components/layout/Navbar";
import { Sidebar } from "@/components/layout/Sidebar";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { useAuth } from "@/lib/auth";
import {
  listAssets,
  createAsset,
  uploadAssetFile,
  BrandAssetItem,
  EntityStatus,
} from "@/lib/api";
import {
  Palette,
  Plus,
  Upload,
  Loader2,
  AlertCircle,
  X,
  Image as ImageIcon,
  Type,
  Layers,
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

type AssetTypeFilter = "ALL" | "COLOR" | "LOGO" | "TYPOGRAPHY" | "OTHER";

const ASSET_TYPE_TABS: { label: string; value: AssetTypeFilter; icon: React.ReactNode }[] = [
  { label: "All", value: "ALL", icon: <Layers className="h-3.5 w-3.5" /> },
  { label: "Colors", value: "COLOR", icon: <Palette className="h-3.5 w-3.5" /> },
  { label: "Logos", value: "LOGO", icon: <ImageIcon className="h-3.5 w-3.5" /> },
  { label: "Typography", value: "TYPOGRAPHY", icon: <Type className="h-3.5 w-3.5" /> },
];

export default function BrandAssetsPage() {
  const { hasPermission } = useAuth();
  const canManage = hasPermission("manage_constitution");

  const [assets, setAssets] = useState<BrandAssetItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [assetTypeFilter, setAssetTypeFilter] = useState<AssetTypeFilter>("ALL");

  // Create color modal
  const [showColorModal, setShowColorModal] = useState(false);
  const [creating, setCreating] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Color form fields
  const [assetCode, setAssetCode] = useState("");
  const [assetName, setAssetName] = useState("");
  const [hexColor, setHexColor] = useState("#000000");
  const [colorUsage, setColorUsage] = useState("");

  // File upload
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [uploadCode, setUploadCode] = useState("");
  const [uploadName, setUploadName] = useState("");
  const [uploadType, setUploadType] = useState("LOGO");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadAssets = () => {
    setLoading(true);
    listAssets(assetTypeFilter !== "ALL" ? assetTypeFilter : undefined)
      .then((data) => setAssets(data))
      .catch((err) => console.error("Error loading assets:", err))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadAssets();
  }, [assetTypeFilter]);

  const resetColorForm = () => {
    setAssetCode("");
    setAssetName("");
    setHexColor("#000000");
    setColorUsage("");
    setErrorMsg(null);
  };

  const resetUploadForm = () => {
    setUploadCode("");
    setUploadName("");
    setUploadType("LOGO");
    setUploadFile(null);
    setUploadError(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleCreateColor = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    if (!assetCode.trim() || !assetName.trim()) {
      setErrorMsg("Asset Code and Name are required.");
      return;
    }
    setCreating(true);
    try {
      await createAsset({
        asset_code: assetCode.trim().toUpperCase(),
        asset_type: "COLOR",
        name: assetName.trim(),
        specifications: {
          hex: hexColor,
          usage: colorUsage.trim() || "General brand color",
        },
        status: "DRAFT",
      });
      setShowColorModal(false);
      resetColorForm();
      loadAssets();
    } catch (err: any) {
      setErrorMsg(err.response?.data?.detail || "Failed to create color asset.");
    } finally {
      setCreating(false);
    }
  };

  const handleUploadAsset = async (e: React.FormEvent) => {
    e.preventDefault();
    setUploadError(null);
    if (!uploadCode.trim() || !uploadName.trim() || !uploadFile) {
      setUploadError("Asset Code, Name, and a file are required.");
      return;
    }

    const allowedTypes = ["image/png", "image/jpeg", "image/jpg", "image/svg+xml"];
    if (!allowedTypes.includes(uploadFile.type)) {
      setUploadError("Only PNG, JPG, JPEG, and SVG files are supported.");
      return;
    }

    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", uploadFile);
      formData.append("asset_code", uploadCode.trim().toUpperCase());
      formData.append("asset_type", uploadType);
      formData.append("name", uploadName.trim());
      await uploadAssetFile(formData);
      setShowUploadModal(false);
      resetUploadForm();
      loadAssets();
    } catch (err: any) {
      setUploadError(err.response?.data?.detail || "Failed to upload asset file.");
    } finally {
      setUploading(false);
    }
  };

  const colorAssets = assets.filter((a) => a.asset_type === "COLOR");
  const fileAssets = assets.filter((a) => a.asset_type !== "COLOR");

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
                  <Palette className="h-6 w-6 text-amber-600" />
                  <span>Brand Asset Library</span>
                </h1>
                <p className="text-xs text-slate-500 mt-1">
                  Official brand colors, logos, typography tokens, and visual assets.
                </p>
              </div>

              {canManage && (
                <div className="flex items-center gap-2 self-start sm:self-auto">
                  <button
                    type="button"
                    onClick={() => { resetUploadForm(); setShowUploadModal(true); }}
                    className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-900 text-white text-xs font-semibold shadow-md transition-all"
                  >
                    <Upload className="h-4 w-4" />
                    <span>Upload File</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => { resetColorForm(); setShowColorModal(true); }}
                    className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-amber-500 hover:bg-amber-600 text-white text-xs font-semibold shadow-md shadow-amber-500/20 transition-all"
                  >
                    <Plus className="h-4 w-4" />
                    <span>Add Color</span>
                  </button>
                </div>
              )}
            </div>

            {/* Filter Tabs */}
            <div className="bg-white p-3 rounded-xl border border-slate-200 shadow-sm flex gap-1 flex-wrap">
              {ASSET_TYPE_TABS.map((tab) => (
                <button
                  key={tab.value}
                  type="button"
                  onClick={() => setAssetTypeFilter(tab.value)}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                    assetTypeFilter === tab.value
                      ? "bg-amber-500 text-white font-semibold"
                      : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                  }`}
                >
                  {tab.icon}
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Content */}
            {loading ? (
              <div className="bg-white p-12 rounded-2xl border border-slate-200 text-center space-y-3">
                <Loader2 className="h-6 w-6 animate-spin text-amber-500 mx-auto" />
                <p className="text-xs text-slate-500">Loading brand assets...</p>
              </div>
            ) : assets.length === 0 ? (
              <div className="bg-white p-12 rounded-2xl border border-slate-200 text-center space-y-3">
                <Palette className="h-8 w-8 text-slate-300 mx-auto" />
                <h3 className="text-sm font-bold text-slate-800">No Assets Found</h3>
                <p className="text-xs text-slate-500 max-w-sm mx-auto">
                  Add brand colors or upload logo files. You can also seed ApexCloud demo data from the Constitution Overview.
                </p>
              </div>
            ) : (
              <div className="space-y-6">
                {/* Color Swatches Section */}
                {(assetTypeFilter === "ALL" || assetTypeFilter === "COLOR") && colorAssets.length > 0 && (
                  <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-4">
                    <div className="flex items-center gap-2">
                      <Palette className="h-4 w-4 text-amber-500" />
                      <h2 className="text-sm font-bold text-slate-900">Brand Colors</h2>
                      <span className="text-xs text-slate-500 ml-auto">{colorAssets.length} colors</span>
                    </div>
                    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-4">
                      {colorAssets.map((asset) => {
                        const hex = asset.specifications?.hex as string | undefined;
                        const usage = asset.specifications?.usage as string | undefined;
                        return (
                          <div key={asset.id} className="space-y-2">
                            <div
                              className="h-20 rounded-xl border-2 border-slate-200 shadow-sm"
                              style={{ backgroundColor: hex ?? "#cccccc" }}
                              title={hex ?? "unknown"}
                            />
                            <div className="space-y-0.5">
                              <div className="text-xs font-bold text-slate-800 truncate">{asset.name}</div>
                              <div className="font-mono text-[10px] text-slate-500 uppercase">{hex ?? "—"}</div>
                              {usage && (
                                <div className="text-[10px] text-slate-400 truncate" title={usage}>{usage}</div>
                              )}
                              <StatusBadge status={asset.status} />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* File Assets Section */}
                {(assetTypeFilter === "ALL" || assetTypeFilter !== "COLOR") && fileAssets.length > 0 && (
                  <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
                    <div className="px-6 py-4 border-b border-slate-100 flex items-center gap-2">
                      <ImageIcon className="h-4 w-4 text-slate-500" />
                      <h2 className="text-sm font-bold text-slate-900">File Assets</h2>
                      <span className="text-xs text-slate-500 ml-auto">{fileAssets.length} files</span>
                    </div>
                    <table className="w-full text-xs">
                      <thead className="bg-slate-50 border-b border-slate-200">
                        <tr>
                          <th className="text-left px-5 py-3 text-slate-500 font-semibold w-28">Code</th>
                          <th className="text-left px-5 py-3 text-slate-500 font-semibold">Name</th>
                          <th className="text-left px-5 py-3 text-slate-500 font-semibold w-28">Type</th>
                          <th className="text-left px-5 py-3 text-slate-500 font-semibold">File</th>
                          <th className="text-left px-5 py-3 text-slate-500 font-semibold w-28">Status</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {fileAssets.map((asset) => (
                          <tr key={asset.id} className="hover:bg-slate-50 transition-colors">
                            <td className="px-5 py-3">
                              <span className="font-mono font-bold text-slate-800 bg-slate-100 px-1.5 py-0.5 rounded">
                                {asset.asset_code}
                              </span>
                            </td>
                            <td className="px-5 py-3 font-medium text-slate-800">{asset.name}</td>
                            <td className="px-5 py-3">
                              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200">
                                {asset.asset_type}
                              </span>
                            </td>
                            <td className="px-5 py-3 text-slate-500">
                              {asset.file_path ? (
                                <span className="font-mono text-[10px] bg-slate-100 px-2 py-0.5 rounded">
                                  {asset.file_path.split("/").pop() ?? asset.file_path}
                                </span>
                              ) : (
                                <span className="text-slate-300 italic">No file</span>
                              )}
                            </td>
                            <td className="px-5 py-3">
                              <StatusBadge status={asset.status} />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
          </main>
        </div>
      </div>

      {/* Create Brand Color Modal */}
      {showColorModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-sm">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 space-y-4 shadow-2xl border border-slate-100">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <Palette className="h-5 w-5 text-amber-500" />
                <span>Add Brand Color</span>
              </h3>
              <button type="button" onClick={() => setShowColorModal(false)} className="text-slate-400 hover:text-slate-700">
                <X className="h-5 w-5" />
              </button>
            </div>

            {errorMsg && (
              <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700 flex items-center gap-2">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span>{errorMsg}</span>
              </div>
            )}

            <form onSubmit={handleCreateColor} className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Asset Code</label>
                  <input
                    type="text"
                    placeholder="e.g. CLR-01"
                    value={assetCode}
                    onChange={(e) => setAssetCode(e.target.value.toUpperCase())}
                    className="w-full text-xs px-3 py-2 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-amber-400 font-mono"
                    required
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Color Name</label>
                  <input
                    type="text"
                    placeholder="e.g. Primary Blue"
                    value={assetName}
                    onChange={(e) => setAssetName(e.target.value)}
                    className="w-full text-xs px-3 py-2 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-amber-400"
                    required
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">HEX Color</label>
                <div className="flex items-center gap-3">
                  <input
                    type="color"
                    value={hexColor}
                    onChange={(e) => setHexColor(e.target.value)}
                    className="h-10 w-16 rounded-lg border border-slate-300 cursor-pointer p-0.5"
                  />
                  <input
                    type="text"
                    value={hexColor}
                    onChange={(e) => setHexColor(e.target.value)}
                    placeholder="#000000"
                    className="flex-1 text-xs font-mono px-3 py-2 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-amber-400"
                    pattern="^#[0-9A-Fa-f]{6}$"
                  />
                </div>
              </div>

              {/* Preview swatch */}
              <div className="flex items-center gap-3 p-3 rounded-xl bg-slate-50 border border-slate-200">
                <div
                  className="h-12 w-12 rounded-lg border-2 border-slate-200 shadow-sm shrink-0"
                  style={{ backgroundColor: hexColor }}
                />
                <div>
                  <div className="text-xs font-bold text-slate-800">{assetName || "Color Preview"}</div>
                  <div className="font-mono text-[11px] text-slate-500 uppercase">{hexColor}</div>
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Usage Description (optional)</label>
                <input
                  type="text"
                  placeholder="e.g. Primary CTAs and button backgrounds"
                  value={colorUsage}
                  onChange={(e) => setColorUsage(e.target.value)}
                  className="w-full text-xs px-3 py-2 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-amber-400"
                />
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowColorModal(false)}
                  className="px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-lg"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creating}
                  className="px-4 py-2 text-xs font-semibold bg-amber-500 hover:bg-amber-600 text-white rounded-lg shadow-sm flex items-center gap-1.5 disabled:opacity-70"
                >
                  {creating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Save Color"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Upload Asset File Modal */}
      {showUploadModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-sm">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 space-y-4 shadow-2xl border border-slate-100">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <Upload className="h-5 w-5 text-slate-700" />
                <span>Upload Asset File</span>
              </h3>
              <button type="button" onClick={() => setShowUploadModal(false)} className="text-slate-400 hover:text-slate-700">
                <X className="h-5 w-5" />
              </button>
            </div>

            {uploadError && (
              <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700 flex items-center gap-2">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span>{uploadError}</span>
              </div>
            )}

            <form onSubmit={handleUploadAsset} className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Asset Code</label>
                  <input
                    type="text"
                    placeholder="e.g. LOGO-01"
                    value={uploadCode}
                    onChange={(e) => setUploadCode(e.target.value.toUpperCase())}
                    className="w-full text-xs px-3 py-2 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-slate-500 font-mono"
                    required
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Asset Type</label>
                  <select
                    value={uploadType}
                    onChange={(e) => setUploadType(e.target.value)}
                    className="w-full text-xs px-3 py-2 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-slate-500 bg-white"
                  >
                    <option value="LOGO">Logo</option>
                    <option value="TYPOGRAPHY">Typography</option>
                    <option value="OTHER">Other</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Asset Name</label>
                <input
                  type="text"
                  placeholder="e.g. ApexCloud Primary Logo"
                  value={uploadName}
                  onChange={(e) => setUploadName(e.target.value)}
                  className="w-full text-xs px-3 py-2 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-slate-500"
                  required
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">File (PNG, JPG, JPEG, SVG)</label>
                <div
                  className="border-2 border-dashed border-slate-300 rounded-xl p-6 text-center cursor-pointer hover:border-slate-400 hover:bg-slate-50 transition-all"
                  onClick={() => fileInputRef.current?.click()}
                >
                  {uploadFile ? (
                    <div className="space-y-1">
                      <ImageIcon className="h-6 w-6 text-slate-500 mx-auto" />
                      <p className="text-xs font-semibold text-slate-700">{uploadFile.name}</p>
                      <p className="text-[10px] text-slate-400">{(uploadFile.size / 1024).toFixed(1)} KB</p>
                    </div>
                  ) : (
                    <div className="space-y-1">
                      <Upload className="h-6 w-6 text-slate-300 mx-auto" />
                      <p className="text-xs text-slate-500">Click to select a file</p>
                      <p className="text-[10px] text-slate-400">PNG, JPG, JPEG, SVG supported</p>
                    </div>
                  )}
                </div>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".png,.jpg,.jpeg,.svg"
                  className="hidden"
                  onChange={(e) => setUploadFile(e.target.files?.[0] ?? null)}
                />
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowUploadModal(false)}
                  className="px-4 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-lg"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={uploading}
                  className="px-4 py-2 text-xs font-semibold bg-slate-800 hover:bg-slate-900 text-white rounded-lg shadow-sm flex items-center gap-1.5 disabled:opacity-70"
                >
                  {uploading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : (
                    <>
                      <Upload className="h-3.5 w-3.5" />
                      Upload
                    </>
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

