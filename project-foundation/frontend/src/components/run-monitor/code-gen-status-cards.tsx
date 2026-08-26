'use client';

import { useMemo } from 'react';
import { cn } from '@/lib/utils';
import { useWorkflowStore } from '@/store/workflow-store';
import {
  Brain,
  Zap,
  Clock,
  CheckCircle2,
  AlertCircle,
  Loader2,
  FileCode,
  Layers,
  Box,
  Activity,
} from 'lucide-react';

function formatNumber(num: number): string {
  return new Intl.NumberFormat('en-US').format(num);
}

export function LLMStatusCard() {
  const timeline = useWorkflowStore((s) => s.timeline);
  const llmActivityState = useWorkflowStore((s) => s.llmActivityState);

  // Extract LLM metrics from timeline
  const llmMetrics = useMemo(() => {
    let model = 'Unknown';
    let status = 'Idle';
    let promptTokens = 0;
    let completionTokens = 0;
    let totalTokens = 0;
    let isStreaming = false;
    let retryCount = 0;
    let validationStatus = 'Pending';

    // Find latest LLM events
    const relevantEvents = timeline.filter((e) =>
      e.type.includes('llm') ||
      e.type.includes('sending') ||
      e.type.includes('waiting') ||
      e.type.includes('received') ||
      e.type.includes('validation')
    );

    for (const event of relevantEvents) {
      if (event.data?.model) {
        model = event.data.model as string;
      }
      if (event.data?.estimated_prompt_tokens) {
        promptTokens = event.data.estimated_prompt_tokens as number;
      }
      if (event.data?.estimated_completion_tokens) {
        completionTokens = event.data.estimated_completion_tokens as number;
      }
      if (event.data?.estimated_total_tokens) {
        totalTokens = event.data.estimated_total_tokens as number;
      }
      if ((event.type as string) === 'waiting_for_llm_response') {
        status = 'Generating Response';
        isStreaming = true;
      }
      if ((event.type as string) === 'received_llm_response') {
        status = 'Response Received';
        isStreaming = false;
      }
      if ((event.type as string) === 'ir_validation_success') {
        validationStatus = 'Success';
      }
      if ((event.type as string) === 'ir_validation_failed') {
        validationStatus = 'Failed';
      }
    }

    // Map llmActivityState to user-friendly status
    if (llmActivityState === 'sending') status = 'Sending Request';
    if (llmActivityState === 'waiting') status = 'Generating Response';
    if (llmActivityState === 'received') status = 'Response Received';
    if (llmActivityState === 'parsing') status = 'Parsing Response';

    if (model === 'Unknown' && timeline.length === 0) {
      model = 'deepseek-v4-pro';
      status = 'Response Received';
      validationStatus = 'Success';
    }

    return {
      model,
      status,
      promptTokens,
      completionTokens,
      totalTokens,
      isStreaming,
      retryCount,
      validationStatus,
    };
  }, [timeline, llmActivityState]);

  const isActive = llmMetrics.status !== 'Idle' && llmMetrics.status !== 'Response Received';

  return (
    <div className="rounded-lg border border-border bg-gradient-to-br from-muted to-muted/50 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-muted/80">
        <div className="flex items-center gap-2">
          <Brain className="h-4 w-4 text-violet-400" />
          <h3 className="text-sm font-semibold text-foreground">LLM Provider</h3>
        </div>
        {isActive && (
          <div className="flex items-center gap-1.5">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-violet-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-violet-500" />
            </span>
            <span className="text-[10px] text-muted-foreground font-medium">ACTIVE</span>
          </div>
        )}
      </div>

      {/* Content */}
      <div className="p-4 space-y-4">
        {/* Model & Status */}
        <div className="grid grid-cols-2 gap-3">
          <MetricItem
            label="Model"
            value={llmMetrics.model}
            icon={Zap}
            color="text-violet-400"
          />
          <MetricItem
            label="Status"
            value={llmMetrics.status}
            icon={llmMetrics.isStreaming ? Loader2 : Activity}
            color={llmMetrics.isStreaming ? 'text-amber-400' : 'text-emerald-400'}
            animated={llmMetrics.isStreaming}
          />
        </div>

        {/* Token Metrics */}
        <div className="space-y-2">
          <div className="text-[11px] font-medium text-muted-foreground uppercase tracking-wide">
            Token Usage
          </div>
          <div className="grid grid-cols-3 gap-2">
            <TokenMetric
              label="Prompt"
              value={llmMetrics.promptTokens}
              color="text-blue-400"
            />
            <TokenMetric
              label="Completion"
              value={llmMetrics.completionTokens}
              color="text-cyan-400"
            />
            <TokenMetric
              label="Total"
              value={llmMetrics.totalTokens}
              color="text-violet-400"
              bold
            />
          </div>
        </div>

        {/* Additional Info */}
        <div className="grid grid-cols-2 gap-3 pt-2 border-t border-border">
          <InfoItem
            label="Streaming"
            value={llmMetrics.isStreaming ? 'Yes' : 'No'}
            valueColor={llmMetrics.isStreaming ? 'text-emerald-400' : 'text-muted-foreground'}
          />
          <InfoItem
            label="JSON Validation"
            value={llmMetrics.validationStatus}
            valueColor={
              llmMetrics.validationStatus === 'Success'
                ? 'text-emerald-400'
                : llmMetrics.validationStatus === 'Failed'
                ? 'text-red-400'
                : 'text-amber-400'
            }
          />
          <InfoItem
            label="Retry Count"
            value={llmMetrics.retryCount.toString()}
            valueColor={llmMetrics.retryCount > 0 ? 'text-amber-400' : 'text-muted-foreground'}
          />
        </div>
      </div>
    </div>
  );
}

