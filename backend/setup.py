"""
MorphPhysique AI — Setup Script (VESSL-optimized)
Run this once after creating a new workspace.

Usage:
    python setup.py                                          # Full setup
    python setup.py --hf-token YOUR_HF_TOKEN                 # Full setup with HF token
    python setup.py --install                                # Only install packages
    python setup.py --models                                 # Only download models
    python setup.py --ngrok --token YOUR_TOKEN               # Only start ngrok tunnel
    python setup.py --verify                                 # Check everything
"""

import subprocess
import sys
import os
import re
import argparse

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_MODELS_DIR = os.path.join(_SCRIPT_DIR, "models")


def run(cmd, desc=""):
    if desc:
        print(f"\n{'='*50}")
        print(f"  {desc}")
        print(f"{'='*50}")
    subprocess.run(cmd, shell=True, check=True)


def setup_disk_layout():
    """Move large files to main disk (/opt) to avoid /root 100GB limit"""
    print(f"\n{'='*50}")
    print("  Setting up disk layout")
    print(f"{'='*50}")

    # Move HF cache to main disk if it's still on /root
    if os.path.isdir("/root/.cache") and not os.path.islink("/root/.cache"):
        print("  Moving .cache to /opt (main disk)...")
        os.makedirs("/opt/hf_cache", exist_ok=True)
        subprocess.run("mv /root/.cache/* /opt/hf_cache/ 2>/dev/null; rm -rf /root/.cache", shell=True)
        os.symlink("/opt/hf_cache", "/root/.cache")
        print("  ✓ .cache moved to /opt/hf_cache")
    elif not os.path.exists("/root/.cache"):
        os.makedirs("/opt/hf_cache", exist_ok=True)
        os.symlink("/opt/hf_cache", "/root/.cache")
        print("  ✓ .cache symlinked to /opt/hf_cache")
    else:
        print("  ✓ .cache already on main disk")

    # Move models to main disk if needed
    if os.path.isdir("/root/models") and not os.path.islink("/root/models"):
        print("  Moving models to /opt...")
        os.makedirs("/opt/models", exist_ok=True)
        subprocess.run("mv /root/models/* /opt/models/ 2>/dev/null; rm -rf /root/models", shell=True)
        os.symlink("/opt/models", "/root/models")
        print("  ✓ models moved to /opt/models")
    elif os.path.islink("/root/models"):
        # Symlink exists — make sure the target directory actually exists
        os.makedirs("/opt/models", exist_ok=True)
        print("  ✓ models symlinked to /opt/models")
    else:
        os.makedirs("/opt/models", exist_ok=True)
        os.symlink("/opt/models", "/root/models")
        print("  ✓ models symlinked to /opt/models")

    # Setup insightface on main disk
    if os.path.isdir("/root/.insightface") and not os.path.islink("/root/.insightface"):
        subprocess.run("rm -rf /root/.insightface", shell=True)
    if not os.path.islink("/root/.insightface"):
        os.makedirs("/opt/insightface/models", exist_ok=True)
        os.symlink("/opt/insightface", "/root/.insightface")
        print("  ✓ .insightface symlinked to /opt/insightface")
    else:
        # Symlink exists — make sure the target directory actually exists
        os.makedirs("/opt/insightface/models", exist_ok=True)
        print("  ✓ .insightface symlinked to /opt/insightface")

    # Check space
    result = subprocess.run("df -h /root | tail -1", shell=True, capture_output=True, text=True)
    print(f"  /root disk: {result.stdout.strip()}")


def install_system_deps():
    # libcudnn9-cuda-12: required by onnxruntime-gpu>=1.19 (cuDNN 8 ships on this image but ORT 1.23 needs 9)
    # unzip: needed to extract buffalo_l.zip
    run("apt-get update && apt-get install -y libgl1-mesa-glx libglib2.0-0 libegl1 libgles2 libcudnn9-cuda-12 unzip",
        "Installing system dependencies")


def install_pip_packages():
    req = os.path.join(_SCRIPT_DIR, "requirements.txt")
    run(f"pip install -r {req}",
        "Installing Python packages")
    # insightface declares `onnxruntime` (CPU-only) as a dependency, which shadows onnxruntime-gpu
    # and blocks CUDA providers. Remove the CPU build and force the GPU one back.
    run("pip uninstall onnxruntime -y || true && pip install --force-reinstall onnxruntime-gpu==1.23.2",
        "Fixing onnxruntime: removing CPU build, keeping GPU build")


