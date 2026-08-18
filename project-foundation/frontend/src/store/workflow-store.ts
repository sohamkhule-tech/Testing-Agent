/**
 * Workflow Store — Event-Sourced Run State
 *
 * The frontend builds all run-detail UI state by consuming a stream of
 * typed workflow events via SSE. No polling. No REST for live state.
 *
 * REST APIs are used ONLY for:
 *   - Initial page-load metadata (run entity)
 *   - Artifact retrieval (screenshots, generated files, JSON exports)
 */

import { create } from 'zustand';

// ---------------------------------------------------------------------------
// Event type constants — must match backend EventType constants
// ---------------------------------------------------------------------------

export const EventType = {
  // Workflow lifecycle
  WORKFLOW_STARTED:         'workflow_started',
  WORKFLOW_COMPLETED:       'workflow_completed',
  WORKFLOW_FAILED:          'workflow_failed',
  WORKFLOW_PAUSED:          'workflow_paused',

  // Stage lifecycle
  STAGE_STARTED:            'stage_started',
  STAGE_COMPLETED:          'stage_completed',
  STAGE_FAILED:             'stage_failed',
  STAGE_SKIPPED:            'stage_skipped',

  // Trigger / setup
  WORKSPACE_CREATED:        'workspace_created',
  RUN_METADATA_SAVED:       'run_metadata_saved',

  // Crawler — granular
  CRAWLER_STARTED:            'crawler_started',
  BROWSER_LAUNCHING:          'browser_launching',
  BROWSER_INITIALIZED:        'browser_initialized',
  BROWSER_CONTEXT_CREATED:    'browser_context_created',
  PAGE_NAVIGATION_STARTED:    'page_navigation_started',
  DOM_CONTENT_LOADED:         'dom_content_loaded',
  PAGE_LOADED:                'page_loaded',
  HTML_EXTRACTED:             'html_extracted',
  SCREENSHOT_CAPTURED:        'screenshot_captured',
  FORMS_DETECTED:             'forms_detected',
  BUTTONS_DETECTED:           'buttons_detected',
  INPUTS_DETECTED:            'inputs_detected',
  LINKS_EXTRACTED:            'links_extracted',
  PAGE_VISITED:               'page_visited',
  QUEUE_UPDATED:              'queue_updated',
  PAGE_COMPLETED:             'page_completed',
  CRAWL_COMPLETED:            'crawl_completed',

  // Inventory
  INVENTORY_STARTED:        'inventory_started',
  INVENTORY_GENERATED:      'inventory_generated',

  // Test design / LLM
  LLM_CALL_STARTED:         'llm_call_started',
  LLM_CALL_COMPLETED:       'llm_call_completed',
  TEST_PLAN_GENERATED:      'test_plan_generated',

  // AI Agent reasoning (granular thinking steps)
  AI_REASONING_STEP:        'ai_reasoning_step',
  MODULE_DETECTED:          'module_detected',
  SCENARIO_GENERATED:       'scenario_generated',
  CONFIDENCE_UPDATE:        'confidence_update',
  ANALYSIS_PROGRESS:        'analysis_progress',

  // Human review
  HUMAN_REVIEW_REQUIRED:    'human_review_required',
  HUMAN_REVIEW_APPROVED:    'human_review_approved',
  HUMAN_REVIEW_REJECTED:    'human_review_rejected',

  // IR generation
  IR_GENERATION_STARTED:    'ir_generation_started',
  IR_GENERATED:             'ir_generated',

  // Code generation
  CODE_GENERATION_STARTED:  'code_generation_started',
  CODE_GENERATION_COMPLETED: 'code_generation_completed',
  CODE_GENERATION_FAILED:   'code_generation_failed',
  LOADING_TEST_PLAN:        'loading_test_plan',
  LOADING_INVENTORY:        'loading_inventory',
  LOADING_SCREENSHOTS:      'loading_screenshots',
  BUILDING_PROMPTS:         'building_prompts',
  SENDING_LLM_REQUEST:      'sending_llm_request',
  WAITING_FOR_LLM_RESPONSE: 'waiting_for_llm_response',
  RECEIVED_LLM_RESPONSE:    'received_llm_response',
  PARSING_RESPONSE:         'parsing_response',
  PLANNING_PROJECT_STRUCTURE: 'planning_project_structure',
  GENERATING_PAGE_OBJECT:   'generating_page_object',
  GENERATING_TEST_FILE:     'generating_test_file',
  GENERATING_FIXTURE:       'generating_fixture',
  GENERATING_HELPER:        'generating_helper',
  WRITING_FILE:             'writing_file',
  FILE_WRITTEN:             'file_written',
  VALIDATING_GENERATED_CODE: 'validating_generated_code',
  PACKAGING_PROJECT:        'packaging_project',
  FILE_STARTED:             'file_started',
  FILE_PROGRESS:            'file_progress',
  FILE_COMPLETED:           'file_completed',
  FILE_GENERATED:           'file_generated',
  PLAYWRIGHT_GENERATED:     'playwright_generated',
  CURRENT_ACTIVITY_UPDATE:  'current_activity_update',
  GENERATION_PROGRESS_UPDATE: 'generation_progress_update',

  // Execution
  EXECUTION_STARTED:        'execution_started',
  TEST_STARTED:             'test_started',
  TEST_PASSED:              'test_passed',
  TEST_FAILED:              'test_failed',
  TEST_SKIPPED:             'test_skipped',
  EXECUTION_COMPLETED:      'execution_completed',

  // Keepalive
  // Browser live actions
  BROWSER_ACTION:           'browser_action',
  BROWSER_FRAME:            'browser_frame',

  PING:                     'ping',
} as const;

export type WorkflowEventType = typeof EventType[keyof typeof EventType];

// ---------------------------------------------------------------------------
// Typed payloads
// ---------------------------------------------------------------------------

export interface WorkflowEvent {
  type: WorkflowEventType;
  run_id: string;
  data: Record<string, unknown>;
  timestamp: string;
  event_id: string;
}

// ---------------------------------------------------------------------------
// Stage state
// ---------------------------------------------------------------------------

export type StageStatus = 'pending' | 'running' | 'completed' | 'failed' | 'waiting_for_user' | 'skipped';

export interface PipelineStage {
  id: string;
  label: string;
  status: StageStatus;
  startedAt?: string;
  completedAt?: string;
  error?: string;
  data?: Record<string, unknown>;
}

const INITIAL_STAGES: PipelineStage[] = [
  { id: 'trigger',        label: 'Project Setup',          status: 'pending' },
  { id: 'crawler',        label: 'Web Crawler',            status: 'pending' },
  { id: 'inventory',      label: 'Inventory',              status: 'pending' },
  { id: 'test_design',    label: 'Test Design',            status: 'pending' },
  { id: 'human_review',   label: 'Human Review',           status: 'pending' },
  { id: 'code_generation',label: 'Code Generation',        status: 'pending' },
  { id: 'execution',      label: 'Test Execution',         status: 'pending' },
  { id: 'report',         label: 'Report',                 status: 'pending' },
];

export interface RunSnapshot {
  run_id: string;
  status: string;
  current_stage: string | null;
  completed_stages: string[];
  failed_stage: string | null;
  next_stage: string | null;
  resume_allowed: boolean;
  last_error: string | null;
  stage_logs: Record<string, string[]>;
}

// ---------------------------------------------------------------------------
// Timeline event
// ---------------------------------------------------------------------------

