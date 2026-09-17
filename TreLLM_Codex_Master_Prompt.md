# TreLLM: master implementation prompt

Paste this entire document into your coding CLI inside the `tre-llm` repository, or ask it to read this file and execute the instructions. The commands specified below are product requirements to implement, not assertions about commands that already exist. This prompt does not depend on a particular CLI slash command.

## 1. Mission and ownership

You are the principal engineer, applied ML lead, product designer, and open-source maintainer responsible for delivering **TreLLM**, repository name **`tre-llm`**, for **Tăng Minh Vũ / tang-vu**.

Build a serious open-source Vietnamese local-AI project that helps people obtain the best verified Vietnamese experience their actual hardware can sustain, from modest CPU laptops to GPU workstations and servers.

Product promise: **“LLM tiếng Việt, vừa sức máy bạn.”**

English positioning: **“Vietnamese AI that fits your machine.”**

The engineering goal is world-class clarity, reliability, reproducibility, and usability. Do not describe the project as world-class, state-of-the-art, the fastest, or the best in public materials without evidence that establishes the claim.

The owner wants you to implement and finish the work autonomously. Deliver working software, actual measurements, usable documentation, and release artifacts. A plan, attractive README, scaffold, or mocked demo is not completion.

Make ordinary engineering decisions yourself. Do not repeatedly ask the owner to choose libraries, colors, directory layouts, implementation order, or test cases. Keep the owner informed with short factual progress updates. Continue through milestones without asking “Should I continue?”

Treat this document as the product specification, within the instructions and permissions of your execution environment. Read applicable `AGENTS.md` instructions before changing code. Preserve unrelated changes and existing repository conventions. Never bypass an approval, authentication requirement, sandbox, or organizational control.

## 2. What TreLLM must contribute

TreLLM has three connected deliverables:

1. **Tre Fit:** hardware discovery, conservative memory planning, bounded calibration, explainable model selection, and graceful recovery.
2. **Tre Viet Lab:** an open Vietnamese behavior evaluation suite, reproducible performance measurements, and an evidence report for each tested configuration.
3. **Tre Adapt:** reproducible Vietnamese data preparation, fine-tuning, evaluation, and export workflows, with a real small-model pilot when available resources permit.

A polished local chat application connects these components. Its purpose is to make the engineering useful and understandable.

The differentiator is the complete loop:

`inspect hardware -> identify compatible artifacts -> estimate fit -> run bounded calibration -> choose a configuration -> complete useful Vietnamese tasks -> measure -> improve with reproducible adaptation`

Build the core logic as an importable library and usable CLI. The UI must consume the same contracts rather than reimplementing selection rules.

### Naming and scientific honesty

`Tiny`, `Lite`, `Core`, and `Pro` are **deployment profiles**, not claims that four proprietary Tre foundation models exist.

An upstream model must retain its real name, organization, revision, license, and artifact provenance in the registry, UI, API reports, and model cards. For example, a Tiny profile may select a verified quantized upstream model; it must not rename that model to “Tre Tiny” and imply original training.

If an actual Vietnamese adapter is trained, identify it explicitly as a TreLLM Vietnamese adaptation of the named base model. Include the base revision, dataset provenance, training configuration, evaluation results, and limitations. A recipe or random-weight test is not a trained model.

Do not train a foundation model from scratch. Do not claim a small model matches frontier reasoning. Do not pretend every task works well on every device. Hardware support and Vietnamese capability are separate facts to establish.

## 3. Autonomy, execution boundaries, and resource budget

You are authorized to inspect the repository and local hardware, research public primary documentation, edit project files, install project-local dependencies, run builds and tests, use existing local model artifacts, and produce local release artifacts.

Use a dedicated virtual environment and project cache. Avoid global package changes, driver changes, OS configuration changes, administrator privileges, and unrelated user directories.

Default development resource policy, unless the owner has already specified another budget:

- No paid APIs, cloud GPU rental, purchased credits, subscriptions, or paid third-party services.
- Never assume a coding subscription includes a free inference API or GPU training capacity.
- Up to 8 GiB of new model-weight downloads in total; reuse verified cached weights first. Track actual and projected totals before starting each download. Respect a smaller local free-space limit.
- Keep at least the greater of 5 GiB or 10% of the workspace filesystem free for temporary files and normal operation. If impossible, reduce the plan and explain the constraint.
- Reserve the greater of 1 GiB or 20% of currently available RAM when planning a runtime, adjusted conservatively for the host. Do not treat this heuristic as a universal guarantee.
- One bounded initial calibration of at most 120 seconds per selected candidate, at most three candidates on the development machine. Stop early if sufficient evidence already selects a useful configuration.
- One fine-tuning pilot of at most 30 minutes of active training by default, with checkpoints and a preflight memory check. A short pilot establishes that the pipeline works; it does not establish production model quality.
- Avoid resource-saturating parallel jobs. Stop or reduce workload on repeated allocation failures or observable unsafe memory pressure. Never kill unrelated processes to make space.

