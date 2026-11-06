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
