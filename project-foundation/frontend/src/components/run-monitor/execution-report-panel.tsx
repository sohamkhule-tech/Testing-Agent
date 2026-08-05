'use client';

/**
 * ExecutionReportPanel — Rich reports view for completed test runs.
 * Fetches /execution + /reports REST endpoints and renders:
 *   - Pass / Fail / Skip summary ring + stat cards
 *   - Execution metadata (duration, command, return code)
 *   - Full test results table with status icons
 *   - Failure analysis section
 */

import React, { useEffect, useState } from 'react';
import { cn } from '@/lib/utils';
import {
  CheckCircle2,
  XCircle,
  SkipForward,
  TrendingUp,
  Clock,
  AlertCircle,
  FileText,
  Activity,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  Terminal,
  Layers,
} from 'lucide-react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface TestItem {
  id: string;
  name: string;
  file?: string;
  status: 'passed' | 'failed' | 'skipped';
  duration?: number | null;
  error?: string | null;
  browser?: string | null;
}

interface ExecutionSummary {
  total: number;
  passed: number;
  failed: number;
  skipped: number;
  pass_rate: number;
}

interface ExecutionData {
  status: string;
  execution_complete: boolean;
  duration_seconds?: number | null;
  return_code?: number | null;
  tests: TestItem[];
  summary: ExecutionSummary;
  execution_metadata?: {
    command?: string;
    browser?: string;
  };
}

