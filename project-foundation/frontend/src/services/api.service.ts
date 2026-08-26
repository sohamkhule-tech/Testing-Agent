import { apiClient, API_BASE_URL } from '@/lib/api-client';
import { 
  Project, 
  CreateProjectRequest,
  TestRun,
  RunListResponse,
  RunStatusResponse,
  WorkflowTimeline,
  DashboardStats,
  ProjectStats,
  PaginationParams,
  ProjectPromptResponse,
  RunPromptResponse,
  PromptAnalysis,
  RunLogsResponse,
  ModelListResponse,
} from '@/types/api';

export const projectsService = {
  // Get all projects
  getAll: async (): Promise<Project[]> => {
    return apiClient.get<Project[]>('/api/v1/projects');
  },

  // Get single project
  getById: async (id: string): Promise<Project> => {
    return apiClient.get<Project>(`/api/v1/projects/${id}`);
  },

  // Create project
  create: async (data: CreateProjectRequest): Promise<Project> => {
    return apiClient.post<Project>('/api/v1/projects', data);
  },

  // Update project
  update: async (id: string, data: Partial<CreateProjectRequest>): Promise<Project> => {
    return apiClient.put<Project>(`/api/v1/projects/${id}`, data);
  },

  // Delete project
  delete: async (id: string): Promise<void> => {
    return apiClient.delete<void>(`/api/v1/projects/${id}`);
  },

  // Get project stats
  getStats: async (id: string): Promise<ProjectStats> => {
    return apiClient.get<ProjectStats>(`/api/v1/projects/${id}/stats`);
  },

  // Get project runs
  getRuns: async (id: string, params?: PaginationParams): Promise<RunListResponse> => {
    return apiClient.get<RunListResponse>(`/api/v1/projects/${id}/runs`, params);
  },

  // Phase 2 — project default prompt
  getPrompt: async (id: string): Promise<ProjectPromptResponse> => {
    return apiClient.get<ProjectPromptResponse>(`/api/v1/projects/${id}/prompt`);
  },

  savePrompt: async (id: string, text: string): Promise<ProjectPromptResponse> => {
    return apiClient.put<ProjectPromptResponse>(`/api/v1/projects/${id}/prompt`, { default_prompt_text: text });
  },
};

