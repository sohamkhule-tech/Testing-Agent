"use client";

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  Activity,
  AlertCircle,
  ArrowUpRight,
  BarChart3,
  Brain,
  CheckCircle2,
  Clock,
  FileText,
  FlaskConical,
  FolderKanban,
  GitPullRequest,
  Play,
  Plus,
  RefreshCw,
  Shield,
  Sparkles,
  Layers,
  TestTube,
  Zap,
  Globe,
  X,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { StatusBadge } from '@/components/status-badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { cn } from '@/lib/utils';
import { formatDateTime, formatDuration } from '@/lib/utils';
import {
  useDashboardStats,
  useRecentRuns,
  useRecentProjects,
  useCreateProject,
} from '@/hooks/use-api';
import type { CreateProjectRequest } from '@/types/api';

// ===================================================================
// Mock data — ONLY for sections without API endpoints
// ===================================================================

const MOCK_HEALTH: { name: string; status: 'healthy' | 'degraded' }[] = [
  { name: 'Backend API', status: 'healthy' },
  { name: 'Database', status: 'healthy' },
  { name: 'AI Models', status: 'healthy' },
  { name: 'Queue', status: 'healthy' },
  { name: 'Playwright', status: 'healthy' },
  { name: 'Storage', status: 'degraded' },
];

const MOCK_REVIEWS = [
  { id: 'REV-001', project: 'Checkout Flow', scenarios: 12, status: 'pending' as const },
  { id: 'REV-002', project: 'Payment API', scenarios: 8, status: 'approved' as const },
  { id: 'REV-003', project: 'Login Module', scenarios: 15, status: 'changes_requested' as const },
  { id: 'REV-004', project: 'Dashboard UI', scenarios: 6, status: 'pending' as const },
];

// ===================================================================
// Dashboard Page — wired to real API hooks
// ===================================================================

function generateInsights(stats: any, recentRuns: any[] | undefined) {
  const insights: { icon: any; color: string; bg: string; message: string; type: string }[] = [];
  if (!stats) return insights;

  if (stats.completed_today > 0) {
    insights.push({
      icon: Sparkles, color: 'text-blue-500', bg: 'bg-blue-50 dark:bg-blue-950', type: 'info',
      message: `AI completed ${stats.completed_today} test run${stats.completed_today !== 1 ? 's' : ''} today across all projects`,
    });
  }

  if (stats.success_rate !== undefined && stats.total_runs > 0) {
    const rate = stats.success_rate;
    if (rate >= 90) {
      insights.push({
        icon: CheckCircle2, color: 'text-emerald-500', bg: 'bg-emerald-50 dark:bg-emerald-950', type: 'success',
        message: `Overall pass rate is ${rate}% — test suite is healthy and reliable`,
      });
    } else if (rate < 70) {
      insights.push({
        icon: AlertCircle, color: 'text-amber-500', bg: 'bg-amber-50 dark:bg-amber-950', type: 'warning',
        message: `Overall pass rate is ${rate}% — review recommended to improve reliability`,
      });
    }
  }

  if (recentRuns && recentRuns.length > 0) {
    const failed = recentRuns.filter((r: any) => r.status === 'failed').length;
    if (failed > 0) {
      insights.push({
        icon: AlertCircle, color: 'text-red-500', bg: 'bg-red-50 dark:bg-red-950', type: 'error',
        message: `${failed} recent run${failed !== 1 ? 's' : ''} failed — check the runs page for details`,
      });
    }
  }

  if (stats.pending_reviews > 0) {
    insights.push({
      icon: FileText, color: 'text-purple-500', bg: 'bg-purple-50 dark:bg-purple-950', type: 'info',
      message: `${stats.pending_reviews} test plan${stats.pending_reviews !== 1 ? 's' : ''} ${stats.pending_reviews === 1 ? 'is' : 'are'} awaiting your review`,
    });
  }

  if (stats.active_runs > 0) {
    insights.push({
      icon: Zap, color: 'text-sky-500', bg: 'bg-sky-50 dark:bg-sky-950', type: 'info',
      message: `${stats.active_runs} autonomous agent${stats.active_runs !== 1 ? 's' : ''} currently executing test workflows`,
    });
  }

  if (insights.length === 0) {
    insights.push({
      icon: Sparkles, color: 'text-purple-500', bg: 'bg-purple-50 dark:bg-purple-950', type: 'info',
      message: 'Create your first project to start generating AI-powered test insights',
    });
  }

  return insights;
}

