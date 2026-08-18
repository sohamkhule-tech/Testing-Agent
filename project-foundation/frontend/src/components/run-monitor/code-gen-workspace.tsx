'use client';

import { useState, useMemo, useEffect } from 'react';
import { cn } from '@/lib/utils';
import { useWorkflowStore, type TimelineEntry, type CurrentGeneratedFile } from '@/store/workflow-store';
import { LiveFileExplorer, LiveCodeViewer, type GenFile } from '@/components/run-monitor/live-code-viewer';
import { CodeGenActivityStream } from '@/components/run-monitor/code-gen-activity-stream';
import {
  LLMStatusCard,
  CurrentActivityPanel,
  LiveMetricsDashboard,
} from '@/components/run-monitor/code-gen-status-cards';
import {
  Code2,
  FileCode,
  AlertCircle,
  RefreshCw,
  Download,
  Clock,
} from 'lucide-react';

const CODEGEN_EVENT_TYPES = new Set([
  'code_generation_started',
  'code_generation_completed',
  'code_generation_failed',
  'loading_test_plan',
  'loading_inventory',
  'loading_screenshots',
  'building_prompts',
  'sending_llm_request',
  'waiting_for_llm_response',
  'received_llm_response',
  'parsing_response',
  'ir_generation_started',
  'ir_generated',
  'planning_project_structure',
  'generating_page_object',
  'generating_test_file',
  'generating_fixture',
  'generating_helper',
  'file_started',
  'file_progress',
  'file_completed',
  'file_generated',
  'validating_generated_code',
  'packaging_project',
  'playwright_generated',
]);

import { useGeneratedFiles } from '@/hooks/use-api';

