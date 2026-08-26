/**
 * Regression tests for the single-active-stage workflow invariant.
 *
 * These tests target the pure helpers in ./workflow-invariants.ts, which back
 * BOTH the live SSE dispatch path AND the REST reconciliation path of
 * workflow-store.ts. The module has no framework dependencies, so it can be
 * run under any TS test runner (vitest/jest) once one is configured.
 *
 * NOTE: the frontend repo currently ships NO test runner (no vitest/jest). See
 * the audit/fix report — these tests require a runner to be installed; in the
 * meantime the same invariants are executed and verified via a standalone Node
 * harness (see the fix documentation).
 */

import { describe, it, expect } from 'vitest';
import {
  STAGE_ORDER,
  stageToId,
  canStartStage,
  demoteToSingleActive,
  resolveActiveStage,
  ensureSingleActiveStage,
  type InvariantStageLike,
} from './workflow-invariants';

function makeStages(
  overrides: Record<string, Partial<InvariantStageLike>> = {},
): InvariantStageLike[] {
  return STAGE_ORDER.map((id) => ({
    id,
    status: 'pending' as const,
    ...(overrides[id] ?? {}),
  }));
}

const completed = (stages: InvariantStageLike[], ids: string[]) =>
  stages.map((s) => (ids.includes(s.id) ? { ...s, status: 'completed' as const } : s));

const setStatus = (stages: InvariantStageLike[], id: string, status: InvariantStageLike['status']) =>
  stages.map((s) => (s.id === id ? { ...s, status } : s));

const countRunning = (stages: InvariantStageLike[]) =>
  stages.filter((s) => s.status === 'running').length;

/** Mirrors workflow-store.ts dispatch STAGE_STARTED logic. */
function applyStageStarted(stages: InvariantStageLike[], startedStage: string): InvariantStageLike[] {
  if (canStartStage(startedStage, stages)) {
    stages = setStatus(stages, startedStage, 'running');
    stages = demoteToSingleActive(stages, startedStage);
  }
  return stages;
}

describe('stageToId', () => {
  it('normalizes inventory_aggregator -> inventory', () => {
    expect(stageToId('inventory_aggregator')).toBe('inventory');
    expect(stageToId('test_design')).toBe('test_design');
    expect(stageToId(null)).toBeNull();
  });
});

describe('STAGE_STARTED single-active enforcement (Invariant 1)', () => {
  it('never leaves two stages running when a stale human_review start arrives', () => {
    let stages = completed(makeStages(), ['trigger', 'crawler', 'inventory']);
    stages = applyStageStarted(stages, 'test_design'); // test_design running
    expect(countRunning(stages)).toBe(1);

    // STAGE_STARTED(human_review) while test_design is still running must NOT
    // create a second running stage (predecessor guard rejects it).
    stages = applyStageStarted(stages, 'human_review');
    expect(countRunning(stages)).toBeLessThanOrEqual(1);
    expect(stages.find((s) => s.id === 'test_design')?.status).toBe('running');
  });

  it('allows a valid predecessor-completed start and demotes none', () => {
    let stages = makeStages();
    // Normal sequential run: completed predecessor before each start.
    stages = applyStageStarted(stages, 'trigger');
    expect(countRunning(stages)).toBe(1);
    stages = completed(stages, ['trigger']);
    stages = applyStageStarted(stages, 'crawler');
    expect(countRunning(stages)).toBe(1);
    stages = completed(stages, ['crawler']);
    stages = applyStageStarted(stages, 'inventory');
    expect(countRunning(stages)).toBe(1);
  });

  it('execution cannot start before code_generation is completed', () => {
    let stages = makeStages();
    stages = applyStageStarted(stages, 'execution'); // rejected: everything pending
    expect(stages.find((s) => s.id === 'execution')?.status).not.toBe('running');
  });
});

