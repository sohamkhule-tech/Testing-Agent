// Core Types
export type RunStatus = 'pending' | 'in_progress' | 'completed' | 'failed' | 'cancelled' | 'paused' | 'running';
export type WorkflowPhase = 'trigger' | 'crawler' | 'inventory' | 'test_design' | 'human_review' | 'code_generation' | 'execution' | 'reporting';
export type ReviewStatus = 'draft' | 'under_review' | 'approved' | 'partially_approved' | 'changes_requested' | 'rejected' | 'archived';

// Project Types
export interface Project {
  id: string;
  name: string;
  description?: string;
  application_url: string;
  auth_type?: string;
  created_at: string;
  updated_at: string;
  total_runs: number;
  last_run_at?: string;
  last_run_status?: RunStatus;
  pending_reviews: number;
  tags?: string[];
  // Phase 2 — project default prompt
  default_prompt_text?: string;
}

export interface TokenUsageInfo {
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
}

export interface OptimizePromptRequest {
  prompt: string;
  model?: string;
}

export interface OptimizePromptResponse {
  originalPrompt: string;
  optimizedPrompt: string;
  model: string;
  usage: TokenUsageInfo;
}

export interface SupportedModel {
  id: string;
  name: string;
  provider: string;
}

export interface ModelListResponse {
  models: SupportedModel[];
  defaultModel: string;
}

export interface CreateProjectRequest {
  name: string;
  description?: string;
  application_url: string;
  starting_urls: string[];
  auth_type?: string;
  max_pages?: number;
  max_depth?: number;
  include_patterns?: string[];
  exclude_patterns?: string[];
  tags?: string[];
}

// Run Types
export interface TestRun {
  run_id: string;
  request_id: string;
  project_id?: string;
  status: RunStatus;
  current_phase: WorkflowPhase;
  started_at: string;
  completed_at?: string;
  duration_seconds?: number;
  requested_by?: string;
  workspace_path: string;
  pages_visited?: number;
  scenarios_generated?: number;
  review_status?: ReviewStatus;
  error_message?: string;
  ai_model?: string;
}

export interface RunListResponse {
  runs: TestRun[];
  total: number;
  page: number;
  page_size: number;
}

// Workflow Types
export interface WorkflowPhaseStatus {
  phase: WorkflowPhase;
  status: 'pending' | 'running' | 'completed' | 'failed';
  started_at?: string;
  completed_at?: string;
  duration_seconds?: number;
  error?: string;
}

export interface WorkflowTimeline {
  run_id: string;
  phases: WorkflowPhaseStatus[];
  overall_status: RunStatus;
}

// Artifact Types
export interface Artifact {
  id: string;
  run_id: string;
  type: 'crawl_package' | 'inventory' | 'test_plan' | 'approved_test_plan' | 'review_metadata';
  file_path: string;
  created_at: string;
  size_bytes?: number;
}

// Statistics Types
export interface DashboardStats {
  total_projects: number;
  total_runs: number;
  active_runs: number;
  pending_reviews: number;
  completed_today: number;
  success_rate: number;
}

export interface ProjectStats {
  total_pages_crawled: number;
  total_forms_discovered: number;
  total_scenarios_generated: number;
  total_runs: number;
  successful_runs: number;
  failed_runs: number;
  average_duration_seconds: number;
}

// Review Types
export interface ReviewMetadata {
  run_id: string;
  review_status: ReviewStatus;
  reviewer_name?: string;
  review_version: number;
  approved_scenarios: number;
  rejected_scenarios: number;
  total_scenarios: number;
  approval_date?: string;
}

// Prompt Types (Phase 1/2/5)
export interface ParsedPromptIntent {
  raw_text: string;
  focus_areas: string[];
  excluded_modules: string[];
  excluded_pages: string[];
  included_pages: string[];
  coverage_preferences: string[];
  output_preferences: string[];
  custom_instructions: string;
  has_credentials: boolean;
}

export interface ProjectPromptResponse {
  project_id: string;
  default_prompt_text: string;
  updated_at: string | null;
}

export interface RunPromptResponse {
  run_id: string;
  user_prompt_redacted_text: string | null;
  prompt_context: ParsedPromptIntent | null;
  prompt_version: string;
}

// -----------------------------------------------------------------------
// Prompt Analysis Types (Transparency feature)
// -----------------------------------------------------------------------

export interface ConfidenceItem {
  label: string;
  value: number;       // 0-100
  category: 'scope' | 'exclude' | 'coverage' | 'output' | 'auth';
  is_low: boolean;
}

export interface ExecutionStep {
  step: number;
  label: string;
  description: string;
  icon: string;
}

export interface CredentialStatus {
  username_detected: boolean;
  password_detected: boolean;
  login_url_detected: boolean;
  is_complete: boolean;
  warnings: string[];
}

export interface PromptQuality {
  score: number;
  strengths: string[];
  suggestions: string[];
}

export interface PromptAmbiguity {
  phrase: string;
  message: string;
  suggestions: string[];
}

export interface ScopeSummary {
  included_modules: string[];
  excluded_modules: string[];
  included_pages: string[];
  excluded_pages: string[];
}

export interface EstimatedStats {
  modules_estimate: number;
  pages_range: string;
  scenarios_range: string;
  framework: string;
  requires_auth: boolean;
  estimated_runtime_minutes: number;
}

export interface PromptInterpretation {
  scope: string[];
  excluded: string[];
  included_pages: string[];
  excluded_pages: string[];
  authentication: { required: boolean; complete: boolean; strategy: string };
  coverage: string[];
  output: string[];
  custom_instructions: string;
  has_section_headers: boolean;
}

export interface PromptAnalysis {
  analysis_id: string;
  raw_prompt: string;
  interpretation: PromptInterpretation;
  confidence_scores: ConfidenceItem[];
  execution_plan: ExecutionStep[];
  quality: PromptQuality;
  ambiguities: PromptAmbiguity[];
  credential_status: CredentialStatus;
  scope_summary: ScopeSummary;
  estimated: EstimatedStats;
  reasoning_steps: string[];
  parsed_intent: ParsedPromptIntent;
  ai_model?: string;
}

// Run Status Response (from GET /api/v1/runs/{run_id}/status)
export interface RunStatusResponse {
  run_id: string;
  status: RunStatus;
  created_at: string;
  updated_at: string;
  current_stage?: string;
  progress_percent?: number;
  message?: string;
}

// API Response Types
export interface ApiError {
  detail: string;
  status_code: number;
}

export interface PaginationParams {
  page?: number;
  page_size?: number;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
}

// Run Logs Types (from GET /api/v1/runs/{run_id}/logs)
export interface RunLogsEvent {
  type: string;
  timestamp: string;
  stage: string;
  message: string;
  level: 'info' | 'success' | 'warning' | 'error';
}

export interface RunLogsResponse {
  run_id: string;
  stage_logs: Record<string, string[]>;
  events: RunLogsEvent[];
  error: string | null;
}