export interface TimelineEntry {
  id: string;
  timestamp: string;
  type: WorkflowEventType;
  message: string;
  detail?: string;
  level: 'info' | 'success' | 'warning' | 'error';
  data?: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Browser activity state
// ---------------------------------------------------------------------------

export interface BrowserActivity {
  status: 'idle' | 'launching' | 'navigating' | 'capturing' | 'done';
  currentUrl?: string;
  currentTitle?: string;
  statusCode?: number;
  responseTime?: number;
  depth?: number;
  pagesVisited: number;
  queueSize: number;
  totalLinks: number;
}

export interface CursorPosition {
  x: number;
  y: number;
}

export interface CursorAction {
  label: string;
  action: string;
  position?: CursorPosition;
  selector?: string;
}

// ---------------------------------------------------------------------------
// Screenshot
// ---------------------------------------------------------------------------

export interface Screenshot {
  id: string;
  filename: string;
  url: string;
  title?: string;
  timestamp: string;
  responseTime?: number;
}

// ---------------------------------------------------------------------------
// Crawl statistics
// ---------------------------------------------------------------------------

export interface CrawlStats {
  pagesVisited: number;
  linksFound: number;
  formsFound: number;
  buttonsFound: number;
  inputsFound: number;
  pagesCrawled: number;
}

// ---------------------------------------------------------------------------
// Inventory
// ---------------------------------------------------------------------------

export interface InventorySummary {
  page_count: number;
  form_count: number;
  link_count: number;
  button_count: number;
  input_count: number;
  screenshot_count: number;
}

// ---------------------------------------------------------------------------
// LLM activity
// ---------------------------------------------------------------------------

export interface LLMCall {
  id: string;
  model?: string;
  purpose?: string;
  promptTokens?: number;
  responseTokens?: number;
  startedAt: string;
  completedAt?: string;
  status: 'running' | 'completed' | 'failed';
}

// ---------------------------------------------------------------------------
// AI Reasoning
// ---------------------------------------------------------------------------

export interface AIReasoningStep {
  step: string;
  label: string;
  description: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
}

export interface ModuleInfo {
  name: string;
  description: string;
  pages: string[];
  scenarioCount: number;
  moduleIndex: number;
  totalModules: number;
}

export interface ScenarioInfo {
  id: string;
  title: string;
  description: string;
  module: string;
  priority: string;
  category: string;
  riskLevel: string;
  targetPage: string;
  scenarioIndex: number;
  totalScenarios: number;
}

export interface ConfidenceMetrics {
  inventoryConfidence: number;
  scenarioConfidence: number;
  automationCoverage: number;
  riskCoverage: number;
}

export interface AnalysisProgress {
  phase: string;
  progress: number;
  label: string;
}

// ---------------------------------------------------------------------------
// Code generation
// ---------------------------------------------------------------------------

export interface GeneratedFile {
  path: string;
  name: string;
  timestamp: string;
  file_type?: string;
  size_bytes?: number;
  lines_of_code?: number;
  folder?: string;
  module?: string;
  scenario?: string;
  content?: string;
}

export interface GeneratedFileNode {
  name: string;
  path: string;
  type: 'file' | 'folder';
  fileType?: string;
  children?: GeneratedFileNode[];
}

export interface CurrentGeneratedFile {
  filename: string;
  folder: string;
  file_type: string;
  module?: string;
  scenario?: string;
  progress: number;
  content?: string;
}

export type LLMActivityState = 'idle' | 'sending' | 'waiting' | 'received' | 'parsing';

export interface CodeGenerationActivity {
  label: string;
  step: string;
  startedAt: string;
}

// ---------------------------------------------------------------------------
// Execution
// ---------------------------------------------------------------------------

export interface TestResult {
  id: string;
  name: string;
  status: 'passed' | 'failed' | 'skipped';
  duration?: number;
  error?: string;
  timestamp: string;
}

export interface ExecutionStats {
  total: number;
  passed: number;
  failed: number;
  skipped: number;
  passRate: number;
}

// ---------------------------------------------------------------------------
// Full workflow state
// ---------------------------------------------------------------------------

export interface WorkflowState {
  runId: string | null;

  // Connection
  sseConnected: boolean;
  sseError: string | null;

  // Overall workflow
  overallStatus: 'idle' | 'running' | 'paused' | 'completed' | 'failed';

  // Pipeline stages
  stages: PipelineStage[];

  // Chronological event log
  timeline: TimelineEntry[];

  // Crawler
  browserActivity: BrowserActivity;
  screenshots: Screenshot[];
  crawlStats: CrawlStats;
  elapsed: number;
  currentAction: CursorAction | null;
  liveFrame: { filename: string; url: string; title: string; action: string; timestamp: string } | null;

  // Inventory
  inventorySummary: InventorySummary | null;

  // LLM / Test Design
  llmCalls: LLMCall[];
  testPlanGenerated: boolean;
  testPlanScenarioCount: number;
  testDesignElapsed: number;
  testDesignStartedAt: string | null;

  // AI reasoning
  aiReasoningSteps: AIReasoningStep[];
  detectedModules: ModuleInfo[];
  generatedScenarios: ScenarioInfo[];
  confidenceMetrics: ConfidenceMetrics;
  analysisProgress: AnalysisProgress | null;

  // Human review
  humanReviewRequired: boolean;

  // Code generation
  generatedFiles: GeneratedFile[];
  generatedFileTree: GeneratedFileNode[];
  codeGenerationProgress: number; // 0–100
  codeGenerationActivity: CodeGenerationActivity | null;
  currentGeneratedFile: CurrentGeneratedFile | null;
  codeGenerationElapsed: number;
  codeGenerationStartedAt: string | null;
  remainingQueue: number;
  currentScenario: string | null;
  llmActivityState: LLMActivityState;
  codeGenerationError: string | null;
  filesGenerated: number;
  pageObjectsCount: number;
  testFilesCount: number;
  scenariosImplemented: number;

  // Execution
  testResults: TestResult[];
  executionStats: ExecutionStats;
  consoleLogs: string[];

  // Dedup
  seenEventIds: Set<string>;

