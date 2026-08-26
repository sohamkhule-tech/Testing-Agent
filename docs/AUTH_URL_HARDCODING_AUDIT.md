# Authentication URL Handling — Read-Only Audit

**Scope:** entire `project-foundation` backend authentication/crawler flow.
**Method:** static code audit only. No files were modified, fixed, or refactored.
**Question answered:** does the crawler contain hardcoded/assumption-based authentication URLs that could make login work for one application but fail for others?

---

## 1. Executive Summary

The crawler **does not hardcode any application hostname** (no `swift`, `rrf`, `dfstage`, `workflow-desk`, `resource-requisition`, or similar domain literal exists in the crawler/auth code). The observed `/login → /signin → /sign-in → /auth/login` sequence originates from **one hardcoded list of conventional login path fallbacks** in `CrawlerService._perform_login`.

The real architectural problem is a **form-login assumption**: the crawler

1. assumes every app uses a conventional login path (the 4-path fallback list),
2. assumes credentials-based **form** login (ignores `auth_strategy` for `oauth`/`sso`/`api`/`basic`),
3. detects success via **generic heuristics** (title keywords, structural selectors, a fixed set of cookie names, and a hardcoded score threshold).

These assumptions are generic but *brittle*: an app with a custom login route, a custom session cookie name, a post-login title not in the keyword set, SSO/OAuth redirects, or an MFA challenge will either churn through the fallback URLs or be reported as failed even when login actually succeeded. This fully explains "works for app A, fails for app B."

---

## 2. Hardcoded URL Findings

### 2.1 URLs the crawler actively *generates and navigates to*

| # | Location | Value | Purpose | Generic or app-specific | Can cause wrong login? |
|---|----------|-------|---------|--------------------------|-------------------------|
| 1 | `app/services/crawler_service.py:1543` (inside `CrawlerService._perform_login`) | `["/login", "/signin", "/sign-in", "/auth/login"]` | Fallback login-path candidates appended to `urls_to_try` | **Generic list** (no hostname) | **YES — primary cause of the observed sequence** |

### 2.2 URL *classifiers* (string matching, not navigation)

| # | Location | Value | Purpose | Can cause wrong login? |
|---|----------|-------|---------|-------------------------|
| 2 | `app/services/crawler_service.py:1855-1860` `_is_login_url` | `["/login", "/signin", "/sign-in", "/sign_in", "/auth", "/logon", "login?", "signin?"]` | Decides whether the target URL is a login page (to derive root) | Yes — a custom login route is not recognized → wrong redirect logic |
| 3 | `app/services/crawler_service.py:2060` `_inspect_auth_state` | `("/login", "/auth", "/signin", "/oauth", "/token")` | Filters captured responses into "auth status codes" | Mild — misclassifies auth-related network responses |
| 4 | `app/context/intent_parser.py:235` `_supplement_login_url` | `("/login", "/signin", "/sign-in", "/auth", "login.", "auth.")` | Infers the login URL from any URL in the prompt | Yes — may mis-identify a non-login URL as login |
| 5 | `app/context/intent_parser.py:279` `_extract_url` | same substring list | Excludes login-looking URLs from target selection | Mild |

### 2.3 URLs only in code-generation / templates / tests (NOT crawler auth)

These match `/login`, `/dashboard` etc. but are **not** used by the crawler's authentication flow:

- `app/generators/playwright_project_generator.py:393` — generated test code example (`await page.goto('/login')`).
- `app/generators/template_engine.py:530` — template comment.
- `app/core/prompt_builder.py:341,379` — generated-test-code examples in LLM prompt (`goto('/login')`, `toHaveURL(/\/dashboard/)`).
- `app/core/template_manager.py:748-749` — route map `{"login": "/login", "dashboard": "/dashboard"}`.
- `app/core/ir/instruction_builder.py:220,295,347,401` — example IR fixtures (`"url_pattern": "/login"`, `"target": "/login"`, `/dashboard`).
- `tests/…` — `RRF`, `dashboard`, `/login` used only as test fixtures.

**Conclusion:** no application-specific URL/hostname is hardcoded anywhere in the auth path.

---

## 3. Authentication URL Generation Trace

