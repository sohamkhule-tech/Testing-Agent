'use client';

import { useEffect, useState } from 'react';
import { cn } from '@/lib/utils';
import { useWorkflowStore, ModuleInfo, ScenarioInfo } from '@/store/workflow-store';
import {
  Layers,
  FileText,
  AlertTriangle,
  Zap,
  TrendingUp,
} from 'lucide-react';

function StatCard({
  label,
  value,
  icon: Icon,
  color,
  prev,
}: {
  label: string;
  value: number;
  icon: React.ElementType;
  color: string;
  prev?: number;
}) {
  const [animate, setAnimate] = useState(false);

  useEffect(() => {
    if (value > 0) {
      setAnimate(true);
      const t = setTimeout(() => setAnimate(false), 600);
      return () => clearTimeout(t);
    }
  }, [value]);

  return (
    <div className={cn(
      'relative p-3 rounded-xl border transition-all duration-300',
      animate ? 'border-blue-500/40 bg-blue-500/10' : 'border-border bg-muted',
    )}>
      <div className="flex items-center justify-between mb-1.5">
        <Icon className={cn('h-4 w-4', color)} />
        {animate && (
          <span className="text-[10px] text-blue-400 animate-pulse">+</span>
        )}
      </div>
      <p className={cn('text-2xl font-bold tabular-nums transition-colors duration-300', animate ? 'text-blue-300' : color)}>
        {value}
      </p>
      <p className="text-[10px] text-muted-foreground mt-0.5">{label}</p>
    </div>
  );
}

export function LiveStats() {
  const stages = useWorkflowStore((s) => s.stages);
  const modules = useWorkflowStore((s) => s.detectedModules);
  const scenarios = useWorkflowStore((s) => s.generatedScenarios);
  const testPlanScenarios = useWorkflowStore((s) => s.testPlanScenarioCount);
  const confidence = useWorkflowStore((s) => s.confidenceMetrics);
  const testStage = stages.find((s) => s.id === 'test_design');
  const isActive = testStage?.status === 'running' || modules.length > 0 || scenarios.length > 0;

  if (!isActive && testPlanScenarios === 0) {
    return null;
  }

  const criticalCount = scenarios.filter((s) => s.priority === 'critical').length;

  return (
    <div className="grid grid-cols-4 gap-2">
      <StatCard
        label="Modules"
        value={modules.length}
        icon={Layers}
        color="text-violet-400"
      />
      <StatCard
        label="Scenarios"
        value={scenarios.length || testPlanScenarios}
        icon={FileText}
        color="text-blue-400"
      />
      <StatCard
        label="Critical"
        value={criticalCount}
        icon={AlertTriangle}
        color="text-red-400"
      />
      <StatCard
        label="Auto Coverage"
        value={confidence.automationCoverage}
        icon={Zap}
        color="text-emerald-400"
      />
    </div>
  );
}
