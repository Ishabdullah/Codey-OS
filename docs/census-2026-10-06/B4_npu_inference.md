# CENSUS TASK B4 — NPU / accelerator inference: what exists, what is consumable, what a BrainManager boundary would cost

Read-only static inspection, 2026-10-06. No model was loaded, no benchmark was
run, no inference process was started. Every number below was read out of
recorded artifacts in the repos. Nothing in any repo was modified.

**Evidence labels used throughout:**
- `[MEASURED]` — a number or behavior recorded in a repo artifact as the output of an actual run, with the artifact cited.
- `[ARTIFACT]` — a fact read directly out of source/config/binary/header in this inspection (strongest tier: I read the thing itself).
- `[REPO CLAIM]` — the repo's own prose assertion that I did not independently re-derive.
- `[INFERENCE]` — my reasoning. Flagged explicitly; gate nothing on these without confirming.

**Status vocabulary:** IMPLEMENTED / PARTIAL / DORMANT / DOCS-ONLY / MISSING.

---

## TL;DR — the three findings that should drive the blueprint

1. **Neither accelerator build produces a `llama-server` binary — but the server
   source is present and was switched OFF deliberately.** Both build scripts pass
   `-DLLAMA_BUILD_SERVER=OFF` and build only `llama-completion llama-bench
   test-backend-ops`, while `tools/server/` exists in both patched trees. So the
   gap is an **unbuilt CMake target**, not a program nobody has written — a far
   smaller prerequisite than "no server exists." It is still MISSING today, and
   there is still no evidence it builds or runs against either accelerator
   backend. See (b).
2. **Both NPU handoff prototypes hard-reject *every* model Codey-OS actually
   deploys.** Allowlists read from the patches: #5 `QWEN2 || QWEN3`; #7
   `QWEN2 || QWEN3 || (LLAMA && !is_swa_any())`. Deployed default is
   `general.architecture = "qwen35"` (hybrid SSM + attention,
   `llm_arch_is_hybrid() == true`); deployed embed model is
   `general.architecture = "nomic-bert"` with `attention.causal = False`. Neither
   is on either list. Zero deployed models are prototype-eligible.
3. **Only one NPU session is demonstrably usable on this phone** (`_session=1`
   returns `0x200` alone and after session 0). Codey-OS runs up to three
   concurrent `llama-server` processes (8080/8081/8082). At most one role could
   ever be NPU-backed.

---

## (a) What is actually validated

### Reproducibility tiers

I grade in three tiers, deliberately kept separate because flattening them is
the overclaim risk this task warns about.

#### TIER 1 — VALIDATED-AND-REPRODUCIBLE (n=3, rotated order, SD reported)

**One result qualifies: the Mistral-7B NPU-hybrid warm-response advantage.**

`[MEASURED]` `OpenCL-S24-Ultra/reports/2026-10-05/README.md:6-18`

Method (verbatim conditions from `:8`): Mistral-7B-Uncensored Q4_K_M,
2048-token synthetic coding prompt, 128 output tokens (127 decode
evaluations), actual context 2560, F16 KV, FA ON, six CPU threads / core mask
FC, batch 512 / microbatch 256, nice 10, profiling OFF. **Three independent
processes per mode in rotated orders** (CPU/NPU/hybrid, hybrid/CPU/NPU,
NPU/hybrid/CPU). Full NPU uses opt-in 2048 MiB registration window, MBUF 512
MiB, VMEM 3200 MiB. API-confirmed unplugged epoch.

| Mode | PP tok/s (mean ± SD) | TG tok/s (mean ± SD) | Warm response s (mean ± SD) |
|---|---:|---:|---:|
| CPU | 21.51 ± 1.44 | 6.26 ± 0.01 | 116.13 ± 6.09 |
| full-NPU | 333.65 ± 2.44 | 3.79 ± 0.18 | 39.68 ± 1.58 |
| NPU-prefill / CPU-decode | 335.05 ± 4.44 | 5.85 ± 1.44 | 29.17 ± 6.21 |

Hybrid won all three matched rounds: 74.9% shorter mean response than CPU,
26.5% shorter than full NPU. Ranges: hybrid 24.19–36.13s, full NPU
38.54–41.48s, CPU 109.09–119.69s. All nine processes completed with finite
logits, preserved model/cache identity and positions, owned library paths,
clean shutdown. All 128 output tokens agreed (repetitive task).

**The shape of the win, stated precisely.** The NPU is ~15.5x faster at
*prefill* (333–335 vs 21.5 tok/s) and *slower* at *decode* (3.79 full-NPU,
5.85 hybrid vs 6.26 CPU). The entire advantage is prefill. `[INFERENCE]` This
means the benefit scales with prompt length and inversely with output length —
it is a long-prompt/short-answer win, which is a real and common agent shape,
but it is not a general "the NPU is faster" result.

**Three mandatory qualifiers that must travel with the 74.9% number:**

- **First-response only.** `[MEASURED]` `reports/2026-10-05/README.md:123`: the
  handoff is one-way, a second switch call explicitly fails, and "The prototype
  does **not** accelerate the next prompt of a resident multi-turn conversation
  after switching to CPU." Codey-OS is a persistent REPL + daemon with
  multi-turn sessions. The measured win applies to turn 1 of a session and then
  the process is CPU-only for its remaining life.
- **Warm response excludes load and admission.** `[MEASURED]` `:18`: "Warm
  response excludes model loading and admission; these results must not be
  presented as cold application startup." Post-load thermal-admission waits in
  the separate 1.5B screen were 10.0 / 20.0 / 104.1 s (`:167`).
- **Not energy, not sustained, not thermal.** `[MEASURED]` `:16`: "This
  establishes a bounded warm-response benefit, not broad output identity, a
  generic OpenCL GPU advantage, sustained thermal superiority or lower energy."

#### TIER 2 — MEASURED-ONCE (capability validated; speed explicitly disclaimed)

**The NPU installer clean-room reproduction.** `[MEASURED]`
`docs/NPU_VALIDATION.md:43-72`. This tier is *validated-and-reproducible for
capability* and *measured-once for speed*.

Capability results, all passed (`:45-58`): source pin + four patched-file
hashes; 30 new DSP translation units built; 12 ELF artifacts validated as
ARM64 host + Hexagon v75 DSP; sphal driver loaded with all 17 required symbols,
architecture `0x8c75`; **8/8 Q4_K/Q6_K matrix tests passed against a CPU
reference**; **29/29 layers offloaded, HTP0 weights 1023.48 MiB**; 32 tokens
generated, exit 0; idempotent rerun with unchanged binary hashes; runtime
isolation (7 loaded llama/ggml libraries all from the independent build despite
deliberately inherited conflicting paths).

Model: official Qwen2.5-Coder-1.5B-Instruct Q4_K_M, pinned SHA-256
(`npu-upstream.json` → `cc324af070c2ecbfd324a30884d2f951a7ff756aba85cb811a6ec436933bb046`).
Context 512. Allocations at c512 (`:70`): HTP0 KV 14.00 MiB, HTP0 compute
74.94 MiB, CPU model 125.19 MiB, CPU compute 2.00 MiB, CPU output 0.58 MiB.

**Speed from this run must not be quoted as a benchmark.** `[MEASURED]` `:72`,
verbatim: "The 32-token smoke run reported 95.22 tok/s for its six-token
prompt and 29.22 tok/s for 31 decode evaluations. These are **not matched
performance benchmark results** and should not replace the research baselines."

