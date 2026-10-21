# Geometry agent and embedded GeoGebra

Date: 2026-10-21
Status: approved by the user on 2026-10-21; ready for implementation planning.

## Intent and agreed decisions

The user wants natural-language geometry and function-plotting requests to produce interactive mathematical constructions. They selected direct GeoGebra embedding because a language model can make mathematical mistakes. GeoGebra performs supported constructions, calculation and rendering; the agent extracts the request and proposes a structured construction rather than supplying authoritative solved coordinates or executable JavaScript.

Selected flow:

`request -> supervisor -> geometry_agent -> typed construction spec -> validation and command compiler -> dedicated SSE artifact -> embedded GeoGebra`

The UI exposes extracted givens, construction steps and illustrative choices for comparison with the request. Successful command execution means the construction is defined, not that the model interpreted the problem correctly or proved a theorem. Optional natural-language solutions are separate from construction data and are not described as verified.

Assumptions: use the existing React chat, Python backend and Ollama model factory; retain existing session behavior; load GeoGebra from its official distribution. Deployment purpose and commercial licensing eligibility have not been established. This document authorizes no purchase or external publication.

## Current repository

- `agents/supervisor_agent.py` routes to research and vision agents only.
- `utils/llm.py` creates the Ollama chat models.
- `api.py` streams agent messages and truncates ordinary tool results to 1,000 characters. The stream generator already receives a session identifier.
- `frontend/src/App.jsx` owns streamed events and browser-memory chat history. Both development and production proxy `/api/`.
- `geometry3d/kernel.py` builds four fixed shape families and checks coordinates and claims. `static/geo3d/index.html` renders them with Three.js.

The new chat flow uses GeoGebra directly. Existing `/geometry/*` and `/geo3d/` routes remain available as legacy behavior during this change; improving or removing that viewer is separate work. Its validation must not be presented as validation of GeoGebra artifacts.

## Approach considered

1. SymPy plus Three.js: compatible with Python and symbolic computation, but requires maintaining construction and graph rendering behavior.
2. Direct GeoGebra embedding: selected; GeoGebra owns dynamic object dependencies and rendering.
3. GeoGebra plus Three.js: adds synchronization and conversion work without improving mathematical correctness.

## First release scope

Support text requests for points, segments, lines, polygons, planes, midpoint, line/plane intersection, point projection onto a line or plane, and explicit-coordinate solid constructions from points and polygonal faces. Support explicit function plots `y=f(x)` and `z=f(x,y)` over finite display domains. The operation registry maps only combinations supported by the selected GeoGebra app and tested in a real browser.

Choose `graphing` for explicit 2D function requests and `3d` for spatial geometry or surfaces. The choice is fixed per artifact. Standalone geometry and mixed requests use the 3D app initially; no dependence on CAS-only commands is assumed.

Defer general implicit surfaces, arbitrary nonlinear constraint solving, automated theorem proving, persistent shared GeoGebra documents, user accounts and full geometric extraction from images. The existing vision agent may transcribe an image as a separate step, but geometric relations must not be inferred from appearance alone.

Requests outside the registry produce an explicit unsupported or needs-clarification response rather than executing raw model-generated commands.

## Backend responsibilities

### Agent

Add `agents/geometry_agent.py`, register it with the supervisor, and configure its model using `GEOMETRY_MODEL_NAME` with the existing supervisor model as the fallback. Follow the existing model factory and agent conventions; validate compatibility with the pinned LangChain and LangGraph versions during implementation.

The agent uses a `prepare_geometry` tool accepting a typed spec. It identifies givens, constructions, goals and display choices separately. Prompt instructions forbid treating a requested conclusion as an input constraint, silently adding special conditions, or claiming frontend execution has already succeeded.

Allow at most two corrected tool submissions following validation errors within a request. If still invalid, return a concise explanation. Applet execution errors are reported in the UI; a retry requiring the agent occurs on an explicit user retry or follow-up, not an automatic model loop.