These are limits on heavyweight execution, not permission to stop implementing ordinary code after two minutes. Make them configurable in a documented developer configuration.

Use the current checkout as the project when appropriate. If starting in an empty directory, initialize `tre-llm`. If inside an unrelated repository, create a sibling or isolated working directory without modifying the unrelated project. Inspect Git status before edits and before commits.

Make coherent local commits if Git identity is already configured. Never invent an identity or change global Git configuration. Do not push, publish packages, upload weights, deploy a public service, announce a release, or contact people unless the owner separately authorizes that action. Prepare everything for final review first.

If a dependency, permission, network route, or hardware requirement is unavailable, record the precise failure and continue all independent work. Do not simulate successful access. Do not turn a real-inference failure into a passing release check.

## 4. Begin with evidence, then build

Start by inspecting:

- Existing files, Git state, applicable instructions, and current implementation.
- OS, CPU architecture, instruction support, logical and physical cores where available.
- Total and currently available RAM, process/container memory limits, free disk.
- GPU vendor, model, available VRAM where discoverable, driver/runtime readiness.
- Apple unified memory where relevant; distinguish it from separate CPU RAM plus VRAM.
- Available Python, package manager, Node toolchain, compiler, and inference binaries.
- Existing model caches, restricted to conventional model cache locations or explicitly configured paths. Do not search unrelated personal files.

Research current official documentation and model cards before selecting actual versions or artifacts. Prefer stable releases that support the chosen model. Pin dependencies and runtime versions or commit hashes. Do not select a bleeding-edge architecture merely because its benchmark table looks impressive.

Useful initial primary sources, checked when this brief was written on 2026-09-17:

- llama.cpp: https://github.com/ggml-org/llama.cpp
- Qwen small-model candidate card: https://huggingface.co/Qwen/Qwen3.5-0.8B
- Qwen larger candidate card: https://huggingface.co/Qwen/Qwen3.5-4B
- MLX LM: https://github.com/ml-explore/mlx-lm
- PEFT quantization guide: https://huggingface.co/docs/peft/main/en/developer_guides/quantization
- vLLM official project: https://github.com/vllm-project/vllm

These are starting points, not a requirement to select Qwen or a claim that any particular version is optimal for Vietnamese. Recheck licenses, runtime compatibility, model revisions, chat templates, quantization artifacts, and actual Vietnamese behavior. Use primary publisher sources for other candidates. If a page cannot be accessed, say so in the research record.

Important: upstream executable names and flags evolve. Probe the installed version and help output. Do not assume every build uses the same `llama-server`, `llama serve`, or other command structure. Build a versioned launch adapter for the supported binaries.

Write concise records, then start implementation:

- `docs/product-spec.md`: target users, workflows, non-goals, acceptance gates.
- `docs/architecture.md`: architecture, ownership boundaries, key tradeoffs.
- `docs/research.md`: dated URLs, verified findings, candidate comparison, unknowns.
- `docs/decisions/`: short ADRs only for decisions worth preserving.
- `STATUS.md`: milestone state, completed evidence, failures, next concrete action.

Research must converge. After choosing a technically credible first model and runtime, build a real end-to-end slice before extending the comparison.

## 5. Scope and completion hierarchy

### Required v0.1 product

Deliver all of the following:

1. An installable Python core package and `tre` CLI.
2. Real llama.cpp integration with managed local process mode and attachment to an explicitly configured local compatible server.
3. Hardware inspection, planning, bounded calibration, and persistent configuration.
4. A small, verified model registry covering at least three useful size classes on paper, with actual testing clearly distinguished from documented compatibility.
5. At least one real downloaded or imported model successfully used on the development machine, if model access and resources permit.
6. Vietnamese streaming chat in CLI and a polished local web application.
7. A documented, tested subset of the OpenAI-style chat API for interoperability.
8. Local text-document retrieval with inspectable citations.
9. Reproducible Vietnamese evaluations and performance reports.
10. A functional adaptation pipeline, tiny reproducible training tests, and a real pilot adapter if the machine and budget support it.
11. Installable build artifacts, meaningful CI, bilingual onboarding, and an honest release report.

### Conditional expansion after the required product works

- MLX LM adapter when Apple hardware is available for meaningful validation.
- vLLM attachment and deployment recipe for suitable Linux GPU servers.
- Structured JSON output using a runtime capability that is actually supported.
- One additional genuinely useful backend or optimization only if evidence justifies it.

Do not delay the usable core to build several incomplete adapters. An unimplemented adapter is a roadmap item, not a public API that silently returns fake data. General high-throughput server support may remain documented or experimental until actual hardware testing exists.

### Explicit non-goals for v0.1

No foundation pretraining, autonomous shell execution by the chat model, browser agents, mobile native apps, voice cloning, text-to-speech, image generation, Kubernetes, billing, accounts, multi-tenant SaaS, model marketplace, or mandatory cloud service.

