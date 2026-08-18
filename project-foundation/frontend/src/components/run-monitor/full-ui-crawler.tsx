'use client';

/**
 * Full UI Crawler Workspace Component
 *
 * Provides a dedicated, full-screen UI layout for the Web Crawler stage.
 * Takes over the entire application workspace with a high-definition browser canvas,
 * integrated live metrics, event timeline, and action feeds.
 */

import { useState } from 'react';
import { cn } from '@/lib/utils';
import { useWorkflowStore } from '@/store/workflow-store';
import { LiveBrowserPreview, CrawlStats, BrowserActivity, ScreenshotGallery } from '@/components/run-monitor/browser-activity';
import { EventTimeline } from '@/components/run-monitor/event-timeline';
import {
  Globe,
  Maximize2,
  Minimize2,
  ExternalLink,
  Layers,
  Activity,
  Camera,
  X,
  Layout,
  LayoutGrid,
  Sparkles,
} from 'lucide-react';

interface FullUICrawlerWorkspaceProps {
  runId: string;
  isModal?: boolean;
  onCloseModal?: () => void;
}

export function FullUICrawlerWorkspace({ runId, isModal = false, onCloseModal }: FullUICrawlerWorkspaceProps) {
  const browser = useWorkflowStore((s) => s.browserActivity);
  const currentAction = useWorkflowStore((s) => s.currentAction);
  const overallStatus = useWorkflowStore((s) => s.overallStatus);

  const [activeRightTab, setActiveRightTab] = useState<'timeline' | 'stats' | 'screenshots'>('timeline');

  const openPopout = () => {
    window.open(
      `/runs/${runId}/live-preview`,
      `LivePreview_${runId}`,
      'width=1280,height=850,resizable=yes,scrollbars=yes'
    );
  };

  const containerClasses = isModal
    ? 'fixed inset-0 z-50 bg-background flex flex-col text-foreground animate-fade-in'
    : 'w-full flex flex-col space-y-4 text-foreground';

  return (
    <div className={containerClasses}>
      {/* Header bar for Full UI workspace */}
      <div className="flex items-center justify-between px-5 py-3 bg-muted border border-border rounded-xl shadow-lg">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-500/10 border border-blue-500/30">
            <Globe className="h-5 w-5 text-blue-400 animate-pulse" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-bold text-foreground">Live Web Crawler UI Workspace</h2>
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-blue-500/20 text-blue-300 border border-blue-500/40">
                Full UI Mode
              </span>
            </div>
            <p className="text-xs text-muted-foreground">
              {browser.currentUrl ? `Navigating: ${browser.currentUrl}` : 'Real-time autonomous browser execution & data collection'}
            </p>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2">
          <button
            onClick={openPopout}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-muted hover:bg-muted border border-input text-foreground text-xs font-medium transition-all"
            title="Open in standalone window"
          >
            <ExternalLink className="h-3.5 w-3.5 text-blue-400" />
            <span className="hidden sm:inline">Pop-out Window</span>
          </button>

          {isModal && onCloseModal && (
            <button
              onClick={onCloseModal}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-red-500/10 hover:bg-red-500/20 border border-red-500/30 text-red-300 text-xs font-medium transition-all"
              title="Exit Full UI Mode"
            >
              <X className="h-4 w-4" />
              <span>Exit Full UI</span>
            </button>
          )}
        </div>
      </div>

      {/* Main Full UI Grid Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 min-h-[580px] flex-1">
        {/* Left Main Viewport (8 Cols on desktop - Full Screen Canvas) */}
        <div className="lg:col-span-8 flex flex-col space-y-3">
          <div className="flex-1 rounded-xl border border-border bg-card shadow-2xl overflow-hidden flex flex-col min-h-[480px]">
            <LiveBrowserPreview runId={runId} />
          </div>

          {/* Quick stats bar */}
          <div className="rounded-xl border border-border bg-card p-3">
            <CrawlStats />
          </div>
        </div>

        {/* Right Sidebar (4 Cols on desktop - Live Feed & Controls) */}
        <div className="lg:col-span-4 flex flex-col space-y-3">
          {/* Sub-tabs for right sidebar */}
          <div className="flex items-center gap-1 p-1 bg-muted/80 border border-border rounded-xl text-xs">
            <button
              onClick={() => setActiveRightTab('timeline')}
              className={cn(
                'flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg font-medium transition-all',
                activeRightTab === 'timeline'
                  ? 'bg-muted text-foreground shadow-sm border border-input'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              <Activity className="h-3.5 w-3.5 text-violet-400" />
              <span>Event Stream</span>
            </button>

            <button
              onClick={() => setActiveRightTab('stats')}
              className={cn(
                'flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg font-medium transition-all',
                activeRightTab === 'stats'
                  ? 'bg-muted text-foreground shadow-sm border border-input'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              <Layers className="h-3.5 w-3.5 text-blue-400" />
              <span>Crawl Activity</span>
            </button>

            <button
              onClick={() => setActiveRightTab('screenshots')}
              className={cn(
                'flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg font-medium transition-all',
                activeRightTab === 'screenshots'
                  ? 'bg-muted text-foreground shadow-sm border border-input'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              <Camera className="h-3.5 w-3.5 text-pink-400" />
              <span>Screenshots</span>
            </button>
          </div>

          {/* Active Sidebar View */}
          <div className="flex-1 rounded-xl border border-border bg-card p-4 overflow-y-auto max-h-[580px]">
            {activeRightTab === 'timeline' && (
              <div className="h-full flex flex-col">
                <EventTimeline />
              </div>
            )}

            {activeRightTab === 'stats' && (
              <div className="space-y-4">
                <BrowserActivity runId={runId} />
              </div>
            )}

            {activeRightTab === 'screenshots' && (
              <div className="space-y-3">
                <h4 className="text-xs font-semibold text-foreground flex items-center gap-2">
                  <Camera className="h-4 w-4 text-pink-400" /> Live Captured Screenshots
                </h4>
                <ScreenshotGallery runId={runId} />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
