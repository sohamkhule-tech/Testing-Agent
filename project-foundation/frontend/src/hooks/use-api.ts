import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { projectsService, runsService, dashboardService } from '@/services/api.service';
import { CreateProjectRequest, PaginationParams } from '@/types/api';

// Query Keys
export const queryKeys = {
  projects: ['projects'] as const,
  project: (id: string) => ['projects', id] as const,
  projectRuns: (id: string) => ['projects', id, 'runs'] as const,
  projectStats: (id: string) => ['projects', id, 'stats'] as const,
  runs: ['runs'] as const,
  run: (id: string) => ['runs', id] as const,
  runTimeline: (id: string) => ['runs', id, 'timeline'] as const,
  dashboard: ['dashboard'] as const,
  dashboardStats: ['dashboard', 'stats'] as const,
  dashboardRecentRuns: ['dashboard', 'recent-runs'] as const,
  dashboardRecentProjects: ['dashboard', 'recent-projects'] as const,
  runStatus: (id: string) => ['runs', id, 'status'] as const,
  latestRun: (projectId: string) => ['projects', projectId, 'latest-run'] as const,
};

// Projects Hooks
export function useProjects() {
  return useQuery({
    queryKey: queryKeys.projects,
    queryFn: () => projectsService.getAll(),
  });
}

export function useProject(id: string) {
  return useQuery({
    queryKey: queryKeys.project(id),
    queryFn: () => projectsService.getById(id),
    enabled: !!id,
  });
}

export function useProjectRuns(id: string, params?: PaginationParams) {
  return useQuery({
    queryKey: [...queryKeys.projectRuns(id), params],
    queryFn: () => projectsService.getRuns(id, params),
    enabled: !!id,
    refetchInterval: (query) => {
      const runs = query.state.data?.runs;
      const hasActive = runs?.some(r => r.status === 'in_progress' || r.status === 'pending' || r.status === 'running');
      return hasActive ? 3000 : 8000;
    },
  });
}

export function useProjectStats(id: string) {
  return useQuery({
    queryKey: queryKeys.projectStats(id),
    queryFn: () => projectsService.getStats(id),
    enabled: !!id,
  });
}

export function useCreateProject() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: (data: CreateProjectRequest) => projectsService.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.projects });
      queryClient.invalidateQueries({ queryKey: queryKeys.dashboardRecentProjects });
    },
  });
}

export function useDeleteProject() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: (id: string) => projectsService.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.projects });
    },
  });
}

// Phase 2 — Project default prompt hooks
export function useProjectPrompt(id: string) {
  return useQuery({
    queryKey: [...queryKeys.project(id), 'prompt'],
    queryFn: () => projectsService.getPrompt(id),
    enabled: !!id,
  });
}

export function useSaveProjectPrompt() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, text }: { id: string; text: string }) => projectsService.savePrompt(id, text),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: [...queryKeys.project(variables.id), 'prompt'] });
    },
  });
}

export function useAnalyzePrompt() {
  return useMutation({
    mutationFn: ({ projectId, userPrompt }: { projectId: string; userPrompt: string }) =>
      runsService.analyzePrompt(projectId, userPrompt),
  });
}

// Runs Hooks
export function useRuns(params?: PaginationParams) {
  return useQuery({
    queryKey: [...queryKeys.runs, params],
    queryFn: () => runsService.getAll(params),
  });
}

export function useRun(id: string) {
  return useQuery({
    queryKey: queryKeys.run(id),
    queryFn: () => runsService.getById(id),
    enabled: !!id,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === 'in_progress' ? 5000 : false;
    },
  });
}

export function useRunTimeline(id: string) {
  return useQuery({
    queryKey: queryKeys.runTimeline(id),
    queryFn: () => runsService.getTimeline(id),
    enabled: !!id,
    refetchInterval: (query) => {
      const status = query.state.data?.overall_status;
      return status === 'in_progress' ? 5000 : false;
    },
  });
}

