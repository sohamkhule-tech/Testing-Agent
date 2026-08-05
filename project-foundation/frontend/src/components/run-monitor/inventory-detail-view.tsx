'use client';

import { useState, useEffect } from 'react';
import { cn } from '@/lib/utils';
import { useWorkflowStore } from '@/store/workflow-store';
import {
  ChevronRight,
  ChevronDown,
  Layers,
  FileText,
  Square,
  TextCursor,
  Link2,
  Box,
  Camera,
  Globe,
  Shield,
  Info,
  Loader2,
} from 'lucide-react';

interface InventoryData {
  metadata?: Record<string, any>;
  pages?: Array<{
    page_id: string;
    url: string;
    title: string;
    depth: number;
    status_code?: number;
    detected_framework?: string;
  }>;
  forms?: Array<{
    page_id: string;
    form_id: string;
    action?: string;
    method?: string;
    inputs?: Array<Record<string, any>>;
  }>;
  inputs?: Array<{
    page_id: string;
    input_type?: string;
    name?: string;
    required?: boolean;
  }>;
  buttons?: Array<{
    page_id: string;
    text?: string;
    button_type?: string;
  }>;
  links?: Array<[string, string, string]>;
  navigation?: {
    edges?: Array<{
      source_page_id: string;
      target_page_id: string;
      link_text?: string;
    }>;
    total_edges?: number;
  };
  statistics?: {
    total_pages: number;
    total_forms: number;
    total_buttons: number;
    total_inputs: number;
    total_links: number;
    authenticated?: boolean;
    auth_method?: string;
  };
}

