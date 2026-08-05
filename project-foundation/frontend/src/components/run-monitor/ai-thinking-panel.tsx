import { useEffect, useState } from 'react';
import { cn } from '@/lib/utils';
import { useWorkflowStore, AIReasoningStep, AnalysisProgress, ConfidenceMetrics } from '@/store/workflow-store';
import {
  Brain,
  Loader2,
  CheckCircle2,
  XCircle,
  BarChart3,
  Shield,
  Zap,
  Target,
  TrendingUp,
  Clock,
} from 'lucide-react';

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  if (mins > 0) {
    return `${mins}m ${secs.toString().padStart(2, '0')}s`;
  }
  return `${secs}s`;
}

function ReasoningStepRow({ step }: { step: AIReasoningStep }) {
  return (
    <div
      className={cn(
        'flex items-start gap-3 px-3 py-2.5 rounded-lg transition-all duration-300',
        step.status === 'running' && 'bg-blue-500/5 border border-blue-500/20',
        step.status === 'completed' && 'bg-emerald-500/5 border border-emerald-500/10',
        step.status === 'pending' && 'opacity-50',
      )}
    >
      <div className="mt-0.5 shrink-0">
        {step.status === 'running' && <Loader2 className="h-4 w-4 text-blue-400 animate-spin" />}
        {step.status === 'completed' && <CheckCircle2 className="h-4 w-4 text-emerald-400" />}
        {step.status === 'pending' && <div className="h-4 w-4 rounded-full border-2 border-zinc-700" />}
        {step.status === 'failed' && <XCircle className="h-4 w-4 text-red-400" />}
      </div>
      <div className="flex-1 min-w-0">
        <p className={cn(
          'text-xs font-medium',
          step.status === 'running' && 'text-blue-300',
          step.status === 'completed' && 'text-emerald-300',
          step.status === 'pending' && 'text-zinc-500',
        )}>
          {step.label}
        </p>
        <p className={cn(
          'text-[10px] mt-0.5',
          step.status === 'running' && 'text-blue-400/70',
          step.status === 'completed' && 'text-emerald-400/70',
          step.status === 'pending' && 'text-zinc-600',
        )}>
          {step.description}
        </p>
      </div>
      {step.status === 'running' && (
        <span className="text-[10px] text-blue-400/60 shrink-0 animate-pulse">Thinking...</span>
      )}
    </div>
  );
}

function ConfidenceGauge({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-[10px]">
        <span className="text-zinc-400">{label}</span>
        <span className={cn('font-mono font-bold', color)}>{value}%</span>
      </div>
      <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
        <div
          className={cn('h-full rounded-full transition-all duration-700', color.replace('text', 'bg'))}
          style={{ width: `${value}%` }}
        />
      </div>
    </div>
  );
}

