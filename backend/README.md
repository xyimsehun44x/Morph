# MorphPhysique AI

An AI-powered body transformation visualizer. Upload your photo and a target physique — the app composites your face onto the target body and generates a personalized workout and diet plan based on the difference between your current and goal physique.

---

## How It Works

1. User uploads their own face photo and a target physique photo
2. The backend swaps the user's face onto the target body using InsightFace
3. Gemini 2.5 Flash analyzes the physique gap and generates a custom workout + meal plan
4. Results are displayed side-by-side with a Genetic Reality Score

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI + uvicorn (Python) |
| Face swap | InsightFace `inswapper_128.onnx` |
| Body generation (preset mode) | Stable Diffusion 1.5 (`Realistic_Vision_V4.0_noVAE`) |
| Pose analysis | MediaPipe Pose Landmarker |
| Plan generation | Gemini 2.5 Flash (`google-genai`) |
| Tunnel | pyngrok (exposes port 8000 to the internet) |
| Frontend | Vanilla HTML/CSS/JS |

---

## Requirements

- VESSL GPU workspace (Ubuntu 22.04, CUDA 12.1)
- Python 3.10
- A GPU with at least 8 GB VRAM
- Internet access for model downloads
- A Gemini API key (free tier works)
- An ngrok auth token (free account works)

---

## Before You Start

You need two keys — both have been provided to you:

| Key | Looks like | Used for |
|---|---|---|
| Gemini API key | `AIzaSy...` | Workout/diet plan generation |
| ngrok auth token | `2abc...` | Exposing the server to the browser |

Substitute them wherever you see `YOUR_GEMINI_API_KEY` and `YOUR_NGROK_TOKEN` in the commands below.

---

## Setup

### Step 1 — Run the setup script

Open a terminal in the **root of the repository** and run:

```bash
export GEMINI_API_KEY=AIzaSy...YOUR_KEY_HERE
python backend/setup.py
```

This single command does everything in order:

1. Sets up disk symlinks (`/root/models`, `/root/.insightface`, `/root/.cache` → `/opt/`) for VESSL disk limits
2. Installs system packages including `libcudnn9-cuda-12` (required for GPU inference)
3. Installs all Python packages from `requirements.txt`
4. Removes the CPU-only `onnxruntime` package that conflicts with `onnxruntime-gpu`
5. Downloads `inswapper_128.onnx` (~529 MB) from HuggingFace
6. Downloads `buffalo_l` face detection models (~275 MB) from InsightFace
7. Downloads the MediaPipe Pose Landmarker model (~5 MB)
8. Caches the Stable Diffusion model (~4 GB) from HuggingFace
9. Runs a verification check

Full setup takes approximately **10–15 minutes** depending on download speed.

To verify everything installed correctly:

```bash
python backend/setup.py --verify
```

---

### Step 2 — Start the ngrok tunnel

Run this in **Terminal 1**:

```bash
python backend/setup.py --ngrok --token YOUR_NGROK_TOKEN
```

This will:
- Open a public HTTPS tunnel to port 8000
- **Automatically update `morph.html`** with the live URL — no manual editing required

You will see output like:

```
==================================================
  YOUR PUBLIC API URL: https://xxxx-xx-xx-xxx-xx.ngrok-free.app
==================================================
  morph.html has been updated automatically.
```

---

### Step 3 — Start the server

Open a **new terminal tab (Terminal 2)** and run:

```bash
cd backend
export GEMINI_API_KEY=AIzaSy...YOUR_KEY_HERE
export HF_HUB_DISABLE_XET=1
uvicorn app:app --host 0.0.0.0 --port 8000
```

Wait until you see:

```
INFO:     Application startup complete.
```

The server loads three models on startup (InsightFace, face swapper, Stable Diffusion pipeline). This takes about **30–60 seconds**.

---

### Step 4 — Open the app

Open `morph.html` directly in a browser (double-click the file, or serve it via any static file server).

The landing page is `index.html`. From there, click **Try It Now** to go to `morph.html`.

---

## Each Time You Restart the Workspace

The ngrok URL changes every session. Re-run Steps 2 and 3 each time:

