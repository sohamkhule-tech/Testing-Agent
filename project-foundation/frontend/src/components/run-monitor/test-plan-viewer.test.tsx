import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { HumanReviewPanel } from '@/components/run-monitor/test-plan-viewer';
import { useWorkflowStore } from '@/store/workflow-store';

const toastMock = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
}));
vi.mock('sonner', () => ({ toast: toastMock }));

const fetchMock = vi.hoisted(() => vi.fn());
vi.stubGlobal('fetch', fetchMock);

const SCENARIOS = [
  { id: 'TC-001', title: 'Positive Login', description: 'd', module: 'Login Module', priority: 'high', category: 'functional', riskLevel: 'medium', targetPage: 'qa', scenarioIndex: 0, totalScenarios: 3 },
  { id: 'TC-002', title: 'Invalid Password', description: 'd', module: 'Login Module', priority: 'high', category: 'negative', riskLevel: 'high', targetPage: 'qa', scenarioIndex: 1, totalScenarios: 3 },
  { id: 'TC-003', title: 'Boundary Length', description: 'd', module: 'Login Module', priority: 'low', category: 'boundary', riskLevel: 'low', targetPage: 'qa', scenarioIndex: 2, totalScenarios: 3 },
];

function seedStore() {
  useWorkflowStore.setState({
    runId: 'run-1',
    humanReviewRequired: true,
    testPlanGenerated: true,
    testPlanScenarioCount: 3,
    overallStatus: 'paused',
    detectedModules: [{ name: 'Login Module', description: '', pages: [], scenarioCount: 3, moduleIndex: 0, totalModules: 1 }],
    generatedScenarios: SCENARIOS,
    stages: useWorkflowStore.getState().stages.map((s) =>
      s.id === 'human_review' ? { ...s, status: 'waiting_for_user' as const } : s
    ),
  });
}

function checkboxIndexes(): { header: HTMLInputElement; rows: HTMLInputElement[] } {
  const all = screen.getAllByRole('checkbox') as HTMLInputElement[];
  return { header: all[0], rows: all.slice(1) };
}

