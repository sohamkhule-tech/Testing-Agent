'use client';

import { use, useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  AlertCircle, Search, LayoutGrid, TestTube, GitPullRequest, Code2, FlaskConical,
  Eye, EyeOff, Sparkles, Zap, ExternalLink, Lock,
} from 'lucide-react';
import { toast } from 'sonner';

import { EmptyState } from '@/components/empty-state';
import { Skeleton } from '@/components/ui/skeleton';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { normalizePhase } from '@/lib/utils';
import { ProjectHeader } from '@/components/project/project-header';
import { WorkflowStepper, PHASE_ORDER } from '@/components/project/workflow-stepper';
import { WorkflowStageCard as StageCard } from '@/components/project/workflow-stage-card';
import { WorkflowTimeline } from '@/components/project/workflow-timeline';
import { RunList } from '@/components/project/run-list';
import { ProjectDetails } from '@/components/project/project-details';
import { PromptAnalysisPanel } from '@/components/project/prompt-analysis-panel';
import {
  useProject, useProjectStats, useProjectRuns, useDeleteProject, useCreateRun, useApproveRun,
  useProjectPrompt, useSaveProjectPrompt, useAnalyzePrompt,
} from '@/hooks/use-api';
import type { ParsedPromptIntent, PromptAnalysis } from '@/types/api';

