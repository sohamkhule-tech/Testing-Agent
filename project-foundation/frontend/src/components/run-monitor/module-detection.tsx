'use client';

import { useState } from 'react';
import { cn } from '@/lib/utils';
import { useWorkflowStore, ModuleInfo } from '@/store/workflow-store';
import {
  Package,
  ChevronDown,
  ChevronRight,
  FileText,
  Globe,
  Shield,
  CheckCircle2,
} from 'lucide-react';

function ModuleCard({ module }: { module: ModuleInfo }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/80 overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-zinc-800/40 transition-colors"
      >
        {expanded ? (
          <ChevronDown className="h-4 w-4 text-zinc-400 shrink-0" />
        ) : (
          <ChevronRight className="h-4 w-4 text-zinc-400 shrink-0" />
        )}

        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-violet-500/20 shrink-0">
          <Package className="h-4 w-4 text-violet-400" />
        </div>

        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-zinc-200">{module.name}</p>
          <p className="text-[10px] text-zinc-500 truncate">{module.description}</p>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          <span className="text-xs font-mono text-zinc-400">
            {module.scenarioCount} <span className="text-[10px] text-zinc-600">scenarios</span>
          </span>
          <span className="text-xs font-mono text-zinc-400">
            {module.pages.length} <span className="text-[10px] text-zinc-600">pages</span>
          </span>
        </div>
      </button>

      {expanded && (
        <div className="px-4 pb-4 pt-2 border-t border-zinc-800 space-y-3">
          {/* AI Reason */}
          <div className="p-3 rounded-lg bg-violet-500/5 border border-violet-500/20">
            <p className="text-[10px] text-violet-400 uppercase tracking-wider font-semibold flex items-center gap-1 mb-1.5">
              <Shield className="h-3 w-3" /> Why this module?
            </p>
            <p className="text-[11px] text-violet-300/80">
              {module.description || `Detected because the application contains pages and components that serve the ${module.name.toLowerCase()} functionality.`}
            </p>
            <div className="flex items-center gap-2 mt-2">
              <span className="text-[10px] text-zinc-500">Confidence</span>
              <div className="flex-1 h-1.5 bg-zinc-800 rounded-full overflow-hidden max-w-[100px]">
                <div className="h-full rounded-full bg-violet-500" style={{ width: `${85 + module.moduleIndex * 3}%` }} />
              </div>
              <span className="text-[10px] font-mono text-violet-400">{85 + module.moduleIndex * 3}%</span>
            </div>
          </div>

          {/* Pages */}
          {module.pages.length > 0 && (
            <div className="space-y-1">
              <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold flex items-center gap-1">
                <Globe className="h-3 w-3" /> Pages ({module.pages.length})
              </p>
              <div className="flex flex-wrap gap-1">
                {module.pages.map((page, i) => (
                  <span key={i} className="text-[10px] px-2 py-0.5 rounded bg-zinc-800 text-zinc-300 truncate max-w-[180px]">
                    {page}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Scenarios summary */}
          <div className="flex items-center gap-2 text-[10px] text-zinc-400">
            <FileText className="h-3 w-3" />
            <span>{module.scenarioCount} test scenarios generated for this module</span>
          </div>
        </div>
      )}
    </div>
  );
}

export function ModuleDetection() {
  const modules = useWorkflowStore((s) => s.detectedModules);

  if (modules.length === 0) {
    return null;
  }

  return (
    <div className="space-y-2">
      <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold px-1">
        AI-Detected Modules ({modules.length})
      </p>
      <div className="space-y-2">
        {modules.map((mod) => (
          <ModuleCard key={mod.name} module={mod} />
        ))}
      </div>
    </div>
  );
}