describe('HumanReviewPanel selective approval', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    fetchMock.mockResolvedValue({
      ok: true,
      status: 202,
      json: async () => ({ approved_test_case_ids: [], status: 'running' }),
    } as Response);
    seedStore();
  });

  afterEach(() => {
    cleanup();
    useWorkflowStore.getState().reset(null);
  });

  it('renders one checkbox per test-case row', () => {
    render(<HumanReviewPanel runId="run-1" />);
    const { header, rows } = checkboxIndexes();
    expect(header).toBeTruthy();
    expect(rows).toHaveLength(3);
  });

  it('approve button is disabled when nothing is selected', () => {
    render(<HumanReviewPanel runId="run-1" />);
    const btn = screen.getByRole('button', { name: /Approve Selected/ });
    expect((btn as HTMLButtonElement).disabled).toBe(true);
  });

  it('selecting a single test case enables Approve Selected (1)', () => {
    render(<HumanReviewPanel runId="run-1" />);
    const { rows } = checkboxIndexes();
    fireEvent.click(rows[0]);
    const btn = screen.getByRole('button', { name: 'Approve Selected (1)' });
    expect((btn as HTMLButtonElement).disabled).toBe(false);
    expect(toastMock.error).not.toHaveBeenCalled();
  });

  it('selecting multiple test cases shows the count', () => {
    render(<HumanReviewPanel runId="run-1" />);
    const { rows } = checkboxIndexes();
    fireEvent.click(rows[0]);
    fireEvent.click(rows[1]);
    expect(screen.getByRole('button', { name: 'Approve Selected (2)' })).toBeTruthy();
  });

  it('Select All selects every visible test case; unchecking clears them', () => {
    render(<HumanReviewPanel runId="run-1" />);
    const { header, rows } = checkboxIndexes();
    fireEvent.click(header);
    expect((header as HTMLInputElement).checked).toBe(true);
    expect(rows.every((r) => r.checked)).toBe(true);
    expect(screen.getByRole('button', { name: 'Approve Selected (3)' })).toBeTruthy();

    fireEvent.click(header);
    expect(rows.every((r) => !r.checked)).toBe(true);
    expect(screen.getByRole('button', { name: 'Approve Selected' })).toBeTruthy();
  });

  it('header checkbox is indeterminate when only some are selected', () => {
    render(<HumanReviewPanel runId="run-1" />);
    const { header, rows } = checkboxIndexes();
    fireEvent.click(rows[0]);
    expect(header.indeterminate).toBe(true);
    expect(header.checked).toBe(false);
  });

  it('Approve Selected sends ONLY the selected test-case IDs to the backend', async () => {
    render(<HumanReviewPanel runId="run-1" />);
    const { rows } = checkboxIndexes();
    fireEvent.click(rows[0]); // TC-001
    fireEvent.click(rows[2]); // TC-003

    fireEvent.click(screen.getByRole('button', { name: 'Approve Selected (2)' }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain('/api/v1/runs/run-1/approve');
    const body = JSON.parse(String(init.body));
    expect(new Set(body.test_case_ids)).toEqual(new Set(['TC-001', 'TC-003']));
    expect(body.test_case_ids).toHaveLength(2);
  });

  it('supports approving a single selected ID', async () => {
    render(<HumanReviewPanel runId="run-1" />);
    const { rows } = checkboxIndexes();
    fireEvent.click(rows[0]);
    fireEvent.click(screen.getByRole('button', { name: 'Approve Selected (1)' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const body = JSON.parse(String(fetchMock.mock.calls[0][1].body));
    expect(body.test_case_ids).toEqual(['TC-001']);
  });

  it('shows approved count after a partial approval (2 of 3)', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      status: 202,
      json: async () => ({ approved_test_case_ids: ['TC-001', 'TC-002'], status: 'running' }),
    } as Response);
    render(<HumanReviewPanel runId="run-1" />);
    const { rows } = checkboxIndexes();
    fireEvent.click(rows[0]);
    fireEvent.click(rows[1]);
    fireEvent.click(screen.getByRole('button', { name: 'Approve Selected (2)' }));

    await waitFor(() =>
      expect(screen.getAllByText(/2 of 3 scenarios approved/i).length).toBeGreaterThan(0)
    );
    expect(toastMock.success).toHaveBeenCalledWith('Approved 2 test cases');
  });

  it('preserves the selection and shows an error when approval fails', async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ detail: 'Test-case IDs do not belong to this run' }),
    } as Response);
    render(<HumanReviewPanel runId="run-1" />);
    const { rows } = checkboxIndexes();
    fireEvent.click(rows[0]);

    fireEvent.click(screen.getByRole('button', { name: 'Approve Selected (1)' }));

    await waitFor(() =>
      expect(toastMock.error).toHaveBeenCalledWith('Test-case IDs do not belong to this run')
    );
    // Selection preserved, still awaiting review (no decision banner).
    expect(screen.getByRole('button', { name: 'Approve Selected (1)' })).toBeTruthy();
    expect(rows[0].checked).toBe(true);
  });

  it('keeps previously selected IDs when a filter hides-away rows and Select All only affects visible set', () => {
    render(<HumanReviewPanel runId="run-1" />);
    const { rows } = checkboxIndexes();
    fireEvent.click(rows[0]); // TC-001 selected

    // Filter to priority 'low' → only TC-003 visible; selection of TC-001 persists.
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'low' } });
    const visible = screen.getAllByRole('checkbox');
    expect(visible).toHaveLength(2); // header + TC-003
    expect((visible[1] as HTMLInputElement).checked).toBe(false);

    // Select All applies to the VISIBLE set only.
    fireEvent.click(visible[0]);
    expect((visible[1] as HTMLInputElement).checked).toBe(true);
    // TC-001 remains selected (hidden rows are preserved).
    expect(screen.getByRole('button', { name: 'Approve Selected (2)' })).toBeTruthy();
  });
});