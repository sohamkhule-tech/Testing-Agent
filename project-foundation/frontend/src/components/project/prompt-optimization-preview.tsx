'use client';

import React from 'react';
import { Sparkles, Check, X, Cpu, ArrowRight } from 'lucide-react';
import type { TokenUsageInfo } from '@/types/api';

interface PromptOptimizationPreviewProps {
  originalPrompt: string;
  optimizedPrompt: string;
  usage: TokenUsageInfo;
  model?: string;
  onUseOptimized: (optimizedText: string) => void;
  onKeepOriginal: () => void;
}

export function PromptOptimizationPreview({
  originalPrompt,
  optimizedPrompt,
  usage,
  model,
  onUseOptimized,
  onKeepOriginal,
}: PromptOptimizationPreviewProps) {
  return (
    <div className="rounded-xl border border-blue-500/30 bg-card p-4 space-y-4 shadow-xl text-card-foreground animate-in fade-in-50 duration-200">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border pb-3">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-blue-500/10 text-blue-500">
            <Sparkles className="h-4 w-4" />
          </div>
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-foreground">
              Optimized Prompt Preview
            </h4>
            <p className="text-[11px] text-muted-foreground">
              Transformed into a structured testing instruction while preserving your original intent.
            </p>
          </div>
        </div>

        {/* Token badge */}
        <div className="flex items-center gap-2">
          {model && (
            <span className="hidden sm:inline-flex items-center gap-1 text-[11px] text-muted-foreground bg-muted px-2 py-0.5 rounded-md font-mono">
              <Cpu className="h-3 w-3" />
              {model}
            </span>
          )}
          <span className="inline-flex items-center gap-1 text-[11px] font-mono font-medium px-2.5 py-1 rounded-full bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20">
            ✨ {usage.totalTokens || usage.promptTokens + usage.completionTokens} tokens
          </span>
        </div>
      </div>

      {/* Comparison Grid */}
      <div className="grid gap-3 md:grid-cols-2">
        {/* Original Prompt */}
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <label className="text-[11px] font-medium text-muted-foreground uppercase tracking-wide">
              Original Prompt
            </label>
          </div>
          <div className="p-3 rounded-lg bg-muted/60 border border-border/60 font-mono text-xs text-muted-foreground whitespace-pre-wrap max-h-48 overflow-y-auto leading-relaxed">
            {originalPrompt}
          </div>
        </div>

        {/* Optimized Prompt */}
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <label className="text-[11px] font-semibold text-blue-500 dark:text-blue-400 uppercase tracking-wide flex items-center gap-1">
              Optimized Prompt <ArrowRight className="h-3 w-3" />
            </label>
          </div>
          <div className="p-3 rounded-lg bg-blue-500/5 dark:bg-blue-950/20 border border-blue-500/30 font-mono text-xs text-foreground whitespace-pre-wrap max-h-48 overflow-y-auto leading-relaxed font-normal shadow-inner">
            {optimizedPrompt}
          </div>
        </div>
      </div>

      {/* Token breakdown footer */}
      <div className="flex items-center justify-between text-[11px] text-muted-foreground font-mono pt-1">
        <div className="flex items-center gap-3">
          <span>Input: {usage.promptTokens} tokens</span>
          <span>•</span>
          <span>Output: {usage.completionTokens} tokens</span>
          <span>•</span>
          <span>Total: {usage.totalTokens} tokens</span>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="flex items-center gap-2 pt-2 border-t border-border">
        <button
          type="button"
          onClick={() => onUseOptimized(optimizedPrompt)}
          className="flex-1 flex items-center justify-center gap-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold py-2.5 px-4 shadow-md transition-all"
        >
          <Check className="h-4 w-4" />
          <span>Use Optimized Prompt</span>
        </button>

        <button
          type="button"
          onClick={onKeepOriginal}
          className="flex items-center justify-center gap-1.5 rounded-lg border border-input hover:border-foreground/40 bg-background text-muted-foreground hover:text-foreground text-xs font-medium py-2.5 px-4 transition-colors"
        >
          <X className="h-4 w-4" />
          <span>Keep Original</span>
        </button>
      </div>
    </div>
  );
}