export default function HomePage() {
  const { data: stats, isLoading: statsLoading } = useDashboardStats();
  const { data: recentRuns } = useRecentRuns(10);
  const { data: recentProjects } = useRecentProjects(6);
  const [showCreate, setShowCreate] = useState(false);

  const hasData = stats && (stats.total_projects > 0 || stats.total_runs > 0);

  return (
    <div className="p-6 space-y-8">
      <HeroHeader onCreateProject={() => setShowCreate(true)} statsLoading={statsLoading} stats={stats} />

      {!hasData && !statsLoading ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16 text-center">
            <FlaskConical className="h-12 w-12 text-muted-foreground/40 mb-4" />
            <h2 className="text-xl font-semibold mb-2">Welcome to AI Testing Platform</h2>
            <p className="text-muted-foreground mb-6 max-w-md">
              Create your first project to start testing your web applications with autonomous AI agents.
            </p>
            <Button size="lg" onClick={() => setShowCreate(true)}>
              <Plus className="h-4 w-4 mr-2" />
              Create Your First Project
            </Button>
          </CardContent>
        </Card>
      ) : (
        <>
          <MetricGrid stats={stats} loading={statsLoading} />
          <AiInsights stats={stats} recentRuns={recentRuns} loading={statsLoading} />
          <div className="grid gap-6 lg:grid-cols-3">
            <ActivityTimeline recentRuns={recentRuns} />
            <SystemHealth />
            <HumanReview />
          </div>
          <ProjectGrid recentProjects={recentProjects} />
          <RunsTable recentRuns={recentRuns} />
        </>
      )}

      {showCreate && <CreateProjectModal onClose={() => setShowCreate(false)} />}
    </div>
  );
}

// ===================================================================
// Section 1: Hero Header
// ===================================================================

function HeroHeader({ onCreateProject, statsLoading, stats }: { onCreateProject: () => void; statsLoading: boolean; stats: any }) {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="space-y-1">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary">
            <FlaskConical className="h-4 w-4 text-primary-foreground" />
          </div>
          <h1 className="text-xl font-semibold tracking-tight">Enterprise AI Testing Platform</h1>
        </div>
        <p className="text-sm text-muted-foreground pl-10">
          {statsLoading ? 'Loading...' : stats ? `${stats.total_projects} projects · ${stats.total_runs} total runs · ${stats.active_runs} active` : 'Monitor autonomous AI testing workflows across your applications'}
        </p>
      </div>
      <div className="flex items-center gap-2">
        <Button variant="outline" size="sm" className="gap-1.5" onClick={onCreateProject}>
          <Plus className="h-4 w-4" />
          New Project
        </Button>
      </div>
    </div>
  );
}

// ===================================================================
// Section 2: Primary Metrics
// ===================================================================

function MetricGrid({ stats, loading }: { stats: any; loading: boolean }) {
  if (loading) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        {[...Array(6)].map((_, i) => <Skeleton key={i} className="h-28 rounded-lg" />)}
      </div>
    );
  }
  const items = [
    { title: 'Total Projects', value: String(stats?.total_projects ?? 0), icon: FolderKanban, subtitle: 'Active projects', color: 'text-blue-500', bg: 'bg-blue-50 dark:bg-blue-950', href: '/projects' },
    { title: 'Total Runs', value: String(stats?.total_runs ?? 0), icon: Play, subtitle: 'All time executions', color: 'text-violet-500', bg: 'bg-violet-50 dark:bg-violet-950', href: '/runs' },
    { title: 'Active Runs', value: String(stats?.active_runs ?? 0), icon: Brain, subtitle: 'Currently running', color: 'text-emerald-500', bg: 'bg-emerald-50 dark:bg-emerald-950', href: '/runs' },
    { title: 'Success Rate', value: stats ? `${stats.success_rate}%` : '-', icon: BarChart3, subtitle: 'Across all projects', color: 'text-amber-500', bg: 'bg-amber-50 dark:bg-amber-950' },
    { title: 'Completed Today', value: String(stats?.completed_today ?? 0), icon: CheckCircle2, subtitle: 'Successful executions', color: 'text-sky-500', bg: 'bg-sky-50 dark:bg-sky-950', href: '/runs' },
    { title: 'Pending Reviews', value: String(stats?.pending_reviews ?? 0), icon: FileText, subtitle: 'Awaiting approval', color: 'text-rose-500', bg: 'bg-rose-50 dark:bg-rose-950', href: '/runs' },
  ];
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
      {items.map((m) => (
        <MetricCard key={m.title} title={m.title} value={m.value} icon={m.icon} subtitle={m.subtitle} color={m.color} bg={m.bg} href={(m as any).href} />
      ))}
    </div>
  );
}