Also in this tier: the Oct-05 partial-NPU-offload screen
(`reports/2026-10-05/README.md:45-59`, single process per point, repo says "no
replicated optimal-offload claim"), the CPU worker-placement screen (`:61-73`),
the separate prefill/decode thread screen (`:75-87`), and the foreground
registration-window profiling (`:32-43`, repo: "These profiled speeds are
diagnostics, not final throughput comparisons").

Notable Tier-2 datum for the registration window `[MEASURED]` `:36-40`:

| Registration window | New maps / decode step | Mapping-call wall % | Eviction-flush wall % | Profiled decode tok/s |
|---|---:|---:|---:|---:|
| 2048 MiB | 11 | 45.5% | 48.6% | 3.69 |
| 3072 MiB | 9 | 40.2% | 54.3% | 4.16 |

`[MEASURED]` `:41` warns these fractions "are not independent pure-overhead
slices and must not be added as an attribution."

#### TIER 3 — n=1, NON-IDENTICAL CONDITIONS (all OpenCL performance)

**OpenCL loses to CPU in every recorded matched comparison.**

`[MEASURED]` `README.md:9-14` — original matched test, 4 threads, 128-token
prompt / 64-token generation: CPU 122.74 vs OpenCL 82.45 tok/s prefill (−32.8%);
CPU 28.72 vs OpenCL 9.50 tok/s generation (−66.9%).

`[MEASURED]` `reports/2026-10-05/README.md:135-147` — the Oct-05 three-test
quota. Qwen2.5-Coder-1.5B-Instruct Q4_K_M, **8192-token** prompt, 128 outputs,
context 8704, six threads, b512/ub256, F16 KV, FA requested ON, profiling OFF,
specialized Adreno kernels OFF. **One process per mode**, OpenCL/hybrid/CPU
order, same unplugged epoch `api-20261005T180328Z-UNPLUGGED`.

| Mode | Prefill tok/s | Decode tok/s | TTFT s | Warm response s |
|---|---:|---:|---:|---:|
| CPU | 66.14 | 11.72 | 123.86 | 134.81 |
| OpenCL | 42.01 | 3.53 | 195.02 | 231.07 |
| OpenCL-prefill / CPU-decode | 34.65 | 2.54 | 236.40 | 286.83 |

OpenCL prefill −36.5%, decode −69.9%, total +71.4% vs CPU. Hybrid +112.8% vs
CPU. `[MEASURED]` `:139`: "No additional repeats were authorized, so standard
deviations and a replicated winner are unavailable." `[MEASURED]` `:165`:
request-start temperatures differed materially (OpenCL 35.8/32.9/27.4 C, hybrid
44.4/40.8/33.3 C, CPU 42.8/40.4/35.1 C) — GPU started *colder* and still lost,
which strengthens the direction of the result but not its magnitude.

**A concrete root-cause lead for the OpenCL loss, read from source**
`[ARTIFACT]` via `reports/2026-10-05/README.md:171-175`: `ggml-opencl.cpp`
classifies Adreno 750 as A7X (lines 295-298), then declines `FLASH_ATTN_EXT`
with F32 queries + F16 KV on A7X (lines 9244-9257). Qwen's FA graph retains F32
queries with F16 KV. So requesting `--flash-attn on` silently runs attention on
CPU even with 29/29 layers offloaded. The guard exists because of an Adreno 740
compiler crash (E031.41); the measured driver reports E031.45.02.26. The repo is
explicit (`:175`) that removing the guard is untested and may crash the driver,
and that the share of runtime attributable to this is unmeasured.

**This matters directly to Codey-OS**: `core/loader_v2.py:698-699` passes
`--flash-attn on` unconditionally. On a hypothetical OpenCL path that flag would
be a silent no-op for attention.

### The virtual-session capability failure — a hard structural ceiling

`[MEASURED]` `reports/2026-10-05/README.md:112-118`. Pinned upstream documents
layer-splitting across virtual sessions on one physical NPU. An isolated v8
helper selected HTP0:0 and HTP0:1. The 1.5B plan failed before model load:
`htp_iface_open` returned `0x200` for `_session=1`. A no-model, zero-graph A/B
probe then opened session 0 alone (succeeded), session 1 alone (failed `0x200`),
and session 0 then session 1 (failed `0x200`). This falsifies an
initialization-order explanation and removes model size, tensor loading and
kernel submission from the failure. Local FastRPC headers name `0x200` as
`AEE_ERPC`, a generic RPC implementation error; the exact vendor/kernel/firmware/
permission restriction is **not identified**. Repo verdict: "Two virtual
sessions are not demonstrated usable on this phone."

### Scorecard against the directive's claims

| Directive claim | Verdict | Grade |
|---|---|---|
| "separately validated Hexagon v75 NPU path" | **TRUE** — clean-room installer reproduction, 8/8 DSP numerical gates, 29/29 offload, generation exit 0 | Validated-and-reproducible for *capability*; measured-once for speed, with the repo's own not-a-benchmark disclaimer |
| "experimental NPU-prefill/CPU-decode work" | **TRUE and stronger than "experimental" implies** — n=3 rotated, SD reported, 74.9% mean response win on Mistral 7B | Validated-and-reproducible, but first-response-only and warm-only |
| OpenCL GPU "experimental" | **TRUE, and the measured sign is negative** — OpenCL loses in every matched comparison | n=1 at 8K; n=3-era original 128-token test also negative |
| "do NOT hard-code NPU as universally superior" | **The repo's own data already enforces this.** NPU decode is *slower* than CPU (3.79/5.85 vs 6.26 tok/s). Full NPU also failed a cold-admission gate after 600s in one screen (`:99`) and produced no result | — |

---

## (b) Consumable artifacts

### THE headline: no `llama-server` binary — because the target is switched OFF

```
$ /usr/bin/find OpenCL-S24-Ultra/.work npu-installer-cleanroom-20261004/.work-npu \
    llama-opencl-build/build -name 'llama-server*' -type f
OpenCL-S24-Ultra/.work/llama.cpp/examples/llama-eval/llama-server-simulator.py
npu-installer-cleanroom-20261004/.work-npu/llama.cpp/examples/llama-eval/llama-server-simulator.py
```

`[ARTIFACT]` Both hits are an upstream Python *simulator* under `examples/`, not
a server binary.

**But the server source IS present, and exclusion is a deliberate installer
choice.** `[ARTIFACT]` `ls OpenCL-S24-Ultra/.work/llama.cpp/tools/server/`:
`CMakeLists.txt`, `main.cpp`, `server-chat.{cpp,h}`, `server-common.{cpp,h}`,
`server-context.{cpp,h}`, `server-cors-proxy.h`, `bench/`, READMEs.

`[ARTIFACT]` `scripts/build.sh:58,60`:
```
-DLLAMA_BUILD_APP=OFF -DLLAMA_BUILD_SERVER=OFF -DLLAMA_BUILD_TESTS=ON
cmake --build "$BUILD_DIR" --target llama-completion llama-bench test-backend-ops -j "$jobs"
```
`[ARTIFACT]` `scripts/build-npu.sh:66,69,72` — identical `-DLLAMA_BUILD_SERVER=OFF`,
plus `--target htp-v75 -j 1` then the same three targets.

**This materially downgrades the prerequisite.** `[INFERENCE]` Getting an
accelerator-backed server is plausibly a build-configuration change
(`-DLLAMA_BUILD_SERVER=ON` + add the target) rather than new software. What it is
*not* yet: evidence that it compiles in these trees, links against
`libggml-hexagon`/`libggml-opencl`, or that the one-way handoff API is reachable
from a multi-slot server. Status stays **MISSING** (nothing built, nothing tried),
but size it as an unbuilt target, not a greenfield program.

What the OpenCL build actually ships
(`OpenCL-S24-Ultra/.work/build/bin/`, 2026-10-02) `[ARTIFACT]`:
`libggml-base.so.0.25.3`, `libggml-cpu.so.0.25.3`, **`libggml-opencl.so.0.25.3`**,
`libggml.so.0.25.3`, `libllama.so.0.5.0`, `libllama-common.so.0.5.0`,
`libllama-bench-impl.so`, `libllama-completion-impl.so`, and three executables:
`llama-bench`, `llama-completion`, `test-backend-ops`.

What the NPU build ships
(`npu-installer-cleanroom-20261004/.work-npu/build/bin/`, 2026-10-03) `[ARTIFACT]`:
identical set but with **`libggml-hexagon.so.0.25.3`** (477424 bytes) in place
of the OpenCL backend. Same three executables. Confirmed by
`README.md:73` for the GPU side: the installer builds "`llama-completion`,
`llama-bench`, and `test-backend-ops`."

`[REPO CLAIM]` `README.md:48`: "The GPU and NPU installers coexist in separate
directories and do not yet provide one validated CPU/GPU/NPU executable."

### Consumability verdict

| Artifact class | Status | Note |
|---|---|---|
| `libggml-hexagon.so` + v75 DSP skel | **IMPLEMENTED** (as a ggml backend) | Real, built, numerically gated. Usable only by a program linked against this `libllama.so`. |
| `libggml-opencl.so` | **IMPLEMENTED** (as a ggml backend) | Built and working; measured slower than CPU. |
| `llama-server` with either backend | **MISSING, but as an unbuilt target** | `tools/server/` present in both trees; both build scripts set `-DLLAMA_BUILD_SERVER=OFF` and omit the target. Never built, never attempted. |
| HTTP/OpenAI-compatible API on an accelerator | **MISSING** | No server built, therefore no API today. |
| Reusable C/C++ library Codey-OS could link | PARTIAL | `libllama.so.0.5.0` exists, but Codey-OS is Python-over-HTTP and has no FFI/binding layer (`CHANGELOG.md:930` records that `llama-cpp-python` was abandoned for a Termux/Android platform limitation). |
| Launcher scripts | **IMPLEMENTED but CLI-only** | `scripts/run-npu.sh`, `scripts/run-model.sh`, `scripts/verify-npu.sh`, `scripts/verify-opencl.sh`, `scripts/benchmark.sh` — all drive `llama-completion`, one-shot, stdout. |
| Hybrid prefill/decode handoff | **PARTIAL / research patch** | Source patch only; one-way; not in any installer default. |
| Anything Codey-OS can call today | **MISSING** | — |

### Patch inventory — all 8 `.patch` files

All eight start from **upstream `ggml-org/llama.cpp` commit
`e358d59178377be4c58ba567925e05faadbccb57`** (`upstream.json`,
`npu-upstream.json`; `tested_date` 2026-10-02 / 2026-10-04) `[ARTIFACT]`.

**Applied by the released installers (2, both in `patches/`):**

| # | File | Lines | Files touched | Applied? |
|---|---|---:|---|---|
| 1 | `patches/llama.cpp-qualcomm-sphal.patch` | 262 | `ggml/src/ggml-opencl/{CMakeLists.txt, cl-program-cache.cpp, ggml-opencl.cpp}` + **new** `opencl-sphal.{cpp,h}` | **YES** — applied by `install.sh`; 5 patched-file SHA-256s pinned in `upstream.json` |
| 2 | `patches/llama.cpp-hexagon-sphal.patch` | 140 | `ggml/src/ggml-hexagon/{CMakeLists.txt, htp-drv.cpp, htp/CMakeLists.txt, htp/cmake-toolchain.cmake}` | **YES** — applied by `install-npu.sh`; 4 patched-file SHA-256s pinned in `npu-upstream.json` |

Purpose of both: Android `sphal` vendor-runtime loading (the private-namespace
path that lets a Termux process `dlopen` `/vendor/lib64` drivers without root),
plus v75 DSP/QAIC toolchain adaptation on the Hexagon side.

**Research snapshots, NOT applied by any installer (6):**

`[REPO CLAIM]` `reports/2026-10-03/patches/README.md`: "preserved for review and
future development, **not automatically applied by the released installer**."
`reports/2026-10-04/patches/README.md`: "**Do not apply them** to the managed
`.work-npu` installation or the original `~/llama.cpp`."

| # | File | Lines | Base | Files touched | Purpose |
|---|---|---:|---|---|---|
| 3 | `reports/2026-10-03/patches/hexagon-sphal-v75.patch` | 140 | generic known-good | same 4 as #2 | Byte-equivalent ancestor of #2; local checkpoint `53d539cc…` |
| 4 | `reports/2026-10-03/patches/opencl-prefill-cpu-decode.patch` | 352 | generic known-good | `include/llama.h`, `src/llama-context.{cpp,h}`, `src/llama-kv-cache.{cpp,h}` | One-way retained-weight/KV migration + CPU-only scheduler prototype |
| 5 | `reports/2026-10-03/patches/npu-prefill-cpu-decode.patch` | 352 | NPU checkpoint `53d539cc…` | same 5 as #4 | **Identical patch bytes to #4** — the repo states the edited context/model files share base content |
| 6 | `reports/2026-10-03/patches/adreno-isolated-instrumentation-and-narrow-launch.patch` | 349 | generic known-good | `ggml/src/ggml-backend.cpp`, `ggml-opencl.cpp`, `opencl-sphal.{cpp,h}`, `tools/llama-bench/llama-bench.cpp` | Opt-in host/op instrumentation + Q4_K wide/narrow launch control. Requires `GGML_OPENCL_Q4K_GEMV_WIDE=0` and an isolated specialized build |
| 7 | `reports/2026-10-04/patches/registration-hybrid.patch` | 509 | NPU checkpoint `53d539cc…` | **9 files**: `include/llama.h`, context/model/model-loader/KV sources+headers, `ggml/src/ggml-hexagon/ggml-hexagon.cpp` | **The one that produced the Tier-1 result.** Retained canonical GGUF weight mappings + one-way KV migration/CPU-only scheduler + arch guard + opt-in idle-weight FastRPC registration window |
| 8 | `reports/2026-10-04/patches/registration-window.patch` | 155 | NPU checkpoint `53d539cc…` | `ggml/src/ggml-hexagon/ggml-hexagon.cpp` only | Window-only alternative. **Mutually exclusive with #7** — repo: "do not apply it together with the combined patch" |

Applicability evidence only: `[REPO CLAIM]` `reports/2026-10-04/patches/README.md`
— "A read-only `git apply --check` passes against the fresh NPU installer's
patched source. Passing that check is not a new clean-room build test." And
`reports/2026-10-03/patches/README.md` — "Passing an apply check does not
establish a standalone build."

### The arch guards — read directly from BOTH handoff patches (decisive)

I opened both, rather than attributing one patch's guard to the other.

**Patch #5, `reports/2026-10-03/patches/npu-prefill-cpu-decode.patch:54`**
(byte-identical to #4, the OpenCL variant), verbatim `[ARTIFACT]`:

```
+    if (!kv || (model.arch != LLM_ARCH_QWEN2 && model.arch != LLM_ARCH_QWEN3)) {
```

Allowlist: `QWEN2 || QWEN3`. Note this is **narrower than #7** — it would not even
accept Mistral (`LLM_ARCH_LLAMA`), which is why #7 added the LLAMA clause.

**Patch #7, `reports/2026-10-04/patches/registration-hybrid.patch:207-212`** —
the patch that produced the Tier-1 Mistral result — verbatim `[ARTIFACT]`:

```
+    if (perf_cpu_only) throw std::runtime_error("hybrid handoff is one-way and already completed");
...
+    const bool supported_arch = model.arch == LLM_ARCH_QWEN2 || model.arch == LLM_ARCH_QWEN3 ||
+            (model.arch == LLM_ARCH_LLAMA && !model.hparams.is_swa_any());
+    if (!kv || !supported_arch) {
+        throw std::runtime_error("hybrid prototype requires supported plain KV without Llama SWA");
```

`LLM_ARCH_QWEN35` is in neither allowlist, and neither is `nomic-bert`. See
section (f) — this disqualifies **both** deployed models, on **both** handoff
patches.

Also read from the same patch: the handoff carries its own admission guards and
can throw at several points — `:292` insufficient MemAvailable for temporary
cache duplication, `:298` CPU KV allocation failed, `:310` KV copy validation
mismatch, `:391` "hybrid mapped shadows require explicit MMAP loading", `:413`
shadow GGUF layout mismatch, `:446` weight-readback admission guard. `[ARTIFACT]`
`:347-350` and `:373-374`: behavior is gated on env var
`GGML_PERF_HYBRID_KEEP_MMAP`.

### Version skew — a concrete prerequisite, not a general risk

`[ARTIFACT]` Three facts that must be read together:

1. Both patch sets pin upstream `e358d59178377be4c58ba567925e05faadbccb57`
   (`upstream.json`, `npu-upstream.json`).
2. Both accelerator builds ship `libllama.so.0.5.0` / `libggml-*.so.0.25.3`
   (build dirs, dated 2026-10-02 / 2026-10-03).
3. `[ARTIFACT]` `~/llama.cpp` HEAD today is `4f540676` ("HIP: use -O0 for host
   code in debug builds (#29795)"), and commit `b5b805a` (2026-10-06) records
   rebuilding it to **0.6.0-dev, build 1372, commit 4f540676**. `utils/config.py:40-49`
   now *prefers* that binary over PATH.

`[INFERENCE]` So the accelerator patch set is pinned behind what Codey-OS
actually runs. Adopting any accelerator path requires one of: (i) pinning
Codey-OS's llama.cpp back to `e358d591`, or (ii) forward-porting up to 8 patches
across a version boundary that has already broken CLI contract once (the
`--mmap` → `--load-mode` change that caused NEW-754). This is a sizing input,
not a caveat.

**Cross-repo ledger item (rule 8 territory).** `[MEASURED]`
`reports/2026-10-05/README.md:127` asserts a preservation audit in which
"Original `~/llama.cpp` was inspected read-only … HEAD and its pre-existing
Vulkan CMake modification remained the same." `[ARTIFACT]` Commit `b5b805a`
(2026-10-06) describes stashing that Vulkan patch, running `git pull`,
rebuilding, and reapplying. **That OpenCL-repo baseline statement is stale as of
2026-10-06.** Worth logging as a finding: the OpenCL repo's preservation audit
now has a known-invalidated premise, and any future audit run against it will
report a spurious mismatch.

---

## (c) Current Codey-OS inference path + exact spawn flags

### Verdict: no backend abstraction exists. CPU `llama-server` is hard-coded.

The only accelerator-shaped token anywhere in Codey-OS source:

```
$ /usr/bin/grep -rniE '\-ngl|n_gpu_layers|n-gpu-layers|opencl|hexagon|\bnpu\b|vulkan|adreno|qnn|htp' \
    --include=*.py --include=*.sh --include=*.json .   # (docs/archive excluded)
./utils/config.py:101:    "n_gpu_layers": 0,
```

`[ARTIFACT]` One line, in a config dict. And it is **dead**: the only other
references are documentation (`docs/configuration.md:44`,
`docs/troubleshooting.md:100`). It is never read by the spawn path. Status:
**DORMANT / dead config** — and its deadness is itself the evidence that no
backend selection mechanism exists.

### The exact spawn command

`[ARTIFACT]` `core/loader_v2.py:676-713` + `:734-748`. Flat `cmd` list, no
device selector, no backend enum, no `-ngl`:

```
<LLAMA_SERVER_BIN>
  -m <model_path>
  --host <SERVER_HOST>            # 127.0.0.1
  --port <port>                   # 8080 primary
  -c <n_ctx>                      # 65536 default (utils/config.py:76-91)
  -t 6                            # MODEL_CONFIG["n_threads"]
  --temp 0.7  --top-p 0.8  --top-k 20  --repeat-penalty 1.1
  --n-predict 2048
  --flash-attn on
  --embedding
  --pooling mean
  --jinja
  --reasoning-format deepseek
  --load-mode <none|mmap|mlock|mmap+mlock>
```

### The NEW-754 spawn contract (commit `b5b805a`, 2026-10-06)

`[ARTIFACT]` The flag that changed, `core/loader_v2.py:727-748`:

```python
# The installed llama-server build replaced the old
# --mmap/--no-mmap/--mlock flags with a single --load-mode
# enum (none|mmap|mlock|mmap+mlock|auto). Map the two
# independent QWEN_MMAP/QWEN_MLOCK booleans onto it. Must be
# passed as two separate argv elements (`--load-mode`, value)
# — `--load-mode=value` is rejected by this build.
```

Mapping: `(mmap=T,mlock=F)→mmap`, `(F,T)→mlock`, `(T,T)→mmap+mlock`,
`(F,F)→none`. Defaults `[ARTIFACT]` `utils/config.py:509-510`: `QWEN_MMAP=True`,
`QWEN_MLOCK=False` → **`--load-mode mmap`** in production.

Binary resolution `[ARTIFACT]` `utils/config.py:40-49`: env `CODEY_LLAMA_SERVER`
→ `~/llama.cpp/build/bin/llama-server` if `os.access(..., X_OK)` → `shutil.which`
→ hardcoded fallback.

Also from this commit: a `--version` diagnostic probe is written to
`core/state/llama-server.log` before every spawn (`:776-792`); the dead
`--reverse-prompt` loop was deleted (`:715-725`) because stop sequences are
enforced per-request via the JSON `"stop"` field in all three inference paths.

`[REPO CLAIM]` Two live open findings from the same commit message: **NEW-757**
(two binaries can still drift; `install_llama_cpp()`'s clone has no version pin)
and **NEW-759** (`repl()`'s one-shot branch is an uncovered 5th model-load call
site). NEW-757 is directly relevant to B4: an unpinned clone is incompatible
with an accelerator path that requires an exact pin.

### Process/lifecycle facts

`[ARTIFACT]` `core/loader_v2.py:799-804` — `Popen` with `preexec_fn=os.setsid`,
stdout/stderr to `core/state/llama-server.log`; `:671` + `:814-815` — the whole
setup runs inside a `SIGINT`-masked window (NEW-9 history); `:807-811` — PID file
`llama-server-<port>.pid` written atomically via `.tmp` + `rename`;
`:820-844` — health-wait loop, 120 × 0.5s = 60s, polling `process.poll()` and
`_check_health()`; `:637-641` — adoption of an already-running server on the port;
`:600-636` — a cross-process `flock` with an upgrade/kill path.

### The one existing backend seam (and why it doesn't help)

`[ARTIFACT]` `CODEY_BACKEND` / `CODEY_BACKEND_P` + `core/model_tiers.py` select
between `"local"` and remote backends (`openrouter`, `unlimitedclaude`) —
`core/model_tiers.py:27,45,61,126,138-139`, `core/inference_openrouter.py:239-244`,
`core/daemon.py:1124`. Status: **IMPLEMENTED, but wrong axis.** It switches
*where inference happens* (this device vs an HTTP API), not *which local compute
device* runs it. `[INFERENCE]` It is nonetheless the best existing precedent for
how a BrainManager selector should be plumbed — role-scoped env var, a tier
table, per-role override.

---

## (d) Backend-variance analysis for a BrainManager boundary

What actually differs between CPU `llama-server`, the NPU path, and OpenCL GPU.
Every row is sourced.

### D1. Process model — the largest gap

| | CPU llama-server | NPU path | OpenCL path |
|---|---|---|---|
| Program | `llama-server` (HTTP daemon) | `llama-completion` (one-shot CLI) / custom C++ helper | same |
| Interface | OpenAI-compatible HTTP | argv in, stdout out | same |
| Residency | long-lived, serves many requests | process per invocation | same |
| Concurrency | multiple slots in one process | n/a | n/a |

`[ARTIFACT]` All Tier-1/Tier-2 NPU numbers came from bespoke C++ helpers, not a
server: `reports/2026-10-05/helpers/hybrid-latency-phase-v4-canonical.cpp`,
`-v5-step-profile.cpp`, `-v6-step-checkpoint.cpp`, `-v7-batch-threads.cpp`,
`-v8-virtual-sessions.cpp`, `npu-virtual-session-order.cpp`.

**Endpoints/flags with no counterpart in `llama-completion`** — this list is the
adapter's actual spine:

| Thing Codey-OS depends on | Site | NPU/OpenCL counterpart |
|---|---|---|
| `GET /health` | `loader_v2.py:835`, `embed_server.py:572-574`, `inference.py:14`, `inference_hybrid.py:320`, `codeydOS:67` | none |
| `POST /v1/chat/completions` | `inference.py:13`, `inference_v2.py:117`, `inference_hybrid.py:505` | none |
| `POST /v1/embeddings` + `--embedding --pooling mean` | `loader_v2.py:700-702`, `embed_server.py:155`, `embeddings.py:143` | none |
| `--jinja` chat templating | `loader_v2.py:703-705` (NEW-162) | none; helpers send raw prompts |
| `--reasoning-format deepseek` → `message.reasoning_content` | `loader_v2.py:706-712` | none |
| Streaming responses | `inference_hybrid.py` | none |
| Concurrent request slots | implicit | none |
| Port + PID lifecycle | `loader_v2.py:807-811`, `codeydOS:140-141` | none |

`[INFERENCE]` Because `--jinja` and `--reasoning-format` have no CLI-path
counterpart, an NPU adapter would have to re-implement chat templating and
`<think>` splitting in Python — i.e. rebuild in Codey-OS exactly the two things
NEW-162 and the reasoning-format work pushed *into* the server.

### D2. Lifecycle

- CPU: start → adopt-or-spawn under `flock` → 60s health wait → serve → PID-file kill. `[ARTIFACT]` `loader_v2.py:600-851`.
- NPU: `[MEASURED]` `reports/2026-10-05/README.md:123` — one-way handoff; a second switch call explicitly fails; converted accelerator weights are released; "Even retaining accelerator buffers would not by itself restore their tensor bindings, allocator, coherency and backend scheduler." A reversible implementation does not exist.
- `[MEASURED]` `:101` — NPU/hybrid sessions "retain SDK MAX/DCVS-off/sleep-disabled requests until lifecycle teardown." `[INFERENCE]` A resident NPU server would hold the DSP at max DCVS for its whole life. On a phone this is a battery concern the repo flags as unmeasured.
- `[MEASURED]` `:116` — **one session only** (`0x200` for `_session=1`). Codey-OS runs 8080 (primary) / 8081 (legacy planner, `inference_v2.py:193`) / 8082 (embed). At most one can be NPU-backed; the rest stay CPU. **This is structural, not tuning.**

### D3. Memory accounting — the gate's model breaks

`[MEASURED]` `reports/2026-10-05/README.md:28`: at c2560 Mistral allocates 320 MiB
F16 KV; **full NPU retains 4510.39 MiB converted weights**; **hybrid releases
those and maps 4095.05 MiB canonical shadows**; CPU repacking adds 4094.04 MiB
*beside* the file mapping. `:28`: "All share physical system DDR; no extra
accelerator RAM or memory-capacity advantage is established."

`[MEASURED]` `:161`: "RSS/PSS omit some driver allocations. … Lower process RSS
does not prove extra RAM … or that OpenCL can run a model/context that CPU
cannot."

New variables with no representation in Codey-OS's gate: `GGML_HEXAGON_REGISTRATION_WINDOW`
(2048/3072 MiB), `GGML_HEXAGON_MBUF` (512 MiB), `GGML_HEXAGON_VMEM` (3200 MiB)
`[MEASURED]` `reports/2026-10-04/patches/README.md`. `[MEASURED]`
`reports/2026-10-05/README.md:43`: one 3072-window attempt was skipped
pre-load because "its projected 4884 MiB buffers exceeded 4719 MiB budget after
preserving 1536 MiB" — i.e. the research harness has its own admission
controller that would need reconciling with `core/resource_gate.py`'s.

`[ARTIFACT]` Good news: `core/resource_gate.py` is already architecture-aware in
the right way. `CostEstimate` (`:1240-1256`) carries a separate
`recurrent_state_bytes` term documented as "non-zero only for hybrid/SSM
models"; `estimate_kv_cache_bytes` (`:1259`+) uses `arch.n_attention_layers`;
`QWEN35_4B_ARCH` (`:1049-1053`) is `n_layers=32, head_dim=256,
n_attention_layers=8`. `[INFERENCE]` So the gate's *shape* can carry a new
backend's terms; what it lacks is any notion that the same model costs different
amounts on different devices.

### D4. Context handling

- Production CPU default: `n_ctx = 65536` `[ARTIFACT]` `utils/config.py:76-91`.
- Max context benchmarked anywhere on an accelerator: **8704** `[MEASURED]` `reports/2026-10-05/README.md:139`.
- NPU clean-room validation context: **512** `[MEASURED]` `docs/NPU_VALIDATION.md:70`.
- Largest NPU *performance* context: **2560** `[MEASURED]` `:8`.

`[INFERENCE]` Production runs at **25.6x** the largest context ever
performance-tested on the NPU and **128x** the clean-room validation context.
This is a larger gap than the model gap.

### D5. Tokenizer / numerics

`[MEASURED]` Numerical agreement is good but explicitly not bit-identity.
Clean-room: 8/8 Q4_K/Q6_K matrix tests vs CPU reference
(`docs/NPU_VALIDATION.md:51`). NPU 3072-window gate: 32/32 forced-prefix top
predictions, mean KL 0.00000961; 24-layer partial 32/32, mean KL 0.00001169
(`reports/2026-10-05/README.md:34`). OpenCL: 127/128 top tokens agreed, mean KL
≈0.000242 (`README.md:138`); at p128/g32 OpenCL and OpenCL-hybrid both passed
32/32 with mean KL 0.00001956 / 0.000021899 (`:108`). Tokenizer itself is
`libllama`-internal and identical across backends.

### D6. Streaming

`[INFERENCE]` No accelerator artifact exposes incremental token streaming over
any IPC boundary. Helpers write to stdout at completion. Codey-OS's TUI consumes
HTTP responses from `inference_hybrid.py`. An adapter must either add streaming
to a new server or lose it.

### D7. Failure modes — each backend has its own, and they are not interchangeable

| Backend | Failure mode | Source |
|---|---|---|
| CPU | spawn dies (exit code), 60s health timeout, port stuck, orphan after SIGINT | `loader_v2.py:824-833, 842-844`; NEW-5/NEW-9 |
| NPU | `htp_iface_open` → `0x200` AEE_ERPC on session 1 | `reports/2026-10-05/README.md:114-116` |
| NPU | cold-admission gate fail → exit 3 before prompt eval (after 600s) | `:99` |
| NPU | registration-window budget exceeded → skipped pre-load | `:43` |
| NPU hybrid | 6 distinct `throw`s: MemAvailable, CPU KV alloc, KV copy mismatch, non-MMAP load, shadow layout mismatch, weight-readback budget | `registration-hybrid.patch:292,298,310,391,413,446` |
| NPU hybrid | second switch attempt always throws | `registration-hybrid.patch:207` |
| OpenCL | FA silently falls back to CPU (no error at all) | `reports/2026-10-05/README.md:171-175` |
| OpenCL | Adreno compiler E031.x crash risk if the FA guard is removed | `:175` |
| All | Android top-app→foreground-boost transition resets affinity mid-run; two 8K CPU runs aborted | `:110, :130-132` |

`[INFERENCE]` D7 is the strongest argument for the directive's
"record compatibility, don't assume it" instruction. **OpenCL's silent CPU
fallback is the dangerous one**: a backend can report success, offload 29/29
layers, and still execute attention on CPU with no error anywhere. A BrainManager
that trusts a backend's self-report would record a false capability.

### D8. What the adapter interface must therefore carry

`[INFERENCE]`, derived from D1–D7:

1. **Capability descriptor keyed on (backend, model-arch, n_ctx, workload-shape)** — not on backend alone. The directive's "per-model/per-context/per-workload" requirement is exactly right, and D2/D4/(f) show why.
2. **Phase awareness as a first-class, one-way state machine** — `prefill_backend` / `decode_backend`, with an explicit "handoff consumed" terminal state, because the real implementation cannot go back.
3. **Per-backend cost model** feeding `resource_gate`, including registration-window / MBUF / VMEM terms, and the fact that full-NPU and hybrid have *different* residency profiles for the same model.
4. **Session-count budget** — NPU capacity is 1.
5. **Verified-capability probes, not self-reports** — because of OpenCL's silent FA fallback.
6. **Per-backend failure taxonomy with distinct recovery** — `0x200` (never retry), admission failure (retry when cool), spawn death (retry), silent fallback (detect and downgrade the recorded capability).
7. **Explicit CPU fallback that is the default, not the exception.**

---

## (e) llama-server assumptions to relocate — file:line

All `[ARTIFACT]`, Codey-OS repo, paths relative to
`/data/data/com.termux/files/home/Codey-OS/`.

### Tier A — spawn/argv (the core of the adapter)

| file:line | Assumption |
|---|---|
| `core/loader_v2.py:676-713` | Flat argv list for `llama-server`; the whole spawn contract |
| `core/loader_v2.py:677` | `LLAMA_SERVER_BIN` is *the* binary — single-backend |
| `core/loader_v2.py:680-683` | `--host`/`--port` — assumes an HTTP server exists |
| `core/loader_v2.py:684-685` | `-c <n_ctx>` |
| `core/loader_v2.py:686-687` | `-t 6` — CPU thread count; meaningless on NPU |
| `core/loader_v2.py:698-699` | `--flash-attn on` — **silent no-op on Adreno** |
| `core/loader_v2.py:700-702` | `--embedding --pooling mean` |
| `core/loader_v2.py:703-705` | `--jinja` |
| `core/loader_v2.py:706-712` | `--reasoning-format deepseek` |
| `core/loader_v2.py:734-748` | `--load-mode` mapping (NEW-754) |
| `core/loader_v2.py:756` | `self.last_argv` → T9 telemetry provenance record |
| `core/embed_server.py:155,167` | **Second spawn site**, port 8082, same contract |

### Tier B — process lifecycle

| file:line | Assumption |
|---|---|
| `core/loader_v2.py:671, 814-815` | SIGINT-masked spawn window (NEW-9) |
| `core/loader_v2.py:799-804` | `Popen` + `preexec_fn=os.setsid` |
| `core/loader_v2.py:807-811` | PID file `llama-server-<port>.pid` |
| `core/loader_v2.py:820-844` | 60s health-wait polling loop |
| `core/loader_v2.py:824-833` | Death detection via exit code + log tail |
| `core/loader_v2.py:600-642` | `flock` + adopt-or-spawn + upgrade/kill path |
| `core/loader_v2.py:853-869` | `stop()` and the adopted-server no-op history (NEW-74) |
| `core/loader_v2.py:776-792` | `--version` diagnostic probe (NEW-754) |
| `core/embed_server.py:60, 83, 291-313, 572-600` | Parallel health/port/adoption logic |
| `codeydOS:140-141, 178-179, 230-260` | `kill_llama_server_gracefully()` reads `llama-server-8080.pid` |
| `codeydOS:67-73, 111` | `port_healthy()` + `status="loading model"` string-match on llama-server's `/health` payload |
| `codeydOS:136-139` | Hardcoded assumption that only port 8080 is ever started |
| `core/daemon.py` | Daemon-side PID/port/watchdog management (same contract) |

### Tier C — HTTP client layer

| file:line | Assumption |
|---|---|
| `core/inference.py:12-14` | `SERVER_URL`/`CHAT_URL`/`HEALTH_URL` hardcoded to `127.0.0.1:<PRIMARY_SERVER_PORT>` |
| `core/inference_v2.py:117, 193, 242, 248` | `/v1/chat/completions`; port-8081 legacy path |
| `core/inference_hybrid.py:10, 304-320, 347, 505, 811, 819` | TCP HTTP to 8080; `:811` "ignored — we always use TCP HTTP with /v1/chat/completions" |
| `core/embeddings.py:81, 131, 143` | `127.0.0.1:8082/health` and `/v1/embeddings` |
| `core/resource_gate.py:4552` | `host: str = "127.0.0.1"` default |

### Tier D — resource accounting

| file:line | Assumption |
|---|---|
| `core/resource_gate.py:1199-1232` (`ModelSpec`) | Cost is a function of (model, n_ctx) — **no backend dimension** |
| `core/resource_gate.py:1240-1256` (`CostEstimate`) | Terms are model/KV/overhead/recurrent — no accelerator-weight, registration-window, MBUF or VMEM term |
| `core/resource_gate.py:1259+` (`estimate_kv_cache_bytes`) | KV lives in system DDR; no notion of HTP0-resident KV |
| `core/resource_gate.py:1305` (`estimate_model_load_cost`) | Single-device cost model |
| `core/resource_gate.py:3393` (`reserve_slot`) | Slot reservation is port-keyed, not device-keyed (NEW-259 history: a missing `port=` kwarg once made this a silent no-op) |
| `core/resource_gate.py:926-967` (`ModelArch`) | Arch descriptor has no backend-compatibility field |
| `core/resource_gate.py:1081` (`KNOWN_MODEL_ARCHS`) | `"primary": QWEN35_4B_ARCH` |
| `utils/config.py:101` | `"n_gpu_layers": 0` — **DORMANT/dead**; never reaches argv |
| `utils/config.py:40-50` | Single `LLAMA_SERVER_BIN` + single `LLAMA_LIB` — no per-backend lib path, though every accelerator helper requires its *own* `LD_LIBRARY_PATH` and `ADSP_LIBRARY_PATH` (`reports/2026-10-04/patches/README.md`; `README.md:106`) |
| `utils/config.py:76-91` | `n_ctx = 65536` default |
| `utils/config.py:100` | `n_threads = 6` |
| `utils/config.py:509-510` | `QWEN_MMAP`/`QWEN_MLOCK` — note the hybrid patch *requires* mmap (`registration-hybrid.patch:391`), so these are not freely settable on that path |

### Tier E — the existing seam to extend rather than duplicate

`core/model_tiers.py:27, 45, 61, 100, 126, 138-139`; `core/inference_openrouter.py:239-244`;
`core/plannd.py:19, 618, 747`; `core/daemon.py:1124`; `core/summarizer.py:95`.
`[INFERENCE]` Role-scoped backend selection already exists here for local-vs-remote.
A device axis belongs alongside it, not in a parallel mechanism.

---

## (f) Deployed models vs benchmarked configs — the coverage gap

### What is in `~/models` (`[ARTIFACT]`, `ls -la`)

| Dir | File | Bytes | Benchmarked in OpenCL-S24-Ultra? |
|---|---|---:|---|
| `qwen3.5-4b-instruct` | `Qwen3.5-4B-Q4_K_M.gguf` | 2740937888 | **NO — never, in any artifact** |
| `nomic-embed` | `nomic-embed-text-v1.5.Q4_K_M.gguf` | 84106624 | **NO** |
| `qwen2.5-coder-1.5b` | `qwen2.5-coder-1.5b-instruct-q4_k_m.gguf` | 1117320768 | **YES** — exact size match to `npu-upstream.json` `test_model.size`; the clean-room + 8K OpenCL model |
| `mistral-7b-uncensored` | `mistral-7b-uncensored.Q4_K_M.gguf` | 4368440640 | **YES** — the Tier-1 hybrid model |
| `qwen3-4b-instruct` | `Qwen3-4B-Instruct-2507-Q4_K_M.gguf` | 2497279136 | **YES, partially** — the charging-epoch 4B screens (`:91-99`) and the FA numerical gate (`:108`) |
| `qwen2.5-coder-7b` | `qwen2.5-coder-7b-instruct-q4_k_m.gguf` | 4683073536 | NO (a "full Qwen 7B gate" is listed as still-needed, `:30`) |
| `qwen2.5-coder-14b` | `qwen2.5-coder-14b-instruct-q4_k_m.gguf` | 8988110272 | NO |
| `qwen2.5-0.5b` | `planner-codey.gguf` | 397807424 | NO |

### Current default, verified from source not docs

`[ARTIFACT]` `utils/config.py:8-13`:
`MODEL_PATH = $CODEY_MODEL or ~/models/qwen3.5-4b-instruct/Qwen3.5-4B-Q4_K_M.gguf`.
`[ARTIFACT]` `utils/config.py:489` — `PLANNER_MODEL_PATH` is the *same file*
(M1-B, 2026-08-23). `[ARTIFACT]` `utils/config.py:22-27` — embed model is
`nomic-embed-text-v1.5.Q4_K_M.gguf` on port 8082. So production uses exactly
**two** model files, and **neither has ever been benchmarked on any accelerator**.

### I read the deployed model's GGUF header. This is the critical finding.

Full unfiltered KV dump (46 keys, `gguf_version=3`, `n_tensors=426`) —
header-only read, no tensor data, no model load. Per rule 12 I dumped the whole
key set rather than grepping for expected keys. The architecture-relevant keys
`[ARTIFACT]`:

```
  0 general.architecture = 'qwen35'
  2 general.name = 'Qwen3.5-4B'
 13 general.tags = ['unsloth', 'image-text-to-text']
 14 qwen35.block_count = 32
 15 qwen35.context_length = 262144
 18 qwen35.attention.head_count = 16
 19 qwen35.attention.head_count_kv = 4
 20 qwen35.rope.dimension_sections = [11, 11, 10, 0]
 23 qwen35.attention.key_length = 256
 24 qwen35.attention.value_length = 256
 25 qwen35.ssm.conv_kernel = 4
 26 qwen35.ssm.state_size = 128
 27 qwen35.ssm.group_count = 16
 28 qwen35.ssm.time_step_rank = 32
 29 qwen35.ssm.inner_size = 4096
 30 qwen35.full_attention_interval = 4
 31 qwen35.rope.dimension_count = 64
 41 general.file_type = 15
```

**Qwen3.5-4B is a hybrid SSM/attention model**, not a plain transformer:
`ssm.*` keys are present, `full_attention_interval = 4` means only every 4th of
32 blocks is full attention, `key_length = value_length = 256` (not the usual
128), `rope.dimension_sections = [11,11,10,0]` indicates mRoPE, and
`general.tags` includes `image-text-to-text` — it is a VLM. This is precisely the
rule-12 trap: nothing about the name "Qwen3.5" predicts any of it, and it is
materially different from Qwen3.

Confirmed independently in the pinned llama.cpp source `[ARTIFACT]`
`OpenCL-S24-Ultra/.work/llama.cpp/src/llama-arch.cpp:1091-1114`:

```cpp
bool llm_arch_is_hybrid(const llm_arch & arch) {
    switch (arch) {
        ...
        case LLM_ARCH_QWEN35:
        case LLM_ARCH_QWEN35MOE:
        ...
            return true;
```

Also `[ARTIFACT]` `llama-arch.cpp:41-42` — `qwen35` / `qwen35moe` are registered
architectures in all three checkouts (pinned OpenCL source, pinned NPU
clean-room source, and current `~/llama.cpp`), so **the model loads fine**; the
problem is not arch support.

Corroboration from Codey-OS's own side `[ARTIFACT]`
`core/resource_gate.py:1049-1053`: `QWEN35_4B_ARCH = ModelArch(n_layers=32,
n_kv_heads=4, head_dim=256, n_attention_layers=8)`, with `:1008-1015` explaining
that the 32/8 disagreement is deliberate and `head_dim=256` is only valid because
`key_length` and `value_length` are both 256. Codey-OS already modeled this
correctly (NEW-157). The two independent readings agree.

### I also read the embed model's GGUF header — it is likewise ineligible

Having caught the name-inference trap on Qwen3.5, I did not then assume
nomic-embed's architecture from its name. Full unfiltered KV dump (23 keys,
`gguf_version=3`, `n_tensors=112`), header-only read `[ARTIFACT]`:

```
  0 general.architecture = 'nomic-bert'
  1 general.name = 'nomic-embed-text-v1.5'
  2 nomic-bert.block_count = 12
  3 nomic-bert.context_length = 2048
  4 nomic-bert.embedding_length = 768
  6 nomic-bert.attention.head_count = 12
  9 nomic-bert.attention.causal = False
 10 nomic-bert.pooling_type = 1
 15 tokenizer.ggml.model = 'bert'
```

`nomic-bert` is on neither allowlist. And `attention.causal = False` is the
deeper problem: this is a **non-causal BERT-style encoder**, so there is no
growing KV cache at all. The handoff's entire mechanism is copying an allocated
KV buffer from accelerator to host — on this model there is nothing of that kind
to copy. `[INFERENCE]` The prototype is not merely unlisted here; its mechanism
is inapplicable in principle.

**This retracts a recommendation I would otherwise have made.** Before reading
this header, the embed server looked like the cheapest NPU candidate (small,
pure-prefill, existing BM25 fallback). It is not a candidate for the *handoff
prototype* at all. A plain full-NPU (non-hybrid) embed path is not excluded by
this evidence — the ggml-hexagon backend itself has no such arch guard — but that
is a different, untested configuration, and `nomic-bert` support on the Hexagon
backend is unverified.

### Consequence: both handoff prototypes reject both deployed models

| | Deployed arch | On #5 allowlist (`QWEN2\|QWEN3`)? | On #7 allowlist (`QWEN2\|QWEN3\|LLAMA&&!SWA`)? |
|---|---|---|---|
| Primary + planner | `qwen35` (hybrid SSM, `llm_arch_is_hybrid()==true`) | **No** | **No** |
| Embed (8082) | `nomic-bert` (`causal=False`, no KV cache) | **No** | **No** |

On the measured code path the prototype throws
`"hybrid prototype requires supported plain KV without Llama SWA"` (#7) or the
equivalent at #5:54.

`[REPO CLAIM]` consistent with this: `reports/2026-10-05/README.md:8` — the
hybrid handles "plain Qwen2/Qwen3 KV"; `reports/2026-10-04/patches/README.md` —
"a plain non-SWA LLAMA architecture guard" and "Existing Qwen2/Qwen3 handoff
support remains."

`[INFERENCE]` And the guard is load-bearing, not conservatism to be relaxed: the
handoff's mechanism is copying an allocated KV buffer from accelerator to host
(`:18` — "copies 320 MiB allocated KV"). A hybrid SSM model's 24 non-attention
layers carry *recurrent state*, not KV — a different object with different
lifetime semantics, which the migration code has no representation for. So the
gap is **not "needs benchmarking"**; it is **"the prototype does not support the
deployed model, and supporting it is new SSM-state-migration work of unknown
size."** That is a materially different blueprint input.

### Coverage gap, quantified

| Dimension | Production | Best accelerator evidence | Gap |
|---|---|---|---|
| Model | Qwen3.5-4B Q4_K_M (`qwen35`) + nomic-embed (`nomic-bert`) | Mistral 7B (llama), Qwen2.5-Coder-1.5B (qwen2), Qwen3-4B (qwen3) | **No overlap.** Zero accelerator measurements on either deployed model |
| Arch class | hybrid SSM+attention; non-causal BERT encoder | plain causal transformer only | **Both prototype allowlists exclude both** |
| Context | 65536 | 8704 (OpenCL 1.5B); 2560 (NPU perf); 512 (NPU clean-room) | **7.5x / 25.6x / 128x** |
| Embed model | nomic-embed-text-v1.5 Q4_K_M (`nomic-bert`) | never tested on any accelerator | **total** |
| Quantization | Q4_K_M | Q4_K_M | **none** — the one dimension that matches |
| Concurrency | 3 servers (8080/8081/8082) | 1 NPU session max | **structural** |
| Session shape | persistent multi-turn | first-response-only handoff | **structural** |

**Directive requirement — "benchmark the exact deployed models before changing
production defaults" — assessment: NOT SATISFIED, and currently NOT SATISFIABLE
on the hybrid path.** Existing evidence covers zero deployed models. Neither
deployed model can be run on either handoff prototype until its arch guard is
extended, and for the primary that additionally requires designing SSM
recurrent-state migration. That is engineering work, not a benchmark run.

`[INFERENCE]` What remains testable without new C++ work: **full-NPU (non-hybrid)
inference**, which carries no arch guard — it is the plain `ggml-hexagon` backend
and would be reached by building `llama-server` with `-DLLAMA_BUILD_SERVER=ON`
against that backend. Whether `ggml-hexagon` supports `qwen35`'s SSM ops or
`nomic-bert` at all is unverified and is the first thing to check (statically, in
`ggml-hexagon`'s `supports_op`, before any run). Note the tradeoff: full-NPU
decode was the *slowest* of the three modes measured (3.79 tok/s vs CPU 6.26), so
full-NPU is attractive only for prefill-dominated roles.

---

## (g) Runtime prerequisites + install.sh gap

### NPU path prerequisites `[ARTIFACT]`

Termux packages (`install-npu.sh:43`):
```
git clang cmake ninja python curl openssl qemu-user-x86-64
```

Not a QNN SDK. **Hexagon SDK 6.6.0.0** (`npu-upstream.json`):
version `6.6.0.0`, tools `19.0.07`, URL the `snapdragon-toolchain/hexagon-sdk`
v6.6.0.0 GitHub release, sha256 `4a916e42c1dab9efdf2e58773f901ea780fa43c907bf054ab76572a3b3d942f4`,
size 694150896 (≈662 MiB, unpacks to ≈3.2 GiB per `docs/NPU_INSTALL.md:41`).

**Nine pinned Debian amd64 runtime `.deb`s**, each with sha256 + a
content-addressed `snapshot.debian.org` fallback (`npu-upstream.json`
`x86_runtime`): `libatomic1`, `libgcc-s1`, `libstdc++6`, `libc6`, `libxml2`,
`libzstd1`, `libtinfo6`, `zlib1g`, `libgmp10`. Extracted with `dpkg-deb` into
project storage — `[REPO CLAIM]` `docs/NPU_INSTALL.md:41`: "they are **not
installed into Android or the global Termux prefix**."

Device prerequisites `[REPO CLAIM]` `docs/NPU_INSTALL.md:39`: readable
`/vendor/lib64/libcdsprpc.so`; no root, no system/vendor modification; "The
device vendor must allow the necessary unsigned DSP session through its FastRPC
broker; file presence alone does not prove access."

Runtime env `[MEASURED]` `reports/2026-10-04/patches/README.md`:
`GGML_HEXAGON_REGISTRATION_WINDOW=2048`, `GGML_HEXAGON_MBUF=512`,
`GGML_HEXAGON_VMEM=3200`; each process must set its library search path to its
own `build/bin` and `ADSP_LIBRARY_PATH` to its own v75 DSP directory, with a
specific own-bin `libc++_shared.so` link — and "never globally append
`$PREFIX/lib`."

Resources: ≥8 GiB free plus model storage; tens of minutes to build; default
concurrency 2 at nice +10; Termux must stay foreground (screen-off/background
cpuset restrictions were observed).

QEMU is for **x86 SDK build tools only**; inference is native ARM64 + Hexagon.

### OpenCL path prerequisites `[ARTIFACT]` `README.md:52-56, 71`

Termux packages: `git clang cmake ninja python opencl-headers openssl`.
Readable `/vendor/lib64/{libOpenCL.so, libOpenCL_adreno.so, libCB.so, libgsl.so}`.
Must live in Termux private storage, not shared Android storage.

### Codey-OS `install.sh` — rule 11 gap

`[ARTIFACT]` `grep -niE 'opencl|hexagon|npu|qnn|vulkan|GGML_|DGGML'` over
`install.sh`: **zero accelerator matches.** The build is CPU-only:

`install.sh:230`:
```
CMAKE_FLAGS="-DBUILD_SHARED_LIBS=OFF -DGGML_NATIVE=OFF -DGGML_FATAL_WARNINGS=OFF -DGGML_ALL_WARNINGS=OFF"
```

`install.sh:100` packages: `python cmake ninja clang wget curl git golang sqlite age ruff`
— no `opencl-headers`, no `qemu-user-x86-64`.

`install.sh:219-220`: `git clone --depth 1 https://github.com/ggerganov/llama.cpp`
— **shallow, unpinned**. This is NEW-757. `[INFERENCE]` A `--depth 1` unpinned
clone is fundamentally incompatible with an accelerator path that requires
checkout `e358d591` plus patches: you cannot `git apply` a commit-pinned patch
set against an arbitrary shallow HEAD, and you cannot check out `e358d591` from
a depth-1 clone without re-fetching.

**Rule 11 status: DOCS-ONLY / MISSING.** Nothing about either accelerator path
exists in `install.sh`, and `docs/troubleshooting.md:100` currently documents the
*opposite* as a permanent limitation: "No NPU / GPU acceleration | Cannot offload
to device accelerator | `n_gpu_layers=0` — CPU path only on Android". That line
is now contradicted by the OpenCL repo's evidence and should be corrected
whichever way the blueprint goes.

Flagged rather than silently skipped, per rule 11: I did **not** determine where
accelerator prerequisites should go in `install.sh`, because that depends on an
undecided product question — whether Codey-OS pins its own llama.cpp to
`e358d591` (which would also roll back the NEW-754 `--load-mode` contract) or
forward-ports the patches. That decision gates the install.sh change.

---

## (h) Risks and research uncertainties

**R1 — No accelerator-backed server has ever been built or run. (Highest, but
smaller than it first looks.)** `tools/server/` is present in both trees and both
build scripts deliberately set `-DLLAMA_BUILD_SERVER=OFF`, so this is an unbuilt
target rather than missing software. Unknowns that remain real: whether it
compiles in these patched trees, whether it links and runs against
`libggml-hexagon` / `libggml-opencl`, whether `--jinja` / `--reasoning-format` /
`/v1/embeddings` behave identically, and whether the one-way handoff API is
reachable at all from a multi-slot server (R4/D2 suggest it is not, cleanly).

**R2 — Version skew is a hard prerequisite, not a caveat.** Patches pin
`e358d591`; Codey-OS runs `4f540676` / 0.6.0-dev as of `b5b805a` yesterday. Pick
one: pin back (and reopen the NEW-754 CLI-contract question) or forward-port 8
patches across a boundary that already broke once.

**R3 — Both deployed models are out of scope for both handoff prototypes.** Not a
benchmark gap: an arch-guard gap, plus SSM-recurrent-state migration for the
primary (`qwen35`) and a mechanism that does not apply at all to a non-causal
encoder (`nomic-bert`, `causal=False`, no KV cache). Size unknown (section f).

**R4 — The 74.9% win is structurally first-response-only.** A one-way,
non-reinitializable handoff in a persistent REPL/daemon means turn 1 accelerates
and the process is CPU-only thereafter. `[MEASURED]` `:123`: "Equal offered-work
sustained hybrid performance cannot be inferred from a single-response result; a
reversible implementation or measured reinitialization cost is required."

**R5 — NPU session capacity is 1, cause unknown.** `0x200` = generic `AEE_ERPC`;
the repo explicitly cannot identify whether it is vendor userspace, kernel,
firmware, or a permission restriction. **Unfixable from this side without new
information.**

**R6 — Silent-fallback class of failure.** OpenCL reports 29/29 layers offloaded
and runs attention on CPU, with no error. Any capability record built from a
backend's self-report will be wrong. `[MEASURED]` `:175`: the share of runtime
this costs is unmeasured, and removing the guard is untested and may crash the
driver.

**R7 — NPU decode is slower than CPU.** 3.79 (full) / 5.85 (hybrid) vs 6.26
tok/s. Any "NPU is faster" framing is false for decode. This is the directive's
"don't hard-code NPU as universally superior" warning, already borne out by the
repo's own data.

**R8 — Resource-gate semantics change, and the gate is this project's main
crash-prevention mechanism.** 4510 MiB retained accelerator weights vs 4095 MiB
canonical shadows vs CPU repacking adding 4094 MiB beside the mapping — and
`[MEASURED]` `:28` "no extra accelerator RAM" and `:161` "RSS/PSS omit some
driver allocations." Combined with rule 2 (prior crash history at ~10.8 GB RAM),
a wrong accelerator cost model is a device-crash risk, not a perf regression.

**R9 — Thermal and Android-scheduling noise is large enough to censor runs.**
Two 8K CPU baselines were aborted by top-app→foreground-boost affinity resets
(`:110`, `:130-132`); a full-NPU run failed cold admission after 600s and exited
3 (`:99`). Any production A/B must survive conditions the research harness
handled by *discarding* runs.

**R10 — Directive's explicit warning applies to patches #4–#8.** They are
research snapshots that their own READMEs say not to apply. They contain raw
`getenv` reads, six `throw` sites, and env-var-gated behavior. Copying them into
cognitive code is exactly what the directive prohibits.

**R11 — DCVS held at MAX until teardown.** `[MEASURED]` `:101` — NPU/hybrid
sessions retain MAX/DCVS-off/sleep-disabled requests for the session lifetime;
idle-vote release is "a source-based engineering lead, not measured energy
savings." For a resident server on a phone this is an unquantified battery cost.

**R12 — The OpenCL repo's preservation-audit baseline is stale.** See (b).
Cross-repo ledger item.

---

## (i) Open questions

**For Ish (product/direction):**
1. Pin Codey-OS's llama.cpp to `e358d591` (rolling back the NEW-754 `--load-mode`
   contract) or forward-port 8 patches to current HEAD? Everything downstream
   depends on this.
2. Given that only one NPU session is possible, which single role gets it? I have
   **no evidence-backed recommendation** — the embed server initially looked like
   the obvious candidate and its GGUF header ruled it out for the handoff path
   (section f). Answering this needs the static `supports_op` check in Q5/Q13
   first.
3. Is a first-response-only acceleration worth integrating at all, or is the bar
   a reversible handoff?
4. Should a deployed model change to one the prototypes support (`qwen2` /
   `qwen3` / non-SWA `llama`), or should a prototype be extended to `qwen35`
   hybrid SSM? Very different costs, and changing the primary model has direct
   agent-quality consequences well outside B4's scope.

**Technical, answerable by work:**
5. Does `llama-server` build and run against `libggml-hexagon` / `libggml-opencl`
   with `-DLLAMA_BUILD_SERVER=ON` in these trees? Nobody has tried. **This is the
   gating experiment, and it is a build, not a benchmark** — no model load needed
   to answer the compile/link half.
6. Does `llama-server`'s multi-slot/continuous-batching model conflict with the
   one-way handoff API and the single-session limit?
7. What is the NPU prefill advantage at production context (65536) rather than
   2560? `[INFERENCE]` registration-window data (`:36-40`) suggests mapping and
   eviction-flush overhead already consume ~90% of decode wall time at 2560 —
   there may be a context ceiling where the advantage inverts. Unmeasured.
8. Can the hybrid arch guard be extended to `qwen35`, and what does migrating SSM
   recurrent state (`ssm.state_size=128`, `group_count=16`, `inner_size=4096`,
   24 non-attention layers) actually require?
9. Does the Adreno 750 driver (E031.45.02.26) actually fail mixed-type FA, or is
   the guard inherited over-caution from Adreno 740 (E031.41)? `[MEASURED]`
   `:175` names this "a high-value next experiment"; untested, may crash.
10. What is the NPU/hybrid cold-start cost end to end? All reported numbers are
    warm and exclude load + admission (10–104s of admission waits observed).
11. Does the embed workload (pure prefill, 2048 ctx, no decode) win on a
    **full-NPU** path? Still the most attractive workload shape, but the handoff
    prototype is ruled out for it, so this requires Q5 + Q13 first.
12. What are the real resource-gate terms for an NPU-backed server, measured
    rather than derived? R8 makes guessing a crash risk.
13. **Statically**, does `ggml-hexagon`'s `supports_op` cover the ops `qwen35`
    needs (SSM conv/scan, 256-wide K/V heads, mRoPE) and `nomic-bert` needs
    (non-causal attention, mean pooling)? This is a source read, loads no model,
    and gates everything in Q2/Q11. Cheapest next step in this whole report.

---

## Appendix — verification method

- Repos inspected read-only. Only file written: this one.
- Full binary paths used for `find`/`grep` throughout (bare `find`/`grep` silently return nothing in this Termux shell).
- No model loaded, no benchmark run, no inference process started. Recorded results were read from committed artifacts.
- `~/.codeyOS/restoricon.db` was never touched.
- GGUF inspection read the metadata header only (magic, version, tensor count, and all KV pairs — 46 for Qwen3.5-4B, 23 for nomic-embed), seeking past the large vocab arrays without materializing them. No tensor data read. Script at `scratchpad/gguf_keys.py`.
- Per rule 12: for **both** deployed models the full GGUF key set was dumped unfiltered before any key was interpreted. The `qwen35` finding was independently corroborated against `llama-arch.cpp` in three separate checkouts and against `core/resource_gate.py:1049-1053`.
- Both handoff patches' arch guards were opened and quoted; neither was inferred from the other.
- One recommendation was retracted mid-report after reading the artifact (the embed-model NPU candidacy, section f). Recorded rather than quietly removed, per rule 6.
