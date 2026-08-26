/**
 * Workflow Stage Invariants
 *
 * Pure, framework-free helpers that enforce the *single-active-stage* invariant
 * of the sequential workflow model:
 *
 *   triggering(t) states:
 *       pending → running → completed
 *       pending → running → failed
 *       pending → (human_review) → waiting_for_user → completed/running
 *
 * Guarantees (for every run):
 *   INVARIANT 1: at most ONE stage has status === "running" at any time.
 *   INVARIANT 2: a stage can only become `running` once every predecessor is
 *                `completed` (per the canonical STAGE_ORDER), except Human
 *                Review's explicit waiting_for_user gate.
 *   INVARIANT 3: completed → running is never allowed.
 *   INVARIANT 4: failed → running is never allowed.
 *   INVARIANT 5: human_review = waiting_for_user is a distinct gate and is
 *                never promoted to `running` by reconciliation (only a real
 *                backend STAGE_STARTED event may do so).
 *
 * These helpers carry no side effects and import nothing, so they are trivially
 * unit-testable in isolation and are reused by both the live SSE dispatch path
 * and the REST reconciliation path in workflow-store.ts.
 */

export const STAGE_ORDER: string[] = [
  'trigger',
  'crawler',
  'inventory',
  'test_design',
  'human_review',
  'code_generation',
  'execution',
  'report',
];

export type StageStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'waiting_for_user'
  | 'skipped';

export interface InvariantStageLike {
  id: string;
  status: StageStatus;
  startedAt?: string;
  completedAt?: string;
}

/** Normalize a backend stage id to the canonical frontend stage id. */
export function stageToId(s: string | null | undefined): string | null {
  if (!s) return null;
  return s === 'inventory_aggregator' ? 'inventory' : s;
}

/** Stage ids that must be `completed` before `stageId` may become running. */
export function predecessorIdsOf(stageId: string): string[] {
  const idx = STAGE_ORDER.indexOf(stageId);
  if (idx <= 0) return [];
  return STAGE_ORDER.slice(0, idx);
}

/** A terminal stage can never change (completed/failed are final). */
export function isTerminal(status: StageStatus): boolean {
  return status === 'completed' || status === 'failed';
}

/**
 * True if every predecessor of `stageId` is confirmed completed, using the
 * authoritative backend `completed` set first, then falling back to existing
 * store stage evidence. This is the predecessor guarantee (INVARIANT 2).
 */
export function predecessorsCompleted(
  stageId: string,
  completed: Set<string>,
  stages: InvariantStageLike[],
): boolean {
  for (const pred of predecessorIdsOf(stageId)) {
    if (completed.has(pred)) continue;
    const s = stages.find((x) => x.id === pred);
    if (!s || s.status !== 'completed') return false;
  }
  return true;
}

/**
 * Whether `stageId` is allowed to transition into `running` right now, given
 * the current store evidence. Terminal and predecessor-blocked stages are
 * rejected (INVARIANTS 2, 3, 4).
 */
export function canStartStage(
  stageId: string,
  stages: InvariantStageLike[],
  completed?: Set<string>,
): boolean {
  const cur = stages.find((x) => x.id === stageId);
  if (!cur) return false;
  if (isTerminal(cur.status)) return false;
  return predecessorsCompleted(stageId, completed ?? new Set(), stages);
}

/**
 * Enforce INVARIANT 1: force at most one `running` stage.
 *
 * Any stage currently `running` other than `keepRunningId` is reconciled to
 * its authoritative state:
 *   - if the backend `completed` set confirms it, → `completed`;
 *   - otherwise → `pending` (a deliberate correction of a stale/erroneous
 *     dual-running state; the normal monotonic path never does this).
 *
 * `keepRunningId = null` leaves the array unchanged (no authoritative active
 * stage known).
 */
export function demoteToSingleActive<T extends InvariantStageLike>(
  stages: T[],
  keepRunningId: string | null,
  completed?: Set<string>,
): T[] {
  if (!keepRunningId) return stages;
  return stages.map((s) => {
    if (s.status !== 'running' || s.id === keepRunningId) return s;
    if (completed && completed.has(s.id)) {
      return { ...s, status: 'completed' as const, completedAt: s.completedAt || new Date().toISOString() } as T;
    }
    return { ...s, status: 'pending' as const, startedAt: undefined } as T;
  });
}