function MetricCard({ title, value, icon: Icon, subtitle, color, bg, href }: {
  title: string; value: string; icon: React.ElementType; subtitle: string; color: string; bg: string; href?: string;
}) {
  const content = (
    <Card className={cn("relative overflow-hidden transition-shadow hover:shadow-md", href && "cursor-pointer hover:shadow-lg hover:border-primary/50 transition-colors")}>
      <CardHeader className="pb-2">
        <div className={cn("flex h-10 w-10 items-center justify-center rounded-lg", bg)}>
          <Icon className={cn("h-5 w-5", color)} />
        </div>
      </CardHeader>
      <CardContent className="space-y-1">
        <div className="text-2xl font-bold tracking-tight">{value}</div>
        <p className="text-xs font-medium text-muted-foreground">{title}</p>
        <p className="text-[11px] text-muted-foreground/70">{subtitle}</p>
      </CardContent>
    </Card>
  );
  if (href) return <Link href={href}>{content}</Link>;
  return content;
}

// ===================================================================
// Section 3: AI Insights
// ===================================================================

function AiInsights({ stats, recentRuns, loading }: { stats: any; recentRuns: any[] | undefined; loading: boolean }) {
  const insights = generateInsights(stats, recentRuns);
  const [lastUpdated] = useState(() => new Date());
  const timeAgo = Math.floor((Date.now() - lastUpdated.getTime()) / 60000);

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-md bg-purple-50 dark:bg-purple-950">
              <Brain className="h-4 w-4 text-purple-500" />
            </div>
            <CardTitle className="text-base">AI Insights</CardTitle>
          </div>
          <Badge variant="secondary" className="text-[11px]">
            {loading ? 'Loading...' : `Updated ${timeAgo}m ago`}
          </Badge>
        </div>
        <CardDescription>Real-time intelligence from autonomous testing agents</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {loading ? (
          [...Array(3)].map((_, i) => <Skeleton key={i} className="h-14 rounded-lg" />)
        ) : insights.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-4">No insights available yet</p>
        ) : (
          insights.map((insight, i) => (
            <div
              key={i}
              className={cn(
                "flex items-start gap-3 rounded-lg border p-3 transition-colors hover:bg-accent/50",
              )}
            >
              <div className={cn("flex h-8 w-8 shrink-0 items-center justify-center rounded-md", insight.bg)}>
                <insight.icon className={cn("h-4 w-4", insight.color)} />
              </div>
              <p className="text-sm leading-relaxed text-foreground/90">{insight.message}</p>
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}

// ===================================================================
// Section 4: Activity Timeline
// ===================================================================

function ActivityTimeline({ recentRuns }: { recentRuns: any[] | undefined }) {
  const activities = recentRuns?.slice(0, 8) ?? [];
  return (
    <Card className="lg:col-span-1">
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-muted-foreground" />
          <CardTitle className="text-base">Recent Activity</CardTitle>
        </div>
        <CardDescription>Agent workflow executions</CardDescription>
      </CardHeader>
      <CardContent className="space-y-0">
        {activities.length === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-6">No recent activity</p>
        ) : activities.map((run: any, i: number) => (
          <div key={run.run_id ?? i} className="relative flex gap-4 pb-5 last:pb-0">
            {i < activities.length - 1 && <div className="absolute left-[15px] top-6 h-full w-px bg-border" />}
            <div className="relative mt-0.5 shrink-0">
              <div className={cn(
                "h-[30px] w-[30px] rounded-full border-2 flex items-center justify-center",
                run.status === 'completed' && "border-emerald-200 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950",
                run.status === 'in_progress' && "border-blue-200 bg-blue-50 dark:border-blue-800 dark:bg-blue-950",
                run.status === 'failed' && "border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-950",
              )}>
                {run.status === 'completed' && <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />}
                {run.status === 'in_progress' && <RefreshCw className="h-3.5 w-3.5 text-blue-500 animate-spin" />}
                {run.status === 'failed' && <AlertCircle className="h-3.5 w-3.5 text-red-500" />}
              </div>
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                  <span className="text-sm font-medium truncate">{run.project_name ?? `Run ${run.run_id?.substring(0, 8)}`}</span>
                  <StatusBadge status={run.status} size="sm" />
              </div>
              <p className="text-xs text-muted-foreground truncate">Phase: {run.current_phase?.replace('_', ' ') ?? '-'}</p>
              <p className="text-[11px] text-muted-foreground/60 mt-0.5">{run.started_at ? formatDateTime(run.started_at) : '-'}</p>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

// ===================================================================
// Section 7: System Health
// ===================================================================

function SystemHealth() {
  return (
    <Card className="lg:col-span-1">
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <Shield className="h-4 w-4 text-muted-foreground" />
          <CardTitle className="text-base">System Health</CardTitle>
        </div>
        <CardDescription>All services operational</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {MOCK_HEALTH.map((h) => (
          <div key={h.name} className="flex items-center justify-between rounded-lg border px-3 py-2.5 transition-colors hover:bg-accent/50">
            <div className="flex items-center gap-3">
              <div
                className={cn(
                  "h-2 w-2 rounded-full",
                  h.status === 'healthy' && "bg-emerald-500",
                  h.status === 'degraded' && "bg-amber-500",
                )}
              />
              <span className="text-sm font-medium">{h.name}</span>
            </div>
            <span
              className={cn(
                "text-xs font-medium",
                h.status === 'healthy' && "text-emerald-500",
                h.status === 'degraded' && "text-amber-500",
              )}
            >
              {h.status === 'healthy' && 'Healthy'}
              {h.status === 'degraded' && 'Degraded'}
            </span>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

// ===================================================================
// Section 8: Human Review
// ===================================================================

function HumanReview() {
  const pending = MOCK_REVIEWS.filter((r) => r.status === 'pending').length;
  const approved = MOCK_REVIEWS.filter((r) => r.status === 'approved').length;
  const changes = MOCK_REVIEWS.filter((r) => r.status === 'changes_requested').length;
  return (
    <Card className="lg:col-span-1">
      <CardHeader className="pb-3">
        <div className="flex items-center gap-2">
          <GitPullRequest className="h-4 w-4 text-muted-foreground" />
          <CardTitle className="text-base">Human Review</CardTitle>
          {pending > 0 && (
            <Badge variant="destructive" className="ml-auto text-[11px]">
              {pending} pending
            </Badge>
          )}
        </div>
        <CardDescription>Test plans awaiting approval</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Summary */}
        <div className="grid grid-cols-3 gap-3">
          <SummaryBlock label="Pending" value={String(pending)} color="text-amber-500" />
          <SummaryBlock label="Approved" value={String(approved)} color="text-emerald-500" />
          <SummaryBlock label="Changes" value={String(changes)} color="text-blue-500" />
        </div>

        {/* List */}
        <div className="space-y-2">
          {MOCK_REVIEWS.slice(0, 3).map((r) => (
            <div key={r.id} className="flex items-center justify-between rounded-lg border px-3 py-2.5 transition-colors hover:bg-accent/50">
              <div className="min-w-0">
                <p className="text-sm font-medium truncate">{r.project}</p>
                <p className="text-xs text-muted-foreground">{r.scenarios} scenarios</p>
              </div>
              <ReviewStatusBadge status={r.status} />
            </div>
          ))}
        </div>

        <Button variant="outline" size="sm" className="w-full gap-1.5">
          <GitPullRequest className="h-4 w-4" />
          View All Reviews
        </Button>
      </CardContent>
    </Card>
  );
}

function SummaryBlock({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="rounded-lg border p-3 text-center">
      <div className={cn("text-xl font-bold", color)}>{value}</div>
      <p className="text-[11px] text-muted-foreground">{label}</p>
    </div>
  );
}

// ===================================================================
// Section 5: Projects Grid
// ===================================================================

function ProjectGrid({ recentProjects }: { recentProjects: any[] | undefined }) {
  const projects = recentProjects ?? [];
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Layers className="h-4 w-4 text-muted-foreground" />
          <h2 className="text-base font-semibold">Projects</h2>
          <span className="text-xs text-muted-foreground">({projects.length})</span>
        </div>
        <Button variant="ghost" size="sm" className="text-xs gap-1" asChild>
          <Link href="/projects">
            View All <ArrowUpRight className="h-3.5 w-3.5" />
          </Link>
        </Button>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        {projects.length === 0 ? (
          <p className="text-sm text-muted-foreground col-span-full text-center py-6">No projects yet</p>
        ) : projects.map((p: any) => (
          <Link key={p.id} href={`/projects/${p.id}`}>
            <Card className="h-full transition-shadow hover:shadow-md">
              <CardHeader className="pb-2">
                <div className="flex items-start gap-2">
                  <div className={cn("h-2 w-2 rounded-full mt-1.5 shrink-0", p.last_run_status === 'failed' ? "bg-red-500" : p.last_run_status ? "bg-emerald-500" : "bg-muted-foreground/40")} />
                  <CardTitle className="text-sm font-medium truncate">{p.name}</CardTitle>
                </div>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground truncate">
                  <Globe className="h-3 w-3 shrink-0" />
                  <span className="truncate">{p.application_url}</span>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">Runs</span>
                  <span className="font-medium">{p.total_runs}</span>
                </div>
                {p.last_run_at && <p className="text-[11px] text-muted-foreground/60">Last run: {formatDateTime(p.last_run_at)}</p>}
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}

// ===================================================================
// Section 6: Runs Table
// ===================================================================

function RunsTable({ recentRuns }: { recentRuns: any[] | undefined }) {
  const runs = recentRuns ?? [];
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-muted-foreground" />
            <CardTitle className="text-base">Latest Executions</CardTitle>
            <span className="text-xs text-muted-foreground">({runs.length})</span>
          </div>
          <Button variant="ghost" size="sm" className="text-xs gap-1" asChild>
            <Link href="/runs">
              View All <ArrowUpRight className="h-3.5 w-3.5" />
            </Link>
          </Button>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        {runs.length === 0 ? (
          <div className="p-6 text-sm text-muted-foreground text-center">No executions yet</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b text-left text-xs font-medium text-muted-foreground">
                  <th className="px-4 py-3">Run</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Phase</th>
                  <th className="px-4 py-3">Started</th>
                  <th className="px-4 py-3">Duration</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r: any) => (
                  <tr key={r.run_id} className="border-b text-sm hover:bg-accent/50 transition-colors">
                    <td className="px-4 py-3 font-mono text-xs">{r.run_id?.substring(0, 8)}...</td>
                    <td className="px-4 py-3"><StatusBadge status={r.status} size="sm" /></td>
                    <td className="px-4 py-3 capitalize text-muted-foreground">{r.current_phase?.replace('_', ' ') ?? '-'}</td>
                    <td className="px-4 py-3 text-muted-foreground">{r.started_at ? formatDateTime(r.started_at) : '-'}</td>
                    <td className="px-4 py-3">{r.duration_seconds ? formatDuration(r.duration_seconds) : '-'}</td>
                    <td className="px-4 py-3 text-right">
                      <Button variant="ghost" size="sm" className="h-7 text-xs gap-1" asChild>
                        <Link href={`/runs/${r.run_id}`}>View <ArrowUpRight className="h-3 w-3" /></Link>
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
  );
}

// ===================================================================
// Shared Status Badges
// ===================================================================

function ReviewStatusBadge({ status }: { status: 'pending' | 'approved' | 'changes_requested' }) {
  const map = {
    pending: { label: 'Pending', variant: 'warning' as const },
    approved: { label: 'Approved', variant: 'success' as const },
    changes_requested: { label: 'Changes', variant: 'info' as const },
  };
  const s = map[status];
  return <Badge variant={s.variant} className="text-[10px] px-1.5 py-0">{s.label}</Badge>;
}

function CreateProjectModal({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const createProject = useCreateProject();
  const [form, setForm] = useState<CreateProjectRequest>({ name: '', description: '', application_url: '', starting_urls: [], max_pages: 50, max_depth: 3 });
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (!form.name.trim()) { setError('Name is required'); return; }
    if (!form.application_url.trim()) { setError('Application URL is required'); return; }
    try {
      const result = await createProject.mutateAsync({ ...form, starting_urls: [form.application_url] });
      onClose();
      router.push(`/projects/${result.id}`);
    } catch { setError('Failed to create project.'); }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <Card className="w-full max-w-lg">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>New Project</CardTitle>
            <Button variant="ghost" size="icon" onClick={onClose}><X className="h-4 w-4" /></Button>
          </div>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="name">Project Name *</Label>
              <Input id="name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="My Web App" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="desc">Description</Label>
              <Input id="desc" value={form.description ?? ''} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Optional description" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="url">Application URL *</Label>
              <Input id="url" value={form.application_url} onChange={(e) => setForm({ ...form, application_url: e.target.value })} placeholder="https://example.com" />
            </div>
            {error && <p className="text-sm text-red-500">{error}</p>}
            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
              <Button type="submit" disabled={createProject.isPending}>{createProject.isPending ? 'Creating...' : 'Create Project'}</Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
