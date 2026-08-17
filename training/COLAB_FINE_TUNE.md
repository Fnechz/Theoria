# Theoria v3 Colab fine-tune

Notebook: `training/theoria_qlora.ipynb`

## Before Colab

Download or keep these three repository files together:

- `training/theoria_qlora.ipynb`
- `data/finetune/seed_identity.json`
- `data/finetune/sorry_fill.jsonl`

Do not upload `data/finetune/train.jsonl`; that is the failed high-risk v2
mixture.

## Run

1. Open Google Colab and upload `theoria_qlora.ipynb` with
   **File → Upload notebook**.
2. Choose **Runtime → Change runtime type → T4 GPU**.
3. Run cell 1. It pins `datasets` (&lt;4.4) and `trl` (≤0.24) for Unsloth.
   If Colab asks for a restart, restart, re-run cell 1, then continue at cell 2.
   Confirm the cell prints versions like `datasets 3.x` / `trl 0.2x` and `Tesla T4`.
4. Cell 2 opens an upload dialog. Select `seed_identity.json` and
   `sorry_fill.jsonl` together.
5. Run cells in order. Do not skip the base evaluation.
6. Training uses QLoRA rank 8, learning rate `5e-5`, assistant-only loss,
   one epoch, and Qwen3 non-thinking formatting.
7. Cell 7 must print `SHIP_CANDIDATE = True`. If it prints `False`, stop:
   keep the official base Q4_K_M.
8. Read the tuned probe answers manually before running cell 9.
9. Cell 9 merges to GGUF (~1.03 GiB) then copies to Drive. If Drive mount
   fails, **do not restart the runtime** — the file is already at
   `/content/theoria-v3-q4_k_m.gguf`. Fix mount and re-run cell 10 only.
10. Cell 10 retries Drive mount and saves GGUF + LoRA zip + eval JSON under
    `MyDrive/Theoria-v3/`.

## Artifacts

- `theoria-v3-q4_k_m.gguf` — candidate submitted model
- `theoria-v3-lora.zip` — reproducible adapter
- `theoria-v3-eval.json` — base/tuned comparison and corpus mixture

## Local comparison

Put the GGUF at:

```text
model/candidates/theoria-v3-q4_k_m.gguf
```

Then compare raw-model behavior:

```bash
python3 scripts/probe_quality.py \
  --model model/candidates/qwen3-1.7b-q4_k_m.gguf \
  --model model/candidates/theoria-v3-q4_k_m.gguf
```

Do not adopt it based on Colab loss alone.

## 8 GB VM audit

On `fnechz@adtc-benchmark`, copy/download the candidate into
`~/Theoria/model/candidates/`, then run:

```bash
cd ~/Theoria
export PATH="$HOME/Theoria/inference/llama.cpp/build/bin:$PATH"

llama-bench \
  -m model/candidates/theoria-v3-q4_k_m.gguf \
  -p 512 -n 128 -t 4 -r 2
```

Temporarily point `metadata.json` `_runtime.model_path` at that GGUF and run
the official participant profiler with `--skip-accuracy`. Restore the file
afterward. Adopt only if:

- raw prompt quality is at least as good as base Q4_K_M;
- no `####`, `<<...>>`, repeated answer tail, or gibberish appears;
- generation TPS and peak RSS are no worse than the official Q4 candidate;
- both required submission prompts remain correct.