const STORAGE_KEY = (id: string) => `ai-test-prompt:${id}`;
const MAX_PROMPT_CHARS = 10000;

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export default function ProjectDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const [showDelete, setShowDelete] = useState(false);
  const [userPrompt, setUserPrompt] = useState('');
  const [showPasswordField, setShowPasswordField] = useState(false);
  const [credUsername, setCredUsername] = useState('');
  const [credPassword, setCredPassword] = useState('');
  const [credLoginUrl, setCredLoginUrl] = useState('');

  // Transparency: analysis state
  const [analysis, setAnalysis] = useState<PromptAnalysis | null>(null);
  const [showAnalysisPanel, setShowAnalysisPanel] = useState(false);

  const { data: project, isLoading, error } = useProject(id);
  const { data: stats } = useProjectStats(id);
  const { data: runsData, isLoading: runsLoading } = useProjectRuns(id);
  const { data: promptData } = useProjectPrompt(id);
  const deleteProject = useDeleteProject();
  const createRun = useCreateRun();
  const approveRun = useApproveRun();
  const savePrompt = useSaveProjectPrompt();
  const analyzePrompt = useAnalyzePrompt();

  // Restore from localStorage on mount, then fall back to project default
  useEffect(() => {
    const stored = typeof window !== 'undefined' ? localStorage.getItem(STORAGE_KEY(id)) : null;
    if (stored) {
      setUserPrompt(stored);
    } else if (promptData?.default_prompt_text) {
      setUserPrompt(promptData.default_prompt_text);
    }
  }, [id, promptData]);

  // Auto-persist to localStorage on change; reset analysis when prompt changes
  const handlePromptChange = useCallback((value: string) => {
    setUserPrompt(value);
    setAnalysis(null);
    setShowAnalysisPanel(false);
    if (typeof window !== 'undefined') {
      if (value) localStorage.setItem(STORAGE_KEY(id), value);
      else localStorage.removeItem(STORAGE_KEY(id));
    }
  }, [id]);

  const latestRun = runsData?.runs?.find(r => !r.project_id || r.project_id === id) ?? runsData?.runs?.[0];
  // Only treat a run as blocking if it explicitly belongs to this project and is actively running.
  const hasRunningRun = !!(latestRun && (!latestRun.project_id || latestRun.project_id === id) &&
    (latestRun.status === 'in_progress' || latestRun.status === 'pending' || latestRun.status === 'running'));
  // Always show the prompt panel so the user can compose a prompt at any time.
  // Action buttons are individually disabled while a run is active.

  if (isLoading) return <PageSkeleton />;
  if (error || !project) {
    return (
      <div className="p-6">
        <EmptyState icon={AlertCircle} title="Project not found" description="This project doesn't exist or has been deleted."
          action={{ label: 'Back to Projects', onClick: () => router.push('/projects') }} />
      </div>
    );
  }

  const handleDelete = async () => {
    try { await deleteProject.mutateAsync(id); router.push('/projects'); }
    catch { toast.error('Failed to delete project'); }
  };

  const handleSaveDefaultPrompt = async () => {
    if (!userPrompt.trim()) return;
    savePrompt.mutate({ id, text: userPrompt }, {
      onSuccess: () => toast.success('Default prompt saved for this project'),
      onError: () => toast.error('Failed to save prompt'),
    });
  };

  const buildFinalPrompt = () => {
    let final = userPrompt;
    if (credUsername || credPassword) {
      final += '\n\n## Credentials';
      if (credLoginUrl) final += `\nLogin URL: ${credLoginUrl}`;
      if (credUsername) final += `\nUsername: ${credUsername}`;
      if (credPassword) final += `\nPassword: ${credPassword}`;
    }
    return final;
  };

  /** Called from both "Approve & Start Run" (in panel) and direct "Start Run" (skip analysis). */
  const handleStartRun = (promptOverride?: string) => {
    const finalPrompt = promptOverride ?? buildFinalPrompt();
    createRun.mutate({ projectId: id, userPrompt: finalPrompt || undefined }, {
      onSuccess: (data) => {
        if (typeof window !== 'undefined') localStorage.removeItem(STORAGE_KEY(id));
        toast.success('Run started');
        if (data?.run_id) router.push(`/runs/${data.run_id}`);
      },
      onError: () => toast.error('Failed to start run'),
    });
  };

  /** Triggered by "Analyse Prompt" button — calls backend, shows panel */
  const handleAnalyzePrompt = () => {
    const finalPrompt = buildFinalPrompt();
    analyzePrompt.mutate(
      { projectId: id, userPrompt: finalPrompt },
      {
        onSuccess: (data) => {
          setAnalysis(data);
          setShowAnalysisPanel(true);
        },
        onError: () => toast.error('Prompt analysis failed'),
      },
    );
    // Show panel immediately so the loading/reasoning animation plays
    setShowAnalysisPanel(true);
    setAnalysis(null);
  };

  const handleDeleteClick = () => setShowDelete(true);
  const handleApprove = () => {
    if (latestRun) {
      approveRun.mutate(latestRun.run_id, {
        onSuccess: () => toast.success('Test plan approved! Generating tests...'),
        onError: () => toast.error('Failed to approve test plan'),
      });
    }
  };

  const currentPhase = normalizePhase(latestRun?.current_phase);
  const charCount = userPrompt.length;
  const charWarning = charCount > MAX_PROMPT_CHARS * 0.9;

  const getStageStatus = (phase: string): 'past' | 'current' | 'pending' | 'failed' => {
    if (!latestRun) return 'pending';
    if (latestRun.status === 'completed') return 'past';
    const normStage = normalizePhase(phase);
    const idx = PHASE_ORDER.indexOf(normStage);
    const curIdx = PHASE_ORDER.indexOf(currentPhase);
    if (curIdx === -1) return 'pending';
    if (idx < curIdx) return 'past';
    if (idx === curIdx) return latestRun.status === 'failed' ? 'failed' : 'current';
    return 'pending';
  };

  return (
    <div className="p-6 space-y-8">
      <ProjectHeader
        project={project}
        latestRun={latestRun}
        isStarting={createRun.isPending}
        hasRunningRun={!!hasRunningRun}
        onStartRun={() => handleStartRun()}
        onDelete={handleDeleteClick}
        onApprove={latestRun?.status === 'paused' ? handleApprove : undefined}
        isApproving={approveRun.isPending}
      />

      {/* Live Execution Banner when run is active */}
      {hasRunningRun && latestRun && (() => {
          const phase = latestRun.current_phase ?? 'crawler';
          const BANNER_META: Record<string, { title: string; desc: string; btnLabel: string; dotColor: string; borderColor: string; bgColor: string; textColor: string; btnColor: string }> = {
            trigger:         { title: 'Run Initialising',          desc: 'Setting up workspace and environment for the run.',                              btnLabel: 'View Run Setup',            dotColor: 'bg-zinc-400',    borderColor: 'border-zinc-600/50',    bgColor: 'bg-zinc-800/50',    textColor: 'text-zinc-200',   btnColor: 'bg-zinc-700 hover:bg-zinc-600' },
            crawler:         { title: 'Live Web Crawler Running',  desc: 'AI is autonomously crawling pages, clicking links, and capturing screenshots.',  btnLabel: 'Open Live Crawler Screen ↗', dotColor: 'bg-blue-400',    borderColor: 'border-blue-500/40',    bgColor: 'bg-blue-500/10',    textColor: 'text-blue-200',   btnColor: 'bg-blue-600 hover:bg-blue-500' },
            inventory:       { title: 'Building Inventory',        desc: 'Analysing crawled data — discovering pages, forms, components and endpoints.',   btnLabel: 'View Inventory ↗',          dotColor: 'bg-violet-400',  borderColor: 'border-violet-500/40',  bgColor: 'bg-violet-500/10',  textColor: 'text-violet-200', btnColor: 'bg-violet-600 hover:bg-violet-500' },
            test_design:     { title: 'AI Test Design In Progress',desc: 'Designing test scenarios, coverage strategy, and generating a test plan.',       btnLabel: 'View AI Test Design ↗',     dotColor: 'bg-indigo-400',  borderColor: 'border-indigo-500/40',  bgColor: 'bg-indigo-500/10',  textColor: 'text-indigo-200', btnColor: 'bg-indigo-600 hover:bg-indigo-500' },
            human_review:    { title: 'Awaiting Human Review',     desc: 'Test plan is ready for review. Your approval is needed to continue.',            btnLabel: 'Open Human Review ↗',       dotColor: 'bg-amber-400',   borderColor: 'border-amber-500/40',   bgColor: 'bg-amber-500/10',   textColor: 'text-amber-200',  btnColor: 'bg-amber-600 hover:bg-amber-500' },
            code_generation: { title: 'Generating Test Code',      desc: 'Creating Playwright test scripts from the approved test plan.',                  btnLabel: 'View Code Generation ↗',    dotColor: 'bg-pink-400',    borderColor: 'border-pink-500/40',    bgColor: 'bg-pink-500/10',    textColor: 'text-pink-200',   btnColor: 'bg-pink-600 hover:bg-pink-500' },
            execution:       { title: 'Test Execution Running',    desc: 'Running Playwright tests against the live application — monitoring results.',    btnLabel: 'View Test Execution ↗',     dotColor: 'bg-emerald-400', borderColor: 'border-emerald-500/40', bgColor: 'bg-emerald-500/10', textColor: 'text-emerald-200',btnColor: 'bg-emerald-600 hover:bg-emerald-500' },
            reporting:       { title: 'Generating Final Report',   desc: 'Compiling test results and building the final automated testing report.',        btnLabel: 'View Report ↗',             dotColor: 'bg-teal-400',    borderColor: 'border-teal-500/40',    bgColor: 'bg-teal-500/10',    textColor: 'text-teal-200',   btnColor: 'bg-teal-600 hover:bg-teal-500' },
          };
          const meta = BANNER_META[phase] ?? BANNER_META['crawler'];
          return (
            <div className={`flex items-center justify-between p-4 rounded-xl border ${meta.borderColor} ${meta.bgColor} ${meta.textColor} shadow-xl`}>
              <div className="flex items-center gap-3">
                <span className="relative flex h-3 w-3 shrink-0">
                  <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${meta.dotColor} opacity-75`} />
                  <span className={`relative inline-flex rounded-full h-3 w-3 ${meta.dotColor}`} />
                </span>
                <div>
                  <p className="text-sm font-semibold text-white">
                    {meta.title} — Run #{latestRun.run_id.slice(0, 8)}…
                  </p>
                  <p className="text-xs opacity-75 mt-0.5">{meta.desc}</p>
                </div>
              </div>
              <Link
                href={`/runs/${latestRun.run_id}`}
                className={`flex items-center gap-1.5 px-4 py-2 rounded-lg ${meta.btnColor} text-white text-xs font-semibold shadow-md transition-all shrink-0 ml-4`}
              >
                <ExternalLink className="h-4 w-4" />
                <span>{meta.btnLabel}</span>
              </Link>
            </div>
          );
        })()}



      {/* AI Test Instructions panel — always visible */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 space-y-3">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-blue-400" />
              <label className="text-xs font-medium text-zinc-300 uppercase tracking-wider">AI Test Instructions</label>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={handleSaveDefaultPrompt}
                disabled={!userPrompt.trim() || savePrompt.isPending}
                className="text-[11px] text-zinc-500 hover:text-zinc-300 disabled:opacity-40 transition-colors"
              >
                {savePrompt.isPending ? 'Saving…' : 'Save as default'}
              </button>
            </div>
          </div>

          {/* Textarea — hidden when analysis panel is open */}
          {!showAnalysisPanel && (
            <>
              <textarea
                value={userPrompt}
                onChange={(e) => handlePromptChange(e.target.value)}
                maxLength={MAX_PROMPT_CHARS}
                placeholder={`Describe what to test in plain English.\n\nExamples:\n- "Test the login form with valid and invalid credentials"\n- "Focus on Reports module, ignore User Management"\n- "Generate negative and boundary scenarios for all forms"\n\nUse ## headings for sections: Focus Areas, Credentials, Exclude, Coverage, Output`}
                className="w-full px-3 py-2 rounded-lg bg-zinc-950 border border-zinc-800 text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:ring-2 focus:ring-blue-500/50 min-h-[100px] resize-y font-mono"
              />
              <div className="flex items-center justify-between">
                <p className="text-[11px] text-zinc-600">
                  Tell the AI what to test. Leave empty for automatic generation.
                </p>
                <span className={`text-[11px] ${charWarning ? 'text-amber-400' : 'text-zinc-600'}`}>
                  {charCount.toLocaleString()} / {MAX_PROMPT_CHARS.toLocaleString()}
                </span>
              </div>

              {/* Structured credentials */}
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <div className="h-px flex-1 bg-zinc-800" />
                  <span className="text-[11px] text-zinc-500 font-medium whitespace-nowrap flex items-center gap-1">
                    <Lock className="h-3 w-3" /> Login Credentials
                  </span>
                  <div className="h-px flex-1 bg-zinc-800" />
                </div>
                <div className="rounded-md border border-zinc-800 bg-zinc-950 p-3 space-y-2">
                  <p className="text-[11px] text-zinc-500">
                    Enter credentials so the crawler can log in. Credentials are encrypted and never logged.
                  </p>
                  <div className="grid gap-2 sm:grid-cols-2">
                    <div>
                      <label className="text-[11px] text-zinc-400 block mb-1">Login URL (optional)</label>
                      <input
                        type="url"
                        value={credLoginUrl}
                        onChange={e => setCredLoginUrl(e.target.value)}
                        placeholder="Auto-detected if empty"
                        className="w-full px-2 py-1.5 rounded-md bg-zinc-900 border border-zinc-800 text-xs text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-blue-500/50"
                        />
                      </div>
                      <div>
                        <label className="text-[11px] text-zinc-500 block mb-1">Username / Email</label>
                        <input
                          type="text"
                          value={credUsername}
                          onChange={e => setCredUsername(e.target.value)}
                          placeholder="admin@example.com"
                          autoComplete="off"
                          className="w-full px-2 py-1.5 rounded-md bg-zinc-900 border border-zinc-800 text-xs text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-blue-500/50"
                        />
                      </div>
                      <div className="sm:col-span-2">
                        <label className="text-[11px] text-zinc-500 block mb-1">Password</label>
                        <div className="flex items-center gap-1">
                          <input
                            type={showPasswordField ? 'text' : 'password'}
                            value={credPassword}
                            onChange={e => setCredPassword(e.target.value)}
                            placeholder="••••••••"
                            autoComplete="new-password"
                            className="flex-1 px-2 py-1.5 rounded-md bg-zinc-900 border border-zinc-800 text-xs text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-blue-500/50"
                          />
                          <button
                            type="button"
                            onClick={() => setShowPasswordField((v: boolean) => !v)}
                            className="p-1.5 text-zinc-500 hover:text-zinc-300 transition-colors"
                            aria-label={showPasswordField ? 'Hide password' : 'Show password'}
                          >
                            {showPasswordField ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

              {/* Action row: Analyse Prompt (primary) + Start Run directly (secondary / skip) */}
              <div className="flex gap-2 pt-1">
                {hasRunningRun && latestRun ? (
                  <Link
                    href={`/runs/${latestRun.run_id}`}
                    className="flex-1 flex items-center justify-center gap-2 rounded-md bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold py-2 px-4 transition-all shadow-md"
                  >
                    <ExternalLink className="h-4 w-4" />
                    <span>Open Live Run & Crawler Screen ↗</span>
                  </Link>
                ) : (
                  <>
                    <button
                      onClick={handleAnalyzePrompt}
                      disabled={analyzePrompt.isPending || createRun.isPending}
                      className="flex-1 flex items-center justify-center gap-2 rounded-md bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium py-2 px-4 transition-colors"
                    >
                      <Zap className="h-4 w-4" />
                      Analyse Prompt
                    </button>
                    <button
                      onClick={() => handleStartRun()}
                      disabled={createRun.isPending || analyzePrompt.isPending}
                      className="flex items-center gap-1.5 rounded-md border border-zinc-700 hover:border-zinc-500 text-zinc-400 hover:text-zinc-200 text-xs py-2 px-3 transition-colors disabled:opacity-50"
                      title="Skip analysis and start run directly"
                    >
                      Skip Analysis
                    </button>
                  </>
                )}
              </div>
            </>
          )}

          {/* Analysis Panel — shown after analyse is clicked */}
          {showAnalysisPanel && (
            <PromptAnalysisPanel
              analysis={analysis ?? {
                analysis_id: '',
                raw_prompt: userPrompt,
                interpretation: {} as any,
                confidence_scores: [],
                execution_plan: [],
                quality: { score: 0, strengths: [], suggestions: [] },
                ambiguities: [],
                credential_status: { username_detected: false, password_detected: false,
                  login_url_detected: false, is_complete: false, warnings: [] },
                scope_summary: { included_modules: [], excluded_modules: [],
                  included_pages: [], excluded_pages: [] },
                estimated: { modules_estimate: 0, pages_range: '—', scenarios_range: '—',
                  framework: 'Playwright', requires_auth: false, estimated_runtime_minutes: 3 },
                reasoning_steps: ['Analysing instructions...'],
                parsed_intent: {} as any,
              }}
              isLoading={analyzePrompt.isPending || !analysis}
              onApprove={() => {
                // Use parsed_intent from analysis so the run gets structured context
                const finalPrompt = buildFinalPrompt();
                handleStartRun(finalPrompt);
              }}
              onEdit={() => {
                setShowAnalysisPanel(false);
                setAnalysis(null);
              }}
              onRegenerate={handleAnalyzePrompt}
              isStarting={createRun.isPending}
            />
          )}
        </div>

      <WorkflowStepper currentPhase={currentPhase} status={latestRun?.status} />

      <div className="space-y-4">
        <StageCard icon={Search} label="Crawler" status={getStageStatus('crawler')}
          runStatus={latestRun?.status} detail={{ pages: latestRun?.pages_visited ? String(latestRun.pages_visited) : '—', forms: '—', apis: '—', duration: '—' }}
          actions={latestRun ? [{ label: 'View Live Crawler ↗', href: `/runs/${latestRun.run_id}` }] : []} />
        <StageCard icon={LayoutGrid} label="Inventory" status={getStageStatus('inventory')}
          runStatus={latestRun?.status} detail={{ pages: latestRun?.pages_visited ? String(latestRun.pages_visited) : '—', forms: '—', components: '—', endpoints: '—' }}
          actions={latestRun ? [{ label: 'Open Inventory', href: `/runs/${latestRun.run_id}` }] : []} />
        <StageCard icon={TestTube} label="Test Design" status={getStageStatus('test_design')}
          runStatus={latestRun?.status} detail={{ scenarios: latestRun?.scenarios_generated ? String(latestRun.scenarios_generated) : '—', coverage: '—', priority: '—' }}
          actions={latestRun ? [{ label: 'View Test Plan', href: `/runs/${latestRun.run_id}` }] : []} />
        <StageCard icon={GitPullRequest} label="Human Review" status={getStageStatus('human_review')}
          runStatus={latestRun?.status} detail={{ approved: '—', rejected: '—', pending: '—' }}
          actions={latestRun ? [{ label: 'Open Reviews', href: `/runs/${latestRun.run_id}` }] : []} />
        <StageCard icon={Code2} label="Playwright Generation" status={getStageStatus('code_generation')}
          runStatus={latestRun?.status} detail={{ files: '—', tests: '—', duration: '—' }}
          actions={latestRun ? [{ label: 'View Generated Code', href: `/runs/${latestRun.run_id}` }] : []} />
        <StageCard icon={FlaskConical} label="Execution" status={getStageStatus('execution')}
          runStatus={latestRun?.status} detail={{ passed: '—', failed: '—', skipped: '—', duration: '—' }}
          actions={latestRun ? [{ label: 'View Results ↗', href: `/runs/${latestRun.run_id}` }] : []} />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <WorkflowTimeline latestRun={latestRun} />
        <RunList runs={runsData?.runs ?? []} isLoading={runsLoading} />
        <ProjectDetails project={project} stats={stats} runs={runsData?.runs} />
      </div>

      {showDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <Card className="w-full max-w-md mx-4">
            <CardHeader><CardTitle className="text-lg">Delete Project</CardTitle>
              <p className="text-sm text-muted-foreground mt-1">Delete <strong>{project.name}</strong>? This cannot be undone.</p>
            </CardHeader>
            <CardContent className="flex justify-end gap-2">
              <button className="px-4 py-2 text-sm rounded-md border hover:bg-accent" onClick={() => setShowDelete(false)}>Cancel</button>
              <button className="px-4 py-2 text-sm rounded-md bg-red-600 text-white hover:bg-red-700 disabled:opacity-50" onClick={handleDelete} disabled={deleteProject.isPending}>
                {deleteProject.isPending ? 'Deleting…' : 'Delete'}
              </button>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}

function PageSkeleton() {
  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center gap-4"><Skeleton className="h-9 w-9 rounded-md" /><div className="space-y-2"><Skeleton className="h-8 w-64" /><Skeleton className="h-4 w-96" /></div></div>
      <Skeleton className="h-32 rounded-lg" />
      {[...Array(4)].map((_, i) => <Skeleton key={i} className="h-28 rounded-lg" />)}
      <div className="grid gap-6 lg:grid-cols-3"><Skeleton className="h-80 rounded-lg" /><Skeleton className="h-80 rounded-lg" /><Skeleton className="h-80 rounded-lg" /></div>
    </div>
  );
}
