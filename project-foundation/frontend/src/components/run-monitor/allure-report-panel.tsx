'use client';

/**
 * AllureReportPanel — Renders the run's generated Allure report.
 *
 * Consumes:
 *   - Zustand workflow store report state (SSE-driven live updates)
 *   - GET /api/v1/runs/{runId}/report/status for authoritative availability
 *   - GET /api/v1/runs/{runId}/report to embed the report in an iframe
 *
 * States: loading → generating / unavailable / failed / generated.
 * In dark mode the report is adapted with a best-effort invert filter;
 * "Open in new tab" always renders the report natively.
 *
 * The "Regenerate" button calls POST /api/v1/runs/{runId}/report/regenerate
 * which re-runs the Allure CLI and synthesises proper result files (with
 * execution steps and real durations) when the allure-playwright reporter
 * did not write them.  This fixes the "No information about test execution
 * is available" and "0s duration" issues in the Allure test case detail view.
 */

import React, { useEffect, useState } from 'react';
import { useTheme } from 'next-themes';
import { cn } from '@/lib/utils';
import {
  BarChart2,
  Download,
  ExternalLink,
  FileText,
  Loader2,
  RefreshCw,
  RotateCcw,
  AlertCircle,
} from 'lucide-react';

const apiBase = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

type ReportStatus = 'idle' | 'generating' | 'generated' | 'failed' | 'unavailable';

interface ReportStatusData {
  status: ReportStatus;
  report_available: boolean;
  report_path?: string | null;
}

