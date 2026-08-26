'use client';

/**
 * CodeGenerationProgress — Live progress bar and generated file list.
 * ExecutionMonitor — Live test results table with pass/fail indicators.
 */

import { cn } from '@/lib/utils';
import { useWorkflowStore, GeneratedFile, TestResult } from '@/store/workflow-store';
import {
  Code2,
  FileCode2,
  CheckCircle2,
  XCircle,
  Clock,
  Play,
  TrendingUp,
  AlertCircle,
  SkipForward,
} from 'lucide-react';

// ---------------------------------------------------------------------------
// CodeGenerationProgress
// ---------------------------------------------------------------------------

function FileItem({ file }: { file: GeneratedFile }) {
  const ext = file.name.split('.').pop() ?? '';
  const extColors: Record<string, string> = {
    ts:   'text-blue-400',
    js:   'text-yellow-400',
    json: 'text-amber-400',
    md:   'text-purple-400',
    yml:  'text-sky-400',
    yaml: 'text-sky-400',
  };

  return (
    <div className="flex items-center gap-2.5 px-3 py-2 rounded-lg hover:bg-accent transition-colors group animate-fade-in">
      <FileCode2 className={cn('h-3.5 w-3.5 shrink-0', extColors[ext] ?? 'text-muted-foreground')} />
      <span className="text-xs font-mono text-foreground flex-1 truncate">{file.path || file.name}</span>
      <span className="text-[10px] text-muted-foreground shrink-0 group-hover:text-muted-foreground transition-colors">
        {new Date(file.timestamp).toLocaleTimeString()}
      </span>
    </div>
  );
}