### Construction contract

Proposed package: `geometry3d/geogebra/`, separate from the legacy kernel.

- `schema.py`: versioned, discriminated operation types and bounded numeric/expression values.
- `compiler.py`: operation registry and deterministic GeoGebra command generation.
- `validation.py`: reference checking, dependency ordering, expression and resource limits.
- `tools/geometry/construction_tool.py`: exposes validation and compilation to the agent and returns the artifact.

A spec contains `version`, `title`, `app`, `givens`, `goals`, `display_choices` and `steps`. Each step has an identifier, a typed operation and named arguments. A given includes its source text from the user's request; the UI labels it as extracted information, not independently verified evidence.

Operations declare their output kind, input kinds and dependencies. Initial operations are point, segment, line, polygon, plane-through-three-points, midpoint, supported intersection, supported projection, function2d and surface-explicit. Bodies are represented by constituent points, edges and polygons; no new fixed-shape kernel is necessary. Registry names are application names, not arbitrary GeoGebra syntax.

Identifiers use a conservative ASCII grammar and cannot shadow expression variables, reserved constants or operation names. Labels for display are separate text. Reject duplicate identifiers, missing references, cycles, incompatible input kinds, non-finite numbers and unsupported operations before compilation. Reject operations with variable output cardinality unless a supported explicit selection identifies the intended result.

Mathematical expressions are parsed to a restricted syntax tree: finite numeric literals, declared variables, arithmetic, powers, and an explicit set of elementary functions (`sin`, `cos`, `tan`, `exp`, `log`, `sqrt`, `abs`). Emit normalized syntax from the tree. Do not use Python or JavaScript evaluation. Reject assignment, attributes, indexing, commands, statement separators and undeclared names. Bound expression length and syntax-tree depth.

First-release limits: 100 construction steps, 500 characters and depth 32 per expression, and 64 KiB UTF-8 for the full artifact. Compiler-generated command boundaries cannot be supplied by model arguments. These are initial product limits to be validated against the example corpus, not claims about GeoGebra capacity.

Explicit problem coordinates are accepted as givens. If dimensions are omitted and a representative configuration is appropriate, choices must be separately listed and labelled illustrative. Representative coordinates cannot be selected merely because they satisfy an unproven goal. If producing a construction requires resolving a substantive ambiguity or adding a hypothesis, return needs-clarification instead. No general constraint solver is added in this release.

The tool reports `invalid_spec`, `needs_clarification`, `unsupported` or `prepared`. `prepared` means commands passed server-side checks and still require browser execution.

## Artifact and streaming contract

On successful preparation, return one structured artifact containing an ID, version, app, title, givens, goals, display choices, ordered command steps, expected object labels, and the original typed spec. Command steps carry source step IDs so runtime errors can name the failed construction.

In `api.py`, identify this result by the exact geometry tool name and validated result schema, before applying ordinary result truncation. Emit a `geometry_artifact` SSE event containing the complete bounded artifact, a server-generated artifact ID, session ID and per-stream request ID. Keep an abbreviated ordinary tool activity message for existing activity panels. Never recover executable data from final-answer Markdown or truncated activity text. Deduplicate by tool-call/artifact ID if stream modes repeat the same result.

The artifact travels in the active request stream; no artifact database or new retrieval endpoint is required. React associates it with that request's assistant message, including when the final answer is empty or streaming ends with an error. A valid prepared artifact must remain accessible independently of whether the supervisor produces final text. Session changes discard pending events from the previous session.

Artifacts follow current browser-memory chat persistence: reload clears them. GeoGebra edits are retained while switching between artifacts during the same page session by saving applet state before disposal. Persistent server storage is outside this release.

## Frontend responsibilities

Add a geometry artifact card and a reusable GeoGebra viewer component. Display an extracted-givens summary, display choices and an Open figure action inside the corresponding assistant message. Load the official GeoGebra script once, lazily, when an artifact is first opened. Use the applet API obtained from `appletOnLoad`; no API polling before readiness.

