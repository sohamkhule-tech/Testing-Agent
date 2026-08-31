# LLM Test Generation Root-Cause Audit

**Scope:** Read-only investigation. No code modified, no tests regenerated, no assertions changed, no model/prompt changed.

**Subject run:** `0a1cc8a5-e35a-4828-8e07-ac19d8a3001d`
**Model used:** `mistral-medium-3-5` (request temperature 0.2, reasoning_level "medium")
**User prompt:** "Test the login page only." + redacted credentials
**Target base_url:** `https://rrf-portal.dfstage.space/login`

---

## 1. Executive Summary

Two generated authentication tests produce logically incorrect expectations:

1. **"Verify Case Sensitivity in Username"** fills the username with the literal strings `'VALID_USER'` and `'valid_user'` (not the real credential) and asserts `toHaveURL('/dashboard')` after each.
2. **"Verify Special Characters in Password"** fills the password with `process.env.SPECIAL_CHAR_PASSWORD || ''` (which is `undefined` → empty string) and asserts `toHaveURL('/dashboard')`.

The real application stays on `/login` for these inputs, so both assertions fail.

**The incorrect behavior does NOT originate in the Template Engine or Playwright.** It originates upstream, in the LLM-generated semantic layer, and is caused by a **missing-evidence context problem** that cascades through two LLM stages:

1. **Crawler/Inventory** captured no authentication evidence (only `/dashboard`, 0 forms, 0 links).
2. **Test Design Agent (LLM)** then fabricated 17 login scenarios with invented/ambiguous expected results and invented placeholder test data.
3. **IR Generation Agent (LLM)** disambiguated those ambiguous results in the *wrong* direction (unconditional success → `toHaveURL('/dashboard')`) and invented concrete but wrong values.
4. **Template Engine (deterministic)** faithfully rendered the IR, but has a *secondary* env-var naming mismatch (`SPECIAL_CHAR_PASSWORD` referenced vs `SPECIAL_CHARS_PASSWORD` written).
5. **Playwright** executed exactly what was generated (NOT the root cause).

**Primary root cause:** the pipeline asks the LLM to reason about authentication behavior while providing **no authentication evidence** in the inventory, and there is **no semantic validation** to reject ambiguous/unassertable expected results or invented test data.

---

## 2. Architecture Flow

```
User prompt ("Test the login page only" + credentials)
  → POST /api/v1/runs  (trigger.py:create_run)
  → ReasoningEngine (LLM)  → AgentState + ExecutionPlan
  → CrawlerAgent (Playwright, deterministic)  → crawl-package.json
  → InventoryAggregatorService (deterministic) → inventory.json
  → TestDesignAgent (LLM)  → test-plan.json
  → HumanReviewService (approved) → approved-test-plan.json
  → IRGenerationAgent (LLM) → code-generation-ir.json
  → TemplateEngine (deterministic) → *.spec.ts + .env + page objects
  → PlaywrightRunner (subprocess, deterministic) → results.json
```

Key files (all under `project-foundation/backend`):
- `app/workflows/trigger_workflow.py`
- `app/agents/test_design_agent.py`
- `app/agents/ir_generation_agent.py`
- `app/core/ir/prompt_composer.py`, `app/core/ir/instruction_builder.py`, `app/core/ir/scenario_builder.py`
- `app/generators/template_engine.py`
- `app/execution/playwright_runner.py`

---

## 3. Case Sensitivity Trace (TC-016)

Full backwards trace with exact values at each stage.

