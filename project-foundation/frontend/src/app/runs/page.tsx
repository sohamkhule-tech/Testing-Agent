'use client';

import { PageHeader } from '@/components/page-header';
import { Card, CardContent } from '@/components/ui/card';
import { EmptyState } from '@/components/empty-state';
import { StatusBadge } from '@/components/status-badge';
import { Button } from '@/components/ui/button';
import { PlayCircle, ExternalLink } from 'lucide-react';
import { useRuns } from '@/hooks/use-api';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateTime, formatDuration } from '@/lib/utils';
import Link from 'next/link';

export default function RunsPage() {
  const { data, isLoading } = useRuns();

  return (
    <div className="container py-6 space-y-6">
      <PageHeader
        title="Test Runs"
        description="Monitor all test executions across your projects"
      />

      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-6 space-y-4">
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} className="h-16 w-full" />
              ))}
            </div>
          ) : !data || data.runs.length === 0 ? (
            <div className="p-6">
              <EmptyState
                icon={PlayCircle}
                title="No runs yet"
                description="Start a run from a project to see test executions here"
              />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="border-b bg-muted/50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider">
                      Run ID
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider">
                      Status
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider">
                      Current Phase
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider">
                      Started
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider">
                      Duration
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-medium uppercase tracking-wider">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {data.runs.map((run) => (
                    <tr key={run.run_id} className="hover:bg-muted/50 transition-colors">
                      <td className="px-4 py-3">
                        <Link
                          href={`/runs/${run.run_id}`}
                          className="text-sm font-mono text-primary hover:underline"
                        >
                          {run.run_id.substring(0, 8)}...
                        </Link>
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge status={run.status} size="sm" />
                      </td>
                      <td className="px-4 py-3">
                        <span className="text-sm capitalize">{run.current_phase.replace('_', ' ')}</span>
                      </td>
                      <td className="px-4 py-3">
                        <span className="text-sm text-muted-foreground">
                          {formatDateTime(run.started_at)}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className="text-sm">
                          {run.duration_seconds
                            ? formatDuration(run.duration_seconds)
                            : '-'}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <Button variant="ghost" size="sm" asChild>
                          <Link href={`/runs/${run.run_id}`}>
                            <ExternalLink className="h-3.5 w-3.5" />
                          </Link>
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
