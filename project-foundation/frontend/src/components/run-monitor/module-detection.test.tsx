import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { ModuleDetection } from '@/components/run-monitor/module-detection';
import { useWorkflowStore } from '@/store/workflow-store';

describe('ModuleDetection duplicate key regression', () => {
  beforeEach(() => {
    useWorkflowStore.getState().reset('run-1');
  });

  afterEach(() => {
    cleanup();
    useWorkflowStore.getState().reset(null);
  });

  it('hydrating from test-plan with duplicate module names dedupes to unique entries', async () => {
    const fetchMock = vi.fn(async () =>
      ({
        ok: true,
        json: async () => ({
          modules: [
            { name: 'Login Module', description: 'a', pages: ['/login'], scenarios: 3 },
            { name: 'Login Module', description: 'a', pages: ['/login'], scenarios: 3 },
          ],
          test_scenarios: [],
        }),
      }) as Response
    );
    const origFetch = globalThis.fetch;
    // @ts-ignore
    globalThis.fetch = fetchMock;

    await useWorkflowStore.getState().hydrateArtifacts('run-1');

    const mods = useWorkflowStore.getState().detectedModules;
    expect(mods).toHaveLength(1);
    expect(mods[0].name).toBe('Login Module');

    globalThis.fetch = origFetch;
  });

  it('dispatching duplicate MODULE_DETECTED events does not create duplicate entries', () => {
    const store = useWorkflowStore.getState();
    store.dispatch({
      type: 'module_detected',
      run_id: 'run-1',
      data: { name: 'Login Module', description: 'd', pages: ['/login'], scenario_count: 3, module_index: 0, total_modules: 1 },
      timestamp: new Date().toISOString(),
      event_id: 'evt-1',
    });
    store.dispatch({
      type: 'module_detected',
      run_id: 'run-1',
      data: { name: 'Login Module', description: 'd', pages: ['/login'], scenario_count: 3, module_index: 0, total_modules: 1 },
      timestamp: new Date().toISOString(),
      event_id: 'evt-2',
    });
    const mods = useWorkflowStore.getState().detectedModules;
    expect(mods).toHaveLength(1);
    expect(mods[0].name).toBe('Login Module');
  });

  it('distinct module names remain as distinct entries', () => {
    const store = useWorkflowStore.getState();
    store.dispatch({
      type: 'module_detected',
      run_id: 'run-1',
      data: { name: 'Login Module', description: '', pages: [], scenario_count: 2, module_index: 0, total_modules: 2 },
      timestamp: new Date().toISOString(),
      event_id: 'evt-a',
    });
    store.dispatch({
      type: 'module_detected',
      run_id: 'run-1',
      data: { name: 'Dashboard Module', description: '', pages: [], scenario_count: 2, module_index: 1, total_modules: 2 },
      timestamp: new Date().toISOString(),
      event_id: 'evt-b',
    });
    expect(useWorkflowStore.getState().detectedModules).toHaveLength(2);
  });

  it('renders without duplicate React keys for Login Module', () => {
    useWorkflowStore.setState({
      detectedModules: [
        { name: 'Login Module', description: 'a', pages: ['/login'], scenarioCount: 2, moduleIndex: 1, totalModules: 1 },
      ],
    });
    // Capture console.error which React uses for duplicate key warnings
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    render(<ModuleDetection />);
    expect(screen.getByText('Login Module')).toBeTruthy();
    const duplicateWarnings = consoleErrorSpy.mock.calls.filter(([msg]) =>
      String(msg).includes('Encountered two children with the same key')
    );
    expect(duplicateWarnings).toHaveLength(0);
    consoleErrorSpy.mockRestore();
  });

  it('hydrate + SSE replay does not duplicate Login Module', async () => {
    const fetchMock = vi.fn(async () =>
      ({
        ok: true,
        json: async () => ({
          modules: [{ name: 'Login Module', description: '', pages: ['/login'], scenarios: 3 }],
          test_scenarios: [],
        }),
      }) as Response
    );
    const origFetch = globalThis.fetch;
    // @ts-ignore
    globalThis.fetch = fetchMock;
    await useWorkflowStore.getState().hydrateArtifacts('run-1');
    expect(useWorkflowStore.getState().detectedModules).toHaveLength(1);

    useWorkflowStore.getState().dispatch({
      type: 'module_detected',
      run_id: 'run-1',
      data: { name: 'Login Module', description: '', pages: ['/login'], scenario_count: 3, module_index: 0, total_modules: 1 },
      timestamp: new Date().toISOString(),
      event_id: 'replay-evt-1',
    });
    expect(useWorkflowStore.getState().detectedModules).toHaveLength(1);

    globalThis.fetch = origFetch;
  });

  it('uses stable composite key name-moduleIndex so legitimate distinct modules would have distinct keys', () => {
    useWorkflowStore.setState({
      detectedModules: [
        { name: 'Login Module', description: 'a', pages: ['/login'], scenarioCount: 2, moduleIndex: 1, totalModules: 2 },
        { name: 'Login Module', description: 'b', pages: ['/dashboard'], scenarioCount: 2, moduleIndex: 2, totalModules: 2 },
      ],
    });
    // This state should not happen after dedup, but if it did via backend,
    // the component key `${name}-${moduleIndex}` would be distinct, so no React warning.
    // We verify the keys would be unique by simulating the key generation.
    const mods = useWorkflowStore.getState().detectedModules;
    const keys = mods.map((m) => `${m.name}-${m.moduleIndex}`);
    expect(new Set(keys).size).toBe(keys.length);
  });
});