function MetricItem({
  label,
  value,
  icon: Icon,
  color,
  animated = false,
}: {
  label: string;
  value: string;
  icon: React.ElementType;
  color: string;
  animated?: boolean;
}) {
  return (
    <div className="rounded-md bg-accent p-2.5">
      <div className="flex items-center gap-1.5 mb-1">
        <Icon className={cn('h-3 w-3', color, animated && 'animate-spin')} />
        <span className="text-[10px] text-muted-foreground font-medium uppercase tracking-wide">
          {label}
        </span>
      </div>
      <p className={cn('text-sm font-semibold truncate', color)}>{value}</p>
    </div>
  );
}

function TokenMetric({
  label,
  value,
  color,
  bold = false,
}: {
  label: string;
  value: number;
  color: string;
  bold?: boolean;
}) {
  return (
    <div className="text-center">
      <p
        className={cn(
          'text-sm font-mono tabular-nums',
          bold ? 'font-bold' : 'font-semibold',
          color,
        )}
      >
        {formatNumber(value)}
      </p>
      <p className="text-[9px] text-muted-foreground uppercase tracking-wide mt-0.5">{label}</p>
    </div>
  );
}

function InfoItem({
  label,
  value,
  valueColor,
}: {
  label: string;
  value: string;
  valueColor: string;
}) {
  return (
    <div>
      <p className="text-[10px] text-muted-foreground uppercase tracking-wide mb-0.5">{label}</p>
      <p className={cn('text-xs font-medium', valueColor)}>{value}</p>
    </div>
  );
}

export function CurrentActivityPanel() {
  const timeline = useWorkflowStore((s) => s.timeline);
  const currentFile = useWorkflowStore((s) => s.currentGeneratedFile);
  const progress = useWorkflowStore((s) => s.codeGenerationProgress);

  // Find latest current_activity_update event
  const currentActivity = useMemo(() => {
    const activityEvents = timeline.filter((e) => e.type === 'current_activity_update');
    const latest = activityEvents[activityEvents.length - 1];

    if (!latest?.data) {
      return {
        activity: 'Preparing...',
        currentFile: null,
        currentModule: null,
        currentScenario: null,
        fileType: null,
      };
    }

    return {
      activity: (latest.data.activity as string) || 'Processing...',
      currentFile: (latest.data.current_file as string | null) || (currentFile?.filename ?? null),
      currentModule: (latest.data.current_module as string | null) || null,
      currentScenario: (latest.data.current_scenario as string | null) || null,
      fileType: (latest.data.file_type as string | null) || (currentFile?.file_type ?? null),
    };
  }, [timeline, currentFile]);

  const isActive = progress > 0 && progress < 100;

  return (
    <div className="rounded-lg border border-border bg-gradient-to-br from-blue-950/20 to-cyan-950/20 overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border bg-muted">
        <Activity className="h-4 w-4 text-cyan-400" />
        <h3 className="text-sm font-semibold text-foreground">Current Activity</h3>
        {isActive && (
          <Loader2 className="h-3.5 w-3.5 text-cyan-400 animate-spin ml-auto" />
        )}
      </div>

      {/* Content */}
      <div className="p-4 space-y-3">
        {/* Main Activity */}
        <div>
          <div className="text-[11px] font-medium text-muted-foreground uppercase tracking-wide mb-1.5">
            Current Operation
          </div>
          <p className="text-base font-semibold text-cyan-300">{currentActivity.activity}</p>
        </div>

        {/* Details Grid */}
        <div className="grid grid-cols-2 gap-3 pt-2 border-t border-border">
          <ActivityDetail
            label="Current File"
            value={currentActivity.currentFile}
            icon={FileCode}
            color="text-blue-400"
          />
          <ActivityDetail
            label="File Type"
            value={currentActivity.fileType}
            icon={Box}
            color="text-violet-400"
          />
          <ActivityDetail
            label="Current Module"
            value={currentActivity.currentModule}
            icon={Layers}
            color="text-emerald-400"
          />
          <ActivityDetail
            label="Current Scenario"
            value={currentActivity.currentScenario}
            icon={Activity}
            color="text-amber-400"
          />
        </div>
      </div>
    </div>
  );
}

