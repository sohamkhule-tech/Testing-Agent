'use client';

/**
 * EventTimeline — Live auto-scrolling chronological event log.
 *
 * Receives events from the Zustand store (which is populated from SSE).
 * Auto-scrolls to the newest entry. No polling.
 */

import { useEffect, useRef } from 'react';
import { cn } from '@/lib/utils';
import { useWorkflowStore, TimelineEntry } from '@/store/workflow-store';
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Info,
  Wifi,
  WifiOff,
} from 'lucide-react';

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString('en-US', {
      hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
    });
  } catch {
    return '--:--:--';
  }
}

function EntryIcon({ level }: { level: TimelineEntry['level'] }) {
  switch (level) {
    case 'success': return <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 shrink-0" />;
    case 'error':   return <XCircle      className="h-3.5 w-3.5 text-red-400 shrink-0" />;
    case 'warning': return <AlertTriangle className="h-3.5 w-3.5 text-amber-400 shrink-0" />;
    default:        return <Info         className="h-3.5 w-3.5 text-muted-foreground shrink-0" />;
  }
}

function TimelineItem({ entry, isNew }: { entry: TimelineEntry; isNew: boolean }) {
  return (
    <div
      className={cn(
        'flex items-start gap-2.5 py-1.5 px-3 rounded-md transition-all duration-300',
        isNew && 'bg-foreground/5 animate-slide-in-bottom',
        entry.level === 'error'   && 'bg-red-500/5',
        entry.level === 'warning' && 'bg-amber-500/5',
        entry.level === 'success' && 'bg-emerald-500/5',
      )}
    >
      <span className="text-[10px] text-muted-foreground font-mono shrink-0 mt-0.5 w-16">
        {formatTime(entry.timestamp)}
      </span>
      <EntryIcon level={entry.level} />
      <span
        className={cn(
          'text-xs leading-relaxed',
          entry.level === 'error'   && 'text-red-300',
          entry.level === 'warning' && 'text-amber-300',
          entry.level === 'success' && 'text-emerald-300',
          entry.level === 'info'    && 'text-foreground',
        )}
      >
        {entry.message}
      </span>
    </div>
  );
}

export function EventTimeline() {
  const timeline    = useWorkflowStore((s) => s.timeline);
  const connected   = useWorkflowStore((s) => s.sseConnected);
  const sseError    = useWorkflowStore((s) => s.sseError);
  const bottomRef   = useRef<HTMLDivElement>(null);
  const prevLen     = useRef(0);

  useEffect(() => {
    // Auto-scroll when new events arrive
    if (timeline.length > prevLen.current) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
    prevLen.current = timeline.length;
  }, [timeline.length]);

  const newIds = new Set(
    timeline.slice(-3).map((e) => e.id)
  );

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border">
        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Event Timeline
        </span>
        <div className="flex items-center gap-1.5">
          {sseError ? (
            <WifiOff className="h-3.5 w-3.5 text-red-400" />
          ) : connected ? (
            <Wifi className="h-3.5 w-3.5 text-emerald-400" />
          ) : (
            <Wifi className="h-3.5 w-3.5 text-muted-foreground animate-pulse" />
          )}
          <span className="text-[10px] text-muted-foreground">
            {sseError ? 'Disconnected' : connected ? 'Live' : 'Connecting...'}
          </span>
          <span className="text-[10px] text-muted-foreground ml-2">
            {timeline.length} events
          </span>
        </div>
      </div>

      {/* Events */}
      <div className="flex-1 overflow-y-auto min-h-0 py-1">
        {timeline.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-2 text-muted-foreground">
            <Wifi className="h-8 w-8 animate-pulse" />
            <p className="text-xs">Waiting for events...</p>
          </div>
        ) : (
          timeline.map((entry) => (
            <TimelineItem
              key={entry.id}
              entry={entry}
              isNew={newIds.has(entry.id)}
            />
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