| Stage | File / Function | Value | Verdict |
|---|---|---|---|
| User prompt | run metadata `user_prompt_text` | "Test the login page only." + credentials | ✅ |
| Crawler evidence | `contracts/crawl-package.json` | **1 page = `/dashboard`**, 0 links, 0 forms | ⚠️ no login form |
| Inventory | `contracts/inventory.json` | 1 page (`/dashboard`), 0 forms, 1 input, 6 buttons | ⚠️ no login page |
| Test plan — `expected_result` | `contracts/test-plan.json` TC-016 | "System behaves consistently with case sensitivity rules (**either accepts only exact case or is case-insensitive**)" | ❌ ambiguous/non-assertable |
| Test plan — `required_test_data` | `test-plan.json` TC-016 | `uppercase_username | lowercase_username | mixed_case_username | valid_password` | ❌ invented placeholders |
| IR — fill value (step 1) | `code-generation-ir.json` TC-016 | `"value": "VALID_USER"` (literal string) | ❌ invented literal, not a variable |
| IR — fill value (step 5) | `code-generation-ir.json` TC-016 | `"value": "valid_user"` (literal string) | ❌ invented literal |
| IR — assertion | `code-generation-ir.json` TC-016 | `toHaveURL "https://rrf-portal.dfstage.space/dashboard"` (both) | ❌ assumed case-insensitive → success |
| Generated TS | `tests/auth-module.spec.ts:278–307` | `fill('VALID_USER')`, `fill('valid_user')`, `expect(page).toHaveURL('.../dashboard')` | ❌ inherited |
| Execution | `execution-artifacts/failure-analysis/failure-analysis.json` | `expect(page).toHaveURL(expected) failed` | ✅ correctly executed |

**Where the meaning became wrong:** the expected result was already ambiguous in `test-plan.json`; the IR LLM then resolved "either accepts only exact case or is case-insensitive" as "case-insensitive → success" and emitted a hard `toHaveURL('/dashboard')`, plus invented `VALID_USER`/`valid_user` as concrete fill strings.

---

## 4. Special Character Password Trace (TC-017)

| Stage | Value | Verdict |
|---|---|---|
| Test plan `expected_result` | "User is authenticated **if password is correct**." | ❌ conditional/non-assertable |
| Test plan `required_test_data` | `valid_username | special_char_password` | ❌ `special_char_password` is invented |
| IR fill value | `"$SPECIAL_CHAR_PASSWORD"` | ⚠️ references a variable |
| IR assertion | `toHaveURL "https://rrf-portal.dfstage.space/dashboard"` | ❌ assumed special-char password is correct |
| IR env vars | `SPECIAL_CHAR_PASSWORD = "P@ssw0rd!#"` (invented) | ❌ invented |
| `.env` written by TemplateEngine | `SPECIAL_CHARS_PASSWORD=hm123!#$` (**plural "CHARS"**) | ❌ name mismatch |
| Generated TS | `fill(process.env.SPECIAL_CHAR_PASSWORD || '')` → `undefined` → `''` (empty) | ❌ empty password |
| Execution | `expect(page).toHaveURL(expected) failed` | ✅ correctly executed |

**Where the value `SPECIAL_CHAR_PASSWORD` originated:** it was **invented by the IR LLM** (as `P@ssw0rd!#`). It is not a real valid password. The Template Engine's `.env` generator writes a **different** name (`SPECIAL_CHARS_PASSWORD`), so `process.env.SPECIAL_CHAR_PASSWORD` is `undefined` and the `|| ''` fallback submits an empty password.

**Where `/dashboard` originated:** the IR LLM invented a `dashboard` page (`url_pattern: "/dashboard"`) as the post-login landing page. The crawler's single observed URL was `/dashboard`, but the crawler never observed a login → dashboard transition (it landed directly on `/dashboard`).

---

## 5. Test Design Audit

- **Agent:** `TestDesignAgent` (`app/agents/test_design_agent.py`).
- **LLM call:** `_complete_and_parse_json` (`:207`) → `OpenAIClient.complete`, model `mistral-medium-3-5`, temperature `0.7`, `max_tokens = default_max_tokens`.
- **System prompt:** `PromptBuilder.build()` → `get_prompt("test-design-agent")` + parsed intent sections (`app/services/prompt_builder.py`).
- **User prompt:** full inventory JSON dump + the coverage-requirements f-string (`test_design_agent.py:403–505`) demanding "≥8 scenarios per page/module", "≥15 for auth", "do not stop early", "≥30% regression".
- **Taxonomy/test-data/expected-result instructions:** none specific beyond the schema; no instruction that expected results must be *assertable*, *single-valued*, or *grounded in evidence*.
- **Authentication-specific instructions:** none — the only auth signal is "credentials provided separately" in `PromptBuilder._build_system` (`prompt_builder.py:600–607`), which does **not** tell the model what invalid/valid/special-character inputs should produce.
- **Verdict:** The Test Design Agent **produced the incorrect semantic content** (ambiguous/conditional expected results, invented placeholder test data). It is the *first* stage where the meaning becomes wrong/ambiguous.

