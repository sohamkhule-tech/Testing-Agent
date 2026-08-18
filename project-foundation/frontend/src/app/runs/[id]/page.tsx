'use client';

/**
 * Run Monitor Page — Real-Time AI Testing Workflow Dashboard
 *
 * Replaces the old polling-based run detail page with a fully event-driven
 * dashboard. All live state is built from SSE events via the Zustand store.
 * REST APIs are used only for initial run metadata (useRun hook).
 */

import { use, useState, useEffect, useRef } from 'react';
import Link from 'next/link';
import { cn } from '@/lib/utils';
import { useRun, useResumeRun, useRunState } from '@/hooks/use-api';
import { useWorkflowSSE } from '@/hooks/use-workflow-sse';
import { useWorkflowStore } from '@/store/workflow-store';

// Components
import { PipelineStages }          from '@/components/run-monitor/pipeline-stages';
import { EventTimeline }           from '@/components/run-monitor/event-timeline';
import { BrowserActivity, CrawlStats, LiveBrowserPreview, ScreenshotGallery } from '@/components/run-monitor/browser-activity';
import { InventoryTree }           from '@/components/run-monitor/inventory-tree';
import { LLMActivity }             from '@/components/run-monitor/llm-activity';
import { TestPlanViewer, HumanReviewPanel } from '@/components/run-monitor/test-plan-viewer';
import { CodeGenerationProgress, ExecutionMonitor } from '@/components/run-monitor/execution-monitor';
import { LiveFileExplorer, LiveCodeViewer } from '@/components/run-monitor/live-code-viewer';
import { CodeGenWorkspace }         from '@/components/run-monitor/code-gen-workspace';
import { FailedStageCard }         from '@/components/run-monitor/failed-stage-card';
import { StageRecoveryPanel }      from '@/components/run-monitor/stage-recovery-panel';
import { ExecutionReportPanel }    from '@/components/run-monitor/execution-report-panel';

// New AI Agent Experience Components
import { AIThinkingPanel }         from '@/components/run-monitor/ai-thinking-panel';
import { AIDecisionLog }           from '@/components/run-monitor/ai-decision-log';
import { LiveStats }               from '@/components/run-monitor/live-stats';
import { ScenarioCards }           from '@/components/run-monitor/scenario-cards';
import { ModuleDetection }         from '@/components/run-monitor/module-detection';
import { TestPlanSummary }         from '@/components/run-monitor/test-plan-summary';
import { InventoryDetailView }     from '@/components/run-monitor/inventory-detail-view';
import { FullUICrawlerWorkspace }  from '@/components/run-monitor/full-ui-crawler';

import {
  ArrowLeft,
  Globe,
  Layers,
  Bot,
  ClipboardList,
  UserCheck,
  Code2,
  Camera,
  Play,
  LayoutDashboard,
  Wifi,
  WifiOff,
  Clock,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Loader2,
  Cpu,
  Box,
  ExternalLink,
  Maximize2,
  BarChart2,
} from 'lucide-react';

// ---------------------------------------------------------------------------
// Tab definitions
// ---------------------------------------------------------------------------

const TABS = [
  { id: 'overview',     label: 'Overview',       icon: LayoutDashboard },
  { id: 'crawler',      label: 'Crawler',         icon: Globe },
  { id: 'inventory',    label: 'Inventory',       icon: Layers },
  { id: 'test-design',  label: 'Test Design',     icon: Bot },
  { id: 'review',       label: 'Review',          icon: UserCheck },
  { id: 'code',         label: 'Code Gen',        icon: Code2 },
  { id: 'execution',    label: 'Execution',       icon: Play },
  { id: 'reports',      label: 'Reports',         icon: BarChart2 },
] as const;

type TabId = typeof TABS[number]['id'];

// ---------------------------------------------------------------------------
// Helper: run status indicator
// ---------------------------------------------------------------------------