export function CodeGenerationProgress() {
  const files    = useWorkflowStore((s) => s.generatedFiles);
  const progress = useWorkflowStore((s) => s.codeGenerationProgress);
  const stages   = useWorkflowStore((s) => s.stages);
  const codeStage= stages.find((s) => s.id === 'code_generation');
  const isActive = codeStage?.status === 'running' || files.length > 0;

  if (!isActive) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-muted-foreground gap-3">
        <Code2 className="h-10 w-10 animate-pulse" />
        <p className="text-xs">Generated files will appear here during code generation.</p>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {/* Progress bar */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs">
          <span className="text-muted-foreground font-medium">Generation Progress</span>
          <span className="font-mono text-foreground">{progress}%</span>
        </div>
        <div className="h-2.5 bg-muted rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-500 bg-gradient-to-r from-violet-600 via-blue-500 to-cyan-400"
            style={{ width: `${progress}%` }}
          />
        </div>
        <p className="text-[10px] text-muted-foreground">
          {files.length} file{files.length !== 1 ? 's' : ''} generated
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-2">
        {[
          { label: 'Files Generated', value: files.length,                       color: 'text-violet-400' },
          { label: 'Test Files',      value: files.filter(f => f.name.includes('.spec')).length, color: 'text-blue-400' },
          { label: 'Page Objects',    value: files.filter(f => f.name.includes('page')).length,  color: 'text-cyan-400' },
        ].map((s) => (
          <div key={s.label} className="p-3 rounded-xl bg-muted border border-border text-center">
            <p className={cn('text-xl font-bold tabular-nums', s.color)}>{s.value}</p>
            <p className="text-[10px] text-muted-foreground mt-0.5">{s.label}</p>
          </div>
        ))}
      </div>

      {/* File list */}
      {files.length > 0 && (
        <div className="space-y-1 border border-border rounded-xl overflow-hidden">
          <div className="px-3 py-2 border-b border-border bg-muted">
            <span className="text-[10px] text-muted-foreground uppercase tracking-wider font-semibold">Generated Files</span>
          </div>
          <div className="max-h-52 overflow-y-auto py-1">
            {files.map((file) => (
              <FileItem key={file.path || file.timestamp} file={file} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ExecutionMonitor
// ---------------------------------------------------------------------------

function TestRow({ result }: { result: TestResult }) {
  return (
    <div className={cn(
      'flex items-center gap-3 px-3 py-2.5 rounded-lg border transition-all duration-200 animate-fade-in',
      result.status === 'passed'  && 'border-emerald-500/20 bg-emerald-500/5',
      result.status === 'failed'  && 'border-red-500/25 bg-red-500/5',
      result.status === 'skipped' && 'border-border bg-muted/30',
    )}>
      {result.status === 'passed'  && <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />}
      {result.status === 'failed'  && <XCircle      className="h-4 w-4 text-red-400 shrink-0" />}
      {result.status === 'skipped' && <SkipForward  className="h-4 w-4 text-muted-foreground shrink-0" />}

      <span className="text-xs text-foreground flex-1 truncate font-medium">{result.name}</span>

      {result.error && (
        <span className="text-[10px] text-red-400 truncate max-w-[180px] shrink-0">{result.error}</span>
      )}

      {result.duration && (
        <span className="text-[10px] font-mono text-muted-foreground shrink-0">
          {result.duration < 1000 ? `${result.duration}ms` : `${(result.duration / 1000).toFixed(1)}s`}
        </span>
      )}
    </div>
  );
}

export function ExecutionMonitor() {
  const results = useWorkflowStore((s) => s.testResults);
  const stats   = useWorkflowStore((s) => s.executionStats);
  const stages  = useWorkflowStore((s) => s.stages);
  const exStage = stages.find((s) => s.id === 'execution');
  const isActive= exStage?.status === 'running' || exStage?.status === 'completed' || results.length > 0;

  if (!isActive) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-muted-foreground gap-3">
        <Play className="h-10 w-10 animate-pulse" />
        <p className="text-xs">Test execution results will appear here once tests run.</p>
      </div>
    );
  }

  // Show "completed but no results" state when stage done but 0 tests
  if (exStage?.status === 'completed' && results.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-amber-500 gap-3">
        <AlertCircle className="h-10 w-10" />
        <p className="text-sm font-semibold text-amber-400">Execution completed — no test results captured</p>
        <p className="text-xs text-muted-foreground">Playwright ran but results.json was not generated. Check the generated tests directory for details.</p>
      </div>
    );
  }


  const passRate = stats.total > 0 ? (stats.passed / stats.total) * 100 : 0;

  return (
    <div className="space-y-5">
      {/* Pass rate ring + stats */}
      <div className="grid grid-cols-4 gap-3">
        <div className="col-span-1 flex flex-col items-center justify-center p-4 rounded-xl bg-muted border border-border">
          <div className="relative h-16 w-16">
            <svg className="h-full w-full -rotate-90" viewBox="0 0 36 36">
              <circle cx="18" cy="18" r="15.9" fill="none" stroke="#27272a" strokeWidth="3.5" />
              <circle
                cx="18" cy="18" r="15.9" fill="none"
                stroke={passRate >= 80 ? '#10b981' : passRate >= 50 ? '#f59e0b' : '#ef4444'}
                strokeWidth="3.5"
                strokeDasharray={`${passRate} ${100 - passRate}`}
                strokeDashoffset="25"
                strokeLinecap="round"
                className="transition-all duration-700"
              />
            </svg>
            <span className="absolute inset-0 flex items-center justify-center text-sm font-bold text-foreground">
              {Math.round(passRate)}%
            </span>
          </div>
          <p className="text-[10px] text-muted-foreground mt-1">Pass Rate</p>
        </div>

        <div className="col-span-3 grid grid-rows-2 grid-cols-2 gap-2">
          {[
            { label: 'Total',   value: stats.total,   color: 'text-foreground',   icon: TrendingUp },
            { label: 'Passed',  value: stats.passed,  color: 'text-emerald-400',icon: CheckCircle2 },
            { label: 'Failed',  value: stats.failed,  color: 'text-red-400',    icon: XCircle },
            { label: 'Skipped', value: stats.skipped, color: 'text-muted-foreground',   icon: SkipForward },
          ].map((s) => (
            <div key={s.label} className="flex items-center gap-2 p-2.5 rounded-lg bg-muted border border-border">
              <s.icon className={cn('h-3.5 w-3.5 shrink-0', s.color)} />
              <div>
                <p className={cn('text-base font-bold tabular-nums', s.color)}>{s.value}</p>
                <p className="text-[10px] text-muted-foreground">{s.label}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Results list */}
      {results.length > 0 && (
        <div className="space-y-1 max-h-72 overflow-y-auto">
          {results.map((r) => <TestRow key={r.id} result={r} />)}
        </div>
      )}

      {exStage?.status === 'running' && results.length === 0 && (
        <div className="flex items-center justify-center gap-2 py-8 text-muted-foreground">
          <AlertCircle className="h-4 w-4 animate-pulse" />
          <span className="text-xs">Running tests... results will appear here</span>
        </div>
      )}
    </div>
  );
}
