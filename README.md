# Theoria

Offline math and science reasoning assistant for **ADTC 2026 — The Laptop LLM Challenge**.

Theoria runs entirely on-device using **llama.cpp** + **Theoria-v3 (Qwen3-1.7B Q4_K_M)**, with an intent-aware pipeline, **SymPy** symbolic verification, **local RAG** over curated math corpora and user-attached PDFs, and a fully offline web UI with KaTeX typesetting, token streaming, and chiShona localization.

## Quick Start

```bash
# 1. Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .

# 2. Build llama.cpp
chmod +x scripts/*.sh download_model.sh
bash scripts/build_llama.sh

# 3. Install ship model (~1.03 GiB theoria-v3 Q4_K_M)
#    Put the GGUF in model/candidates/ first (from Colab/Drive), then:
bash download_model.sh

# 4. Build RAG index
python -m theoria.rag.embed

# 5. CLI
theoria "Solve x^2 - 5x + 6 = 0"

# 6. Web UI (offline, localhost only)
python -m theoria.server
# Open http://127.0.0.1:8080
```

## Benchmarks & Model Selection

```bash
python scripts/bakeoff.py          # ADTC mechanical scores (speed + RAM)
python scripts/probe_quality.py    # answer-quality probes per candidate
bash scripts/benchmark.sh          # official adtc-profiler run
```

Ship decision (ADTC VM 2026-08-13): **theoria-v3 Q4_K_M** — ~18 t/s,
~1880 MB peak, S_perf 100; cleaner probes than mikromini Q4; faster than
stock Q8 (~12.6 t/s). Details in `REPORT.md`.

## Custom Fine-Tune (QLoRA)

```bash
# Colab: training/theoria_qlora.ipynb + seed_identity.json + sorry_fill.jsonl
# Output: theoria-v3-q4_k_m.gguf → model/candidates/ → bash download_model.sh
```

See `training/COLAB_FINE_TUNE.md`.

## Project Structure

```
Theoria/
├── metadata.json          # ADTC submission metadata
├── download_model.sh      # Model download script
├── REPORT.md              # Technical report
├── theoria/               # Python package (router, pipeline, RAG, SymPy, i18n)
├── static/                # Web UI (vendored KaTeX, SSE streaming)
├── data/                  # RAG source data + fine-tune dataset
├── training/              # QLoRA Colab notebook
├── rag/                   # Vector index (generated)
├── scripts/               # Build, download, bake-off, benchmark
└── inference/llama.cpp/   # llama.cpp (built locally)
```

## Key Features

- **Intent router:** chitchat, math, science, and general queries each get the
  right prompt — greetings never trigger math hallucinations.
- **SymPy verification (load-bearing):** exact symbolic results constrain and
  verify the model's math; shown as a badge in the UI.
- **PDF attachments:** drop a PDF in the sidebar, ask questions, get answers
  with page citations — fully offline.
- **Streaming + KaTeX:** tokens stream into the UI and render as typeset math.
- **chiShona:** localized UI, Shona query understanding, canned greetings
  (model-level Shona lands with the fine-tune).

## License

Open source — see ADTC submission requirements.
