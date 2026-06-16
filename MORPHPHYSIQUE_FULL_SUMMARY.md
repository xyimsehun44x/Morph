# MorphPhysique AI — Complete Project Summary

## Table of Contents
1. [Project Overview](#1-project-overview)
2. [Course Context](#2-course-context)
3. [Landing Page (Fake Door)](#3-landing-page-fake-door)
4. [Google Apps Script Backend (Data Collection)](#4-google-apps-script-backend)
5. [Visitor Tracking System](#5-visitor-tracking-system)
6. [Email Form & sendMail](#6-email-form--sendmail)
7. [Netlify Deployment](#7-netlify-deployment)
8. [Mobile Responsive CSS](#8-mobile-responsive-css)
9. [Marketing & Distribution](#9-marketing--distribution)
10. [Midterm Presentation](#10-midterm-presentation)
11. [Core AI Implementation](#11-core-ai-implementation)
12. [FastAPI Web App](#12-fastapi-web-app)
13. [Frontend Morph Page](#13-frontend-morph-page)
14. [File Structure](#14-file-structure)
15. [Submission Form Answers](#15-submission-form-answers)
16. [All Code Files](#16-all-code-files)
17. [Google Colab Setup](#17-google-colab-setup-alternative-to-vessl)
18. [ngrok + FastAPI Live Demo](#18-ngrok--fastapi-live-demo-on-colab)
19. [Compute Platform Comparison](#19-compute-platform-comparison)
20. [Additional Lessons](#20-additional-lessons-from-colab-migration)

---

## 1. Project Overview

**MorphPhysique AI** is an AI fitness app concept that:
- Takes a user's face photo + target physique
- Generates a realistic "morphed" image showing what the user could look like
- Provides personalized workout and meal plans based on the morph

**The Core Problem (Visual Ambiguity Gap):**
Most fitness beginners don't know what a realistic transformation looks like on their unique bone structure. They chase genetically impossible goals and lose motivation.

**XyZ Hypothesis:**
> 운동을 시작하려는 사람들(X)은 자신의 체형을 기반으로 AI가 변환된 몸 이미지를 생성해주고 맞춤형 운동/식단 플랜을 제공하는 앱(Y)에 대해 웨이팅 리스트에 이메일을 남길 것이다(Z)

---

## 2. Course Context

**Course:** SW·AI비즈니스응용설계 (2026-1, Yonsei University)

**Midterm:** Fake Door test with action — deploy a landing page, collect real data, analyze results

**Final:** Implement the core function — build the actual AI pipeline

**Grading criteria:**
- 실행력 (25) / 구현력 (25) / 발표논리력 (25) / 완성도 (25)
- 교수 adds 교과적용도 가중곱

---

## 3. Landing Page (Fake Door)

Built on top of **TemplateMo 614 Quantix SaaS** template, completely reskinned for MorphPhysique AI.

**Design changes from original Quantix:**
- Brand: "MorphPhysique" with M icon, orange accent (#FF4D00)
- Font: Bebas Neue for headings (gym/athletic feel)
- Hero: Custom morph comparison mockup (before/after body silhouettes)
- Sections: How It Works (3 steps), Features (5 tabs), Guardrails (3 cards), Waitlist form
- Aspirational phrase: "Be the next cBum. Be the next Karina."
- Before/after images: AI-generated golden anatomy figures (Gemini)

**Key files:**
- `index.html` — main landing page with all tracking code
- `templatemo-quantix-style.css` — restyled CSS with orange theme + mobile responsive
- `templatemo-quantix-script.js` — navbar, tabs, pricing toggle, scroll animations
- `templates.html` — secondary templates page (from original Quantix)
- `morph.html` — the actual AI morph tool page (NEW for final)
- `before.png` / `after.jpg` — AI-generated body type illustrations
- `morph_figures.png` — outline body comparison (earlier version)

**Live URL:** https://morphphysique.netlify.app

---

## 4. Google Apps Script Backend

**Purpose:** CRUD API for Google Sheets — tracks visitors and collects waitlist signups

**Google Sheet:** `db_mvt` with two sheets:
- `visitors` — columns: id, landingUrl, ip, referer, time_stamp, utm, device
- `tab_final` — columns: id, email, advice

**Apps Script URL (deployed):**
```
https://script.google.com/macros/s/AKfycbzt__ZqvXLU8TgT1pOdeebh9XIy2jeX92h0hYUULV3lovjYzIuF0Il6aGR_SewKDqqmyg/exec
```

**Apps Script Code (Code.gs):**

```javascript
function doGet(req) {
    var SHEET_URL = "https://docs.google.com/spreadsheets/d/1PctMF99--Tj_XyFySse8tC_rlyiTJ8MwF5tKHTyQvyM/edit"
    var action    = req.parameter.action;
    var table_req = req.parameter.table;
    var db = SpreadsheetApp.openByUrl(SHEET_URL);
    var table = db.getSheetByName( table_req );
    var ret;

    switch(action) {
        case "read":    ret = Read( req, table ); break;
        case "insert":  ret = Insert( req, table ); break;
        case "update":  ret = Update( req, table ); break;
        case "delete":  ret = Delete( req, table ); break;
        default: break;
    }
    return response().jsonp(req, ret);
}

function Insert( request, table ) {
    var errors = [];
    var last_col     = table.getLastColumn();
    var first_row    = table.getRange(1, 1, 1, last_col).getValues();
    var headers      = first_row.shift();
    var data         = JSON.parse( request.parameter.data );

    // Send email if it's a waitlist submission
    if (request.parameter.table == "tab_final") {
        sendMail(data.email);
    }

    var new_row;
    var result = {};
    try {
        new_row = prepareRow( data, headers );
        table.appendRow( new_row );
        result.success = true;
        result.data = data;
    } catch ( error ) {
        result.success = false;
        result.data = { error: error.messsage };
    }
    return result;
}

// ... Read, Update, Delete, response, _read, prepareRow functions ...

function sendMail(email) {
    try {
        MailApp.sendEmail({
            to: email,
            subject: "감사합니다. 알려드리겠습니다.",
            htmlBody: "<html> <p> 감사합니다. 많은 도움이 되었습니다. </p> </html>"
        })
    } catch(e) {
        console.log(e);
    }
}
```

**Important:** After editing Apps Script, must 배포 관리 → 새 버전으로 배포 (Google caches old versions).

---

## 5. Visitor Tracking System

All tracking code is in `index.html` inline scripts. Fires on page load via axios GET to Apps Script.

**Data collected per visit:**

| Field | How it's collected |
|---|---|
| id | Cookie-based 6-char hash (getUVfromCookie), persists 180 days |
| landingUrl | `window.location.href` |
| ip | External service: `https://jsonip.com?format=jsonp&callback=getIP` |
| referer | `document.referrer` |
| time_stamp | Custom `getTimeStamp()` function (YYYY-MM-DD HH:MM:SS) |
| utm | `URLSearchParams(location.search).get("utm")` |
| device | User-agent regex check for mobile keywords |

**Cookie functions:**
```javascript
function getCookieValue(name) { ... }
function setCookieValue(name, value, days) { ... }
function getUVfromCookie() {
    const hash = Math.random().toString(36).substring(2, 8).toUpperCase();
    const existingHash = getCookieValue("user");
    if (!existingHash) {
        setCookieValue("user", hash, 180);
        return hash;
    }
    return existingHash;
}
```

**UTM tracking links used:**
- Instagram: `https://morphphysique.netlify.app?utm=instagram`
- Everytime: `https://morphphysique.netlify.app?utm=everytime`
- KakaoTalk: `https://morphphysique.netlify.app?utm=kakao`
- Reddit: `https://morphphysique.netlify.app?utm=reddit`

---

## 6. Email Form & sendMail

**Form HTML** (in waitlist section of index.html):
```html
<input id="submit-email" type="email" placeholder="you@example.com" />
<textarea id="submit-advice" placeholder="Tell us what features matter most..."></textarea>
<button id="submit-btn">Get Early Access →</button>
```

**Submit handler:**
```javascript
$("#submit-btn").on("click", function () {
    // Validate email
    // Build JSON: { id, email, advice }
    // $.busyLoadFull("show")
    // axios.get(addrScript + '?action=insert&table=tab_final&data=' + finalData)
    // On success: clear form, hide loader, show popup
});
```

**Popup (simple-popup library):** Dark themed "Access Confirmed" dialog with checkmark icon.

**Email:** Apps Script's `sendMail()` sends a thank-you email to each registrant.

**Libraries used:**
- jQuery (for selectors, busy-load, simple-popup)
- axios (for HTTP requests to Apps Script)
- busy-load (loading spinner overlay)
- simple-popup (confirmation popup)

**Script load order in `<head>` (matters!):**
```html
<script src="jquery-latest.min.js"></script>
<script src="simple-popup.min.js"></script>  <!-- needs jQuery -->
<script src="axios.min.js"></script>
<script src="busy-load/app.min.js"></script>  <!-- needs jQuery -->
```

---

## 7. Netlify Deployment

**Site URL:** https://morphphysique.netlify.app
**Netlify project:** `morphphysique`
**Deploy method:** Netlify Drop (drag and drop folder)

**To redeploy:** Go to Netlify dashboard → Project overview → drag updated folder to "Production deploys" area.

**Files deployed:**
- index.html, morph.html, templates.html
- templatemo-quantix-style.css, templatemo-quantix-script.js
- before.png, after.jpg, morph_figures.png

---

## 8. Mobile Responsive CSS

Added mobile breakpoints in `templatemo-quantix-style.css` for MorphPhysique-specific sections:

**Key mobile fixes:**
- Hero: overflow-x hidden, reduced padding
- Morph window: removed 3D tilt, forced max-width 100%
- Morph comparison: fixed grid columns (1fr 36px 1fr)
- Steps/guardrails grid: single column on mobile
- Waitlist form: tighter padding
- Trusted logos: flex-wrap

**Navbar scroll border fix:** Changed from `var(--border-subtle)` (white) to `rgba(255, 77, 0, 0.08)` (invisible orange).

**Hero grid lines fix:** Pushed `hero::after` background-image grid down 80px and reduced opacity from 0.035 to 0.025.

---

## 9. Marketing & Distribution

**Deployed to:**

1. **Everytime (에브리타임):**
   - Post URL: `https://everytime.kr/442356/v/408756892`
   - Title: "운동 목표 있는데 어디서부터 시작해야 할지 모르는 분들 👀"
   - Mentioned SW·AI비즈니스응용설계 수업 과제

2. **Instagram Story:**
   - Story URL: `https://www.instagram.com/stories/im.sehun__/3885101854682460544`
   - Caption: "Made an AI fitness app for uni. Check it out! 💪🙏"

3. **KakaoTalk Open Chat:**
   - URL: `https://open.kakao.com/o/g9zDrtsi`

4. **Reddit r/workout:**
   - Title: "App that shows you what your body could actually look like after training before you even start"
   - Got feedback from PindaPanter (Top 1% Commenter) and AwayhKhkhk — critical but useful

**Reddit feedback (key takeaways for presentation):**
- "You can't gauge genetic potential from a picture" → led to Genetic Reality Score guardrail
- "InBody is not accurate" → led to DEXA integration idea
- "How do you measure that from a photo?" → led to two-step pipeline approach

---

## 10. Midterm Presentation

**5-minute structure:**

**Part 1 — Problem & Idea (1:30):**
- Visual Ambiguity Gap explanation
- Show the website live
- "cBum처럼 될 수 있을까?" hook

**Part 2 — Data & Reactions (2:00):**
- Show DB data (visitors sheet, tab_final sheet)
- Quote real feedback:
  - "막연히 상상만 하던 '살 빠진 나'의 모습을 보여줌으로써, 운동 욕구에 긍정적인 영향을 줄 것 같습니다"
  - Instagram DM: "사이트가 꽤 괜찮다, 후기나 신뢰 요소가 있으면 좋겠다"
  - Reddit criticism: "결국 MS Paint로 얼굴 합성하는 것과 다를 게 없다"

**Part 3 — Insights (1:30):**
1. 신뢰와 개인정보 보호가 최우선 — users worried about photo uploads
2. "AI Slop"을 피해야 함 — need scientific grounding, not just face paste

---

## 11. Core AI Implementation

### Environment Setup (VESSL AI)

**Workspace:** yonsei-ai-gpu cluster, gpu-1 resource (RTX 3090, 24GB VRAM)

**Full setup script:**
```bash
# System deps
apt-get update && apt-get install -y libgl1-mesa-glx libglib2.0-0

# PyTorch
pip install torch==2.4.0 torchvision==0.19.0 --index-url https://download.pytorch.org/whl/cu121

# AI packages
pip install transformers==4.44.2 diffusers==0.30.3
pip install insightface onnxruntime-gpu
pip install accelerate safetensors peft
pip install opencv-python pillow
pip install fastapi uvicorn python-multipart
pip install git+https://github.com/tencent-ailab/IP-Adapter.git

# Download models
python -c "
from huggingface_hub import hf_hub_download
hf_hub_download(repo_id='h94/IP-Adapter-FaceID', filename='ip-adapter-faceid_sd15.bin', local_dir='./models')
hf_hub_download(repo_id='h94/IP-Adapter-FaceID', filename='ip-adapter-faceid_sd15_lora.safetensors', local_dir='./models')
hf_hub_download(repo_id='ezioruan/inswapper_128.onnx', filename='inswapper_128.onnx', local_dir='./models')
print('All models downloaded!')
"

# Pre-cache SD model
python -c "
from diffusers import StableDiffusionPipeline
pipe = StableDiffusionPipeline.from_pretrained('SG161222/Realistic_Vision_V4.0_noVAE')
print('SD model cached!')
"
```

### Approach Evolution

**Attempt 1: IP-Adapter FaceID direct generation** (`test_morph.py`)
- Used IP-Adapter to generate face + body together
- Result: Uncanny valley, face didn't look like user
- ❌ Abandoned

**Attempt 2: Two-step (generate body + face swap)** (`test_faceswap.py`)
- Step 1: SD generates clean muscular body (no face constraints)
- Step 2: InsightFace inswapper swaps user's face onto generated body
- Result: Much better, but basic
- ⚠️ Improved in next version

**Attempt 3: Enhanced pipeline with body types + edge blending** (`test_enhanced.py`)
- Three body type presets: lean, athletic, muscular
- Face swap with smooth edge blending
- Skin tone matching
- ✅ **This is the working pipeline**

### Working Pipeline (test_enhanced.py)

```
User face photo
    ↓
InsightFace: extract face embedding + face data
    ↓
Stable Diffusion (RealisticVision V4): generate body image for selected type
    ↓
InsightFace inswapper: swap user's face onto generated body
    ↓
Post-processing: edge blending (elliptical mask + Gaussian blur)
    ↓
Output: final_lean.png / final_athletic.png / final_muscular.png
```

### Body Type Presets

```python
body_types = {
    "lean": {
        "prompt": "portrait photo of a young asian man with lean toned body, standing in gym, front view, wearing gray tank top, slim athletic build, visible but not bulky muscles, soft natural lighting, sharp focus, raw photo, 8k uhd, looking at camera",
        "seed": 100,
    },
    "athletic": {
        "prompt": "portrait photo of a young asian man with athletic muscular body, standing in gym, front view, wearing gray tank top, broad shoulders, defined arms, medium muscle mass, soft natural lighting, sharp focus, raw photo, 8k uhd, looking at camera",
        "seed": 300,
    },
    "muscular": {
        "prompt": "portrait photo of a young asian man with very muscular body, standing in gym, front view, wearing gray tank top, large shoulders, big arms, visible veins, bodybuilder physique, soft natural lighting, sharp focus, raw photo, 8k uhd, looking at camera",
        "seed": 777,
    },
}

negative_prompt = "deformed, ugly, bad anatomy, extra limbs, blurry, cartoon, anime, painting, disfigured, mutated, extra fingers, plastic skin, text, watermark, crop top"
```

### Models Used

| Model | Purpose | Size |
|---|---|---|
| SG161222/Realistic_Vision_V4.0_noVAE | Body image generation (SD 1.5) | ~4GB |
| insightface buffalo_l | Face detection + embedding extraction | ~300MB |
| inswapper_128.onnx | Face swapping | ~554MB |
| ip-adapter-faceid_sd15.bin | (Not used in final pipeline) | ~97MB |

---

## 12. FastAPI Web App

**File: `app.py`**

**Architecture:**
```
Frontend (morph.html on Netlify) 
    → POST /morph (face photo + body_type)
    → FastAPI on VESSL (GPU server)
    → Returns base64 PNG image
```

**Endpoints:**
- `GET /` — health check
- `GET /health` — detailed status (GPU available, models loaded)
- `POST /morph` — accepts face photo upload + body_type form field, returns base64 image

**Key design decisions:**
- Models loaded once at startup (`@app.on_event("startup")`)
- CORS enabled for all origins (frontend on different domain)
- Images processed in memory, never saved to disk
- Returns base64 encoded PNG in JSON response

**Run command:**
```bash
python app.py
# Server starts on 0.0.0.0:8000
```

---

## 13. Frontend Morph Page

**File: `morph.html`**

**User flow:**
1. Upload face photo (drag or click)
2. Select body type (lean / athletic / muscular)
3. Click "Generate My Morph"
4. See loading spinner (~20-30 seconds)
5. See before/after comparison

**Key features:**
- File preview before upload
- Body type selector with icons
- Loading state with spinner
- Error handling
- "Try Again" reset button
- Responsive (mobile-friendly)

**Connection to backend:**
```javascript
const API_URL = "http://YOUR_VESSL_URL:8000";  // Change this

const formData = new FormData();
formData.append('face', selectedFile);
formData.append('body_type', selectedBodyType);

const response = await fetch(`${API_URL}/morph`, {
    method: 'POST',
    body: formData,
});
```

**For demo/presentation without live VESSL:**
Pre-generate results and modify morph.html to show them directly (demo mode).

---

## 14. File Structure

```
morphphysique/
├── frontend/                        ← Deploy to Netlify
│   ├── index.html                   ← Landing page with tracking
│   ├── morph.html                   ← AI morph tool page
│   ├── templates.html               ← Secondary page
│   ├── templatemo-quantix-style.css ← Restyled CSS
│   ├── templatemo-quantix-script.js ← UI interactions
│   ├── before.png                   ← Yellow figure (before)
│   ├── after.jpg                    ← Yellow figure (after)
│   └── morph_figures.png            ← Outline figures (earlier version)
│
├── backend/                         ← Run on VESSL GPU
│   ├── app.py                       ← FastAPI server
│   ├── test_enhanced.py             ← Standalone test script
│   ├── models/
│   │   ├── ip-adapter-faceid_sd15.bin
│   │   ├── ip-adapter-faceid_sd15_lora.safetensors
│   │   └── inswapper_128.onnx
│   └── requirements.txt
│
├── results/                         ← Pre-generated for demo
│   ├── input_face.jpg
│   ├── final_lean.png
│   ├── final_athletic.png
│   └── final_muscular.png
│
└── README.md
```

---

## 15. Submission Form Answers

### Midterm Submission

| Field | Answer |
|---|---|
| 아이디어 제목 | MorphPhysique AI |
| 문제정의 | 운동을 시작하려는 사람들은 자신의 몸이 현실적으로 어떻게 변할지 시각적으로 알 수 없어, 잘못된 목표 설정과 동기 부족으로 쉽게 포기하게 된다. |
| Front 주소 | https://morphphysique.netlify.app/ |
| DB 주소 | (Google Sheets URL, set to 뷰어 access) |
| 홍보 배포처 | https://everytime.kr/442356/v/408756892 / https://www.instagram.com/stories/im.sehun__/3885101854682460544 |
| 배포 제목 | 운동 목표 있는데 어디서부터 시작해야 할지 모르는 분들 👀 / Made an AI fitness app for uni. Check it out! 💪🙏 |
| XyZ 가설 | 운동을 시작하려는 사람들(X)은 자신의 체형을 기반으로 AI가 변환된 몸 이미지를 생성해주고 맞춤형 운동/식단 플랜을 제공하는 앱(Y)에 대해 웨이팅 리스트에 이메일을 남길 것이다(Z) |

### Final Submission

| Field | Answer |
|---|---|
| 코어 기술 (시나리오) | 사용자가 자신의 얼굴 사진과 목표 체형 사진을 업로드하면, AI가 사용자의 얼굴 정체성을 유지하면서 목표 체형에 맞게 변환된 이미지를 생성한다. 이때 단순 얼굴 합성이 아니라, 사용자의 실제 골격 구조에 맞게 근육 분포를 조정하여 현실적으로 달성 가능한 체형을 보여준다. 이후 해당 목표 체형과 현재 체형 간의 차이를 분석하여, 사용자 맞춤형 운동 플랜과 식단 플랜을 자동 생성한다. |
| 기술 스택 | Stable Diffusion XL (이미지 생성), IP-Adapter FaceID (얼굴 정체성 보존), ControlNet OpenPose (체형/포즈 제어), MediaPipe Pose (골격 랜드마크 추출), Python FastAPI (백엔드 API), Next.js (프론트엔드), VESSL/RunPod A100 GPU (AI 추론 서버) |
| 왜 코어 기능인지 | "AI 체형 시뮬레이션"이 코어 기능인 이유는 중간 발표에서 수집한 피드백에서 가장 큰 관심과 의문이 이 기능에 집중되었기 때문. Reddit에서는 "결국 얼굴 합성 아니냐"는 비판, Instagram에서는 "컨셉이 멋지다"는 긍정. AI 체형 시뮬레이션의 현실성을 확보하는 것이 최우선 과제이다. |

---

## 16. All Code Files

### test_enhanced.py (Working AI Pipeline)

```python
import cv2
import torch
import numpy as np
from PIL import Image
from insightface.app import FaceAnalysis
from diffusers import StableDiffusionPipeline, DDIMScheduler
import insightface

print("Step 1: Loading SD pipeline...")
noise_scheduler = DDIMScheduler(
    num_train_timesteps=1000,
    beta_start=0.00085,
    beta_end=0.012,
    beta_schedule="scaled_linear",
    clip_sample=False,
    set_alpha_to_one=False,
    steps_offset=1,
)

pipe = StableDiffusionPipeline.from_pretrained(
    "SG161222/Realistic_Vision_V4.0_noVAE",
    torch_dtype=torch.float16,
    scheduler=noise_scheduler,
    safety_checker=None,
).to("cuda")

body_types = {
    "lean": {
        "prompt": "portrait photo of a young asian man with lean toned body, standing in gym, front view, wearing gray tank top, slim athletic build, visible but not bulky muscles, soft natural lighting, sharp focus, raw photo, 8k uhd, looking at camera",
        "seed": 100,
    },
    "athletic": {
        "prompt": "portrait photo of a young asian man with athletic muscular body, standing in gym, front view, wearing gray tank top, broad shoulders, defined arms, medium muscle mass, soft natural lighting, sharp focus, raw photo, 8k uhd, looking at camera",
        "seed": 300,
    },
    "muscular": {
        "prompt": "portrait photo of a young asian man with very muscular body, standing in gym, front view, wearing gray tank top, large shoulders, big arms, visible veins, bodybuilder physique, soft natural lighting, sharp focus, raw photo, 8k uhd, looking at camera",
        "seed": 777,
    },
}

negative_prompt = "deformed, ugly, bad anatomy, extra limbs, blurry, cartoon, anime, painting, disfigured, mutated, extra fingers, plastic skin, text, watermark, crop top"

print("Step 2: Generating body types...")
body_files = {}
for btype, config in body_types.items():
    generator = torch.Generator("cuda").manual_seed(config["seed"])
    result = pipe(
        prompt=config["prompt"],
        negative_prompt=negative_prompt,
        width=512,
        height=768,
        num_inference_steps=40,
        guidance_scale=5.5,
        generator=generator,
    ).images[0]
    path = f"body_{btype}.png"
    result.save(path)
    body_files[btype] = path
    print(f"Saved {path}")

del pipe
torch.cuda.empty_cache()

print("Step 3: Loading face tools...")
app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
app.prepare(ctx_id=0, det_size=(640, 640))

swapper = insightface.model_zoo.get_model(
    "./models/inswapper_128.onnx",
    providers=["CPUExecutionProvider"]
)

source_img = cv2.imread("test_face.jpg")
source_faces = app.get(source_img)
source_face = source_faces[0]

def smooth_face_edges(image, face_mask, blur_radius=15):
    kernel = np.ones((5, 5), np.uint8)
    mask_eroded = cv2.erode(face_mask, kernel, iterations=2)
    mask_eroded_float = mask_eroded.astype(np.float32) / 255.0
    mask_final = cv2.GaussianBlur(mask_eroded_float, (blur_radius*2+1, blur_radius*2+1), 0)
    return mask_final

print("Step 4: Swapping and enhancing faces...")
for btype, body_path in body_files.items():
    target_img = cv2.imread(body_path)
    target_faces = app.get(target_img)
    if len(target_faces) == 0:
        print(f"No face in {body_path}, skipping...")
        continue
    original_body = target_img.copy()
    result = swapper.get(target_img, target_faces[0], source_face, paste_back=True)
    face_bbox = target_faces[0].bbox.astype(int)
    face_mask = np.zeros(result.shape[:2], dtype=np.uint8)
    x1, y1, x2, y2 = face_bbox
    pad_x = int((x2 - x1) * 0.1)
    pad_y = int((y2 - y1) * 0.15)
    x1 = max(0, x1 - pad_x)
    y1 = max(0, y1 - pad_y)
    x2 = min(result.shape[1], x2 + pad_x)
    y2 = min(result.shape[0], y2 + pad_y)
    center = ((x1 + x2) // 2, (y1 + y2) // 2)
    axes = ((x2 - x1) // 2, (y2 - y1) // 2)
    cv2.ellipse(face_mask, center, axes, 0, 0, 360, 255, -1)
    mask_3d = smooth_face_edges(result, face_mask, blur_radius=20)
    mask_3d = np.stack([mask_3d] * 3, axis=-1)
    blended = (result.astype(np.float32) * mask_3d +
               original_body.astype(np.float32) * (1 - mask_3d))
    blended = np.clip(blended, 0, 255).astype(np.uint8)
    output_path = f"final_{btype}.png"
    cv2.imwrite(output_path, blended)
    print(f"Saved {output_path}")

print("Done! Check final_lean.png, final_athletic.png, final_muscular.png")
```

### app.py (FastAPI Backend)

See the app.py file provided separately — it wraps the test_enhanced.py pipeline into HTTP endpoints with:
- POST /morph endpoint (accepts face upload + body_type)
- Models loaded once at startup
- CORS enabled
- Returns base64 PNG in JSON

### Key Lessons & Gotchas

1. **Script load order matters** — jQuery must load before plugins that depend on it
2. **Google Apps Script URL** — must use the deployed `/exec` URL, not the editor URL
3. **VESSL PyTorch version** — pre-installed 2.3.1 was too old for transformers, needed upgrade to 2.4.0
4. **IP-Adapter FaceID XL** — the SDXL version class didn't exist in the pip package, only SD 1.5 version
5. **Two-step approach >> one-step** — generating body separately then face-swapping produces much better results than trying to do both at once
6. **heredoc corruption** — terminal pasting of multi-line scripts gets garbled, use JupyterLab file editor or Python file writing instead
7. **`libGL.so.1` missing** — common in Docker/container environments, fix with `apt-get install libgl1-mesa-glx`
8. **fade-up CSS class** — caused sections to be invisible (opacity: 0) when scroll observer didn't trigger, removed for reliability
9. **Netlify redeploy** — drag entire folder to Production deploys area, not just individual files
10. **Google Sheets sharing** — change from 편집자 to 뷰어 before sharing DB URL with professor

### Future Improvements Discussed

1. **RAG integration** — retrieve real physiques from database with similar stats to ground the morph in reality
2. **ControlNet** — use OpenPose to control body pose from target physique photo
3. **Genetic Reality Score** — based on skeletal frame similarity (40%), muscle insertion compatibility (35%), body type compatibility (25%)
4. **PED detection** — FFMI-based classifier to detect enhanced physiques and auto-downgrade
5. **4-week rescan** — progress tracking with CV comparison against predicted timeline
6. **DEXA/InBody integration** — use real body composition data for more accurate morphs
7. **Privacy infrastructure** — in-memory processing only, no storage, E2E encryption

---

## 17. Google Colab Setup (Alternative to VESSL)

**Why Colab:** VESSL workspace can get stuck in "pending" when GPU cluster is full. Colab provides free T4 GPU (16GB VRAM) on demand.

### Cell-by-Cell Setup

**Cell 1 — Check GPU:**
```python
!nvidia-smi
```

**Cell 2 — Install everything:**
```python
!pip install -q transformers==4.44.2 diffusers==0.30.3
!pip install -q insightface onnxruntime-gpu
!pip install -q accelerate safetensors peft
!pip install -q opencv-python pillow
!pip install -q fastapi uvicorn python-multipart
!pip install -q git+https://github.com/tencent-ailab/IP-Adapter.git
!apt-get install -y -q libgl1-mesa-glx libglib2.0-0
```

**Cell 3 — Download models:**
```python
from huggingface_hub import hf_hub_download
import os
os.makedirs("models", exist_ok=True)
hf_hub_download(repo_id='h94/IP-Adapter-FaceID', filename='ip-adapter-faceid_sd15.bin', local_dir='./models')
hf_hub_download(repo_id='h94/IP-Adapter-FaceID', filename='ip-adapter-faceid_sd15_lora.safetensors', local_dir='./models')
hf_hub_download(repo_id='ezioruan/inswapper_128.onnx', filename='inswapper_128.onnx', local_dir='./models')
```

**Cell 4 — Upload face photo:**
```python
from google.colab import files
import shutil
uploaded = files.upload()
for filename in uploaded.keys():
    shutil.move(filename, "test_face.jpg")
```

**Cell 5 — Verify face detection:**
```python
import cv2
from insightface.app import FaceAnalysis
from PIL import Image
from IPython.display import display
app = FaceAnalysis(name="buffalo_l", providers=['CUDAExecutionProvider', 'CPUExecutionProvider'])
app.prepare(ctx_id=0, det_size=(640, 640))
image = cv2.imread("test_face.jpg")
faces = app.get(image)
print(f"Faces detected: {len(faces)}")
display(Image.open("test_face.jpg").resize((200, 260)))
```

**Cells 6-10:** See Section 11 for the full body generation, face swap, result display, and download cells.

---

## 18. ngrok + FastAPI Live Demo (on Colab)

**Purpose:** Expose the Colab FastAPI server to the internet so the Netlify frontend (morph.html) can call it.

**Architecture:**
```
User browser -> morph.html (Netlify)
    -> POST /morph
    -> ngrok tunnel (https://abc123.ngrok-free.app)
    -> Colab FastAPI server (port 8000)
    -> GPU processes morph
    -> Returns base64 image
    -> morph.html displays result
```

**Cell 11 — Install ngrok:**
```python
!pip install -q pyngrok
```

**Cell 12 — Start ngrok tunnel:**
```python
from pyngrok import ngrok
ngrok.set_auth_token("YOUR_NGROK_AUTH_TOKEN")
public_url = ngrok.connect(8000)
print(f"YOUR PUBLIC API URL: {public_url}")
```

**Cell 13 — Write app.py and start server:**
```python
!uvicorn app:app --host 0.0.0.0 --port 8000
```

**Then update morph.html:**
```javascript
const API_URL = "https://abc123.ngrok-free.app";  // your ngrok URL
```

**Important notes:**
- ngrok URL changes every time you restart
- Colab times out after ~90 min idle or ~12 hrs max
- Keep the Colab tab open during presentation
- Have pre-generated results as backup

---

## 19. Compute Platform Comparison

| Platform | GPU | VRAM | Cost | Pros | Cons |
|---|---|---|---|---|---|
| VESSL (yonsei) | RTX 3090 | 24GB | Free (school) | Fast, reliable | Queue/pending issues |
| Colab Free | T4 | 16GB | Free | No queue, instant | 90min timeout, slower |
| Local RTX 4050 | RTX 4050 | 6GB | Free | Always available | SD 1.5 only, slow |
| RunPod | A100 | 80GB | $0.40/hr | Instant, fast | Paid |

---

## 20. Additional Lessons from Colab Migration

11. **VESSL pending state** — GPU cluster can be fully occupied near deadlines
12. **Colab packages don't persist** — must reinstall each session
13. **ngrok auth token** — required for tunneling, free at ngrok.com/signup
14. **HuggingFace token** — set `os.environ["HF_TOKEN"]` for faster downloads
15. **Colab runtime timeout** — free tier disconnects after ~90 min idle
16. **%%writefile** — use this Colab magic to write files from notebook cells