Where `login_url` actually comes from (proven, in order):

1. **User prompt regex** — `app/services/prompt_builder.py:32`
   `("login_url", r"(?:login\s+url|login\s+page|sign[- ]in\s+url)\s*[:\-=]\s*(https?://\S+)")`
2. **Deterministic fallback inference** — `app/context/intent_parser.py:227-238` `_supplement_login_url`
   If no explicit `login_url`, scans all prompt URLs and assigns the first one whose lowercase form contains `/login`, `/signin`, `/sign-in`, `/auth`, `login.`, or `auth.`.
3. **Credential persistence** — `app/services/prompt_builder.py:493-537` `CredentialStore.save/load`
   `login_url` is encrypted into `run_credentials.enc` (Fernet) and reloaded later.
4. **Workflow fallback to target URL** — `app/workflows/trigger_workflow.py:243-244`
   ```python
   _target_url = (state.request_data or {}).get("target_application", {}).get("base_url") or ""
   _login_url = _loaded_auth.login_url or _target_url or None
   ```
   If the prompt had no login URL, **the app's base URL is treated as the login URL**.
5. **Agent hand-off** — `app/agents/crawler_agent.py:147`
   `login_url=auth_context_dict.get("login_url")` → `self.service._auth_context`.
6. **Consumption** — `app/services/crawler_service.py:1531` `login_url = auth.login_url`.

