'use client';

import { useState, useMemo, useEffect, useRef } from 'react';
import { cn } from '@/lib/utils';
import { useWorkflowStore, type TimelineEntry } from '@/store/workflow-store';
import {
  Code2,
  Terminal,
  Clock,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Zap,
  Activity,
  Box,
  FileCode,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';

const CODE_GEN_EVENT_TYPES = new Set([
  'code_generation_started',
  'code_generation_completed',
  'code_generation_failed',
  'loading_test_plan',
  'test_plan_loaded',
  'loading_inventory',
  'building_prompts',
  'prompts_prepared',
  'sending_llm_request',
  'waiting_for_llm_response',
  'received_llm_response',
  'parsing_response',
  'json_parsed',
  'ir_validation_started',
  'ir_validation_success',
  'ir_validation_failed',
  'ir_auto_repair_started',
  'ir_auto_repair_success',
  'planning_project_structure',
  'project_structure_planned',
  'generating_page_object',
  'page_object_generated',
  'generating_test_file',
  'test_file_generated',
  'generating_fixture',
  'fixture_generated',
  'generating_helper',
  'helper_generated',
  'generating_config',
  'config_generated',
  'formatting_code',
  'code_formatted',
  'packaging_project',
  'project_packaged',
  'file_started',
  'file_completed',
  'current_activity_update',
  'generation_metrics_update',
  'generation_progress_update',
]);

interface LogEntry {
  id: string;
  timestamp: Date;
  level: 'info' | 'success' | 'warning' | 'error';
  message: string;
  stage?: string;
  icon?: React.ElementType;
}

function formatTimestamp(date: Date): string {
  return date.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  const seconds = Math.floor(ms / 1000);
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m > 0 ? `${m}m ${s.toString().padStart(2, '0')}s` : `${s}s`;
}

import { useRunLogs } from '@/hooks/use-api';

export function CodeGenActivityStream() {
  const runId = useWorkflowStore((s) => s.runId);
  const timeline = useWorkflowStore((s) => s.timeline);
  const progress = useWorkflowStore((s) => s.codeGenerationProgress);
  const startedAt = useWorkflowStore((s) => s.codeGenerationStartedAt);
  const error = useWorkflowStore((s) => s.codeGenerationError);

  const { data: logsData } = useRunLogs(runId ?? '');
  
  const [elapsedMs, setElapsedMs] = useState(0);
  const [isExpanded, setIsExpanded] = useState(true);

  const isGenerating = progress > 0 && progress < 100 && !error;
  const isFailed = !!error;
  const isComplete = progress === 100 && !error;

  // Live elapsed timer
  useEffect(() => {
    if (!startedAt || (!isGenerating && !isComplete && !isFailed)) {
      setElapsedMs(0);
      return;
    }
    const start = new Date(startedAt).getTime();
    const tick = () => setElapsedMs(Date.now() - start);
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [startedAt, isGenerating, isComplete, isFailed]);

  // Filter and convert timeline or REST backend logs to log entries
  const logEntries = useMemo(() => {
    const timelineEntries = timeline
      .filter((t) => CODE_GEN_EVENT_TYPES.has(t.type))
      .map((entry): LogEntry => {
        let level: LogEntry['level'] = 'info';
        let message = entry.message;
        let icon = Activity;

        if (entry.type.includes('_failed') || entry.type.includes('error')) {
          level = 'error';
          icon = AlertCircle;
        } else if (
          entry.type.includes('_completed') ||
          entry.type.includes('_success') ||
          entry.type.includes('_generated')
        ) {
          level = 'success';
          icon = CheckCircle2;
        } else if (entry.type.includes('waiting') || entry.type.includes('_started')) {
          level = 'info';
          icon = Loader2;
        }

        if (entry.data?.label) {
          message = entry.data.label as string;
        }

        return {
          id: entry.id,
          timestamp: new Date(entry.timestamp),
          level,
          message,
          icon,
        };
      });

    if (timelineEntries.length > 0) return timelineEntries;

    // Fallback: use the structured events array from REST API (reconstructed from artifacts)
    const events = logsData?.events ?? [];

    if (events.length > 0) {
      return events
        .filter((ev) => ev.message && ev.message.trim().length > 0)
        .map((ev, index): LogEntry => {
          const msg = ev.message ?? '';
          const lvl = ev.level ?? 'info';
          let level: LogEntry['level'] = 'info';
          let icon = Activity;

          if (lvl === 'error' || msg.includes('failed') || msg.includes('Error') || msg.includes('❌')) {
            level = 'error';
            icon = AlertCircle;
          } else if (
            lvl === 'success' ||
            msg.includes('✅') ||
            msg.includes('complete') ||
            msg.includes('generated') ||
            msg.includes('approved')
          ) {
            level = 'success';
            icon = CheckCircle2;
          } else if (msg.includes('...') || msg.includes('🤖') || msg.includes('🔧') || msg.includes('💭')) {
            level = 'info';
            icon = Loader2;
          }

          let timestamp = new Date();
          if (ev.timestamp) {
            try { timestamp = new Date(ev.timestamp); } catch { /* ignore */ }
          }

          return {
            id: `ev-${index}`,
            timestamp,
            level,
            message: msg,
            stage: ev.stage,
            icon,
          };
        });
    }

    // Last fallback: stage_logs string lines
    if (!logsData?.stage_logs) return [];
    const codeGenLogs = logsData.stage_logs['code_generation'] || [];
    const allLogs =
      codeGenLogs.length > 0
        ? codeGenLogs
        : Object.values(logsData.stage_logs).flat();

    return allLogs.map((line: string, index: number): LogEntry => {
      let level: LogEntry['level'] = 'info';
      let icon = Activity;

      if (line.includes('[error]') || line.includes('failed') || line.includes('Error')) {
        level = 'error';
        icon = AlertCircle;
      } else if (
        line.includes('[info]') &&
        (line.includes('completed') ||
          line.includes('success') ||
          line.includes('installed') ||
          line.includes('generated'))
      ) {
        level = 'success';
        icon = CheckCircle2;
      } else if (line.includes('[warning]')) {
        level = 'warning';
        icon = AlertCircle;
      }

      let message = line;
      let timestamp = new Date();

      const timeMatch = line.match(/^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})/);
      if (timeMatch) {
        timestamp = new Date(timeMatch[1]);
        message = line.replace(/^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\s*/, '');
      }

      return {
        id: `rest-log-${index}`,
        timestamp,
        level,
        message,
        icon,
      };
    });
  }, [timeline, logsData]);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Terminal className="h-4 w-4 text-cyan-400" />
          <h3 className="text-sm font-semibold text-zinc-200">Live Activity Log</h3>
          {isGenerating && (
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500" />
            </span>
          )}
          {logEntries.length > 0 && (
            <span className="text-[10px] font-mono bg-zinc-800 text-zinc-400 px-1.5 py-0.5 rounded">
              {logEntries.length} entries
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 text-xs text-zinc-400">
            <Clock className="h-3.5 w-3.5" />
            <span className="font-mono">{formatDuration(elapsedMs)}</span>
          </div>
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="p-1 hover:bg-zinc-800 rounded transition-colors"
          >
            {isExpanded ? (
              <ChevronUp className="h-4 w-4 text-zinc-400" />
            ) : (
              <ChevronDown className="h-4 w-4 text-zinc-400" />
            )}
          </button>
        </div>
      </div>

      {/* Log Console */}
      {isExpanded && (
        <LogConsole entries={logEntries} isStreaming={isGenerating} />
      )}

      {/* Progress Summary */}
      <ProgressSummary progress={progress} isGenerating={isGenerating} isFailed={isFailed} />
    </div>
  );
}

function LogConsole({ entries, isStreaming }: { entries: LogEntry[]; isStreaming: boolean }) {
  const consoleRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);

  // Auto-scroll to bottom when new entries arrive
  useEffect(() => {
    if (autoScroll && consoleRef.current) {
      consoleRef.current.scrollTop = consoleRef.current.scrollHeight;
    }
  }, [entries, autoScroll]);

  // Detect manual scroll
  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const { scrollTop, scrollHeight, clientHeight } = e.currentTarget;
    const isAtBottom = Math.abs(scrollHeight - clientHeight - scrollTop) < 10;
    setAutoScroll(isAtBottom);
  };

  return (
    <div className="relative rounded-lg border border-zinc-800 bg-zinc-950 overflow-hidden">
      {/* Console header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-zinc-800 bg-zinc-900/50">
        <div className="flex items-center gap-2">
          <div className="flex gap-1">
            <div className="w-2.5 h-2.5 rounded-full bg-red-500/80" />
            <div className="w-2.5 h-2.5 rounded-full bg-amber-500/80" />
            <div className="w-2.5 h-2.5 rounded-full bg-emerald-500/80" />
          </div>
          <span className="text-[10px] text-zinc-500 font-mono">console.log</span>
        </div>
        <div className="flex items-center gap-2">
          {!autoScroll && (
            <button
              onClick={() => setAutoScroll(true)}
              className="text-[10px] text-cyan-400 hover:text-cyan-300 transition-colors"
            >
              Jump to bottom ↓
            </button>
          )}
          {isStreaming && (
            <div className="flex items-center gap-1.5">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500" />
              </span>
              <span className="text-[10px] text-zinc-500">LIVE</span>
            </div>
          )}
        </div>
      </div>

      {/* Console content */}
      <div
        ref={consoleRef}
        onScroll={handleScroll}
        className="h-[400px] overflow-y-auto p-2 space-y-0.5 font-mono text-[11px]"
        style={{
          scrollBehavior: autoScroll ? 'smooth' : 'auto',
        }}
      >
        {entries.length === 0 ? (
          <div className="flex items-center justify-center h-full text-zinc-600">
            <div className="text-center space-y-2">
              <Terminal className="h-8 w-8 mx-auto opacity-50" />
              <p className="text-xs">No activity data</p>
              <p className="text-[10px] text-zinc-700">Restart backend and refresh to load logs</p>
            </div>
          </div>
        ) : (
          entries.map((entry) => {
            const Icon = entry.icon || Activity;
            return (
              <div
                key={entry.id}
                className={cn(
                  'flex items-start gap-2 px-2 py-1 rounded hover:bg-zinc-900/50 transition-colors',
                  entry.level === 'error' && 'bg-red-950/20',
                )}
              >
                {/* Timestamp */}
                <span className="text-zinc-600 shrink-0 w-20 select-all">
                  {formatTimestamp(entry.timestamp)}
                </span>

                {/* Stage badge */}
                {entry.stage && (
                  <span className="shrink-0 text-[9px] font-mono uppercase px-1 py-0.5 rounded bg-zinc-800 text-zinc-500 w-24 text-center truncate">
                    {entry.stage.replace('_', ' ')}
                  </span>
                )}

                {/* Icon */}
                <Icon
                  className={cn(
                    'h-3.5 w-3.5 shrink-0 mt-0.5',
                    entry.level === 'error' && 'text-red-400',
                    entry.level === 'success' && 'text-emerald-400',
                    entry.level === 'warning' && 'text-amber-400',
                    entry.level === 'info' && 'text-cyan-400',
                    entry.icon === Loader2 && 'animate-spin',
                  )}
                />

                {/* Message */}
                <span
                  className={cn(
                    'flex-1',
                    entry.level === 'error' && 'text-red-300',
                    entry.level === 'success' && 'text-emerald-300',
                    entry.level === 'warning' && 'text-amber-300',
                    entry.level === 'info' && 'text-zinc-400',
                  )}
                >
                  {entry.message}
                </span>
              </div>
            );
          })
        )}
      </div>

      {/* Scroll indicator */}
      {!autoScroll && (
        <div className="absolute bottom-0 left-0 right-0 h-12 bg-gradient-to-t from-zinc-950 to-transparent pointer-events-none" />
      )}
    </div>
  );
}

