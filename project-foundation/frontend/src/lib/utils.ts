import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDate(date: string | Date): string {
  return new Date(date).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

export function formatDateTime(date: string | Date): string {
  return new Date(date).toLocaleString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function formatDuration(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;

  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  if (minutes > 0) {
    return `${minutes}m ${secs}s`;
  }
  return `${secs}s`;
}

export function truncate(str: string, length: number): string {
  if (str.length <= length) return str;
  return str.slice(0, length) + '...';
}

export function normalizePhase(phase?: string | null): 'trigger' | 'crawler' | 'inventory' | 'test_design' | 'human_review' | 'code_generation' | 'execution' | 'reporting' {
  if (!phase) return 'trigger';
  const p = String(phase).toLowerCase().trim().replace(/-/g, '_');
  if (p === 'initialization' || p === 'init' || p === 'setup' || p === 'trigger' || p === 'project') return 'trigger';
  if (p === 'crawler' || p === 'crawl' || p === 'web_crawler') return 'crawler';
  if (p === 'inventory' || p === 'inventory_aggregation') return 'inventory';
  if (p === 'test_design' || p === 'testdesign' || p === 'test_plan' || p === 'design') return 'test_design';
  if (p === 'human_review' || p === 'review' || p === 'humanreview') return 'human_review';
  if (p === 'code_generation' || p === 'code_gen' || p === 'codegen' || p === 'playwright_generation') return 'code_generation';
  if (p === 'execution' || p === 'exec' || p === 'test_execution') return 'execution';
  if (p === 'reporting' || p === 'report' || p === 'reports') return 'reporting';
  return 'trigger';
}

