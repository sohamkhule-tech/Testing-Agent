'use client';

/**
 * LLMActivity — Live LLM call progress panel.
 * Shows each LLM call, its purpose, token counts, duration, and status.
 */

import { cn } from '@/lib/utils';
import { useWorkflowStore, LLMCall } from '@/store/workflow-store';
import { Bot, Loader2, CheckCircle2, XCircle, Cpu, Zap } from 'lucide-react';

function formatDuration(startedAt: string, completedAt?: string): string {
  const start = new Date(startedAt).getTime();
  const end   = completedAt ? new Date(completedAt).getTime() : Date.now();
  const ms    = end - start;
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function LLMCallCard({ call }: { call: LLMCall }) {
  return (
    <div className={cn(
      'rounded-xl border px-4 py-3 space-y-3 transition-all duration-300',
      call.status === 'running'   && 'border-blue-500/50 bg-blue-500/5 animate-pulse-border',
      call.status === 'completed' && 'border-zinc-800 bg-zinc-900/50',
      call.status === 'failed'    && 'border-red-500/50 bg-red-500/5',
    )}>
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className={cn(
          'flex h-8 w-8 items-center justify-center rounded-lg shrink-0',
          call.status === 'running'   && 'bg-blue-500/20',
          call.status === 'completed' && 'bg-emerald-500/20',
          call.status === 'failed'    && 'bg-red-500/20',
        )}>
          {call.status === 'running'   && <Loader2 className="h-4 w-4 text-blue-400 animate-spin" />}
          {call.status === 'completed' && <CheckCircle2 className="h-4 w-4 text-emerald-400" />}
          {call.status === 'failed'    && <XCircle className="h-4 w-4 text-red-400" />}
        </div>

        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-zinc-200 truncate">{call.purpose ?? 'LLM Call'}</p>
          {call.model && (
            <p className="text-[10px] text-zinc-500 font-mono">{call.model}</p>
          )}
        </div>

        <div className="text-right shrink-0">
          <p className={cn(
            'text-sm font-mono tabular-nums',
            call.status === 'running'   && 'text-blue-400',
            call.status === 'completed' && 'text-emerald-400',
            call.status === 'failed'    && 'text-red-400',
          )}>
            {formatDuration(call.startedAt, call.completedAt)}
          </p>
          <p className="text-[10px] text-zinc-600 capitalize">{call.status}</p>
        </div>
      </div>

      {/* Token bar */}
      {call.status === 'running' && (
        <div className="space-y-1.5">
          <div className="flex items-center gap-2">
            <div className="flex-1 h-1 bg-zinc-800 rounded-full overflow-hidden">
              <div className="h-full bg-gradient-to-r from-blue-600 to-blue-400 rounded-full animate-progress-indeterminate" />
            </div>
            <span className="text-[10px] text-zinc-500 shrink-0">Processing...</span>
          </div>
        </div>
      )}

      {call.status === 'completed' && (
        <div className="flex items-center gap-4 text-[10px] text-zinc-500">
          {call.promptTokens && (
            <span className="flex items-center gap-1">
              <Cpu className="h-3 w-3" /> Prompt: <span className="text-zinc-300 font-mono">{call.promptTokens?.toLocaleString()}</span>
            </span>
          )}
          {call.responseTokens && (
            <span className="flex items-center gap-1">
              <Zap className="h-3 w-3" /> Response: <span className="text-zinc-300 font-mono">{call.responseTokens?.toLocaleString()}</span>
            </span>
          )}
        </div>
      )}
    </div>
  );
}

export function LLMActivity() {
  const calls = useWorkflowStore((s) => s.llmCalls);
  const running = calls.filter((c) => c.status === 'running').length;

  if (calls.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-zinc-600 gap-3">
        <Bot className="h-10 w-10 animate-pulse" />
        <p className="text-xs">LLM calls will appear here when test design begins.</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {running > 0 && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-blue-500/10 border border-blue-500/30">
          <Loader2 className="h-3.5 w-3.5 text-blue-400 animate-spin shrink-0" />
          <span className="text-xs text-blue-300">
            {running} LLM call{running > 1 ? 's' : ''} in progress...
          </span>
        </div>
      )}
      <div className="space-y-2">
        {calls.map((call) => (
          <LLMCallCard key={call.id} call={call} />
        ))}
      </div>
    </div>
  );
}
