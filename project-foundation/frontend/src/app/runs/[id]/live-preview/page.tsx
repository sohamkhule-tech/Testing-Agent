'use client';

/**
 * Dedicated Live Browser Preview Page (Pop-out Window Mode)
 *
 * Opens the crawler live feed in a separate, dedicated window or browser tab.
 * Uses SSE to stream real-time browser frames, cursor actions, current URL, and crawl statistics.
 */

import { use } from 'react';
import Link from 'next/link';
import { cn } from '@/lib/utils';
import { useRun } from '@/hooks/use-api';
import { useWorkflowSSE } from '@/hooks/use-workflow-sse';
import { useWorkflowStore } from '@/store/workflow-store';
import { LiveBrowserPreview, CrawlStats, BrowserActivity } from '@/components/run-monitor/browser-activity';
import { EventTimeline } from '@/components/run-monitor/event-timeline';
import {
  ArrowLeft,
  Globe,
  Wifi,
  WifiOff,
  Clock,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Loader2,
  Maximize2,
  ExternalLink,
  Layers,
  Activity,
} from 'lucide-react';

function StatusChip({ status }: { status: string }) {
  const map: Record<string, { label: string; icon: React.ElementType; cls: string }> = {
    running:   { label: 'Live Crawling', icon: Loader2,       cls: 'text-blue-400 bg-blue-500/15 border-blue-500/40 [&_svg]:animate-spin' },
    completed: { label: 'Completed',     icon: CheckCircle2,  cls: 'text-emerald-400 bg-emerald-500/15 border-emerald-500/40' },
    failed:    { label: 'Failed',        icon: XCircle,       cls: 'text-red-400 bg-red-500/15 border-red-500/40' },
    pending:   { label: 'Pending',       icon: Clock,         cls: 'text-zinc-400 bg-zinc-800 border-zinc-700' },
    paused:    { label: 'Paused',        icon: AlertTriangle, cls: 'text-amber-400 bg-amber-500/15 border-amber-400/40 [&_svg]:animate-pulse' },
  };
  const cfg = map[status] ?? map['pending'];
  const Icon = cfg.icon;
  return (
    <span className={cn('inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-medium', cfg.cls)}>
      <Icon className="h-3.5 w-3.5" />
      {cfg.label}
    </span>
  );
}

export default function LivePreviewPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data: run } = useRun(id);
  const { connected, error: sseError } = useWorkflowSSE(id);

  const overallStatus = useWorkflowStore((s) => s.overallStatus);
  const browser = useWorkflowStore((s) => s.browserActivity);

  return (
    <div className="min-h-screen bg-[#07070b] text-foreground flex flex-col">
      {/* ── Top Header ─────────────────────────────────────────────── */}
      <header className="border-b border-zinc-800 bg-[#0a0a0f]/95 backdrop-blur-xl px-4 py-2.5 flex items-center justify-between sticky top-0 z-50">
        <div className="flex items-center gap-3 min-w-0">
          <Link
            href={`/runs/${id}`}
            className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-zinc-100 transition-colors bg-zinc-900 border border-zinc-800 px-2.5 py-1.5 rounded-lg"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            <span>Main Run Dashboard</span>
          </Link>

          <div className="h-4 w-px bg-zinc-800" />

          <div className="flex items-center gap-2 min-w-0">
            <Globe className="h-4 w-4 text-blue-400 shrink-0" />
            <span className="text-xs font-semibold text-zinc-200">Live Crawler View</span>
            <span className="font-mono text-xs text-zinc-500 truncate hidden sm:inline">
              ({run?.run_id ?? id})
            </span>
          </div>
        </div>

        {/* Controls and Status */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            {sseError ? (
              <WifiOff className="h-3.5 w-3.5 text-red-400" />
            ) : connected ? (
              <>
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
                </span>
                <span className="text-[11px] text-emerald-400 font-medium">Live Feed</span>
              </>
            ) : (
              <Wifi className="h-3.5 w-3.5 text-zinc-600 animate-pulse" />
            )}
          </div>

          <StatusChip status={overallStatus} />
        </div>
      </header>

      {/* ── Main Viewport Content ─────────────────────────────────── */}
      <main className="flex-1 container py-4 space-y-4 max-w-7xl mx-auto">
        {/* Main Live Preview Box */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-950 shadow-2xl overflow-hidden">
          <LiveBrowserPreview runId={id} />
        </div>

        {/* Crawl Stats & Live Activity */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2 space-y-4">
            <div className="rounded-xl border border-zinc-800 bg-zinc-950/70 p-4 space-y-3">
              <h3 className="text-xs font-semibold text-zinc-300 flex items-center gap-2">
                <Layers className="h-4 w-4 text-blue-400" /> Discovered Inventory Metrics
              </h3>
              <CrawlStats />
            </div>

            <div className="rounded-xl border border-zinc-800 bg-zinc-950/70 p-4 space-y-3">
              <h3 className="text-xs font-semibold text-zinc-300 flex items-center gap-2">
                <Activity className="h-4 w-4 text-violet-400" /> Live Browser Navigation Activity
              </h3>
              <BrowserActivity runId={id} />
            </div>
          </div>

          {/* Right side live event timeline */}
          <div className="rounded-xl border border-zinc-800 bg-zinc-950/70 h-[380px] flex flex-col overflow-hidden">
            <EventTimeline />
          </div>
        </div>
      </main>
    </div>
  );
}
