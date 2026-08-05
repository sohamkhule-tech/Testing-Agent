'use client';

import { cn } from '@/lib/utils';
import { useWorkflowStore } from '@/store/workflow-store';
import {
  Layers,
  FileText,
  AlertTriangle,
  Shield,
  Zap,
  Eye,
  Lock,
  Sliders,
  Gauge,
  CheckCircle2,
} from 'lucide-react';

export function TestPlanSummary() {
  const modules = useWorkflowStore((s) => s.detectedModules);
  const scenarios = useWorkflowStore((s) => s.generatedScenarios);
  const testPlanScenarios = useWorkflowStore((s) => s.testPlanScenarioCount);
  const testPlanGenerated = useWorkflowStore((s) => s.testPlanGenerated);
  const confidence = useWorkflowStore((s) => s.confidenceMetrics);

  if (!testPlanGenerated && modules.length === 0) {
    return null;
  }

  const totalScenarios = scenarios.length || testPlanScenarios;
  const criticalCount = scenarios.filter((s) => s.priority === 'critical').length;
  const highCount = scenarios.filter((s) => s.priority === 'high').length;
  const mediumCount = scenarios.filter((s) => s.priority === 'medium').length;
  const lowCount = scenarios.filter((s) => s.priority === 'low').length;
  const functionalCount = scenarios.filter((s) => s.category === 'functional' || s.category === 'happy_path').length;
  const negativeCount = scenarios.filter((s) => s.category === 'negative').length;
  const boundaryCount = scenarios.filter((s) => s.category === 'boundary').length;
  const authCount = scenarios.filter((s) => s.category === 'authentication' || s.category === 'authorization').length;
  const securityCount = scenarios.filter((s) => s.category === 'security').length;

  const totalPages = modules.reduce((acc, m) => acc + m.pages.length, 0);
  const totalUIComponents = scenarios.length > 0 ? scenarios.length * 2 : 0;

  const automationCoverage = confidence.automationCoverage || (scenarios.length > 0 ? Math.round(((scenarios.length - lowCount) / scenarios.length) * 100) : 0);

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/80 p-4 space-y-4">
      <div className="flex items-center gap-2">
        <Gauge className="h-4 w-4 text-blue-400" />
        <p className="text-xs font-semibold text-zinc-200">AI Test Plan Summary</p>
        {testPlanGenerated && (
          <span className="ml-auto text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
            Generated
          </span>
        )}
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-4 gap-2">
        {[
          { label: 'Modules', value: modules.length, icon: Layers, color: 'text-violet-400' },
          { label: 'Pages', value: totalPages, icon: Eye, color: 'text-blue-400' },
          { label: 'UI Components', value: totalUIComponents, icon: Sliders, color: 'text-cyan-400' },
          { label: 'Scenarios', value: totalScenarios, icon: FileText, color: 'text-emerald-400' },
        ].map((s) => (
          <div key={s.label} className="p-2.5 rounded-lg bg-zinc-800/50 border border-zinc-800 text-center">
            <s.icon className={cn('h-4 w-4 mx-auto mb-1', s.color)} />
            <p className={cn('text-lg font-bold tabular-nums', s.color)}>{s.value}</p>
            <p className="text-[9px] text-zinc-500">{s.label}</p>
          </div>
        ))}
      </div>

      {/* Category breakdown */}
      {scenarios.length > 0 && (
        <div className="space-y-2">
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold">Scenario Breakdown</p>
          <div className="grid grid-cols-4 gap-2">
            {[
              { label: 'Functional', value: functionalCount, color: 'text-blue-400' },
              { label: 'Negative', value: negativeCount, color: 'text-red-400' },
              { label: 'Boundary', value: boundaryCount, color: 'text-amber-400' },
              { label: 'Auth/Security', value: authCount + securityCount, color: 'text-purple-400' },
            ].map((s) => (
              <div key={s.label} className="p-2 rounded-lg bg-zinc-800/30">
                <p className={cn('text-sm font-bold tabular-nums', s.color)}>{s.value}</p>
                <p className="text-[9px] text-zinc-500">{s.label}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Priority breakdown */}
      {scenarios.length > 0 && (
        <div className="space-y-2">
          <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold">Priority Distribution</p>
          <div className="space-y-1.5">
            {[
              { label: 'Critical', value: criticalCount, color: 'bg-red-500' },
              { label: 'High', value: highCount, color: 'bg-orange-500' },
              { label: 'Medium', value: mediumCount, color: 'bg-amber-500' },
              { label: 'Low', value: lowCount, color: 'bg-zinc-500' },
            ].map((s) => (
              <div key={s.label} className="flex items-center gap-2">
                <span className="text-[10px] text-zinc-400 w-14 shrink-0">{s.label}</span>
                <div className="flex-1 h-2 bg-zinc-800 rounded-full overflow-hidden">
                  <div
                    className={cn('h-full rounded-full transition-all duration-500', s.color)}
                    style={{ width: `${(s.value / Math.max(totalScenarios, 1)) * 100}%` }}
                  />
                </div>
                <span className="text-[10px] font-mono text-zinc-400 w-8 text-right">{s.value}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Coverage */}
      {automationCoverage > 0 && (
        <div className="p-3 rounded-lg bg-emerald-500/5 border border-emerald-500/20">
          <div className="flex items-center justify-between mb-1">
            <span className="text-[10px] text-emerald-400 uppercase tracking-wider font-semibold flex items-center gap-1">
              <Zap className="h-3 w-3" /> Estimated Automation Coverage
            </span>
            <span className="text-sm font-bold text-emerald-400">{automationCoverage}%</span>
          </div>
          <div className="h-2 bg-zinc-800 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full bg-gradient-to-r from-emerald-600 to-emerald-400"
              style={{ width: `${automationCoverage}%` }}
            />
          </div>
          <p className="text-[10px] text-zinc-500 mt-1.5">
            {automationCoverage >= 90 ? 'Excellent automation potential' : automationCoverage >= 70 ? 'Good automation coverage' : 'Moderate automation coverage'}
            {' — '}{totalScenarios - lowCount} of {totalScenarios} scenarios are automatable
          </p>
        </div>
      )}
    </div>
  );
}