/**
 * Resolve the single authoritative active stage from a backend snapshot.
 *
 * Priority (per the audit):
 *   1. snapshot.current_stage
 *   2. snapshot.next_stage
 *   3. completed_stages + STAGE_ORDER (first non-completed, non-terminal stage
 *      whose predecessors are confirmed completed)
 *
 * Never returns a stage that the backend has not yet made reachable, so it
 * cannot skip ahead to a future stage (e.g. code_generation while human_review
 * is still waiting_for_user).
 */
export function resolveActiveStage(input: {
  status: string;
  currentStage: string | null;
  nextStage: string | null;
  completed: Set<string>;
  stages: InvariantStageLike[];
}): string | null {
  const { status, currentStage, nextStage, completed, stages } = input;
  if (status !== 'running') return null;

  const usable = (id: string | null): id is string => {
    if (!id) return false;
    if (completed.has(id)) return false;
    const s = stages.find((x) => x.id === id);
    if (!s || isTerminal(s.status)) return false;
    return true;
  };

  if (usable(currentStage)) return currentStage;
  if (usable(nextStage)) return nextStage;

  for (const id of STAGE_ORDER) {
    if (completed.has(id)) continue;
    const s = stages.find((x) => x.id === id);
    if (!s || isTerminal(s.status)) continue;
    if (predecessorsCompleted(id, completed, stages)) return id;
  }
  return null;
}

/**
 * Promote `active` to `running` only if it is allowed: not terminal, not the
 * waiting_for_user gate, and all predecessors confirmed completed.
 * Used by the reconciliation path — it never fabricates a start.
 */
function promoteIfRunnable<T extends InvariantStageLike>(
  stages: T[],
  active: string,
  completed: Set<string>,
): T[] {
  const cur = stages.find((s) => s.id === active);
  if (!cur) return stages;
  if (isTerminal(cur.status)) return stages; // INVARIANT 3/4
  if (cur.status === 'waiting_for_user') return stages; // INVARIANT 5
  if (!predecessorsCompleted(active, completed, stages)) return stages; // INVARIANT 2
  if (cur.status !== 'running') {
    return stages.map((s) =>
      s.id === active
        ? { ...s, status: 'running' as const, startedAt: s.startedAt || new Date().toISOString() }
        : s,
    ) as T[];
  }
  return stages;
}

/**
 * Apply the full single-active invariant from a backend snapshot, while never
 * regressing a stage the live SSE stream already advanced (SSE is the primary
 * real-time source; REST is only the recovery source).
 *
 * Rules:
 *   - status must be "running" and an authoritative active stage must resolve.
 *   - If the snapshot's active stage is *ahead of* (or equal to, and actually
 *     running) every currently-running stage, the stale running stage(s) are
 *     reconciled (to completed when the backend confirms, else pending) and the
 *     authoritative active stage is promoted if runnable. This is what corrects
 *     the original dual-`running` bug (INVARIANT 1).
 *   - If the snapshot's active stage is *behind* the store's running stage, the
 *     snapshot is stale — nothing is demoted or regressed (requirement: REST
 *     reconciliation must never move state backward).
 */
export function ensureSingleActiveStage<T extends InvariantStageLike>(
  stages: T[],
  activeStageId: string | null,
  completed: Set<string>,
  status: string,
): T[] {
  if (status !== 'running' || !activeStageId) return stages;

  const activeIdx = STAGE_ORDER.indexOf(activeStageId);
  const runningIds = stages.filter((s) => s.status === 'running').map((s) => s.id);

  if (runningIds.length === 0) {
    return promoteIfRunnable(stages, activeStageId, completed);
  }

  const maxRunningIdx = Math.max(
    ...runningIds.map((id) => STAGE_ORDER.indexOf(id)).filter((i) => i >= 0),
    -1,
  );

  // Snapshot is stale (behind the store): do not demote/regress live state.
  if (activeIdx <= maxRunningIdx && !runningIds.includes(activeStageId)) {
    return stages;
  }

  // Snapshot is authoritative/ahead (or the active stage is the current runner):
  // demote any other running stage and promote the active one if runnable.
  let out = demoteToSingleActive(stages, activeStageId, completed);
  return promoteIfRunnable(out, activeStageId, completed);
}