Evidence (test-plan.json):
- TC-016 `expected_result`: "System behaves consistently with case sensitivity rules (either accepts only exact case or is case-insensitive)."
- TC-017 `expected_result`: "User is authenticated if password is correct."

Both are **non-assertable** — they describe a condition, not an observable outcome.

---

## 6. LLM Input Audit

**Model:** `mistral-medium-3-5` (resolved via `model_registry.py`; request `ai.model`). Provider via `OPENAI_BASE_URL` (NOT read here — secret).

**Semantic input actually given to the LLM:**

1. **Inventory** (`inventory.json`) contained exactly **one page** (`https://rrf-portal.dfstage.space/dashboard`), **0 forms, 0 links, 1 input, 6 buttons**, **0 user flows**, **0 API calls**. There is **no login page, no login form, no username/password/submit element** in the inventory.
2. **User intent:** "Test the login page only." + credentials (redacted in the prompt, supplied separately).
3. **System prompt:** tells the model the crawler is authenticated and to "generate test scenarios for both authenticated and unauthenticated states."

**Critical finding:** the LLM was asked to generate login tests while receiving **zero authentication structure** in the inventory. It therefore **hallucinated** the entire login page (username/password fields, a "Login" button, an "Invalid username or password" error, a `/login` URL, a `/dashboard` landing page) and all of the test data.

**Input was insufficient and contradictory:** the base_url is `/login`, but the crawler's only observed URL is `/dashboard`. The model had no evidence about what a wrong-cased username or a special-character password actually does.

---

## 7. Raw LLM Response Audit

**The raw LLM response is NOT persisted anywhere.** The code never stores the raw `completion` text — only the *parsed* result is written (`test-plan.json`, `code-generation-ir.json`). Log statements (`openai_client.py:132`, `ir_generation_agent.py:373`) record token counts/durations, not content. No `llm/response/raw` artifacts exist under the run workspace.

**Therefore: NOT CONFIRMED whether the LLM emitted wrong information vs. the parser/post-processing changed it.** The only observable artifacts are the parsed `test-plan.json` and `code-generation-ir.json`, which already contain the wrong/ambiguous semantics.

---

## 8. Parser Audit

- **Test plan parsing:** `TestDesignAgent._extract_json` (`:102`) + manual field mapping (`:554–658`). No default `expected_result` is injected — `expected_result` is taken verbatim as `_safe_str(meta.get("expected_result", ""))`. So the ambiguous `expected_result` string is the LLM's, **not** a parser default.
- **Enum coercion:** `_coerce_enum` (`:49`) only affects `priority`/`category`/`risk_level`, not `expected_result` or `test_data`.
- **IR parsing:** `IRGenerationAgent._parse_ir_response` (`:427`) + `_normalize_ir_data` (`:644`) + `SchemaAwareRepairer`. These fill missing optional keys and normalize ids, but do **not** alter `expected_value`/`value` semantics.

**Verdict:** the parser does **not** introduce the wrong expectation; it faithfully carries the LLM's ambiguous/conditional `expected_result` and invented test data.

---

## 9. Test Plan Audit

The persisted `test-plan.json` (and the fully-approved `approved-test-plan.json`) already contain the wrong semantics:

| Field | TC-016 (Case Sensitivity) | TC-017 (Special Chars) |
|---|---|---|
| expected_result | "either accepts only exact case or is case-insensitive" | "authenticated if password is correct" |
| required_test_data | uppercase_username, lowercase_username, mixed_case_username, valid_password | valid_username, special_char_password |
| test_steps | Enter uppercase → valid password → submit → repeat lowercase/mixed | valid username → special-char password → submit |

