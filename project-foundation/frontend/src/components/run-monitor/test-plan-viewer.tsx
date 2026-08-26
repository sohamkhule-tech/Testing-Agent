'use client';

import React, { useState } from 'react';
import { cn } from '@/lib/utils';
import { useWorkflowStore } from '@/store/workflow-store';
import { toast } from 'sonner';
import {
  ClipboardList,
  CheckCircle2,
  Clock,
  UserCheck,
  ThumbsUp,
  ThumbsDown,
  Download,
  AlertTriangle,
  Loader2,
  FileSpreadsheet,
  Eye,
  Edit3,
  RefreshCw,
  Table2,
  FileText,
  ListChecks,
  BarChart3,
  Shield,
  Link2,
  Zap,
  Target,
  Search,
  ChevronDown,
  ChevronRight,
  MessageSquare,
  X,
  Filter,
  ExternalLink,
} from 'lucide-react';

type SheetName = 'Summary' | 'Inventory' | 'Modules' | 'Scenarios' | 'Test Data';

const SHEETS: { name: SheetName; icon: React.ElementType }[] = [
  { name: 'Summary', icon: BarChart3 },
  { name: 'Inventory', icon: ListChecks },
  { name: 'Modules', icon: Shield },
  { name: 'Scenarios', icon: FileText },
  { name: 'Test Data', icon: Table2 },
];

