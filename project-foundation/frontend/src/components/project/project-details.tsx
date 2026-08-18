'use client';

import { Shield } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateTime, formatDuration } from '@/lib/utils';
import type { TestRun } from '@/types/api';

export function ProjectDetails({
  project,
  stats,
  runs,
  isLoading,
}: {
  project?: any;
  stats?: any;
  runs?: TestRun[];
  isLoading?: boolean;
}) {
  if (isLoading) {
    return (
      <Card>
        <CardHeader className="pb-3"><Skeleton className="h-5 w-24" /></CardHeader>
        <CardContent className="space-y-3"><Skeleton className="h-4 w-full" /><Skeleton className="h-4 w-3/4" /><Skeleton className="h-4 w-1/2" /></CardContent>
      </Card>
    );
  }
  if (!project) return null;

  // Calculate actual total runs and success rate dynamically from runs array if available
  const actualTotalRuns = runs && runs.length > 0 ? runs.length : (project.total_runs || 0);
  const completedCount = runs ? runs.filter(r => r.status === 'completed').length : (stats?.successful_runs || 0);
  const failedCount = runs ? runs.filter(r => r.status === 'failed').length : (stats?.failed_runs || 0);
  const finishedCount = completedCount + failedCount;

  const successRatePct = finishedCount > 0
    ? Math.round((completedCount / finishedCount) * 100)
    : (stats?.total_runs > 0 ? Math.round((stats.successful_runs / stats.total_runs) * 100) : 0);

  const avgDuration = stats?.average_duration_seconds
    ? formatDuration(stats.average_duration_seconds)
    : (runs && runs.filter(r => r.duration_seconds).length > 0
        ? formatDuration(Math.round(runs.reduce((acc, r) => acc + (r.duration_seconds || 0), 0) / runs.filter(r => r.duration_seconds).length))
        : '—');

  const lastRunAt = runs?.[0]?.started_at || project.last_run_at;

  return (
    <Card className="border-border bg-card">
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <Shield className="h-4 w-4 text-muted-foreground" />
          <CardTitle className="text-base text-foreground">Details</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <Row label="Created" value={formatDateTime(project.created_at)} />
        <Row label="Environment" value={project.auth_type || 'Default'} />
        <Row label="Total Runs" value={<span className="font-bold text-foreground">{actualTotalRuns}</span>} />
        {lastRunAt && <Row label="Last Run" value={formatDateTime(lastRunAt)} />}
        <div className="border-t border-border pt-3" />
        <Row
          label="Success Rate"
          value={
            <span className={finishedCount > 0 && successRatePct >= 50 ? 'text-emerald-400 font-semibold' : 'text-amber-400 font-semibold'}>
              {finishedCount > 0 || stats?.total_runs > 0 ? `${successRatePct}%` : '—'}
            </span>
          }
        />
        <Row label="Avg Duration" value={avgDuration} />
      </CardContent>
    </Card>
  );
}

function Row({ label, value }: { label: string; value: string | React.ReactNode }) {
  return (
    <div className="flex justify-between items-center text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium text-foreground truncate ml-2">{value}</span>
    </div>
  );
}
