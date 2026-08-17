# SSH workflow: Mac → physical i5 → profiler

Yes — **SSH works with the RAM cap.** The profiler script uses `sudo systemd-run` (system scope), which is reliable over SSH. (Plain `systemd-run --user` often fails on headless SSH until you enable linger; we avoid that.)

Assume:
- Mac = your daily machine  
- `i5-host` = the Ubuntu box (8th-gen, 16 GB)  
- user can `sudo`

---

## A. One-time on the i5 (SSH in once)

```bash
ssh you@i5-host
```

```bash
sudo apt update
sudo apt install -y build-essential cmake git curl python3-venv python3-pip \
  libopenblas-dev pkg-config rsync

# passwordless sudo for profiling (optional but nice)
# sudo visudo  →  you ALL=(ALL) NOPASSWD: /usr/bin/systemd-run
```

Leave that SSH session open or exit — next steps can be from the Mac.

---

## B. Copy the code from your Mac

**Option 1 — rsync (recommended)**

On the Mac:

```bash
rsync -av --progress \
  --exclude .venv \
  --exclude 'model/*.gguf' \
  --exclude 'model/candidates/*.gguf' \
  --exclude '**/__pycache__' \
  --exclude .git \
  --exclude data/chats.db \
  ~/Desktop/Theoria/ you@i5-host:~/Theoria/
```

Do **not** copy GGUFs over Wi-Fi if the i5 has internet — download there instead.

**Option 2 — git**

```bash
# on i5
git clone <your-public-or-private-repo-url> ~/Theoria
cd ~/Theoria
```

---

## C. First-time build on the i5 (still over SSH)

```bash
ssh you@i5-host
cd ~/Theoria

python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
pip install "git+https://github.com/Africa-Deep-Tech-Foundation/adtc-profiler.git"

bash scripts/build_llama.sh      # compiles llama-bench / llama-server — several minutes
bash download_model.sh           # ~1.7 GB GGUF into model/
# optional: bash scripts/setup_lean.sh
```

---

## D. Day-to-day loop

### 1. Push code changes from Mac

```bash
rsync -av --progress \
  --exclude .venv --exclude 'model/*.gguf' --exclude 'model/candidates/*.gguf' \
  --exclude '**/__pycache__' --exclude data/chats.db \
  ~/Desktop/Theoria/ you@i5-host:~/Theoria/
```

### 2. SSH and work

```bash
ssh you@i5-host
cd ~/Theoria
source .venv/bin/activate
```

### 3. Optional: UI over SSH tunnel (browse from Mac)

On the **Mac**:

```bash
ssh -L 8080:127.0.0.1:8080 you@i5-host
```

On the **i5** (same or second session):

```bash
cd ~/Theoria && source .venv/bin/activate
python -m theoria.server
```

On the Mac open: http://127.0.0.1:8080  
(tunnel forwards to the i5’s server)

### 4. Profile under 8 GB ceiling (the important part)

```bash
cd ~/Theoria
source .venv/bin/activate

# Fast iteration
bash scripts/profile_i5.sh --skip-install

# Before Gate 1 submit
bash scripts/profile_i5.sh --skip-install --full
```

What happens:
1. Bake-off at **4 threads** → `bakeoff_i5.txt`
2. `adtc-profiler` inside **`sudo systemd-run`** with `MemoryMax=7500M` and `CPUQuota=400%` → `submission.json`

SSH stays connected the whole time. If sudo asks for a password, type it once when prompted.

**Pass bar:** in `submission.json`, `memory.peak_rss_mb` **&lt; 7000**.

```bash
python3 -c "import json; d=json.load(open('submission.json')); print(d.get('memory', d))"
```

---

## E. Does the RAM cap break SSH?

No. The cap applies only to the **profiler process tree**, not to `sshd` or your shell. Your SSH session keeps running even if the profiler OOMs under 7.5 GB (that OOM is useful signal — same as judges).

---

## F. If `sudo systemd-run` fails

```bash
# see the error
sudo systemd-run --scope -p MemoryMax=7500M -p CPUQuota=400% \
  --working-directory=$HOME/Theoria \
  -- /bin/true

# enable linger only if you insist on --user scopes (not required with our script)
sudo loginctl enable-linger $USER
```

Or install Docker and the script will fall back to `docker --memory=7.5g --cpus=4`.

---

## G. Copy results back to the Mac

```bash
# on Mac
scp you@i5-host:~/Theoria/submission.json ~/Desktop/Theoria/
scp you@i5-host:~/Theoria/bakeoff_i5.txt ~/Desktop/Theoria/
```

Then refresh `REPORT.md` with those numbers.

---

## Quick cheat sheet

| Step | Where | Command |
|---|---|---|
| Sync code | Mac | `rsync … ~/Desktop/Theoria/ you@i5-host:~/Theoria/` |
| Shell | Mac | `ssh you@i5-host` |
| Activate | i5 | `cd ~/Theoria && source .venv/bin/activate` |
| UI tunnel | Mac | `ssh -L 8080:127.0.0.1:8080 you@i5-host` |
| Profile | i5 | `bash scripts/profile_i5.sh --skip-install --full` |
| Fetch reports | Mac | `scp you@i5-host:~/Theoria/submission.json .` |
