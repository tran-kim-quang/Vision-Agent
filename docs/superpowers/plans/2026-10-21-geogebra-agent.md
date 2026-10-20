# Geometry Agent and Embedded GeoGebra Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Execution method remains subject to user selection.

**Goal:** Turn text geometry and explicit-function requests into inspectable constructions displayed directly in an embedded GeoGebra app inside the existing chat.

**Architecture:** A geometry agent proposes a typed construction, and a deterministic compiler validates dependencies and emits bounded GeoGebra commands. A dedicated SSE event carries the full artifact to React; a single lazy-loaded applet executes it, preserves edits between figure switches and reports runtime errors. GeoGebra owns mathematical construction and rendering; command success does not establish correct interpretation or prove a goal.

**Tech Stack:** Existing Python 3.11/3.12, Pydantic 2, FastAPI, LangChain 0.3.24 / LangChain Core 0.3.56, LangGraph 0.3.33 / supervisor 0.0.16, Ollama model factory, React 18, Vite 6, GeoGebra Apps API. Python `unittest`, Node's built-in test runner, Playwright for browser checks.

**Spec:** [Approved design](../specs/2026-10-21-geogebra-agent-design.md), approved 2026-10-21.

## Global Constraints

- First-release limits: 100 construction steps, 500 characters and depth 32 per expression, and 64 KiB UTF-8 for the full artifact.
- Allow at most two corrected tool submissions following validation errors within a request. Enforce this in code, not only a prompt.
- The tool reports `invalid_spec`, `needs_clarification`, `unsupported` or `prepared`.
- Choose `graphing` for explicit 2D function requests and `3d` for spatial geometry or surfaces.
- Explicit problem coordinates are accepted as givens; illustrative choices are separate; goals never become assumed input constraints.
- Use `appletOnLoad`, one active applet, lazy script loading, session-local edit restoration and explicit disposal.
- Retain existing `/geometry/*` and `/geo3d/` routes as legacy behavior. No CAS-only commands, general constraint solver or theorem prover in this release.
- No model-provided HTML, JavaScript, script URLs or raw GeoGebra commands. No Python or JavaScript expression evaluation.
- New backend units must be importable/testable without vision-model initialization or model credentials. Preserve research/vision behavior.
- No deployment, purchase, persistent document store or server-side GeoGebra service in this implementation.

## Review Focus

1. React StrictMode mounts and stale applet callbacks: obsolete instances never execute commands (Task 5).
2. Transport interruption after an artifact but before `done`: the figure remains associated with its turn exactly once (Task 6).
3. Unicode descriptions and multibyte text: artifact limits count UTF-8 bytes, while display text remains escaped and readable (Tasks 1 and 6).
4. Concurrent browser sessions and follow-up turns: retry counters, artifacts and deduplication never leak across requests (Tasks 3 and 4).
5. A script blocked once or a figure switched during asynchronous state export: retry works and the latest selection wins (Task 5).

## Files and Environment

Create the isolated execution workspace using the worktree skill at implementation time. Do not create another worktree if the harness already provides isolation. This plan and the approved spec must travel with the implementation checkout.

The inspected host has Python 3.10 and 3.14 only; neither matches `pyproject.toml` (`^3.11,<3.13`). Use an available project environment with 3.11/3.12, or a Python 3.11 container; do not relax the project's Python range. `Dockerfile.backend` already uses Python 3.11. Node 24 is installed; the frontend Dockerfile uses Node 20, so verify that browser-test dependency versions support that runtime before installing them. Never print `.env` or credential values.

File ownership:

| Files | Responsibility |
| --- | --- |
| `geometry3d/geogebra/{__init__,schema,expressions,validation,compiler}.py` | Typed spec, expression parser, dependency checks, deterministic commands |
| `tools/geometry/{__init__,construction_tool}.py` | Model-facing preparation tool |
| `agents/geometry_agent.py`, `agents/supervisor_agent.py` | Bounded geometry graph and routing |
| `geometry3d/geogebra/streaming.py`, `api.py` | Artifact extraction and complete SSE emission |
| `frontend/src/geometry/{loader,runtime,chatState}.js` | Script lifecycle, applet adapter, turn association |
| `frontend/src/geometry/{GeoGebraViewer,GeometryArtifactCard}.jsx` | Viewer and extracted-assumption UI |
| `frontend/src/App.jsx`, `frontend/src/App.css` | Chat integration and layout |
| `tests/test_geogebra_*.py`, `tests/fixtures/geogebra/*.json` | Offline validation, graph, stream tests and shared fixtures |
| `frontend/tests/geometry-*.test.js`, `frontend/e2e/geometry-*.spec.js` | Node helpers and mocked/real browser acceptance |
| `frontend/playwright.config.js`, `frontend/package*.json`, `README.md` | Browser test setup and product instructions |

## Task 1: Typed Spec, Restricted Expressions and Dependency Validation

**Files:** Create `geometry3d/geogebra/__init__.py`, `schema.py`, `expressions.py`, `validation.py`; `tests/test_geogebra_schema.py`, `tests/test_geogebra_expressions.py`; fixtures `tetrahedron.json`, `projection.json`, `function2d.json`, `surface.json`, `undefined-intersection.json` under `tests/fixtures/geogebra/`.

**Interfaces:**
- `ConstructionSpec`: `version: Literal[1]`, bounded `title: str`, `app: Literal['graphing','3d']`, `givens: list[Given]`, `goals: list[str]`, `display_choices: list[str]`, `steps: list[Step]`.
- `Given`: `text: str`, `source_text: str`; both are displayed as extracted, not independently verified.
- `Step`: discriminated union on `op`, with `id: str` and typed operation arguments. Operations: `point(coords)`, `segment(a,b)`, `line(a,b)`, `polygon(points)`, `plane(points)`, `midpoint(a,b)`, `intersection(a,b)`, `projection(point,target)`, `function2d(expression,domain)`, `surface_explicit(expression,x_domain,y_domain)`.
- Points have three finite numeric coordinates; geometry operations require app `3d`. Functions accept declared `x`; surfaces accept `x,y`. Finite domains are ordered pairs with start strictly less than end. Function2d may also appear in mixed `3d` scenes; surfaces require `3d`.
- `parse_expression(text: str, variables: frozenset[str]) -> ExpressionNode`; `emit_expression(node: ExpressionNode, rename: dict[str,str] | None = None) -> str`.
- `validate_spec(raw: dict) -> ValidatedConstruction` returning the parsed spec plus stable topologically ordered steps. Errors use `SpecError(code: str, step_id: str | None, message: str)`.

- [ ] Write failing unittest cases `test_accepts_tetrahedron_fixture`, `test_rejects_duplicate_and_reserved_ids`, `test_sorts_dependencies_stably`, `test_rejects_cycle_missing_reference_and_wrong_kind`, `test_rejects_nonfinite_numbers_and_reversed_domains`, `test_limits_100_steps_500_chars_and_depth_32`. Assert a 101st step fails, a valid 100-step fixture passes, and booleans are not accepted as coordinates.
- [ ] Write expression tests rejecting `x;Delete(A)`, assignment, `__import__('os')`, attributes, indexing, undeclared variables, overlong/deep trees and nonfinite constants. Assert both `x^2-y^2` and `x**2-y**2` normalize identically; constant names are restricted to `pi,e`; `log` is natural logarithm. Store unambiguous operator precedence in the emitted fully parenthesized expression.
- [ ] Run `python -m unittest discover -s tests -p 'test_geogebra_*.py' -v` in Python 3.11/3.12; expected initial failure is missing new package/interfaces.
- [ ] Implement the models with forbidden extra fields and independent default collections. Restrict identifiers to `[A-Za-z][A-Za-z0-9_]{0,31}`; reserve `x,y,z,u,v,e,pi`, supported function/operation names and a compiler-helper prefix. Use a small restricted expression tree built from Python `ast` after token-aware normalization of `^`; never evaluate it. Use source/AST bounds before recursive processing, then stable topological sorting and operation-specific type checks. Allow intersection only line-line, line-plane or plane-plane; cardinality/type is statically selected by the input kinds, with coincident/parallel/skew results deferred to runtime.
- [ ] Run the tests again; expected all new tests PASS, plus `python tests/test_geometry3d.py` PASS. Commit only the named files: `feat: validate typed GeoGebra construction specs`.