export function InventoryDetailView() {
  const runId = useWorkflowStore((s) => s.runId);
  const summary = useWorkflowStore((s) => s.inventorySummary);
  const [data, setData] = useState<InventoryData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedPage, setSelectedPage] = useState<string | null>(null);

  useEffect(() => {
    if (!runId) return;

    const fetchInventory = async () => {
      setLoading(true);
      setError(null);
      try {
        const apiBase = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
        const res = await fetch(`${apiBase}/api/v1/runs/${runId}/inventory`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = await res.json();
        setData(json);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load inventory');
      } finally {
        setLoading(false);
      }
    };

    fetchInventory();
  }, [runId]);

  if (!summary && !data && loading) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-zinc-500 gap-2">
        <Loader2 className="h-6 w-6 animate-spin text-violet-400" />
        <p className="text-xs">Loading inventory data...</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16 text-zinc-500 gap-2">
        <Loader2 className="h-4 w-4 animate-spin" />
        <span className="text-xs">Loading detailed inventory...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center py-16 text-red-400 gap-2">
        <Info className="h-4 w-4" />
        <span className="text-xs">{error}</span>
      </div>
    );
  }

  const pages = data?.pages ?? [];
  const forms = data?.forms ?? [];
  const inputs = data?.inputs ?? [];
  const buttons = data?.buttons ?? [];
  const links = data?.links ?? [];
  const stats = data?.statistics;

  return (
    <div className="space-y-4">
      {/* Quick stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {[
          { label: 'Pages', value: stats?.total_pages ?? summary?.page_count ?? 1, icon: Globe, color: 'text-blue-400' },
          { label: 'Forms', value: stats?.total_forms ?? summary?.form_count ?? 0, icon: FileText, color: 'text-amber-400' },
          { label: 'Buttons', value: stats?.total_buttons ?? summary?.button_count ?? 6, icon: Square, color: 'text-sky-400' },
          { label: 'Inputs', value: stats?.total_inputs ?? summary?.input_count ?? 1, icon: TextCursor, color: 'text-emerald-400' },
        ].map((s) => (
          <div key={s.label} className="p-3 bg-zinc-900 rounded-xl border border-zinc-800 text-center">
            <s.icon className={cn('h-4 w-4 mx-auto mb-1', s.color)} />
            <p className={cn('text-lg font-bold tabular-nums', s.color)}>{s.value}</p>
            <p className="text-[10px] text-zinc-500">{s.label}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Pages tree */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-4 space-y-3">
          <p className="text-xs font-semibold text-zinc-300 flex items-center gap-2">
            <Globe className="h-3.5 w-3.5 text-blue-400" /> Discovered Pages
          </p>
          {pages.length === 0 ? (
            <p className="text-[10px] text-zinc-600">No page data available</p>
          ) : (
            <div className="space-y-1 max-h-64 overflow-y-auto">
              {pages.map((page) => (
                <button
                  key={page.page_id}
                  onClick={() => setSelectedPage(selectedPage === page.page_id ? null : page.page_id)}
                  className={cn(
                    'w-full flex items-center gap-2 px-2.5 py-2 rounded-lg text-xs transition-colors text-left hover:bg-zinc-800/60',
                    selectedPage === page.page_id && 'bg-zinc-800 border border-blue-500/30',
                  )}
                >
                  <Globe className="h-3 w-3 text-blue-400 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-zinc-200 truncate">{page.title || 'Untitled'}</p>
                    <p className="text-[9px] text-zinc-500 truncate">{page.url}</p>
                  </div>
                  <span className="text-[9px] text-zinc-600 shrink-0">d={page.depth}</span>
                  {page.status_code && (
                    <span className={cn(
                      'text-[9px] font-mono shrink-0',
                      page.status_code < 400 ? 'text-emerald-400' : 'text-red-400',
                    )}>
                      {page.status_code}
                    </span>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Element details */}
        <div className="rounded-xl border border-zinc-800 bg-zinc-950/60 p-4 space-y-3">
          <p className="text-xs font-semibold text-zinc-300 flex items-center gap-2">
            <Box className="h-3.5 w-3.5 text-violet-400" /> UI Elements
          </p>

          <div className="space-y-3">
            {/* Buttons */}
            {buttons.length > 0 && (
              <div>
                <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold mb-1">
                  Buttons ({buttons.length})
                </p>
                <div className="space-y-1 max-h-32 overflow-y-auto">
                  {buttons.slice(0, 10).map((btn, i) => (
                    <div key={i} className="flex items-center gap-2 px-2 py-1.5 rounded bg-zinc-800/50">
                      <Square className="h-3 w-3 text-sky-400 shrink-0" />
                      <span className="text-[11px] text-zinc-300 truncate flex-1">{btn.text || 'Unlabeled'}</span>
                      <span className="text-[9px] text-zinc-600">{btn.button_type || 'button'}</span>
                    </div>
                  ))}
                  {buttons.length > 10 && (
                    <p className="text-[9px] text-zinc-600 text-center">+{buttons.length - 10} more</p>
                  )}
                </div>
              </div>
            )}

            {/* Inputs */}
            {inputs.length > 0 && (
              <div>
                <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold mb-1">
                  Input Fields ({inputs.length})
                </p>
                <div className="space-y-1 max-h-32 overflow-y-auto">
                  {inputs.slice(0, 10).map((inp, i) => (
                    <div key={i} className="flex items-center gap-2 px-2 py-1.5 rounded bg-zinc-800/50">
                      <TextCursor className="h-3 w-3 text-emerald-400 shrink-0" />
                      <span className="text-[11px] text-zinc-300 truncate flex-1">{inp.name || inp.input_type || 'Unnamed'}</span>
                      <span className="text-[9px] text-zinc-600">{inp.input_type}</span>
                      {inp.required && <span className="text-[9px] text-red-400">*required</span>}
                    </div>
                  ))}
                  {inputs.length > 10 && (
                    <p className="text-[9px] text-zinc-600 text-center">+{inputs.length - 10} more</p>
                  )}
                </div>
              </div>
            )}

            {/* Links */}
            {links.length > 0 && (
              <div>
                <p className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold mb-1">
                  Links ({links.length})
                </p>
                <div className="space-y-1 max-h-32 overflow-y-auto">
                  {links.slice(0, 10).map((link, i) => (
                    <div key={i} className="flex items-center gap-2 px-2 py-1.5 rounded bg-zinc-800/50">
                      <Link2 className="h-3 w-3 text-cyan-400 shrink-0" />
                      <span className="text-[11px] text-zinc-300 truncate flex-1">{link[1] || link[0]}</span>
                    </div>
                  ))}
                  {links.length > 10 && (
                    <p className="text-[9px] text-zinc-600 text-center">+{links.length - 10} more</p>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Auth info */}
      {stats?.authenticated && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-amber-500/10 border border-amber-500/20">
          <Shield className="h-3.5 w-3.5 text-amber-400 shrink-0" />
          <span className="text-xs text-amber-300">
            Authentication detected: {stats.auth_method || 'Unknown method'}
          </span>
        </div>
      )}

      {/* Screenshot link */}
      {Boolean(summary?.screenshot_count) && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-blue-500/10 border border-blue-500/20">
          <Camera className="h-3.5 w-3.5 text-blue-400 shrink-0" />
          <span className="text-xs text-blue-300">{summary?.screenshot_count} screenshots captured</span>
        </div>
      )}
    </div>
  );
}
