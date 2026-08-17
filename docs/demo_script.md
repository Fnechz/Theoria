# Theoria — 2-Minute Demo Video Script

**Target:** Gate 1 submission (max 2 minutes)

## 0:00–0:15 — Problem

> "Across Africa, students need math and science help but often lack cloud APIs, stable internet, or GPUs. Theoria runs fully offline on an 8 GB laptop."

## 0:15–0:45 — Live Demo (CLI)

```bash
theoria "Solve x^2 - 5x + 6 = 0"
```

Show SymPy result + LLM explanation + RAG sources.

## 0:45–1:10 — Web UI

Open http://127.0.0.1:8080, ask:

> "Find the derivative of sin(x^2)"

Show answer, SymPy line, sources panel.

## 1:10–1:30 — Performance

Show Activity Monitor / htop while a query runs. Highlight peak RAM under 7 GB.

## 1:30–1:50 — Architecture

Brief slide: llama.cpp + SymPy + RAG. Mention ADTC profiler compatibility.

## 1:50–2:00 — Close

> "Theoria — open source, offline, built for the hardware Africa already has. GitHub link in description."

## Recording Checklist

- [ ] Screen recording at 1080p
- [ ] Voice-over or subtitles
- [ ] Show both CLI and web UI
- [ ] Show RAM monitor during inference
- [ ] Export as MP4, upload to DevPost
