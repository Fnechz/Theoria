# Technical Report — Theoria

**Team ID:** theoria
**Domain:** math_scientific_reasoning
**Model:** Theoria-v3 (Qwen3-1.7B Q4_K_M, conservative QLoRA)

---

## Problem

Students and professionals across Africa often lack reliable internet, cloud API budgets, or GPU hardware for advanced math and science tools. Theoria targets the **Math & Scientific Reasoning** domain by delivering an **offline workstation** that runs on the ADTC Standard Laptop (8 GB RAM, integrated graphics, Ubuntu 22.04).

The target user is a secondary/university student or clinic/education worker who needs step-by-step math help without sending data to the cloud. Theoria combines a compact LLM with **symbolic computation (SymPy)**, **local RAG** over curated math corpora and user-attached PDFs, and a fully offline web UI with LaTeX typesetting.

---

## Design Decisions

- **Base family:** Qwen3-1.7B (earlier bake-off beat Qwen2.5-Math-1.5B on identity/science while matching math). Stock Q8 was the interim ship; ADTC VM profiling (2026-08-13) showed Q4_K_M reaches the 15 t/s S_perf cap with lower size.
- **Ship weights — Theoria-v3 Q4_K_M:** conservative QLoRA (r=8, 1 epoch, assistant-only loss) for identity / Lean / science style, exported via Unsloth. On the 8 GB / 4 vCPU VM: **~18 t/s**, peak RSS **~1880 MB**, S_perf **100**, S_eff **~73**. Matched mikromini Q4 on speed but without its thinking-leak / false \(n^2>n\) failures; beat stock Q8 (~12.6 t/s, S_perf ~84).
- **Quantization:** Q4_K_M (~1.03 GiB) — full S_perf on the ADTC laptop profile with ~1.9 GB peak RSS (far under the 7 GB ceiling).
- **Runtime:** llama.cpp (required by ADTC), run as a **persistent llama-server** with the model resident in RAM — first-token latency drops from ~11 s (cold llama-cli) to under a second. KV cache quantized to q8_0. Chat completions use the model's own template (`--jinja`), so generation stops at EOS instead of running away. Qwen3 thinking mode is disabled by default for responsiveness.
- **Intent routing:** a lightweight heuristic router classifies queries as chitchat / math / science / general. Chitchat gets a persona prompt with no RAG and no boxed-answer instruction (fixing "hello" answered with a math hallucination). RAG chunks are only injected when cosine similarity ≥ 0.55.
- **Cross-disciplinary pairing (load-bearing):** SymPy solves/differentiates/integrates deterministically alongside the LLM; the verified result is injected into the prompt as a constraint ("your final answer must agree"), and shown in the UI as a verification badge. SymPy also serves as an instant fallback if inference fails.
- **RAG:** BGE-small-en-v1.5 embeddings (384-d) in SQLite with numpy cosine search. Indexed GSM8K samples, curated theorem snippets, and **user-attached PDFs** (PyMuPDF extraction, page-cited chunks).
- **Custom fine-tune (shipped as v3):** small QLoRA on Colab T4 (`training/theoria_qlora.ipynb`) — identity seeds, clean GSM8K, science, Lean sorry-fill, base replay — gated before GGUF export. Artifact: `model/theoria-v3-q4_k_m.gguf`.
- **UI:** FastAPI + static HTML/JS with **vendored KaTeX** (offline LaTeX typesetting), SSE token streaming, sources panel with PDF page citations, SymPy verification badge, and chiShona localization. No Electron; UI RAM cost is near zero.

---

## Constraints

- **Hardware:** Intel i5 10th–12th gen, 8 GB DDR4, no discrete GPU, Ubuntu 22.04 LTS.
- **Memory ceiling:** Peak RSS must stay under **7 GB** or submission is disqualified.
- **Offline:** Zero network calls during inference and profiling (KaTeX and all assets vendored).
- **Runtime:** llama.cpp + GGUF only.

---

## Benchmarks

Official `adtc-profiler` on GCP `adtc-benchmark` (AMD EPYC, 7.8 GB RAM, Ubuntu 22.04, 4 threads, `--skip-accuracy`, 2026-08-13):

| Model | Gen t/s | Peak RSS | S_perf | S_eff |
|---|---|---|---|---|
| **theoria-v3 Q4_K_M (ship)** | **17.98** | **1880 MB** | **100.0** | **73.1** |
| mikromini-math Q4_K_M | 18.16 | 1880 MB | 100.0 | 73.1 |
| Qwen3-1.7B Q8_0 | 12.55 | 1934 MB | 83.7 | 72.4 |

Quality probes rejected mikromini (thinking-tag leak; incorrectly affirms ∀n, n²>n). theoria-v3 kept clean identity/math/science answers.

Run locally:

```bash
bash download_model.sh
bash scripts/build_llama.sh
python scripts/bakeoff.py              # mechanical scores
python scripts/probe_quality.py        # answer-quality probes
bash scripts/benchmark.sh              # official adtc-profiler run
```

Official scores are measured by the ADTC profiler on the standard evaluation machine.

---

## Architecture

```
User → Web UI (KaTeX, SSE streaming) / CLI
         └→ FastAPI → Intent router (chitchat | math | science | general)
                          ├─ RAG retrieve (SQLite + BGE, threshold 0.55,
                          │                corpora + user PDFs w/ page cites)
                          ├─ SymPy tool (verify math exactly)
                          └─ llama-server (persistent theoria-v3 Q4_K_M,
                                           q8_0 KV cache, chat template)
```

---

## Language Support (African Alpha)

chiShona support is layered: query-side vocabulary translation (so SymPy/RAG understand Shona math queries), canned Shona replies for common greetings, full chiShona UI strings, and Shona instruction pairs in the fine-tune dataset. The `african_alpha_claim` flag will be flipped once the fine-tuned model demonstrably generates Shona (the base model cannot).

---

## Future Work

- Complete the QLoRA fine-tune and ship the custom Theoria GGUF (identity + Shona in the raw weights)
- Lean4 formal proof verification
- Expanded RAG corpus (OpenWebMath subset, ProofNet)
- imatrix-calibrated Q4_K_M variant if an even smaller footprint is needed
