'use client';

import { useState } from 'react';
import { cn } from '@/lib/utils';
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Download,
  ExternalLink,
  Loader2,
  Play,
  RefreshCw,
  XCircle,
  Clock,
  FileText,
  FileSpreadsheet,
  Eye,
  Layers,
  ScrollText,
  Code2,
  TestTube,
  Bot,
} from 'lucide-react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface RunState {
  run_id: string;
  status: string;
  current_stage: string | null;
  completed_stages: string[];
  last_completed_stage: string | null;
  failed_stage: string | null;
  next_stage: string | null;
  resume_allowed: boolean;
  artifact_paths: Record<string, string>;
  stage_logs: Record<string, string[]>;
  last_error: string | null;
}

interface FailedStageCardProps {
  runId: string;
  state: RunState | null;
  isLoading: boolean;
  error: string | null;
  status: string;
  onResume: () => void;
  isResuming: boolean;
}

// ---------------------------------------------------------------------------
// Stage metadata
// ---------------------------------------------------------------------------

const STAGE_META: Record<string, { label: string; icon: React.ElementType; color: string }> = {
  trigger:              { label: 'Trigger / Setup',     icon: Bot,             color: 'text-blue-400' },
  crawler:              { label: 'Web Crawler',         icon: Eye,             color: 'text-purple-400' },
  inventory_aggregator: { label: 'Inventory',           icon: Layers,          color: 'text-cyan-400' },
  test_design:          { label: 'Test Design',         icon: ScrollText,      color: 'text-amber-400' },
  human_review:         { label: 'Human Review',        icon: CheckCircle2,    color: 'text-emerald-400' },
  code_generation:      { label: 'Code Generation',     icon: Code2,           color: 'text-indigo-400' },
  execution:            { label: 'Execution',            icon: TestTube,        color: 'text-rose-400' },
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function FailedStageCard({ runId, state, isLoading, error, status, onResume, isResuming }: FailedStageCardProps) {
  const [showLogs, setShowLogs] = useState(false);
  const [expandedStage, setExpandedStage] = useState<string | null>(null);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8 text-zinc-500 text-xs gap-2">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading run state...
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center py-8 text-red-400 text-xs gap-2">
        <XCircle className="h-4 w-4" />
        Failed to load run state: {error}
      </div>
    );
  }

  if (!state) return null;

  const isFailed = status === 'failed';
  const isPaused = status === 'paused';
  const canResume = state.resume_allowed && (isFailed || isPaused);

  const completedMap = new Map(state.completed_stages.map((s) => [s, true]));

  const allStages = ['trigger', 'crawler', 'inventory_aggregator', 'test_design', 'human_review', 'code_generation', 'execution'] as const;

  const failedStageLabel = state.failed_stage
    ? (STAGE_META[state.failed_stage]?.label || state.failed_stage)
    : null;

  return (
    <div className="space-y-4">
      {/* Failure banner */}
      {isFailed && (
        <div className="flex items-start gap-3 px-4 py-3 rounded-xl border border-red-500/40 bg-red-500/10">
          <XCircle className="h-5 w-5 text-red-400 shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-red-300">Workflow Failed</p>
            {failedStageLabel && (
              <p className="text-xs text-zinc-400 mt-0.5">
                Failed at: <span className="text-red-400 font-medium">{failedStageLabel}</span>
              </p>
            )}
            {state.last_error && (
              <p className="text-xs text-red-400/70 mt-1 break-all line-clamp-2">{state.last_error}</p>
            )}
          </div>
        </div>
      )}

      {/* Stage timeline */}
      <div className="space-y-1">
        <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold">Pipeline Stages</p>
        <div className="rounded-lg border border-zinc-800 overflow-hidden">
          {allStages.map((stage, i) => {
            const meta = STAGE_META[stage];
            const Icon = meta.icon;
            const isCompleted = completedMap.has(stage);
            const isFailed = state.failed_stage === stage;
            const isCurrent = state.next_stage === stage;
            const isExpanded = expandedStage === stage;
            const logs = state.stage_logs?.[stage] || [];

            return (
              <div key={stage}>
                <div
                  className={cn(
                    'flex items-center gap-3 px-3 py-2 cursor-pointer transition-colors hover:bg-zinc-800/50',
                    isFailed && 'bg-red-500/10',
                    isCurrent && 'bg-amber-500/5',
                    i > 0 && 'border-t border-zinc-800',
                  )}
                  onClick={() => setExpandedStage(isExpanded ? null : stage)}
                >
                  <div className={cn(
                    'h-6 w-6 rounded-full flex items-center justify-center shrink-0',
                    isCompleted && 'bg-emerald-500/20',
                    isFailed && 'bg-red-500/20',
                    isCurrent && 'bg-amber-500/20',
                    !isCompleted && !isFailed && !isCurrent && 'bg-zinc-800',
                  )}>
                    {isCompleted ? (
                      <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                    ) : isFailed ? (
                      <XCircle className="h-3.5 w-3.5 text-red-400" />
                    ) : isCurrent ? (
                      <Clock className="h-3.5 w-3.5 text-amber-400" />
                    ) : (
                      <Icon className="h-3 w-3 text-zinc-600" />
                    )}
                  </div>
                  <span className={cn(
                    'flex-1 text-xs',
                    isCompleted && 'text-zinc-300',
                    isFailed && 'text-red-400 font-medium',
                    isCurrent && 'text-amber-400',
                    !isCompleted && !isFailed && !isCurrent && 'text-zinc-600',
                  )}>
                    {meta.label}
                  </span>
                  {isCompleted && state.artifact_paths?.[stage] && (
                    <span className="text-[9px] text-zinc-500">Artifact saved</span>
                  )}
                  {logs.length > 0 && (
                    <span className="text-[9px] text-zinc-500">{logs.length} log{logs.length !== 1 ? 's' : ''}</span>
                  )}
                  <span className="text-zinc-600">
                    {isExpanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                  </span>
                </div>
                {isExpanded && (
                  <div className="px-4 py-2 border-t border-zinc-800 bg-zinc-900/50 space-y-1">
                    {isCompleted && state.artifact_paths?.[stage] && (
                      <div className="flex items-center gap-2 text-xs">
                        <FileText className="h-3 w-3 text-zinc-500" />
                        <span className="text-zinc-500">Artifact:</span>
                        <span className="text-zinc-400 font-mono text-[10px] truncate">{state.artifact_paths[stage]}</span>
                      </div>
                    )}
                    {logs.length > 0 && (
                      <div className="text-[10px] font-mono text-zinc-400 max-h-32 overflow-y-auto space-y-0.5 pt-1">
                        {logs.map((l, i) => (
                          <div key={i} className="text-zinc-500">  {l}</div>
                        ))}
                      </div>
                    )}
                    {!isCompleted && !isFailed && !logs.length && (
                      <p className="text-[10px] text-zinc-600 italic">No data available</p>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-3">
        {canResume && (
          <button
            onClick={onResume}
            disabled={isResuming}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-amber-600 hover:bg-amber-500 text-white font-semibold text-sm transition-colors disabled:opacity-50"
          >
            {isResuming ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            Resume from {failedStageLabel || state.next_stage || 'Last Failed Stage'}
          </button>
        )}
        <button
          disabled
          className="flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-zinc-800 border border-zinc-700 text-zinc-500 text-sm font-medium cursor-not-allowed"
        >
          <Download className="h-4 w-4" />
          Download Logs
        </button>
      </div>

      {/* Resume info */}
      {canResume && (
        <p className="text-[10px] text-zinc-500 text-center">
          Completed stages will be preserved and skipped. Only unfinished stages will execute.
        </p>
      )}
    </div>
  );
}
