'use client';

import { useCallback, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { runsService } from '@/services/api.service';
import { toast } from 'sonner';
import { Download, Loader2 } from 'lucide-react';

interface DownloadGeneratedCodeButtonProps {
  runId: string;
  ready: boolean;
}

/**
 * Downloads the COMPLETE generated Playwright project (ZIP) for a run.
 *
 * Behaviour:
 * - disabled until the generated project is complete (``ready``) to avoid
 *   shipping an incomplete archive;
 * - shows a spinner + disables itself while a download is in flight;
 * - ignores duplicate clicks (ref guard + disabled state);
 * - surfaces success/failure via toasts.
 */
export function DownloadGeneratedCodeButton({
  runId,
  ready,
}: DownloadGeneratedCodeButtonProps) {
  const [downloading, setDownloading] = useState(false);
  const downloadingRef = useRef(false);

  const handleDownload = useCallback(async () => {
    if (!runId || downloadingRef.current) return; // prevent duplicate downloads
    downloadingRef.current = true;
    setDownloading(true);

    let blob: Blob;
    try {
      blob = await runsService.downloadGeneratedCode(runId);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Failed to download generated code';
      toast.error(`Download failed: ${message}`);
      downloadingRef.current = false;
      setDownloading(false);
      return;
    }

    try {
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `playwright-generated-code-${runId}.zip`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      toast.success('Generated Playwright project downloaded');
    } catch {
      toast.error('Failed to save the downloaded generated code');
    } finally {
      downloadingRef.current = false;
      setDownloading(false);
    }
  }, [runId]);

  return (
    <Button
      variant="outline"
      size="sm"
      onClick={handleDownload}
      disabled={!ready || downloading}
      title="Download the complete generated Playwright project"
      className="shrink-0"
    >
      {downloading ? (
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
      ) : (
        <Download className="h-3.5 w-3.5" />
      )}
      {downloading ? 'Downloading…' : ready ? 'Download Code' : 'Generating…'}
    </Button>
  );
}