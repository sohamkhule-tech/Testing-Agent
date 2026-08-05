'use client';

import Link from 'next/link';
import {
  ArrowLeft, Globe, Clock, Trash2, Play, Loader2, CheckCircle,
  ExternalLink, Globe2, Layers, Bot, UserCheck, Code2, FlaskConical, BarChart3, Zap,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { StatusBadge } from '@/components/status-badge';
import { Badge } from '@/components/ui/badge';
import { formatDateTime, cn } from '@/lib/utils';
import type { TestRun, Project, WorkflowPhase } from '@/types/api';

// Maps current_phase to a human-readable button label, icon, and colour
const PHASE_CTA: Record<WorkflowPhase, { label: string; Icon: React.ElementType; color: string }> = {
  trigger:         { label: 'View Run Setup',           Icon: Zap,          color: 'bg-zinc-700 hover:bg-zinc-600' },
  crawler:         { label: 'Open Live Crawler Screen', Icon: Globe2,       color: 'bg-blue-600 hover:bg-blue-500' },
  inventory:       { label: 'View Inventory Analysis',  Icon: Layers,       color: 'bg-violet-600 hover:bg-violet-500' },
  test_design:     { label: 'View AI Test Design',      Icon: Bot,          color: 'bg-indigo-600 hover:bg-indigo-500' },
  human_review:    { label: 'Open Human Review',        Icon: UserCheck,    color: 'bg-amber-600 hover:bg-amber-500' },
  code_generation: { label: 'View Code Generation',     Icon: Code2,        color: 'bg-pink-600 hover:bg-pink-500' },
  execution:       { label: 'View Test Execution',      Icon: FlaskConical, color: 'bg-emerald-600 hover:bg-emerald-500' },
  reporting:       { label: 'View Report',              Icon: BarChart3,    color: 'bg-teal-600 hover:bg-teal-500' },
};

export function ProjectHeader({
  project, latestRun, isStarting, hasRunningRun, onStartRun, onDelete, onApprove, isApproving,
}: {
  project: Project;
  latestRun?: TestRun;
  isStarting: boolean;
  hasRunningRun: boolean;
  onStartRun: () => void;
  onDelete: () => void;
  onApprove?: () => void;
  isApproving?: boolean;
}) {
  const successRate = project.total_runs > 0 ? Math.round(
    ((project.total_runs - (latestRun?.status === 'failed' ? 1 : 0)) / project.total_runs) * 100
  ) : 0;
  const healthColor =
    successRate >= 90 ? 'text-emerald-500 border-emerald-200 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950' :
    successRate >= 70 ? 'text-amber-500 border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-950' :
    'text-red-500 border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-950';

  // Phase-aware CTA
  const phase: WorkflowPhase = latestRun?.current_phase ?? 'crawler';
  const cta = PHASE_CTA[phase] ?? PHASE_CTA['crawler'];
  const CtaIcon = cta.Icon;

  // Phase label for the banner description
  const PHASE_DESCRIPTION: Record<WorkflowPhase, string> = {
    trigger:         'Setting up workspace and initialising the run.',
    crawler:         'AI is autonomously crawling pages, clicking links, and taking screenshots.',
    inventory:       'Analysing crawled data and building application inventory.',
    test_design:     'AI is designing test scenarios and generating a test plan.',
    human_review:    'Waiting for human review and approval of the test plan.',
    code_generation: 'Generating Playwright test code from approved test plan.',
    execution:       'Running Playwright tests against the live application.',
    reporting:       'Compiling results and generating final test report.',
  };

  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div className="flex items-start gap-4 min-w-0">
        <Button variant="ghost" size="icon" asChild className="shrink-0 mt-0.5">
          <Link href="/projects"><ArrowLeft className="h-4 w-4" /></Link>
        </Button>
        <div className="min-w-0">
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="text-2xl font-bold tracking-tight truncate">{project.name}</h1>
            {latestRun && <StatusBadge status={latestRun.status} size="sm" />}
            {project.total_runs > 0 && (
              <Badge variant="outline" className={cn('text-[11px] gap-1', healthColor)}>
                <div className={cn('h-1.5 w-1.5 rounded-full', successRate >= 90 ? 'bg-emerald-500' : successRate >= 70 ? 'bg-amber-500' : 'bg-red-500')} />
                {successRate}% health
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-2 mt-1 text-sm text-muted-foreground flex-wrap">
            <Globe className="h-3.5 w-3.5" />
            <span className="truncate">{project.application_url}</span>
            <span className="text-muted-foreground/40">·</span>
            <Clock className="h-3.5 w-3.5" />
            <span>Created {formatDateTime(project.created_at)}</span>
            <span className="text-muted-foreground/40">·</span>
            <span>{project.total_runs} runs</span>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2 shrink-0">
        <Button variant="outline" size="sm" onClick={onDelete}>
          <Trash2 className="h-4 w-4" />
        </Button>
        {onApprove && (
          <Button size="sm" onClick={onApprove} disabled={isApproving} className="bg-emerald-600 hover:bg-emerald-700 text-white">
            {isApproving ? <Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> : <CheckCircle className="h-4 w-4 mr-1.5" />}
            {isApproving ? 'Processing...' : 'Approve & Continue'}
          </Button>
        )}
        {hasRunningRun && latestRun ? (
          <Button size="sm" asChild className={cn('text-white font-medium shadow-md', cta.color)}>
            <Link href={`/runs/${latestRun.run_id}`}>
              <CtaIcon className="h-4 w-4 mr-1.5" />
              {cta.label}
            </Link>
          </Button>
        ) : (
          <Button size="sm" onClick={onStartRun} disabled={isStarting}>
            {isStarting ? <Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> : <Play className="h-4 w-4 mr-1.5" />}
            {isStarting ? 'Starting...' : 'Start Run'}
          </Button>
        )}
      </div>
    </div>
  );
}
