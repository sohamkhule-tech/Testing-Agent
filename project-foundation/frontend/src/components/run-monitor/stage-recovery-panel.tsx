'use client';

import { useState } from 'react';
import { cn } from '@/lib/utils';
import { useRunState, useResumeRun } from '@/hooks/use-api';
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Copy,
  Download,
  Loader2,
  Play,
  RefreshCw,
  SkipForward,
  Terminal,
  ThumbsDown,
  XCircle,
  Bug,
  ChevronDown,
  ChevronRight,
  FileText,
  Edit3,
  Eye,
} from 'lucide-react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface StageRecoveryPanelProps {
  runId: string;
  stageId: string;
  stageLabel: string;
  stageIcon: React.ElementType;
  overallStatus: string;
  actions?: React.ReactNode;
  children?: React.ReactNode;
}

interface StageFailureData {
  failed_stage: string | null;
  failure_reason: string | null;
  failure_stacktrace: string[];
  stage_logs: string[];
  retry_count: number;
  resume_allowed: boolean;
  completed_stages: string[];
  status: string;
}

// ---------------------------------------------------------------------------
// Stage-specific actions
// ---------------------------------------------------------------------------

const STAGE_RECOVERY_ACTIONS: Record<string, string[]> = {
  trigger: ['Retry Setup', 'Edit Configuration', 'Cancel Workflow'],
  crawler: ['Retry Crawl', 'Change URL', 'View Screenshots', 'Browser Logs'],
  inventory_aggregator: ['Retry Inventory', 'View Crawl Data'],
  test_design: ['Regenerate Test Plan', 'Edit AI Prompt', 'Download Current Plan'],
  human_review: ['Approve', 'Reject', 'Request Regeneration'],
  code_generation: ['Retry Code Generation', 'View Partial Files', 'Download Generated Code'],
  execution: ['Retry Execution', 'Run Failed Tests Only', 'Download Playwright Report'],
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function StageRecoveryPanel({ runId, stageId, stageLabel, stageIcon: Icon, overallStatus, actions, children }: StageRecoveryPanelProps) {
  const { data: failureData, isLoading: failureLoading } = useRunState(overallStatus === 'failed' ? runId : '');
  const resumeRun = useResumeRun();

  const [showStacktrace, setShowStacktrace] = useState(false);
  const [showLogs, setShowLogs] = useState(false);
  const [copied, setCopied] = useState(false);

  const isFailed = overallStatus === 'failed';
  const failure = failureData as StageFailureData | null;
  const stageFailed = failure?.failed_stage === stageId;
  const completedBeforeFailure = failure?.completed_stages?.includes(stageId);
  const isNextStage = failure?.completed_stages?.length && !completedBeforeFailure;

  const handleCopyError = () => {
    if (failure?.failure_reason) {
      navigator.clipboard.writeText(failure.failure_reason);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleRetry = () => resumeRun.mutate(runId);

  // Show recovery panel when this stage specifically failed
  if (isFailed && stageFailed) {
    return (
      <div className="space-y-4">
        {/* Failure banner */}
        <div className="flex items-start gap-3 px-4 py-3 rounded-xl border border-red-500/40 bg-red-500/10">
          <XCircle className="h-5 w-5 text-red-400 shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <Icon className="h-4 w-4 text-red-400" />
              <p className="text-sm font-semibold text-red-300">{stageLabel} Failed</p>
            </div>
            {failureLoading ? (
              <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground">
                <Loader2 className="h-3 w-3 animate-spin" />
                Loading failure details...
              </div>
            ) : (
              <>
                {failure?.failure_reason && (
                  <p className="text-xs text-red-400/80 mt-1 break-all line-clamp-3">{failure.failure_reason}</p>
                )}
                <div className="flex items-center gap-3 mt-2 text-[10px] text-muted-foreground">
                  {failure?.retry_count !== undefined && failure.retry_count > 0 && (
                    <span>Retried {failure.retry_count} time{failure.retry_count !== 1 ? 's' : ''}</span>
                  )}
                </div>
              </>
            )}
          </div>
        </div>

        {/* Stacktrace (collapsible) */}
        {failure?.failure_stacktrace?.length! > 0 && (
          <div className="rounded-lg border border-border overflow-hidden">
            <button
              onClick={() => setShowStacktrace(!showStacktrace)}
              className="flex items-center gap-2 w-full px-3 py-2 text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              {showStacktrace ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
              <Bug className="h-3 w-3" />
              Full Stack Trace
            </button>
            {showStacktrace && (
              <div className="px-3 pb-3 font-mono text-[10px] text-muted-foreground max-h-48 overflow-y-auto space-y-0.5 bg-card">
                {failure!.failure_stacktrace.map((line, i) => (
                  <div key={i} className="text-red-400/70">{line}</div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Stage logs (collapsible) */}
        {failure?.stage_logs?.length! > 0 && (
          <div className="rounded-lg border border-border overflow-hidden">
            <button
              onClick={() => setShowLogs(!showLogs)}
              className="flex items-center gap-2 w-full px-3 py-2 text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              {showLogs ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
              <Terminal className="h-3 w-3" />
              Stage Logs ({failure!.stage_logs.length} lines)
            </button>
            {showLogs && (
              <div className="px-3 pb-3 font-mono text-[10px] text-muted-foreground max-h-48 overflow-y-auto space-y-0.5 bg-card">
                {failure!.stage_logs.map((line, i) => (
                  <div key={i}>{line}</div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Actions */}
        <div className="space-y-2">
          <div className="flex gap-2">
            <button
              onClick={handleRetry}
              disabled={resumeRun.isPending}
              className="flex-1 flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg bg-amber-600 hover:bg-amber-500 text-white text-xs font-semibold transition-colors disabled:opacity-50"
            >
              {resumeRun.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
              Retry {stageLabel}
            </button>
            <button
              onClick={handleCopyError}
              className="flex items-center justify-center gap-1.5 px-3 py-2.5 rounded-lg bg-muted border border-input text-foreground text-xs font-medium hover:bg-secondary transition-colors"
            >
              {copied ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
              {copied ? 'Copied' : 'Copy Error'}
            </button>
          </div>

          {/* Stage-specific actions */}
          {STAGE_RECOVERY_ACTIONS[stageId] && (
            <div className="flex flex-wrap gap-1">
              {STAGE_RECOVERY_ACTIONS[stageId].map((action) => (
                <button
                  key={action}
                  disabled
                  className="px-2 py-1 rounded text-[10px] bg-accent border border-border text-muted-foreground cursor-not-allowed"
                >
                  {action}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  }

  // When the run failed but this stage was already completed, keep its content
  // (e.g. generated project/code) visible and mark the later failure, rather
  // than replacing valid previous-stage data with an empty placeholder.
  if (isFailed && completedBeforeFailure) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 text-xs">
          <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
          <span className="font-medium text-emerald-300">{stageLabel} completed successfully</span>
          <span className="text-muted-foreground">· Workflow failed at a later stage</span>
        </div>
        {children}
      </div>
    );
  }

  // Normal content (passed via children)
  return <>{children}</>;
}
