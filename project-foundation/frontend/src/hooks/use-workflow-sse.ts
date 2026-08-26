/**
 * useWorkflowSSE — React hook for consuming the SSE workflow event stream.
 *
 * Connects to /api/v1/runs/{runId}/events and dispatches every event into
 * the Zustand workflow store. Handles reconnection with exponential backoff.
 *
 * REST APIs are NOT used for live state here — only SSE events.
 */

import { useEffect, useRef, useCallback } from 'react';
import { useWorkflowStore, WorkflowEvent } from '@/store/workflow-store';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
// Backoff is open-ended: the backend replays on every re-subscribe and REST
// reconciliation is a second recovery path, so we keep retrying rather than
// permanently giving up on a transient disconnect.
const MAX_RETRIES = 10;
const BASE_DELAY_MS = 1000;
const MAX_DELAY_MS = 30_000;

interface UseWorkflowSSEOptions {
  /** Called when the SSE connection is first established. */
  onConnect?: () => void;
  /** Called when the SSE connection permanently fails (all retries exhausted). */
  onPermanentError?: (error: string) => void;
}

export function useWorkflowSSE(
  runId: string | null | undefined,
  options: UseWorkflowSSEOptions = {}
) {
  const dispatch       = useWorkflowStore((s) => s.dispatch);
  const reset          = useWorkflowStore((s) => s.reset);
  const setSSEConnected= useWorkflowStore((s) => s.setSSEConnected);
  const setSSEError    = useWorkflowStore((s) => s.setSSEError);

  const esRef          = useRef<EventSource | null>(null);
  const retryCountRef  = useRef(0);
  const retryTimerRef  = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef     = useRef(true);

  const connect = useCallback(() => {
    if (!runId || !mountedRef.current) return;

    // Safely tear down any existing EventSource before opening a new one so we
    // never hold two live streams for the same run.
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
    if (retryTimerRef.current) {
      clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }

    // Reset store when first connecting ONLY if switching to a different run
    if (retryCountRef.current === 0 && useWorkflowStore.getState().runId !== runId) {
      reset(runId);
    }

    const url = `${API_BASE}/api/v1/runs/${runId}/events`;

    const es = new EventSource(url);
    esRef.current = es;

    es.onopen = () => {
      if (!mountedRef.current || esRef.current !== es) return;
      retryCountRef.current = 0;
      setSSEConnected(true);
      setSSEError(null);
      options.onConnect?.();
    };

    // Generic message handler (backend sends named events; EventSource uses
    // the event: field to set the event type, so we listen on all event types)
    es.onmessage = (e: MessageEvent) => {
      if (!mountedRef.current || esRef.current !== es) return;
      try {
        const event: WorkflowEvent = JSON.parse(e.data);
        dispatch(event);
      } catch {
        // malformed message — ignore
      }
    };

    es.onerror = () => {
      if (!mountedRef.current) return;
      const isCurrent = esRef.current === es;
      // The stream ended — the browser fires onerror either because the run
      // finished (drain sentinel → backend closes the stream) or because of a
      // transient network/proxy failure.
      const store = useWorkflowStore.getState();
      const runEnded = store.runId === runId &&
        (store.overallStatus === 'completed' || store.overallStatus === 'failed');

      es.close();
      if (isCurrent) {
        esRef.current = null;
        setSSEConnected(false);
      }

      // If the workflow already reached a terminal state, the stream ended
      // normally — nothing to recover, so do not spin reconnections.
      if (runEnded) return;

      // Otherwise reconnect with exponential backoff. We never permanently
      // give up: the backend replays missed events on re-subscribe, and REST
      // reconciliation is an independent catch-up path.
      const retryCount = retryCountRef.current;
      const delay = Math.min(BASE_DELAY_MS * Math.pow(1.5, retryCount), MAX_DELAY_MS);
      retryCountRef.current += 1;
      if (retryCount >= MAX_RETRIES) {
        setSSEError('SSE reconnecting…');
      }
      retryTimerRef.current = setTimeout(() => {
        if (mountedRef.current) connect();
      }, delay);
    };

    // Bind all known event types (named events from backend)
    // The backend sends `event: <type_name>` so EventSource routes by name
    const knownTypes = [
      'workflow_started', 'workflow_completed', 'workflow_failed', 'workflow_paused',
      'stage_started', 'stage_completed', 'stage_failed', 'stage_skipped',
      'workspace_created', 'run_metadata_saved',
      'crawler_started', 'browser_launching', 'browser_initialized', 'browser_context_created',
      'page_navigation_started', 'dom_content_loaded', 'page_loaded', 'html_extracted',
      'forms_detected', 'buttons_detected', 'inputs_detected', 'links_extracted',
      'page_visited', 'queue_updated', 'page_completed', 'screenshot_captured', 'crawl_completed',
      'browser_action', 'browser_frame',
      'auth_started', 'auth_url_discovered', 'auth_form_detected', 'auth_submitted',
      'auth_redirect_started', 'auth_redirect_completed', 'oauth_detected', 'mfa_required',
      'auth_verification_started', 'authenticated', 'authentication_failed',
      'authentication_timeout', 'authentication_unknown', 'auth_strategy_unsupported',
      'auth_url_not_found',
      'inventory_started', 'inventory_generated',
      'llm_call_started', 'llm_call_completed', 'test_plan_generated',
      'ai_reasoning_step', 'module_detected', 'scenario_generated', 'confidence_update', 'analysis_progress',
      'human_review_required', 'human_review_approved', 'human_review_rejected',
      'ir_generation_started', 'ir_generated',
      'code_generation_started', 'code_generation_completed', 'code_generation_failed',
      'file_started', 'file_progress', 'file_completed', 'file_generated', 'playwright_generated',
      'current_activity_update', 'generation_progress_update',
      'execution_started', 'test_started', 'test_passed', 'test_failed', 'test_skipped', 'execution_completed',
      'report_generation_started', 'report_generation_completed', 'report_generation_failed', 'report_available',
      'ping',
    ];

    const handleNamedEvent = (e: Event) => {
      if (!mountedRef.current || esRef.current !== es) return;
      const msgEvent = e as MessageEvent;
      try {
        const event: WorkflowEvent = JSON.parse(msgEvent.data);
        dispatch(event);
      } catch {
        // ignore
      }
    };

    knownTypes.forEach((type) => {
      es.addEventListener(type, handleNamedEvent);
    });

  }, [runId, dispatch, reset, setSSEConnected, setSSEError, options.onConnect, options.onPermanentError]);

  useEffect(() => {
    mountedRef.current = true;
    retryCountRef.current = 0;

    if (runId) {
      connect();
    }

    return () => {
      mountedRef.current = false;
      if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
      if (esRef.current) {
        esRef.current.close();
        esRef.current = null;
      }
      setSSEConnected(false);
    };
  }, [runId]); // eslint-disable-line react-hooks/exhaustive-deps

  const sseConnected = useWorkflowStore((s) => s.sseConnected);
  const sseError     = useWorkflowStore((s) => s.sseError);

  return { connected: sseConnected, error: sseError };
}