interface ReportsData {
  has_data: boolean;
  execution_summary?: any;
  failure_report?: {
    total_failures: number;
    failures: any[];
    flaky_tests: any[];
  };
  metrics_report?: {
    metrics?: {
      health_score?: number;
      health_status?: string;
    };
  };
  failure_analysis?: {
    root_causes?: string[];
    recommendations?: string[];
  };
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StatCard({
  icon: Icon,
  label,
  value,
  color,
}: {
  icon: React.ElementType;
  label: string;
  value: string | number;
  color: string;
}) {
  return (
    <div className="flex items-center gap-3 p-4 rounded-xl bg-zinc-900 border border-zinc-800">
      <div className={cn('p-2 rounded-lg', color.replace('text-', 'bg-').replace('-400', '-500/15'))}>
        <Icon className={cn('h-4 w-4', color)} />
      </div>
      <div>
        <p className={cn('text-xl font-bold tabular-nums', color)}>{value}</p>
        <p className="text-[11px] text-zinc-500">{label}</p>
      </div>
    </div>
  );
}

function PassRateRing({ passRate }: { passRate: number }) {
  const color = passRate >= 80 ? '#10b981' : passRate >= 50 ? '#f59e0b' : '#ef4444';
  const pct = Math.min(100, Math.max(0, passRate));
  return (
    <div className="flex flex-col items-center justify-center p-5 rounded-xl bg-zinc-900 border border-zinc-800">
      <div className="relative h-20 w-20">
        <svg className="h-full w-full -rotate-90" viewBox="0 0 36 36">
          <circle cx="18" cy="18" r="15.9" fill="none" stroke="#27272a" strokeWidth="3.5" />
          <circle
            cx="18" cy="18" r="15.9" fill="none"
            stroke={color}
            strokeWidth="3.5"
            strokeDasharray={`${pct} ${100 - pct}`}
            strokeDashoffset="25"
            strokeLinecap="round"
            className="transition-all duration-700"
          />
        </svg>
        <span className="absolute inset-0 flex items-center justify-center text-base font-bold text-zinc-200">
          {Math.round(pct)}%
        </span>
      </div>
      <p className="text-[11px] text-zinc-500 mt-2 font-medium">Pass Rate</p>
    </div>
  );
}

function TestRow({ test }: { test: TestItem }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div
      className={cn(
        'rounded-lg border transition-all duration-200',
        test.status === 'passed' && 'border-emerald-500/20 bg-emerald-500/5',
        test.status === 'failed' && 'border-red-500/25 bg-red-500/5',
        test.status === 'skipped' && 'border-zinc-700/50 bg-zinc-900/30',
      )}
    >
      <div
        className="flex items-center gap-3 px-3 py-2.5 cursor-pointer"
        onClick={() => test.error && setExpanded((e) => !e)}
      >
        {test.status === 'passed'  && <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />}
        {test.status === 'failed'  && <XCircle      className="h-4 w-4 text-red-400 shrink-0" />}
        {test.status === 'skipped' && <SkipForward  className="h-4 w-4 text-zinc-500 shrink-0" />}

        <span className="text-xs text-zinc-200 flex-1 truncate font-medium">{test.name}</span>

        {test.browser && (
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 shrink-0">
            {test.browser}
          </span>
        )}

        {typeof test.duration === 'number' && (
          <span className="text-[10px] font-mono text-zinc-500 shrink-0">
            {test.duration < 1000 ? `${test.duration}ms` : `${(test.duration / 1000).toFixed(1)}s`}
          </span>
        )}

        {test.error && (
          <span className="text-zinc-500 shrink-0">
            {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          </span>
        )}
      </div>
      {expanded && test.error && (
        <div className="px-3 pb-3">
          <pre className="text-[10px] font-mono text-red-300 bg-red-950/30 border border-red-900/40 rounded p-2 overflow-x-auto max-h-32 whitespace-pre-wrap break-all">
            {test.error}
          </pre>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function ExecutionReportPanel({ runId }: { runId: string }) {
  const [execData, setExecData] = useState<ExecutionData | null>(null);
  const [reportsData, setReportsData] = useState<ReportsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeSection, setActiveSection] = useState<'results' | 'failures' | 'metrics'>('results');

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    const apiBase = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
    try {
      const [exRes, rpRes] = await Promise.all([
        fetch(`${apiBase}/api/v1/runs/${runId}/execution`),
        fetch(`${apiBase}/api/v1/runs/${runId}/reports`),
      ]);

      if (exRes.ok) setExecData(await exRes.json());
      if (rpRes.ok) setReportsData(await rpRes.json());
    } catch (e: any) {
      setError(e.message ?? 'Failed to load reports');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, [runId]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-4">
        <div className="h-8 w-8 border-2 border-violet-500 border-t-transparent rounded-full animate-spin" />
        <p className="text-sm text-zinc-500">Loading execution reports…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3 text-red-400">
        <AlertCircle className="h-10 w-10" />
        <p className="text-sm font-semibold">Failed to load reports</p>
        <p className="text-xs text-zinc-500">{error}</p>
        <button
          onClick={fetchData}
          className="mt-2 flex items-center gap-2 text-xs px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors"
        >
          <RefreshCw className="h-3.5 w-3.5" /> Retry
        </button>
      </div>
    );
  }

  if (!execData || !execData.execution_complete) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-zinc-600 gap-3">
        <FileText className="h-10 w-10 animate-pulse" />
        <p className="text-sm font-medium text-zinc-500">Reports will appear after test execution completes.</p>
      </div>
    );
  }

  const { summary, tests, execution_metadata, duration_seconds, return_code } = execData;
  const failures = reportsData?.failure_report?.failures ?? [];
  const failureAnalysis = reportsData?.failure_analysis;
  const metricsReport = reportsData?.metrics_report;

  const SECTIONS = [
    { id: 'results', label: 'Test Results', icon: CheckCircle2, count: summary.total },
    { id: 'failures', label: 'Failures', icon: XCircle, count: summary.failed },
    { id: 'metrics', label: 'Metrics', icon: Activity, count: null },
  ] as const;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-violet-500/15 border border-violet-500/30">
            <FileText className="h-5 w-5 text-violet-400" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-zinc-200">Execution Report</h2>
            <p className="text-[11px] text-zinc-500">
              {duration_seconds ? `Completed in ${duration_seconds.toFixed(1)}s` : 'Test execution finished'}
              {typeof return_code === 'number' && ` · Exit code ${return_code}`}
            </p>
          </div>
        </div>
        <button
          onClick={fetchData}
          className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-zinc-200 transition-colors border border-zinc-700"
        >
          <RefreshCw className="h-3 w-3" /> Refresh
        </button>
      </div>

      {/* Summary strip */}
      <div className="grid grid-cols-5 gap-3">
        <PassRateRing passRate={summary.pass_rate} />
        <StatCard icon={TrendingUp}   label="Total Tests"  value={summary.total}   color="text-zinc-300" />
        <StatCard icon={CheckCircle2} label="Passed"       value={summary.passed}  color="text-emerald-400" />
        <StatCard icon={XCircle}      label="Failed"       value={summary.failed}  color="text-red-400" />
        <StatCard icon={SkipForward}  label="Skipped"      value={summary.skipped} color="text-zinc-400" />
      </div>

      {/* Execution metadata bar */}
      {(execution_metadata?.command || execution_metadata?.browser) && (
        <div className="flex items-start gap-3 px-4 py-3 rounded-xl border border-zinc-800 bg-zinc-900/60">
          <Terminal className="h-4 w-4 text-zinc-500 shrink-0 mt-0.5" />
          <div className="space-y-0.5 min-w-0">
            {execution_metadata.command && (
              <p className="text-[11px] font-mono text-zinc-400 truncate">{execution_metadata.command}</p>
            )}
            {execution_metadata.browser && (
              <p className="text-[10px] text-zinc-600">Browser: {execution_metadata.browser}</p>
            )}
          </div>
        </div>
      )}

      {/* Section tabs */}
      <div className="flex gap-1 p-1 rounded-xl bg-zinc-900/80 border border-zinc-800">
        {SECTIONS.map((s) => (
          <button
            key={s.id}
            onClick={() => setActiveSection(s.id)}
            className={cn(
              'flex-1 flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg text-xs font-medium transition-all duration-200',
              activeSection === s.id
                ? 'bg-zinc-800 text-zinc-200 shadow-sm'
                : 'text-zinc-500 hover:text-zinc-300'
            )}
          >
            <s.icon className="h-3.5 w-3.5" />
            {s.label}
            {s.count !== null && (
              <span className={cn(
                'px-1.5 py-0.5 rounded-full text-[10px] font-bold',
                s.id === 'failures' && s.count > 0 ? 'bg-red-500/20 text-red-400' : 'bg-zinc-700 text-zinc-400'
              )}>
                {s.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Section content */}
      {activeSection === 'results' && (
        <div className="space-y-2">
          {tests.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-zinc-600 gap-2">
              <Layers className="h-8 w-8" />
              <p className="text-xs">No test result details available.</p>
              <p className="text-[11px] text-zinc-700">Playwright ran but result artifacts could not be parsed.</p>
            </div>
          ) : (
            <div className="space-y-1.5 max-h-[480px] overflow-y-auto pr-1">
              {tests.map((t) => <TestRow key={t.id} test={t} />)}
            </div>
          )}
        </div>
      )}

      {activeSection === 'failures' && (
        <div className="space-y-4">
          {summary.failed === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-emerald-500 gap-2">
              <CheckCircle2 className="h-10 w-10" />
              <p className="text-sm font-semibold text-emerald-400">No failures! All tests passed.</p>
            </div>
          ) : (
            <>
              {/* Failed tests list */}
              <div className="space-y-1.5 max-h-[300px] overflow-y-auto">
                {tests.filter((t) => t.status === 'failed').map((t) => (
                  <TestRow key={t.id} test={t} />
                ))}
              </div>

              {/* Failure analysis */}
              {failureAnalysis && (
                <div className="rounded-xl border border-red-900/40 bg-red-950/20 p-4 space-y-3">
                  <h4 className="text-xs font-semibold text-red-400 flex items-center gap-1.5">
                    <AlertCircle className="h-3.5 w-3.5" /> Failure Analysis
                  </h4>
                  {(failureAnalysis.root_causes || []).length > 0 && (
                    <div>
                      <p className="text-[11px] text-zinc-500 mb-1.5 font-medium uppercase tracking-wider">Root Causes</p>
                      <ul className="space-y-1">
                        {(failureAnalysis.root_causes || []).map((rc: string, i: number) => (
                          <li key={i} className="text-xs text-zinc-300 flex items-start gap-1.5">
                            <span className="text-red-500 shrink-0 mt-0.5">•</span> {rc}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {(failureAnalysis.recommendations || []).length > 0 && (
                    <div>
                      <p className="text-[11px] text-zinc-500 mb-1.5 font-medium uppercase tracking-wider">Recommendations</p>
                      <ul className="space-y-1">
                        {(failureAnalysis.recommendations || []).map((r: string, i: number) => (
                          <li key={i} className="text-xs text-zinc-300 flex items-start gap-1.5">
                            <span className="text-amber-400 shrink-0 mt-0.5">→</span> {r}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      )}

      {activeSection === 'metrics' && (
        <div className="space-y-4">
          {metricsReport ? (
            <>
              {/* Health score */}
              {metricsReport.metrics && (
                <div className="p-4 rounded-xl border border-zinc-800 bg-zinc-900">
                  <p className="text-xs font-semibold text-zinc-400 mb-3">Health Score</p>
                  <div className="flex items-center gap-4">
                    <div className="text-3xl font-bold tabular-nums text-violet-400">
                      {Math.round((metricsReport.metrics.health_score ?? 0) * 100)}
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-zinc-300 capitalize">
                        {metricsReport.metrics.health_status ?? 'unknown'}
                      </p>
                      <p className="text-xs text-zinc-500">Overall test suite health</p>
                    </div>
                  </div>
                  <div className="mt-3 h-2 bg-zinc-800 rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-violet-600 to-cyan-500 transition-all duration-700"
                      style={{ width: `${(metricsReport.metrics.health_score ?? 0) * 100}%` }}
                    />
                  </div>
                </div>
              )}

              {/* Pass / Fail bar */}
              <div className="p-4 rounded-xl border border-zinc-800 bg-zinc-900 space-y-3">
                <p className="text-xs font-semibold text-zinc-400">Pass / Fail Distribution</p>
                {summary.total > 0 && (
                  <div className="h-3 rounded-full overflow-hidden flex bg-zinc-800">
                    <div
                      className="bg-emerald-500 transition-all duration-700"
                      style={{ width: `${(summary.passed / summary.total) * 100}%` }}
                    />
                    <div
                      className="bg-red-500 transition-all duration-700"
                      style={{ width: `${(summary.failed / summary.total) * 100}%` }}
                    />
                    <div
                      className="bg-zinc-600 transition-all duration-700"
                      style={{ width: `${(summary.skipped / summary.total) * 100}%` }}
                    />
                  </div>
                )}
                <div className="flex gap-4 text-[11px]">
                  <span className="flex items-center gap-1.5 text-emerald-400"><span className="h-2 w-2 rounded-full bg-emerald-500 inline-block" /> Passed ({summary.passed})</span>
                  <span className="flex items-center gap-1.5 text-red-400"><span className="h-2 w-2 rounded-full bg-red-500 inline-block" /> Failed ({summary.failed})</span>
                  <span className="flex items-center gap-1.5 text-zinc-500"><span className="h-2 w-2 rounded-full bg-zinc-600 inline-block" /> Skipped ({summary.skipped})</span>
                </div>
              </div>
            </>
          ) : (
            <div className="flex flex-col items-center justify-center py-12 text-zinc-600 gap-2">
              <Activity className="h-8 w-8" />
              <p className="text-xs">Metrics data not available for this run.</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