def download_models(hf_token=None):
    print(f"\n{'='*50}")
    print("  Downloading AI models")
    print(f"{'='*50}")

    # Set HF token and disable XET (causes IO errors on VESSL)
    token = hf_token or os.environ.get("HF_TOKEN", "")
    if token:
        os.environ["HF_TOKEN"] = token
        print("  Using HuggingFace token for faster downloads")
    else:
        print("  No HF_TOKEN set — downloading as anonymous (may be slower)")

    os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"
    os.environ["HF_HUB_DISABLE_XET"] = "1"

    from huggingface_hub import hf_hub_download

    os.makedirs(_MODELS_DIR, exist_ok=True)

    print("  Downloading InsightFace inswapper_128 (face swap model)...")
    hf_hub_download(
        repo_id="ezioruan/inswapper_128.onnx",
        filename="inswapper_128.onnx",
        local_dir=_MODELS_DIR,
    )

    print("  ✓ All HuggingFace models downloaded!")


def download_pose_model():
    """Download MediaPipe Pose Landmarker model (~5.6MB)"""
    dest = "/tmp/pose_landmarker.task"
    if os.path.exists(dest):
        print("  ✓ MediaPipe pose model already exists")
        return
    print("  Downloading MediaPipe Pose Landmarker model...")
    subprocess.run(
        f"wget -q -O {dest} "
        "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
        "pose_landmarker_lite/float16/1/pose_landmarker_lite.task",
        shell=True, check=True
    )
    print("  ✓ Pose model downloaded!")


def download_buffalo_l():
    """Download InsightFace buffalo_l model manually (auto-download often fails)"""
    print(f"\n{'='*50}")
    print("  Downloading InsightFace buffalo_l")
    print(f"{'='*50}")

    buffalo_dir = "/opt/insightface/models/buffalo_l"
    if os.path.exists(os.path.join(buffalo_dir, "det_10g.onnx")):
        print("  ✓ buffalo_l already exists, skipping")
        return

    os.makedirs(buffalo_dir, exist_ok=True)

    print("  Downloading buffalo_l.zip (~275MB)...")
    subprocess.run(
        "wget -q -O /tmp/buffalo_l.zip https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip",
        shell=True, check=True
    )

    print("  Extracting...")
    import zipfile
    with zipfile.ZipFile("/tmp/buffalo_l.zip", "r") as z:
        z.extractall(buffalo_dir)

    os.remove("/tmp/buffalo_l.zip")
    print("  ✓ buffalo_l installed!")


def cache_sd_model():
    print(f"\n{'='*50}")
    print("  Caching Stable Diffusion model (~4GB)")
    print(f"{'='*50}")

    os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"
    os.environ["HF_HUB_DISABLE_XET"] = "1"

    from diffusers import StableDiffusionPipeline
    pipe = StableDiffusionPipeline.from_pretrained("SG161222/Realistic_Vision_V4.0_noVAE")
    del pipe
    print("  ✓ SD model cached!")