**Comparison matrix (Test Plan → IR → Generated TS):**

| Field | Test Plan | IR | Generated TS | Changed? | Stage |
|---|---|---|---|---|---|
| TC-016 expected outcome | ambiguous | `toHaveURL('/dashboard')` (success) | `expect(page).toHaveURL(dashboard)` | ❌ disambiguated wrong | IR |
| TC-016 username value | placeholder `uppercase_username` | literal `"VALID_USER"` / `"valid_user"` | `fill('VALID_USER')` / `fill('valid_user')` | ❌ invented concrete value | IR |
| TC-017 expected outcome | conditional | `toHaveURL('/dashboard')` (success) | `expect(page).toHaveURL(dashboard)` | ❌ disambiguated wrong | IR |
| TC-017 password value | placeholder `special_char_password` | `$SPECIAL_CHAR_PASSWORD` | `process.env.SPECIAL_CHAR_PASSWORD \|\| ''` → empty | ❌ invented + env mismatch | IR + TemplateEngine |

---

## 10. IR Audit

`code-generation-ir.json` (TC-016, TC-017) already encodes:
- `assertion_type: "toHaveURL"`, `expected_value: "https://rrf-portal.dfstage.space/dashboard"` for both tests.
- `value: "VALID_USER"` and `"valid_user"` (literals) for TC-016.
- `value: "$SPECIAL_CHAR_PASSWORD"` for TC-017.
- `environment.variables` invented: `VALID_USERNAME: "valid_user"`, `SPECIAL_CHAR_PASSWORD: "P@ssw0rd!#"`, `MAX_LENGTH_USERNAME: "a"`, `EXCEED_MAX_USERNAME: "a"`, etc.

**Verdict:** the IR is the stage where the ambiguous test-plan expectation is concretized into a **wrong** success assertion. IR generation is a **contributing root cause** (it disambiguated the ambiguity incorrectly), but it inherited the ambiguity from Test Design.

---

## 11. Code Generation Audit

`CodeGenerationAgent.execute` (`app/agents/code_generation_agent.py:82`) delegates to `IRGenerationAgent` (LLM) then `TemplateEngine` (deterministic). The `expect(page).toHaveURL('/dashboard')` is generated by:

- **Function:** `TemplateEngine._generate_assertion_code` (`app/generators/template_engine.py:1026`, specifically `:1038–1041` for `HAS_URL`).
- **Source of value:** `assertion.expected_value` from the IR — i.e., the **IR LLM** produced the `toHaveURL(dashboard)` assertion, not the TemplateEngine and not a hardcoded rule.

The fill values come from `_generate_action_code` (`:979`):
- `"$SPECIAL_CHAR_PASSWORD"` → `process.env.SPECIAL_CHAR_PASSWORD || ''` (`:1000–1002`).
- `"VALID_USER"` (literal) → `'VALID_USER'` (`:1003`).

**Verdict:** Code Generation / Template Engine is a faithful renderer of the IR. It is **not** the primary root cause, but `_generate_env_file` (`:386`) is a **secondary deterministic bug** (see §12).

---

## 12. Test Data Audit

