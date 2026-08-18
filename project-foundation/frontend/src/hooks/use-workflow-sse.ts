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
const MAX_RETRIES = 10;
const BASE_DELAY_MS = 1000;

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

    // Reset store when first connecting ONLY if switching to a different run
    if (retryCountRef.current === 0 && useWorkflowStore.getState().runId !== runId) {
      reset(runId);
    }

    const url = `${API_BASE}/api/v1/runs/${runId}/events`;

    const es = new EventSource(url);
    esRef.current = es;

    es.onopen = () => {
      if (!mountedRef.current) return;
      retryCountRef.current = 0;
      setSSEConnected(true);
      setSSEError(null);
      options.onConnect?.();
    };

    // Generic message handler (backend sends named events; EventSource uses
    // the event: field to set the event type, so we listen on all event types)
    es.onmessage = (e: MessageEvent) => {
      if (!mountedRef.current) return;
      try {
        const event: WorkflowEvent = JSON.parse(e.data);
        dispatch(event);
      } catch {
        // malformed message — ignore
      }
    };

    // Named event listener — backend sends `event: <type>\ndata: {...}`
    // EventSource doesn't fire onmessage for named events, so we need to
    // add a generic listener that catches everything via addEventListener.
    // We use a single "catch-all" approach by listening on the raw message.
    //
    // Because EventSource only routes *unnamed* messages to onmessage,
    // we also bind individual named event listeners for the event types
    // we know about. Alternatively, we can use a proxy server or use
    // an approach where the backend sends all events as unnamed (no event: field).
    //
    // For simplicity, we override with a MessageChannel approach:

    es.onerror = () => {
      if (!mountedRef.current) return;
      es.close();
      setSSEConnected(false);

      const retryCount = retryCountRef.current;
      if (retryCount >= MAX_RETRIES) {
        const msg = `SSE connection failed after ${MAX_RETRIES} retries`;
        setSSEError(msg);
        options.onPermanentError?.(msg);
        return;
      }

      const delay = Math.min(BASE_DELAY_MS * Math.pow(1.5, retryCount), 30_000);
      retryCountRef.current += 1;

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
      'code_generation_started', 'file_generated', 'playwright_generated',
      'execution_started', 'test_started', 'test_passed', 'test_failed', 'test_skipped', 'execution_completed',
      'ping',
    ];

    const handleNamedEvent = (e: Event) => {
      if (!mountedRef.current) return;
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