```bash
# Terminal 1
python backend/setup.py --ngrok --token YOUR_NGROK_TOKEN

# Terminal 2
cd backend && export GEMINI_API_KEY=AIzaSy...YOUR_KEY_HERE && export HF_HUB_DISABLE_XET=1 && uvicorn app:app --host 0.0.0.0 --port 8000
```

If the workspace was fully reset (models deleted), re-run Step 1 first.

---

## Using the App

### Quick morph (no stats required)

1. Click **Step 1 — Upload Photos**
2. Upload your face photo under **Your Photo**
3. Upload a target physique photo under **Target Physique**
4. Click **Generate My Morph →**
5. The result appears in 20–40 seconds

### Full morph + plan (requires body stats)

1. Fill in **Height (cm)**, **Weight (kg)**, and **Body Fat %** in addition to the two photos
2. Optionally enter the target person's name (e.g. `Chris Bumstead`) for better analysis
3. Click **Generate My Morph + Plan →**
4. The result includes:
   - Before / After side-by-side images
   - Genetic Reality Score (0–100) with reasoning
   - Physique analysis (muscle groups, proportions)
   - 8-week periodized workout plan
   - Weekly meal plan with macros
   - Key coaching tips

### Tips for best results

- Use a **front-facing, well-lit photo** with your full torso visible
- The target physique photo should also be **front-facing** for accurate face placement
- Supported formats: JPG, PNG, HEIF/HEIC (iPhone photos work directly)
- Body fat % can be estimated visually — a rough number is fine

---

## Project Structure

```
repo root/
├── index.html              # Landing page
├── morph.html              # Main app UI
├── before.png / after.jpg  # Demo images
└── backend/
    ├── app.py              # FastAPI backend
    ├── requirements.txt    # Python dependencies
    ├── setup.py            # One-command setup script
    ├── README.md           # This file
    └── models/
        └── inswapper_128.onnx  # Downloaded by setup.py (~529 MB)
```

**Disk layout (VESSL-specific):**

On VESSL, large model files are stored in `/opt/` and symlinked into `/root/` to stay within the 100 GB root disk limit:

| Symlink | Target | Contents |
|---|---|---|
| `/root/.cache` | `/opt/hf_cache` | HuggingFace model cache (~4 GB SD model) |
| `/root/.insightface` | `/opt/insightface` | `buffalo_l` detection models (~275 MB) |

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Health check |
| `GET` | `/health` | Detailed model load status |
| `POST` | `/morph/custom` | Face swap onto a custom target photo |
| `POST` | `/morph/full` | Face swap + physique analysis + plan generation |
| `POST` | `/morph/preset` | Face swap onto a generated preset body type |
| `POST` | `/plan` | Generate workout + meal plan only (no image) |

---

## Troubleshooting

**Server crashes on startup with `FileNotFoundError: /root/.insightface/models`**

The symlink target directory is missing. Run:

```bash
python backend/setup.py --models
```

---

**`CUDAExecutionProvider` not available / face swap runs slowly**

The CPU-only `onnxruntime` package is shadowing `onnxruntime-gpu`. Fix it:

```bash
pip uninstall onnxruntime -y && pip install --force-reinstall onnxruntime-gpu==1.23.2
```

---

**`libcudnn.so.9: cannot open shared object file`**

cuDNN 9 is not installed. The VESSL image ships cuDNN 8 by default. Fix it:

```bash
apt-get install -y libcudnn9-cuda-12
```

---

**`inswapper_128.onnx` not found on server startup**

The face swap model was not downloaded. Run:

```bash
python backend/setup.py --models
```

---

**Gemini plan/analysis returns an error**

Make sure `GEMINI_API_KEY` is exported before starting the server:

```bash
export GEMINI_API_KEY=AIzaSy...YOUR_KEY_HERE
uvicorn app:app --host 0.0.0.0 --port 8000
```

---

**morph.html shows a connection error**

The ngrok tunnel is not running or the URL is stale. Re-run:

```bash
python backend/setup.py --ngrok --token YOUR_NGROK_TOKEN
```

This automatically updates `morph.html` with the new URL. Then refresh the page.

---

**The before photo does not appear on mobile**

This is a known issue fixed in the current version of `morph.html`. The fix uses `URL.createObjectURL()` instead of `FileReader.readAsDataURL()` to avoid base64 size limits on mobile browsers.
