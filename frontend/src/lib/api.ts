import axios from "axios";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
  withCredentials: true, // Sends and receives HttpOnly cookies
  timeout: 10000,
});

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp("(^|;\\s*)(" + name + ")=([^;]*)"));
  return match ? decodeURIComponent(match[3]) : null;
}

// Automatic JWT and CSRF attachment interceptor
apiClient.interceptors.request.use(
  (config) => {
    if (typeof window !== "undefined") {
      const token = localStorage.getItem("brandguard_token");
      if (token && config.headers) {
        config.headers.Authorization = `Bearer ${token}`;
      }
      const csrfToken = getCookie("csrf_token");
      if (csrfToken && config.headers) {
        config.headers["X-CSRF-Token"] = csrfToken;
      }
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface SystemHealth {
  status: string;
  environment: string;
  version: string;
  database: {
    connected: boolean;
    pgvector: boolean;
    version?: string;
    pgvector_version?: string;
  };
  ai_status: {
    gemini_configured: boolean;
    ollama_endpoint: string;
    mode: string;
  };
}

export type UserRole =
  | "ADMIN"
  | "CONTENT_CREATOR"
  | "EXTERNAL_AGENCY"
  | "REVIEWER"
  | "BRAND_MANAGER"
  | "LEGAL_REVIEWER"
  | "LEADERSHIP";

export interface UserProfile {
  id: string;
  organization_id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  permissions?: string[];
}

export interface OrganizationInfo {
  id: string;
  name: string;
  slug: string;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: UserProfile;
}

export interface AuditLogItem {
  id: string;
  organization_id: string;
  actor_id?: string;
  action: string;
  target_entity: string;
  target_id: string;
  version_number?: number;
  details?: Record<string, unknown>;
  timestamp: string;
}

export type RuleCategory =
  | "TONE_VOICE"
  | "WRITING_STYLE"
  | "MESSAGING_PILLAR"
  | "VISUAL"
  | "ACCESSIBILITY";

export type EntityStatus =
  | "DRAFT"
  | "PENDING_APPROVAL"
  | "ACTIVE"
  | "REJECTED"
  | "ARCHIVED"
  | "EXPIRED";

export interface BrandRule {
  id: string;
  organization_id: string;
  constitution_id: string;
  rule_code: string;
  category: RuleCategory;
  title: string;
  description: string;
  examples_positive?: string[];
  examples_negative?: string[];
  status: EntityStatus;
  approved_by?: string;
  created_at: string;
}

export interface FactRegistryItem {
  id: string;
  organization_id: string;
  constitution_id: string;
  fact_code: string;
  claim_type: string;
  statement: string;
  numerical_value?: number;
  unit?: string;
  source_reference: string;
  fact_owner: string;
  expiry_date: string;
  is_expired: boolean;
  status: EntityStatus;
  approved_by?: string;
  created_at: string;
}

export interface FactConflict {
  claim_type: string;
  conflicting_facts: FactRegistryItem[];
  conflict_reason: string;
}

export interface TermBankItem {
  id: string;
  organization_id: string;
  constitution_id: string;
  term_code: string;
  prohibited_term: string;
  preferred_term: string;
  usage_context?: string;
  is_case_sensitive: boolean;
  status: EntityStatus;
  created_at: string;
}

export interface BrandAssetItem {
  id: string;
  organization_id: string;
  constitution_id: string;
  asset_code: string;
  asset_type: string;
  name: string;
  specifications: Record<string, any>;
  file_path?: string;
  status: EntityStatus;
  created_at: string;
}

export interface ConstitutionOverview {
  constitution_id: string;
  title: string;
  version: string;
  total_rules: number;
  approved_rules: number;
  pending_rules: number;
  total_facts: number;
  approved_facts: number;
  expired_facts: number;
  total_terms: number;
  prohibited_terms: number;
  total_assets: number;
  pending_approvals: number;
}

// ---------------------------------------------------------------------------
// Auth API
// ---------------------------------------------------------------------------

export async function fetchHealth(): Promise<SystemHealth> {
  const response = await apiClient.get<SystemHealth>("/health");
  return response.data;
}

export async function listOrganizations(): Promise<OrganizationInfo[]> {
  const response = await apiClient.get<OrganizationInfo[]>("/auth/organizations");
  return response.data;
}

export async function apiBootstrapOrganization(payload: {
  org_name: string;
  org_slug: string;
  admin_email: string;
  admin_password: string;
  admin_full_name: string;
}): Promise<AuthResponse> {
  const response = await apiClient.post<AuthResponse>("/auth/bootstrap", payload);
  return response.data;
}

export async function apiLogin(payload: {
  email: string;
  password: string;
  organization_slug?: string;
  organization_id?: string;
}): Promise<AuthResponse> {
  const response = await apiClient.post<AuthResponse>("/auth/login", payload);
  return response.data;
}

export async function apiRegister(payload: {
  email: string;
  password: string;
  full_name: string;
  role?: UserRole;
  organization_slug?: string;
  organization_id?: string;
}): Promise<UserProfile> {
  const response = await apiClient.post<UserProfile>("/auth/register", payload);
  return response.data;
}

export async function apiGetMe(): Promise<UserProfile> {
  const response = await apiClient.get<UserProfile>("/auth/me");
  return response.data;
}

export async function apiLogout(): Promise<{ message: string }> {
  const response = await apiClient.post<{ message: string }>("/auth/logout");
  return response.data;
}

export async function apiListAuditLogs(limit: number = 20): Promise<AuditLogItem[]> {
  const response = await apiClient.get<AuditLogItem[]>(`/audit/logs?limit=${limit}`);
  return response.data;
}

// ---------------------------------------------------------------------------
// Constitution API
// ---------------------------------------------------------------------------

export async function fetchConstitutionOverview(): Promise<ConstitutionOverview> {
  const response = await apiClient.get<ConstitutionOverview>("/constitution/overview");
  return response.data;
}

export async function seedDemoConstitution(): Promise<{ message: string }> {
  const response = await apiClient.post<{ message: string }>("/constitution/seed-demo");
  return response.data;
}

export async function listBrandRules(params?: {
  category?: string;
  status_filter?: string;
  search?: string;
}): Promise<BrandRule[]> {
  const response = await apiClient.get<BrandRule[]>("/constitution/rules", { params });
  return response.data;
}

export async function createBrandRule(payload: {
  rule_code: string;
  category: RuleCategory;
  title: string;
  description: string;
  examples_positive?: string[];
  examples_negative?: string[];
  status?: EntityStatus;
}): Promise<BrandRule> {
  const response = await apiClient.post<BrandRule>("/constitution/rules", payload);
  return response.data;
}

export async function submitBrandRule(id: string): Promise<BrandRule> {
  const response = await apiClient.post<BrandRule>(`/constitution/rules/${id}/submit`);
  return response.data;
}

export async function approveBrandRule(id: string): Promise<BrandRule> {
  const response = await apiClient.post<BrandRule>(`/constitution/rules/${id}/approve`);
  return response.data;
}

export async function rejectBrandRule(id: string): Promise<BrandRule> {
  const response = await apiClient.post<BrandRule>(`/constitution/rules/${id}/reject`);
  return response.data;
}

export async function listFacts(params?: {
  claim_type?: string;
  status_filter?: string;
  search?: string;
}): Promise<FactRegistryItem[]> {
  const response = await apiClient.get<FactRegistryItem[]>("/constitution/facts", { params });
  return response.data;
}

export async function createFact(payload: {
  fact_code: string;
  claim_type: string;
  statement: string;
  numerical_value?: number;
  unit?: string;
  source_reference: string;
  fact_owner: string;
  expiry_date: string;
  status?: EntityStatus;
}): Promise<FactRegistryItem> {
  const response = await apiClient.post<FactRegistryItem>("/constitution/facts", payload);
  return response.data;
}

export async function approveFact(id: string): Promise<FactRegistryItem> {
  const response = await apiClient.post<FactRegistryItem>(`/constitution/facts/${id}/approve`);
  return response.data;
}

export async function detectFactConflicts(): Promise<FactConflict[]> {
  const response = await apiClient.get<FactConflict[]>("/constitution/facts/conflicts/detect");
  return response.data;
}

export async function listTerms(params?: {
  search?: string;
  status_filter?: string;
}): Promise<TermBankItem[]> {
  const response = await apiClient.get<TermBankItem[]>("/constitution/terms", { params });
  return response.data;
}

export async function createTerm(payload: {
  term_code: string;
  prohibited_term: string;
  preferred_term: string;
  usage_context?: string;
  is_case_sensitive?: boolean;
  status?: EntityStatus;
}): Promise<TermBankItem> {
  const response = await apiClient.post<TermBankItem>("/constitution/terms", payload);
  return response.data;
}

export async function listAssets(asset_type?: string): Promise<BrandAssetItem[]> {
  const response = await apiClient.get<BrandAssetItem[]>("/constitution/assets", {
    params: asset_type ? { asset_type } : {},
  });
  return response.data;
}

export async function createAsset(payload: {
  asset_code: string;
  asset_type: string;
  name: string;
  specifications: Record<string, any>;
  status?: EntityStatus;
}): Promise<BrandAssetItem> {
  const response = await apiClient.post<BrandAssetItem>("/constitution/assets", payload);
  return response.data;
}

export async function uploadAssetFile(formData: FormData): Promise<BrandAssetItem> {
  const response = await apiClient.post<BrandAssetItem>("/constitution/assets/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
}

// ---------------------------------------------------------------------------
// Document Ingestion & Extraction API (Phase 4)
// ---------------------------------------------------------------------------

export interface TextSegment {
  segment_id: string;
  page_number: number;
  paragraph_index: number;
  sentence_index: number;
  text: string;
  char_start: number;
  char_end: number;
  heading_context?: string;
}

export interface StructuredContent {
  title?: string;
  total_segments: number;
  total_paragraphs: number;
  total_pages: number;
  headings: Array<{ text: string; level: number; page: number }>;
  paragraphs: Array<{
    paragraph_index: number;
    page_number: number;
    text: string;
    heading_context?: string;
    char_start: number;
    char_end: number;
  }>;
  segments: TextSegment[];
  word_count: number;
  character_count: number;
}

export interface DocumentVersionItem {
  id: string;
  organization_id: string;
  document_id: string;
  version_number: number;
  original_filename?: string;
  file_size_bytes?: number;
  mime_type?: string;
  extraction_status: "COMPLETED" | "EMPTY" | "FAILED" | "OCR_UNAVAILABLE" | "PENDING";
  extracted_text?: string;
  word_count: number;
  character_count: number;
  brand_health_score?: number;
  version_status: string;
  is_locked: boolean;
  created_at: string;
  extraction_metadata?: Record<string, any>;
  structured_content?: StructuredContent;
}

export interface DocumentItem {
  id: string;
  organization_id: string;
  creator_id: string;
  title: string;
  content_type: "TEXT" | "DOCX" | "PDF" | "IMAGE";
  lifecycle_status: string;
  created_at: string;
  updated_at: string;
  latest_version?: DocumentVersionItem;
  versions_count: number;
}

export interface DocumentUploadResponse {
  document: DocumentItem;
  version: DocumentVersionItem;
  message: string;
}

export async function listDocuments(params?: {
  content_type?: string;
  search?: string;
}): Promise<DocumentItem[]> {
  const response = await apiClient.get<DocumentItem[]>("/documents", { params });
  return response.data;
}

export async function getDocumentDetails(document_id: string): Promise<DocumentItem> {
  const response = await apiClient.get<DocumentItem>(`/documents/${document_id}`);
  return response.data;
}

export async function listDocumentVersions(document_id: string): Promise<DocumentVersionItem[]> {
  const response = await apiClient.get<DocumentVersionItem[]>(`/documents/${document_id}/versions`);
  return response.data;
}

export async function getVersionDetails(
  document_id: string,
  version_id: string
): Promise<DocumentVersionItem> {
  const response = await apiClient.get<DocumentVersionItem>(
    `/documents/${document_id}/versions/${version_id}`
  );
  return response.data;
}

export async function uploadDocument(formData: FormData): Promise<DocumentUploadResponse> {
  const response = await apiClient.post<DocumentUploadResponse>("/documents/upload", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
}

export async function uploadNewVersion(
  document_id: string,
  formData: FormData
): Promise<DocumentUploadResponse> {
  const response = await apiClient.post<DocumentUploadResponse>(
    `/documents/${document_id}/versions`,
    formData,
    {
      headers: { "Content-Type": "multipart/form-data" },
    }
  );
  return response.data;
}

export async function retryExtraction(
  document_id: string,
  version_id: string
): Promise<DocumentVersionItem> {
  const response = await apiClient.post<DocumentVersionItem>(
    `/documents/${document_id}/versions/${version_id}/retry`
  );
  return response.data;
}

export async function deleteDocument(document_id: string): Promise<{ message: string }> {
  const response = await apiClient.delete<{ message: string }>(`/documents/${document_id}`);
  return response.data;
}

export async function downloadDocumentFile(
  document_id: string,
  version_id: string,
  filename: string
): Promise<void> {
  const response = await apiClient.get(
    `/documents/${document_id}/versions/${version_id}/download`,
    {
      responseType: "blob",
    }
  );
  const blob = new Blob([response.data]);
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename || "document.bin";
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// Brand Analysis Engine API (Phase 5)
// ---------------------------------------------------------------------------

export interface AnalysisRunItem {
  id: string;
  organization_id: string;
  document_id: string;
  version_id: string;
  status: "RUNNING" | "COMPLETED" | "FAILED";
  trigger_type: string;
  total_findings: number;
  categories_analyzed: string[];
  execution_metadata: Record<string, any>;
  started_at: string;
  completed_at?: string;
  error_message?: string;
}

export interface FindingItem {
  id: string;
  organization_id: string;
  document_id: string;
  version_id: string;
  job_id: string;
  category: "TONE" | "TERMINOLOGY" | "MESSAGING" | "VISUAL" | "ACCESSIBILITY" | "CLAIMS";
  severity: "INFO" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  confidence: number;
  flagged_snippet: string;
  char_offset_start?: number;
  char_offset_end?: number;
  explanation: string;
  evidence_type: "RULE" | "FACT" | "TERM" | "ASSET";
  cited_code: string;
  rule_id?: string;
  fact_id?: string;
  term_id?: string;
  asset_id?: string;
  source: "DETERMINISTIC_ENGINE" | "LIVE_LLM";
  status: "OPEN" | "ACCEPTED" | "EDITED" | "DISPUTED" | "DISMISSED" | "NEEDS_REVIEW";
  segment_id?: string;
  suggested_correction?: string;
  created_at: string;
  evidence_reference?: {
    type?: string;
    title?: string;
    rule_code?: string;
    category?: string;
    statement?: string;
    fact_code?: string;
    source?: string;
    expiry?: string;
    prohibited?: string;
    preferred?: string;
    context?: string;
    name?: string;
    asset_code?: string;
    specs?: Record<string, any>;
  };
}

export interface DocumentAnalysisSummaryItem {
  document_id: string;
  latest_run?: AnalysisRunItem;
  brand_health_score?: number;
  findings_count_by_severity: Record<string, number>;
  findings_count_by_category: Record<string, number>;
  total_findings: number;
}

export async function startDocumentAnalysis(
  document_id: string,
  version_id?: string
): Promise<AnalysisRunItem> {
  const response = await apiClient.post<AnalysisRunItem>(
    `/analysis/documents/${document_id}/run`,
    { version_id }
  );
  return response.data;
}

export async function listDocumentAnalysisRuns(
  document_id: string
): Promise<AnalysisRunItem[]> {
  const response = await apiClient.get<AnalysisRunItem[]>(
    `/analysis/documents/${document_id}/runs`
  );
  return response.data;
}

export async function getAnalysisRun(job_id: string): Promise<AnalysisRunItem> {
  const response = await apiClient.get<AnalysisRunItem>(`/analysis/runs/${job_id}`);
  return response.data;
}

export async function getRunFindings(
  job_id: string,
  filters?: { category?: string; severity?: string; status?: string }
): Promise<FindingItem[]> {
  const response = await apiClient.get<FindingItem[]>(
    `/analysis/runs/${job_id}/findings`,
    { params: filters }
  );
  return response.data;
}

export async function getSingleFinding(finding_id: string): Promise<FindingItem> {
  const response = await apiClient.get<FindingItem>(`/analysis/findings/${finding_id}`);
  return response.data;
}

export async function updateFindingStatus(
  finding_id: string,
  status: string,
  justification?: string
): Promise<FindingItem> {
  const response = await apiClient.patch<FindingItem>(
    `/analysis/findings/${finding_id}/status`,
    { status, justification }
  );
  return response.data;
}

export async function getDocumentAnalysisSummary(
  document_id: string
): Promise<DocumentAnalysisSummaryItem> {
  const response = await apiClient.get<DocumentAnalysisSummaryItem>(
    `/analysis/documents/${document_id}/summary`
  );
  return response.data;
}

// ---------------------------------------------------------------------------
// Phase 6: Human Review, Approval & Governance Types & APIs
// ---------------------------------------------------------------------------

export type ReviewWorkflowStatus =
  | "DRAFT"
  | "SUBMITTED"
  | "UNDER_REVIEW"
  | "CHANGES_REQUESTED"
  | "RESUBMITTED"
  | "PENDING_BRAND_APPROVAL"
  | "PENDING_LEGAL_APPROVAL"
  | "APPROVED"
  | "REJECTED"
  | "WITHDRAWN";

export type FindingDecisionType = "ACCEPTED" | "DISMISSED" | "DISPUTED" | "RESOLVED";

export interface ReviewHistoryItem {
  id: string;
  review_id: string;
  from_status?: string;
  to_status: string;
  action: string;
  actor_id: string;
  actor_name?: string;
  actor_role?: string;
  notes?: string;
  created_at: string;
}

export interface FindingDecisionItem {
  id: string;
  finding_id: string;
  review_id: string;
  decision: FindingDecisionType;
  decided_by_id: string;
  decided_by_name?: string;
  reason?: string;
  suggested_correction?: string;
  created_at: string;
}

export interface ReviewCommentItem {
  id: string;
  organization_id: string;
  document_id: string;
  version_id: string;
  review_id: string;
  finding_id?: string;
  user_id: string;
  user_name?: string;
  user_role?: string;
  parent_comment_id?: string;
  content: string;
  created_at: string;
  replies: ReviewCommentItem[];
}

export interface ReviewItem {
  id: string;
  organization_id: string;
  document_id: string;
  version_id: string;
  document_title?: string;
  version_number?: number;
  brand_health_score?: number;
  creator_id: string;
  creator_name?: string;
  creator_email?: string;
  assigned_reviewer_id?: string;
  reviewer_name?: string;
  reviewer_email?: string;
  legal_reviewer_id?: string;
  legal_reviewer_name?: string;
  status: ReviewWorkflowStatus;
  priority: string;
  due_date?: string;
  legal_review_required: boolean;
  legal_status: string;
  submission_notes?: string;
  final_decision_notes?: string;
  final_decision_by?: string;
  created_at: string;
  updated_at: string;
  history?: ReviewHistoryItem[];
  finding_decisions?: FindingDecisionItem[];
}

export interface ReviewQueueStats {
  total: number;
  submitted: number;
  under_review: number;
  changes_requested: number;
  pending_approval: number;
  approved: number;
  rejected: number;
  assigned_to_current_user: number;
}

export interface VersionDiffTextSummary {
  v1_lines_count: number;
  v2_lines_count: number;
  added_lines_count: number;
  removed_lines_count: number;
  modified_lines_count: number;
}

export interface TextDiffLine {
  type: "SAME" | "ADD" | "REMOVE";
  text: string;
  line_number_v1?: number;
  line_number_v2?: number;
}

export interface VersionDiffFindingsSummary {
  v1_total_findings: number;
  v2_total_findings: number;
  resolved_findings_count: number;
  new_findings_count: number;
  persistent_findings_count: number;
  resolved_findings: any[];
  new_findings: any[];
}

export interface DocumentVersionComparison {
  document_id: string;
  v1_id: string;
  v2_id: string;
  v1_version_number: number;
  v2_version_number: number;
  v1_score?: number;
  v2_score?: number;
  score_delta?: number;
  text_summary: VersionDiffTextSummary;
  diff_lines: TextDiffLine[];
  findings_summary: VersionDiffFindingsSummary;
}

export interface NotificationItem {
  id: string;
  title: string;
  message: string;
  notification_type: string;
  reference_entity?: string;
  reference_id?: string;
  is_read: boolean;
  created_at: string;
}

export async function listReviews(filters?: {
  status?: string;
  priority?: string;
  assigned_to_me?: boolean;
}): Promise<ReviewItem[]> {
  const response = await apiClient.get<ReviewItem[]>("/reviews", { params: filters });
  return response.data;
}

export async function getReviewQueueStats(): Promise<ReviewQueueStats> {
  const response = await apiClient.get<ReviewQueueStats>("/reviews/queue/stats");
  return response.data;
}

export async function getReviewDetail(review_id: string): Promise<ReviewItem> {
  const response = await apiClient.get<ReviewItem>(`/reviews/${review_id}`);
  return response.data;
}

export async function createReview(data: {
  document_id: string;
  version_id?: string;
  priority?: string;
  assigned_reviewer_id?: string;
  legal_reviewer_id?: string;
  legal_review_required?: boolean;
  due_date?: string;
  submission_notes?: string;
}): Promise<ReviewItem> {
  const response = await apiClient.post<ReviewItem>("/reviews", data);
  return response.data;
}

export async function transitionReview(
  review_id: string,
  data: {
    action: string;
    notes?: string;
    new_version_id?: string;
  }
): Promise<ReviewItem> {
  const response = await apiClient.post<ReviewItem>(`/reviews/${review_id}/transition`, data);
  return response.data;
}

export async function assignReviewers(
  review_id: string,
  data: {
    assigned_reviewer_id?: string;
    legal_reviewer_id?: string;
    due_date?: string;
  }
): Promise<ReviewItem> {
  const response = await apiClient.patch<ReviewItem>(`/reviews/${review_id}/assign`, data);
  return response.data;
}

export async function recordFindingDecision(
  review_id: string,
  finding_id: string,
  data: {
    decision: FindingDecisionType;
    reason?: string;
    suggested_correction?: string;
  }
): Promise<FindingDecisionItem> {
  const response = await apiClient.post<FindingDecisionItem>(
    `/reviews/${review_id}/findings/${finding_id}/decision`,
    data
  );
  return response.data;
}

export async function listReviewComments(review_id: string): Promise<ReviewCommentItem[]> {
  const response = await apiClient.get<ReviewCommentItem[]>(`/reviews/${review_id}/comments`);
  return response.data;
}

export async function addReviewComment(
  review_id: string,
  data: {
    content: string;
    finding_id?: string;
    parent_comment_id?: string;
  }
): Promise<ReviewCommentItem> {
  const response = await apiClient.post<ReviewCommentItem>(
    `/reviews/${review_id}/comments`,
    data
  );
  return response.data;
}

export async function compareDocumentVersions(
  document_id: string,
  v1_id: string,
  v2_id: string
): Promise<DocumentVersionComparison> {
  const response = await apiClient.get<DocumentVersionComparison>(
    `/reviews/documents/${document_id}/compare`,
    { params: { v1: v1_id, v2: v2_id } }
  );
  return response.data;
}

export async function listNotifications(unread_only = false): Promise<NotificationItem[]> {
  const response = await apiClient.get<NotificationItem[]>("/notifications", {
    params: { unread_only },
  });
  return response.data;
}

export async function markNotificationRead(notification_id: string): Promise<NotificationItem> {
  const response = await apiClient.patch<NotificationItem>(
    `/notifications/${notification_id}/read`
  );
  return response.data;
}

export async function markAllNotificationsRead(): Promise<{ marked_read_count: number }> {
  const response = await apiClient.post<{ marked_read_count: number }>(
    "/notifications/read-all"
  );
  return response.data;
}