export const runsService = {
  // Get all runs
  getAll: async (params?: PaginationParams): Promise<RunListResponse> => {
    return apiClient.get<RunListResponse>('/api/v1/runs', params);
  },

  // Get single run
  getById: async (id: string): Promise<TestRun> => {
    return apiClient.get<TestRun>(`/api/v1/runs/${id}`);
  },

  // Generate run (trigger workflow, returns immediately, runs in background)
  create: async (projectId: string, userPrompt?: string, model?: string): Promise<{ run_id: string; status: string; ai_model?: string }> => {
    const body: Record<string, any> = { project_id: projectId };
    if (userPrompt) body.user_prompt = userPrompt;
    if (model) body.ai = { model };
    return apiClient.post<{ run_id: string; status: string; ai_model?: string }>('/api/v1/runs', body);
  },

  // Phase 1 — get prompt used for a run
  getPrompt: async (id: string): Promise<RunPromptResponse> => {
    return apiClient.get<RunPromptResponse>(`/api/v1/runs/${id}/prompt`);
  },

  // Transparency — analyse prompt before starting a run
  analyzePrompt: async (projectId: string, userPrompt: string, model?: string): Promise<PromptAnalysis> => {
    return apiClient.post<PromptAnalysis>('/api/v1/runs/analyze-prompt', {
      project_id: projectId,
      user_prompt: userPrompt,
      ai: model ? { model } : undefined,
    });
  },

  // Get workflow timeline
  getTimeline: async (id: string): Promise<WorkflowTimeline> => {
    return apiClient.get<WorkflowTimeline>(`/api/v1/runs/${id}/timeline`);
  },

  // Cancel run
  cancel: async (id: string): Promise<void> => {
    return apiClient.post<void>(`/api/v1/runs/${id}/cancel`);
  },

  // Approve run (continue to code generation)
  approve: async (id: string): Promise<any> => {
    return apiClient.post<any>(`/api/v1/runs/${id}/approve`);
  },

  // Resume / retry a failed run
  resume: async (id: string): Promise<any> => {
    return apiClient.post<any>(`/api/v1/runs/${id}/resume`);
  },

  retry: async (id: string): Promise<any> => {
    return apiClient.post<any>(`/api/v1/runs/${id}/retry`);
  },

  // Get run checkpoint state
  getState: async (id: string): Promise<any> => {
    return apiClient.get<any>(`/api/v1/runs/${id}/state`);
  },

  // Get run stage logs
  getLogs: async (id: string): Promise<RunLogsResponse> => {
    return apiClient.get<RunLogsResponse>(`/api/v1/runs/${id}/logs`);
  },

  // Get run status (live polling)
  getStatus: async (id: string): Promise<RunStatusResponse> => {
    return apiClient.get<RunStatusResponse>(`/api/v1/runs/${id}/status`);
  },

  // Workflow endpoints
  getWorkflow: async (id: string): Promise<any> => {
    return apiClient.get<any>(`/api/v1/runs/${id}/workflow`);
  },

  getTestPlan: async (id: string): Promise<any> => {
    return apiClient.get<any>(`/api/v1/runs/${id}/test-plan`);
  },

  getReview: async (id: string): Promise<any> => {
    return apiClient.get<any>(`/api/v1/runs/${id}/review`);
  },

  getCrawlerResults: async (id: string): Promise<any> => {
    return apiClient.get<any>(`/api/v1/runs/${id}/crawler`);
  },

  getInventory: async (id: string): Promise<any> => {
    return apiClient.get<any>(`/api/v1/runs/${id}/inventory`);
  },

  // Generated code
  getGeneratedFiles: async (id: string): Promise<any> => {
    return apiClient.get<any>(`/api/v1/runs/${id}/generated-files`);
  },

  // Download the COMPLETE generated Playwright project as a ZIP archive.
  downloadGeneratedCode: async (id: string): Promise<Blob> => {
    const response = await fetch(
      `${API_BASE_URL}/api/v1/runs/${id}/generated-code/download`
    );
    if (!response.ok) {
      let detail = `HTTP ${response.status}`;
      try {
        const body = await response.json();
        if (body && typeof body.detail === 'string') detail = body.detail;
      } catch {
        // Non-JSON error body — keep the HTTP fallback message.
      }
      throw new Error(detail);
    }
    return response.blob();
  },
};

export const dashboardService = {
  // Get dashboard stats
  getStats: async (): Promise<DashboardStats> => {
    return apiClient.get<DashboardStats>('/api/v1/dashboard/stats');
  },

  // Get recent runs
  getRecentRuns: async (limit: number = 10): Promise<TestRun[]> => {
    return apiClient.get<TestRun[]>('/api/v1/dashboard/recent-runs', { limit });
  },

  // Get recent projects
  getRecentProjects: async (limit: number = 5): Promise<Project[]> => {
    return apiClient.get<Project[]>('/api/v1/dashboard/recent-projects', { limit });
  },
};

export const healthService = {
  // Check API health
  check: async (): Promise<{ status: string }> => {
    return apiClient.get<{ status: string }>('/health');
  },
};

export const promptsService = {
  // Optimize prompt via LLM
  optimize: async (prompt: string, model?: string): Promise<import('@/types/api').OptimizePromptResponse> => {
    return apiClient.post<import('@/types/api').OptimizePromptResponse>('/api/v1/prompts/optimize', { prompt, model });
  },
};

export const modelsService = {
  getAll: async (): Promise<ModelListResponse> => {
    return apiClient.get<ModelListResponse>('/api/v1/models');
  },
};
