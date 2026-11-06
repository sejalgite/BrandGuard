"use client";

import React, { useState, useEffect } from "react";
import {
  BarChart3,
  CheckCircle2,
  AlertTriangle,
  Lightbulb,
  Play,
  RotateCcw,
  ShieldCheck,
  Target,
  Scale,
  Sparkles,
  Info,
  Database,
  Search,
  ExternalLink,
  Lock
} from "lucide-react";
import {
  getQualityDashboard,
  getRuleClarityAnalytics,
  getGuidelineRecommendations,
  seedBenchmarkDataset,
  triggerEvaluationRun,
  listEvaluationDatasets,
  QualityDashboardData,
  RulePerformanceItem,
  RecommendationItem,
  EvaluationDatasetItem,
  EvaluationRunItem,
  CategoryMetricDetailItem
} from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function EvaluationDashboardPage() {
  const { user } = useAuth();
  const [dashboardData, setDashboardData] = useState<QualityDashboardData | null>(null);
  const [rulesAnalytics, setRulesAnalytics] = useState<RulePerformanceItem[]>([]);
  const [recommendations, setRecommendations] = useState<RecommendationItem[]>([]);
  const [datasets, setDatasets] = useState<EvaluationDatasetItem[]>([]);
  const [activeTab, setActiveTab] = useState<"categories" | "clarity" | "recommendations" | "runs">("categories");

  const [loading, setLoading] = useState<boolean>(true);
  const [evaluating, setEvaluating] = useState<boolean>(false);
  const [seeding, setSeeding] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [dash, clarity, recs, dsets] = await Promise.all([
        getQualityDashboard().catch(() => null),
        getRuleClarityAnalytics().catch(() => ({ total_rules_analyzed: 0, rules: [] })),
        getGuidelineRecommendations().catch(() => ({ total_recommendations: 0, recommendations: [] })),
        listEvaluationDatasets().catch(() => [])
      ]);
      if (dash) setDashboardData(dash);
      setRulesAnalytics(clarity.rules || []);
      setRecommendations(recs.recommendations || []);
      setDatasets(dsets || []);
    } catch (err: any) {
      setError(err?.response?.data?.error?.message || err?.message || "Failed to load evaluation data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    if (typeof window !== "undefined" && window.location.hash === "#clarity") {
      setActiveTab("clarity");
    }
  }, []);

  const handleSeedDataset = async () => {
    setSeeding(true);
    setError(null);
    setSuccessMsg(null);
    try {
      await seedBenchmarkDataset();
      setSuccessMsg("ApexCloud Gold Benchmark Dataset successfully seeded.");
      await fetchData();
    } catch (err: any) {
      setError(err?.response?.data?.error?.message || err?.message || "Failed to seed benchmark dataset");
    } finally {
      setSeeding(false);
    }
  };

  const handleRunEvaluation = async () => {
    if (!datasets || datasets.length === 0) {
      setError("Please seed the benchmark dataset first.");
      return;
    }
    const targetDataset = datasets[0];
    setEvaluating(true);
    setError(null);
    setSuccessMsg(null);
    try {
      const run = await triggerEvaluationRun(targetDataset.id, "BENCHMARK");
      setSuccessMsg(`Evaluation Run #${run.id.slice(0, 8)} executed! F1-Score: ${(run.overall_f1 * 100).toFixed(1)}%`);
      await fetchData();
    } catch (err: any) {
      setError(err?.response?.data?.error?.message || err?.message || "Failed to run evaluation engine");
    } finally {
      setEvaluating(false);
    }
  };

  const latestRun = dashboardData?.latest_run;
  const categories = latestRun?.category_metrics
    ? Object.entries(latestRun.category_metrics)
    : dashboardData?.category_performance
    ? Object.entries(dashboardData.category_performance)
    : [];

  return (
    <div className="space-y-8 p-6 max-w-7xl mx-auto">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b border-slate-200 pb-5">
        <div>
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-lg bg-indigo-50 border border-indigo-200 flex items-center justify-center text-indigo-600">
              <BarChart3 className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-slate-900">
                Evaluation, Reliability & Intelligence
              </h1>
              <p className="text-sm text-slate-500">
                Independent precision & recall benchmark, quality verification audit, and rule friction analytics.
              </p>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={fetchData}
            disabled={loading}
            className="inline-flex items-center gap-2 px-3.5 py-2 text-sm font-medium text-slate-700 bg-white border border-slate-300 rounded-md hover:bg-slate-50 transition shadow-sm disabled:opacity-50"
          >
            <RotateCcw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </button>

          <button
            onClick={handleSeedDataset}
            disabled={seeding || loading}
            className="inline-flex items-center gap-2 px-3.5 py-2 text-sm font-medium text-indigo-700 bg-indigo-50 border border-indigo-200 rounded-md hover:bg-indigo-100 transition shadow-sm disabled:opacity-50"
          >
            <Database className="h-4 w-4" />
            {seeding ? "Seeding..." : "Seed Benchmark"}
          </button>

          <button
            onClick={handleRunEvaluation}
            disabled={evaluating || loading}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 rounded-md transition shadow-sm disabled:opacity-50"
          >
            <Play className={`h-4 w-4 ${evaluating ? "animate-spin" : ""}`} />
            {evaluating ? "Evaluating Engine..." : "Run Benchmark"}
          </button>
        </div>
      </div>

      {/* Notifications */}
      {error && (
        <div className="rounded-md bg-red-50 border border-red-200 p-4 flex items-start gap-3">
          <AlertTriangle className="h-5 w-5 text-red-600 mt-0.5" />
          <div className="text-sm text-red-700">{error}</div>
        </div>
      )}

      {successMsg && (
        <div className="rounded-md bg-emerald-50 border border-emerald-200 p-4 flex items-start gap-3">
          <CheckCircle2 className="h-5 w-5 text-emerald-600 mt-0.5" />
          <div className="text-sm text-emerald-800">{successMsg}</div>
        </div>
      )}

      {/* Top Level Metric KPIs */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Overall Precision</span>
            <Target className="h-4 w-4 text-indigo-600" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-3xl font-extrabold text-slate-900">
              {latestRun ? `${(latestRun.overall_precision * 100).toFixed(1)}%` : "0.0%"}
            </span>
          </div>
          <p className="mt-1 text-xs text-slate-500">Accuracy of flagged snippets</p>
        </div>

        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Overall Recall</span>
            <Scale className="h-4 w-4 text-emerald-600" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-3xl font-extrabold text-slate-900">
              {latestRun ? `${(latestRun.overall_recall * 100).toFixed(1)}%` : "0.0%"}
            </span>
          </div>
          <p className="mt-1 text-xs text-slate-500">Ground-truth violation coverage</p>
        </div>

        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">F1-Score</span>
            <Sparkles className="h-4 w-4 text-purple-600" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-3xl font-extrabold text-slate-900">
              {latestRun ? `${(latestRun.overall_f1 * 100).toFixed(1)}%` : "0.0%"}
            </span>
          </div>
          <p className="mt-1 text-xs text-slate-500">Harmonic mean balance</p>
        </div>

        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Quality Gate</span>
            <ShieldCheck className="h-4 w-4 text-emerald-600" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-3xl font-extrabold text-emerald-600">
              {dashboardData ? `${(dashboardData.finding_quality_verification_rate * 100).toFixed(1)}%` : "100.0%"}
            </span>
          </div>
          <p className="mt-1 text-xs text-slate-500">No citation, no flag enforcement</p>
        </div>

        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Test Cases</span>
            <Info className="h-4 w-4 text-slate-500" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-3xl font-extrabold text-slate-900">
              {latestRun ? `${latestRun.passed_cases}/${latestRun.total_cases}` : "0/0"}
            </span>
          </div>
          <p className="mt-1 text-xs text-slate-500">
            {latestRun ? `${(latestRun.overall_accuracy * 100).toFixed(1)}% Accuracy` : "Benchmark suite"}
          </p>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="border-b border-slate-200">
        <nav className="flex space-x-8" aria-label="Tabs">
          <button
            onClick={() => setActiveTab("categories")}
            className={`py-4 px-1 inline-flex items-center gap-2 border-b-2 font-medium text-sm transition ${
              activeTab === "categories"
                ? "border-indigo-600 text-indigo-600"
                : "border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300"
            }`}
          >
            <BarChart3 className="h-4 w-4" />
            Category Performance Matrix
          </button>

          <button
            onClick={() => setActiveTab("clarity")}
            className={`py-4 px-1 inline-flex items-center gap-2 border-b-2 font-medium text-sm transition ${
              activeTab === "clarity"
                ? "border-indigo-600 text-indigo-600"
                : "border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300"
            }`}
          >
            <Lightbulb className="h-4 w-4" />
            Guideline Clarity & Review Friction
            <span className="ml-1.5 py-0.5 px-2 rounded-full text-xs bg-slate-100 text-slate-600">
              {rulesAnalytics.length}
            </span>
          </button>

          <button
            onClick={() => setActiveTab("recommendations")}
            className={`py-4 px-1 inline-flex items-center gap-2 border-b-2 font-medium text-sm transition ${
              activeTab === "recommendations"
                ? "border-indigo-600 text-indigo-600"
                : "border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300"
            }`}
          >
            <CheckCircle2 className="h-4 w-4" />
            Governance Recommendations
            <span className="ml-1.5 py-0.5 px-2 rounded-full text-xs bg-indigo-100 text-indigo-700">
              {recommendations.length}
            </span>
          </button>

          <button
            onClick={() => setActiveTab("runs")}
            className={`py-4 px-1 inline-flex items-center gap-2 border-b-2 font-medium text-sm transition ${
              activeTab === "runs"
                ? "border-indigo-600 text-indigo-600"
                : "border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300"
            }`}
          >
            <RotateCcw className="h-4 w-4" />
            Evaluation History
          </button>
        </nav>
      </div>

      {/* Tab 1: Category Performance Matrix */}
      {activeTab === "categories" && (
        <div className="space-y-6">
          <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm">
            <div className="p-5 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
              <div>
                <h3 className="text-base font-semibold text-slate-900">Category-Specific Detection Metrics</h3>
                <p className="text-sm text-slate-500">
                  Precision, Recall, F1 and Coverage calculated across all six compliance categories.
                </p>
              </div>
              {latestRun && (
                <span className="text-xs text-slate-500">
                  Engine Version: <span className="font-mono text-slate-700">{latestRun.engine_version}</span>
                </span>
              )}
            </div>

            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead className="bg-slate-50 text-slate-600 uppercase text-xs font-semibold">
                  <tr>
                    <th scope="col" className="px-6 py-3.5 text-left">Category</th>
                    <th scope="col" className="px-4 py-3.5 text-center">TP</th>
                    <th scope="col" className="px-4 py-3.5 text-center">FP</th>
                    <th scope="col" className="px-4 py-3.5 text-center">FN</th>
                    <th scope="col" className="px-6 py-3.5 text-left">Precision</th>
                    <th scope="col" className="px-6 py-3.5 text-left">Recall</th>
                    <th scope="col" className="px-6 py-3.5 text-left">F1-Score</th>
                    <th scope="col" className="px-6 py-3.5 text-center">Coverage</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 bg-white">
                  {categories.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="px-6 py-12 text-center text-slate-500">
                        No evaluation metrics available. Click &quot;Run Benchmark&quot; to execute evaluation.
                      </td>
                    </tr>
                  ) : (
                    categories.map(([cat, m]: [string, CategoryMetricDetailItem]) => (
                      <tr key={cat} className="hover:bg-slate-50 transition">
                        <td className="px-6 py-4 font-semibold text-slate-900 flex items-center gap-2">
                          <span className="w-2.5 h-2.5 rounded-full bg-indigo-500" />
                          {cat}
                        </td>
                        <td className="px-4 py-4 text-center text-slate-700 font-mono">{m.tp}</td>
                        <td className="px-4 py-4 text-center text-slate-700 font-mono">{m.fp}</td>
                        <td className="px-4 py-4 text-center text-slate-700 font-mono">{m.fn}</td>
                        <td className="px-6 py-4">
                          <div className="flex items-center gap-2">
                            <div className="w-24 bg-slate-200 rounded-full h-2 overflow-hidden">
                              <div
                                className="bg-indigo-600 h-2 rounded-full"
                                style={{ width: `${Math.min(100, m.precision * 100)}%` }}
                              />
                            </div>
                            <span className="font-medium text-slate-800">{(m.precision * 100).toFixed(1)}%</span>
                          </div>
                        </td>
                        <td className="px-6 py-4">
                          <div className="flex items-center gap-2">
                            <div className="w-24 bg-slate-200 rounded-full h-2 overflow-hidden">
                              <div
                                className="bg-emerald-500 h-2 rounded-full"
                                style={{ width: `${Math.min(100, m.recall * 100)}%` }}
                              />
                            </div>
                            <span className="font-medium text-slate-800">{(m.recall * 100).toFixed(1)}%</span>
                          </div>
                        </td>
                        <td className="px-6 py-4 font-bold text-slate-900">
                          {(m.f1 * 100).toFixed(1)}%
                        </td>
                        <td className="px-6 py-4 text-center">
                          <span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${
                            m.coverage >= 1.0 ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"
                          }`}>
                            {(m.coverage * 100).toFixed(1)}%
                          </span>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: Guideline Clarity & Review Friction */}
      {activeTab === "clarity" && (
        <div className="space-y-6">
          <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm">
            <div className="p-5 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
              <div>
                <h3 className="text-base font-semibold text-slate-900">Brand Rule Ambiguity & Review Friction</h3>
                <p className="text-sm text-slate-500">
                  Calculates subjective wording ambiguity and reviewer dispute frequencies.
                </p>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead className="bg-slate-50 text-slate-600 uppercase text-xs font-semibold">
                  <tr>
                    <th scope="col" className="px-6 py-3.5 text-left">Rule Code & Title</th>
                    <th scope="col" className="px-4 py-3.5 text-left">Category</th>
                    <th scope="col" className="px-4 py-3.5 text-center">Ambiguity Score</th>
                    <th scope="col" className="px-6 py-3.5 text-left">Subjective Terms</th>
                    <th scope="col" className="px-4 py-3.5 text-center">Findings</th>
                    <th scope="col" className="px-4 py-3.5 text-center">Disputes</th>
                    <th scope="col" className="px-4 py-3.5 text-center">Dispute Rate</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 bg-white">
                  {rulesAnalytics.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="px-6 py-12 text-center text-slate-500">
                        No rule analytics available.
                      </td>
                    </tr>
                  ) : (
                    rulesAnalytics.map((r) => (
                      <tr key={r.rule_id} className="hover:bg-slate-50 transition">
                        <td className="px-6 py-4">
                          <div className="font-semibold text-slate-900">{r.title}</div>
                          <div className="text-xs font-mono text-slate-500">{r.rule_code}</div>
                        </td>
                        <td className="px-4 py-4 text-xs font-medium text-slate-600">
                          <span className="px-2 py-0.5 bg-slate-100 rounded text-slate-700">
                            {r.category}
                          </span>
                        </td>
                        <td className="px-4 py-4 text-center font-mono">
                          <span className={`px-2 py-0.5 rounded text-xs font-semibold ${
                            r.ambiguity_score > 0.3 ? "bg-amber-100 text-amber-800" : "bg-emerald-100 text-emerald-800"
                          }`}>
                            {r.ambiguity_score.toFixed(2)}
                          </span>
                        </td>
                        <td className="px-6 py-4">
                          {r.subjective_terms.length > 0 ? (
                            <div className="flex flex-wrap gap-1">
                              {r.subjective_terms.map((t) => (
                                <span key={t} className="px-1.5 py-0.5 bg-red-50 text-red-700 border border-red-200 rounded text-xs">
                                  {t}
                                </span>
                              ))}
                            </div>
                          ) : (
                            <span className="text-xs text-slate-400">None detected</span>
                          )}
                        </td>
                        <td className="px-4 py-4 text-center text-slate-700 font-mono">
                          {r.total_findings_generated}
                        </td>
                        <td className="px-4 py-4 text-center text-slate-700 font-mono">
                          {r.total_disputes}
                        </td>
                        <td className="px-4 py-4 text-center font-mono font-medium text-slate-800">
                          {(r.dispute_rate * 100).toFixed(1)}%
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Tab 3: Governance Recommendations */}
      {activeTab === "recommendations" && (
        <div className="space-y-4">
          <div className="p-4 bg-indigo-50 border border-indigo-200 rounded-xl flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Lock className="h-5 w-5 text-indigo-700" />
              <div>
                <h4 className="text-sm font-semibold text-indigo-950">Strict Human-in-the-Loop Governance</h4>
                <p className="text-xs text-indigo-700">
                  Recommendations never automatically alter active Constitution rules. Each action requires Brand Manager authorization.
                </p>
              </div>
            </div>
          </div>

          {recommendations.length === 0 ? (
            <div className="bg-white p-12 text-center rounded-xl border border-slate-200 text-slate-500">
              <CheckCircle2 className="h-10 w-10 text-emerald-500 mx-auto mb-3" />
              <h4 className="text-base font-semibold text-slate-800">All Guidelines Well-Formed</h4>
              <p className="text-sm text-slate-500 mt-1">
                No rule conflicts, excessive dispute rates, or ambiguous phrasing recommendations at this time.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {recommendations.map((rec) => (
                <div key={rec.id} className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex flex-col justify-between">
                  <div>
                    <div className="flex items-center justify-between gap-2">
                      <span className="px-2 py-0.5 rounded text-xs font-semibold bg-amber-100 text-amber-800">
                        {rec.type}
                      </span>
                      <span className="text-xs px-2 py-0.5 rounded bg-slate-100 text-slate-600 font-medium">
                        Requires Approval
                      </span>
                    </div>

                    <h4 className="text-base font-bold text-slate-900 mt-2">{rec.title}</h4>
                    <p className="text-sm text-slate-600 mt-1">{rec.description}</p>

                    <div className="mt-4 p-3 bg-slate-50 rounded-lg border border-slate-200">
                      <span className="text-xs font-semibold text-slate-700 uppercase">Proposed Action:</span>
                      <p className="text-xs text-slate-800 mt-0.5 font-medium">{rec.proposed_action}</p>
                    </div>

                    <div className="mt-2 text-xs text-slate-500">
                      <span className="font-semibold">Reason:</span> {rec.reason}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Tab 4: Historical Runs */}
      {activeTab === "runs" && (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-sm">
          <div className="p-5 border-b border-slate-200 bg-slate-50">
            <h3 className="text-base font-semibold text-slate-900">Evaluation Execution History</h3>
            <p className="text-sm text-slate-500">Audit trail of automated and benchmark evaluation runs.</p>
          </div>

          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50 text-slate-600 uppercase text-xs font-semibold">
                <tr>
                  <th scope="col" className="px-6 py-3.5 text-left">Run ID</th>
                  <th scope="col" className="px-4 py-3.5 text-left">Type</th>
                  <th scope="col" className="px-4 py-3.5 text-left">Engine Version</th>
                  <th scope="col" className="px-4 py-3.5 text-center">F1-Score</th>
                  <th scope="col" className="px-4 py-3.5 text-center">Accuracy</th>
                  <th scope="col" className="px-4 py-3.5 text-center">Cases Passed</th>
                  <th scope="col" className="px-6 py-3.5 text-right">Executed At</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 bg-white">
                {!dashboardData?.historical_runs || dashboardData.historical_runs.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-6 py-12 text-center text-slate-500">
                      No historical evaluation runs recorded.
                    </td>
                  </tr>
                ) : (
                  dashboardData.historical_runs.map((hr) => (
                    <tr key={hr.id} className="hover:bg-slate-50 transition">
                      <td className="px-6 py-4 font-mono text-xs text-indigo-600 font-semibold">
                        {hr.id.slice(0, 8)}...
                      </td>
                      <td className="px-4 py-4 text-xs font-medium text-slate-700">
                        {hr.run_type}
                      </td>
                      <td className="px-4 py-4 font-mono text-xs text-slate-600">
                        {hr.engine_version}
                      </td>
                      <td className="px-4 py-4 text-center font-bold text-slate-900">
                        {(hr.overall_f1 * 100).toFixed(1)}%
                      </td>
                      <td className="px-4 py-4 text-center font-medium text-slate-800">
                        {(hr.overall_accuracy * 100).toFixed(1)}%
                      </td>
                      <td className="px-4 py-4 text-center text-slate-700 font-mono">
                        {hr.passed_cases}/{hr.total_cases}
                      </td>
                      <td className="px-6 py-4 text-right text-xs text-slate-500">
                        {new Date(hr.created_at).toLocaleString()}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