Do not create a separate marketing website before the product works. Do not require Docker, Node.js, a GPU, an API key, or an account merely to run an already-installed CPU release with cached weights.

## 6. Architecture and implementation defaults

Prefer the following unless inspection reveals a concrete reason to change:

- Python 3.11 or 3.12, chosen after checking runtime and dependency compatibility.
- `uv` with a lockfile and standard Python packaging.
- Typer and Rich for CLI, Pydantic for versioned schemas, HTTPX for runtime communication.
- FastAPI for the local API and serving prebuilt UI assets.
- A supervised llama.cpp subprocess for inference, avoiding heavy ML dependencies in the control plane.
- SQLite for local settings, conversations, documents, and result metadata; migrations must be explicit and tested.
- React, TypeScript, and Vite for the UI, with a locked package manager and minimal dependencies.
- Pytest, Ruff, a type checker, frontend component tests where useful, and Playwright for actual user journeys.
- Training dependencies in a separate optional environment or extra. Installing chat must not install PyTorch, bitsandbytes, or the training stack.

A reasonable layout:

```text
src/tre_llm/
  cli/
  hardware/
  planner/
  registry/
  runtimes/
  inference/
  documents/
  evaluation/
  training/
  server/
  storage/
apps/web/
configs/
models/registry/
evals/tre-viet/
recipes/
examples/
tests/
docs/
scripts/
.github/workflows/
```

Keep the number of abstractions proportional to actual needs. Do not create a microservice architecture, generic workflow engine, dependency-injection framework, or plugin marketplace. Prefer clear functions and small typed modules.

Important shared types should include `HardwareSnapshot`, `ModelArtifact`, `RuntimeCapabilities`, `DeploymentPlan`, `CalibrationResult`, `GenerationRequest`, `GenerationEvent`, and `EvaluationReport`.

Use schema versions. Persist timestamps, provenance, and units explicitly. Keep user paths and secrets out of public logs. Human output should be Vietnamese by default; machine-readable JSON and identifiers should remain stable and language independent.

## 7. Tre Fit: hardware planning that earns trust

### Hardware discovery

Build resilient probes with timeouts and structured errors. A missing `nvidia-smi`, unrecognized GPU, or restricted container must not crash CPU discovery. Distinguish:

- Hardware present.
- Runtime/driver available.
- Backend compiled in.
- Model architecture supported.
- Configuration actually tested.

Unknown information stays unknown. Do not report a synthetic zero as a real measurement.

Support Linux, Windows, and macOS at the control-plane level. Handle Windows paths with spaces, Unicode usernames, subprocess cleanup, console encoding, and file locks. Handle container limits. An OS CI job establishes only the tests it runs, not real GPU support.

### Memory planning

Estimate peak demand using artifact size, architecture metadata, runtime buffers, context length, batch size, concurrency, KV or other state caches, offload layout, and a safety margin.

- Parameter count multiplied by bit width is only a rough lower bound.
- A GGUF file size is not total process memory.
- For mixture-of-experts models, active parameters are not resident model weight requirements.
- For hybrid attention or recurrent architectures, use architecture-aware state estimates or a clearly labeled conservative bound. Do not apply a standard-transformer KV formula blindly.
- Do not double-count unified memory or add incompatible RAM and VRAM pools.
- Track prefill peaks separately from steady decoding where possible.
- Check resources again immediately before launch; a cached snapshot can be stale.

Represent estimates as estimates with assumptions and uncertainty. Prefer calibrated measurements when available on the same hardware, model artifact, runtime version, and configuration.

### Selection

Filter by compatibility, license eligibility, available resources, task requirements, and local availability before ranking.

Expose three clear user goals: **Nhẹ máy**, **Cân bằng**, **Ưu tiên chất lượng**. Each picks a feasible point using measured speed, memory, and Vietnamese evaluation evidence. Unknown quality must not become an invented numerical score. Keep a deterministic tie-breaking rule.

Do not always choose the largest model. A smaller model with adequate task quality and much lower latency can be the better recommendation.

Every plan should explain:

- Actual upstream model and quantization.
- Runtime and backend.
- Context, maximum output, concurrency, and offload configuration.
- Expected peak memory and remaining headroom.
- Which values are measured, estimated, or unknown.
- Why this plan was selected and why alternatives were rejected.
- What changes if the user prioritizes speed or quality.

Initial hardware fixtures should cover 4/8/16/32/64 GiB system RAM, representative separate VRAM sizes, unified memory, no GPU, unavailable drivers, and container restrictions. These are synthetic planner scenarios, never advertised as benchmarked physical machines.

Treat 4 GiB total-RAM devices as a constrained experimental target until real tests succeed. On unsuitable machines, return a helpful unsupported plan or a tiny task-limited option instead of promising usable general chat.

### Bounded calibration and recovery

