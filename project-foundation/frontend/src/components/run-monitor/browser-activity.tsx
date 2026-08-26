'use client';

/**
 * BrowserActivity — Live browser status panel during crawling.
 * ScreenshotGallery — Real-time screenshot grid.
 * CrawlStats — Live stat cards.
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { cn } from '@/lib/utils';
import { useWorkflowStore, Screenshot, CursorPosition } from '@/store/workflow-store';
import {
  Globe,
  Layers,
  Link2,
  FileText,
  Square,
  TextCursor,
  Camera,
  AlertCircle,
  Wifi,
  ArrowRight,
  X,
  ZoomIn,
  Monitor,
  Loader2,
  Maximize2,
  Minimize2,
  ExternalLink,
} from 'lucide-react';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

// ---------------------------------------------------------------------------
// Browser Activity Panel
// ---------------------------------------------------------------------------

export function BrowserActivity({ runId }: { runId: string }) {
  const browser = useWorkflowStore((s) => s.browserActivity);
  const stats = useWorkflowStore((s) => s.crawlStats);
  const [elapsed, setElapsed] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval>>(undefined);
  useEffect(() => {
    if (browser.status === 'launching' || browser.status === 'navigating' || browser.status === 'capturing') {
      const t0 = Date.now();
      timerRef.current = setInterval(() => setElapsed(Date.now() - t0), 200);
    } else if (browser.status === 'done') {
      if (timerRef.current) clearInterval(timerRef.current);
    }
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [browser.status]);

  const statusLabel: Record<string, string> = {
    idle:       'Idle',
    launching:  'Launching Chromium...',
    navigating: 'Navigating',
    capturing:  'Taking Screenshot',
    done:       'Crawl Complete',
  };

  const statusColor: Record<string, string> = {
    idle:       'text-muted-foreground',
    launching:  'text-blue-400',
    navigating: 'text-blue-400',
    capturing:  'text-amber-400',
    done:       'text-emerald-400',
  };

  return (
    <div className="space-y-4">
      <div className={cn(
        'flex items-center gap-2 px-3 py-2 rounded-lg border text-sm font-medium',
        browser.status === 'idle'       && 'border-border bg-muted text-muted-foreground',
        browser.status === 'launching'  && 'border-blue-500/40 bg-blue-500/10 text-blue-400',
        browser.status === 'navigating' && 'border-blue-500/40 bg-blue-500/10 text-blue-400',
        browser.status === 'capturing'  && 'border-amber-400/40 bg-amber-400/10 text-amber-400',
        browser.status === 'done'       && 'border-emerald-500/40 bg-emerald-500/10 text-emerald-400',
      )}>
        <Globe className={cn('h-4 w-4', statusColor[browser.status])} />
        {statusLabel[browser.status]}
        {elapsed > 0 && <span className="ml-auto text-xs text-muted-foreground">{(elapsed / 1000).toFixed(1)}s</span>}
        {(browser.status === 'navigating' || browser.status === 'launching') && (
          <span className="flex gap-0.5">{[0,1,2].map(i => <span key={i} className="h-1.5 w-1.5 rounded-full bg-blue-400 animate-bounce" style={{animationDelay:`${i*0.15}s`}} />)}</span>
        )}
      </div>

      {browser.currentUrl && (
        <div className="space-y-1">
          <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Current URL</p>
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-muted border border-border">
            <ArrowRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
            <span className="text-xs font-mono text-foreground truncate max-w-[300px]">{browser.currentUrl}</span>
            <div className="flex items-center gap-1 ml-auto shrink-0">
              {browser.statusCode && (
                <span className={cn('text-[10px] font-mono px-1.5 py-0.5 rounded', browser.statusCode < 300 ? 'bg-emerald-500/20 text-emerald-400' : browser.statusCode < 400 ? 'bg-amber-500/20 text-amber-400' : 'bg-red-500/20 text-red-400')}>{browser.statusCode}</span>
              )}
              {browser.responseTime && <span className="text-[10px] text-muted-foreground font-mono">{browser.responseTime}ms</span>}
              {browser.depth !== undefined && <span className="text-[10px] text-muted-foreground">D:{browser.depth}</span>}
            </div>
          </div>
          {browser.currentTitle && <p className="text-xs text-muted-foreground px-1 truncate">{browser.currentTitle}</p>}
        </div>
      )}

      <div className="grid grid-cols-4 gap-2">
        {[
          { label: 'Pages', value: browser.pagesVisited, color: 'text-blue-400' },
          { label: 'Links', value: stats.linksFound, color: 'text-violet-400' },
          { label: 'Forms', value: stats.formsFound, color: 'text-amber-400' },
          { label: 'Queue', value: browser.queueSize, color: 'text-sky-400' },
        ].map(s => (
          <div key={s.label} className="px-3 py-2 rounded-lg bg-muted border border-border text-center">
            <p className={cn('text-xl font-bold tabular-nums', s.color)}>{s.value}</p>
            <p className="text-[10px] text-muted-foreground">{s.label}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Crawl Statistics
// ---------------------------------------------------------------------------

export function CrawlStats() {
  const stats = useWorkflowStore((s) => s.crawlStats);
  const screenshots = useWorkflowStore((s) => s.screenshots);

  const items = [
    { label: 'Pages',    value: stats.pagesCrawled || stats.pagesVisited, icon: Layers,     color: 'text-blue-400',    bg: 'bg-blue-500/10' },
    { label: 'Links',    value: stats.linksFound,    icon: Link2,      color: 'text-violet-400',  bg: 'bg-violet-500/10' },
    { label: 'Forms',    value: stats.formsFound,    icon: FileText,   color: 'text-amber-400',   bg: 'bg-amber-500/10' },
    { label: 'Buttons',  value: stats.buttonsFound,  icon: Square,     color: 'text-sky-400',     bg: 'bg-sky-500/10' },
    { label: 'Inputs',   value: stats.inputsFound,   icon: TextCursor, color: 'text-emerald-400', bg: 'bg-emerald-500/10' },
    { label: 'Photos',   value: screenshots.length,   icon: Camera,     color: 'text-pink-400',    bg: 'bg-pink-500/10' },
  ];

  return (
    <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
      {items.map((item) => (
        <div key={item.label} className="flex items-center gap-2 px-2 py-2 rounded-lg border border-border bg-muted/50">
          <div className={cn('flex h-7 w-7 shrink-0 items-center justify-center rounded', item.bg)}>
            <item.icon className={cn('h-3.5 w-3.5', item.color)} />
          </div>
          <div>
            <p className={cn('text-base font-bold tabular-nums leading-none', item.color)}>{item.value}</p>
            <p className="text-[9px] text-muted-foreground">{item.label}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Screenshot Gallery
// ---------------------------------------------------------------------------

function ScreenshotCard({ shot, runId, onClick }: { shot: Screenshot; runId: string; onClick: () => void }) {
  const imgUrl = `${API_BASE}/api/v1/runs/${runId}/screenshots/${encodeURIComponent(shot.filename)}`;

  return (
    <button
      onClick={onClick}
      className="group relative overflow-hidden rounded-xl border border-border bg-muted hover:border-input transition-all duration-200 hover:shadow-lg hover:shadow-black/40 animate-fade-in text-left"
    >
      {/* Thumbnail */}
      <div className="aspect-video relative overflow-hidden bg-muted">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={imgUrl}
          alt={shot.title ?? shot.url}
          className="h-full w-full object-cover group-hover:scale-105 transition-transform duration-300"
          onError={(e) => {
            (e.target as HTMLImageElement).style.display = 'none';
          }}
        />
        <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-200 flex items-center justify-center">
          <ZoomIn className="h-6 w-6 text-white" />
        </div>
      </div>

      {/* Info */}
      <div className="p-2.5 space-y-1">
        {shot.title && (
          <p className="text-xs font-medium text-foreground truncate">{shot.title}</p>
        )}
        <p className="text-[10px] text-muted-foreground truncate font-mono">{shot.url}</p>
        <p className="text-[10px] text-muted-foreground">
          {new Date(shot.timestamp).toLocaleTimeString()}
        </p>
      </div>
    </button>
  );
}