## Task 2: Deterministic Commands and Model-Facing Tool

**Files:** Create `geometry3d/geogebra/compiler.py`, `tools/geometry/__init__.py`, `tools/geometry/construction_tool.py`, `tests/test_geogebra_compiler.py`, `tests/test_geogebra_tool.py`.

**Interfaces:**
- `CommandStep`: `source_step_id: str`, `commands: list[str]`, `expected_labels: list[str]`.
- `GeometryArtifact`: UUID `id`, `version: Literal[1]`, `app`, `title`, `givens`, `goals`, `display_choices`, `steps: list[CommandStep]`, `spec: ConstructionSpec`.
- `PreparationResult`: discriminated status plus either `artifact: GeometryArtifact`, or structured `issues: list[Issue]` with `code,step_id,message`.
- `compile_construction(validated: ValidatedConstruction) -> GeometryArtifact`; `prepare_geometry(spec: dict, unresolved_issues: list[str] | None = None) -> dict` is the LangChain tool exported as `prepare_geometry_tool`. Its schema accepts a JSON object so invalid model proposals can be reported as structured tool results rather than escaping graph control flow. `unresolved_issues` is a bounded list of at most 10 strings, 500 characters each; it is part of the tool input, not `ConstructionSpec`.

- [ ] Add failing tests `test_midpoint_depends_on_source_points`, `test_goals_never_compile_to_constraints`, `test_surface_renames_variables_to_u_v`, `test_projection_emits_supported_perpendicular_construction`, `test_rejects_oversized_utf8_artifact`, `test_tool_returns_structured_errors`. A title containing Vietnamese must survive round-trip JSON; build a >65,536-byte multibyte artifact and assert rejection using UTF-8 bytes, not Python character count.
- [ ] Run the Task 1 command and confirm failures point to missing compiler/tool behavior.
- [ ] Compile points, Segment, Line, Polygon, Plane, Midpoint and typed Intersect operations from validated values only. Project to a line using `ClosestPoint(line,point)`; project to a plane by a compiler-owned helper `PerpendicularLine(point,plane)` followed by `Intersect(helper,plane)`. Reserve helper names deterministically. For functions use bounded `Function(expression,start,end)`; for surfaces use `Surface(u,v,expression[x->u,y->v],u,xmin,xmax,v,ymin,ymax)`. Rename through the expression tree, never textual substring replacement. Emit the spec's natural `log` as GeoGebra `ln` explicitly and test that mapping. Expected labels cover intermediate helpers as well as outputs. Verify these mappings in Task 7's real app, not only string tests.
- [ ] Return `unsupported` for known out-of-scope operations, `needs_clarification` when `unresolved_issues` is nonempty, and `invalid_spec` for malformed proposals. Reject oversized/malformed unresolved-issues inputs; do not guess intent merely from a validation error. Measure final serialized artifact size against 64 KiB. UUIDs are generated in Python, not supplied by the model. No wrapper status may claim browser execution.
- [ ] Rerun new and legacy tests; expected PASS. Commit: `feat: compile validated constructions for GeoGebra`.

## Task 3: Geometry Agent and Supervisor Routing

**Files:** Create `agents/geometry_agent.py`, `tests/test_geogebra_agent.py`; modify `agents/supervisor_agent.py`; add `langchain-ollama==0.3.0` to `requirements.txt` if still absent to match the existing factory and `pyproject.toml`.

**Interfaces:**
- `build_geometry_agent(model=None)` returns a compiled graph named `geometry_agent` compatible with the existing supervisor. Import the model factory lazily when no test model is injected.
- State includes `messages` with the existing message reducer, `geometry_request_id: str`, `geometry_attempts: int`. API supplies a fresh `configurable.geometry_request_id` each request (Task 4).
- Agent executes only `prepare_geometry`; successful results appear in a normal `ToolMessage` with exact tool name `prepare_geometry` and JSON `PreparationResult` content.

