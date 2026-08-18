'use client';

import { useState, useEffect, useRef } from 'react';
import { cn } from '@/lib/utils';
import {
  Folder,
  FolderOpen,
  File,
  FileCode,
  FileJson,
  FileText,
  ChevronRight,
  ChevronDown,
  Play,
  Code2,
  Zap,
  Loader2,
  ExternalLink,
} from 'lucide-react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface GenFile {
  path: string;
  name: string;
  file_type?: string;
  size_bytes?: number;
  lines_of_code?: number;
  timestamp?: string;
}

interface TreeNode {
  name: string;
  isDir: boolean;
  children: TreeNode[];
  file?: GenFile;
}

interface LiveFileExplorerProps {
  files: GenFile[];
  onSelectFile: (file: GenFile) => void;
  selectedPath?: string;
  isGenerating: boolean;
}

// ---------------------------------------------------------------------------
// Build file tree
// ---------------------------------------------------------------------------

function buildTree(files: GenFile[]): TreeNode[] {
  const root: TreeNode = { name: '', isDir: true, children: [] };
  for (const f of files) {
    const parts = f.path.replace(/\\/g, '/').split('/');
    let current = root;
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      const isLast = i === parts.length - 1;
      let child = current.children.find((c) => c.name === part);
      if (!child) {
        child = { name: part, isDir: !isLast, children: [], file: isLast ? f : undefined };
        current.children.push(child);
      } else if (isLast) {
        child.file = f;
        child.isDir = false;
      }
      current = child;
    }
  }
  return root.children;
}

// ---------------------------------------------------------------------------
// Icon by file type
// ---------------------------------------------------------------------------

function fileIcon(name: string, isDir: boolean, isExpanded: boolean) {
  if (isDir) return isExpanded ? FolderOpen : Folder;
  const ext = name.split('.').pop() || '';
  switch (ext) {
    case 'ts': case 'tsx': return FileCode;
    case 'json': return FileJson;
    case 'md': return FileText;
    default: return File;
  }
}