export function AIThinkingPanel() {
  const steps = useWorkflowStore((s) => s.aiReasoningSteps);
  const progress = useWorkflowStore((s) => s.analysisProgress);
  const confidence = useWorkflowStore((s) => s.confidenceMetrics);
  const generated = useWorkflowStore((s) => s.testPlanGenerated);
  const stages = useWorkflowStore((s) => s.stages);
  const storeElapsed = useWorkflowStore((s) => s.testDesignElapsed);
  const testDesignStartedAt = useWorkflowStore((s) => s.testDesignStartedAt);

  const testDesignStage = stages.find((s) => s.id === 'test_design' || s.id === 'test_plan');
  const isRunning = testDesignStage?.status === 'running' || (!generated && steps.length > 0);

  const [liveElapsed, setLiveElapsed] = useState(0);

  useEffect(() => {
    if (!isRunning) return;

    const startTime = testDesignStartedAt
      ? new Date(testDesignStartedAt).getTime()
      : (testDesignStage?.startedAt ? new Date(testDesignStage.startedAt).getTime() : Date.now());

    const interval = setInterval(() => {
      const now = Date.now();
      const diffSecs = Math.max(0, Math.floor((now - startTime) / 1000));
      setLiveElapsed(diffSecs);
    }, 1000);

    return () => clearInterval(interval);
  }, [isRunning, testDesignStartedAt, testDesignStage?.startedAt]);

  const displayElapsed = isRunning ? liveElapsed : (storeElapsed > 0 ? storeElapsed : liveElapsed);

  const hasContent = steps.length > 0 || progress !== null;

  if (!hasContent && !generated) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-zinc-600 gap-3">
        <Brain className="h-10 w-10 animate-pulse" />
        <p className="text-xs">AI reasoning will appear here when test design begins.</p>
      </div>
    );
  }

  const activeSteps = steps.filter((s) => s.status === 'running');
  const completedSteps = steps.filter((s) => s.status === 'completed');

  return (
    <div className="space-y-4">
      {/* Status header with live / final timer */}
      {!generated && activeSteps.length > 0 && (
        <div className="flex items-center justify-between px-3 py-2 rounded-lg bg-blue-500/10 border border-blue-500/30">
          <div className="flex items-center gap-2">
            <Loader2 className="h-3.5 w-3.5 text-blue-400 animate-spin shrink-0" />
            <span className="text-xs font-medium text-blue-300">AI analyzing application...</span>
          </div>
          <div className="flex items-center gap-1.5 text-xs font-mono font-semibold text-blue-300 bg-blue-950/60 px-2 py-0.5 rounded border border-blue-500/40">
            <Clock className="h-3 w-3 text-blue-400 animate-pulse" />
            <span>{formatDuration(displayElapsed)}</span>
          </div>
        </div>
      )}

      {generated && (
        <div className="flex items-center justify-between px-3 py-2 rounded-lg bg-emerald-500/10 border border-emerald-500/30">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
            <span className="text-xs font-medium text-emerald-300">Analysis complete — {completedSteps.length || steps.length} steps</span>
          </div>
          {displayElapsed > 0 && (
            <div className="flex items-center gap-1.5 text-xs font-mono font-semibold text-emerald-300 bg-emerald-950/60 px-2 py-0.5 rounded border border-emerald-500/40">
              <Clock className="h-3 w-3 text-emerald-400" />
              <span>{formatDuration(displayElapsed)}</span>
            </div>
          )}
        </div>
      )}

      {/* Progress bar */}
      {progress && (
        <div className="space-y-1.5">
          <div className="flex items-center justify-between text-xs">
            <span className="text-zinc-400">{progress.label}</span>
            <span className="font-mono text-zinc-500">{progress.progress}%</span>
          </div>
          <div className="h-2 bg-zinc-800 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500 bg-gradient-to-r from-blue-600 via-violet-500 to-emerald-400"
              style={{ width: `${progress.progress}%` }}
            />
          </div>
        </div>
      )}

      {/* Reasoning steps */}
      {steps.length > 0 && (
        <div className="space-y-1">
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold px-1">AI Reasoning</p>
          <div className="space-y-1">
            {steps.map((step) => (
              <ReasoningStepRow key={step.step} step={step} />
            ))}
          </div>
        </div>
      )}

      {/* Confidence dashboard */}
      {(confidence.inventoryConfidence > 0 || confidence.scenarioConfidence > 0) && (
        <div className="space-y-3 p-3 rounded-xl border border-zinc-800 bg-zinc-900/50">
          <div className="flex items-center gap-2">
            <TrendingUp className="h-3.5 w-3.5 text-violet-400" />
            <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold">AI Confidence</p>
          </div>
          <div className="space-y-2">
            {confidence.inventoryConfidence > 0 && (
              <ConfidenceGauge label="Inventory Confidence" value={confidence.inventoryConfidence} color="text-blue-400" />
            )}
            {confidence.scenarioConfidence > 0 && (
              <ConfidenceGauge label="Scenario Confidence" value={confidence.scenarioConfidence} color="text-emerald-400" />
            )}
            {confidence.automationCoverage > 0 && (
              <ConfidenceGauge label="Automation Coverage" value={confidence.automationCoverage} color="text-violet-400" />
            )}
            {confidence.riskCoverage > 0 && (
              <ConfidenceGauge label="Risk Coverage" value={confidence.riskCoverage} color="text-amber-400" />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