export function AllureReportPanel({ runId }: { runId: string }) {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === 'dark';

  const [fetchedStatus, setFetchedStatus] = useState<ReportStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [regenerating, setRegenerating] = useState(false);
  const [regenError, setRegenError] = useState<string | null>(null);

  const reportUrl = `${apiBase}/api/v1/runs/${runId}/report`;
  const iframeSrc = `${reportUrl}?v=${refreshKey}`;

  const fetchStatus = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${apiBase}/api/v1/runs/${runId}/report/status`);
      if (!res.ok) throw new Error(`Status request failed (${res.status})`);
      const data: ReportStatusData = await res.json();
      setFetchedStatus(data.status);
    } catch (e: any) {
      setError(e.message ?? 'Failed to check report availability');
      setFetchedStatus(null);
    } finally {
      setLoading(false);
    }
  };

  /** Call the regeneration endpoint, then reload the status + iframe. */
  const handleRegenerate = async () => {
    setRegenerating(true);
    setRegenError(null);
    try {
      const res = await fetch(
        `${apiBase}/api/v1/runs/${runId}/report/regenerate`,
        { method: 'POST' },
      );
      const data = await res.json();
      if (!res.ok || data.status !== 'generated') {
        setRegenError(data.error ?? data.detail ?? 'Regeneration failed');
      } else {
        // Bump refreshKey → triggers fetchStatus + iframe reload
        setRefreshKey((k) => k + 1);
      }
    } catch (e: any) {
      setRegenError(e.message ?? 'Regeneration request failed');
    } finally {
      setRegenerating(false);
    }
  };

  useEffect(() => { fetchStatus(); }, [runId, refreshKey]);

  // Iframe remounts when theme flips so the CSS filter applies cleanly.
  const iframeKey = `${isDark ? 'dark' : 'light'}-${refreshKey}`;

  if (loading && fetchedStatus === null) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-3">
        <div className="h-7 w-7 border-2 border-violet-500 border-t-transparent rounded-full animate-spin" />
        <p className="text-sm text-muted-foreground">Checking report availability…</p>
      </div>
    );
  }

  const status = fetchedStatus;

  if (error && status === null) {
    return (
      <div className="flex flex-col items-center justify-center py-14 gap-3 text-red-400">
        <AlertCircle className="h-10 w-10" />
        <p className="text-sm font-semibold">Failed to load report status</p>
        <p className="text-xs text-muted-foreground">{error}</p>
        <button
          onClick={() => setRefreshKey((k) => k + 1)}
          className="mt-2 flex items-center gap-2 text-xs px-3 py-1.5 rounded-lg bg-muted hover:bg-secondary text-foreground transition-colors"
        >
          <RefreshCw className="h-3.5 w-3.5" /> Retry
        </button>
      </div>
    );
  }

  if (status === 'unavailable' || status === 'idle') {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-muted-foreground gap-4 bg-card rounded-xl border border-border shadow-xs">
        <FileText className="h-10 w-10 text-muted-foreground/60" />
        <div className="text-center space-y-1">
          <p className="text-sm font-semibold text-foreground">Report Not Generated Yet</p>
          <p className="text-xs text-muted-foreground max-w-md">
            Click below to generate the interactive Allure HTML report from execution results.
          </p>
        </div>
        <button
          onClick={handleRegenerate}
          disabled={regenerating}
          className="flex items-center gap-2 text-xs px-4 py-2 rounded-lg bg-violet-600 hover:bg-violet-700 text-white font-semibold shadow-xs transition-colors disabled:opacity-50"
        >
          {regenerating ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <RotateCcw className="h-4 w-4" />
          )}
          {regenerating ? 'Generating Report…' : 'Generate Allure Report'}
        </button>
        {regenError && (
          <p className="text-xs text-red-600 dark:text-red-400 text-center max-w-sm mt-1">{regenError}</p>
        )}
      </div>
    );
  }

  if (status === 'generating') {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-muted-foreground gap-3 bg-card rounded-xl border border-border">
        <Loader2 className="h-9 w-9 animate-spin text-violet-600 dark:text-violet-400" />
        <p className="text-sm font-medium text-foreground">Generating Allure report…</p>
      </div>
    );
  }

  if (status === 'failed') {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-red-600 dark:text-red-400 gap-3 bg-card rounded-xl border border-border">
        <AlertCircle className="h-10 w-10" />
        <p className="text-sm font-semibold">Allure report generation failed</p>
        <div className="flex items-center gap-2 mt-2">
          <button
            onClick={() => setRefreshKey((k) => k + 1)}
            className="flex items-center gap-2 text-xs px-3 py-1.5 rounded-lg bg-muted hover:bg-secondary text-foreground transition-colors border border-border"
          >
            <RefreshCw className="h-3.5 w-3.5" /> Retry
          </button>
          <button
            onClick={handleRegenerate}
            disabled={regenerating}
            className="flex items-center gap-2 text-xs px-3 py-1.5 rounded-lg bg-violet-600 hover:bg-violet-700 text-white font-medium transition-colors disabled:opacity-50"
          >
            {regenerating
              ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
              : <RotateCcw className="h-3.5 w-3.5" />}
            {regenerating ? 'Regenerating…' : 'Regenerate Report'}
          </button>
        </div>
        {regenError && (
          <p className="text-xs text-red-600 dark:text-red-400 text-center max-w-sm">{regenError}</p>
        )}
      </div>
    );
  }

  // status === 'generated'
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between p-4 bg-card rounded-xl border border-border shadow-2xs">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-violet-500/15 border border-violet-500/30">
            <BarChart2 className="h-5 w-5 text-violet-600 dark:text-violet-400" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-foreground">Allure Report</h3>
            <p className="text-[11px] text-muted-foreground font-medium">Test results, trends, and failure analysis</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {/* Regenerate */}
          <button
            onClick={handleRegenerate}
            disabled={regenerating}
            title="Re-generate the report with corrected execution details and durations"
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-violet-50 dark:bg-violet-600/15 hover:bg-violet-100 dark:hover:bg-violet-600/30 border border-violet-200 dark:border-violet-500/30 text-violet-700 dark:text-violet-300 font-semibold transition-colors disabled:opacity-50"
          >
            {regenerating
              ? <Loader2 className="h-3 w-3 animate-spin" />
              : <RotateCcw className="h-3 w-3" />}
            {regenerating ? 'Regenerating…' : 'Regenerate'}
          </button>
          <button
            onClick={() => setRefreshKey((k) => k + 1)}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-secondary hover:bg-muted text-foreground font-medium transition-colors border border-border"
          >
            <RefreshCw className="h-3 w-3" /> Refresh
          </button>
          <a
            href={reportUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-blue-50 dark:bg-blue-600/20 hover:bg-blue-100 dark:hover:bg-blue-600/35 border border-blue-200 dark:border-blue-500/40 text-blue-700 dark:text-blue-300 font-semibold transition-colors"
          >
            <ExternalLink className="h-3 w-3" /> Open in New Tab
          </a>
          <a
            href={`${apiBase}/api/v1/runs/${runId}/report/download`}
            download
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-emerald-50 dark:bg-emerald-600/20 hover:bg-emerald-100 dark:hover:bg-emerald-600/35 border border-emerald-200 dark:border-emerald-500/40 text-emerald-700 dark:text-emerald-300 font-semibold transition-colors"
            title="Download complete Allure report as a ZIP archive"
          >
            <Download className="h-3 w-3" /> Download Report
          </a>
        </div>
      </div>

      {regenError && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg border border-red-500/30 bg-red-500/10 text-xs text-red-400">
          <AlertCircle className="h-3.5 w-3.5 shrink-0" />
          <span>{regenError}</span>
        </div>
      )}

      <div className="rounded-xl border border-border overflow-hidden bg-muted/40">
        <iframe
          key={iframeKey}
          src={iframeSrc}
          title="Allure Report"
          className={cn(
            'w-full h-[700px] border-0',
            isDark && 'invert-[0.92] hue-rotate-180'
          )}
        />
      </div>
    </div>
  );
}
