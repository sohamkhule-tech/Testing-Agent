import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { ExecutionMonitor } from '@/components/run-monitor/execution-monitor';
import { useWorkflowStore, type TestResult } from '@/store/workflow-store';

const results: TestResult[] = [
  { id: 'p1', name: 'passed-1', status: 'passed', timestamp: new Date().toISOString() },
  { id: 'f1', name: 'failed-1', status: 'failed', timestamp: new Date().toISOString() },
  { id: 'f2', name: 'failed-2', status: 'failed', timestamp: new Date().toISOString() },
];

function seedStore(classification: string | null) {
  useWorkflowStore.setState({
    testResults: results,
    executionStats: {
      total: 3,
      passed: 1,
      failed: 2,
      skipped: 0,
      notExecuted: 0,
      executed: 3,
      passRate: 33.3,
    },
    executionClassification: classification,
    stages: useWorkflowStore
      .getState()
      .stages.map((s) => (s.id === 'execution' ? { ...s, status: 'completed' as const } : s)),
  });
}

describe('ExecutionMonitor timeout banner', () => {
  beforeEach(() => {
    useWorkflowStore.getState().reset('run-1');
  });

  afterEach(() => {
    cleanup();
    useWorkflowStore.getState().reset(null);
  });

  it('shows "Test Execution Timed Out" only for an execution_timeout classification', () => {
    seedStore('execution_timeout');
    render(<ExecutionMonitor />);
    expect(screen.getByText('Test Execution Timed Out')).toBeTruthy();
  });

  it('does NOT show a timeout banner when tests completed with failures', () => {
    seedStore('test_execution_completed_with_failures');
    render(<ExecutionMonitor />);
    expect(screen.queryByText('Test Execution Timed Out')).toBeNull();
    // Execution monitor data remains authoritative.
    expect(screen.getByText('3')).toBeTruthy(); // Total
    expect(screen.getByText('1')).toBeTruthy(); // Passed
    expect(screen.getByText('2')).toBeTruthy(); // Failed
  });

  it('shows "Test Execution Failed" for an infrastructure_failure classification', () => {
    seedStore('infrastructure_failure');
    render(<ExecutionMonitor />);
    expect(screen.getByText('Test Execution Failed')).toBeTruthy();
    expect(screen.queryByText('Test Execution Timed Out')).toBeNull();
  });

  it('legacy playwright_timeout value is not treated as an active timeout banner', () => {
    // Runs healed by the backend no longer carry this value; ensure the UI is
    // not hard-wired to the legacy string so it cannot show a false banner.
    seedStore('playwright_timeout');
    render(<ExecutionMonitor />);
    expect(screen.queryByText('Test Execution Timed Out')).toBeNull();
  });
});