'use client';

import { useState } from 'react';
import { PageHeader } from '@/components/page-header';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { StatusBadge } from '@/components/status-badge';
import { EmptyState } from '@/components/empty-state';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { CheckSquare, ChevronRight, FileText, GitPullRequest, Eye, AlertCircle, CheckCircle2, XCircle, Clock } from 'lucide-react';
import { useRuns, useRunTestPlan, useRunReview } from '@/hooks/use-api';
import { formatDateTime } from '@/lib/utils';
import { cn } from '@/lib/utils';

export default function ReviewPage() {
  const { data: runsData, isLoading } = useRuns();
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const runs = runsData?.runs ?? [];
  const reviewableRuns = runs.filter(r => r.current_phase !== 'trigger');

  if (isLoading) {
    return (
      <div className="container py-6 space-y-6">
        <PageHeader title="Human Review" description="Review and approve AI-generated test plans" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  return (
    <div className="container py-6 space-y-6">
      <PageHeader title="Human Review" description="Review and approve AI-generated test plans" />

      {reviewableRuns.length === 0 ? (
        <EmptyState icon={CheckSquare} title="No reviews available" description="Start a run from a project to generate test plans for review." />
      ) : (
        <div className="grid gap-6 lg:grid-cols-3">
          <div className="lg:col-span-1 space-y-3">
            <Card>
              <CardHeader className="pb-3"><CardTitle className="text-base">Runs</CardTitle></CardHeader>
              <CardContent className="p-0">
                {reviewableRuns.map(run => (
                  <button key={run.run_id} onClick={() => setSelectedRunId(run.run_id)}
                    className={cn("w-full text-left px-4 py-3 border-b hover:bg-accent/50 transition-colors flex items-center justify-between gap-2",
                      selectedRunId === run.run_id && "bg-accent")}>
                    <div className="min-w-0">
                      <p className="text-sm font-mono truncate">{run.run_id.substring(0, 12)}...</p>
                      <div className="flex items-center gap-2 mt-1">
                        <StatusBadge status={run.status} size="sm" />
                        <span className="text-xs text-muted-foreground capitalize">{run.current_phase?.replace('_', ' ')}</span>
                      </div>
                    </div>
                    <ChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />
                  </button>
                ))}
              </CardContent>
            </Card>
          </div>

          <div className="lg:col-span-2">
            {selectedRunId ? <ReviewDetail runId={selectedRunId} /> : (
              <Card><CardContent className="py-12 text-center text-muted-foreground">Select a run to view its test plan and review status</CardContent></Card>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function ReviewDetail({ runId }: { runId: string }) {
  const { data: testPlan, isLoading: planLoading } = useRunTestPlan(runId);
  const { data: review, isLoading: reviewLoading } = useRunReview(runId);

  if (planLoading || reviewLoading) return <Skeleton className="h-96 w-full" />;

  const scenarios = testPlan?.test_scenarios ?? [];
  const reviewMeta = review?.review_metadata;
  const approvedPlan = review?.approved_test_plan;
  const approvedScenarios = approvedPlan?.test_scenarios ?? [];
  const reviewStatus = reviewMeta?.review_status;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">Test Plan</CardTitle>
            {reviewStatus && <Badge variant={reviewStatus === 'approved' ? 'success' : reviewStatus === 'changes_requested' ? 'warning' : 'secondary'}>{reviewStatus.replace('_', ' ')}</Badge>}
          </div>
          {testPlan && <CardDescription>{testPlan.application_summary?.name ?? 'Test Plan'} — {scenarios.length} scenarios</CardDescription>}
        </CardHeader>
        <CardContent>
          {scenarios.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4 text-center">No scenarios found</p>
          ) : (
            <div className="space-y-3">
              {scenarios.map((s: any, i: number) => (
                <ScenarioCard key={s.scenario_id ?? i} scenario={s} index={i} />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {reviewMeta && (
        <Card>
          <CardHeader className="pb-3"><CardTitle className="text-base">Review Summary</CardTitle></CardHeader>
          <CardContent className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <SummaryStat icon={CheckCircle2} label="Approved" value={reviewMeta.approved_scenarios ?? 0} color="text-emerald-500" />
            <SummaryStat icon={XCircle} label="Rejected" value={reviewMeta.rejected_scenarios ?? 0} color="text-red-500" />
            <SummaryStat icon={Eye} label="Reviewed By" value={reviewMeta.reviewer_name ?? 'system'} color="text-blue-500" />
            <SummaryStat icon={Clock} label="Version" value={`v${reviewMeta.review_version ?? 1}`} color="text-muted-foreground" />
          </CardContent>
        </Card>
      )}

      {approvedScenarios.length > 0 && (
        <Card>
          <CardHeader className="pb-3"><CardTitle className="text-base">Approved Scenarios</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            {approvedScenarios.map((s: any, i: number) => (
              <div key={s.scenario_id ?? i} className="flex items-center gap-3 rounded-lg border p-3">
                <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
                <div>
                  <p className="text-sm font-medium">{s.title ?? s.name ?? `Scenario ${i + 1}`}</p>
                  {s.description && <p className="text-xs text-muted-foreground mt-0.5">{s.description}</p>}
                </div>
                <Badge variant="outline" className="ml-auto text-xs capitalize">{s.priority ?? 'medium'}</Badge>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function ScenarioCard({ scenario, index }: { scenario: any; index: number }) {
  const [expanded, setExpanded] = useState(false);
  const steps = scenario.steps ?? scenario.test_steps ?? [];
  return (
    <div className="rounded-lg border">
      <button onClick={() => setExpanded(!expanded)} className="w-full text-left px-4 py-3 flex items-center justify-between gap-2 hover:bg-accent/50 transition-colors">
        <div className="flex items-center gap-3 min-w-0">
          <span className="text-xs font-mono text-muted-foreground w-6">{index + 1}</span>
          <span className="text-sm font-medium truncate">{scenario.title ?? scenario.name ?? `Scenario ${index + 1}`}</span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {scenario.priority && <Badge variant="outline" className="text-xs capitalize">{scenario.priority}</Badge>}
          {scenario.risk && <Badge variant="secondary" className="text-xs capitalize">{scenario.risk}</Badge>}
          <ChevronRight className={cn("h-4 w-4 text-muted-foreground transition-transform", expanded && "rotate-90")} />
        </div>
      </button>
      {expanded && (
        <div className="px-4 pb-3 border-t">
          {scenario.description && <p className="text-xs text-muted-foreground mt-2">{scenario.description}</p>}
          {scenario.category && <p className="text-xs text-muted-foreground mt-1">Category: {scenario.category}</p>}
          {steps.length > 0 && (
            <div className="mt-2 space-y-1">
              <p className="text-xs font-medium text-muted-foreground">Steps ({steps.length}):</p>
              {steps.map((step: any, si: number) => (
                <p key={si} className="text-xs text-muted-foreground pl-3 border-l-2 border-muted">
                  {si + 1}. {step.description ?? step.action ?? step.name ?? `Step ${si + 1}`}
                </p>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function SummaryStat({ icon: Icon, label, value, color }: { icon: any; label: string; value: string | number; color: string }) {
  return (
    <div className="rounded-lg border p-3 text-center">
      <Icon className={cn("h-5 w-5 mx-auto mb-1", color)} />
      <div className="text-lg font-bold">{value}</div>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  );
}