function iconColor(name: string) {
  const ext = name.split('.').pop() || '';
  switch (ext) {
    case 'ts': case 'tsx': return 'text-blue-400';
    case 'json': return 'text-amber-400';
    case 'md': return 'text-purple-400';
    case 'yml': case 'yaml': return 'text-sky-400';
    default: return 'text-muted-foreground';
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function LiveFileExplorer({ files, onSelectFile, selectedPath, isGenerating }: LiveFileExplorerProps) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set(['', 'pages', 'tests', 'fixtures', 'utils']));
  const listRef = useRef<HTMLDivElement>(null);

  const tree = buildTree(files);

  // Auto-expand all folders when new files arrive
  useEffect(() => {
    if (files.length > 0) {
      setExpanded((prev) => {
        const next = new Set(prev);
        const addFolders = (nodes: TreeNode[], parent: string) => {
          for (const n of nodes) {
            if (n.isDir) {
              const p = parent ? `${parent}/${n.name}` : n.name;
              next.add(p);
              if (n.children) addFolders(n.children, p);
            }
          }
        };
        addFolders(tree, '');
        return next;
      });
    }
  }, [files.length]);

  useEffect(() => {
    if (isGenerating && listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [files.length, isGenerating]);

  const toggleDir = (path: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(path) ? next.delete(path) : next.add(path);
      return next;
    });
  };

  const renderNode = (node: TreeNode, depth: number, parentPath: string) => {
    const fullPath = parentPath ? `${parentPath}/${node.name}` : node.name;
    const isExpanded = expanded.has(fullPath);
    const Icon = fileIcon(node.name, node.isDir, isExpanded);

    return (
      <div key={fullPath}>
        <div
          className={cn(
            'flex items-center gap-1 px-2 py-0.5 cursor-pointer hover:bg-accent transition-colors text-xs',
            selectedPath === (node.file?.path || fullPath) && 'bg-blue-500/10 border-l-2 border-blue-500',
          )}
          style={{ paddingLeft: `${depth * 12 + 4}px` }}
          onClick={() => {
            if (node.isDir) {
              toggleDir(fullPath);
            } else if (node.file) {
              onSelectFile(node.file);
            }
          }}
        >
          {node.isDir && (
            isExpanded
              ? <ChevronDown className="h-3 w-3 text-muted-foreground shrink-0" />
              : <ChevronRight className="h-3 w-3 text-muted-foreground shrink-0" />
          )}
          {!node.isDir && <span className="w-3 shrink-0" />}
          <Icon className={cn('h-3.5 w-3.5 shrink-0', iconColor(node.name))} />
          <span className={cn(
            'truncate',
            node.isDir ? 'text-foreground font-medium' : 'text-muted-foreground',
          )}>
            {node.name}
          </span>
          {!node.isDir && node.file?.timestamp && (
            <span className="text-[9px] text-muted-foreground ml-auto shrink-0 animate-pulse">
              NEW
            </span>
          )}
        </div>
        {node.isDir && isExpanded && node.children.map((c) => renderNode(c, depth + 1, fullPath))}
      </div>
    );
  };

  return (
    <div className="rounded-lg border border-border bg-card overflow-hidden">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border">
        <Folder className="h-3.5 w-3.5 text-amber-400" />
        <span className="text-xs font-medium text-foreground">Generated Project</span>
        {isGenerating && (
          <span className="flex items-center gap-1 text-[10px] text-muted-foreground ml-auto">
            <Loader2 className="h-3 w-3 animate-spin text-amber-400" />
            Generating...
          </span>
        )}
      </div>
      <div ref={listRef} className="max-h-[320px] overflow-y-auto py-1">
        {tree.length === 0 ? (
          <div className="flex items-center justify-center py-8 text-muted-foreground text-xs">
            {isGenerating ? (
              <span className="flex items-center gap-2">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Creating project structure...
              </span>
            ) : (
              'No files generated yet'
            )}
          </div>
        ) : (
          tree.map((node) => renderNode(node, 0, ''))
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Live Code Viewer
// ---------------------------------------------------------------------------

interface LiveCodeViewerProps {
  file: GenFile | null;
  isLoading: boolean;
  isStreaming: boolean;
}

import { useWorkflowStore } from '@/store/workflow-store';

export function LiveCodeViewer({ file, isLoading, isStreaming }: LiveCodeViewerProps) {
  const runId = useWorkflowStore((s) => s.runId);
  const currentGenFile = useWorkflowStore((s) => s.currentGeneratedFile);
  const generatedFiles = useWorkflowStore((s) => s.generatedFiles);

  const [content, setContent] = useState<string | null>(null);
  const [displayedLineCount, setDisplayedLineCount] = useState<number>(9999);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (!file) {
      setContent(null);
      setLoadError(null);
      return;
    }

    // 1. Check in-memory generated files list first
    const inMem = generatedFiles.find(
      (f) => f.name === file.name || f.path === file.path || f.path.endsWith(file.name)
    );
    if (inMem?.content) {
      setContent(inMem.content);
      setLoadError(null);
      return;
    }

    // 2. Check currentGeneratedFile store object
    if (currentGenFile?.filename === file.name && currentGenFile.content) {
      setContent(currentGenFile.content);
      setLoadError(null);
      return;
    }

    // 3. Fallback to REST fetch
    setContent(null);
    setLoadError(null);

    const apiBase = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
    const endpoint = runId
      ? `${apiBase}/api/v1/runs/${runId}/generated-files/content?path=${encodeURIComponent(file.path)}`
      : `${apiBase}/api/v1/runs/generated-files/content?path=${encodeURIComponent(file.path)}`;

    fetch(endpoint)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => {
        setContent(typeof data === 'string' ? data : data.content ?? '');
      })
      .catch((e) => setLoadError(e.message));
  }, [file?.path, file?.name, runId, generatedFiles, currentGenFile]);

  // Live typewriter effect for line-by-line streaming
  useEffect(() => {
    if (!content) return;
    const totalLines = content.split('\n').length;
    if (isStreaming) {
      setDisplayedLineCount(1);
      const timer = setInterval(() => {
        setDisplayedLineCount((prev) => {
          if (prev >= totalLines) {
            clearInterval(timer);
            return totalLines;
          }
          return prev + Math.max(1, Math.floor(totalLines / 15));
        });
      }, 30);
      return () => clearInterval(timer);
    } else {
      setDisplayedLineCount(totalLines);
    }
  }, [content, isStreaming]);

  if (!file) {
    return (
      <div className="rounded-lg border border-border bg-card h-full flex items-center justify-center">
        <div className="text-center text-muted-foreground space-y-2">
          <FileCode className="h-8 w-8 mx-auto opacity-30" />
          <p className="text-xs">Select a file from the explorer to view its code</p>
        </div>
      </div>
    );
  }

  if (isLoading || content === null) {
    return (
      <div className="rounded-lg border border-border bg-card h-full flex items-center justify-center">
        <div className="text-center text-muted-foreground text-xs space-y-2">
          <Loader2 className="h-5 w-5 mx-auto animate-spin text-cyan-400" />
          <p>Generating {file.name}...</p>
        </div>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="rounded-lg border border-red-500/30 bg-card h-full flex items-center justify-center">
        <p className="text-xs text-red-400">Failed to load: {loadError}</p>
      </div>
    );
  }

  const allLines = content.split('\n');
  const visibleLines = allLines.slice(0, displayedLineCount);

  return (
    <div className="rounded-lg border border-border bg-card overflow-hidden h-full flex flex-col">
      {/* File header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border bg-muted/50">
        <FileCode className={cn('h-3.5 w-3.5', iconColor(file.name))} />
        <span className="text-xs font-medium text-foreground">{file.name}</span>
        <span className="text-[10px] text-muted-foreground ml-auto tabular-nums">{allLines.length} lines</span>
        {isStreaming && (
          <span className="text-[10px] text-cyan-400 flex items-center gap-1 font-mono">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500" />
            </span>
            Streaming...
          </span>
        )}
      </div>

      {/* Code area */}
      <div className="flex-1 overflow-auto">
        <pre className="text-xs font-mono text-foreground p-0">
          <table className="w-full border-collapse">
            <tbody>
              {visibleLines.map((line, i) => (
                <tr
                  key={i}
                  className={cn(
                    'hover:bg-accent/60 transition-colors',
                    isStreaming && i === visibleLines.length - 1 && 'bg-cyan-950/30 border-l-2 border-cyan-400',
                  )}
                >
                  <td className="select-none text-right pr-4 pl-3 text-muted-foreground border-r border-border w-12 align-top leading-6">
                    {i + 1}
                  </td>
                  <td className="pl-3 leading-6 whitespace-pre-wrap break-all">
                    {highlightCode(line)}
                    {isStreaming && i === visibleLines.length - 1 && (
                      <span className="inline-block w-1.5 h-3.5 bg-cyan-400 ml-0.5 animate-pulse align-middle" />
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </pre>
      </div>
    </div>
  );
}

function highlightCode(line: string): React.ReactNode {
  if (/^import\b|^export\b/.test(line)) return <span className="text-purple-400">{line}</span>;
  if (/^(async\s+)?(function|class)\b/.test(line)) return <span className="text-amber-400">{line}</span>;
  if (/const\s+\w+\s*[:=]|let\s+\w+\s*[:=]/.test(line)) return <span className="text-cyan-400">{line}</span>;
  if (/\btest\b\(/.test(line)) return <span className="text-emerald-400">{line}</span>;
  if (/\bexpect\b\(/.test(line)) return <span className="text-orange-400">{line}</span>;
  if (/^(\s*\/\/|^\s*\/\*|\s*\*\/)/.test(line)) return <span className="text-muted-foreground italic">{line}</span>;
  if (/^\s*$/.test(line)) return '\u00A0';
  return line;
}