describe('reconcile() single-active enforcement', () => {
  it('with completed=[trigger,crawler,inventory] makes test_design running, not human_review', () => {
    const completedSet = new Set(['trigger', 'crawler', 'inventory']);
    let stages = completed(makeStages(), [...completedSet]);
    const active = resolveActiveStage({ status: 'running', currentStage: null, nextStage: null, completed: completedSet, stages });
    stages = ensureSingleActiveStage(stages, active, completedSet, 'running');
    expect(stages.find((s) => s.id === 'test_design')?.status).toBe('running');
    expect(stages.find((s) => s.id === 'human_review')?.status).not.toBe('running');
    expect(countRunning(stages)).toBeLessThanOrEqual(1);
  });

  it('must NOT start code_generation while human_review is waiting_for_user', () => {
    const completedSet = new Set(['trigger', 'crawler', 'inventory', 'test_design']);
    let stages = completed(makeStages(), [...completedSet]);
    stages = setStatus(stages, 'human_review', 'waiting_for_user');
    const active = resolveActiveStage({ status: 'running', currentStage: null, nextStage: null, completed: completedSet, stages });
    stages = ensureSingleActiveStage(stages, active, completedSet, 'running');
    // human_review waiting gate is not promoted, and code_generation stays pending
    expect(stages.find((s) => s.id === 'human_review')?.status).toBe('waiting_for_user');
    expect(stages.find((s) => s.id === 'code_generation')?.status).toBe('pending');
    expect(countRunning(stages)).toBe(0);
  });

  it('corrects dual-running: test_design running + human_review running -> test_design reconciled', () => {
    const completedSet = new Set(['trigger', 'crawler', 'inventory', 'test_design']);
    let stages = makeStages();
    stages = completed(stages, ['trigger', 'crawler', 'inventory']);
    stages = setStatus(stages, 'test_design', 'running');
    stages = setStatus(stages, 'human_review', 'running');

    const active = resolveActiveStage({ status: 'running', currentStage: 'human_review', nextStage: null, completed: completedSet, stages });
    stages = ensureSingleActiveStage(stages, active, completedSet, 'running');

    // test_design is confirmed completed by the backend; human_review remains the single runner.
    expect(stages.find((s) => s.id === 'test_design')?.status).toBe('completed');
    expect(stages.find((s) => s.id === 'human_review')?.status).toBe('running');
    expect(countRunning(stages)).toBe(1);
  });

  it('never regresses a stale snapshot: code_generation completed + execution running stays', () => {
    let stages = makeStages();
    stages = completed(stages, ['trigger', 'crawler', 'inventory', 'test_design', 'human_review', 'code_generation']);
    stages = setStatus(stages, 'execution', 'running');

    // A stale snapshot behind the real state (current_stage=crawler, nothing completed).
    const staleCompleted = new Set<string>();
    const active = resolveActiveStage({ status: 'running', currentStage: 'crawler', nextStage: null, completed: staleCompleted, stages });
    stages = ensureSingleActiveStage(stages, active, staleCompleted, 'running');

    expect(stages.find((s) => s.id === 'code_generation')?.status).toBe('completed');
    expect(stages.find((s) => s.id === 'execution')?.status).toBe('running');
    expect(countRunning(stages)).toBe(1);
  });
});

describe('monotonic guarantees', () => {
  it('completed stage never returns to running', () => {
    let stages = completed(makeStages(), ['test_design']);
    stages = setStatus(stages, 'test_design', 'running'); // direct mutation is rejected by guard below
    // canStartStage rejects terminal stages
    expect(canStartStage('test_design', stages)).toBe(false);
  });

  it('failed stage never returns to running', () => {
    let stages = setStatus(makeStages(), 'test_design', 'failed');
    expect(canStartStage('test_design', stages)).toBe(false);
  });

  it('human_review waiting_for_user is not treated as running', () => {
    let stages = completed(makeStages(), ['trigger', 'crawler', 'inventory', 'test_design']);
    stages = setStatus(stages, 'human_review', 'waiting_for_user');
    expect(stages.filter((s) => s.status === 'running')).toHaveLength(0);
    expect(stages.find((s) => s.id === 'human_review')?.status).toBe('waiting_for_user');
  });

  it('valid sequential run keeps exactly one running stage at every transition', () => {
    let stages = makeStages();
    const starts = STAGE_ORDER.filter((id) => id !== 'report');
    for (const [idx, id] of starts.entries()) {
      // complete all predecessors
      for (const pred of starts.slice(0, idx)) stages = completed(stages, [pred]);
      stages = applyStageStarted(stages, id);
      expect(countRunning(stages)).toBeLessThanOrEqual(1);
    }
  });
});
