'use client';

/**
 * PipelineStages — Horizontal animated workflow pipeline
 *
 * Renders each workflow stage as a step node with color-coded status,
 * animated pulse for running stages, and connectors between nodes.
 * State comes entirely from the Zustand workflow store (built from SSE events).
 */

import { cn } from '@/lib/utils';
import { useWorkflowStore, PipelineStage, StageStatus } from '@/store/workflow-store';
import {
  CheckCircle2,
  Circle,
  Loader2,
  XCircle,
  AlertTriangle,
  SkipForward,
  GitBranch,
  Globe,
  LayoutList,
  FileText,
  UserCheck,
  Code2,
  Play,
  BarChart3,
} from 'lucide-react';

const STAGE_ICONS: Record<string, React.ElementType> = {
  trigger:         GitBranch,
  crawler:         Globe,
  inventory:       LayoutList,
  test_design:     FileText,
  human_review:    UserCheck,
  code_generation: Code2,
  execution:       Play,
  report:          BarChart3,
};

interface StatusConfig {
  icon: React.ElementType;
  ring: string;
  bg: string;
  iconColor: string;
  labelColor: string;
  dot: string;
  animate?: boolean;
}

function getStatusConfig(status: StageStatus): StatusConfig {
  switch (status) {
    case 'running':
      return {
        icon: Loader2,
        ring: 'ring-2 ring-blue-500 ring-offset-2 ring-offset-background',
        bg: 'bg-blue-500/15 border-blue-500',
        iconColor: 'text-blue-400 animate-spin',
        labelColor: 'text-blue-400 font-semibold',
        dot: 'bg-blue-500 animate-pulse',
        animate: true,
      };
    case 'completed':
      return {
        icon: CheckCircle2,
        ring: '',
        bg: 'bg-emerald-500/15 border-emerald-500/50',
        iconColor: 'text-emerald-400',
        labelColor: 'text-emerald-400',
        dot: 'bg-emerald-500',
      };
    case 'failed':
      return {
        icon: XCircle,
        ring: 'ring-2 ring-red-500/60 ring-offset-1 ring-offset-background',
        bg: 'bg-red-500/15 border-red-500/60',
        iconColor: 'text-red-400',
        labelColor: 'text-red-400',
        dot: 'bg-red-500',
      };
    case 'waiting_for_user':
      return {
        icon: AlertTriangle,
        ring: 'ring-2 ring-amber-400 ring-offset-2 ring-offset-background',
        bg: 'bg-amber-500/15 border-amber-400/70',
        iconColor: 'text-amber-400 animate-pulse',
        labelColor: 'text-amber-400 font-semibold',
        dot: 'bg-amber-400 animate-ping',
        animate: true,
      };
    case 'skipped':
      return {
        icon: SkipForward,
        ring: '',
        bg: 'bg-zinc-800 border-zinc-700',
        iconColor: 'text-zinc-500',
        labelColor: 'text-zinc-500',
        dot: 'bg-zinc-600',
      };
    default: // pending
      return {
        icon: Circle,
        ring: '',
        bg: 'bg-zinc-900 border-zinc-700',
        iconColor: 'text-zinc-600',
        labelColor: 'text-zinc-500',
        dot: 'bg-zinc-700',
      };
  }
}

function StageNode({ stage, isLast }: { stage: PipelineStage; isLast: boolean }) {
  const cfg = getStatusConfig(stage.status);
  const Icon = STAGE_ICONS[stage.id] ?? Circle;
  const StatusIcon = cfg.icon;

  return (
    <div className="flex items-center">
      {/* Node */}
      <div className="flex flex-col items-center gap-1.5">
        {/* Circle */}
        <div
          className={cn(
            'relative flex h-11 w-11 items-center justify-center rounded-full border-2 transition-all duration-500',
            cfg.bg,
            cfg.ring
          )}
        >
          {/* Pulsing ring for running/waiting */}
          {cfg.animate && (
            <span
              className={cn(
                'absolute inset-0 rounded-full opacity-40 animate-ping',
                stage.status === 'running' ? 'bg-blue-500' : 'bg-amber-400'
              )}
            />
          )}
          <Icon className={cn('h-5 w-5', cfg.iconColor)} />

          {/* Status badge */}
          <span
            className={cn(
              'absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full border border-background',
              cfg.dot
            )}
          />
        </div>

        {/* Label */}
        <span
          className={cn(
            'text-[10px] text-center leading-tight whitespace-nowrap transition-colors duration-300',
            cfg.labelColor
          )}
        >
          {stage.label}
        </span>

        {/* Status text */}
        <span className="text-[9px] text-zinc-600 capitalize">
          {stage.status.replace('_', ' ')}
        </span>
      </div>

      {/* Connector */}
      {!isLast && (
        <div
          className={cn(
            'h-0.5 w-10 sm:w-14 md:w-20 flex-shrink-0 mx-1 rounded-full transition-all duration-500',
            stage.status === 'completed'
              ? 'bg-emerald-500/60'
              : stage.status === 'running' || stage.status === 'waiting_for_user'
              ? 'bg-blue-500/40'
              : 'bg-zinc-800'
          )}
        />
      )}
    </div>
  );
}

export function PipelineStages() {
  const stages = useWorkflowStore((s) => s.stages);
  const overall = useWorkflowStore((s) => s.overallStatus);

  const completedCount = stages.filter((s) => s.status === 'completed').length;
  const progress = Math.round((completedCount / stages.length) * 100);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div
            className={cn(
              'h-2 w-2 rounded-full',
              overall === 'running'          && 'bg-blue-500 animate-pulse',
              overall === 'completed'        && 'bg-emerald-500',
              overall === 'failed'           && 'bg-red-500',
              overall === 'paused'           && 'bg-amber-400 animate-pulse',
              overall === 'idle'             && 'bg-zinc-600',
            )}
          />
          <span className="text-sm font-medium text-foreground/80">
            {overall === 'running'   && 'Workflow Running'}
            {overall === 'completed' && 'Workflow Completed'}
            {overall === 'failed'    && 'Workflow Failed'}
            {overall === 'paused'    && 'Paused — Awaiting Review'}
            {overall === 'idle'      && 'Workflow Idle'}
          </span>
        </div>
        <span className="text-xs text-zinc-500">
          {completedCount}/{stages.length} stages · {progress}%
        </span>
      </div>

      {/* Progress bar */}
      <div className="h-1 rounded-full bg-zinc-800 overflow-hidden">
        <div
          className={cn(
            'h-full rounded-full transition-all duration-700',
            overall === 'failed'    ? 'bg-red-500' :
            overall === 'completed' ? 'bg-emerald-500' :
            overall === 'paused'    ? 'bg-amber-400' :
            'bg-blue-500'
          )}
          style={{ width: `${progress}%` }}
        />
      </div>

      {/* Stage nodes */}
      <div className="flex items-start overflow-x-auto pb-2 scrollbar-hide">
        {stages.map((stage, idx) => (
          <StageNode key={stage.id} stage={stage} isLast={idx === stages.length - 1} />
        ))}
      </div>
    </div>
  );
}