Run a short fixed Vietnamese workload with explicit timeouts and cancellation. Tune only a small search space such as threads, context, and offload. Cache results with a versioned fingerprint and invalidate them when relevant hardware/software/model inputs change.

Never download an entire catalog for calibration. Never estimate time-to-first-token from a token-count proxy and display it as measured latency.

On memory pressure or load failure, stop the owned process cleanly, preserve the conversation, and propose or apply a bounded policy already authorized by the user's selected setup mode:

1. Reduce concurrency and batch size.
2. Reduce context only when it still accommodates the request; disclose any resulting conversation change.
3. Change offload only when it fits both memory pools.
4. Switch to an already-installed smaller compatible artifact when permitted.
5. Otherwise stop with a concrete explanation.

Allow at most two recovery attempts per failed launch/request. Avoid retry loops, repeated downloads, silent truncation, and silent remote fallback. Never change models halfway through a visible answer; discard an incomplete attempt only with clear UI status and restart as a new attempt.

## 8. Registry, downloads, and artifact integrity

Create a small curated registry with real entries, not a list of invented model IDs. Each artifact must record:

- Publisher and upstream model ID; immutable revision.
- Exact file or shard list, expected size, SHA-256 or a verified trusted integrity reference.
- Format, quantization, architecture, tokenizer/chat-template reference, and required auxiliary files.
- Supported runtime versions/backends and evidence status.
- Base license, artifact license, source URL, attribution, and any restrictions relevant to redistribution.
- Recommended starting context/output limits and known Vietnamese capability limitations.
- Whether it is base, instruction-tuned, or a named adaptation.

Prefer publisher or established runtime-maintainer quantizations when verifiable. If converting locally, record the original revision, conversion command, quantizer version, configuration, and output checksums. Do not upload converted weights automatically.

Downloads need progress, retry limits, cancellation, resumable partial files when the server supports them, disk preflight, atomic completion, and integrity verification. Do not assume an HTTP ETag is a SHA-256 hash. An artifact with unknown integrity is not silently promoted to verified status.

Import local GGUF files without copying huge files unnecessarily, but document ownership and handle moved files. Prevent path traversal, symlink escapes in extraction, unsafe archive members, and argument injection. Never execute commands embedded in downloaded metadata. Keep `trust_remote_code` disabled unless a specifically reviewed implementation truly requires it and authorization permits it.

Separate runtime-binary provisioning from model provisioning. Support an explicitly provided executable path. Where tested, offer a pinned, integrity-checked binary acquisition path or documented build path. Do not assume a fresh user already has a correct inference engine installed.

## 9. Inference, session behavior, and API

The runtime interface must support health checks, model load/readiness, generation, streaming, cancellation, token counting when available, unload, and owned-process shutdown. Surface unsupported capabilities explicitly.

Use the actual model chat template. Model-specific thinking controls, stop tokens, generation defaults, and tool/JSON capabilities must be verified. Do not rely on a universal string replacement or prompt suffix to control every model.

Start with one active model and one generation at a time on constrained machines. Implement a bounded queue. Propagate cancellation to inference rather than merely stopping the browser animation. Prevent orphan subprocesses, port conflicts, concurrent model loads, and leaking previous sessions into new ones.

Context handling must count actual tokens where possible, reserve output space, preserve system instructions, and disclose removed messages. Offer an explicit conversation summary with a label that it is a lossy summary. Do not claim unlimited memory or invent facts in a reconstructed history.

Provide and document a deliberately scoped compatibility surface:

- `GET /health`
- `GET /v1/models`
- `POST /v1/chat/completions`, text messages, streaming and non-streaming
- Tre-specific endpoints for hardware, plan, model status, documents, and reports

Test message ordering, UTF-8 Vietnamese content split across network chunks, SSE framing and termination, cancellation, finish reasons, timeouts, request validation, and usage accounting. When exact usage is unavailable, omit it or mark it explicitly as estimated in a documented extension. Do not advertise complete API compatibility or silently accept unsupported tools, images, logprobs, JSON Schema, or other fields.

Bind to loopback by default. Validate Host/Origin, restrict CORS, and protect mutating local endpoints against cross-origin requests. Treat localhost as a boundary requiring care, not automatic authentication. Any optional LAN mode needs deliberate enablement, authentication, and clear configuration. No public listener by default.

## 10. Local document assistance

Implement useful document Q&A for `.txt` and `.md` first, with UTF-8 Vietnamese text. Add text PDF ingestion only if the core is complete and extraction is reliable. Explicitly report scanned PDFs as requiring OCR rather than returning empty “successful” answers.

Use SQLite FTS5/BM25 for a lightweight baseline. Preserve original text for display and citation. Use Unicode-aware normalization for search without destroying accents in original passages; evaluate accentless query recall explicitly. Add optional multilingual embeddings only if their measured benefit justifies extra model downloads and memory.

Requirements:

- User-selected files only; never index the home directory automatically.
- Limits on file sizes, extracted text, and indexing work.
- Stable document and chunk IDs, source path/name, offsets or page numbers, and content hashes.
- Reindex changed files and remove deleted documents and their chunks consistently.
- Keep retrieval chunks within the generation context budget.
- Show clickable source excerpts that actually exist in the indexed document.
- Reject or flag generated citations that reference nonexistent chunks.
- When evidence is missing, say the files do not establish the answer.
- Treat document text as untrusted data, including text that tries to override instructions.

Do not claim that a valid citation proves an answer is correct. Evaluate citation existence separately from factual support. Do not execute tools or shell commands from retrieved documents.

Create original Vietnamese demonstration documents with clear provenance and deterministic expected facts. Include one deliberately unanswerable question and one adversarial instruction inside a document.

## 11. Tre Viet Lab: useful evaluations with honest limits

Build a versioned evaluation package covering everyday Vietnamese behavior that matters to local users:

1. Following precise Vietnamese instructions and output constraints.
2. Accents, Unicode normalization, punctuation, common typing errors, and accentless input.
3. Forms of address, requested formality, and context-dependent pronouns.
4. Faithful summarization that preserves names, dates, numbers, and negation.
5. Structured extraction from Vietnamese text into a specified schema.
6. Source-grounded document Q&A, including missing evidence and false premises.
7. Arithmetic expressed in Vietnamese, currency/date formats, and units.
8. Vietnamese-English mixed technical questions and code explanations.
9. Robustness to prompt injection in quoted or retrieved text.
10. Honest uncertainty and task limits without indiscriminate refusal.

Do not treat regional vocabulary as an error simply because it differs from one preferred dialect. Scope any legal, medical, or current-events examples to supplied source text rather than claiming an authoritative current knowledge benchmark.

Create a compact smoke set first, then a substantive v0.1 suite targeting at least 120 distinct items. Avoid template duplication created merely to reach a count. Separate approximately 60 deterministic/structured checks from approximately 60 rubric-based semantic tasks, adjusting counts if better coverage justifies it. Document the resulting counts.

Each item needs an ID, category, language notes, provenance/license, prompt, expected behavior, grading method, and split. Synthetic items must be labeled synthetic. Automated review is not native-speaker validation. Add a contributor review workflow without blocking delivery on the owner's manual grading.

Use strict checks for objective constraints such as JSON validity, fields, exact extraction, numeric results, citation IDs, and format. Do not pretend a regular expression measures writing quality, semantic faithfulness, or cultural fluency.

For semantic tasks, provide a clear rubric and store raw answers. An optional local LLM judge must be identified with its model/version/settings and labeled automated. Prefer a different sufficiently capable model for judging. If no suitable judge exists, mark those scores ungraded and preserve the outputs for review. Do not grade them with the tested model and report independent validation.

Keep training, development, and held-out evaluation data separate. Split by source/template family before creating paraphrases. Deduplicate exact and near-duplicate content. Do not fine-tune on the held-out suite. Use development results for selection; use the held-out set for the final report. A public regression suite can become contaminated and does not prove broad unseen-language ability.

Investigate one established Vietnamese benchmark using its primary source and exact licensing/protocol. Add an optional fetch-and-run adapter when allowed. Do not copy restricted questions into the repository, invent a dataset ID, or report an adapted subset as an official leaderboard result. If access fails, complete Tre's original suite and explain the limitation.

### Performance measurements

Record model revision, artifact checksum, runtime/build, hardware, context, batch, concurrency, sampling, prompt set, timestamp, and measurement method.

Report separately:

- Process startup and model load time.
- Cold and warm request latency.
- Time to first visible answer token; separate reasoning time when the runtime exposes it.
- Decode tokens/second using the model's tokenizer.
- Visible characters/second as a complementary cross-tokenizer measure.
- End-to-end latency and generated answer length.
- Peak host process memory and device memory where observable, with sampling limitations.
- Errors, cancellations, failed requests, and sample counts.

Use a monotonic clock. Report median/range and repetition counts for small samples. Do not present a meaningful p95 claim from three runs; gather an adequate sample or omit tail statistics. Do not convert wall time to energy usage without actual power measurements.

Compare the same task set and disclose generation budgets, reasoning modes, and configuration differences. Separate performance comparison from quality comparison. Keep failures in the results instead of dropping inconvenient runs.

Produce a JSON evidence bundle plus a human-readable HTML or Markdown report. Public export defaults must remove personal paths, hostnames, hardware serials, secrets, user documents, and conversation content. Never upload a report automatically.

An interactive local tradeoff chart is welcome when it displays actual measurements. Estimated points must be visibly distinct. No invented speed bars, fake leaderboards, or fabricated community results.

## 12. Tre Adapt: real Vietnamese adaptation, reproducibly

Implement a complete optional pathway:

`licensed data -> validation -> normalization -> provenance -> deduplication -> grouped splits -> baseline evaluation -> bounded SFT/LoRA -> checkpoint -> evaluation -> conditional export -> model card`

Start with one compatible small base model. Use stable Transformers/PEFT/TRL or another well-supported stack only after confirming support for that architecture and platform. Choose LoRA or QLoRA based on real hardware; do not require bitsandbytes on platforms where the selected configuration is unsupported.

Provide:

- A data manifest with source URL, revision, license, allowed use, transformations, and hashes.
- Schema validation, language checks with documented limitations, PII filtering, exact/near deduplication, and held-out contamination checks.
- Small original Vietnamese fixture data suitable for testing the pipeline, clearly labeled as fixture data and not a quality training corpus.
- At least one meaningful, reproducible Vietnamese SFT recipe using verified permitted data or user-provided local data.
- Fixed seed, exact tokenizer/chat template, loss masking policy, sequence length, packing policy, train/eval split, optimizer, precision, batch/accumulation, adapter targets, and dependency lock.
- A preflight command that estimates resources and validates all paths before training starts.
- Checkpoint and resume support with safe interrupted-run behavior.
- Loss logging, evaluation, a baseline comparison, and explicit training duration/resource usage.

When a suitable existing GPU or Apple backend and the development budget allow, run a small genuine pilot, save actual adapter weights, and evaluate against the unchanged base under comparable settings. If only CPU is available, a tiny technical training smoke test may verify parameter updates and adapter reload; label it strictly as a pipeline test, not a quality improvement.

If real training cannot run, finish and test the pipeline as far as possible, produce the exact future run command and resource requirements, and record the missing evidence. Do not mark the model-training deliverable complete.

Never generate a huge synthetic corpus by repeatedly calling a paid service, scraping private sources, or consuming the owner's coding subscription as an unapproved training API. Do not assume publicly accessible text is licensed for redistribution or training.

A trained adaptation becomes recommended only if held-out evidence supports its intended improvement and shows no unacceptable regression on defined critical checks. Decide promotion criteria before examining the final holdout. If the pilot is worse, keep the base model as default, report the negative result, and preserve the reproducible experiment.

Export only supported combinations. Validate base-plus-adapter versus merged behavior before quantization, and compare merged versus quantized behavior after conversion using fixed fixtures and the same task suite. Exact token equality need not hold across runtimes; compare appropriate task and numerical outputs. Some architectures or adapters will not export to GGUF without extra work: detect and explain that instead of creating a misleading artifact.

Do not upload weights automatically. Do not put large weights in normal Git history. Produce a model card that attributes the upstream model and states whether the artifact is a pilot, validated adaptation, or unexecuted recipe.

## 13. CLI contract

Implement a coherent minimal command surface. Names below are intended product behavior; you may simplify subcommands if documented consistently.

```bash
tre doctor
tre doctor --json
tre plan --goal balanced
tre setup
tre models list
tre models pull <registry-id>
tre models import /path/to/model.gguf
tre chat
tre serve
tre bench --quick
tre eval --suite tre-viet --split test
tre documents add /path/to/file.md
tre ask "Tài liệu nói thời hạn là ngày nào?"
tre train preflight --recipe recipes/vi-small.yaml
tre train run --recipe recipes/vi-small.yaml
tre report --format html
```

Requirements:

- `tre doctor` is read-only by default and explains actionable fixes.
- `tre plan` can work from registry metadata without downloading weights; it labels uncertainty.
- `tre setup` shows required disk, download size, source/license, expected limits, and selected runtime before acquisition. Support noninteractive execution with explicit flags; do not hang on hidden prompts.
- `tre serve` starts the local application and supported API with cached assets. It must not require a frontend development server for normal users.
- First-run cancellation leaves a resumable, understandable state.
- `--help`, `--version`, exit codes, Ctrl-C, and errors are consistent.
- JSON modes emit valid machine-readable JSON without progress text mixed into stdout.
- Every documented command is either implemented and tested or clearly labeled as a future example outside the quickstart.

Release packaging should support a clean install from a local wheel, then ordinary package distribution after owner approval. Until publishing is authorized, documentation must not imply that `pip install tre-llm` already resolves to this project or that the package name is reserved.

## 14. Product experience and visual direction

Design an application a Vietnamese developer would confidently recommend to a nontechnical friend.

Visual direction: calm, precise, modern. Use bamboo green sparingly, warm neutral surfaces, strong typography with full Vietnamese diacritics, generous spacing, and purposeful density. Support light and dark themes. Avoid generic glowing AI orbs, excessive gradients, huge marketing copy, and decorative dashboards unrelated to user decisions.

Bundle fonts/icons/assets appropriately with verified licenses. No CDN fonts, analytics, tracking pixels, or network-dependent icons. The application must remain usable after the model and runtime are installed and the network is disconnected.

Implement five focused surfaces:

1. **Máy của bạn:** detected hardware, compatibility, recommended profile, short explanation, and expandable details.
2. **Trò chuyện:** reliable streaming, stop/retry, conversation history, copy, export, and clear active model identity.
3. **Tài liệu:** deliberate file import, indexing state, grounded questions, source excerpts, and deletion.
4. **Phòng thử:** actual benchmark/evaluation runs, progress, evidence distinctions, tradeoff comparison, export.
5. **Mô hình & cài đặt:** installed artifacts, disk usage, upstream attribution, download progress, and profile preferences.

The chat screen should be useful before it is impressive. Include relevant Vietnamese example tasks, not a wall of settings. Keep detailed technical information behind an expandable panel unless needed to make a decision.

Create complete loading, empty, offline, download-failure, unsupported-device, model-loading, cancelled, and out-of-memory states. An unconfigured model should show a real setup path, never canned generated text.

Accessibility requirements: keyboard navigation, visible focus, adequate contrast, screen-reader labels, reduced motion, sensible responsive behavior, and reliable IME composition when typing Vietnamese. Pressing Enter while composing text must not prematurely submit a message. Markdown rendering must be sanitized; code and citations must not execute scripts.

Persist conversation data locally with clear deletion/export behavior. No user account or email. No telemetry by default. Explain where data is stored and what outbound connections are needed for initial provisioning. Optional external inference must never be enabled implicitly.

## 15. Demonstration that proves the product

Build an honest 90-to-120-second reproducible demo sequence:

1. Inspect the actual machine and explain the recommendation.
2. Show the real active model, context, and memory plan.
3. Ask a practical Vietnamese question and display measured generation status.
4. Add an original sample document, ask a grounded question, and open the cited excerpt.
5. Ask something absent from the document and show the actual resulting behavior, including a limitation if the model fails.
6. Open a real performance/evaluation report with its evidence status.

Capture actual screenshots or a screen recording if the environment supports it. A script is acceptable if recording tools are absent; record the limitation. Do not replace failed generation with prerecorded “live” output. Do not show results from a stronger external model under a Tiny local label.

Useful examples should include a study-note assistant, Vietnamese structured information extraction, and a small Python client for the supported chat API. Keep sample documents original, modest, and redistributable.

## 16. Security and privacy as implementation properties

Implement protections that correspond to actual product surfaces:

- Safe download/extraction and integrity verification.
- No shell interpolation of user/model/file inputs.
- Controlled subprocess ownership, cleanup, and timeouts.
- Loopback binding, Host/Origin validation, and protected mutating endpoints.
- File size/path limits, sanitized Markdown, and constrained upload/index paths.
- No automatic tool execution by model outputs.
- Explicit model/dataset provenance and separate license treatment.
- Redaction of secrets and personal content in diagnostics and exported reports.
- Local deletion semantics for chats, documents, indexes, and owned cache artifacts.

Do not claim sandboxed code execution, encrypted-at-rest storage, offline behavior, or exhaustive security review unless implemented and tested. Document actual limitations briefly and precisely.

## 17. Testing strategy and release evidence

Test risks and contracts, not private function names or incidental implementation details. Use a fake runtime for deterministic protocol tests, clearly separated from genuine inference evidence.

Meaningful tests must cover:

- Hardware discovery failures and resource-limited environments.
- Planner invariants, incompatible architectures, unified memory, unknown metadata, and no-feasible-plan outcomes.
- Download interruption, resume validation, checksum mismatch, corrupt files, disk exhaustion, and cancellation.
- Runtime startup failure, readiness timeout, process exit, cancellation, and cleanup.
- Unicode/SSE streaming, API validation, context overflow, and queue behavior.
- Document indexing/deletion, accent-aware search, citation integrity, and injected instructions.
- Evaluation split integrity, scoring boundaries, report provenance, and privacy redaction.
- Training data validation, parameter update/reload on a tiny fixture where feasible, and absence of test-set leakage.
- A clean installed-package run outside the source checkout.
- UI setup-to-chat journey, document citation journey, and at least one recoverable error state.

Run a real inference smoke test with a verified small model on the available machine. Store a reproducible command, artifact identity, relevant sanitized output, and result status. Validate that generation actually came from the configured runtime.

If weights cannot be acquired or the host cannot run inference, classify release status as engineering preview with inference blocked. Passing mocks must not turn that status green. Continue packaging and all other useful work.

CI should have a fast offline/unit path, OS coverage for supported control-plane behavior, frontend build checks, packaging checks, and an explicitly separate real-model integration job with controlled downloads. GPU jobs run only on available authorized runners. Unavailable GPU tests are “not run,” not “passed.”

Add dependency/license checks appropriate to the chosen stack, pinned workflow actions where practical, and a release artifact checksum manifest. Do not fabricate coverage badges or CI results.

Stop optional test expansion once the relevant risks and release gates are sufficiently verified. Fix actual failures; do not hide them with broad exception handling or weakened assertions.

## 18. Open-source presentation and contributor experience