function RunStatusChip({ status }: { status: string }) {
  const map: Record<string, { label: string; icon: React.ElementType; cls: string }> = {
    running:   { label: 'Running',   icon: Loader2,       cls: 'text-blue-400 bg-blue-500/15 border-blue-500/40 [&_svg]:animate-spin' },
    completed: { label: 'Completed', icon: CheckCircle2,  cls: 'text-emerald-400 bg-emerald-500/15 border-emerald-500/40' },
    failed:    { label: 'Failed',    icon: XCircle,       cls: 'text-red-400 bg-red-500/15 border-red-500/40' },
    pending:   { label: 'Pending',   icon: Clock,         cls: 'text-muted-foreground bg-muted border-input' },
    paused:    { label: 'Paused',    icon: AlertTriangle, cls: 'text-amber-400 bg-amber-500/15 border-amber-400/40 [&_svg]:animate-pulse' },
  };
  const cfg = map[status] ?? map['pending'];
  const Icon = cfg.icon;
  return (
    <span className={cn('inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-medium', cfg.cls)}>
      <Icon className="h-3.5 w-3.5" />
      {cfg.label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Tab content
// ---------------------------------------------------------------------------

function TabContent({ tab, runId, overallStatus, runState, stateLoading, stateError, onResume, isResuming }: {
  tab: TabId; runId: string;
  overallStatus: string;
  runState: any; stateLoading: boolean; stateError: Error | null;
  onResume: () => void; isResuming: boolean;
}) {
  switch (tab) {
    case 'overview':
      return (
        <div className="space-y-6">
          {/* Failed / Paused state card with resume */}
          {(overallStatus === 'failed' || overallStatus === 'paused') && (
            <div className="rounded-xl border border-border bg-card p-5">
              <FailedStageCard
                runId={runId}
                state={runState ?? null}
                isLoading={stateLoading}
                error={stateError?.message ?? null}
                status={overallStatus}
                onResume={onResume}
                isResuming={isResuming}
              />
            </div>
          )}
          <LiveBrowserPreview runId={runId} />
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 rounded-xl border border-border bg-card p-5 space-y-4">
              <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                <Globe className="h-4 w-4 text-blue-400" /> Browser Activity
              </h3>
              <BrowserActivity runId={runId} />
            </div>
            <div className="rounded-xl border border-border bg-card h-[400px] flex flex-col overflow-hidden">
              <EventTimeline />
            </div>
          </div>
        </div>
      );

    case 'crawler':
      return (
        <StageRecoveryPanel runId={runId} stageId="crawler" stageLabel="Web Crawler" stageIcon={Globe} overallStatus={overallStatus}>
          <FullUICrawlerWorkspace runId={runId} />
        </StageRecoveryPanel>
      );

    case 'inventory':
      return (
        <StageRecoveryPanel runId={runId} stageId="inventory_aggregator" stageLabel="Inventory Aggregation" stageIcon={Layers} overallStatus={overallStatus}>
        <div className="space-y-4">
          {/* Application Inventory header */}
          <div className="flex items-center gap-3 px-4 py-3 rounded-xl border border-violet-500/40 bg-violet-500/10">
            <Layers className="h-5 w-5 text-violet-400 shrink-0" />
            <div>
              <p className="text-sm font-semibold text-violet-300">Application Inventory</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                Detailed breakdown of all discovered pages, components, and UI elements
              </p>
            </div>
          </div>

          <InventoryDetailView />

          {/* Module Detection */}
          <ModuleDetection />

          {/* Original tree (kept for compatibility) */}
          <div className="rounded-xl border border-border bg-card p-5">
            <h3 className="text-sm font-semibold text-foreground mb-4 flex items-center gap-2">
              <Box className="h-4 w-4 text-violet-400" /> Categorized View
            </h3>
            <InventoryTree />
          </div>
        </div>
        </StageRecoveryPanel>
      );

    case 'test-design':
      return (
        <StageRecoveryPanel runId={runId} stageId="test_design" stageLabel="Test Design" stageIcon={Bot} overallStatus={overallStatus}>
        <div className="space-y-4">
          {/* Live stats */}
          <LiveStats />

          {/* AI Test Plan Summary */}
          <TestPlanSummary />

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Left column: AI Thinking */}
            <div className="space-y-4">
              <div className="rounded-xl border border-border bg-card p-5 space-y-4">
                <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                  <Bot className="h-4 w-4 text-blue-400" /> AI Test Designer
                </h3>
                <AIThinkingPanel />
              </div>

              {/* AI Decision Log */}
              <AIDecisionLog />

              {/* LLM Activity (kept for token details) */}
              <div className="rounded-xl border border-border bg-card p-4">
                <h3 className="text-xs font-semibold text-muted-foreground flex items-center gap-2 mb-3">
                  <Cpu className="h-3.5 w-3.5 text-muted-foreground" /> LLM Call Details
                </h3>
                <LLMActivity />
              </div>
            </div>

            {/* Right column: Results */}
            <div className="space-y-4">
              {/* Module Detection */}
              <ModuleDetection />

              {/* Scenario Cards */}
              <div className="rounded-xl border border-border bg-card p-5 space-y-4">
                <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                  <ClipboardList className="h-4 w-4 text-emerald-400" /> Generated Scenarios
                </h3>
                <ScenarioCards />
                <TestPlanViewer />
              </div>
            </div>
          </div>
        </div>
        </StageRecoveryPanel>
      );

    case 'review':
      return (
        <StageRecoveryPanel runId={runId} stageId="human_review" stageLabel="Human Review" stageIcon={UserCheck} overallStatus={overallStatus}>
        <div className="w-full">
          <div className="rounded-xl border border-border bg-card p-6">
            <h3 className="text-sm font-semibold text-foreground mb-5 flex items-center gap-2">
              <UserCheck className="h-4 w-4 text-amber-400" /> Human Review
            </h3>
            <HumanReviewPanel runId={runId} />
          </div>
        </div>
        </StageRecoveryPanel>
      );

    case 'code':
      return (
        <StageRecoveryPanel runId={runId} stageId="code_generation" stageLabel="Code Generation" stageIcon={Code2} overallStatus={overallStatus}>
          <CodeGenWorkspace />
        </StageRecoveryPanel>
      );

    case 'execution':
      return (
        <StageRecoveryPanel runId={runId} stageId="execution" stageLabel="Test Execution" stageIcon={Play} overallStatus={overallStatus}>
        <div className="rounded-xl border border-border bg-card p-5 space-y-4">
          <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
            <Play className="h-4 w-4 text-emerald-400" /> Test Execution Monitor
          </h3>
          <ExecutionMonitor />
        </div>
        </StageRecoveryPanel>
      );

    case 'reports':
      return (
        <div className="rounded-xl border border-border bg-card p-5">
          <ExecutionReportPanel runId={runId} />
        </div>
      );

    default:
      return (
        <div className="flex items-center justify-center py-16 text-muted-foreground text-xs">
          Unknown tab: {tab}
        </div>
      );
  }
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function RunDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [activeTab, setActiveTab] = useState<TabId>('overview');
  const [isFullUIModal, setIsFullUIModal] = useState(false);

  // Initial metadata via REST (just for header display)
  const { data: run, isLoading: runLoading } = useRun(id);

  // Hydrate store from REST snapshot BEFORE SSE connects
  // Also used for resume support (stateLoading, stateError, runState)
  const hydrate = useWorkflowStore((s) => s.hydrate);
  const { data: runState, isLoading: stateLoading, error: stateError } = useRunState(id);
  const didHydrate = useRef<string | null>(null);
  useEffect(() => {
    if (runState && didHydrate.current !== id) {
      hydrate(runState);
      useWorkflowStore.getState().hydrateArtifacts(id);
      didHydrate.current = id;
    }
  }, [id, runState, hydrate]);

  // Connect SSE — appends new events on top of hydrated state
  const { connected, error: sseError } = useWorkflowSSE(id);

  // Pull live state from Zustand store
  const overallStatus  = useWorkflowStore((s) => s.overallStatus);
  const stages         = useWorkflowStore((s) => s.stages);
  const humanReview    = useWorkflowStore((s) => s.humanReviewRequired);

  const resumeRun = useResumeRun();
  const handleResume = () => resumeRun.mutate(id);

  // Auto-open failed stage tab
  const prevStatusRef = useRef(overallStatus);
  useEffect(() => {
    if (overallStatus === 'failed' && prevStatusRef.current !== 'failed' && runState) {
      const stageToTab: Record<string, TabId> = {
        trigger: 'overview',
        crawler: 'crawler',
        inventory_aggregator: 'inventory',
        test_design: 'test-design',
        human_review: 'review',
        code_generation: 'code',
        execution: 'execution',
      };
      const failedStage = (runState as any)?.failed_stage;
      if (failedStage && stageToTab[failedStage]) {
        setActiveTab(stageToTab[failedStage]);
      }
    }
    prevStatusRef.current = overallStatus;
  }, [overallStatus, runState]);

  // Auto-switch to Code Gen tab when generation starts (if user is on overview)
  const codeGenStage = stages.find((s) => s.id === 'code_generation');
  const didAutoSwitchToCode = useRef(false);
  useEffect(() => {
    if (
      codeGenStage?.status === 'running' &&
      activeTab === 'overview' &&
      !didAutoSwitchToCode.current
    ) {
      setActiveTab('code');
      didAutoSwitchToCode.current = true;
    }
  }, [codeGenStage?.status, activeTab]);

  const activeStage    = stages.find((s) => s.status === 'running' || s.status === 'waiting_for_user');

  const openSeparateWindow = () => {
    window.open(
      `/runs/${id}/live-preview`,
      `LivePreviewWindow_${id}`,
      'width=1280,height=850,resizable=yes,scrollbars=yes,status=no,toolbar=no,menubar=no'
    );
  };

  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* Full UI Modal Overlay */}
      {isFullUIModal && (
        <FullUICrawlerWorkspace runId={id} isModal onCloseModal={() => setIsFullUIModal(false)} />
      )}

      {/* ── Top nav bar ─────────────────────────────────────────────── */}
      <div className="sticky top-0 z-40 border-b border-border bg-background/90 backdrop-blur-xl">
        <div className="container flex items-center gap-4 py-3">
          {/* Back */}
          <Link
            href="/runs"
            className="flex items-center gap-1.5 text-muted-foreground hover:text-foreground transition-colors text-sm"
          >
            <ArrowLeft className="h-4 w-4" />
            <span className="hidden sm:inline">All Runs</span>
          </Link>

          <div className="h-4 w-px bg-secondary" />

          {/* Run ID */}
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-xs text-muted-foreground">Run</span>
            <span className="font-mono text-xs text-foreground truncate max-w-[120px] sm:max-w-none">
              {run?.run_id ?? id}
            </span>
          </div>

          {/* Live status & Popout Controls */}
          <div className="ml-auto flex items-center gap-3">
            {/* Full UI Mode Button */}
            <button
              onClick={() => setIsFullUIModal(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-violet-600/20 hover:bg-violet-600/35 border border-violet-500/40 text-violet-300 text-xs font-medium transition-all duration-150 shadow-sm"
              title="Expand Crawler to Full UI Screen Workspace"
            >
              <Maximize2 className="h-3.5 w-3.5 text-violet-400" />
              <span className="hidden sm:inline">Full UI Mode</span>
            </button>

            {/* Popout button */}
            <button
              onClick={openSeparateWindow}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-600/20 hover:bg-blue-600/35 border border-blue-500/40 text-blue-300 text-xs font-medium transition-all duration-150 shadow-sm"
              title="Open Live Crawler View in a separate standalone window"
            >
              <ExternalLink className="h-3.5 w-3.5 text-blue-400" />
              <span className="hidden sm:inline">Open Live Screen Separately</span>
              <span className="sm:hidden">Separately</span>
            </button>

            {/* SSE indicator */}
            <div className="flex items-center gap-1.5">
              {sseError ? (
                <WifiOff className="h-3.5 w-3.5 text-red-400" />
              ) : connected ? (
                <>
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
                  </span>
                  <span className="text-[10px] text-emerald-400 hidden sm:inline">Live</span>
                </>
              ) : (
                <Wifi className="h-3.5 w-3.5 text-muted-foreground animate-pulse" />
              )}
            </div>

            {/* Status chip — driven by SSE events, not REST polling */}
            <RunStatusChip status={overallStatus} />

            {/* Active stage label */}
            {activeStage && (
              <span className="hidden md:inline text-xs text-muted-foreground">
                {activeStage.label}
              </span>
            )}
          </div>
        </div>

        {/* Pipeline progress */}
        <div className="container py-4">
          <PipelineStages />
        </div>

        {/* Tabs */}
        <div className="container">
          <div className="flex gap-1 overflow-x-auto scrollbar-hide border-t border-border pt-1">
            {TABS.map((tab) => {
              const isReviewAlert = tab.id === 'review' && humanReview;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={cn(
                    'flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-t-md whitespace-nowrap transition-all duration-150 relative',
                    activeTab === tab.id
                      ? 'text-foreground bg-accent border-b-2 border-blue-500'
                      : 'text-muted-foreground hover:text-foreground hover:bg-accent/60',
                    isReviewAlert && 'text-amber-400 hover:text-amber-300'
                  )}
                >
                  <tab.icon className={cn('h-3.5 w-3.5', isReviewAlert && 'animate-pulse')} />
                  {tab.label}
                  {isReviewAlert && (
                    <span className="absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full bg-amber-400 animate-ping" />
                  )}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* ── Main content ────────────────────────────────────────────── */}
      <div className="container py-6">
        {runLoading && !run ? (
          // Minimal skeleton only for the very first load
          <div className="space-y-4">
            <div className="h-6 w-48 bg-muted rounded animate-pulse" />
            <div className="h-64 bg-muted rounded-xl animate-pulse" />
          </div>
        ) : (
          <TabContent tab={activeTab} runId={id} overallStatus={overallStatus} runState={runState ?? null} stateLoading={stateLoading} stateError={stateError as Error | null} onResume={handleResume} isResuming={resumeRun.isPending} />
        )}
      </div>
    </div>
  );
}
