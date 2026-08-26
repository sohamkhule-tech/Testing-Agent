'use client';

import { Bot, Search, LayoutGrid, TestTube, GitPullRequest, Code2, FlaskConical, Activity, CheckCircle2, Loader2, AlertCircle, Circle } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { cn, normalizePhase } from '@/lib/utils';
import type { WorkflowPhase } from '@/types/api';

export const STAGES: { phase: WorkflowPhase | 'reporting'; label: string; icon: any }[] = [
  { phase: 'trigger', label: 'Project', icon: Bot },
  { phase: 'crawler', label: 'Crawler', icon: Search },
  { phase: 'inventory', label: 'Inventory', icon: LayoutGrid },
  { phase: 'test_design', label: 'Test Design', icon: TestTube },
  { phase: 'human_review', label: 'Review', icon: GitPullRequest },
  { phase: 'code_generation', label: 'Code Gen', icon: Code2 },
  { phase: 'execution', label: 'Execution', icon: FlaskConical },
  { phase: 'reporting', label: 'Reports', icon: Activity },
];

export const PHASE_ORDER: (WorkflowPhase | 'reporting')[] = STAGES.map(s => s.phase);

export function WorkflowStepper({
  currentPhase: rawCurrentPhase, status,
}: {
  currentPhase?: string;
  status?: string;
}) {
  const currentPhase = normalizePhase(rawCurrentPhase);
  const currentIdx = PHASE_ORDER.indexOf(currentPhase);
  const latestRunStatus = status;

  return (
    <Card className="border-border bg-card">
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-blue-400" />
          <CardTitle className="text-base text-foreground">AI Workflow Pipeline</CardTitle>
          {latestRunStatus && (
            <Badge variant={latestRunStatus === 'failed' ? 'destructive' : 'outline'} className="ml-auto text-xs capitalize">
              {latestRunStatus === 'in_progress' || latestRunStatus === 'running' ? (
                <><Loader2 className="h-3 w-3 mr-1 animate-spin" />Running</>
              ) : latestRunStatus === 'completed' ? 'Completed' : latestRunStatus === 'failed' ? 'Failed' : latestRunStatus === 'paused' ? 'Awaiting Review' : 'Pending'}
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent>
        <div className="flex items-start gap-0 overflow-x-auto pb-2">
          {STAGES.map((stage, i) => {
            const idx = PHASE_ORDER.indexOf(stage.phase);
            const isCompleted = latestRunStatus === 'completed';
            const isPast = isCompleted || (currentIdx !== -1 && idx < currentIdx);
            const isCurrent = !isCompleted && stage.phase === currentPhase;
            const isPending = !isCompleted && (currentIdx === -1 || idx > currentIdx);
            const isFailed = isCurrent && latestRunStatus === 'failed';

            return (
              <div key={stage.phase} className="flex items-center min-w-0">
                <div className="flex flex-col items-center gap-1.5 min-w-0">
                  <div className={cn(
                    "flex h-9 w-9 shrink-0 items-center justify-center rounded-full border-2 transition-colors",
                    isPast && "border-emerald-500/60 bg-emerald-500/10 text-emerald-400",
                    isCurrent && !isFailed && "border-blue-500 bg-blue-500/15 text-blue-400 shadow-md ring-2 ring-blue-500/30",
                    isFailed && "border-red-500/60 bg-red-500/10 text-red-400",
                    isPending && "border-border bg-muted text-muted-foreground",
                  )}>
                    {isPast ? <CheckCircle2 className="h-4 w-4 text-emerald-400" /> :
                     isCurrent && (latestRunStatus === 'in_progress' || latestRunStatus === 'running') ? <Loader2 className="h-4 w-4 animate-spin text-blue-400" /> :
                     isFailed ? <AlertCircle className="h-4 w-4 text-red-400" /> :
                     <stage.icon className="h-4 w-4" />}
                  </div>
                  <span className={cn("text-[11px] font-medium whitespace-nowrap", (isPast || isCurrent) && "text-foreground", isPending && "text-muted-foreground")}>{stage.label}</span>
                </div>
                {i < STAGES.length - 1 && (
                  <div className={cn("h-px w-8 sm:w-12 mx-1 mt-4", isPast ? "bg-emerald-500/60" : isCurrent ? "bg-blue-500/60" : "bg-border")} />
                )}
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