export function useCreateRun() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: ({ projectId, userPrompt }: { projectId: string; userPrompt?: string }) => runsService.create(projectId, userPrompt),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.runs });
      queryClient.invalidateQueries({ queryKey: queryKeys.dashboardRecentRuns });
      if (variables?.projectId) {
        queryClient.invalidateQueries({ queryKey: queryKeys.latestRun(variables.projectId) });
        queryClient.invalidateQueries({ queryKey: queryKeys.projectRuns(variables.projectId) });
        queryClient.invalidateQueries({ queryKey: queryKeys.project(variables.projectId) });
        queryClient.invalidateQueries({ queryKey: queryKeys.projectStats(variables.projectId) });
      }
    },
  });
}

export function useApproveRun() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => runsService.approve(id),
    onSuccess: (_data, id) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.run(id) });
      queryClient.invalidateQueries({ queryKey: queryKeys.runs });
    },
  });
}

export function useResumeRun() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => runsService.resume(id),
    onSuccess: (_data, id) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.run(id) });
      queryClient.invalidateQueries({ queryKey: queryKeys.runs });
    },
  });
}

export function useRunState(id: string) {
  return useQuery({
    queryKey: [...queryKeys.run(id), 'state'],
    queryFn: () => runsService.getState(id),
    enabled: !!id,
    refetchInterval: 10000,
  });
}

export function useRunLogs(id: string) {
  return useQuery({
    queryKey: [...queryKeys.run(id), 'logs'],
    queryFn: () => runsService.getLogs(id),
    enabled: !!id,
  });
}

export function useCancelRun() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: (id: string) => runsService.cancel(id),
    onSuccess: (_data, id) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.run(id) });
      queryClient.invalidateQueries({ queryKey: queryKeys.runs });
    },
  });
}

// Dashboard Hooks
export function useDashboardStats() {
  return useQuery({
    queryKey: queryKeys.dashboardStats,
    queryFn: () => dashboardService.getStats(),
  });
}

export function useRecentRuns(limit: number = 10) {
  return useQuery({
    queryKey: [...queryKeys.dashboardRecentRuns, limit],
    queryFn: () => dashboardService.getRecentRuns(limit),
  });
}

export function useRecentProjects(limit: number = 5) {
  return useQuery({
    queryKey: [...queryKeys.dashboardRecentProjects, limit],
    queryFn: () => dashboardService.getRecentProjects(limit),
  });
}

// Workflow Data Hooks
export function useRunWorkflow(id: string) {
  return useQuery({
    queryKey: ['runs', id, 'workflow'],
    queryFn: () => runsService.getWorkflow(id),
    enabled: !!id,
  });
}

export function useRunTestPlan(id: string) {
  return useQuery({
    queryKey: ['runs', id, 'test-plan'],
    queryFn: () => runsService.getTestPlan(id),
    enabled: !!id,
  });
}

export function useRunReview(id: string) {
  return useQuery({
    queryKey: ['runs', id, 'review'],
    queryFn: () => runsService.getReview(id),
    enabled: !!id,
  });
}

export function useGeneratedFiles(id: string) {
  return useQuery({
    queryKey: ['runs', id, 'generated-files'],
    queryFn: () => runsService.getGeneratedFiles(id),
    enabled: !!id,
  });
}

// ── Run Status (live polling) ──

export function useRunStatus(id: string) {
  return useQuery({
    queryKey: queryKeys.runStatus(id),
    queryFn: () => runsService.getStatus(id),
    enabled: !!id,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === 'in_progress' || status === 'pending' ? 5000 : false;
    },
  });
}

export function useLatestRun(projectId: string) {
  return useQuery({
    queryKey: queryKeys.latestRun(projectId),
    queryFn: async () => {
      const response = await projectsService.getRuns(projectId, { page_size: 1 });
      return response.runs[0] ?? null;
    },
    enabled: !!projectId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === 'in_progress' || status === 'pending' ? 5000 : false;
    },
  });
}