| Value | Source | File | Agent | LLM? | Env var? | Hardcoded? | Evidence? |
|---|---|---|---|---|---|---|---|
| `VALID_USERNAME` | real credential | `_generate_env_file` (`template_engine.py:418`) → `hm001` | TemplateEngine | No | yes | no | ✅ CredentialStore |
| `VALID_PASSWORD` | real credential | `_generate_env_file:419` → `hm123` | TemplateEngine | No | yes | no | ✅ CredentialStore |
| `INVALID_USERNAME` / `INVALID_PASSWORD` | hardcoded `invalid_user_xyz` / `wrong_password_xyz` | `_generate_env_file:420–421` | TemplateEngine | No | yes | **yes** | ❌ invented |
| `SPECIAL_CHAR_PASSWORD` | **invented** `P@ssw0rd!#` in IR; `.env` writes `SPECIAL_CHARS_PASSWORD` | IR `:27` + `.env:448` | IR LLM | **Yes** | name mismatch | no | ❌ invented |
| `MAX_LENGTH_USERNAME` | IR says `"a"`; `.env` writes real `hm001` | IR `:23` + `.env:430` | IR LLM / TemplateEngine | Mixed | yes | no | ❌ contradictory |
| `EXCEED_MAX_USERNAME` | IR ref `$EXCEED_MAX_USERNAME`; **not in `.env`** | IR `:25` | IR LLM | Yes | missing | no | ❌ undefined |
| `SQL_INJECTION_PAYLOAD` | IR ref; `.env` writes `SQL_INJECTION_PASSWORD` | IR `:25` + `.env:435` | IR LLM / TemplateEngine | Yes | name mismatch | no | ❌ undefined |
| `XSS_PAYLOAD` | IR ref; `.env` writes `XSS_PAYLOAD_USERNAME/PASSWORD` | IR `:26` + `.env:436–437` | IR LLM / TemplateEngine | Yes | name mismatch | no | ❌ undefined |
| `"VALID_USER"` / `"valid_user"` (literals) | IR fill values | IR TC-016 | IR LLM | Yes | no (literal) | yes | ❌ invented |
| `/dashboard` | IR `dashboard` page `url_pattern` | IR `:166` | IR LLM | Yes | no | no | ⚠️ crawler saw `/dashboard` but not a login→dashboard transition |

**Key facts:**
- `SPECIAL_CHAR_PASSWORD` is **not** known to be a valid password — it was invented by the IR LLM (`P@ssw0rd!#`), and the `.env` never defines that exact name.
- `"User"`/`"VALID_USER"` is **not** the real username (`hm001`); `VALID_USER` is the IR LLM's invented uppercase of its invented `valid_user` username.

**The `.env` variable-name mismatch is a deterministic bug:** the IR references `$SPECIAL_CHAR_PASSWORD`, `$SQL_INJECTION_PAYLOAD`, `$XSS_PAYLOAD`, `$EXCEED_MAX_USERNAME`, but `_generate_env_file` writes `SPECIAL_CHARS_PASSWORD`, `SQL_INJECTION_PASSWORD`, `XSS_PAYLOAD_PASSWORD`, and nothing for `EXCEED_MAX_USERNAME`. Every such `process.env.X || ''` therefore resolves to an empty string.

---

## 13. Template Engine Audit

The Template Engine (`app/generators/template_engine.py`) is **deterministic and faithful** to the IR:

- `$VAR` → `process.env.VAR || ''` (`:1000–1002`) ✅ correct mapping of the IR's variable reference.
- literal → quoted string (`:1003`) ✅.
- `toHaveURL` → `expect(page).toHaveURL(...)` (`:1038–1041`) ✅.
- `toHaveURL` with empty `expected_value` is **correctly skipped** as a TODO (`:1039–1040`) — but the IR supplied a non-empty (wrong) value, so this guard did not fire.

The only TemplateEngine defect relevant to these tests is `_generate_env_file` (`:386–463`), which:
1. Hardcodes its own set of env var names that do **not** match the IR's `environment.variables` (it never reads `ir.environment.variables`).
2. Produces the `SPECIAL_CHARS_PASSWORD` vs `SPECIAL_CHAR_PASSWORD` (and `SQL_INJECTION_*`/`XSS_PAYLOAD_*`) name mismatch.

---

## 14. Playwright Execution Audit

`PlaywrightRunner` (`app/execution/playwright_runner.py`) runs `npx playwright test` via `node .../cli.js` in a subprocess, with a JSON reporter, and parses `results.json`.

Observed results (`execution-artifacts/failure-analysis/failure-analysis.json`):
- Both tests failed with `expect(page).toHaveURL(expected) failed`.
- Failure analyzer **misclassified** them as `timeout` and marked them `flaky` (the analyzer maps URL-mismatch failures to "timeout" — a separate classification bug, not the test-generation bug).

