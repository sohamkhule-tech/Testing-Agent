'use client';

import { useState } from 'react';
import { cn } from '@/lib/utils';
import { useWorkflowStore, ScenarioInfo } from '@/store/workflow-store';
import {
  ChevronDown,
  ChevronRight,
  AlertTriangle,
  Shield,
  Zap,
  Target,
  Info,
  FileText,
  Layers,
  Link2,
  Camera,
} from 'lucide-react';

const priorityColors: Record<string, string> = {
  critical: 'text-red-400 bg-red-500/15 border-red-500/30',
  high: 'text-orange-400 bg-orange-500/15 border-orange-500/30',
  medium: 'text-amber-400 bg-amber-500/15 border-amber-500/30',
  low: 'text-zinc-400 bg-zinc-800 border-zinc-700',
};

const riskColors: Record<string, string> = {
  high: 'text-red-400',
  medium: 'text-amber-400',
  low: 'text-emerald-400',
};

function ScenarioCard({ scenario }: { scenario: ScenarioInfo }) {
  const [expanded, setExpanded] = useState(false);

  const hasFullDetails = Boolean(scenario.description);

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/80 hover:border-zinc-700 transition-all duration-200 overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-zinc-800/40 transition-colors"
      >
        {expanded ? (
          <ChevronDown className="h-4 w-4 text-zinc-400 shrink-0" />
        ) : (
          <ChevronRight className="h-4 w-4 text-zinc-400 shrink-0" />
        )}

        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-500/15 text-blue-400 text-xs font-bold shrink-0">
          {scenario.id.replace('TC-', '')}
        </div>

        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-zinc-200 truncate">{scenario.title}</p>
          <p className="text-[10px] text-zinc-500 truncate">{scenario.module}</p>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <span className={cn(
            'text-[10px] px-2 py-0.5 rounded-full border font-medium',
            priorityColors[scenario.priority] ?? 'text-zinc-400 bg-zinc-800 border-zinc-700',
          )}>
            {scenario.priority}
          </span>
          <span className={cn(
            'text-[10px] font-medium flex items-center gap-1',
            riskColors[scenario.riskLevel] ?? 'text-zinc-400',
          )}>
            <Shield className="h-3 w-3" />
            {scenario.riskLevel}
          </span>
        </div>
      </button>

      {/* Expanded content */}
      {expanded && hasFullDetails && (
        <div className="px-4 pb-4 pt-2 border-t border-zinc-800 space-y-3">
          {/* Description */}
          {scenario.description && (
            <div className="space-y-1">
              <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold flex items-center gap-1">
                <Info className="h-3 w-3" /> Description
              </p>
              <p className="text-xs text-zinc-300">{scenario.description}</p>
            </div>
          )}

          {/* AI Reasoning */}
          {scenario.description && (
            <div className="p-2.5 rounded-lg bg-violet-500/10 border border-violet-500/20">
              <p className="text-[10px] text-violet-400 uppercase tracking-wider font-semibold flex items-center gap-1 mb-1">
                <Brain className="h-3 w-3" /> AI Reasoning
              </p>
              <p className="text-[11px] text-violet-300/80">
                This scenario was generated based on the <strong className="text-violet-200">{scenario.module}</strong> module.
                {scenario.priority === 'critical' && ' It covers a critical application flow that requires thorough validation.'}
                {scenario.riskLevel === 'high' && ' High risk due to potential impact on core functionality.'}
                {scenario.category === 'authentication' && ' Authentication scenarios ensure secure access control.'}
                {scenario.category === 'negative' && ' Negative testing validates error handling and input validation.'}
              </p>
            </div>
          )}

          {/* Metadata grid */}
          <div className="grid grid-cols-3 gap-2">
            <div className="p-2 rounded-lg bg-zinc-800/50">
              <p className="text-[10px] text-zinc-500">Category</p>
              <p className="text-xs font-medium text-zinc-200 capitalize">{scenario.category}</p>
            </div>
            <div className="p-2 rounded-lg bg-zinc-800/50">
              <p className="text-[10px] text-zinc-500">Target Page</p>
              <p className="text-xs font-medium text-zinc-200 truncate">{scenario.targetPage || 'N/A'}</p>
            </div>
            <div className="p-2 rounded-lg bg-zinc-800/50">
              <p className="text-[10px] text-zinc-500">Risk Level</p>
              <p className={cn('text-xs font-medium capitalize', riskColors[scenario.riskLevel])}>{scenario.riskLevel}</p>
            </div>
          </div>

          {/* Traceability */}
          <div className="p-2.5 rounded-lg bg-zinc-800/30 border border-zinc-800">
            <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold flex items-center gap-1 mb-1.5">
              <Link2 className="h-3 w-3" /> Traceability
            </p>
            <div className="flex items-center gap-2 text-[10px] text-zinc-400">
              <span className="px-1.5 py-0.5 rounded bg-zinc-800">{scenario.module}</span>
              <span className="text-zinc-600">→</span>
              <span className="px-1.5 py-0.5 rounded bg-zinc-800">{scenario.targetPage || 'Application'}</span>
              <span className="text-zinc-600">→</span>
              <span className="px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-400">{scenario.id}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Brain({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3Z" />
      <path d="M19 12v-1a3 3 0 0 0-3-3" />
      <path d="M5 12v-1a3 3 0 0 1 3-3" />
      <path d="M12 21v-6" />
      <path d="M9 21h6" />
    </svg>
  );
}

export function ScenarioCards() {
  const scenarios = useWorkflowStore((s) => s.generatedScenarios);
  const testPlanScenarios = useWorkflowStore((s) => s.testPlanScenarioCount);
  const testPlanGenerated = useWorkflowStore((s) => s.testPlanGenerated);
  const modules = useWorkflowStore((s) => s.detectedModules);

  if (scenarios.length === 0 && !testPlanGenerated) {
    return null;
  }

  const displayScenarios = scenarios.length > 0 ? scenarios : [];

  return (
    <div className="space-y-3">
      {/* Summary header */}
      <div className="flex items-center justify-between px-1">
        <p className="text-xs text-zinc-400">
          <span className="font-semibold text-zinc-200">{displayScenarios.length || testPlanScenarios}</span> scenarios across{' '}
          <span className="font-semibold text-zinc-200">{modules.length}</span> modules
        </p>
      </div>

      {/* Scenario cards */}
      <div className="space-y-2 max-h-[500px] overflow-y-auto pr-1">
        {displayScenarios.map((scenario) => (
          <ScenarioCard key={scenario.id} scenario={scenario} />
        ))}
        {displayScenarios.length === 0 && testPlanGenerated && (
          <div className="flex items-center justify-center py-8 text-zinc-500">
            <p className="text-xs">Scenarios will appear during generation...</p>
          </div>
        )}
      </div>
    </div>
  );
}