- [ ] Add fake-model tests for valid tool invocation, invalid-then-corrected invocation and `test_third_failed_submission_ends_without_fourth_call`. Assert attempts are reset for a new request ID, isolated between simultaneous invocations and counted per tool call even when multiple calls appear in one model response. Malformed arguments and unknown tools return bounded errors, not an uncaught exception or unlimited retry. Verify all tool-call IDs receive matching responses.
- [ ] Run `python -m unittest discover -s tests -p 'test_geogebra_agent.py' -v`; expected FAIL until graph exists. Use fake models; no live model calls or heavyweight supervisor import in these unit tests.
- [ ] Implement a small StateGraph with model and controlled tool-execution nodes. Bind the one preparation tool, run tool calls sequentially, enforce an initial attempt plus at most two corrections, and stop after preparation or a clarification/unsupported result. Reset counters from request metadata before execution; never store per-request counters in a global tool object. Use only APIs compatible with pinned LangGraph 0.3.33; do not solve compatibility by upgrading the agent stack.
- [ ] Prompt the model to extract source-backed givens, list illustrative choices and separate goals/optional solution. It must not claim a figure was executed or a goal verified. Register the geometry graph in `build_supervisor()` and update routing for geometry/functions while retaining research/vision routes. Test registration with injected/mocked graphs and models.
- [ ] Run all new unit tests and the legacy kernel tests. Commit: `feat: route geometry requests to a bounded construction agent`.

## Task 4: Complete Artifact Streaming

**Files:** Create `geometry3d/geogebra/streaming.py`, `tests/test_geogebra_streaming.py`; modify `api.py` around `event_stream` and the ordinary tool-result branch.

**Interfaces:**
- `artifact_event(tool_name: str, content: str, tool_call_id: str, session_id: str, request_id: str, seen: set[str]) -> dict | None` handles only exact tool name `prepare_geometry` and prepared results.
- SSE shape: `{type:'geometry_artifact', session_id, request_id, artifact}`. The request ID is generated by the server before graph execution and passed as `configurable.geometry_request_id`. A `request_start` event exposes it to the frontend before other request events; ordinary legacy events remain accepted.

- [ ] Write tests showing a >1,000-character artifact arrives intact, repeated tool results emit once, separate requests do not share `seen`, invalid/fabricated envelopes emit no artifact, and unsuccessful preparation emits ordinary activity only. Revalidate the typed spec and ensure compiled commands match the result before streaming executable data; malformed payloads produce bounded activity errors and the stream continues.
- [ ] Add an async integration-style test of `event_stream` using a fake supervisor that emits ToolMessages, tokens and an exception; stub model startup/import boundaries. Assert `request_start` precedes artifacts, configurable ID matches, an artifact survives a subsequent stream error, and `done` still occurs. Assert research tool-result truncation remains unchanged.
- [ ] Run `python -m unittest discover -s tests -p 'test_geogebra_streaming.py' -v`; expected FAIL for missing event behavior.
- [ ] Implement validation/deduplication in the pure helper and wire it before the 1,000-character activity snippet is produced. Keep complete artifacts out of token/Markdown parsing. Use graph tool-call IDs as the per-request deduplication key; server-generated artifact IDs are stable for repeated emissions of the same prepared result.
- [ ] Rerun tests; expected PASS without real model credentials. Commit: `feat: stream complete geometry artifacts separately from activity text`.

## Task 5: GeoGebra Loader, Runtime and Viewer Lifecycle

**Files:** Create `frontend/src/geometry/loader.js`, `runtime.js`, `GeoGebraViewer.jsx`, `frontend/tests/geometry-runtime.test.js`, `frontend/e2e/geometry-viewer.spec.js`, `frontend/playwright.config.js`; modify `frontend/package.json` and lockfile for browser-test dev dependencies and scripts.