**Playwright executed the generated instructions exactly as written.** The submitted values were wrong (invented username / empty password), so the app remained on `/login`, and the `toHaveURL('/dashboard')` assertion failed.

**Verdict: Playwright is NOT the root cause.**

---

## 15. Cross-Test Analysis

The same bug class (negative/edge/validation inputs incorrectly asserting a **successful dashboard redirect**) appears across the generated module, confirming a **systemic** generation problem:

| Test | Scenario semantics | Data | Expected result | Assertion | Verdict |
|---|---|---|---|---|---|
| Successful Login | correct | `VALID_USERNAME`/`VALID_PASSWORD` (real) | redirect dashboard | `toHaveURL(dashboard)` | ✅ plausible (but unverified: crawler never saw a login form) |
| Empty Username+Password | correct | clear | error visible | `usernameError`/`passwordError` visible | ✅ plausible |
| Empty Username Only | correct | clear | error visible | `usernameError` visible | ✅ plausible |
| Empty Password Only | correct | clear | error visible | `passwordError` visible | ✅ plausible |
| Invalid Username | correct | `INVALID_USERNAME` | auth error | `authError` visible | ✅ plausible |
| Invalid Password | correct | `INVALID_PASSWORD` | auth error | `authError` visible | ✅ plausible |
| Invalid Username+Password | correct | both invalid | auth error | `authError` visible | ✅ plausible |
| Max Length Username | ambiguous | `MAX_LENGTH_USERNAME` (=real `hm001`) | "dashboard if valid OR error if invalid" | `toHaveURL(dashboard)` | ❌ disambiguated wrong |
| Exceed Max Username | correct | `EXCEED_MAX_USERNAME` (undefined → empty) | "too long" error | `usernameError` visible | ⚠️ wrong data (empty, not overlong) |
| SQL Injection (user/pass) | correct | `SQL_INJECTION_PAYLOAD` (undefined → empty) | reject/sanitize | `authError` visible | ⚠️ wrong data |
| XSS (user/pass) | correct | `XSS_PAYLOAD` (undefined → empty) | reject/escape | `authError` visible | ⚠️ wrong data |
| Session Persistence | correct | real | persist session | `toHaveURL(dashboard)` + TODO refresh | ⚠️ TODO placeholder |
| **Case Sensitivity** | ambiguous | `VALID_USER`/`valid_user` (wrong) | "either/or" | `toHaveURL(dashboard)` ×2 | ❌ **root-cause exemplar** |
| **Special Chars Password** | conditional | `SPECIAL_CHAR_PASSWORD` (undefined → empty) | "if correct" | `toHaveURL(dashboard)` | ❌ **root-cause exemplar** |

Pattern: **any scenario whose expected result is conditional or ambiguous gets converted into an unconditional success (`toHaveURL(dashboard)`)**; and any scenario that uses an edge/security input relies on env vars whose names don't exist or whose values are invented.

This is a **systemic generation problem**, not one isolated test.

---

## 16. Root Cause Matrix

| Stage | File | Verdict | Evidence |
|---|---|---|---|
| User requirement | prompt | ✅ | "Test the login page only" |
| Crawler | `crawler_agent.py` / `crawl-package.json` | ⚠️ missing evidence | 1 page `/dashboard`, 0 forms |
| Inventory | `inventory.json` | ⚠️ missing evidence | no login form/elements |
| LLM input (Test Design) | `test_design_agent.py:403` | ⚠️ insufficient/contradictory context | no auth structure + "≥8 scenarios" demand |
| LLM response (Test Design) | (not persisted) | ❌ ambiguous/invented | `test-plan.json` shows ambiguous expected_result + invented data |
| Parser | `test_design_agent.py:102` | ✅ faithful | no semantic rewriting |
| Test Plan | `test-plan.json` | ❌ ambiguous/non-assertable | TC-016/TC-017 expected_result |
| IR | `code-generation-ir.json` | ❌ disambiguated wrong + invented values | `toHaveURL(dashboard)`, `VALID_USER`, `$SPECIAL_CHAR_PASSWORD` |
| Template Engine | `template_engine.py` | ⚠️ faithful render + env-name bug | `_generate_env_file` name mismatch |
| Playwright | `playwright_runner.py` | ✅ executed correctly | `expect(page).toHaveURL(expected) failed` |

