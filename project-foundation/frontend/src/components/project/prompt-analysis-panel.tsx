'use client';

/**
 * Prompt Analysis Panel
 *
 * Transparent AI interpretation of the user's test instructions.
 * Displayed between prompt input and run start — user must approve before
 * any crawling begins.
 *
 * Sections:
 *  1. Live reasoning animation (steps stream in one-by-one)
 *  2. Scope visualisation (included ✓ / excluded ✗ modules)
 *  3. Confidence scores per extracted item
 *  4. Execution plan (ordered steps)
 *  5. Credential status & warnings
 *  6. Ambiguity warnings
 *  7. Prompt quality score
 *  8. Final execution summary
 *  9. Action buttons: Approve / Edit Prompt / Regenerate
 */

import React, { useEffect, useState, useRef } from 'react';
import {
  CheckCircle2, XCircle, AlertTriangle, Shield, ChevronRight,
  Loader2, RefreshCw, Edit3, Play, Info, Zap, Target,
  FileText, Settings, Clock,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type {
  PromptAnalysis, ConfidenceItem, ExecutionStep, PromptAmbiguity,
} from '@/types/api';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PromptAnalysisPanelProps {
  analysis: PromptAnalysis;
  isLoading: boolean;
  onApprove: () => void;
  onEdit: () => void;
  onRegenerate: () => void;
  isStarting: boolean;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function QualityBar({ score }: { score: number }) {
  const color =
    score >= 80 ? 'bg-emerald-500' :
    score >= 60 ? 'bg-yellow-500' :
    'bg-red-500';
  const label =
    score >= 80 ? 'text-emerald-400' :
    score >= 60 ? 'text-yellow-400' :
    'text-red-400';
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted-foreground">Prompt Quality</span>
        <span className={`font-bold text-base ${label}`}>{score}/100</span>
      </div>
      <div className="h-2 rounded-full bg-muted overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ${color}`}
          style={{ width: `${score}%` }}
        />
      </div>
    </div>
  );
}

function ConfidencePill({ item }: { item: ConfidenceItem }) {
  const colorClass =
    item.value >= 90 ? 'text-emerald-600 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-950/40' :
    item.value >= 75 ? 'text-blue-600 dark:text-blue-400 border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-950/40' :
    'text-yellow-600 dark:text-yellow-400 border-yellow-200 dark:border-yellow-800 bg-yellow-50 dark:bg-yellow-950/40';
  return (
    <div className={`flex items-center justify-between rounded border px-2 py-1 ${colorClass}`}>
      <span className="text-xs truncate max-w-[140px]">{item.label}</span>
      <span className="text-xs font-bold ml-2 shrink-0">{item.value}%</span>
    </div>
  );
}

function ScopeRow({ label, included }: { label: string; included: boolean }) {
  return (
    <div className="flex items-center gap-2 text-sm py-0.5">
      {included
        ? <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
        : <XCircle className="h-4 w-4 text-red-500 shrink-0" />}
      <span className={included ? 'text-foreground' : 'text-muted-foreground line-through'}>{label}</span>
    </div>
  );
}

function StepNode({ step }: { step: ExecutionStep }) {
  return (
    <div className="flex items-start gap-3">
      <div className="flex flex-col items-center shrink-0">
        <div className="w-7 h-7 rounded-full bg-muted border border-border flex items-center justify-center text-xs font-bold text-foreground">
          {step.step}
        </div>
        {/* connector line — rendered by the parent */}
      </div>
      <div className="pb-4">
        <div className="flex items-center gap-1.5 text-sm font-medium text-foreground">
          <span>{step.icon}</span>
          <span>{step.label}</span>
        </div>
        <p className="text-xs text-muted-foreground mt-0.5">{step.description}</p>
      </div>
    </div>
  );
}

function CredentialBadge({ detected, label }: { detected: boolean; label: string }) {
  return (
    <div className="flex items-center gap-1.5 text-xs">
      {detected
        ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
        : <XCircle className="h-3.5 w-3.5 text-red-500" />}
      <span className={detected ? 'text-foreground' : 'text-muted-foreground'}>{label}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Live reasoning animation
// ---------------------------------------------------------------------------

function LiveReasoning({ steps, active }: { steps: string[]; active: boolean }) {
  const [visible, setVisible] = useState<string[]>([]);
  const idx = useRef(0);

  useEffect(() => {
    if (!active || steps.length === 0) {
      setVisible(steps); // show all immediately when done
      return;
    }
    setVisible([]);
    idx.current = 0;
    const interval = setInterval(() => {
      if (idx.current < steps.length) {
        setVisible(prev => [...prev, steps[idx.current]]);
        idx.current += 1;
      } else {
        clearInterval(interval);
      }
    }, 280);
    return () => clearInterval(interval);
  }, [steps, active]);

  if (visible.length === 0 && !active) return null;

  return (
    <div className="rounded-lg border border-border bg-muted/60 p-3 space-y-1">
      <p className="text-[11px] uppercase tracking-wider text-muted-foreground mb-2">AI Reasoning</p>
      {visible.map((s, i) => (
        <div key={i} className="flex items-center gap-2 text-xs text-muted-foreground">
          <CheckCircle2 className="h-3 w-3 text-blue-500 shrink-0" />
          <span>{s}</span>
        </div>
      ))}
      {active && visible.length < steps.length && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="h-3 w-3 animate-spin shrink-0" />
          <span>Analysing…</span>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main panel
// ---------------------------------------------------------------------------

export function PromptAnalysisPanel({
  analysis,
  isLoading,
  onApprove,
  onEdit,
  onRegenerate,
  isStarting,
}: PromptAnalysisPanelProps) {
  const { interpretation, confidence_scores, execution_plan, quality,
          ambiguities, credential_status, scope_summary, estimated,
          reasoning_steps } = analysis;

  const hasScope = scope_summary.included_modules.length > 0 || scope_summary.excluded_modules.length > 0;
  const hasCredWarnings = credential_status.warnings.length > 0;
  const hasAmbiguities = ambiguities.length > 0;

  return (
    <div className="space-y-4 animate-in fade-in slide-in-from-top-2 duration-300">
      {/* ── Header ── */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Zap className="h-4 w-4 text-blue-400" />
          <h3 className="text-sm font-semibold text-foreground">AI Prompt Analysis</h3>
        </div>
        <button
          onClick={onRegenerate}
          disabled={isLoading}
          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors disabled:opacity-40"
        >
          <RefreshCw className={`h-3 w-3 ${isLoading ? 'animate-spin' : ''}`} />
          Regenerate
        </button>
      </div>

      {/* ── Live Reasoning ── */}
      <LiveReasoning steps={reasoning_steps} active={isLoading} />

      {isLoading ? (
        <div className="flex items-center gap-2 text-xs text-muted-foreground py-4 justify-center">
          <Loader2 className="h-4 w-4 animate-spin" />
          Analysing prompt…
        </div>
      ) : (
        <>
          {/* ── Scope Visualisation ── */}
          {hasScope && (
            <div className="rounded-lg border border-border bg-muted/40 p-3">
              <p className="text-[11px] uppercase tracking-wider text-muted-foreground mb-2 flex items-center gap-1">
                <Target className="h-3 w-3" /> Modules
              </p>
              <div className="grid grid-cols-2 gap-x-4">
                <div>
                  {scope_summary.included_modules.map(m => (
                    <ScopeRow key={m} label={m} included />
                  ))}
                </div>
                <div>
                  {scope_summary.excluded_modules.map(m => (
                    <ScopeRow key={m} label={m} included={false} />
                  ))}
                </div>
              </div>
              {scope_summary.included_pages.length > 0 && (
                <div className="mt-2 border-t border-border pt-2">
                  <p className="text-[11px] text-muted-foreground mb-1">URL Scope</p>
                  {scope_summary.included_pages.map(p => <ScopeRow key={p} label={p} included />)}
                  {scope_summary.excluded_pages.map(p => <ScopeRow key={p} label={p} included={false} />)}
                </div>
              )}
            </div>
          )}

          {/* ── Interpretation summary chips ── */}
          <div className="flex flex-wrap gap-1.5">
            {interpretation.coverage?.map(c => (
              <Badge key={c} variant="secondary" className="bg-purple-100 text-purple-700 border-purple-300 dark:bg-purple-950/60 dark:text-purple-300 dark:border-purple-800 text-xs">
                {c}
              </Badge>
            ))}
            {interpretation.output?.map(o => (
              <Badge key={o} variant="secondary" className="bg-blue-100 text-blue-700 border-blue-300 dark:bg-blue-950/60 dark:text-blue-300 dark:border-blue-800 text-xs">
                {o}
              </Badge>
            ))}
            {interpretation.authentication?.required && (
              <Badge variant="secondary" className={`text-xs ${interpretation.authentication.complete
                ? 'bg-emerald-100 text-emerald-700 border-emerald-300 dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-800'
                : 'bg-yellow-100 text-yellow-700 border-yellow-300 dark:bg-yellow-950/60 dark:text-yellow-300 dark:border-yellow-800'}`}>
                {interpretation.authentication.complete ? '🔐 Auth: Complete' : '⚠️ Auth: Partial'}
              </Badge>
            )}
          </div>

          {/* ── Confidence Scores ── */}
          {confidence_scores.length > 0 && (
            <div className="rounded-lg border border-border bg-muted/40 p-3">
              <p className="text-[11px] uppercase tracking-wider text-muted-foreground mb-2">Confidence</p>
              <div className="grid grid-cols-2 gap-1.5">
                {confidence_scores.map((c, i) => <ConfidencePill key={i} item={c} />)}
              </div>
              {confidence_scores.some(c => c.is_low) && (
                <p className="text-xs text-yellow-500 mt-2 flex items-center gap-1">
                  <AlertTriangle className="h-3 w-3" />
                  Some items have low confidence. Use <code className="bg-muted px-1 rounded">## section headers</code> for higher accuracy.
                </p>
              )}
            </div>
          )}

          {/* ── Execution Plan ── */}
          {execution_plan.length > 0 && (
            <div className="rounded-lg border border-border bg-muted/40 p-3">
              <p className="text-[11px] uppercase tracking-wider text-muted-foreground mb-3 flex items-center gap-1">
                <FileText className="h-3 w-3" /> Execution Plan
              </p>
              <div className="relative">
                {/* vertical connector */}
                <div className="absolute left-3.5 top-7 bottom-4 w-px bg-muted" />
                <div className="space-y-0">
                  {execution_plan.map(s => <StepNode key={s.step} step={s} />)}
                </div>
              </div>
            </div>
          )}

          {/* ── Credential Status ── */}
          <div className="rounded-lg border border-border bg-muted/40 p-3">
            <p className="text-[11px] uppercase tracking-wider text-muted-foreground mb-2 flex items-center gap-1">
              <Shield className="h-3 w-3" /> Authentication
            </p>
            <div className="flex gap-4">
              <CredentialBadge detected={credential_status.username_detected} label="Username" />
              <CredentialBadge detected={credential_status.password_detected} label="Password" />
              <CredentialBadge detected={credential_status.login_url_detected} label="Login URL" />
            </div>
            {hasCredWarnings && (
              <div className="mt-2 space-y-1">
                {credential_status.warnings.map((w, i) => (
                  <p key={i} className="text-xs text-yellow-500 flex items-start gap-1">
                    <AlertTriangle className="h-3 w-3 shrink-0 mt-0.5" />{w}
                  </p>
                ))}
              </div>
            )}
            {credential_status.is_complete && (
              <p className="text-xs text-emerald-500 mt-1 flex items-center gap-1">
                <CheckCircle2 className="h-3 w-3" /> Credentials are complete. Login will be automated.
              </p>
            )}
          </div>

          {/* ── Ambiguity Warnings ── */}
          {hasAmbiguities && (
            <div className="rounded-lg border border-yellow-300 dark:border-yellow-900/50 bg-yellow-50/60 dark:bg-yellow-950/20 p-3 space-y-2">
              <p className="text-[11px] uppercase tracking-wider text-yellow-600 flex items-center gap-1">
                <AlertTriangle className="h-3 w-3" /> Ambiguous Instructions
              </p>
              {ambiguities.map((a: PromptAmbiguity, i) => (
                <div key={i} className="text-xs">
                  <p className="text-yellow-600 dark:text-yellow-400">
                    <span className="font-mono bg-muted px-1 rounded">{a.phrase}</span>
                    {' — '}{a.message}
                  </p>
                  {a.suggestions.length > 0 && (
                    <p className="text-muted-foreground mt-0.5">
                      Suggestions: {a.suggestions.join(', ')}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* ── Prompt Quality Score ── */}
          <div className="rounded-lg border border-border bg-muted/40 p-3 space-y-2">
            <QualityBar score={quality.score} />
            {quality.strengths.length > 0 && (
              <div className="space-y-0.5">
                {quality.strengths.map((s, i) => (
                  <p key={i} className="text-xs text-emerald-500 flex items-center gap-1">
                    <CheckCircle2 className="h-3 w-3 shrink-0" />{s}
                  </p>
                ))}
              </div>
            )}
            {quality.suggestions.length > 0 && (
              <div className="space-y-0.5 border-t border-border pt-2">
                <p className="text-[11px] text-muted-foreground mb-1">Suggestions</p>
                {quality.suggestions.map((s, i) => (
                  <p key={i} className="text-xs text-muted-foreground flex items-start gap-1">
                    <Info className="h-3 w-3 shrink-0 mt-0.5 text-muted-foreground" />{s}
                  </p>
                ))}
              </div>
            )}
          </div>

          {/* ── Final Execution Summary ── */}
          <div className="rounded-lg border border-border bg-muted/60 p-3">
            <p className="text-[11px] uppercase tracking-wider text-muted-foreground mb-3 flex items-center gap-1">
              <Settings className="h-3 w-3" /> AI Execution Summary
            </p>
            <div className="grid grid-cols-3 gap-2 text-center">
              <div className="rounded bg-muted/60 p-2">
                <p className="text-lg font-bold text-foreground">{estimated.modules_estimate}</p>
                <p className="text-[10px] text-muted-foreground">Modules</p>
              </div>
              <div className="rounded bg-muted/60 p-2">
                <p className="text-lg font-bold text-foreground">{estimated.pages_range}</p>
                <p className="text-[10px] text-muted-foreground">Pages</p>
              </div>
              <div className="rounded bg-muted/60 p-2">
                <p className="text-lg font-bold text-foreground">{estimated.scenarios_range}</p>
                <p className="text-[10px] text-muted-foreground">Scenarios</p>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-2 text-center mt-2">
              <div className="rounded bg-muted/60 p-2">
                <p className="text-xs font-semibold text-foreground">{estimated.framework}</p>
                <p className="text-[10px] text-muted-foreground">Framework</p>
              </div>
              <div className="rounded bg-muted/60 p-2">
                <p className="text-xs font-semibold text-foreground">
                  {estimated.requires_auth ? 'Required' : 'Not Required'}
                </p>
                <p className="text-[10px] text-muted-foreground">Auth</p>
              </div>
              <div className="rounded bg-muted/60 p-2">
                <p className="text-xs font-semibold text-foreground flex items-center justify-center gap-1">
                  <Clock className="h-3 w-3" />{estimated.estimated_runtime_minutes} min
                </p>
                <p className="text-[10px] text-muted-foreground">Est. Runtime</p>
              </div>
            </div>
          </div>

          {/* ── Action Buttons ── */}
          <div className="flex gap-2 pt-1">
            <button
              onClick={onApprove}
              disabled={isStarting}
              className="flex-1 flex items-center justify-center gap-2 rounded-md bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm font-medium py-2 px-4 transition-colors"
            >
              {isStarting
                ? <><Loader2 className="h-4 w-4 animate-spin" /> Starting…</>
                : <><Play className="h-4 w-4" /> Approve &amp; Start Run</>}
            </button>
            <button
              onClick={onEdit}
              disabled={isStarting}
              className="flex items-center gap-1.5 rounded-md border border-input hover:border-foreground/40 text-foreground hover:text-foreground/80 text-sm py-2 px-3 transition-colors disabled:opacity-50"
            >
              <Edit3 className="h-3.5 w-3.5" /> Edit Prompt
            </button>
          </div>
        </>
      )}
    </div>
  );
}
