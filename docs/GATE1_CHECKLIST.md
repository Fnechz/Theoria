# Gate 1 Submission Checklist

## Repo & Files

- [ ] Public GitHub repository
- [ ] `metadata.json` filled (team_id, submitter, 2 test prompts)
- [ ] `download_model.sh` works idempotently
- [ ] `REPORT.md` complete with benchmarks
- [ ] `.gitignore` excludes `model/*.gguf`

## Technical

- [ ] Model: Qwen3-4B Q4_K_M GGUF via llama.cpp
- [ ] Peak RAM < 7 GB (verify with adtc-profiler)
- [ ] 100% offline during inference
- [ ] Cross-disciplinary pairing documented (LLM + SymPy)

## Deliverables

- [ ] `submission.json` from full profiler run
- [ ] 2-minute demo video (see docs/demo_script.md)
- [ ] Screenshots of CLI + web UI

## DevPost

- [ ] Register at https://adtc-2026.devpost.com/
- [ ] Submit repo URL before **August 25, 2026**
- [ ] Tag release: `gate1_submission`

## Commands

```bash
bash download_model.sh
bash scripts/build_llama.sh
export PATH="$PWD/inference/llama.cpp/build/bin:$PATH"
bash scripts/benchmark.sh
git tag gate1_submission
```
