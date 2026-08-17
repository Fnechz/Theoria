# Gate 1 submission checklist (ADTC 2026)

Official sources:
- Devpost: https://adtc-2026.devpost.com/ — deadline **24 Aug 2026 11:45pm PDT**
- Template: https://github.com/Africa-Deep-Tech-Foundation/adtc-2026-submission-template
- Profiler: https://github.com/Africa-Deep-Tech-Foundation/adtc-profiler

## Required artifacts

- [ ] Public GitHub repo (fork/clone of template structure)
- [ ] `metadata.json` — real `team_id`, name, email, github_handle (no placeholders)
- [ ] Exactly **2** `test_prompts` for `math_scientific_reasoning`
- [ ] `download_model.sh` downloads public GGUF to `_runtime.model_path`
- [ ] `*.gguf` / `model/` in `.gitignore` (never commit weights)
- [ ] `REPORT.md` with problem, design, constraints, **i5 benchmarks**
- [ ] `model.runtime` = `llama.cpp`, GGUF quant documented
- [ ] `budget_laptop_claim`: true
- [ ] Fully offline inference (no network after download)
- [ ] 2-minute video (problem → demo → RAM/TPS → journey)
- [ ] Devpost submission with repo URL + video

## Local validation (must pass)

```bash
bash download_model.sh
bash scripts/profile_i5.sh --full
# inspect submission.json: peak_rss_mb < 7000
```

## Scoring reminder

`S = 0.50·Sacc + 0.30·Sperf + 0.20·Seff − Pthermal`

- Peak RAM > 7 GB → **disqualification**
- Temp > 85°C or throttle → −10
- African Use Case bonus only if `african_alpha_claim: true` and demo warrants it (Shona parked for now)

## Theoria status vs template

| Requirement | Status |
|---|---|
| Domain math_scientific_reasoning | ✅ |
| llama.cpp + GGUF | ✅ Theoria-v3 Q4_K_M |
| download_model.sh | ✅ |
| REPORT.md | ⚠️ refresh with i5 numbers |
| metadata placeholders | ⚠️ team_id=`theoria`; replace email with Devpost contact if needed |
| Cross-disciplinary SymPy/Lean | ✅ load_bearing |
| Profiler-compatible layout | ✅ |
| Video | ❌ not recorded |
| Fine-tuned custom GGUF | ✅ theoria-v3 Q4_K_M (needs public download URL) |

## Differentiator stack (already in app)

SymPy verify · counterexample engine · Lean4 TheoriaKit + auto-fill sorry · photo OCR · chat history · Think mode · TeX preview
