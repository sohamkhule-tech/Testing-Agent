'use client';

import { useEffect, useRef } from 'react';
import { cn } from '@/lib/utils';
import { useWorkflowStore, AIReasoningStep, ModuleInfo, ScenarioInfo } from '@/store/workflow-store';
import {
  Brain,
  Package,
  FileText,
  BarChart3,
  Zap,
  CheckCircle2,
  Loader2,
  Box,
  ListChecks,
} from 'lucide-react';

type LogEntry = {
  id: string;
  icon: React.ElementType;
  label: string;
  detail?: string;
  timestamp: string;
  status?: 'running' | 'completed' | 'pending' | 'failed';
};

export function AIDecisionLog() {
  const steps = useWorkflowStore((s) => s.aiReasoningSteps);
  const modules = useWorkflowStore((s) => s.detectedModules);
  const scenarios = useWorkflowStore((s) => s.generatedScenarios);
  const progress = useWorkflowStore((s) => s.analysisProgress);
  const bottomRef = useRef<HTMLDivElement>(null);

  const entries: LogEntry[] = [];

  steps.forEach((s) => {
    entries.push({
      id: `step-${s.step}`,
      icon: Brain,
      label: s.label,
      detail: s.description,
      timestamp: new Date().toISOString(),
      status: s.status === 'failed' ? 'completed' : s.status,
    });
  });

  modules.forEach((m) => {
    entries.push({
      id: `module-${m.name}`,
      icon: Package,
      label: `${m.name} Module Created`,
      detail: `${m.scenarioCount} scenarios, ${m.pages.length} pages`,
      timestamp: new Date().toISOString(),
      status: 'completed',
    });
  });

  scenarios.filter((s, i) => i < 5 || i === scenarios.length - 1).forEach((s) => {
    entries.push({
      id: `scenario-${s.id}`,
      icon: FileText,
      label: `${s.id}: ${s.title}`,
      detail: `${s.module} | ${s.priority} | ${s.riskLevel} risk`,
      timestamp: new Date().toISOString(),
      status: 'completed',
    });
  });

  if (progress && !entries.some(e => e.id === 'progress')) {
    entries.push({
      id: 'progress',
      icon: progress.phase === 'complete' ? CheckCircle2 : Loader2,
      label: progress.label,
      detail: `${progress.progress}%`,
      timestamp: new Date().toISOString(),
      status: progress.phase === 'complete' ? 'completed' : 'running',
    });
  }

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [entries.length]);

  if (entries.length === 0) {
    return null;
  }

  return (
    <div className="border border-border rounded-xl bg-muted/50 overflow-hidden">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border bg-muted">
        <ListChecks className="h-3.5 w-3.5 text-blue-400" />
        <span className="text-[10px] text-muted-foreground uppercase tracking-wider font-semibold">AI Activity Log</span>
        <span className="ml-auto text-[10px] text-muted-foreground font-mono">{entries.length} events</span>
      </div>
      <div className="max-h-48 overflow-y-auto py-1">
        {entries.map((entry) => {
          const Icon = entry.icon;
          return (
            <div
              key={entry.id}
              className={cn(
                'flex items-start gap-2.5 px-3 py-2 hover:bg-accent/60 transition-colors',
                entry.status === 'running' && 'bg-blue-500/5',
              )}
            >
              <Icon className={cn(
                'h-3.5 w-3.5 mt-0.5 shrink-0',
                entry.status === 'running' ? 'text-blue-400 animate-spin' : 'text-muted-foreground',
              )} />
              <div className="flex-1 min-w-0">
                <p className={cn(
                  'text-[11px] font-medium truncate',
                  entry.status === 'running' ? 'text-blue-300' : 'text-foreground',
                )}>
                  {entry.label}
                </p>
                {entry.detail && (
                  <p className="text-[10px] text-muted-foreground truncate">{entry.detail}</p>
                )}
              </div>
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