---

## 17. Model vs Prompt vs Agent Analysis

### Is the model itself the problem?
**PARTIALLY.** The model (`mistral-medium-3-5`) hallucinated a complete login page, test data, and expected results from a near-empty inventory, and resolved conditional outcomes as unconditional success. A stronger model might do better, **but**:

### Would a model change fix it?
**No — not reliably.** The model is being asked an **under-constrained question**. The inventory had no authentication evidence (0 forms). No amount of model intelligence can correctly know the real app's case-sensitivity or special-character behavior when that behavior was never observed and never described. The failure is upstream (missing context) and downstream (no semantic validation).

### Would a prompt change fix it?
**Partially.** A prompt could instruct the model to (a) never emit ambiguous/conditional `expected_result`, (b) only use `$VAR` references for test data, (c) not invent pages/elements, and (d) mark un-evidenced scenarios as `pending`/`requires_review`. This would reduce, but not eliminate, the fabrication because the **evidence is fundamentally absent** from the crawler.

### Would code changes be required?
**Yes.** The deterministic Template Engine `_generate_env_file` name mismatch is a code bug; and there is **no semantic validation layer** between Test Design → IR → Code Generation to reject ambiguous expected results or invented test data. A generic semantic validation step (assertion ground-truth check) would be the robust fix.

---

## 18. Definitive Root Cause

### ROOT CAUSE:
**Missing authentication evidence in the inventory combined with no semantic validation of LLM-generated expectations.**

### FILE:
- `app/agents/test_design_agent.py` (produces the ambiguous/invented test plan)
- `app/agents/ir_generation_agent.py` (concretizes ambiguity into a wrong success assertion)
- `app/generators/template_engine.py` (`_generate_env_file` — env-var name mismatch)

### FUNCTION:
- `TestDesignAgent._generate_test_plan` (`test_design_agent.py:249`)
- `IRGenerationAgent._generate_ir` / `_complete_and_parse_ir` (`ir_generation_agent.py:133` / `:275`)
- `TemplateEngine._generate_env_file` (`template_engine.py:386`)

### EVIDENCE (before → after):

**Before (correct user intent):**
```
User prompt: "Test the login page only" + credentials (hm001 / hm123)
base_url: https://rrf-portal.dfstage.space/login
```

**After (incorrect expectation):**
```
test-plan.json TC-016 expected_result:
  "System behaves consistently with case sensitivity rules
   (either accepts only exact case or is case-insensitive)"
→ code-generation-ir.json TC-016:
  fill "VALID_USER" / "valid_user"  +  toHaveURL(".../dashboard")   [unconditional success]
→ auth-module.spec.ts:
  await loginPage.usernameInput.fill('VALID_USER');
  await expect(page).toHaveURL('https://rrf-portal.dfstage.space/dashboard');
```

### WHY:
1. The crawler only observed `/dashboard` (0 forms, 0 links) — it never observed the login form, so the inventory contained **no authentication structure**.
2. The Test Design Agent, prompted to produce "≥8 scenarios per page/module" and "≥15 for auth", **fabricated** the login page, its fields, error messages, and 17 scenarios — with ambiguous expected results ("either … or …", "authenticated if correct") and invented placeholder test data.
3. The IR Agent resolved those ambiguities as **unconditional success** and invented concrete values (`VALID_USER`, `$SPECIAL_CHAR_PASSWORD`).
4. The deterministic Template Engine rendered the IR faithfully, but wrote `.env` variables under different names (`SPECIAL_CHARS_PASSWORD`), so `process.env.SPECIAL_CHAR_PASSWORD` is `undefined` → empty password.

### DOWNSTREAM EFFECT:
Both generated tests assert `toHaveURL('/dashboard')`; the real app stays on `/login` (wrong/invalid/empty credentials), so Playwright correctly fails both assertions. The failure analyzer then mislabels them as "timeout/flaky".