export function TestPlanViewer() {
  const generated       = useWorkflowStore((s) => s.testPlanGenerated);
  const scenarioCount   = useWorkflowStore((s) => s.testPlanScenarioCount);
  const runId           = useWorkflowStore((s) => s.runId);
  const modules         = useWorkflowStore((s) => s.detectedModules);
  const scenarios       = useWorkflowStore((s) => s.generatedScenarios);
  const [showPreview, setShowPreview] = useState(false);
  const [activeSheet, setActiveSheet] = useState<SheetName>('Summary');

  if (!generated) {
    return null;
  }

  const apiBase = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

  return (
    <div className="space-y-3 pt-3 border-t border-border">
      <div className="flex items-center gap-3 px-4 py-3 rounded-xl border border-emerald-500/40 bg-emerald-500/10">
        <CheckCircle2 className="h-5 w-5 text-emerald-400 shrink-0" />
        <div>
          <p className="text-sm font-semibold text-emerald-300">Test Plan Generated Successfully</p>
          <p className="text-xs text-muted-foreground mt-0.5">
            <span className="font-mono text-emerald-400">{scenarioCount}</span> scenarios across{' '}
            <span className="font-mono text-emerald-400">{modules.length}</span> modules
          </p>
        </div>
      </div>

      {!showPreview ? (
        <button
          onClick={() => setShowPreview(true)}
          className="w-full flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg bg-muted hover:bg-secondary border border-input text-foreground text-xs font-medium transition-colors"
        >
          <Eye className="h-3.5 w-3.5" />
          Preview Workbook Before Download
        </button>
      ) : (
        <div className="rounded-xl border border-border bg-muted/80 overflow-hidden">
          <div className="flex border-b border-border overflow-x-auto">
            {SHEETS.map((sheet) => {
              const Icon = sheet.icon;
              return (
                <button
                  key={sheet.name}
                  onClick={() => setActiveSheet(sheet.name)}
                  className={cn(
                    'flex items-center gap-1.5 px-3 py-2 text-[10px] font-medium whitespace-nowrap transition-colors',
                    activeSheet === sheet.name
                      ? 'text-emerald-400 border-b-2 border-emerald-500 bg-emerald-500/5'
                      : 'text-muted-foreground hover:text-foreground hover:bg-accent/60',
                  )}
                >
                  <Icon className="h-3 w-3" />
                  {sheet.name}
                  <CheckCircle2 className="h-2.5 w-2.5 text-emerald-500/60" />
                </button>
              );
            })}
          </div>

          <div className="p-4">
            {activeSheet === 'Summary' && (
              <div className="space-y-2">
                <p className="text-xs font-semibold text-foreground">Executive Summary</p>
                <div className="grid grid-cols-2 gap-2 text-[10px]">
                  {[
                    ['Total Scenarios', String(scenarioCount)],
                    ['Modules Identified', String(modules.length)],
                    ['Critical Scenarios', String(scenarios.filter(s => s.priority === 'critical').length)],
                    ['Automation Coverage', `${scenarios.length > 0 ? Math.round(((scenarios.length - scenarios.filter(s => s.priority === 'low').length) / scenarios.length) * 100) : 0}%`],
                  ].map(([label, value]) => (
                    <div key={label} className="flex items-center justify-between p-2 rounded bg-accent">
                      <span className="text-muted-foreground">{label}</span>
                      <span className="font-mono text-foreground">{value}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {activeSheet === 'Inventory' && (
              <div className="space-y-2">
                <p className="text-xs font-semibold text-foreground">Application Inventory</p>
                <p className="text-[10px] text-muted-foreground">All discovered pages, forms, inputs, and UI components.</p>
                <div className="text-[10px] text-muted-foreground italic">
                  Full inventory available in the Inventory tab.
                </div>
              </div>
            )}

            {activeSheet === 'Modules' && (
              <div className="space-y-2">
                <p className="text-xs font-semibold text-foreground">Detected Modules</p>
                <div className="space-y-1">
                  {modules.map((m) => (
                    <div key={m.name} className="flex items-center justify-between p-2 rounded bg-accent">
                      <span className="text-[10px] text-foreground">{m.name}</span>
                      <span className="text-[10px] text-muted-foreground">{m.scenarioCount} scenarios</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {activeSheet === 'Scenarios' && (
              <div className="space-y-2">
                <p className="text-xs font-semibold text-foreground">Test Scenarios</p>
                <p className="text-[10px] text-muted-foreground">
                  {scenarioCount} scenarios generated. View all in the scenario cards above.
                </p>
              </div>
            )}

            {activeSheet === 'Test Data' && (
              <div className="space-y-2">
                <p className="text-xs font-semibold text-foreground">Test Data</p>
                <p className="text-[10px] text-muted-foreground">Required test data for scenario execution.</p>
              </div>
            )}
          </div>
        </div>
      )}

      {runId && (
        <div className="flex gap-2">
          <a
            href={`${apiBase}/api/v1/runs/${runId}/test-plan/export`}
            className="flex-1 flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium transition-colors"
          >
            <Download className="h-3.5 w-3.5" />
            Download Excel (.xlsx)
          </a>
          <a
            href={`${apiBase}/api/v1/runs/${runId}/artifacts/test-plan`}
            download
            className="flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg bg-muted hover:bg-secondary border border-input text-foreground text-xs font-medium transition-colors"
          >
            <FileSpreadsheet className="h-3.5 w-3.5" />
            JSON
          </a>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// HumanReviewPanel
// ---------------------------------------------------------------------------

interface HumanReviewPanelProps {
  runId: string;
}

type ReviewFilter = 'all' | 'critical' | 'high' | 'medium' | 'low';

function StatCard({ icon: Icon, value, label, color, suffix }: { icon: React.ElementType; value: number; label: string; color: string; suffix?: string }) {
  const colors: Record<string, string> = {
    blue: 'text-blue-400',
    red: 'text-red-400',
    amber: 'text-amber-400',
    emerald: 'text-emerald-400',
  };
  return (
    <div className="p-2 rounded-lg bg-muted border border-border text-center">
      <Icon className={cn('h-3.5 w-3.5 mx-auto mb-0.5', colors[color] || 'text-muted-foreground')} />
      <p className={cn('text-sm font-bold tabular-nums', colors[color] || 'text-muted-foreground')}>{value}{suffix || ''}</p>
      <p className="text-[9px] text-muted-foreground">{label}</p>
    </div>
  );
}

export function HumanReviewPanel({ runId }: HumanReviewPanelProps) {
  const required        = useWorkflowStore((s) => s.humanReviewRequired);
  const testPlanReady   = useWorkflowStore((s) => s.testPlanGenerated);
  const scenarioCount   = useWorkflowStore((s) => s.testPlanScenarioCount);
  const stages          = useWorkflowStore((s) => s.stages);
  const modules         = useWorkflowStore((s) => s.detectedModules);
  const scenarios       = useWorkflowStore((s) => s.generatedScenarios);
  const overallStatus   = useWorkflowStore((s) => s.overallStatus);
  const reviewStage     = stages.find((s) => s.id === 'human_review');
  const codeGenStage    = stages.find((s) => s.id === 'code_generation');

  const [submitting, setSubmitting]  = useState(false);
  const [decision, setDecision]      = useState<'approved' | 'rejected' | null>(null);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const [feedbackText, setFeedbackText] = useState('');
  const [searchTerm, setSearchTerm]   = useState('');
  const [filterPriority, setFilterPriority] = useState<ReviewFilter>('all');
  const [expandedScenarios, setExpandedScenarios] = useState<Set<string>>(new Set());
  // Selective approval: stable test-case ID selection, independent of the
  // scenario data itself. Survives filter/search changes.
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [approvedIds, setApprovedIds] = useState<Set<string>>(new Set());

  const isCompleted = overallStatus === 'completed' || codeGenStage?.status === 'completed' || reviewStage?.status === 'completed';
  const isActive = required || reviewStage?.status === 'waiting_for_user' || testPlanReady || isCompleted;

  const filteredScenarios = React.useMemo(() => {
    let s = scenarios;
    if (filterPriority !== 'all') s = s.filter((sc) => sc.priority === filterPriority);
    if (searchTerm.trim()) {
      const q = searchTerm.toLowerCase();
      s = s.filter((sc) =>
        sc.title?.toLowerCase().includes(q) ||
        sc.description?.toLowerCase().includes(q) ||
        sc.module?.toLowerCase().includes(q)
      );
    }
    return s;
  }, [scenarios, filterPriority, searchTerm]);

  const criticalCount = scenarios.filter((s) => s.priority === 'critical').length;
  const highCount     = scenarios.filter((s) => s.priority === 'high').length;
  const mediumCount   = scenarios.filter((s) => s.priority === 'medium').length;
  const lowCount      = scenarios.filter((s) => s.priority === 'low').length;

  const categoryCounts = React.useMemo(() => {
    const m: Record<string, number> = {};
    scenarios.forEach((s) => {
      const c = s.category || 'functional';
      m[c] = (m[c] || 0) + 1;
    });
    return m;
  }, [scenarios]);

  const toggleExpand = (id: string) => {
    setExpandedScenarios((prev) => {
      const n = new Set(prev);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  };

  // ── Selective approval (stable IDs, filter-aware) ─────────────────────────
  const visibleIds = filteredScenarios.map((s) => s.id);
  const allVisibleSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedIds.has(id));
  const someVisibleSelected = visibleIds.some((id) => selectedIds.has(id));
  const selectedCount = selectedIds.size;

  const headerCheckboxRef = React.useRef<HTMLInputElement>(null);
  React.useEffect(() => {
    if (headerCheckboxRef.current) {
      headerCheckboxRef.current.indeterminate = someVisibleSelected && !allVisibleSelected;
    }
  }, [someVisibleSelected, allVisibleSelected]);

  const toggleSelect = (id: string) => {
    // Selecting a checkbox never mutates the scenario data itself.
    setSelectedIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    // Select All applies ONLY to the currently visible/filtered set; selections
    // of hidden rows are preserved. Unchecking clears the visible selections.
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (allVisibleSelected) {
        visibleIds.forEach((id) => next.delete(id));
      } else {
        visibleIds.forEach((id) => next.add(id));
      }
      return next;
    });
  };

  const clearSelection = () => setSelectedIds(new Set());

  if (!isActive) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-muted-foreground gap-3">
        <UserCheck className="h-10 w-10 animate-pulse" />
        <p className="text-xs">Human review panel will activate once test plan is ready.</p>
      </div>
    );
  }

  const handleApprove = async () => {
    const toApprove = Array.from(selectedIds);
    if (toApprove.length === 0 || submitting) return;
    setSubmitting(true);
    try {
      const apiBase = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
      const res = await fetch(`${apiBase}/api/v1/runs/${runId}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ test_case_ids: toApprove }),
      });
      if (!res.ok) {
        let detail = `Approve request failed (${res.status})`;
        try {
          const err = await res.json();
          if (err?.detail) detail = String(err.detail);
        } catch {
          // non-JSON error body — keep HTTP fallback message
        }
        console.warn(detail);
        toast.error(detail);
        return; // selection preserved — backend approved nothing
      }
      const data = await res.json().catch(() => null);
      const approvedIdsResult = (data?.approved_test_case_ids as string[] | undefined) ?? toApprove;
      setApprovedIds((prev) => {
        const next = new Set(prev);
        approvedIdsResult.forEach((id) => next.add(id));
        return next;
      });
      setSelectedIds(new Set());
      setDecision('approved');
      toast.success(`Approved ${approvedIdsResult.length} test case${approvedIdsResult.length !== 1 ? 's' : ''}`);
    } catch (e) {
      console.error('Approve failed:', e);
      toast.error('Approval failed. Your selection was preserved.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleRejectClick = () => {
    setFeedbackOpen(true);
  };

  const handleRejectSubmit = async () => {
    setSubmitting(true);
    setDecision('rejected');
    setFeedbackOpen(false);
    try {
      const apiBase = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
      await fetch(`${apiBase}/api/v1/runs/${runId}/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ feedback: feedbackText }),
      });
    } catch (e) {
      console.error('Reject failed:', e);
    } finally {
      setSubmitting(false);
    }
  };

  const PriorityBadge = ({ p }: { p: string }) => {
    const colors: Record<string, string> = {
      critical: 'bg-red-500/20 text-red-400 border-red-500/40',
      high: 'bg-orange-500/20 text-orange-400 border-orange-500/40',
      medium: 'bg-amber-500/20 text-amber-400 border-amber-500/40',
      low: 'bg-muted text-muted-foreground border-input',
    };
    return (
      <span className={cn('text-[10px] px-1.5 py-0.5 rounded border font-semibold uppercase', colors[p] || colors.low)}>
        {p}
      </span>
    );
  };

  const CategoryBadge = ({ c }: { c: string }) => (
    <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted border border-input text-muted-foreground capitalize">
      {c.replace(/_/g, ' ')}
    </span>
  );

  const apiBase = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

  return (
    <div className="space-y-4">
      {isCompleted && !decision && (
        <div className="flex items-center gap-3 px-4 py-3 rounded-xl border border-emerald-500/50 bg-emerald-500/10 text-emerald-300">
          <CheckCircle2 className="h-5 w-5 text-emerald-400 shrink-0" />
          <div>
            <p className="text-sm font-semibold">Human Review Completed</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              The test plan has already been approved and processed for this workflow.
            </p>
          </div>
        </div>
      )}

      {!isCompleted && !decision && (
        <div className="flex items-start gap-3 px-4 py-3 rounded-xl border border-amber-400/50 bg-amber-400/10">
          <AlertTriangle className="h-5 w-5 text-amber-400 shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-semibold text-amber-300">Human Review Required</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              Review the AI-generated test plan with <span className="font-mono text-amber-300">{scenarioCount}</span> scenarios
              across <span className="font-mono text-amber-300">{modules.length}</span> modules.
            </p>
          </div>
        </div>
      )}

      {decision && (
        <div className={cn(
          'flex items-center justify-center gap-2 px-4 py-3 rounded-xl border text-sm font-medium',
          decision === 'approved'
            ? 'border-emerald-500/50 bg-emerald-500/10 text-emerald-400'
            : 'border-red-500/50 bg-red-500/10 text-red-400'
        )}>
          {decision === 'approved' ? <ThumbsUp className="h-4 w-4" /> : <ThumbsDown className="h-4 w-4" />}
          Review {decision === 'approved'
            ? (approvedIds.size > 0 ? `${approvedIds.size} of ${scenarioCount} scenarios approved` : 'Approved')
            : 'Rejected'} &mdash; Workflow continuing...
        </div>
      )}

      {/* Summary stat cards */}
      <div className="grid grid-cols-4 gap-2">
        <StatCard icon={FileText} value={scenarioCount} label="Total Scenarios" color="blue" />
        <StatCard icon={AlertTriangle} value={criticalCount + highCount} label="Critical / High" color="red" />
        <StatCard icon={Shield} value={modules.length} label="Modules" color="amber" />
        <StatCard icon={Zap} value={scenarioCount > 0 ? Math.round(((scenarioCount - lowCount) / scenarioCount) * 100) : 0} label="Auto %" color="emerald" suffix="%" />
      </div>

      {/* Priority distribution bar */}
      <div className="flex items-center gap-2 h-5 rounded-full overflow-hidden bg-muted">
        {criticalCount > 0 && (
          <div className="bg-red-500 h-full text-[9px] flex items-center justify-center text-white font-semibold" style={{ width: `${(criticalCount / scenarioCount) * 100}%` }}>
            {criticalCount}
          </div>
        )}
        {highCount > 0 && (
          <div className="bg-orange-500 h-full text-[9px] flex items-center justify-center text-white font-semibold" style={{ width: `${(highCount / scenarioCount) * 100}%` }}>
            {highCount}
          </div>
        )}
        {mediumCount > 0 && (
          <div className="bg-amber-500 h-full text-[9px] flex items-center justify-center text-zinc-900 font-semibold" style={{ width: `${(mediumCount / scenarioCount) * 100}%` }}>
            {mediumCount}
          </div>
        )}
        {lowCount > 0 && (
          <div className="bg-zinc-500 h-full text-[9px] flex items-center justify-center text-white font-semibold" style={{ width: `${(lowCount / scenarioCount) * 100}%` }}>
            {lowCount}
          </div>
        )}
      </div>

      {/* Category breakdown */}
      <div className="flex flex-wrap gap-1">
        {Object.entries(categoryCounts).map(([cat, count]) => (
          <span key={cat} className="text-[10px] px-2 py-0.5 rounded-full bg-muted border border-input text-muted-foreground capitalize">
            {cat.replace(/_/g, ' ')} ({count})
          </span>
        ))}
      </div>

      {/* Module chips */}
      {modules.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {modules.map((m) => (
            <span key={m.name} className="text-[10px] px-2 py-0.5 rounded-full bg-blue-500/10 border border-blue-500/30 text-blue-400">
              {m.name} ({m.scenarioCount})
            </span>
          ))}
        </div>
      )}

      {/* Search & Filters */}
      <div className="flex gap-2">
        <div className="flex-1 relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search scenarios..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-7 pr-3 py-1.5 text-xs rounded-lg bg-muted border border-input text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-amber-500/50"
          />
        </div>
        <select
          value={filterPriority}
          onChange={(e) => setFilterPriority(e.target.value as ReviewFilter)}
          className="px-2 py-1.5 text-xs rounded-lg bg-muted border border-input text-foreground focus:outline-none focus:border-amber-500/50"
        >
          <option value="all">All Priorities</option>
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
      </div>

      {/* Scenario table */}
      <div className="max-h-64 overflow-y-auto rounded-lg border border-input">
        {filteredScenarios.length === 0 ? (
          <div className="flex items-center justify-center py-8 text-muted-foreground text-xs">
            No scenarios match the current filter.
          </div>
        ) : (
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-muted">
              <tr className="text-muted-foreground text-left">
                <th className="py-2 px-2 font-medium w-8">
                  <input
                    ref={headerCheckboxRef}
                    type="checkbox"
                    checked={allVisibleSelected}
                    onChange={toggleSelectAll}
                    title={allVisibleSelected ? 'Clear selection' : 'Select all visible test cases'}
                    className="accent-emerald-500"
                  />
                </th>
                <th className="py-2 px-3 font-medium w-20">ID</th>
                <th className="py-2 px-3 font-medium">Title</th>
                <th className="py-2 px-3 font-medium w-20">Priority</th>
                <th className="py-2 px-3 font-medium w-24">Category</th>
                <th className="py-2 px-3 font-medium w-16"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {filteredScenarios.map((sc) => {
                const isExpanded = expandedScenarios.has(sc.id);
                const isSelected = selectedIds.has(sc.id);
                const isApproved = approvedIds.has(sc.id);
                return (
                  <React.Fragment key={sc.id}>
                    <tr
                      className="hover:bg-accent cursor-pointer transition-colors"
                      onClick={() => toggleExpand(sc.id)}
                    >
                      <td className="py-1.5 px-2 w-8" onClick={(e) => e.stopPropagation()}>
                        {isApproved ? (
                          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" aria-label="Approved" />
                        ) : (
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => toggleSelect(sc.id)}
                            className="accent-emerald-500"
                          />
                        )}
                      </td>
                      <td className="py-1.5 px-3 font-mono text-muted-foreground">{sc.id}</td>
                      <td className="py-1.5 px-3 text-foreground">
                        {sc.title}
                        {approvedIds.size > 0 && (
                          <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/15 border border-emerald-500/40 text-emerald-400 font-semibold uppercase">
                            Approved
                          </span>
                        )}
                      </td>
                      <td className="py-1.5 px-3"><PriorityBadge p={sc.priority} /></td>
                      <td className="py-1.5 px-3"><CategoryBadge c={sc.category || 'functional'} /></td>
                      <td className="py-1.5 px-3 text-muted-foreground">
                        {isExpanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr className="bg-muted/50">
                        <td colSpan={6} className="px-4 py-3">
                          <div className="text-xs space-y-2">
                            <div className="flex gap-4 text-muted-foreground">
                              <span>Module: <span className="text-foreground">{sc.module || '-'}</span></span>
                              <span>Risk: <span className="text-foreground capitalize">{sc.riskLevel || 'medium'}</span></span>
                            </div>
                            <p className="text-muted-foreground">{sc.description}</p>
                            {(sc as any).test_steps?.length > 0 && (
                              <div>
                                <p className="text-[11px] font-semibold text-muted-foreground mb-1">Test Steps</p>
                                <ol className="list-decimal list-inside space-y-0.5 text-muted-foreground">
                                  {(sc as any).test_steps.map((step: string, i: number) => (
                                    <li key={i} className="leading-relaxed">{step}</li>
                                  ))}
                                </ol>
                              </div>
                            )}
                            {(sc as any).expected_result && (
                              <p className="text-muted-foreground"><span className="text-muted-foreground">Expected:</span> {(sc as any).expected_result}</p>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Actions */}
      {!decision ? (
        <div className="space-y-2">
          <div className="flex gap-3">
            <button
              onClick={handleApprove}
              disabled={submitting || isCompleted || selectedCount === 0}
              className={cn(
                "flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl font-semibold text-sm transition-colors",
                isCompleted
                  ? "bg-emerald-950/60 border border-emerald-500/40 text-emerald-400 cursor-not-allowed opacity-80"
                  : "bg-emerald-600 hover:bg-emerald-500 text-white disabled:opacity-50 disabled:cursor-not-allowed"
              )}
            >
              {submitting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : isCompleted ? (
                <CheckCircle2 className="h-4 w-4 text-emerald-400" />
              ) : (
                <ThumbsUp className="h-4 w-4" />
              )}
              {isCompleted
                ? 'Approved'
                : selectedCount > 0
                ? `Approve Selected (${selectedCount})`
                : 'Approve Selected'}
            </button>
            <button
              onClick={handleRejectClick}
              disabled={submitting || isCompleted}
              className={cn(
                "flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl font-semibold text-sm transition-colors",
                isCompleted
                  ? "bg-muted border border-border text-muted-foreground cursor-not-allowed opacity-50"
                  : "bg-muted hover:bg-red-900/50 border border-input hover:border-red-500/50 text-foreground disabled:opacity-50 disabled:cursor-not-allowed"
              )}
            >
              <ThumbsDown className="h-4 w-4" />
              Reject
            </button>
          </div>
          <div className="flex gap-2">
            <button
              disabled
              className="flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-accent border border-border text-muted-foreground text-xs cursor-not-allowed"
            >
              <Edit3 className="h-3.5 w-3.5" />
              Edit Scenarios
            </button>
            <button
              disabled
              className="flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-accent border border-border text-muted-foreground text-xs cursor-not-allowed"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Regenerate
            </button>
          </div>
        </div>
      ) : (
        <div className={cn(
          'flex items-center justify-center gap-2 px-4 py-3 rounded-xl border text-sm font-medium',
          decision === 'approved' ? 'border-emerald-500/50 bg-emerald-500/10 text-emerald-400' : 'border-red-500/50 bg-red-500/10 text-red-400'
        )}>
          {decision === 'approved' ? <ThumbsUp className="h-4 w-4" /> : <ThumbsDown className="h-4 w-4" />}
          Review {decision === 'approved'
            ? (approvedIds.size > 0 ? `${approvedIds.size} of ${scenarioCount} scenarios approved` : 'Approved')
            : 'Rejected'} &mdash; Workflow continuing...
        </div>
      )}

      {/* Downloads */}
      <div className="flex gap-2">
        <a
          href={`${apiBase}/api/v1/runs/${runId}/test-plan/export`}
          className="flex-1 flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium transition-colors"
        >
          <Download className="h-3.5 w-3.5" />
          Download Excel (.xlsx)
        </a>
        <a
          href={`${apiBase}/api/v1/runs/${runId}/artifacts/test-plan`}
          download
          className="flex items-center justify-center gap-2 px-3 py-2.5 rounded-lg bg-muted hover:bg-secondary border border-input text-foreground text-xs font-medium transition-colors"
        >
          <FileSpreadsheet className="h-3.5 w-3.5" />
          View JSON
        </a>
      </div>

      {/* Feedback dialog (reject) */}
      {feedbackOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-muted border border-input rounded-xl w-full max-w-md mx-4 shadow-2xl">
            <div className="flex items-center justify-between px-4 py-3 border-b border-border">
              <div className="flex items-center gap-2">
                <MessageSquare className="h-4 w-4 text-amber-400" />
                <h3 className="text-sm font-semibold text-foreground">Reject Test Plan</h3>
              </div>
              <button onClick={() => setFeedbackOpen(false)} className="text-muted-foreground hover:text-foreground">
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="p-4 space-y-3">
              <p className="text-xs text-muted-foreground">Please explain what changes are needed before this test plan can be approved.</p>
              <textarea
                value={feedbackText}
                onChange={(e) => setFeedbackText(e.target.value)}
                placeholder="e.g. Add more boundary test scenarios, missing login validation edge cases, need API-level tests for /api/users endpoint..."
                rows={4}
                className="w-full px-3 py-2 text-xs rounded-lg bg-muted border border-input text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-amber-500/50 resize-none"
              />
            </div>
            <div className="flex gap-3 px-4 py-3 border-t border-border">
              <button
                onClick={() => setFeedbackOpen(false)}
                className="flex-1 px-3 py-2 rounded-lg bg-muted border border-input text-foreground text-xs font-medium hover:bg-secondary transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleRejectSubmit}
                disabled={!feedbackText.trim() || submitting}
                className="flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-red-600 hover:bg-red-500 text-white text-xs font-medium transition-colors disabled:opacity-50"
              >
                {submitting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ThumbsDown className="h-3.5 w-3.5" />}
                Reject & Request Changes
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