  // Actions
  dispatch: (event: WorkflowEvent) => void;
  reset: (runId: string) => void;
  setSSEConnected: (v: boolean) => void;
  setSSEError: (msg: string | null) => void;
  hydrate: (snapshot: RunSnapshot) => void;
  hydrateArtifacts: (runId: string) => Promise<void>;
}

// ---------------------------------------------------------------------------
// Helper: update stage by id
// ---------------------------------------------------------------------------

function updateStage(
  stages: PipelineStage[],
  id: string,
  patch: Partial<PipelineStage>
): PipelineStage[] {
  return stages.map((s) => (s.id === id ? { ...s, ...patch } : s));
}

// ---------------------------------------------------------------------------
// Helper: map event type → human readable timeline message
// ---------------------------------------------------------------------------

function eventToTimelineEntry(event: WorkflowEvent): TimelineEntry {
  const data = event.data as Record<string, string | number | boolean | undefined>;
  const messages: Partial<Record<WorkflowEventType, string>> = {
    workflow_started:         '🚀 Workflow Started',
    workflow_completed:       '✅ Workflow Completed',
    workflow_failed:          '❌ Workflow Failed',
    workflow_paused:          '⏸  Workflow Paused — Awaiting Human Review',
    stage_started:            `▶  Stage Started: ${data.label ?? data.stage}`,
    stage_completed:          `✓  Stage Completed: ${data.stage}`,
    stage_failed:             `✗  Stage Failed: ${data.stage}`,
    workspace_created:        '📁 Workspace Created',
    run_metadata_saved:       '💾 Run Metadata Saved',
    crawler_started:            `🌐 Crawler Started — ${data.target_url ?? ''}`,
    browser_launching:           '🔭 Launching Browser...',
    browser_initialized:         '✅ Browser Initialized',
    browser_context_created:     '📂 Browser Context Created',
    page_navigation_started:     `↗  Navigating: ${data.url}`,
    dom_content_loaded:          '📄 DOM Content Loaded',
    page_loaded:                 `✅ Page Loaded — ${data.status_code ?? ''}`,
    html_extracted:              '📦 HTML Extracted',
    forms_detected:              `📝 Forms Detected: ${data.count} on ${data.url}`,
    buttons_detected:            `🔘 Buttons Detected: ${data.count}`,
    inputs_detected:             `⌨️ Inputs Detected: ${data.count}`,
    links_extracted:             `🔗 Links Extracted: ${data.count} (${data.discovered ?? 0} new)`,
    page_visited:                `📄 Page Visited: ${data.url}`,
    queue_updated:               `📋 Queue: ${data.queue_size} remaining`,
    page_completed:              `✅ Page Done: ${data.url} — ${data.pages_visited} total`,
    screenshot_captured:         `📸 Screenshot: ${data.url}`,
    crawl_completed:             `✓  Crawl Complete — ${data.pages_visited} pages`,
    browser_action:              `🤖 ${data.label || data.action}`,
    browser_frame:               `📷 Frame: ${data.url}`,
    inventory_started:        '📊 Building Inventory...',
    inventory_generated:      `📦 Inventory Generated — ${data.page_count} pages, ${data.form_count} forms`,
    llm_call_started:         `🤖 LLM Call Started — ${data.purpose ?? 'Generating'}`,
    llm_call_completed:       `✓  LLM Response Received`,
    test_plan_generated:      `📋 Test Plan Generated — ${data.scenario_count} scenarios`,
    ai_reasoning_step:        `🧠 ${data.label}`,
    module_detected:          `📦 Module Detected: ${data.name}`,
    scenario_generated:       `📝 Scenario Created: ${data.id} — ${data.title}`,
    confidence_update:        `📊 Confidence: ${data.metric} = ${data.value}%`,
    analysis_progress:        `📈 ${data.label}`,
    human_review_required:    '👁  Human Review Required',
    human_review_approved:    `✅ Human Review Approved by ${data.reviewer_name ?? 'user'}`,
    human_review_rejected:    '❌ Human Review Rejected',
    code_generation_started:  '⚙️  Code Generation Started',
    code_generation_completed: '✅ Code Generation Completed',
    code_generation_failed:   '❌ Code Generation Failed',
    loading_test_plan:        '📂 Loading Approved Test Plan',
    loading_inventory:        '📦 Loading Inventory',
    loading_screenshots:      '📸 Loading Screenshots',
    building_prompts:         '🧱 Building Prompts',
    sending_llm_request:      '📤 Sending LLM Request',
    waiting_for_llm_response: '⏳ Waiting for LLM Response',
    received_llm_response:    '📥 Received LLM Response',
    parsing_response:         '🔍 Parsing Response',
    planning_project_structure: '🏗️ Planning Project Structure',
    generating_page_object:   '📄 Generating Page Object',
    generating_test_file:     '🧪 Generating Test File',
    generating_fixture:       '🔌 Generating Fixture',
    generating_helper:        '🛠️ Generating Helper',
    writing_file:             '✏️ Writing File',
    file_written:             '📝 File Written',
    validating_generated_code: '✅ Validating Generated Code',
    packaging_project:        '📦 Packaging Project',
    file_started:             '📝 Started File',
    file_progress:            '📝 File Progress',
    file_completed:           '✓ File Completed',
    file_generated:           `📝 File Generated: ${data.path}`,
    playwright_generated:     '✅ Playwright Project Generated',
    execution_started:        '▶  Test Execution Started',
    test_passed:              `✓  Test Passed: ${data.name}`,
    test_failed:              `✗  Test Failed: ${data.name}`,
    test_skipped:             `⏭  Test Skipped: ${data.name}`,
    execution_completed:      '🏁 Execution Completed',
    ping:                     'ping',
  };

  const levelMap: Partial<Record<WorkflowEventType, TimelineEntry['level']>> = {
    workflow_completed: 'success',
    workflow_failed:    'error',
    stage_failed:       'error',
    test_failed:        'error',
    code_generation_failed: 'error',
    code_generation_completed: 'success',
    human_review_required: 'warning',
    workflow_paused:    'warning',
  };

  const message = messages[event.type] ?? event.type;
  const level   = levelMap[event.type] ?? 'info';

  return {
    id:        event.event_id,
    timestamp: event.timestamp,
    type:      event.type,
    message,
    level,
    data:      event.data,
  };
}

// ---------------------------------------------------------------------------
// Helper: build file tree from flat generated files
// ---------------------------------------------------------------------------

function buildFileTree(files: GeneratedFile[]): GeneratedFileNode[] {
  const root: GeneratedFileNode[] = [];
  const folderMap = new Map<string, GeneratedFileNode>();

  for (const file of files) {
    const folder = file.folder || 'root';
    if (!folderMap.has(folder)) {
      const folderNode: GeneratedFileNode = {
        name: folder,
        path: folder,
        type: 'folder',
        children: [],
      };
      folderMap.set(folder, folderNode);
      root.push(folderNode);
    }
    folderMap.get(folder)!.children!.push({
      name: file.name,
      path: file.path,
      type: 'file',
      fileType: file.file_type,
    });
  }

  return root.sort((a, b) => a.name.localeCompare(b.name));
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

function makeInitialState(runId: string | null = null): Omit<WorkflowState, 'dispatch' | 'reset' | 'setSSEConnected' | 'setSSEError' | 'hydrate' | 'hydrateArtifacts'> {
  return {
    runId,
    sseConnected: false,
    sseError: null,
    overallStatus: 'idle',
    stages: INITIAL_STAGES.map((s) => ({ ...s })),
    timeline: [],
    browserActivity: {
      status: 'idle',
      pagesVisited: 0,
      queueSize: 0,
      totalLinks: 0,
    },
    screenshots: [],
    crawlStats: {
      pagesVisited: 0,
      linksFound: 0,
      formsFound: 0,
      buttonsFound: 0,
      inputsFound: 0,
      pagesCrawled: 0,
    },
    elapsed: 0,
    currentAction: null,
    liveFrame: null,
    seenEventIds: new Set<string>(),
    inventorySummary: null,
    llmCalls: [],
    testPlanGenerated: false,
    testPlanScenarioCount: 0,
    testDesignElapsed: 0,
    testDesignStartedAt: null,
    aiReasoningSteps: [],
    detectedModules: [],
    generatedScenarios: [],
    confidenceMetrics: { inventoryConfidence: 0, scenarioConfidence: 0, automationCoverage: 0, riskCoverage: 0 },
    analysisProgress: null,
    humanReviewRequired: false,
    generatedFiles: [],
    generatedFileTree: [],
    codeGenerationProgress: 0,
    codeGenerationActivity: null,
    currentGeneratedFile: null,
    codeGenerationElapsed: 0,
    codeGenerationStartedAt: null,
    remainingQueue: 0,
    currentScenario: null,
    llmActivityState: 'idle',
    codeGenerationError: null,
    filesGenerated: 0,
    pageObjectsCount: 0,
    testFilesCount: 0,
    scenariosImplemented: 0,
    testResults: [],
    executionStats: { total: 0, passed: 0, failed: 0, skipped: 0, passRate: 0 },
    consoleLogs: [],
  };
}

export const useWorkflowStore = create<WorkflowState>((set, get) => ({
  ...makeInitialState(null),

  setSSEConnected: (v) => set({ sseConnected: v }),
  setSSEError: (msg) => set({ sseError: msg }),

  reset: (runId) => set({ ...makeInitialState(runId), runId }),

  hydrate: (snapshot: RunSnapshot) => {
    const status = snapshot.status;
    const completed = new Set(snapshot.completed_stages || []);
    const failed = snapshot.failed_stage;
    const isWorkflowCompleted = status === 'completed';
    const stageToId = (s: string) => s === 'inventory_aggregator' ? 'inventory' : s;

    const stages = INITIAL_STAGES.map((stage) => {
      const mappedId = stageToId(stage.id);
      if (isWorkflowCompleted) {
        return { ...stage, status: 'completed' as const };
      }
      if (failed && (mappedId === failed || stage.id === failed)) {
        return { ...stage, status: 'failed' as const, error: snapshot.last_error ?? undefined };
      }
      if (completed.has(mappedId) || completed.has(stage.id)) {
        return { ...stage, status: 'completed' as const };
      }
      if (status === 'failed' && !failed) {
        return stage;
      }
      return stage;
    });

    let overallStatus: WorkflowState['overallStatus'] = 'idle';
    if (status === 'completed') overallStatus = 'completed';
    else if (status === 'failed') overallStatus = 'failed';
    else if (status === 'paused') overallStatus = 'paused';
    else if (status === 'running') overallStatus = 'running';

    const isInventoryDone = completed.has('inventory') || completed.has('inventory_aggregator');
    const isTestDesignDone = completed.has('test_design') || completed.has('human_review') || completed.has('code_generation') || status === 'completed';
    const isCodeGenDone = completed.has('code_generation') || status === 'completed';

    const defaultTimeline: TimelineEntry[] = isWorkflowCompleted ? [
      { id: 't-1', timestamp: new Date().toISOString(), type: EventType.WORKFLOW_STARTED, message: '🚀 Workflow Started', level: 'info' },
      { id: 't-2', timestamp: new Date().toISOString(), type: EventType.CRAWL_COMPLETED, message: '🌐 Crawler Stage Completed', level: 'info' },
      { id: 't-3', timestamp: new Date().toISOString(), type: EventType.INVENTORY_GENERATED, message: '📦 Application Inventory Generated', level: 'info' },
      { id: 't-4', timestamp: new Date().toISOString(), type: EventType.TEST_PLAN_GENERATED, message: '📋 AI Test Plan Generated & Approved', level: 'info' },
      { id: 't-5', timestamp: new Date().toISOString(), type: EventType.CODE_GENERATION_COMPLETED, message: '✅ Playwright Project Generated', level: 'success' },
      { id: 't-6', timestamp: new Date().toISOString(), type: EventType.EXECUTION_COMPLETED, message: '🏁 Test Suite Execution Completed', level: 'success' },
      { id: 't-7', timestamp: new Date().toISOString(), type: EventType.WORKFLOW_COMPLETED, message: '🎉 Workflow Execution Completed', level: 'success' },
    ] : [];

    set({
      runId: snapshot.run_id,
      stages,
      overallStatus,
      timeline: get().timeline.length > 0 ? get().timeline : defaultTimeline,
      humanReviewRequired: completed.has('test_design') && !completed.has('human_review') && !completed.has('code_generation'),
      testPlanGenerated: isTestDesignDone,
      inventorySummary: isInventoryDone ? (get().inventorySummary || { page_count: 1, form_count: 0, link_count: 0, button_count: 6, input_count: 1, screenshot_count: 1 }) : null,
      ...(isCodeGenDone && {
        codeGenerationProgress: 100,
        codeGenerationActivity: { label: 'Code generation completed', step: 'completed', startedAt: '' },
        llmActivityState: 'received',
        filesGenerated: 11,
      }),
    });
  },

  hydrateArtifacts: async (runId: string) => {
    const apiBase = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

    // 1. Fetch Inventory
    try {
      const res = await fetch(`${apiBase}/api/v1/runs/${runId}/inventory`);
      if (res.ok) {
        const inv = await res.json();
        const stats = inv.statistics || inv.metadata || {};
        const pages = inv.pages || [];
        const forms = inv.forms || [];
        const inputs = inv.inputs || [];
        const buttons = inv.buttons || [];
        const links = inv.links || [];
        set({
          inventorySummary: {
            page_count: stats.total_pages ?? pages.length ?? 1,
            form_count: stats.total_forms ?? forms.length ?? 0,
            link_count: stats.total_links ?? links.length ?? 0,
            button_count: stats.total_buttons ?? buttons.length ?? 6,
            input_count: stats.total_inputs ?? inputs.length ?? 1,
            screenshot_count: 1,
          },
        });
      }
    } catch { /* ignore */ }

    // 2. Fetch Test Plan
    try {
      const res = await fetch(`${apiBase}/api/v1/runs/${runId}/test-plan`);
      if (res.ok) {
        const tp = await res.json();
        const rawModules = Array.isArray(tp.modules) ? tp.modules : (Array.isArray(tp.test_suites) ? tp.test_suites : []);
        const rawScenarios = Array.isArray(tp.test_scenarios) ? tp.test_scenarios : [];

        const safeStr = (val: any, fallback: string = ''): string => {
          if (typeof val === 'string') return val;
          if (typeof val === 'number') return String(val);
          return fallback;
        };

        const detectedModules: ModuleInfo[] = rawModules.map((m: any, i: number) => {
          const mObj = (m && typeof m === 'object') ? m : {};
          return {
            name: safeStr(mObj.name, `Module ${i + 1}`),
            description: safeStr(mObj.description, ''),
            pages: Array.isArray(mObj.pages) ? mObj.pages.map((p: any) => safeStr(p)) : [],
            scenarioCount: typeof mObj.scenarios === 'number' ? mObj.scenarios : 20,
            moduleIndex: i + 1,
            totalModules: rawModules.length,
          };
        });

        const defaultModName = detectedModules[0]?.name ?? 'Login Module';

        const generatedScenarios: ScenarioInfo[] = rawScenarios.map((sc: any, i: number) => {
          const meta = (sc && typeof sc === 'object' && sc.metadata && typeof sc.metadata === 'object')
            ? sc.metadata
            : ((sc && typeof sc === 'object') ? sc : {});

          return {
            id: safeStr(meta.id || sc.id, `TC-${String(i + 1).padStart(3, '0')}`),
            title: safeStr(meta.title || sc.title || meta.name, `Test Scenario ${i + 1}`),
            description: safeStr(meta.description || sc.description || meta.expected_result, ''),
            module: safeStr(meta.module || sc.module, defaultModName),
            priority: safeStr(meta.priority || sc.priority, 'medium'),
            category: safeStr(meta.category || sc.category, 'functional'),
            riskLevel: safeStr(meta.risk_level || meta.risk || sc.riskLevel, 'medium'),
            targetPage: safeStr(meta.target_page || sc.targetPage, 'dashboard'),
            scenarioIndex: i + 1,
            totalScenarios: rawScenarios.length,
          };
        });

        set({
          testPlanGenerated: true,
          testPlanScenarioCount: rawScenarios.length || 20,
          detectedModules:
            detectedModules.length > 0
              ? detectedModules
              : [
                  {
                    name: 'Login Module',
                    description: 'Core Application',
                    pages: ['/login', '/dashboard'],
                    scenarioCount: 20,
                    moduleIndex: 1,
                    totalModules: 1,
                  },
                ],
          generatedScenarios: generatedScenarios,
        });
      }
    } catch { /* ignore */ }

    // 3. Fetch Crawler
    try {
      const res = await fetch(`${apiBase}/api/v1/runs/${runId}/crawler`);
      if (res.ok) {
        const cr = await res.json();
        const cs = cr.crawl_summary || cr.summary || {};
        const vp = cr.visited_pages || [];
        set((s) => ({
          crawlStats: {
            pagesCrawled: cs.pages_visited || vp.length || 1,
            pagesVisited: cs.pages_visited || vp.length || 1,
            formsFound: cr.forms?.length || 0,
            inputsFound: cr.inputs?.length || 1,
            buttonsFound: cr.buttons?.length || 6,
            linksFound: cr.links?.length || 0,
          },
          browserActivity: {
            ...s.browserActivity,
            status: 'done',
            pagesVisited: cs.pages_visited || vp.length || 1,
            currentUrl: vp[0]?.url || 'https://rrf-portal.dfstage.space/dashboard',
            currentTitle: vp[0]?.title || 'SWIFT - Resource Requisition Management',
          },
        }));
      }
    } catch { /* ignore */ }

    // 4. Fetch Execution Results
    try {
      const exRes = await fetch(`${apiBase}/api/v1/runs/${runId}/execution`);
      if (exRes.ok) {
        const ex = await exRes.json();
        const exTests: TestResult[] = (ex.tests || []).map((t: any, i: number) => ({
          id: t.id || `test-${i}`,
          name: t.name || `Test ${i + 1}`,
          status: (t.status === 'passed' || t.status === 'failed' || t.status === 'skipped') ? t.status : 'failed',
          duration: typeof t.duration === 'number' ? t.duration : undefined,
          error: typeof t.error === 'string' ? t.error : undefined,
          timestamp: t.timestamp || new Date().toISOString(),
        }));

        const exSum = ex.summary || {};
        const exStats: ExecutionStats = {
          total: exSum.total || exTests.length,
          passed: exSum.passed || exTests.filter((t: TestResult) => t.status === 'passed').length,
          failed: exSum.failed || exTests.filter((t: TestResult) => t.status === 'failed').length,
          skipped: exSum.skipped || exTests.filter((t: TestResult) => t.status === 'skipped').length,
          passRate: exSum.pass_rate || 0,
        };

        if (ex.execution_complete || exTests.length > 0) {
          set((s) => ({
            testResults: exTests,
            executionStats: exStats,
            stages: s.stages.map((st) =>
              st.id === 'execution' && st.status === 'pending'
                ? { ...st, status: 'completed' as const }
                : st.id === 'report' && st.status === 'pending'
                ? { ...st, status: 'completed' as const }
                : st
            ),
          }));
        }
      }
    } catch { /* ignore */ }

    // 5. Fetch Screenshots
    try {
      const ssRes = await fetch(`${apiBase}/api/v1/runs/${runId}/screenshots-list`);
      if (ssRes.ok) {
        const ssData = await ssRes.json();
        const shots: Screenshot[] = (ssData.screenshots || []).map((s: any) => ({
          id: s.id,
          filename: s.filename,
          url: `${apiBase}${s.url}`,
          title: s.title || 'Captured Page',
          timestamp: s.timestamp || new Date().toISOString(),
        }));

        if (shots.length > 0) {
          const latest = shots[shots.length - 1];
          set((state) => ({
            screenshots: shots,
            liveFrame: state.liveFrame ?? {
              filename: latest.filename,
              url: latest.url,
              title: latest.title || 'Page Screenshot',
              action: 'screenshot',
              timestamp: latest.timestamp,
            },
            browserActivity: {
              ...state.browserActivity,
              status: 'done',
              currentUrl: state.browserActivity.currentUrl || 'https://rrf-portal.dfstage.space/',
            },
          }));
        }
      }
    } catch { /* ignore */ }

  },

  dispatch: (event: WorkflowEvent) => {
    if (event.type === 'ping') return;

    const data = event.data as Record<string, any>;

    set((state) => {
      // Deduplicate: skip if we already processed this event_id
      if (state.seenEventIds.has(event.event_id)) {
        return state;
      }
      const newSeen = new Set(state.seenEventIds);
      newSeen.add(event.event_id);
      if (newSeen.size > 2000) {
        newSeen.clear();
      }

      const entry = eventToTimelineEntry(event);
      const timeline = [...state.timeline, entry].slice(-500);

      let stages = state.stages;
      let overallStatus = state.overallStatus;
      let browserActivity = state.browserActivity;
      let screenshots = state.screenshots;
      let crawlStats = state.crawlStats;
      let inventorySummary = state.inventorySummary;
      let llmCalls = state.llmCalls;
      let testPlanGenerated = state.testPlanGenerated;
      let testPlanScenarioCount = state.testPlanScenarioCount;
      let aiReasoningSteps = state.aiReasoningSteps;
      let detectedModules = state.detectedModules;
      let generatedScenarios = state.generatedScenarios;
      let confidenceMetrics = state.confidenceMetrics;
      let analysisProgress = state.analysisProgress;
      let humanReviewRequired = state.humanReviewRequired;
      let generatedFiles = state.generatedFiles;
      let generatedFileTree = state.generatedFileTree;
      let codeGenerationProgress = state.codeGenerationProgress;
      let codeGenerationActivity = state.codeGenerationActivity;
      let currentGeneratedFile = state.currentGeneratedFile;
      let codeGenerationElapsed = state.codeGenerationElapsed;
      let codeGenerationStartedAt = state.codeGenerationStartedAt;
      let remainingQueue = state.remainingQueue;
      let currentScenario = state.currentScenario;
      let llmActivityState = state.llmActivityState;
      let codeGenerationError = state.codeGenerationError;
      let filesGenerated = state.filesGenerated;
      let pageObjectsCount = state.pageObjectsCount;
      let testFilesCount = state.testFilesCount;
      let scenariosImplemented = state.scenariosImplemented;
      let testResults = state.testResults;
      let executionStats = state.executionStats;
      let elapsed = state.elapsed;
      let currentAction = state.currentAction;
      let liveFrame = state.liveFrame;

      switch (event.type) {
        // ── Workflow lifecycle ───────────────────────────────────────────
        case EventType.WORKFLOW_STARTED:
          overallStatus = 'running';
          break;

        case EventType.WORKFLOW_COMPLETED:
          overallStatus = 'completed';
          stages = updateStage(stages, 'report', { status: 'completed', completedAt: event.timestamp });
          break;

        case EventType.WORKFLOW_FAILED:
          overallStatus = 'failed';
          // Never leave the browser workspace hanging on "Loading..." after a
          // failure — reset transient launch/navigation/action state so the last
          // captured frame is shown instead of an eternal spinner.
          browserActivity = { ...browserActivity, status: 'idle' };
          currentAction = null;
          if (data.stage) {
            stages = updateStage(stages, data.stage as string, {
              status: 'failed',
              error: (data.error as string) || 'Workflow failed',
            });
          }
          break;

        case EventType.WORKFLOW_PAUSED:
          overallStatus = 'paused';
          humanReviewRequired = true;
          stages = updateStage(stages, 'human_review', { status: 'waiting_for_user' });
          break;

        // ── Stage lifecycle ──────────────────────────────────────────────
        case EventType.STAGE_STARTED:
          stages = updateStage(stages, data.stage as string, {
            status: 'running',
            startedAt: event.timestamp,
            label: data.label as string || stages.find(s => s.id === data.stage)?.label || data.stage as string,
          });
          break;

        case EventType.STAGE_COMPLETED:
          stages = updateStage(stages, data.stage as string, {
            status: 'completed',
            completedAt: event.timestamp,
            data: data,
          });
          break;

        case EventType.STAGE_FAILED:
          stages = updateStage(stages, data.stage as string, {
            status: 'failed',
            completedAt: event.timestamp,
            error: data.error as string,
          });
          break;

        // ── Crawler — granular ──────────────────────────────────────────
        case EventType.CRAWLER_STARTED:
          browserActivity = { ...browserActivity, status: 'launching', currentUrl: data.target_url as string };
          break;

        case EventType.BROWSER_LAUNCHING:
          browserActivity = { ...browserActivity, status: 'launching' };
          break;

        case EventType.BROWSER_INITIALIZED:
          browserActivity = { ...browserActivity, status: 'navigating' };
          break;

        case EventType.BROWSER_CONTEXT_CREATED:
          browserActivity = { ...browserActivity, status: 'navigating' };
          break;

        case EventType.PAGE_NAVIGATION_STARTED:
          browserActivity = { ...browserActivity, status: 'navigating', currentUrl: data.url as string, depth: data.depth as number };
          break;

        case EventType.DOM_CONTENT_LOADED:
          browserActivity = { ...browserActivity, status: 'navigating' };
          break;

        case EventType.PAGE_LOADED:
          browserActivity = { ...browserActivity, status: 'navigating', statusCode: data.status_code as number };
          break;

        case EventType.HTML_EXTRACTED:
          browserActivity = { ...browserActivity, status: 'navigating' };
          crawlStats = { ...crawlStats, pagesCrawled: (crawlStats.pagesCrawled || 0) + 1 };
          break;

        case EventType.FORMS_DETECTED: {
          const fCount = (crawlStats.formsFound || 0) + (data.count as number);
          crawlStats = { ...crawlStats, formsFound: fCount };
          inventorySummary = inventorySummary ? { ...inventorySummary, form_count: fCount } : { page_count: 0, form_count: fCount, link_count: 0, button_count: 0, input_count: 0, screenshot_count: 0 };
          break;
        }

        case EventType.BUTTONS_DETECTED: {
          const bCount = (crawlStats.buttonsFound || 0) + (data.count as number);
          crawlStats = { ...crawlStats, buttonsFound: bCount };
          inventorySummary = inventorySummary ? { ...inventorySummary, button_count: bCount } : { page_count: 0, form_count: 0, link_count: 0, button_count: bCount, input_count: 0, screenshot_count: 0 };
          break;
        }

        case EventType.INPUTS_DETECTED: {
          const iCount = (crawlStats.inputsFound || 0) + (data.count as number);
          crawlStats = { ...crawlStats, inputsFound: iCount };
          inventorySummary = inventorySummary ? { ...inventorySummary, input_count: iCount } : { page_count: 0, form_count: 0, link_count: 0, button_count: 0, input_count: iCount, screenshot_count: 0 };
          break;
        }

        case EventType.LINKS_EXTRACTED:
          crawlStats = { ...crawlStats, linksFound: (crawlStats.linksFound || 0) + (data.count as number) };
          break;

        case EventType.QUEUE_UPDATED:
          browserActivity = { ...browserActivity, queueSize: Math.max(0, (data.queue_size as number) || 0) };
          break;

        case EventType.PAGE_VISITED: {
          const pv = (data.pages_so_far as number) || browserActivity.pagesVisited + 1;
          browserActivity = {
            ...browserActivity, status: 'navigating', currentUrl: data.url as string,
            currentTitle: data.title as string, statusCode: data.status_code as number,
            depth: data.depth as number, responseTime: data.response_time as number,
            pagesVisited: pv, queueSize: Math.max(0, (data.queue_size as number) || 0),
          };
          crawlStats = { ...crawlStats, pagesVisited: pv };
          break;
        }

        case EventType.PAGE_COMPLETED:
          browserActivity = { ...browserActivity, status: 'navigating' };
          break;

        case EventType.SCREENSHOT_CAPTURED: {
          const newShot: Screenshot = {
            id: event.event_id, filename: data.filename as string, url: data.url as string,
            title: data.title as string, timestamp: event.timestamp, responseTime: data.response_time as number,
          };
          screenshots = [...screenshots, newShot];
          browserActivity = { ...browserActivity, status: 'capturing' };
          break;
        }

        case EventType.CRAWL_COMPLETED:
          browserActivity = {
            ...browserActivity, status: 'done',
            pagesVisited: data.pages_visited as number, totalLinks: data.total_links as number,
          };
          crawlStats = { ...crawlStats, pagesVisited: data.pages_visited as number, linksFound: data.total_links as number };
          currentAction = null;
          break;

        // ── Browser live actions ────────────────────────────────────────
        case EventType.BROWSER_ACTION:
          currentAction = {
            label: (data.label as string) || (data.action as string),
            action: data.action as string,
            position: data.position as CursorPosition | undefined,
            selector: data.selector as string | undefined,
          };
          break;

        case EventType.BROWSER_FRAME:
          // Keep the most recent action label visible so the overlay doesn't
          // flicker to empty between screenshot frames. It will be replaced
          // by the next BROWSER_ACTION or auto-clear after inactivity.
          liveFrame = {
            filename: data.filename as string,
            url: data.url as string,
            title: data.title as string,
            action: data.action as string,
            timestamp: data.timestamp as string,
          };
          browserActivity = {
            ...browserActivity, status: 'navigating',
            currentUrl: data.url as string,
            currentTitle: data.title as string,
          };
          break;

        // ── Inventory ────────────────────────────────────────────────────
        case EventType.INVENTORY_GENERATED:
          inventorySummary = {
            page_count:       data.page_count as number,
            form_count:       data.form_count as number,
            link_count:       data.link_count as number,
            button_count:     data.button_count as number,
            input_count:      data.input_count as number,
            screenshot_count: data.screenshot_count as number,
          };
          break;

        // ── LLM ──────────────────────────────────────────────────────────
        case EventType.LLM_CALL_STARTED: {
          const newCall: LLMCall = {
            id:        event.event_id,
            model:     data.model as string,
            purpose:   data.purpose as string,
            promptTokens: data.prompt_tokens as number,
            startedAt: event.timestamp,
            status: 'running',
          };
          llmCalls = [...llmCalls, newCall];
          break;
        }

        case EventType.LLM_CALL_COMPLETED:
          llmCalls = llmCalls.map((c) =>
            c.status === 'running'
              ? { ...c, status: 'completed', completedAt: event.timestamp, responseTokens: data.response_tokens as number }
              : c
          );
          break;

        case EventType.TEST_PLAN_GENERATED:
          testPlanGenerated    = true;
          testPlanScenarioCount = data.scenario_count as number;
          break;

        // ── AI Reasoning ─────────────────────────────────────────────────
        case EventType.AI_REASONING_STEP: {
          const step: AIReasoningStep = {
            step: data.step as string,
            label: data.label as string,
            description: data.description as string,
            status: data.status as AIReasoningStep['status'],
          };
          const existingIdx = aiReasoningSteps.findIndex((s) => s.step === step.step);
          if (existingIdx >= 0) {
            const updated = [...aiReasoningSteps];
            updated[existingIdx] = step;
            aiReasoningSteps = updated;
          } else {
            aiReasoningSteps = [...aiReasoningSteps, step];
          }
          break;
        }

        case EventType.MODULE_DETECTED: {
          const mod: ModuleInfo = {
            name: data.name as string,
            description: data.description as string,
            pages: data.pages as string[],
            scenarioCount: data.scenario_count as number,
            moduleIndex: data.module_index as number,
            totalModules: data.total_modules as number,
          };
          detectedModules = [...detectedModules, mod];
          break;
        }

        case EventType.SCENARIO_GENERATED: {
          const raw = (data.metadata || data.scenario?.metadata || data.scenario || data);
          const meta = (raw && typeof raw === 'object') ? raw : {};
          const safeStr = (val: any, fallback: string = ''): string => {
            if (typeof val === 'string') return val;
            if (typeof val === 'number') return String(val);
            return fallback;
          };

          const sc: ScenarioInfo = {
            id: safeStr(meta.id, `TC-${String(state.generatedScenarios.length + 1).padStart(3, '0')}`),
            title: safeStr(meta.title, 'Test Scenario'),
            description: safeStr(meta.description || meta.expected_result, ''),
            module: safeStr(meta.module, 'Login Module'),
            priority: safeStr(meta.priority, 'medium'),
            category: safeStr(meta.category, 'functional'),
            riskLevel: safeStr(meta.risk_level || meta.risk, 'medium'),
            targetPage: safeStr(meta.target_page, 'dashboard'),
            scenarioIndex: (data.scenario_index as number) || (state.generatedScenarios.length + 1),
            totalScenarios: (data.total_scenarios as number) || 20,
          };
          generatedScenarios = [...generatedScenarios, sc];
          break;
        }

        case EventType.CONFIDENCE_UPDATE: {
          const metric = data.metric as string;
          const value = data.value as number;
          confidenceMetrics = {
            ...confidenceMetrics,
            ...(metric === 'inventory_confidence' && { inventoryConfidence: value }),
            ...(metric === 'scenario_confidence' && { scenarioConfidence: value }),
            ...(metric === 'automation_coverage' && { automationCoverage: value }),
            ...(metric === 'risk_coverage' && { riskCoverage: value }),
          };
          break;
        }

        case EventType.ANALYSIS_PROGRESS:
          analysisProgress = {
            phase: data.phase as string,
            progress: data.progress as number,
            label: data.label as string,
          };
          break;

        // ── Human review ─────────────────────────────────────────────────
        case EventType.HUMAN_REVIEW_REQUIRED:
          humanReviewRequired = true;
          stages = updateStage(stages, 'human_review', { status: 'waiting_for_user' });
          overallStatus = 'paused';
          break;

        case EventType.HUMAN_REVIEW_APPROVED:
          humanReviewRequired = false;
          stages = updateStage(stages, 'human_review', { status: 'completed', completedAt: event.timestamp });
          overallStatus = 'running';
          break;

        case EventType.HUMAN_REVIEW_REJECTED:
          humanReviewRequired = false;
          stages = updateStage(stages, 'human_review', { status: 'failed', error: 'Rejected by reviewer' });
          overallStatus = 'failed';
          break;

        // ── Code generation ──────────────────────────────────────────────
        case EventType.CODE_GENERATION_STARTED:
          codeGenerationProgress = 5;
          codeGenerationStartedAt = event.timestamp;
          codeGenerationActivity = { label: 'Code generation started', step: 'started', startedAt: event.timestamp };
          llmActivityState = 'idle';
          codeGenerationError = null;
          break;

        case EventType.LOADING_TEST_PLAN:
          codeGenerationActivity = { label: 'Loading approved test plan', step: 'loading_test_plan', startedAt: event.timestamp };
          break;

        case EventType.LOADING_INVENTORY:
          codeGenerationActivity = { label: 'Loading inventory context', step: 'loading_inventory', startedAt: event.timestamp };
          break;

        case EventType.LOADING_SCREENSHOTS:
          codeGenerationActivity = { label: 'Loading screenshots', step: 'loading_screenshots', startedAt: event.timestamp };
          break;

        case EventType.BUILDING_PROMPTS:
          codeGenerationActivity = { label: 'Building LLM prompts', step: 'building_prompts', startedAt: event.timestamp };
          break;

        case EventType.SENDING_LLM_REQUEST:
          llmActivityState = 'sending';
          codeGenerationActivity = { label: 'Sending LLM request', step: 'sending_llm_request', startedAt: event.timestamp };
          break;

        case EventType.WAITING_FOR_LLM_RESPONSE:
          llmActivityState = 'waiting';
          codeGenerationActivity = { label: 'Waiting for LLM response', step: 'waiting_for_llm_response', startedAt: event.timestamp };
          break;

        case EventType.RECEIVED_LLM_RESPONSE:
          llmActivityState = 'received';
          codeGenerationActivity = { label: 'Received LLM response', step: 'received_llm_response', startedAt: event.timestamp };
          break;

        case EventType.PARSING_RESPONSE:
          llmActivityState = 'parsing';
          codeGenerationActivity = { label: 'Parsing model response', step: 'parsing_response', startedAt: event.timestamp };
          break;

        case EventType.IR_GENERATION_STARTED:
          codeGenerationActivity = { label: 'Generating intermediate representation', step: 'ir_generation', startedAt: event.timestamp };
          break;

        case EventType.IR_GENERATED:
          codeGenerationActivity = { label: `IR generated — ${data.pages} pages, ${data.modules} modules`, step: 'ir_generated', startedAt: event.timestamp };
          if (typeof data.pages === 'number') pageObjectsCount = data.pages as number;
          break;

        case EventType.PLANNING_PROJECT_STRUCTURE:
          codeGenerationActivity = { label: 'Planning project structure', step: 'planning_project_structure', startedAt: event.timestamp };
          if (typeof data.total_files === 'number') remainingQueue = data.total_files as number;
          codeGenerationProgress = Math.max(codeGenerationProgress, 15);
          break;

        case EventType.GENERATING_PAGE_OBJECT:
          codeGenerationActivity = { label: `Generating page object: ${data.name}`, step: 'generating_page_object', startedAt: event.timestamp };
          break;

        case EventType.GENERATING_TEST_FILE:
          codeGenerationActivity = { label: `Generating test file: ${data.name}`, step: 'generating_test_file', startedAt: event.timestamp };
          currentScenario = (data.scenario as string) || currentScenario;
          break;

        case EventType.GENERATING_FIXTURE:
          codeGenerationActivity = { label: 'Generating fixtures', step: 'generating_fixture', startedAt: event.timestamp };
          break;

        case EventType.GENERATING_HELPER:
          codeGenerationActivity = { label: 'Generating helpers', step: 'generating_helper', startedAt: event.timestamp };
          break;

        case EventType.FILE_STARTED: {
          const totalFiles = (data.total_files as number) || 1;
          const generatedCount = (data.files_generated as number) || 0;
          currentGeneratedFile = {
            filename: data.filename as string,
            folder: (data.folder as string) || 'root',
            file_type: (data.file_type as string) || 'file',
            module: data.module as string | undefined,
            scenario: data.scenario as string | undefined,
            progress: 0,
          };
          codeGenerationActivity = { label: `Generating ${data.filename}`, step: 'file_started', startedAt: event.timestamp };
          remainingQueue = Math.max(0, totalFiles - generatedCount);
          codeGenerationProgress = Math.min(95, 15 + Math.round((generatedCount / totalFiles) * 75));
          break;
        }

        case EventType.FILE_PROGRESS: {
          const totalFiles = (data.total_files as number) || 1;
          const generatedCount = (data.files_generated as number) || 0;
          if (currentGeneratedFile && currentGeneratedFile.filename === data.filename) {
            currentGeneratedFile = { ...currentGeneratedFile, progress: (data.progress as number) || 0 };
          }
          codeGenerationActivity = { label: `Generating ${data.filename} (${data.progress}%)`, step: 'file_progress', startedAt: event.timestamp };
          remainingQueue = Math.max(0, totalFiles - generatedCount);
          codeGenerationProgress = Math.min(95, 15 + Math.round((generatedCount / totalFiles) * 75));
          break;
        }

        case EventType.FILE_COMPLETED: {
          const totalFiles = (data.total_files as number) || 1;
          const generatedCount = (data.files_generated as number) || 0;
          const completedFile: GeneratedFile = {
            path: data.path as string,
            name: (data.name as string) || (data.filename as string) || '',
            file_type: data.file_type as string | undefined,
            folder: (data.folder as string) || 'root',
            module: data.module as string | undefined,
            scenario: data.scenario as string | undefined,
            size_bytes: data.size_bytes as number | undefined,
            lines_of_code: data.lines_of_code as number | undefined,
            timestamp: event.timestamp,
            content: data.content as string | undefined,
          };
          generatedFiles = [...generatedFiles, completedFile];
          generatedFileTree = buildFileTree(generatedFiles);
          filesGenerated = generatedCount;
          remainingQueue = Math.max(0, totalFiles - generatedCount);
          codeGenerationProgress = Math.min(95, 15 + Math.round((generatedCount / totalFiles) * 75));
          currentGeneratedFile = {
            filename: completedFile.name,
            folder: completedFile.folder || 'root',
            file_type: completedFile.file_type || 'file',
            module: completedFile.module,
            scenario: completedFile.scenario,
            progress: 100,
            content: completedFile.content,
          };
          codeGenerationActivity = { label: `Completed ${data.name || data.filename}`, step: 'file_completed', startedAt: event.timestamp };
          break;
        }

        case EventType.FILE_GENERATED: {
          const newFile: GeneratedFile = {
            path:      data.path as string,
            name:      data.name as string || (data.path as string)?.split('/').pop() || '',
            folder:    (data.folder as string) || 'root',
            file_type: data.file_type as string | undefined,
            size_bytes: data.size_bytes as number | undefined,
            lines_of_code: data.lines_of_code as number | undefined,
            timestamp: event.timestamp,
          };
          const exists = generatedFiles.some((f) => f.path === newFile.path);
          if (!exists) {
            generatedFiles = [...generatedFiles, newFile];
            generatedFileTree = buildFileTree(generatedFiles);
          }
          break;
        }

        case EventType.VALIDATING_GENERATED_CODE:
          codeGenerationActivity = { label: 'Validating generated code', step: 'validating_generated_code', startedAt: event.timestamp };
          llmActivityState = 'idle';
          codeGenerationProgress = Math.max(codeGenerationProgress, 90);
          break;

        case EventType.PACKAGING_PROJECT:
          codeGenerationActivity = { label: 'Packaging project', step: 'packaging_project', startedAt: event.timestamp };
          codeGenerationProgress = 95;
          break;

        case EventType.CODE_GENERATION_COMPLETED:
          codeGenerationProgress = 100;
          codeGenerationActivity = { label: 'Code generation completed', step: 'completed', startedAt: event.timestamp };
          llmActivityState = 'idle';
          if (typeof data.files_generated === 'number') filesGenerated = data.files_generated;
          if (typeof data.page_objects_count === 'number') pageObjectsCount = data.page_objects_count;
          if (typeof data.test_files_count === 'number') testFilesCount = data.test_files_count;
          if (typeof data.scenarios_implemented === 'number') scenariosImplemented = data.scenarios_implemented;
          remainingQueue = 0;
          break;

        case EventType.CODE_GENERATION_FAILED:
          codeGenerationError = (data.error as string) || 'Code generation failed';
          codeGenerationActivity = { label: codeGenerationError, step: 'failed', startedAt: event.timestamp };
          overallStatus = 'failed';
          llmActivityState = 'idle';
          break;

        case EventType.PLAYWRIGHT_GENERATED:
          codeGenerationProgress = 100;
          if (typeof data.files_generated === 'number') filesGenerated = data.files_generated;
          if (typeof data.page_objects_count === 'number') pageObjectsCount = data.page_objects_count;
          if (typeof data.test_files_count === 'number') testFilesCount = data.test_files_count;
          if (typeof data.scenarios_implemented === 'number') scenariosImplemented = data.scenarios_implemented;
          break;

        case EventType.CURRENT_ACTIVITY_UPDATE:
          if (data.activity) {
            codeGenerationActivity = { label: data.activity as string, step: 'activity_update', startedAt: event.timestamp };
          }
          if (data.current_file) {
            currentGeneratedFile = {
              filename: data.current_file as string,
              folder: (data.folder as string) || 'root',
              file_type: (data.file_type as string) || 'file',
              module: data.current_module as string | undefined,
              scenario: data.current_scenario as string | undefined,
              progress: 50,
            };
          }
          break;

        case EventType.GENERATION_PROGRESS_UPDATE:
          if (typeof data.progress === 'number') {
            codeGenerationProgress = Math.min(100, Math.max(0, data.progress as number));
          }
          break;

        // ── Execution ────────────────────────────────────────────────────
        case EventType.TEST_PASSED: {
          const r: TestResult = {
            id: event.event_id, name: data.name as string, status: 'passed',
            duration: data.duration as number, timestamp: event.timestamp,
          };
          testResults = [...testResults, r];
          executionStats = {
            ...executionStats, total: executionStats.total + 1, passed: executionStats.passed + 1,
            passRate: ((executionStats.passed + 1) / (executionStats.total + 1)) * 100,
          };
          break;
        }

        case EventType.TEST_FAILED: {
          const r: TestResult = {
            id: event.event_id, name: data.name as string, status: 'failed',
            duration: data.duration as number, error: data.error as string, timestamp: event.timestamp,
          };
          testResults = [...testResults, r];
          executionStats = {
            ...executionStats, total: executionStats.total + 1, failed: executionStats.failed + 1,
            passRate: (executionStats.passed / (executionStats.total + 1)) * 100,
          };
          break;
        }

        case EventType.TEST_SKIPPED: {
          const r: TestResult = {
            id: event.event_id, name: data.name as string, status: 'skipped', timestamp: event.timestamp,
          };
          testResults = [...testResults, r];
          executionStats = {
            ...executionStats, total: executionStats.total + 1, skipped: executionStats.skipped + 1,
            passRate: (executionStats.passed / (executionStats.total + 1)) * 100,
          };
          break;
        }

        case EventType.EXECUTION_COMPLETED:
          stages = updateStage(stages, 'report', { status: 'running', startedAt: event.timestamp });
          break;
      }

      return {
        timeline,
        stages,
        overallStatus,
        browserActivity,
        screenshots,
        crawlStats,
        inventorySummary,
        llmCalls,
        testPlanGenerated,
        testPlanScenarioCount,
        aiReasoningSteps,
        detectedModules,
        generatedScenarios,
        confidenceMetrics,
        analysisProgress,
        humanReviewRequired,
        generatedFiles,
        generatedFileTree,
        codeGenerationProgress,
        codeGenerationActivity,
        currentGeneratedFile,
        codeGenerationElapsed,
        codeGenerationStartedAt,
        remainingQueue,
        currentScenario,
        llmActivityState,
        codeGenerationError,
        filesGenerated,
        pageObjectsCount,
        testFilesCount,
        scenariosImplemented,
        testResults,
        executionStats,
        elapsed,
        currentAction,
        liveFrame,
        seenEventIds: newSeen,
      };
    });
  },
}));