### CONFIDENCE:
**HIGH** — verified against the actual persisted artifacts (`test-plan.json`, `code-generation-ir.json`, `auth-module.spec.ts`, `.env`, `failure-analysis.json`) for run `0a1cc8a5`.

---

## 19. Recommended Fix Location (no implementation)

1. **Crawler/inventory** — the crawler never captured the login form (it landed directly on `/dashboard`). The auth evidence gap originates here.
2. **Test Design prompt** — must forbid conditional/ambiguous `expected_result` and invented test data; mark un-evidenced scenarios `requires_review`.
3. **IR generation** — must not disambiguate conditional expectations into unconditional success; should propagate "unknown outcome" rather than default to success.
4. **Template Engine `_generate_env_file`** — must consume `ir.environment.variables` (not a hardcoded list) so `$VAR` references match the `.env` names.
5. **Add a semantic validation layer** — before code generation, reject/flag any assertion whose expected value cannot be grounded in inventory/crawler evidence.

---

## 20. Evidence / File References

All paths relative to `project-foundation/backend/storage/runs/0a1cc8a5-e35a-4828-8e07-ac19d8a3001d/`:

| Artifact | Path | Key content |
|---|---|---|
| User prompt + model | `../../metadata/0a1cc8a5-….json` | "Test the login page only", model `mistral-medium-3-5`, base_url `/login` |
| Crawl package | `contracts/crawl-package.json` | 1 page `/dashboard`, 0 links, 0 forms |
| Inventory | `contracts/inventory.json` | 1 page, 0 forms, 1 input, 6 buttons |
| Test plan | `contracts/test-plan.json` | TC-016/TC-017 ambiguous expected_result + invented data |
| Approved plan | `contracts/approved-test-plan.json` | all 17 scenarios `approved` |
| IR | `artifacts/ir/code-generation-ir.json` | `toHaveURL(dashboard)`, `VALID_USER`, `$SPECIAL_CHAR_PASSWORD` |
| Generated spec | `artifacts/generated-tests/playwright/tests/auth-module.spec.ts` | `fill('VALID_USER')`, `process.env.SPECIAL_CHAR_PASSWORD \|\| ''`, `expect(page).toHaveURL(dashboard)` |
| Generated env | `artifacts/generated-tests/playwright/.env` | `SPECIAL_CHARS_PASSWORD=hm123!#$` (name mismatch) |
| Failure analysis | `artifacts/generated-tests/execution-artifacts/failure-analysis/failure-analysis.json` | both tests `expect(page).toHaveURL(expected) failed` |

Source files:
- `app/agents/test_design_agent.py` — `_generate_test_plan` (`:249`), `_complete_and_parse_json` (`:207`)
- `app/agents/ir_generation_agent.py` — `_generate_ir` (`:133`), `_complete_and_parse_ir` (`:275`), `_parse_ir_response` (`:427`)
- `app/generators/template_engine.py` — `_generate_env_file` (`:386`), `_generate_action_code` (`:979`), `_generate_assertion_code` (`:1026`)
- `app/core/ir/prompt_composer.py`, `app/core/ir/instruction_builder.py` — IR prompt construction
- `app/execution/playwright_runner.py` — execution (correct)

---

## Final Verdict (one-line answers)

- **Is the model itself the problem?** PARTIALLY (it hallucinated from missing evidence).
- **Is Test Design generation the problem?** YES (primary — ambiguous/invented expectations).
- **Is LLM input/context the problem?** YES (co-equal primary — no authentication evidence was supplied).
- **Is LLM response parsing the problem?** NO.
- **Is IR generation the problem?** YES (secondary — disambiguated ambiguity into wrong success assertion).
- **Is Code Generation the problem?** NO (faithful renderer).
- **Is TemplateEngine the problem?** PARTIALLY (deterministic env-var name mismatch, not the semantic error).
- **Is Test Data generation/resolution the problem?** YES (secondary — invented values + env-var mismatch).
- **Is Playwright execution the problem?** NO.
- **Is the application under test the problem?** NO.
