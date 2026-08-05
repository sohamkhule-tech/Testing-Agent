'use client';

import { Clock, CheckCircle2, Loader2, AlertCircle, Circle } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { cn, formatDateTime, normalizePhase } from '@/lib/utils';
import type { TestRun, WorkflowPhase } from '@/types/api';

export function WorkflowTimeline({ latestRun }: { latestRun?: TestRun }) {
  if (!latestRun) {
    return (
      <Card className="border-zinc-800 bg-zinc-950/60">
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <Clock className="h-4 w-4 text-zinc-400" />
            <CardTitle className="text-base text-zinc-200">Timeline</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <p className="text-xs text-zinc-500 text-center py-4">No activity yet. Start a run to track workflow timeline.</p>
        </CardContent>
      </Card>
    );
  }

  const currentPhase = normalizePhase(latestRun.current_phase);
  const events = generateEvents(latestRun, currentPhase);

  return (
    <Card className="border-zinc-800 bg-zinc-950/60">
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <Clock className="h-4 w-4 text-blue-400" />
          <CardTitle className="text-base text-zinc-200">Timeline</CardTitle>
          <span className="text-[11px] font-mono text-zinc-400 ml-auto">
            Run #{latestRun.run_id.slice(0, 8)}
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-0">
        {events.map((ev, i) => (
          <div key={i} className="relative flex gap-3 pb-4 last:pb-0">
            {i < events.length - 1 && <div className="absolute left-[11px] top-5 h-full w-px bg-zinc-800" />}
            <div className={cn(
              "mt-0.5 flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-full border text-xs",
              ev.type === 'completed' ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-400' :
              ev.type === 'running' ? 'border-blue-500/40 bg-blue-500/10 text-blue-400' :
              ev.type === 'failed' ? 'border-red-500/40 bg-red-500/10 text-red-400' :
              'border-zinc-800 bg-zinc-900 text-zinc-600'
            )}>
              {ev.type === 'completed' ? <CheckCircle2 className="h-3 w-3 text-emerald-400" /> :
               ev.type === 'running' ? <Loader2 className="h-3 w-3 text-blue-400 animate-spin" /> :
               ev.type === 'failed' ? <AlertCircle className="h-3 w-3 text-red-400" /> :
               <Circle className="h-3 w-3 text-zinc-600" />}
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-medium text-zinc-200">{ev.title}</p>
              <p className="text-[11px] text-zinc-500">{ev.detail}</p>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function generateEvents(run: TestRun, currentPhase: WorkflowPhase) {
  const events: { title: string; detail: string; type: 'completed' | 'running' | 'failed' | 'pending' }[] = [];
  const phases: WorkflowPhase[] = ['trigger', 'crawler', 'inventory', 'test_design', 'human_review', 'code_generation', 'execution', 'reporting'];
  const currentIdx = phases.indexOf(currentPhase);
  const isCompleted = run.status === 'completed';

  events.push({ title: 'Project Created', detail: `Run ${run.run_id.substring(0, 8)}`, type: 'completed' });
  if (run.status === 'pending') return events;

  for (let i = 0; i < phases.length; i++) {
    const label = phases[i].replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    if (isCompleted || i < currentIdx) {
      events.push({ title: `${label} Completed`, detail: formatDateTime(run.started_at), type: 'completed' });
    } else if (i === currentIdx) {
      events.push({
        title: `${label} ${run.status === 'failed' ? 'Failed' : run.status === 'paused' ? 'Awaiting Review' : 'Running'}`,
        detail: formatDateTime(run.started_at),
        type: run.status === 'failed' ? 'failed' : 'running',
      });
    } else {
      events.push({ title: `${label} Pending`, detail: '—', type: 'pending' });
    }
  }
  return events;
}