**Interfaces:**
- `loadGeoGebra({document,timeoutMs=20000}={}) -> Promise<GGBAppletConstructor>`: singleton in-flight load of the official `https://www.geogebra.org/apps/deployggb.js`; failed load clears the singleton so retry works.
- `executeArtifact(api, artifact, {isCurrent}) -> Promise<void>` checks epoch, each command's result and expected labels via `exists`/`isDefined`; a failure identifies source step and stops subsequent execution.
- `GeoGebraViewer({artifact,stateCache,onClose})` receives a session-local `Map<artifactId, xmlString>` owned by App; applet state exports/imports use the documented XML API (`getXML`/`setXML`) to make capture synchronous before disposal. Save user-edited state, not just initial commands. After restoring XML, verify expected labels are defined before entering ready; an invalid snapshot can be discarded explicitly and the original construction rebuilt.
- Workspace owns a monotonically increasing selection epoch; callbacks may mutate state only for the current epoch. Applet IDs and DOM container IDs are unique per instance. Script/readiness timeout is 20 seconds each; retry creates a fresh applet. Synchronous snapshot capture avoids asynchronous export races; applet initialization and import callbacks still require epoch guards.

- [ ] Write Node tests with injected document/API fakes for singleton loading, load failure then retry, readiness gating, stop-on-failure, expected-label checks and stale callback suppression. Use `node --test tests/geometry-*.test.js` from `frontend` (no DOM dependency required for pure helpers).
- [ ] Set up Playwright against the Vite dev server and add mocked-app tests `strict_mode_never_executes_stale_applet`, `rapid_switch_latest_selection_wins`, `switch_restores_edited_state`, `new_chat_removes_applet`, `blocked_script_can_retry`. Mock only the external loader script and applet API; exercise the actual React component. Add `test:unit`, `test:e2e` and `test:e2e:real` scripts; resolve a Playwright version compatible with Node 20 and retain it in the lockfile. Install the browser through the documented Playwright installer during execution.
- [ ] Run the new tests; expected FAIL until runtime and component exist.
- [ ] Implement loader, bounded execution and viewer states `closed/loading/executing/ready/error`. Keep snapshots by artifact ID in workspace memory, reset on New chat, and remove API/listeners on close, switch or unmount. Disable arbitrary initial GeoGebra JavaScript from restored state; restore only snapshots created by this app's running instance. Use lifecycle epochs to neutralize StrictMode mount/cleanup races, including constructor creation before readiness. No hidden second applet is retained for prior cards.
- [ ] Add a retry button and escaped text fallback with construction steps. Never render error/title/given strings as HTML. Run unit tests, mocked browser tests and `npm run build`; expected PASS. Commit: `feat: add lazy embedded GeoGebra viewer with safe lifecycle`.

## Task 6: Artifact Cards and Robust Chat Association

**Files:** Create `frontend/src/geometry/chatState.js`, `GeometryArtifactCard.jsx`, `frontend/tests/geometry-chat.test.js`, `frontend/e2e/geometry-chat.spec.js`; modify `frontend/src/App.jsx`, `frontend/src/App.css`.

**Interfaces:**
- Chat assistant entries gain `id`, `requestId`, `artifacts: GeometryArtifact[]`, `text` and optional stream-error metadata.
- `createGeometryTurn(sessionId: str) -> turn` and `reduceGeometryTurn(turn,event) -> turn` are pure JS helpers. Turn state tracks session/request IDs, artifacts deduplicated by ID and a finalized flag; legacy text/activity remains in the current UI.
- `<GeometryArtifactCard artifact={artifact} onOpen={selectArtifact}/>` displays givens, source text, illustrative choices, goals and construction summary. The App owns `selectedArtifactId` and mounts one viewer workspace.

- [ ] Write tests for artifact plus final text, artifact without final text, repeated artifact and `done`, event from an old session, and explicit finalization in fetch `finally` after disconnect. Assert no duplicated assistant entry, no lost artifact, and a figure already received remains visible after an error. Include UTF-8 artifact text with literal `<img onerror=...>` and assert it is text, not an element.
- [ ] Mock SSE in Playwright: split frames across network chunks and close the connection after an artifact before `done`; also send two requests in a session and then New chat. Assert correct turn association, latest workspace selection and stale-stream suppression. Retain unread final SSE buffer handling so an EOF without trailing newline does not discard a complete event.
- [ ] Run frontend tests and confirm failures point to missing artifact association/card behavior.
- [ ] Handle `request_start` and `geometry_artifact` before generic activity events. Keep request-local synchronous accumulators and a single idempotent turn finalizer used by `done`, network EOF and error/finally. Associate complete artifacts with their assistant entry independently of supervisor text. Ignore late results using a session/request generation guard; abort the prior request on New chat. Add geometry agent activity metadata without changing research/vision display.
- [ ] Integrate cards, one expandable workspace, loading/errors and responsive sizing. Display user-facing states in Vietnamese and avoid proof/verification badges. Existing ordinary chat must not load GeoGebra. Run frontend suites and production build; expected PASS. Commit: `feat: display geometry artifacts in chat without losing streamed results`.