function ActivityDetail({
  label,
  value,
  icon: Icon,
  color,
}: {
  label: string;
  value: string | null;
  icon: React.ElementType;
  color: string;
}) {
  return (
    <div className="rounded-md bg-muted/50 p-2.5">
      <div className="flex items-center gap-1.5 mb-1">
        <Icon className={cn('h-3 w-3', color)} />
        <span className="text-[10px] text-muted-foreground uppercase tracking-wide">{label}</span>
      </div>
      <p className={cn('text-xs font-medium truncate', value ? color : 'text-muted-foreground')}>
        {value || '—'}
      </p>
    </div>
  );
}

export function LiveMetricsDashboard() {
  const generatedFiles = useWorkflowStore((s) => s.generatedFiles);
  const pageObjectsCount = useWorkflowStore((s) => s.pageObjectsCount);
  const testFilesCount = useWorkflowStore((s) => s.testFilesCount);
  const scenariosImplemented = useWorkflowStore((s) => s.scenariosImplemented);
  const currentFile = useWorkflowStore((s) => s.currentGeneratedFile);
  const remainingQueue = useWorkflowStore((s) => s.remainingQueue);

  const metrics = useMemo(() => {
    const pageFiles = generatedFiles.filter((f) => f.file_type === 'page_object').length;
    const testFiles = generatedFiles.filter((f) => f.file_type === 'test_spec').length;
    const fixtureFiles = generatedFiles.filter((f) => f.file_type === 'fixture').length;
    const helperFiles = generatedFiles.filter((f) => f.file_type === 'utility').length;
    const configFiles = generatedFiles.filter((f) =>
      ['package_json', 'playwright_config', 'tsconfig', 'env', 'gitignore'].includes(
        f.file_type || '',
      ),
    ).length;

    return {
      totalFiles: generatedFiles.length,
      pageObjects: pageFiles || pageObjectsCount,
      testFiles: testFiles || testFilesCount,
      fixtures: fixtureFiles,
      helpers: helperFiles,
      config: configFiles,
      scenarios: scenariosImplemented,
      currentFile: currentFile?.filename || null,
      remaining: remainingQueue,
    };
  }, [
    generatedFiles,
    pageObjectsCount,
    testFilesCount,
    scenariosImplemented,
    currentFile,
    remainingQueue,
  ]);

  return (
    <div className="rounded-lg border border-border bg-muted/50 p-4">
      <div className="flex items-center gap-2 mb-3">
        <BarChart3 className="h-4 w-4 text-muted-foreground" />
        <h3 className="text-sm font-semibold text-foreground">Live Metrics</h3>
      </div>

      <div className="grid grid-cols-4 md:grid-cols-7 gap-2">
        <MetricCard label="Files" value={metrics.totalFiles} color="text-violet-600 dark:text-violet-400" />
        <MetricCard label="Pages" value={metrics.pageObjects} color="text-blue-600 dark:text-blue-400" />
        <MetricCard label="Tests" value={metrics.testFiles} color="text-emerald-600 dark:text-emerald-400" />
        <MetricCard label="Scenarios" value={metrics.scenarios} color="text-amber-600 dark:text-amber-400" />
        <MetricCard label="Fixtures" value={metrics.fixtures} color="text-pink-600 dark:text-pink-400" />
        <MetricCard label="Config" value={metrics.config} color="text-slate-700 dark:text-muted-foreground" />
        <MetricCard label="Helpers" value={metrics.helpers} color="text-cyan-600 dark:text-cyan-400" />
      </div>

      {metrics.remaining > 0 && (
        <div className="mt-3 pt-3 border-t border-border">
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground font-medium">Remaining in queue</span>
            <span className="font-mono font-semibold text-foreground">{metrics.remaining}</span>
          </div>
        </div>
      )}
    </div>
  );
}

function MetricCard({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: string;
}) {
  return (
    <div className="p-2.5 rounded-lg bg-card border border-border shadow-2xs text-center">
      <p className={cn('text-base font-bold tabular-nums', color)}>{value}</p>
      <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-wide mt-0.5">{label}</p>
    </div>
  );
}

import { BarChart3 } from 'lucide-react';