def start_ngrok(token=None):
    print(f"\n{'='*50}")
    print("  Starting ngrok tunnel")
    print(f"{'='*50}")

    from pyngrok import ngrok

    if token:
        ngrok.set_auth_token(token)
    else:
        env_token = os.environ.get("NGROK_AUTH_TOKEN", "")
        if env_token:
            ngrok.set_auth_token(env_token)
        else:
            print("  ERROR: No ngrok auth token provided.")
            print("  Get one free at: https://dashboard.ngrok.com/get-started/your-authtoken")
            print("  Usage: python setup.py --ngrok --token YOUR_TOKEN")
            sys.exit(1)

    public_url = str(ngrok.connect(8000))

    # Auto-patch morph.html so the user doesn't have to edit it manually
    morph_html = os.path.join(_SCRIPT_DIR, "..", "morph.html")
    morph_html = os.path.abspath(morph_html)
    if os.path.exists(morph_html):
        with open(morph_html, "r", encoding="utf-8") as f:
            html = f.read()
        html = re.sub(r'const API_URL = ".*?"', f'const API_URL = "{public_url}"', html)
        with open(morph_html, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  ✓ morph.html API_URL updated automatically")
    else:
        print(f"  ⚠  morph.html not found — set API_URL manually in morph.html")

    print(f"\n{'='*50}")
    print(f"  YOUR PUBLIC API URL: {public_url}")
    print(f"{'='*50}")
    print(f"\n  morph.html has been updated automatically.")
    print(f"  In a NEW terminal tab run:")
    print(f"  cd {_SCRIPT_DIR} && export HF_HUB_DISABLE_XET=1 && uvicorn app:app --host 0.0.0.0 --port 8000\n")


def verify():
    print(f"\n{'='*50}")
    print("  Verifying setup")
    print(f"{'='*50}")

    import torch
    print(f"  PyTorch: {torch.__version__}")
    print(f"  CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"  GPU: {torch.cuda.get_device_name(0)}")
        vram = torch.cuda.get_device_properties(0).total_mem / 1e9
        print(f"  VRAM: {vram:.1f} GB")

    # Check models
    all_ok = True
    checks = [
        (os.path.join(_MODELS_DIR, "inswapper_128.onnx"), "InsightFace inswapper_128"),
    ]
    for path, name in checks:
        if os.path.exists(path):
            print(f"  ✓ {name}")
        else:
            print(f"  ✗ {name} MISSING — run: python setup.py --models")
            all_ok = False

    # Check buffalo_l
    buffalo_path = "/opt/insightface/models/buffalo_l/det_10g.onnx"
    if os.path.exists(buffalo_path):
        print(f"  ✓ InsightFace buffalo_l")
    else:
        print(f"  ✗ InsightFace buffalo_l MISSING")
        all_ok = False

    # Check onnxruntime GPU providers
    try:
        import onnxruntime as ort
        providers = ort.get_available_providers()
        if "CUDAExecutionProvider" in providers:
            print(f"  ✓ onnxruntime CUDA provider available")
        else:
            print(f"  ✗ CUDAExecutionProvider MISSING — providers: {providers}")
            print(f"    Fix: pip uninstall onnxruntime -y && pip install --force-reinstall onnxruntime-gpu==1.23.2")
            all_ok = False
    except Exception as e:
        print(f"  ✗ onnxruntime import failed: {e}")
        all_ok = False

    # Check symlinks
    for link in ["/root/.cache", "/root/.insightface"]:
        if os.path.islink(link):
            print(f"  ✓ {link} -> {os.readlink(link)}")
        else:
            print(f"  ⚠ {link} is not a symlink")

    # Check disk
    result = subprocess.run("df -h /root | tail -1", shell=True, capture_output=True, text=True)
    print(f"  /root disk: {result.stdout.strip()}")

    if all_ok:
        print("\n  ✓ Setup complete! Ready to run.")
        print("  Next steps:")
        print("    1. python setup.py --ngrok --token YOUR_NGROK_TOKEN")
        print("    2. (new tab) export HF_HUB_DISABLE_XET=1 && uvicorn app:app --host 0.0.0.0 --port 8000")
    else:
        print("\n  ✗ Some components are missing. Check above.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MorphPhysique AI Setup")
    parser.add_argument("--install", action="store_true", help="Install packages only")
    parser.add_argument("--models", action="store_true", help="Download models only")
    parser.add_argument("--cache", action="store_true", help="Cache SD model only")
    parser.add_argument("--ngrok", action="store_true", help="Start ngrok tunnel only")
    parser.add_argument("--token", type=str, help="ngrok auth token")
    parser.add_argument("--hf-token", type=str, help="HuggingFace auth token")
    parser.add_argument("--verify", action="store_true", help="Verify setup")
    args = parser.parse_args()

    # If no flags, run full setup
    run_all = not any([args.install, args.models, args.cache, args.ngrok, args.verify])

    if run_all:
        setup_disk_layout()

    if run_all or args.install:
        install_system_deps()
        install_pip_packages()

    if run_all:
        setup_disk_layout()  # Run again after pip installs (may create new dirs)

    if run_all or args.models:
        setup_disk_layout()  # ensure symlink targets exist before downloading
        download_models(hf_token=getattr(args, 'hf_token', None))
        download_buffalo_l()
        download_pose_model()

    if run_all or args.cache:
        cache_sd_model()

    if run_all or args.verify:
        verify()

    if args.ngrok:
        start_ngrok(args.token)

    if run_all:
        print(f"\n{'='*50}")
        print("  SETUP COMPLETE!")
        print(f"{'='*50}")
        print("\nNext steps:")
        print("  1. python setup.py --ngrok --token YOUR_NGROK_TOKEN")
        print("  2. (new tab) export HF_HUB_DISABLE_XET=1 && uvicorn app:app --host 0.0.0.0 --port 8000")