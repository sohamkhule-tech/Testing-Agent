'use client';

/**
 * InventoryTree — Discovered elements expandable tree view.
 * Displays pages, forms, fields, buttons, navigation links, modals, etc.
 */

import { useState } from 'react';
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
  ListFilter,
  Box,
} from 'lucide-react';

interface TreeNodeProps {
  label: string;
  count?: number;
  icon: React.ElementType;
  children?: React.ReactNode;
  defaultOpen?: boolean;
}

function TreeNode({ label, count, icon: Icon, children, defaultOpen = false }: TreeNodeProps) {
  const [open, setOpen] = useState(defaultOpen);
  const hasChildren = Boolean(children);

  return (
    <div className="space-y-1">
      <button
        onClick={() => setOpen(!open)}
        disabled={!hasChildren}
        className={cn(
          'flex items-center gap-2 w-full px-2.5 py-1.5 rounded-lg text-xs transition-colors hover:bg-zinc-800/60 text-left',
          !hasChildren && 'cursor-default opacity-80'
        )}
      >
        {hasChildren ? (
          open ? (
            <ChevronDown className="h-3.5 w-3.5 text-zinc-400 shrink-0" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 text-zinc-400 shrink-0" />
          )
        ) : (
          <span className="w-3.5 shrink-0" />
        )}
        <Icon className="h-4 w-4 text-blue-400 shrink-0" />
        <span className="font-medium text-zinc-200 flex-1 truncate">{label}</span>
        {count !== undefined && (
          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400">
            {count}
          </span>
        )}
      </button>
      {open && children && <div className="pl-6 space-y-1 border-l border-zinc-800 ml-4">{children}</div>}
    </div>
  );
}

export function InventoryTree() {
  const summary = useWorkflowStore((s) => s.inventorySummary);

  if (!summary) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-zinc-600 gap-2">
        <Box className="h-10 w-10 animate-pulse" />
        <p className="text-xs">Inventory will populate automatically once crawler completes.</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pb-3 border-b border-zinc-800">
        <div className="p-2.5 bg-zinc-900 rounded-lg border border-zinc-800">
          <span className="text-[10px] text-zinc-500 block">Total Pages</span>
          <span className="text-lg font-bold text-blue-400">{summary.page_count}</span>
        </div>
        <div className="p-2.5 bg-zinc-900 rounded-lg border border-zinc-800">
          <span className="text-[10px] text-zinc-500 block">Forms Discovered</span>
          <span className="text-lg font-bold text-amber-400">{summary.form_count}</span>
        </div>
        <div className="p-2.5 bg-zinc-900 rounded-lg border border-zinc-800">
          <span className="text-[10px] text-zinc-500 block">Interactive Buttons</span>
          <span className="text-lg font-bold text-sky-400">{summary.button_count}</span>
        </div>
        <div className="p-2.5 bg-zinc-900 rounded-lg border border-zinc-800">
          <span className="text-[10px] text-zinc-500 block">Input Fields</span>
          <span className="text-lg font-bold text-emerald-400">{summary.input_count}</span>
        </div>
      </div>

      <div className="space-y-1">
        <TreeNode label="Application Root & Discovered Pages" count={summary.page_count} icon={Layers} defaultOpen>
          <TreeNode label="Forms & User Inputs" count={summary.form_count} icon={FileText} defaultOpen>
            <TreeNode label="Input Fields" count={summary.input_count} icon={TextCursor} />
            <TreeNode label="Action Buttons" count={summary.button_count} icon={Square} />
          </TreeNode>
          <TreeNode label="Navigation & External Links" count={summary.link_count} icon={Link2} />
          <TreeNode label="Interactive UI Elements" count={summary.button_count + summary.input_count} icon={ListFilter} />
        </TreeNode>
      </div>
    </div>
  );
}