function ProgressSummary({
  progress,
  isGenerating,
  isFailed,
}: {
  progress: number;
  isGenerating: boolean;
  isFailed: boolean;
}) {
  const milestones = [
    { progress: 5, label: 'Prompt Preparation', color: 'bg-violet-500' },
    { progress: 12, label: 'LLM Generation', color: 'bg-violet-500' },
    { progress: 25, label: 'IR Validation', color: 'bg-blue-500' },
    { progress: 40, label: 'Project Structure', color: 'bg-cyan-500' },
    { progress: 55, label: 'Page Objects', color: 'bg-emerald-500' },
    { progress: 70, label: 'Tests', color: 'bg-amber-500' },
    { progress: 82, label: 'Fixtures & Config', color: 'bg-pink-500' },
    { progress: 91, label: 'Formatting', color: 'bg-orange-500' },
    { progress: 100, label: 'Complete', color: 'bg-emerald-500' },
  ];

  const currentMilestone = milestones.reduce((prev, curr) => {
    return progress >= curr.progress ? curr : prev;
  }, milestones[0]);

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 space-y-3">
      {/* Progress bar */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-medium text-zinc-400">Generation Progress</span>
          <span className="text-xs font-mono font-bold text-zinc-300">{progress}%</span>
        </div>
        <div className="h-2 rounded-full bg-zinc-800 overflow-hidden">
          <div
            className={cn(
              'h-full rounded-full transition-all duration-700 ease-out',
              isFailed ? 'bg-red-500' : isGenerating ? currentMilestone.color : 'bg-emerald-500',
            )}
            style={{ width: `${Math.max(2, progress)}%` }}
          />
        </div>
      </div>

      {/* Milestones */}
      <div className="flex flex-wrap gap-2">
        {milestones.map((milestone) => {
          const isReached = progress >= milestone.progress;
          const isCurrent =
            progress >= milestone.progress &&
            progress < (milestones[milestones.indexOf(milestone) + 1]?.progress || 101);

          return (
            <div
              key={milestone.label}
              className={cn(
                'flex items-center gap-1.5 px-2 py-1 rounded text-[10px] font-medium transition-all',
                isReached ? 'bg-zinc-800 border border-zinc-700' : 'bg-zinc-900 border border-zinc-800',
                isCurrent && isGenerating && 'ring-1 ring-cyan-500/50',
              )}
            >
              {isReached ? (
                <CheckCircle2 className="h-3 w-3 text-emerald-400" />
              ) : (
                <div className="h-3 w-3 rounded-full border border-zinc-700" />
              )}
              <span className={cn(isReached ? 'text-zinc-300' : 'text-zinc-600')}>
                {milestone.label}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