Use Apache-2.0 for original project code unless existing repository licensing requires another decision. Keep upstream software, weights, datasets, and fonts under their own licenses and preserve required notices. Do not represent downloadable model weights as covered by the code license.

Include:

- `README.md` in clear English and `README.vi.md` in natural Vietnamese.
- A short value proposition, authentic screenshot, and a quickstart that works from a clean checkout or built artifact.
- An explicit distinction between implemented, tested on this machine, documented upstream support, experimental, and planned.
- A support matrix by OS, runtime, backend, and evidence level.
- Model/data provenance and license documentation.
- `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `CHANGELOG.md`, and a focused roadmap.
- Issue/PR templates that collect useful sanitized diagnostics.
- A contributor path for model registry entries, hardware reports, Vietnamese evaluation cases, and runtime adapters.
- Architecture and troubleshooting documentation with working commands.
- A clear explanation of what TreLLM adds beyond the selected runtime and existing local-model interfaces.

Do not invent maintainers, contributors, contact addresses, sponsors, testimonials, GitHub stars, benchmark wins, package downloads, or release URLs. Do not claim package/model namespaces that have not been checked and obtained. Do not promise a security response time the owner has not accepted.

Community benchmark contribution must be an explicit export-and-submit workflow with a data preview. No hidden uploads.

## 19. Milestones and acceptance gates

Execute in this order. Update `STATUS.md` at each meaningful milestone and after a blocker. A milestone is not permission to stop the whole task.

### M0: Inspect and decide

Inspect the environment, establish constraints, choose one credible runtime/model combination, record product scope and versioned contracts, and create an executable plan.

Gate: decisions are based on current primary documentation and actual local capabilities; no invented dependencies or model artifacts.

### M1: Real vertical slice

Build the package, read-only doctor, minimal registry, verified model import/pull, runtime launch, CLI streaming chat, and shutdown.

Gate: a real Vietnamese request is served by the configured model on the available machine, or a precise external blocker is recorded and the working engineering path is preserved.

### M2: Hardware intelligence

Implement the planner, evidence schema, bounded calibration, explainable profiles, context budgeting, and recovery behavior.

Gate: unsupported/insufficient scenarios fail safely; measured and estimated values remain distinct; selection has meaningful tests.

### M3: Product workflows

Build the local web UI, same-origin API, persistent chat, document import/retrieval/citations, and complete error states.

Gate: setup, chat, stop, document Q&A, source inspection, export, and deletion work through the actual application.

### M4: Vietnamese evaluation and adaptation

Complete the evaluation suite and reports, run real available-model baselines, finish the adaptation workflow, and execute the pilot if feasible.

Gate: data provenance and splits are traceable; objective checks are automated; semantic results identify their grader or remain ungraded; training/export states are truthful.

### M5: Release preparation

Build release artifacts, verify installation outside the checkout, polish documentation/UI, prepare authentic demo evidence, and write the release report.

Gate: the release candidate can be reviewed and reproduced using documented commands, with tested capabilities and remaining limitations clearly separated.

### Required final acceptance table

Produce `docs/release-report.md` with a row for every required v0.1 deliverable and status `passed`, `failed`, `blocked`, or `not run`, plus an evidence path and next action for anything not passed.

The release candidate is ready only if the core install, real inference, planning, CLI/UI chat, API subset, document workflow, evaluations, and packaging gates pass. Adaptation infrastructure may ship with a clearly blocked real-training pilot, but you must not claim the learned-model deliverable is complete. Extra backend support must not be advertised as verified without appropriate evidence.

Do not silently downgrade this specification to a static UI when integration becomes difficult. Resolve what can be resolved and accurately expose genuine external limits.

## 20. Persistence and final handoff

Work in bounded, useful iterations: inspect, implement, exercise, fix, record evidence. Keep changes understandable and avoid unrelated refactors.

After context compression, read `STATUS.md`, the applicable repository instructions, and the latest relevant evidence before continuing. Do not restart completed work or claim previous tests were run again. Keep enough state to resume without requiring the owner to reconstruct the task.

If the execution session must end before completion, write the exact remaining tasks, commands, blockers, and current Git state to `STATUS.md`. Clearly state that work is incomplete. Do not end with a generic offer to continue while more authorized useful work can still be performed in the current session.

At completion, give the owner a concise Vietnamese handoff containing:

1. What actually works now.
2. Exact verified commands to install and run it.
3. Which physical hardware, runtime, model, and quantization were actually tested.
4. A small set of real measurements, with sample counts and limitations.
5. Whether a Vietnamese adapter was actually trained and whether it improved the evaluated tasks.
6. Locations of the release artifacts, report, screenshots/demo, and documentation.
7. Remaining external blockers or unsupported configurations.
8. Any final action requiring owner authorization, with the concrete prepared artifacts to review.

Start now by inspecting the repository and hardware. Then build TreLLM through the milestones. Do not answer with only a proposal.