## Task 7: Real GeoGebra Acceptance and Documentation

**Files:** Create `frontend/e2e/geometry-real.spec.js`; update shared fixture JSON only if compiler corrections are required; modify `README.md`. Add a small fixture-export helper to tests if needed so browser tests consume actual compiler output rather than hand-maintained command copies.

**Interfaces:** Real browser tests accept serialized artifacts produced by `compile_construction` from the Task 1 fixtures. Use mocked `/api/stream` solely to remove model nondeterminism; keep the actual GeoGebra script, engine and React integration.

- [ ] Write browser tests asserting coordinates for midpoint M of `(0,0,0)` and `(4,0,0)` equal `(2,0,0)` within `1e-8`; projection of `(1,2,3)` to `z=0` equals `(1,2,0)`; a line through `(1,2,3)` and `(1,2,-1)` meets that plane at `(1,2,0)`. Parallel disjoint inputs must show a runtime failure, not ready. All coordinate assertions read the real applet API.
- [ ] Add `sin(x)` on `[-6,6]` and `x^2-y^2` on `[-3,3] x [-3,3]` examples; assert expected app, defined objects and visible graphics in screenshots. Verify interactive rotation/zoom and editable input manually where automation cannot establish visual behavior. A CAS-only command failure must lead to a supported compiler mapping, not silent mode switching.
- [ ] Execute the real-browser suite on a recorded browser/device. Record cold first-open duration, warm opening, parameter-update latency and frame responsiveness separately, without imposing an unmeasured performance target. If CDN access or browser provisioning prevents the check, report that limitation explicitly and do not label real-engine acceptance passed.
- [ ] Update README with new request examples, `GEOMETRY_MODEL_NAME`, local/backend/frontend commands, exact test commands, artifact lifetime and error semantics. State that legacy Three.js routes remain separate. Link official embedding/API/license references without inventing commercial prices or promising automatic proof correctness.
- [ ] Run `python -m unittest discover -s tests -p 'test_geogebra_*.py' -v`, `python tests/test_geometry3d.py`, `npm run test:unit`, `npm run test:e2e`, `npm run test:e2e:real`, `npm run build`, and `git diff --check` in their appropriate directories. Review actual output; only claim checks that ran. Avoid generated `frontend/dist` changes unless the repository explicitly requires them; scope commits to source/docs/test files. Commit: `test: verify real GeoGebra constructions and document integration`.

## Plan Self-Review and Handoff

- Spec mapping: schema/expressions/limits -> Tasks 1-2; agent and correction cap -> Task 3; untruncated transport -> Task 4; viewer lifecycle -> Task 5; artifact persistence within chat and turn association -> Task 6; real-engine verification/docs -> Task 7.
- Review Focus coverage: all five failure modes above have named tests in their owning tasks.
- Interfaces are defined before use. `prepared` is a backend state; only frontend execution yields `ready`; neither means a proved goal.
- Native inline execution is recommended because the tasks share the spec/artifact/stream interfaces and do not need independent implementation branches. The user may select subagent-driven execution instead.
- Next action: the user reviews this written plan and selects the execution method. No product implementation or dependency installation has been performed by writing this plan.

Reference commands and APIs must be checked against their official documentation during implementation: [embedding](https://geogebra.github.io/docs/reference/en/GeoGebra_Apps_Embedding/), [Apps API](https://geogebra.github.io/docs/reference/en/GeoGebra_Apps_API/), [Surface](https://geogebra.github.io/docs/manual/en/commands/Surface/), [ClosestPoint](https://geogebra.github.io/docs/manual/en/commands/ClosestPoint/), [Intersect](https://geogebra.github.io/docs/manual/en/commands/Intersect/).
