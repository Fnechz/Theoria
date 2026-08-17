# Inference runtime

llama.cpp is **not** stored in this repository (too large). Build it locally:

```bash
bash scripts/build_llama.sh
export PATH="$PWD/inference/llama.cpp/build/bin:$PATH"
```

Weights are downloaded separately:

```bash
bash download_model.sh
```
