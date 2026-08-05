'use client';

import Link from 'next/link';
import { Activity } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { StatusBadge } from '@/components/status-badge';
import { formatDuration, formatDateTime } from '@/lib/utils';
import type { TestRun } from '@/types/api';

export function RunList({ runs, isLoading }: { runs: TestRun[]; isLoading?: boolean }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-muted-foreground" />
            <CardTitle className="text-base">Runs</CardTitle>
            <span className="text-xs text-muted-foreground">({runs.length})</span>
          </div>
          <Button variant="ghost" size="sm" className="text-xs" asChild><Link href="/runs">View All</Link></Button>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        {runs.length === 0 ? (
          <div className="p-6 text-sm text-muted-foreground text-center">No runs yet</div>
        ) : (
          <div className="divide-y">
            {runs.slice(0, 5).map((run) => (
              <div key={run.run_id} className="flex items-center justify-between px-4 py-3 hover:bg-accent/50 transition-colors">
                <div className="min-w-0 flex-1">
                  <Link href={`/runs/${run.run_id}`} className="text-xs font-mono text-primary hover:underline">
                    {run.run_id.substring(0, 8)}...
                  </Link>
                  <div className="flex items-center gap-2 mt-0.5">
                    <StatusBadge status={run.status} size="sm" />
                    <span className="text-xs text-muted-foreground capitalize">{run.current_phase.replace('_', ' ')}</span>
                  </div>
                </div>
                <div className="text-right shrink-0 ml-2">
                  <p className="text-xs text-muted-foreground">{run.duration_seconds ? formatDuration(run.duration_seconds) : '-'}</p>
                  <p className="text-[11px] text-muted-foreground/60">{run.started_at ? formatDateTime(run.started_at) : ''}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