export function CodeGenWorkspace() {
  const runId              = useWorkflowStore((s) => s.runId);
  const generatedFiles     = useWorkflowStore((s) => s.generatedFiles);
  const progress           = useWorkflowStore((s) => s.codeGenerationProgress);
  const error              = useWorkflowStore((s) => s.codeGenerationError);
  const startedAt          = useWorkflowStore((s) => s.codeGenerationStartedAt);

  // Fetch REST generated files for completed runs / page refresh
  const { data: restFilesData } = useGeneratedFiles(runId ?? '');

  const displayFiles = useMemo(() => {
    if (generatedFiles.length > 0) return generatedFiles;
    if (!restFilesData?.files) return [];

    const list: GenFile[] = [];
    const flatten = (items: any[]) => {
      for (const item of items) {
        if (item.type === 'file') {
          list.push({
            path: item.path,
            name: item.name,
            size_bytes: item.size_bytes,
          });
        } else if (item.children) {
          flatten(item.children);
        }
      }
    };
    flatten(restFilesData.files);
    return list;
  }, [generatedFiles, restFilesData]);

  const currentGenFile = useWorkflowStore((s) => s.currentGeneratedFile);
  const overallStatus = useWorkflowStore((s) => s.overallStatus);

  const [selectedFile, setSelectedFile] = useState<GenFile | null>(null);
  const [elapsedMs, setElapsedMs] = useState(0);

  // Auto-select first file when displayFiles loads
  useEffect(() => {
    if (!selectedFile && displayFiles.length > 0) {
      const preferred =
        displayFiles.find((f) => f.name.endsWith('.spec.ts')) ||
        displayFiles.find((f) => f.name === 'playwright.config.ts') ||
        displayFiles[0];
      if (preferred) setSelectedFile(preferred);
    }
  }, [displayFiles, selectedFile]);

  // Real-time auto-switch to currently generating file
  useEffect(() => {
    if (currentGenFile?.filename) {
      const match = displayFiles.find((f) => f.name === currentGenFile.filename || f.path.endsWith(currentGenFile.filename));
      if (match) {
        setSelectedFile(match);
      } else {
        setSelectedFile({
          path: `${currentGenFile.folder}/${currentGenFile.filename}`,
          name: currentGenFile.filename,
          file_type: currentGenFile.file_type,
          lines_of_code: undefined,
          size_bytes: undefined,
        });
      }
    }
  }, [currentGenFile, displayFiles]);

  const effectiveProgress = overallStatus === 'completed' ? 100 : progress;
  const isGenerating = effectiveProgress > 0 && effectiveProgress < 100 && !error;
  const isFailed = !!error;
  const isComplete = effectiveProgress === 100 && !error;

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

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="p-1.5 rounded-md bg-violet-500/10">
          <Code2 className="h-4 w-4 text-violet-400" />
        </div>
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-foreground">Playwright Code Generation</span>
            {isGenerating && <LivePulse />}
          </div>
          <p className="text-[11px] text-muted-foreground">
            {isFailed
              ? 'Generation failed — see details below'
              : isComplete
              ? 'Project generated and packaged'
              : 'Generating Playwright test automation project...'}
          </p>
        </div>
        <div className="text-right">
          <div className="text-xs font-mono text-muted-foreground flex items-center justify-end gap-1">
            <Clock className="h-3 w-3" />
            {formatDuration(elapsedMs)}
          </div>
          <div className="text-[10px] text-muted-foreground">elapsed</div>
        </div>
      </div>

      {/* Failure recovery */}
      {isFailed && <FailureCard error={error} />}

      {/* Live generation telemetry — only shown while actively generating so a
          completed/idle run does not reserve space for streaming placeholders. */}
      {isGenerating && (
        <>
          {/* Live Activity Stream & Status Cards */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {/* LLM Status Card */}
            <div className="lg:col-span-1">
              <LLMStatusCard />
            </div>

            {/* Current Activity Panel */}
            <div className="lg:col-span-2">
              <CurrentActivityPanel />
            </div>
          </div>

          {/* Live Metrics Dashboard */}
          <LiveMetricsDashboard />
        </>
      )}

      {/* Activity Log (collapses when idle) + Generation Progress */}
      <CodeGenActivityStream />

      {/* File Explorer + Code Viewer */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        <div className="lg:col-span-2">
          <LiveFileExplorer
            files={displayFiles as any[]}
            onSelectFile={setSelectedFile}
            selectedPath={selectedFile?.path}
            isGenerating={isGenerating}
          />
        </div>
        <div className="lg:col-span-3 min-h-[420px]">
          <LiveCodeViewer
            file={selectedFile}
            isLoading={false}
            isStreaming={isGenerating}
          />
        </div>
      </div>

      {/* Legacy compact list */}
      <CodeGenProgressLegacy />
    </div>
  );
}

function LivePulse() {
  return (
    <span className="relative flex h-2 w-2">
      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75" />
      <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500" />
    </span>
  );
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  const seconds = Math.floor(ms / 1000);
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m > 0 ? `${m}m ${s.toString().padStart(2, '0')}s` : `${s}s`;
}

function FailureCard({ error }: { error: string }) {
  return (
    <div className="rounded-lg border border-red-500/30 bg-red-950/20 p-4 space-y-3">
      <div className="flex items-start gap-3">
        <AlertCircle className="h-5 w-5 text-red-400 shrink-0 mt-0.5" />
        <div>
          <h4 className="text-sm font-semibold text-red-300">Code generation failed</h4>
          <p className="text-xs text-red-200/80 mt-1">{error}</p>
        </div>
      </div>
      <div className="flex gap-2">
        <button
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-red-500/10 hover:bg-red-500/20 text-red-300 text-xs transition-colors"
          onClick={() => window.location.reload()}
        >
          <RefreshCw className="h-3 w-3" /> Retry
        </button>
        <button
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-muted hover:bg-secondary text-foreground text-xs transition-colors"
          onClick={() => alert('Partial download not yet implemented')}
        >
          <Download className="h-3 w-3" /> Download partial project
        </button>
      </div>
    </div>
  );
}

function CodeGenProgressLegacy() {
  const generatedFiles = useWorkflowStore((s) => s.generatedFiles);

  if (generatedFiles.length === 0) return null;

  return (
    <details className="text-xs">
      <summary className="text-muted-foreground cursor-pointer hover:text-foreground py-1">
        View all generated files ({generatedFiles.length})
      </summary>
      <div className="mt-2 max-h-48 overflow-y-auto space-y-0.5 pl-2 border-l border-border">
        {generatedFiles.map((f, i) => (
          <div key={i} className="flex items-center gap-2 text-[10px] text-muted-foreground font-mono">
            <FileCode className="h-3 w-3 shrink-0" />
            <span className="truncate">{f.path}</span>
            {f.lines_of_code && (
              <span className="text-muted-foreground ml-auto shrink-0">{f.lines_of_code} LOC</span>
            )}
          </div>
        ))}
      </div>
    </details>
  );
}
         