So `login_url` is either **user-supplied**, **inferred from a URL in the prompt**, or **defaulted to the target URL**. It is never hardcoded. The hardcoded *paths* are the fallback candidates generated from it (Section 2.1 #1).

---

## 4. Exact Trace of `/login → /signin → /sign-in → /auth/login`

All inside `CrawlerService._perform_login` (`app/services/crawler_service.py:1510-1657`).

| Observed step | Producing code | Line | Explanation |
|---|---|---|---|
| 1. Initial URL `https://workflow-desk.dfstage.space/login?next=%2Fworkspace%2FPRJ-044%2Fws-insights` | `login_url = auth.login_url` then `page.goto(attempt_url, …)` | `:1531`, `:1561` | The **configured** login URL (from prompt/store/target fallback). Not hardcoded. |
| 2. Login submission | `_locate_username_field` / `_locate_password_field` / `fill` / `_locate_submit_button` / `_submit_and_wait_for_auth` | `:1581-1603` | Form-based fill+submit. |
| 3. `auth_check` | `_submit_and_wait_for_auth` emits `BROWSER_ACTION {action:"auth_check"}` | `:1968-1974` | Emitted once per candidate that had a username+password form, after signal scoring. |
| 4. `/login` | fallback list `for path in ["/login", "/signin", "/sign-in", "/auth/login"]` → `urljoin(base, path)` | `:1540-1546` | `base = f"{scheme}://{netloc}"` of the configured login URL; `/login` is appended (same path, minus `?next=…`). |
| 5. `/signin` | same list | `:1543` | `urljoin(base, "/signin")`. |
| 6. `/sign-in` | same list | `:1543` | `urljoin(base, "/sign-in")`. |
| 7. `/auth/login` | same list | `:1543` | `urljoin(base, "/auth/login")`. |
| 8. Authentication failure | loop exhausts `urls_to_try`, `login_succeeded` stays False → `return (False, None)` | `:1551-1652` | Emits `STAGE_FAILED` `:1650-1651`; `_crawl_impl` records `AUTH_FAILED` warning and crawls publicly (`:339-346`). |

**Mechanism:** `urls_to_try = [configured_login_url] + [base/login, base/signin, base/sign-in, base/auth/login]`. The `for attempt_url in urls_to_try:` loop (`:1551`) opens a fresh page for each candidate, waits for a password input, and — only if both username and password fields are found — fills and submits. Each submission re-runs the signal scoring. Because the first attempt's `?next=/workspace/…` redirects away (or the signals fail), the loop continues through every conventional path. The final failure reason is whatever the *last* attempt produced.

**Root cause:** the four conventional paths are generated **unconditionally** whenever a login URL is present, regardless of whether the target app actually uses those routes.

---

## 5. Application-Specific Assumptions

**No domain is hardcoded.** The application-specific-looking behavior is entirely **generic-heuristic**:

- Post-login title keywords — `app/services/crawler_service.py:79-82`
  ```python
  _POST_LOGIN_TITLE_KW = {"dashboard", "home", "workspace", "welcome",
                          "overview", "projects", "portal", "app"}
  ```
  (`workspace` notably matches the observed `/workspace/…` app, but the set is generic.)
- Post-login structural selectors — `:85-91`
  ```python
  'nav:visible', '[role="navigation"]:visible',
  'a:has-text("Logout")', 'a:has-text("Log out")', 'a:has-text("Sign out")',
  'button:has-text("Logout")', 'a:has-text("Profile")', 'a:has-text("Account")',
  '[aria-label="User menu"]', '[aria-label="Account"]'
  ```
- Auth cookie-name set — `:2087`
  ```python
  {"session", "connect.sid", "auth", "token", "jwt", "access_token", "JSESSIONID", "PHPSESSID"}
  ```
- Auth error text patterns — `:68-76` (includes `mfa`, `captcha`, `2fa`, `two-factor`, `verify your identity`).
- Local/session storage token keys — `:2039`, `:2049` (`token`, `auth_token`, `access_token`, `jwt`, `id_token`, `user`).

None of these are SWIFT/RRF-specific, but they were clearly tuned against conventional single-page apps and **do not generalize** to apps with non-standard cookie names, non-English or differently-phrased post-login titles, or SSO/MFA flows.

---

## 6. Authentication Success Detection Audit

Success is decided in `CrawlerService._evaluate_auth_signals` (`app/services/crawler_service.py:2065-2175`) with a **weighted score**, threshold at `:1962`:

```python
if score >= 3:
    result["success"] = True
```

| Signal | Method | Line | Hardcoded? |
|---|---|---|---|
| URL changed | `current_url != pre_login_url` | `:2077` | Generic |
| Auth cookie present | `auth_cookie_names` fixed set | `:2087-2093` | **Yes (fixed set)** |
| Storage token | localStorage/sessionStorage key list | `:2039`, `:2049` | **Yes (fixed keys)** |
| 2xx/302 auth status code | captured response status | `:2102-2108` | Generic |
| Set-Cookie present | header presence | `:2111-2113` | Generic |
| Post-login title | `_POST_LOGIN_TITLE_KW` keyword set | `:2119` | **Yes (fixed keywords)** |
| Password field gone | `input[type=password]:visible` count | `:2129` | Generic |
| Post-login UI appeared | `_POST_LOGIN_UI_SELECTORS` | `:2139` | **Yes (fixed selectors)** |
| Auth error text | `_AUTH_ERROR_TEXT_PATTERNS` | `:2157` | **Yes (fixed text)** |
| aria-invalid present | `[aria-invalid="true"]` count | `:2167` | Generic |

**Classification:** success is detected using a mix of **cookies, storage, redirects, network responses, hardcoded text/selectors/titles, and a generic score threshold** — not a single authoritative "authenticated" state.

**Failure mode:** an app whose session cookie is named e.g. `df_session`/`authsid` (not in `:2087`), or whose post-login title is a brand name (not in `:79-82`), can score below 3 despite a successful login → **false negative**. Conversely an app that merely redirects to a URL with a title containing "home" and any cookie named "token" could score ≥ 3 → **false positive**.

---

## 7. OAuth / SSO URL Handling

- `auth_strategy` is defined as `form | api | basic | oauth | sso` (`app/services/prompt_builder.py:81`, `app/schemas/crawler.py:110`, `app/schemas/trigger.py:50`).
- **`_perform_login` never branches on `auth_strategy`.** It always executes the form flow (locate username/password fields + submit). `auth_strategy` is only:
  - carried through `AuthContext.safe_summary` (`:92`),
  - recorded in `SessionInfo.auth_method` (`crawler_service.py:1380`).
- There is **no** OAuth/SSO redirect handling, no `redirect_uri`/`state`/`code` exchange, no IdP navigation, no token callback processing.
- `_derive_root_url` (`crawler_service.py:1863-1874`) only inspects `next`/`redirect`/`return` query params when a login URL looks like a login page — a *root-derivation* helper, not an OAuth flow.

**Conclusion:** OAuth/SSO-protected applications are not supported by the authentication implementation; they will fail. This is a cross-app compatibility gap, not a URL hardcoding bug per se.

---

## 8. MFA / Challenge Handling

- MFA/captcha are only **detected**, never **handled**:
  - `_AUTH_ERROR_TEXT_PATTERNS` includes `"mfa required"`, `"multi-factor authentication"`, `"2fa required"`, `"two-factor authentication"`, `"captcha"`, `"verify your identity"` (`crawler_service.py:74-75`).
  - `_determine_failure_reason` (`:2177-2208`) maps these to `MFA_REQUIRED` / `CAPTCHA_REQUIRED`.
- No OTP entry, no TOTP/WebAuthn, no challenge-response. After classification the flow simply returns failure (`AUTH_FAILED` warning at `:339-346`) and continues crawling publicly.

**Conclusion:** MFA-protected apps are detected as "MFA required" and reported as failed; they cannot complete authentication.

---

## 9. Cross-Application Compatibility Analysis

| Login URL shape | Works? | Why |
|---|---|---|
| `/login` | Yes (typical) | Conventional path; form detected; success via generic signals |
| `/signin` | Yes (typical) | Same |
| `/sign-in` | Yes (typical) | Same |
| `/auth` | **No** | `_is_login_url` classifies it, but `_perform_login` does not *navigate* to `/auth` (it is not in the fallback list `:1543`); only works if the user supplies `/auth` as the explicit `login_url` |
| `/auth/login` | Partial | Present in fallback list (`:1543`); works only if a username+password form is at that path |
| Completely custom route (e.g. `/gateway`, `/idp`, `/portal/session`) | **No** | Not in fallback list; `_is_login_url` won't recognize it; if user supplies it as `login_url` the form flow may still work, but success detection may still false-negative |
| External OAuth/SSO provider | **No** | No SSO flow; form-only (`auth_strategy` ignored) |
| MFA challenge | **No** | Only detected as failure reason; no interactive handling |

**Primary incorrect assumption:** every application has a conventional login route and a conventional form + conventional success signals. For apps that deviate, the crawler churns through `/login`, `/signin`, `/sign-in`, `/auth/login` (the observed sequence) and ultimately reports failure.

---

## 10. Root Causes — Ranked by Severity

1. **CRITICAL — Unconditional conventional-path fallback generation**
   `crawler_service.py:1540-1546` (`_perform_login`). Direct source of `/login → /signin → /sign-in → /auth/login`. Causes wrong-page navigation, wasted attempts, and misleading failure for non-conventional apps.

2. **HIGH — `login_url` defaults to the target app URL**
   `trigger_workflow.py:244`. When no login URL is given, the crawler treats the app base URL as the login page; if that page has no password field, the fallback list takes over.

3. **HIGH — Success detection is heuristic + hardcoded**
   `crawler_service.py:79-91` (title/selector), `:2087` (cookie names), `:2039/:2049` (storage keys), `:1962` (score threshold). False negatives/positives for non-standard apps.

4. **MEDIUM — `auth_strategy` is ignored**
   `_perform_login` always uses the form flow; `oauth`/`sso`/`api`/`basic` are never implemented (`crawler_service.py:1510-1657`).

5. **MEDIUM — Login URL classification is substring-based**
   `crawler_service.py:1855-1860` `_is_login_url`; `intent_parser.py:235,279`. Custom login routes are not recognized, affecting root-derivation and target selection.

6. **LOW — MFA/SSO are detect-only**
   `crawler_service.py:2177-2208` reports `MFA_REQUIRED`/`CAPTCHA_REQUIRED` but cannot proceed.

7. **LOW — `networkidle` wait in auth completion**
   `crawler_service.py:2001` (`_wait_for_auth_completion`). Adds up to 10s latency on SPA/polling apps (recoverable via try/except), contributing to perceived slowness/failure.

---

## 11. Evidence (exact file / function / line)

| Evidence | File:line | Function |
|---|---|---|
| Hardcoded fallback list `["/login", "/signin", "/sign-in", "/auth/login"]` | `app/services/crawler_service.py:1543` | `CrawlerService._perform_login` |
| `urls_to_try = [login_url]` + base derivation | `crawler_service.py:1540-1542` | `_perform_login` |
| `for attempt_url in urls_to_try:` navigation loop | `crawler_service.py:1551` | `_perform_login` |
| `page.goto(attempt_url, wait_until="domcontentloaded", timeout=15000)` | `crawler_service.py:1561` | `_perform_login` |
| `_is_login_url` indicator list | `crawler_service.py:1855-1860` | `CrawlerService._is_login_url` |
| `_derive_root_url` next/redirect/return params | `crawler_service.py:1863-1874` | `CrawlerService._derive_root_url` |
| `auth_check` BROWSER_ACTION emission | `crawler_service.py:1968-1974` | `CrawlerService._submit_and_wait_for_auth` |
| Score threshold `if score >= 3` | `crawler_service.py:1962` | `_submit_and_wait_for_auth` |
| `_POST_LOGIN_TITLE_KW` keyword set | `crawler_service.py:79-82` | module-level constant |
| `_POST_LOGIN_UI_SELECTORS` list | `crawler_service.py:85-91` | module-level constant |
| `_AUTH_ERROR_TEXT_PATTERNS` list | `crawler_service.py:68-76` | module-level constant |
| `auth_cookie_names` fixed set | `crawler_service.py:2087` | `CrawlerService._evaluate_auth_signals` |
| localStorage/sessionStorage token keys | `crawler_service.py:2039`, `:2049` | `CrawlerService._inspect_auth_state` |
| Auth status-code URL filter | `crawler_service.py:2060` | `_inspect_auth_state` |
| `networkidle` wait strategy | `crawler_service.py:2001` | `CrawlerService._wait_for_auth_completion` |
| MFA/captcha → failure reason mapping | `crawler_service.py:2177-2208` | `CrawlerService._determine_failure_reason` |
| login_url regex in prompt parser | `app/services/prompt_builder.py:32` | module-level `_CRED_PATTERNS` |
| `_supplement_login_url` URL inference | `app/context/intent_parser.py:227-238` | `IntentParser._supplement_login_url` |
| `_extract_url` login-URL exclusion | `app/context/intent_parser.py:263-282` | `IntentParser._extract_url` |
| login_url fallback to target URL | `app/workflows/trigger_workflow.py:243-244` | `crawler_node` |
| auth context hand-off to service | `app/agents/crawler_agent.py:147` | `CrawlerAgent._execute_impl` |
| `auth_strategy` field (never branched on) | `app/services/prompt_builder.py:81` | `AuthContext` |
| `auth_method` recorded in session | `crawler_service.py:1380` | `CrawlerService._build_crawl_package` |

---

## 12. Recommended Fix Direction (NO CODE)

1. **Make fallback path generation data-driven, not hardcoded.** Replace the unconditional `["/login", "/signin", "/sign-in", "/auth/login"]` list with logic that only tries a fallback if the app actually exposes it (e.g., only follow links/forms discovered on the page, or derive from the configured login URL, not from an assumed conventional path).
2. **Stop defaulting `login_url` to the target base URL.** If no login URL is supplied, either detect the login route from the page (browser-discovered link/form) or skip authentication explicitly rather than assuming the base URL is a login page.
3. **Make success detection authoritative, not heuristic.** Prefer a single authenticated-state signal (e.g., presence of the app's own session indicator detected from the page, or a configurable cookie name/title/URL pattern per project) over a hardcoded weighted score of generic signals.
4. **Honor `auth_strategy`.** Branch the login flow by strategy and implement (or clearly reject with a distinct reason) `oauth`/`sso`/`basic`/`api`; do not silently run the form flow for non-form strategies.
5. **Parameterize the auth cookie/storage/title heuristics** per project so non-standard apps can be configured, instead of relying on one global fixed set.
6. **Keep MFA/SSO detection as an explicit, surfaced outcome** (already partly present via `MFA_REQUIRED`/`CAPTCHA_REQUIRED`) rather than a generic "login failed".

---

*Audit performed read-only. No implementation, tests, or configuration were changed.*
