'use client';

import { useState } from 'react';
import { use } from 'react';
import Link from 'next/link';
import { PageHeader } from '@/components/page-header';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { EmptyState } from '@/components/empty-state';
import { useGeneratedFiles } from '@/hooks/use-api';
import { apiClient } from '@/lib/api-client';
import { ArrowLeft, FileCode, Folder, File, Download, Copy, CheckCircle2, AlertCircle } from 'lucide-react';
import { cn } from '@/lib/utils';

export default function GeneratedCodePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data, isLoading } = useGeneratedFiles(id);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string | null>(null);
  const [contentLoading, setContentLoading] = useState(false);

  const handleFileClick = async (path: string) => {
    setSelectedFile(path);
    setContentLoading(true);
    try {
      const result = await apiClient.get<{ content: string }>(`/api/v1/runs/${id}/generated-files/content`, { path });
      setFileContent(result.content);
    } catch {
      setFileContent('// Error loading file content');
    }
    setContentLoading(false);
  };

  if (isLoading) {
    return (
      <div className="container py-6 space-y-6">
        <Skeleton className="h-12 w-full" />
        <div className="grid gap-6 lg:grid-cols-4">
          <Skeleton className="h-96 lg:col-span-1" />
          <Skeleton className="h-96 lg:col-span-3" />
        </div>
      </div>
    );
  }

  if (!data?.exists) {
    return (
      <div className="container py-6">
        <PageHeader title="Generated Code" description="Playwright test automation project" />
        <EmptyState icon={FileCode} title="No generated code yet" description="Complete the code generation stage to view generated Playwright tests." />
      </div>
    );
  }

  const metadata = data.metadata;
  const files = data.files ?? [];

  return (
    <div className="container py-6 space-y-6">
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="sm" asChild>
          <Link href={`/runs/${id}`}><ArrowLeft className="h-4 w-4 mr-1" /> Back to Run</Link>
        </Button>
      </div>

      <PageHeader title="Generated Playwright Project" description="Browse generated test files, page objects, and fixtures." />

      {metadata && (
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3">
          <MetadataBadge label="Status" value={metadata.status ?? '-'} color={metadata.status === 'completed' ? 'text-emerald-500' : 'text-amber-500'} />
          <MetadataBadge label="Files" value={String(metadata.files_generated ?? 0)} />
          <MetadataBadge label="Page Objects" value={String(metadata.page_objects_count ?? 0)} />
          <MetadataBadge label="Test Files" value={String(metadata.test_files_count ?? 0)} />
          <MetadataBadge label="Scenarios" value={String(metadata.scenarios_implemented ?? 0)} />
          <MetadataBadge label="Validation" value={metadata.validation_status ?? '-'} color={metadata.validation_status === 'passed' ? 'text-emerald-500' : 'text-red-500'} />
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-4">
        <Card className="lg:col-span-1">
          <CardHeader className="pb-2"><CardTitle className="text-sm">Project Files</CardTitle></CardHeader>
          <CardContent className="p-0">
            <FileTree files={files} selectedFile={selectedFile} onFileClick={handleFileClick} depth={0} />
          </CardContent>
        </Card>

        <Card className="lg:col-span-3">
          <CardHeader className="pb-2 flex flex-row items-center justify-between">
            <CardTitle className="text-sm truncate">{selectedFile ?? 'Select a file'}</CardTitle>
            {selectedFile && (
              <div className="flex items-center gap-1">
                <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => navigator.clipboard.writeText(fileContent ?? '')}>
                  <Copy className="h-3 w-3 mr-1" /> Copy
                </Button>
              </div>
            )}
          </CardHeader>
          <CardContent className="p-0">
            {contentLoading ? (
              <div className="p-6 space-y-2"><Skeleton className="h-4 w-full" /><Skeleton className="h-4 w-3/4" /><Skeleton className="h-4 w-1/2" /></div>
            ) : fileContent ? (
              <pre className="text-xs overflow-auto max-h-[600px] p-4 bg-muted/30 rounded-md"><code>{fileContent}</code></pre>
            ) : (
              <div className="p-6 text-center text-sm text-muted-foreground">Select a file to view its contents</div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function FileTree({ files, selectedFile, onFileClick, depth }: { files: any[]; selectedFile: string | null; onFileClick: (path: string) => void; depth: number }) {
  return (
    <div className="text-sm">
      {files.map((item) => (
        <div key={item.path}>
          {item.type === 'directory' ? (
            <div>
              <div className={cn("flex items-center gap-2 px-3 py-1.5 text-xs font-medium text-muted-foreground", depth > 0 && "pl-" + (depth * 4 + 3))}>
                <Folder className="h-3.5 w-3.5" />
                {item.name}
              </div>
              {item.children && <FileTree files={item.children} selectedFile={selectedFile} onFileClick={onFileClick} depth={depth + 1} />}
            </div>
          ) : (
            <button onClick={() => onFileClick(item.path)}
              className={cn("w-full text-left flex items-center gap-2 px-3 py-1.5 hover:bg-accent/50 transition-colors text-xs",
                selectedFile === item.path && "bg-accent text-accent-foreground",
                depth > 0 && `pl-${depth * 4 + 3}`)}>
              {item.name.endsWith('.ts') || item.name.endsWith('.tsx') ? <FileCode className="h-3.5 w-3.5 text-blue-500" /> : <File className="h-3.5 w-3.5" />}
              <span className="truncate">{item.name}</span>
              <span className="ml-auto text-[10px] text-muted-foreground">{item.size_bytes ? `${(item.size_bytes / 1024).toFixed(1)}KB` : ''}</span>
            </button>
          )}
        </div>
      ))}
    </div>
  );
}

function MetadataBadge({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="rounded-lg border p-3 text-center">
      <div className={cn("text-lg font-bold", color ?? 'text-foreground')}>{value}</div>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  );
}
