"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { listOrganizations, OrganizationInfo } from "@/lib/api";
import {
  ShieldCheck,
  Building2,
  Mail,
  Lock,
  User as UserIcon,
  BadgeCheck,
  AlertCircle,
  PlusCircle,
  ArrowRight,
  Loader2,
  ShieldAlert,
} from "lucide-react";

export default function LoginPage() {
  const router = useRouter();
  const { login, register, bootstrap, isAuthenticated, isLoading } = useAuth();

  const [mode, setMode] = useState<"login" | "register" | "bootstrap">("login");
  const [organizations, setOrganizations] = useState<OrganizationInfo[]>([]);
  const [loadingOrgs, setLoadingOrgs] = useState<boolean>(true);

  // Common form states
  const [orgSlugOrId, setOrgSlugOrId] = useState<string>("");
  const [email, setEmail] = useState<string>("");
  const [password, setPassword] = useState<string>("");
  const [fullName, setFullName] = useState<string>("");

  // Bootstrap fields
  const [bootstrapOrgName, setBootstrapOrgName] = useState<string>("");
  const [bootstrapOrgSlug, setBootstrapOrgSlug] = useState<string>("");

  // Submission & errors
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // If already logged in, redirect home
  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      router.push("/");
    }
  }, [isLoading, isAuthenticated, router]);

  // Load existing organisations
  useEffect(() => {
    listOrganizations()
      .then((orgs) => {
        setOrganizations(orgs);
        if (orgs.length > 0 && !orgSlugOrId) {
          setOrgSlugOrId(orgs[0].slug);
        }
      })
      .catch((err) => {
        console.warn("Failed to list orgs:", err);
      })
      .finally(() => {
        setLoadingOrgs(false);
      });
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    setSuccessMsg(null);

    setSubmitting(true);
    try {
      if (mode === "bootstrap") {
        if (!bootstrapOrgName.trim() || !bootstrapOrgSlug.trim()) {
          setErrorMsg("Organisation name and slug are required.");
          setSubmitting(false);
          return;
        }
        if (!email.trim() || !password || !fullName.trim()) {
          setErrorMsg("Admin full name, email, and password are required.");
          setSubmitting(false);
          return;
        }
        await bootstrap(bootstrapOrgName, bootstrapOrgSlug, email, password, fullName);
      } else if (mode === "login") {
        if (!orgSlugOrId.trim()) {
          setErrorMsg("Please select or enter an organisation.");
          setSubmitting(false);
          return;
        }
        if (!email.trim() || !password) {
          setErrorMsg("Please enter both email and password.");
          setSubmitting(false);
          return;
        }
        await login(email, password, orgSlugOrId);
      } else {
        // mode === "register"
        if (!orgSlugOrId.trim()) {
          setErrorMsg("Please select an organisation to join.");
          setSubmitting(false);
          return;
        }
        if (!fullName.trim() || !email.trim() || !password) {
          setErrorMsg("Please complete all registration fields.");
          setSubmitting(false);
          return;
        }
        await register(email, password, fullName, orgSlugOrId);
      }
    } catch (err: any) {
      const detail =
        err.response?.data?.error?.message ||
        err.response?.data?.detail ||
        "Authentication failed. Please verify credentials.";
      setErrorMsg(detail);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-indigo-950 to-slate-900 flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md text-center space-y-3">
        <div className="inline-flex h-14 w-14 rounded-2xl bg-gradient-to-tr from-blue-600 to-indigo-500 items-center justify-center text-white shadow-xl shadow-blue-500/25">
          <ShieldCheck className="h-8 w-8" />
        </div>
        <h1 className="text-3xl font-extrabold text-white tracking-tight">BrandGuard</h1>
        <p className="text-sm text-slate-400">
          Enterprise Pre-Publication Governance & RBAC Authentication
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-white py-8 px-6 shadow-2xl rounded-2xl sm:px-10 border border-slate-100">
          {/* Tab selector */}
          <div className="flex rounded-lg bg-slate-100 p-1 mb-6">
            <button
              type="button"
              onClick={() => {
                setMode("login");
                setErrorMsg(null);
              }}
              className={`flex-1 py-2 text-xs font-semibold rounded-md transition-all ${
                mode === "login"
                  ? "bg-white text-slate-900 shadow-sm"
                  : "text-slate-500 hover:text-slate-900"
              }`}
            >
              Sign In
            </button>
            <button
              type="button"
              onClick={() => {
                setMode("register");
                setErrorMsg(null);
              }}
              className={`flex-1 py-2 text-xs font-semibold rounded-md transition-all ${
                mode === "register"
                  ? "bg-white text-slate-900 shadow-sm"
                  : "text-slate-500 hover:text-slate-900"
              }`}
            >
              Join Org
            </button>
            <button
              type="button"
              onClick={() => {
                setMode("bootstrap");
                setErrorMsg(null);
              }}
              className={`flex-1 py-2 text-xs font-semibold rounded-md transition-all ${
                mode === "bootstrap"
                  ? "bg-white text-slate-900 shadow-sm"
                  : "text-slate-500 hover:text-slate-900"
              }`}
            >
              New Tenant
            </button>
          </div>

          {/* Feedback messages */}
          {errorMsg && (
            <div className="mb-4 flex items-center gap-2 p-3 rounded-lg bg-red-50 border border-red-200 text-xs text-red-700">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>{errorMsg}</span>
            </div>
          )}

          {successMsg && (
            <div className="mb-4 flex items-center gap-2 p-3 rounded-lg bg-emerald-50 border border-emerald-200 text-xs text-emerald-700">
              <BadgeCheck className="h-4 w-4 shrink-0" />
              <span>{successMsg}</span>
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Mode: Bootstrap New Organisation */}
            {mode === "bootstrap" ? (
              <>
                <div className="p-3 bg-blue-50/60 rounded-xl border border-blue-200 text-xs text-blue-900 space-y-1">
                  <div className="flex items-center gap-1.5 font-bold">
                    <ShieldAlert className="h-4 w-4 text-blue-600" />
                    <span>One-Time Organisation Bootstrap</span>
                  </div>
                  <p className="text-[11px] text-blue-700">
                    Creates an isolated organisation and registers its initial Admin account atomically.
                  </p>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Organisation Name</label>
                  <input
                    type="text"
                    placeholder="ApexCloud Technologies"
                    value={bootstrapOrgName}
                    onChange={(e) => {
                      setBootstrapOrgName(e.target.value);
                      if (!bootstrapOrgSlug) {
                        setBootstrapOrgSlug(
                          e.target.value
                            .toLowerCase()
                            .replace(/[^a-z0-9]+/g, "-")
                            .replace(/^-+|-+$/g, "")
                        );
                      }
                    }}
                    className="block w-full text-xs px-3 py-2.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    required
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Organisation Slug (unique identifier)</label>
                  <input
                    type="text"
                    placeholder="apexcloud"
                    value={bootstrapOrgSlug}
                    onChange={(e) => setBootstrapOrgSlug(e.target.value.toLowerCase())}
                    className="block w-full text-xs px-3 py-2.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono"
                    required
                  />
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Initial Admin Full Name</label>
                  <input
                    type="text"
                    placeholder="Sarah Connor"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    className="block w-full text-xs px-3 py-2.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    required
                  />
                </div>
              </>
            ) : (
              /* Mode: Login or Join existing */
              <>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Organisation</label>
                  <div className="relative">
                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
                      <Building2 className="h-4 w-4" />
                    </div>
                    {organizations.length > 0 ? (
                      <select
                        value={orgSlugOrId}
                        onChange={(e) => setOrgSlugOrId(e.target.value)}
                        className="block w-full text-xs pl-9 pr-3 py-2.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
                      >
                        {organizations.map((org) => (
                          <option key={org.id} value={org.slug}>
                            {org.name} ({org.slug})
                          </option>
                        ))}
                      </select>
                    ) : (
                      <input
                        type="text"
                        placeholder="Enter organisation slug or UUID"
                        value={orgSlugOrId}
                        onChange={(e) => setOrgSlugOrId(e.target.value)}
                        className="block w-full text-xs pl-9 pr-3 py-2.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500"
                      />
                    )}
                  </div>
                </div>

                {mode === "register" && (
                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">Full Name</label>
                    <div className="relative">
                      <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
                        <UserIcon className="h-4 w-4" />
                      </div>
                      <input
                        type="text"
                        placeholder="Jane Doe"
                        value={fullName}
                        onChange={(e) => setFullName(e.target.value)}
                        className="block w-full text-xs pl-9 pr-3 py-2.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500"
                        required
                      />
                    </div>
                  </div>
                )}
              </>
            )}

            {/* Email Address */}
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                {mode === "bootstrap" ? "Admin Email Address" : "Email Address"}
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
                  <Mail className="h-4 w-4" />
                </div>
                <input
                  type="email"
                  placeholder="user@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="block w-full text-xs pl-9 pr-3 py-2.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  required
                />
              </div>
            </div>

            {/* Password */}
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Password{" "}
                {mode !== "login" && (
                  <span className="text-slate-400 font-normal">(min 8 chars, letters & numbers)</span>
                )}
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
                  <Lock className="h-4 w-4" />
                </div>
                <input
                  type="password"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="block w-full text-xs pl-9 pr-3 py-2.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  required
                />
              </div>
            </div>

            {/* Role Notice on Join */}
            {mode === "register" && (
              <div className="p-2.5 bg-slate-50 rounded-lg border border-slate-200 text-[11px] text-slate-600">
                <span>Account role: </span>
                <strong className="text-slate-900">Content Creator</strong>
                <p className="text-[10px] text-slate-500 mt-0.5">
                  Privileged roles (Admin, Brand Manager, Legal, Reviewer) require assignment by your organisation Admin.
                </p>
              </div>
            )}

            {/* Submit Button */}
            <button
              type="submit"
              disabled={submitting}
              className="w-full mt-2 flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold shadow-md shadow-blue-500/20 transition-all disabled:opacity-70"
            >
              {submitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span>Processing...</span>
                </>
              ) : (
                <>
                  <span>
                    {mode === "bootstrap"
                      ? "Bootstrap Organisation & Admin"
                      : mode === "login"
                      ? "Sign In to BrandGuard"
                      : "Create Creator Account"}
                  </span>
                  <ArrowRight className="h-3.5 w-3.5" />
                </>
              )}
            </button>
          </form>

          {/* Security footnote */}
          <div className="mt-6 pt-4 border-t border-slate-100 text-center">
            <p className="text-[11px] text-slate-400">
              Argon2id Hashing • Server-Side Revocation • Strict RBAC & Tenant Isolation
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