function Lightbox({ shot, runId, onClose }: { shot: Screenshot; runId: string; onClose: () => void }) {
  const imgUrl = `${API_BASE}/api/v1/runs/${runId}/screenshots/${encodeURIComponent(shot.filename)}`;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div className="relative max-w-5xl w-full" onClick={(e) => e.stopPropagation()}>
        <button
          onClick={onClose}
          className="absolute -top-10 right-0 text-muted-foreground hover:text-white transition-colors"
        >
          <X className="h-6 w-6" />
        </button>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={imgUrl} alt={shot.title ?? shot.url} className="w-full rounded-xl border border-input" />
        <div className="mt-3 text-center space-y-1">
          {shot.title && <p className="text-sm font-medium text-foreground">{shot.title}</p>}
          <p className="text-xs text-muted-foreground font-mono">{shot.url}</p>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Live Browser Preview — shows live frames as the agent navigates
// ---------------------------------------------------------------------------

export function LiveBrowserPreview({ runId }: { runId: string }) {
  const browser = useWorkflowStore((s) => s.browserActivity);
  const liveFrame = useWorkflowStore((s) => s.liveFrame);
  const currentAction = useWorkflowStore((s) => s.currentAction);
  const screenshots = useWorkflowStore((s) => s.screenshots);
  const latestShot = screenshots.length > 0 ? screenshots[screenshots.length - 1] : null;

  const displayFrame = liveFrame ?? (latestShot ? { filename: latestShot.filename, url: latestShot.url, title: latestShot.title || '', action: 'screenshot', timestamp: latestShot.timestamp } : null);
  const imgUrl = displayFrame ? `${API_BASE}/api/v1/runs/${runId}/screenshots/${encodeURIComponent(displayFrame.filename)}` : null;
  const isLoading = browser.status === 'launching' || browser.status === 'navigating' || !!currentAction;

  const viewportRef = useRef<HTMLDivElement>(null);
  const [cursorPos, setCursorPos] = useState<CursorPosition | null>(null);
  const [showRipple, setShowRipple] = useState(false);
  const [showTyping, setShowTyping] = useState(false);
  const prevActionRef = useRef<string | null>(null);

  const [fitMode, setFitMode] = useState<'contain' | 'full'>('contain');
  const actionTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Auto-clear stale action labels after 4s if no new action arrives
  useEffect(() => {
    if (currentAction) {
      if (actionTimerRef.current) clearTimeout(actionTimerRef.current);
      actionTimerRef.current = setTimeout(() => {
        useWorkflowStore.setState({ currentAction: null });
      }, 4000);
    }
    return () => { if (actionTimerRef.current) clearTimeout(actionTimerRef.current); };
  }, [currentAction]);

  useEffect(() => {
    if (currentAction?.position && viewportRef.current) {
      const rect = viewportRef.current.getBoundingClientRect();
      const relX = (currentAction.position.x / 1920) * 100;
      const relY = (currentAction.position.y / 1080) * 100;
      setCursorPos({ x: relX, y: relY });

      const actionKey = currentAction.label + currentAction.position.x + currentAction.position.y;
      if (actionKey !== prevActionRef.current) {
        prevActionRef.current = actionKey;
        if (currentAction.action === 'click') {
          setShowRipple(true);
          setTimeout(() => setShowRipple(false), 700);
        }
        if (currentAction.action === 'fill') {
          setShowTyping(true);
          setTimeout(() => setShowTyping(false), 1200);
        }
      }
    } else {
      setCursorPos(null);
      prevActionRef.current = null;
    }
  }, [currentAction]);

  const clearCursor = useCallback(() => {
    if (!currentAction) {
      setCursorPos(null);
      setShowRipple(false);
      setShowTyping(false);
      prevActionRef.current = null;
    }
  }, [currentAction]);

  const actionLabel = currentAction?.label ?? null;

  const openSeparateWindow = useCallback(() => {
    window.open(
      `/runs/${runId}/live-preview`,
      `LivePreviewWindow_${runId}`,
      'width=1280,height=850,resizable=yes,scrollbars=yes,status=no,toolbar=no,menubar=no'
    );
  }, [runId]);

  return (
    <div className="rounded-xl border border-border bg-card overflow-hidden">
      {/* Browser chrome */}
      <div className="flex items-center gap-3 px-4 py-2.5 bg-muted border-b border-border">
        <div className="flex gap-1.5">
          <div className="h-3 w-3 rounded-full bg-red-500/80" />
          <div className="h-3 w-3 rounded-full bg-amber-500/80" />
          <div className="h-3 w-3 rounded-full bg-emerald-500/80" />
        </div>
        <div className="flex-1 flex items-center gap-2 px-3 py-1 rounded-md bg-muted border border-border min-w-0">
          <Globe className="h-3 w-3 text-muted-foreground shrink-0" />
          <span className="text-xs text-muted-foreground truncate font-mono">{displayFrame?.url || browser.currentUrl || 'Waiting...'}</span>
          {browser.statusCode && (
            <span className={cn('ml-auto text-[10px] font-mono px-1 py-0.5 rounded shrink-0', browser.statusCode < 300 ? 'bg-emerald-500/20 text-emerald-400' : browser.statusCode < 400 ? 'bg-amber-500/20 text-amber-400' : 'bg-red-500/20 text-red-400')}>{browser.statusCode}</span>
          )}
        </div>
        {displayFrame?.title && (
          <span className="text-[10px] text-muted-foreground truncate max-w-[160px] hidden sm:block">{displayFrame.title}</span>
        )}
        <button
          onClick={() => setFitMode(m => m === 'contain' ? 'full' : 'contain')}
          className="ml-2 p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
          title={fitMode === 'contain' ? 'Show full page' : 'Fit to viewport'}
        >
          {fitMode === 'contain' ? <Maximize2 className="h-3.5 w-3.5" /> : <Minimize2 className="h-3.5 w-3.5" />}
        </button>
      </div>

      {/* Viewport with cursor overlay */}
      <div ref={viewportRef} className={cn(
        'relative bg-muted flex items-start justify-center',
        fitMode === 'contain' ? 'aspect-video overflow-hidden' : 'min-h-[420px] max-h-[80vh] overflow-y-auto',
      )}>
        {imgUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            key={displayFrame?.filename || 'frame'}
            src={imgUrl}
            alt={displayFrame?.title ?? 'Browser'}
            className={cn(
              'bg-white transition-opacity duration-300',
              fitMode === 'contain' ? 'w-full h-full object-contain' : 'w-full h-auto object-top',
            )}
          />
        ) : isLoading ? (
          <div className="flex flex-col items-center gap-3 text-muted-foreground">
            <Loader2 className="h-8 w-8 animate-spin text-blue-400" />
            <p className="text-xs">{actionLabel || 'Loading...'}</p>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3 text-muted-foreground">
            <Monitor className="h-10 w-10" />
            <p className="text-xs">Waiting for browser to start...</p>
          </div>
        )}

        {/* Visual cursor */}
        {cursorPos && (
          <div
            className="absolute pointer-events-none z-20 transition-all duration-200 ease-out"
            style={{ left: `${cursorPos.x}%`, top: `${cursorPos.y}%`, transform: 'translate(-50%, -50%)' }}
          >
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" className="drop-shadow-lg">
              <path d="M5 3l4 12 3-3 5 6 2-2-5-6 4-2L5 3z" fill="white" stroke="#3b82f6" strokeWidth="0.5" />
            </svg>
          </div>
        )}

        {/* Click ripple */}
        {showRipple && cursorPos && (
          <div
            className="absolute pointer-events-none z-10"
            style={{ left: `${cursorPos.x}%`, top: `${cursorPos.y}%`, transform: 'translate(-50%, -50%)' }}
          >
            {[0, 1, 2].map((i) => (
              <div
                key={i}
                className="absolute rounded-full border-2 border-blue-400 animate-ripple"
                style={{
                  width: '12px',
                  height: '12px',
                  left: '-6px',
                  top: '-6px',
                  animationDelay: `${i * 0.15}s`,
                }}
              />
            ))}
          </div>
        )}

        {/* Typing indicator */}
        {showTyping && cursorPos && (
          <div
            className="absolute pointer-events-none z-10"
            style={{ left: `${cursorPos.x}%`, top: `calc(${cursorPos.y}% - 18px)`, transform: 'translate(-50%, -100%)' }}
          >
            <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-blue-500/20 backdrop-blur-sm border border-blue-500/40">
              {[0, 1, 2].map((i) => (
                <span
                  key={i}
                  className="h-1.5 w-1.5 rounded-full bg-blue-300 animate-typing-dot"
                  style={{ animationDelay: `${i * 0.12}s` }}
                />
              ))}
              <span className="text-[10px] text-blue-300 font-medium ml-1">typing...</span>
            </div>
          </div>
        )}

        {/* Current action badge — fixed to viewport, never overflows */}
        {actionLabel && imgUrl && (
          <div className={cn(
            'fixed bottom-6 left-6 flex items-center gap-2 px-4 py-2 rounded-lg backdrop-blur-md border shadow-lg z-50',
            currentAction?.action === 'click' ? 'bg-amber-500/25 border-amber-500/50' :
            currentAction?.action === 'fill' ? 'bg-violet-500/25 border-violet-500/50' :
            'bg-blue-500/25 border-blue-500/40 animate-pulse',
          )}>
            <Loader2 className={cn(
              'h-3.5 w-3.5 animate-spin',
              currentAction?.action === 'click' ? 'text-amber-400' :
              currentAction?.action === 'fill' ? 'text-violet-400' :
              'text-blue-400',
            )} />
            <span className={cn(
              'text-xs font-medium',
              currentAction?.action === 'click' ? 'text-amber-300' :
              currentAction?.action === 'fill' ? 'text-violet-300' :
              'text-blue-300',
            )}>{actionLabel}</span>
          </div>
        )}
      </div>

      {/* Action + Stats bar */}
      <div className="flex items-center gap-4 px-4 py-2 bg-muted/50 border-t border-border text-[10px] text-muted-foreground">
        {actionLabel ? (
          <span className={cn(
            'flex items-center gap-1.5',
            currentAction?.action === 'click' ? 'text-amber-400' :
            currentAction?.action === 'fill' ? 'text-violet-400' :
            'text-blue-400',
          )}>
            <Loader2 className="h-3 w-3 animate-spin" />
            {actionLabel}
          </span>
        ) : (
          <span className="text-muted-foreground">Idle</span>
        )}
        <span className="ml-auto">Pages: <span className="text-foreground font-mono">{browser.pagesVisited}</span></span>
        <span>Queue: <span className="text-foreground font-mono">{browser.queueSize}</span></span>
        {displayFrame?.timestamp && <span className="text-muted-foreground">{new Date(displayFrame.timestamp).toLocaleTimeString()}</span>}
      </div>
    </div>
  );
}


export function ScreenshotGallery({ runId }: { runId: string }) {
  const screenshots = useWorkflowStore((s) => s.screenshots);
  const [selected, setSelected] = useState<Screenshot | null>(null);

  if (screenshots.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-3 text-muted-foreground">
        <Camera className="h-10 w-10" />
        <p className="text-sm">Screenshots will appear here as pages are crawled</p>
      </div>
    );
  }

  return (
    <>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        {screenshots.map((shot) => (
          <ScreenshotCard
            key={shot.id}
            shot={shot}
            runId={runId}
            onClick={() => setSelected(shot)}
          />
        ))}
      </div>
      {selected && (
        <Lightbox shot={selected} runId={runId} onClose={() => setSelected(null)} />
      )}
    </>
  );
}