Use one active applet in an expandable workspace associated with the selected card. This avoids mounting a heavyweight application for every chat message. Save an edited applet's state before switching cards, restore it on return, and call the GeoGebra removal API on disposal. Clean up application listeners and stale asynchronous initialization callbacks on unmount or New chat.

Runtime states: closed, loading, executing, ready and error. A script-load or applet-readiness timeout produces an actionable retry state. Execute bounded commands in dependency order, stop on the first failed command, and verify expected labels exist and are defined. Do not label a partially built construction ready. Retry uses a fresh applet to avoid residual objects from failed execution.

Keep a visible distinction between construction prepared, successfully displayed and any mathematical goals. No green proof badge based solely on command success. Show runtime step errors adjacent to the extracted construction. Offer a text view of the construction when GeoGebra cannot load.

Render all titles, error messages and extracted text with React text escaping. The model supplies no HTML, script URL or JavaScript callback. Only the deterministic compiler's commands enter the applet API. Point labels are generated separately from user-facing descriptions. Use supported app configuration and branding; no removal of required attribution.

## Failure behavior and limits of assurance

- Invalid references or expressions: return tool validation errors, allowing bounded agent correction.
- Ambiguous geometry: surface the ambiguity instead of inventing a unique answer.
- Undefined intersection or degenerate construction: stop execution and show the source step.
- CDN unavailable or applet initialization timeout: preserve the artifact and allow retry.
- Interrupted SSE or empty supervisor answer: preserve received artifacts and show the actual stream status.
- Request/session changes: ignore stale initialization and stream results.
- Correct commands for an incorrectly interpreted premise: remain possible; extracted givens and source text are the review mechanism, not an automated guarantee.

## Verification and acceptance

Backend checks must exercise validation and compilation without model credentials or importing heavyweight vision models. Cover dependency failures, duplicate IDs, expression injection, numeric limits, and separating goals from assumptions. Verify complete artifact emission beyond 1,000 characters, stream deduplication, request association and compatibility of ordinary chat events.

Frontend checks cover script loading once, readiness gating, artifact switching/state restoration, cleanup, late callbacks after New chat, failed commands, and artifact-only replies. Run the production Vite build.

Browser acceptance uses the real GeoGebra distribution, not only mocks:

1. A nondegenerate tetrahedron with midpoints on two edges displays the expected objects; parallelism is retained as a goal rather than an input constraint.
2. A point projected to a plane and a unique line-plane intersection are defined and visible.
3. Parallel nonintersecting objects produce a clear runtime failure.
4. `y=sin(x)` displays in the 2D app and `z=x^2-y^2` in the 3D app over explicit finite display domains.
5. An injected statement in an identifier/expression is rejected before execution.
6. Opening only ordinary research chat loads no GeoGebra script; opening multiple figure cards retains only one active applet and restores user edits on return.

Measure first-open time separately from parameter-update latency and frame responsiveness. Report results on the actual browser/device and network; no unmeasured FPS, payload-size or startup-time promises are made.

## Licensing and references

GeoGebra Apps API controls an embedded application; integration documentation does not describe per-`evalCommand` metering. Use of the full GeoGebra product is subject to its licensing terms. Non-commercial eligibility and any commercial agreement must be established for the intended deployment; no price is assumed and self-hosting is not treated as a license exemption.

References reviewed in this conversation on 2026-10-21:

- https://geogebra.github.io/docs/reference/en/GeoGebra_Apps_Embedding/
- https://geogebra.github.io/docs/reference/en/GeoGebra_Apps_API/
- https://www.geogebra.org/license

## Implementation handoff

The user reviewed and approved this written specification on 2026-10-21. Plan schema/compiler and offline tests first, then agent routing and artifact transport, then viewer lifecycle and real-browser acceptance. Review the written implementation plan and select its execution method before implementing product code. This document is a design artifact; product code and dependencies have not been changed as part of drafting it.
