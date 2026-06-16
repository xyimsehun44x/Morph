import cv2
import torch
import numpy as np
import base64
import io
import json
import os
import insightface
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision
from google import genai as google_genai
import pillow_heif
from PIL import Image

pillow_heif.register_heif_opener()  # adds HEIF/AVIF support to PIL
from fastapi import FastAPI, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from diffusers import StableDiffusionPipeline, DDIMScheduler
from insightface.app import FaceAnalysis

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="MorphPhysique AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== GLOBALS =====
pipe = None
face_app = None
swapper = None

# ===== CONFIGURE GEMINI =====
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
if GEMINI_API_KEY:
    gemini_client = google_genai.Client(api_key=GEMINI_API_KEY)
    GEMINI_MODEL = "gemini-2.5-flash"
else:
    gemini_client = None
    GEMINI_MODEL = None
    print("WARNING: GEMINI_API_KEY not set. /plan endpoint will be disabled.")
gemini_model = gemini_client  # used for null-checks throughout

NEGATIVE_PROMPT = (
    "deformed, ugly, bad anatomy, extra limbs, blurry, cartoon, anime, painting, "
    "disfigured, mutated, extra fingers, plastic skin, text, watermark, crop top, "
    "dark skin, tanned skin"
)

# ===== BODY PRESETS =====
# Each preset has a male and female prompt variant.
# Single proven seed per type (multi-seed added latency without quality gain).
# "light skin, fair skin" in prompt anchors skin tone to avoid ethnicity drift.
BODY_PRESETS = {
    "lean": {
        "prompt_m": (
            "portrait photo of a young east asian man with lean toned body, "
            "standing in gym, front view, wearing gray tank top, "
            "slim athletic build, visible but not bulky muscles, "
            "light skin, fair skin, "
            "soft natural lighting, sharp focus, raw photo, 8k uhd, looking at camera"
        ),
        "prompt_f": (
            "portrait photo of a young east asian woman with lean toned body, "
            "standing in gym, front view, wearing sports bra and leggings, "
            "slim athletic build, visible but not bulky muscles, "
            "light skin, fair skin, "
            "soft natural lighting, sharp focus, raw photo, 8k uhd, looking at camera"
        ),
        "seed": 100,
    },
    "athletic": {
        "prompt_m": (
            "portrait photo of a young east asian man with athletic muscular body, "
            "standing in gym, front view, wearing gray tank top, "
            "broad shoulders, defined arms, medium muscle mass, "
            "light skin, fair skin, "
            "soft natural lighting, sharp focus, raw photo, 8k uhd, looking at camera"
        ),
        "prompt_f": (
            "portrait photo of a young east asian woman with athletic muscular body, "
            "standing in gym, front view, wearing sports bra and leggings, "
            "broad shoulders, defined arms, medium muscle mass, "
            "light skin, fair skin, "
            "soft natural lighting, sharp focus, raw photo, 8k uhd, looking at camera"
        ),
        "seed": 300,
    },
    "muscular": {
        "prompt_m": (
            "portrait photo of a young east asian man with very muscular body, "
            "standing in gym, front view, wearing gray tank top, "
            "large shoulders, big arms, visible veins, bodybuilder physique, "
            "light skin, fair skin, "
            "soft natural lighting, sharp focus, raw photo, 8k uhd, looking at camera"
        ),
        "prompt_f": (
            "portrait photo of a young east asian woman with very muscular body, "
            "standing in gym, front view, wearing sports bra and leggings, "
            "large shoulders, defined arms, bodybuilder physique, "
            "light skin, fair skin, "
            "soft natural lighting, sharp focus, raw photo, 8k uhd, looking at camera"
        ),
        "seed": 777,
    },
    "slim": {
        "prompt_m": (
            "portrait photo of a young east asian man with slim fit body, "
            "standing in gym, front view, wearing gray tank top, "
            "runner physique, low body fat, lean muscles, thin waist, "
            "light skin, fair skin, "
            "soft natural lighting, sharp focus, raw photo, 8k uhd, looking at camera"
        ),
        "prompt_f": (
            "portrait photo of a young east asian woman with slim fit body, "
            "standing in gym, front view, wearing sports bra and leggings, "
            "runner physique, low body fat, lean muscles, thin waist, "
            "light skin, fair skin, "
            "soft natural lighting, sharp focus, raw photo, 8k uhd, looking at camera"
        ),
        "seed": 50,
    },
    "powerlifter": {
        "prompt_m": (
            "portrait photo of a young east asian man with thick powerlifter body, "
            "standing in gym, front view, wearing gray tank top, "
            "stocky build, barrel chest, thick arms, strong legs, "
            "light skin, fair skin, "
            "soft natural lighting, sharp focus, raw photo, 8k uhd, looking at camera"
        ),
        "prompt_f": (
            "portrait photo of a young east asian woman with thick powerlifter body, "
            "standing in gym, front view, wearing sports bra and leggings, "
            "stocky build, strong shoulders, thick arms, strong legs, "
            "light skin, fair skin, "
            "soft natural lighting, sharp focus, raw photo, 8k uhd, looking at camera"
        ),
        "seed": 400,
    },
}


# ===========================================================================
#  HELPER FUNCTIONS
# ===========================================================================

def smooth_face_edges(image, face_mask, blur_radius=15):
    """Create a soft alpha mask for blending the swapped face onto the body."""
    kernel = np.ones((5, 5), np.uint8)
    mask_eroded = cv2.erode(face_mask, kernel, iterations=2)
    mask_eroded_float = mask_eroded.astype(np.float32) / 255.0
    mask_final = cv2.GaussianBlur(
        mask_eroded_float,
        (blur_radius * 2 + 1, blur_radius * 2 + 1),
        0,
    )
    return mask_final


def _correct_face_tone(result, original_target, face_mask):
    """
    Partially shift the swapped face's chrominance toward the body's ambient
    skin tone (sampled from the ring just outside the face region).
    Only corrects A/B channels in LAB space — preserves face lighting.
    """
    kernel = np.ones((40, 40), np.uint8)
    body_ring = cv2.dilate(face_mask, kernel, iterations=4).astype(bool)
    body_ring &= ~face_mask.astype(bool)

    result_lab  = cv2.cvtColor(result,          cv2.COLOR_BGR2LAB).astype(np.float32)
    target_lab  = cv2.cvtColor(original_target, cv2.COLOR_BGR2LAB).astype(np.float32)

    body_pixels = target_lab[body_ring]
    face_pixels = result_lab[face_mask > 0]
    if len(body_pixels) < 50 or len(face_pixels) < 50:
        return result

    STRENGTH = 0.45  # partial correction — enough to close tone gap without going artificial
    for ch in (1, 2):  # A and B channels only
        diff = body_pixels[:, ch].mean() - face_pixels[:, ch].mean()
        result_lab[:, :, ch] = np.where(
            face_mask > 0,
            result_lab[:, :, ch] + diff * STRENGTH,
            result_lab[:, :, ch],
        )

    return cv2.cvtColor(np.clip(result_lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)


def blend_face(swapped_img, original_img, face_bbox):
    """Poisson blending + skin-tone correction for natural face compositing."""
    x1, y1, x2, y2 = face_bbox.astype(int)
    pad_x = int((x2 - x1) * 0.12)
    pad_y = int((y2 - y1) * 0.18)
    x1 = max(0, x1 - pad_x)
    y1 = max(0, y1 - pad_y)
    x2 = min(swapped_img.shape[1], x2 + pad_x)
    y2 = min(swapped_img.shape[0], y2 + pad_y)
    center = ((x1 + x2) // 2, (y1 + y2) // 2)
    axes   = ((x2 - x1) // 2, (y2 - y1) // 2)

    mask = np.zeros(swapped_img.shape[:2], dtype=np.uint8)
    cv2.ellipse(mask, center, axes, 0, 0, 360, 255, -1)

    try:
        result = cv2.seamlessClone(swapped_img, original_img, mask, center, cv2.NORMAL_CLONE)
        return _correct_face_tone(result, original_img, mask)
    except Exception:
        # Fallback: alpha blend when face is near image edge
        mask_3d = smooth_face_edges(swapped_img, mask, blur_radius=20)
        mask_3d = np.stack([mask_3d] * 3, axis=-1)
        blended = (
            swapped_img.astype(np.float32) * mask_3d
            + original_img.astype(np.float32) * (1 - mask_3d)
        )
        return np.clip(blended, 0, 255).astype(np.uint8)


def analyze_face(face_bytes):
    """Decode face image, detect face, return (cv2 image, face object, gender)."""
    if len(face_bytes) == 0:
        raise ValueError("Empty file uploaded")

    source_img = decode_image_bytes(face_bytes)

    # Resize if too large (saves VRAM during face detection)
    h, w = source_img.shape[:2]
    if max(h, w) > 1600:
        scale = 1600 / max(h, w)
        source_img = cv2.resize(source_img, (int(w * scale), int(h * scale)))

    source_faces = face_app.get(source_img)
    if len(source_faces) == 0:
        raise ValueError("No face detected. Please use a clear front-facing photo.")
    face = source_faces[0]
    gender = "M" if face.sex == "M" else "F"
    return source_img, face, gender


def generate_body(prompt, seed):
    """Generate a single body image with the given prompt and seed."""
    generator = torch.Generator("cuda").manual_seed(seed)
    image = pipe(
        prompt=prompt,
        negative_prompt=NEGATIVE_PROMPT,
        width=512,
        height=768,
        num_inference_steps=40,
        guidance_scale=5.5,
        generator=generator,
    ).images[0]
    img_cv2 = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

    # Verify the generated body has a detectable face (needed for swap)
    faces = face_app.get(img_cv2)
    if len(faces) == 0:
        raise ValueError("Generated body has no detectable face — try again.")
    return img_cv2


def do_face_swap(source_face, target_img_cv2):
    """Swap source_face onto target image and blend edges."""
    target_faces = face_app.get(target_img_cv2)
    if len(target_faces) == 0:
        raise ValueError("No face detected in target image")
    original_body = target_img_cv2.copy()
    result = swapper.get(target_img_cv2, target_faces[0], source_face, paste_back=True)
    blended = blend_face(result, original_body, target_faces[0].bbox)
    return blended


def decode_image_bytes(img_bytes):
    """Decode any image format (including AVIF/HEIC) to a BGR cv2 array."""
    try:
        pil_img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    except Exception:
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Could not decode image. Try JPG or PNG format.")
        return img


def img_to_base64(cv2_img):
    _, buffer = cv2.imencode(".png", cv2_img)
    return base64.b64encode(buffer).decode("utf-8")


_POSE_MODEL_PATH = "/tmp/pose_landmarker.task"
_pose_options = mp_vision.PoseLandmarkerOptions(
    base_options=mp_python.BaseOptions(model_asset_path=_POSE_MODEL_PATH),
    running_mode=mp_vision.RunningMode.IMAGE,
)


def extract_body_proportions(img_cv2):
    """
    Run MediaPipe Pose Landmarker on the target physique image and return key
    body proportion ratios.  Returns None if no pose is detected (e.g. face-only
    headshot).  All coordinates are normalised [0,1] so ratios are scale-independent.
    """
    if not os.path.exists(_POSE_MODEL_PATH):
        print("MediaPipe pose model not found — skipping proportions")
        return None

    img_rgb = cv2.cvtColor(img_cv2, cv2.COLOR_BGR2RGB)
    mp_img  = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_rgb)

    with mp_vision.PoseLandmarker.create_from_options(_pose_options) as lm:
        results = lm.detect(mp_img)

    if not results.pose_landmarks:
        return None

    lm = results.pose_landmarks[0]  # first (most confident) person

    def pt(idx):
        return np.array([lm[idx].x, lm[idx].y])

    ls, rs = pt(11), pt(12)   # shoulders
    lh, rh = pt(23), pt(24)   # hips
    le          = pt(13)        # left elbow
    lw          = pt(15)        # left wrist
    lk, rk = pt(25), pt(26)   # knees

    shoulder_w  = np.linalg.norm(ls - rs)
    hip_w       = np.linalg.norm(lh - rh)
    shoulder_mid = (ls + rs) / 2
    hip_mid      = (lh + rh) / 2
    knee_mid     = (lk + rk) / 2
    torso_len    = np.linalg.norm(shoulder_mid - hip_mid)
    upper_leg    = np.linalg.norm(hip_mid - knee_mid)
    left_arm     = np.linalg.norm(ls - le) + np.linalg.norm(le - lw)

    shr = float(shoulder_w / max(hip_w, 1e-3))
    return {
        "shoulder_hip_ratio":  round(shr, 2),
        "torso_leg_ratio":     round(float(torso_len / max(upper_leg, 1e-3)), 2),
        "arm_torso_ratio":     round(float(left_arm  / max(torso_len,  1e-3)), 2),
        "v_taper":             bool(shr > 1.35),
    }


def analyze_physique_with_gemini(img_bytes, person_name="", lang="en"):
    """
    Send the target physique photo to Gemini Vision and get a structured
    analysis: body type, estimated BF%, dominant muscle groups, training style.
    Returns a dict, or None if Gemini is unavailable or the call fails.
    """
    if gemini_model is None:
        return None
    try:
        pil_img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        pil_img.thumbnail((1024, 1024), Image.LANCZOS)

        person_hint = ""
        if person_name:
            person_hint = (
                f"You may know this person as {person_name}. "
                "Use any factual knowledge you have about their actual body composition, height, weight, "
                "shoulder-to-hip ratio, training history, and whether they use PEDs — "
                "in addition to visual assessment. Prioritize known factual data over visual estimates when they conflict.\n\n"
            )

        lang_note = (
            "\nRESPONSE LANGUAGE: Write all free-text values — physique_description, honesty_note, "
            "and every item inside key_visual_traits and dominant_muscle_groups — in Korean (한국어). "
            "Keep enum values (body_type, training_style, natural_achievability) and boolean fields in English.\n"
        ) if lang == "kr" else ""

        prompt = (
            f"{person_hint}"
            f"{lang_note}"
            "Analyze this physique photo and return ONLY valid JSON (no markdown fences):\n"
            "{\n"
            '  "body_type": "lean|athletic|muscular|powerlifter|slim",\n'
            '  "estimated_body_fat_pct": <integer 5-40>,\n'
            '  "dominant_muscle_groups": ["3-5 most visibly developed groups"],\n'
            '  "training_style": "hypertrophy|powerlifting|calisthenics|endurance|mixed",\n'
            '  "physique_description": "2 sentences on key physical characteristics",\n'
            '  "key_visual_traits": ["3-5 traits e.g. V-taper, visible abs, capped shoulders"],\n'
            '  "natural_achievability": "naturally_achievable|elite_enhanced|genetic_outlier",\n'
            '  "requires_peds": <true|false — true if this physique almost certainly requires anabolic steroids or other PEDs to achieve>,\n'
            '  "is_elite_athlete": <true|false — true if this appears to be a world-class or professional-level athlete>,\n'
            '  "honesty_note": "One blunt, honest sentence about whether an average person can realistically achieve this naturally"\n'
            "}\n\n"
            "Be brutally honest about PED use — extreme muscularity combined with very low body fat and freakish size is a strong indicator. "
            "Do NOT downplay this to be encouraging."
        )
        response = gemini_client.models.generate_content(model=GEMINI_MODEL, contents=[prompt, pil_img])
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        return json.loads(text.strip())
    except Exception as e:
        print(f"Gemini Vision analysis failed: {e}")
        return None


def compute_reality_score(user_body_fat, physique_analysis, lang="en"):
    """
    Honest reality score. Accounts for PED-enhanced and elite physiques
    with realistic natural muscle-building timelines.
    """
    KR_LABELS = {
        "Unknown":                           "알 수 없음",
        "Not Naturally Achievable":          "자연적으로 달성 불가",
        "Extreme — Elite Genetics Required": "극단적 — 최상위 유전자 필요",
        "Highly Achievable":                 "달성 가능성 높음",
        "Achievable (6–12 months)":          "달성 가능 (6–12개월)",
        "Challenging (1–2 years)":           "도전적 (1–2년)",
        "Very Challenging (2–5 years)":      "매우 도전적 (2–5년)",
        "Extreme Long-Term Goal (5+ years)": "극도의 장기 목표 (5년 이상)",
    }

    def _label(en): return KR_LABELS.get(en, en) if lang == "kr" else en

    if physique_analysis is None:
        return {
            "score": 50, "label": _label("Unknown"),
            "timeline_weeks": None,
            "body_fat_to_lose_pct": None,
            "reasoning": "목표 체형을 분석할 수 없습니다." if lang == "kr" else "Could not analyse target physique.",
        }

    requires_peds   = physique_analysis.get("requires_peds", False)
    achievability   = physique_analysis.get("natural_achievability", "naturally_achievable")
    is_elite        = physique_analysis.get("is_elite_athlete", False)
    honesty_note    = physique_analysis.get("honesty_note", "")

    # Hard ceiling for PED-dependent or genetic-outlier physiques
    if requires_peds or achievability == "genetic_outlier":
        return {
            "score": 5,
            "label": _label("Not Naturally Achievable"),
            "timeline_weeks": None,
            "body_fat_to_lose_pct": None,
            "reasoning": honesty_note or (
                "이 체형은 거의 확실히 단백동화 스테로이드나 다른 성능 향상 약물과 최상위 유전자가 필요합니다. 대부분의 사람들은 자연적으로 이를 복제할 수 없습니다."
                if lang == "kr" else
                "This physique almost certainly requires anabolic steroids or other "
                "performance-enhancing drugs, combined with elite genetics. "
                "It cannot be replicated naturally by the vast majority of people."
            ),
        }

    if achievability == "elite_enhanced" or is_elite:
        return {
            "score": 15,
            "label": _label("Extreme — Elite Genetics Required"),
            "timeline_weeks": None,
            "body_fat_to_lose_pct": None,
            "reasoning": honesty_note or (
                "이것은 수년간의 헌신적인 훈련을 해도 대부분의 사람들이 자연적으로 달성할 수 있는 한계에 있거나 그를 초과하는 엘리트 수준의 체형입니다."
                if lang == "kr" else
                "This is an elite-level physique that sits at or beyond the ceiling "
                "of what most people can achieve naturally, even with years of dedicated training."
            ),
        }

    # Naturally achievable physiques — use realistic timelines
    target_bf = physique_analysis.get("estimated_body_fat_pct", 15)
    bf_gap    = max(0.0, float(user_body_fat) - float(target_bf))
    bf_weeks  = bf_gap / 0.5  # ~0.5 % BF/week sustainable

    # Realistic natural muscle-building time (dedicated natural trainee, male)
    muscle_weeks = {
        "slim":        0,
        "lean":        26,   # ~6 months
        "athletic":    78,   # ~18 months
        "muscular":    208,  # ~4 years
        "powerlifter": 260,  # ~5 years
    }.get(physique_analysis.get("body_type", "athletic"), 78)

    total_weeks = max(bf_weeks, muscle_weeks)

    if   total_weeks <= 16:  score, label = 90, "Highly Achievable"
    elif total_weeks <= 52:  score, label = 70, "Achievable (6–12 months)"
    elif total_weeks <= 104: score, label = 50, "Challenging (1–2 years)"
    elif total_weeks <= 260: score, label = 30, "Very Challenging (2–5 years)"
    else:                    score, label = 15, "Extreme Long-Term Goal (5+ years)"

    if lang == "kr":
        reasoning = (
            f"체지방 격차: {bf_gap:.1f}% (주당 0.5%로 약 {round(bf_weeks)}주 소요). "
            f"{physique_analysis.get('body_type', '목표')} 체형을 위한 자연적인 근육 증가: "
            f"약 {round(muscle_weeks / 52, 1)}년의 헌신적인 훈련이 필요합니다."
        )
    else:
        reasoning = (
            f"Body fat gap: {bf_gap:.1f}% (~{round(bf_weeks)} weeks at 0.5%/week). "
            f"Natural muscle building for {physique_analysis.get('body_type', 'target')} "
            f"physique: ~{round(muscle_weeks / 52, 1)} years of dedicated training."
        )

    return {
        "score":                score,
        "label":                _label(label),
        "timeline_weeks":       round(total_weeks),
        "body_fat_to_lose_pct": round(bf_gap, 1),
        "reasoning":            reasoning,
    }


async def _generate_full_plan(height, weight, body_fat, gender,
                               goal, physique_analysis, proportions, person_name="", lang="en"):
    """
    Gemini text plan enriched with Gemini Vision analysis and MediaPipe
    proportions so the exercises and macros target the *exact* physique shown.
    """
    if gemini_model is None:
        return None

    bmi       = round(weight / ((height / 100) ** 2), 1)
    lean_mass = round(weight * (1 - body_fat / 100), 1)
    fat_mass  = round(weight * body_fat / 100, 1)

    physique_ctx = ""
    if physique_analysis:
        requires_peds = physique_analysis.get("requires_peds", False)
        is_elite      = physique_analysis.get("is_elite_athlete", False)
        honesty_note  = physique_analysis.get("honesty_note", "")
        ped_warning   = ""
        if requires_peds or is_elite:
            ped_warning = (
                f"\nIMPORTANT: This target physique is {'PED-enhanced and ' if requires_peds else ''}at elite/genetic-outlier level. "
                "Do NOT promise the user they can fully achieve it naturally. "
                "Frame the plan as maximising their natural potential in the same direction. "
                f"Acknowledge honestly in the summary: {honesty_note}\n"
            )
        physique_ctx = (
            "\nTARGET PHYSIQUE (from uploaded photo):\n"
            f"- Body Type: {physique_analysis.get('body_type', '?')}\n"
            f"- Est. Body Fat: {physique_analysis.get('estimated_body_fat_pct', '?')}%\n"
            f"- Dominant Muscles: {', '.join(physique_analysis.get('dominant_muscle_groups', []))}\n"
            f"- Training Style: {physique_analysis.get('training_style', '?')}\n"
            f"- Key Traits: {', '.join(physique_analysis.get('key_visual_traits', []))}\n"
            + ped_warning
        )

    proportions_ctx = ""
    if proportions:
        taper = "strong V-taper" if proportions.get("v_taper") else "balanced frame"
        proportions_ctx = (
            "\nTARGET BODY PROPORTIONS (MediaPipe):\n"
            f"- Shoulder-to-Hip Ratio: {proportions.get('shoulder_hip_ratio')} ({taper})\n"
            f"- Torso-to-Leg Ratio: {proportions.get('torso_leg_ratio')}\n"
        )

    person_ctx = f"\nTARGET PERSON: {person_name}\n" if person_name else ""

    lang_instruction = (
        "\nRESPONSE LANGUAGE: Write ALL text values in Korean (한국어). "
        "Keep every JSON key in English. Translate summary, timeline rationale, split name, "
        "day labels, exercise notes, meal descriptions, supplement names, hydration advice, "
        "week_5_8_changes, and every key tip into Korean. Do not use English in any value field.\n"
    ) if lang == "kr" else ""

    prompt = f"""You are an expert fitness coach. Create a specific 8-week plan to reach the target physique shown.
{lang_instruction}

USER:
- Height: {height} cm | Weight: {weight} kg | BF: {body_fat}%
- Gender: {'Male' if gender == 'M' else 'Female'}
- BMI: {bmi} | Lean Mass: {lean_mass} kg | Fat Mass: {fat_mass} kg
- Goal: {goal or 'Achieve the target physique'}
{physique_ctx}{proportions_ctx}{person_ctx}
Prioritise the dominant muscle groups above. Match the training style that produced the target physique.

Return ONLY valid JSON (no markdown fences):
{{
    "summary": "2-sentence personalised assessment referencing the specific target",
    "phase": "bulk|cut|recomp",
    "timeline": "X weeks with brief rationale",
    "workout_plan": {{
        "split": "split name",
        "frequency": "X days/week",
        "focus_areas": ["top 3 muscle groups from the target physique"],
        "week_1_4": [
            {{"day": "Day 1 – Push", "exercises": [
                {{"name": "Bench Press", "sets": 4, "reps": "8-10", "notes": "control descent"}}
            ]}}
        ],
        "week_5_8_changes": "progression strategy"
    }},
    "meal_plan": {{
        "daily_calories": 0,
        "protein_g": 0,
        "carbs_g": 0,
        "fat_g": 0,
        "meals": [
            {{"meal": "Breakfast",    "description": "specific foods", "calories": 0}},
            {{"meal": "Lunch",        "description": "specific foods", "calories": 0}},
            {{"meal": "Pre-Workout",  "description": "specific foods", "calories": 0}},
            {{"meal": "Post-Workout", "description": "specific foods", "calories": 0}},
            {{"meal": "Dinner",       "description": "specific foods", "calories": 0}}
        ],
        "supplements": ["evidence-based picks for this goal"],
        "hydration": "daily water target"
    }},
    "key_tips": ["4 tips referencing the exact target physique and user starting point"]
}}"""

    try:
        response = gemini_client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        return json.loads(text.strip())
    except Exception as e:
        print(f"Plan generation failed: {e}")
        return {"error": str(e)}


# ===========================================================================
#  STARTUP — load models once
# ===========================================================================

@app.on_event("startup")
async def load_models():
    global pipe, face_app, swapper

    print("Loading SD pipeline...")
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

    print("Loading InsightFace...")
    face_app = FaceAnalysis(
        name="buffalo_l",
        providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
    )
    face_app.prepare(ctx_id=0, det_size=(640, 640))

    print("Loading face swapper...")
    swapper = insightface.model_zoo.get_model(
        os.path.join(_SCRIPT_DIR, "models", "inswapper_128.onnx"),
        providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
    )
    print("All models loaded! Server ready.")


# ===========================================================================
#  ENDPOINTS
# ===========================================================================

@app.get("/")
async def root():
    return {"status": "MorphPhysique AI is running"}


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "gpu": torch.cuda.is_available(),
        "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "models_loaded": all(x is not None for x in [pipe, face_app, swapper]),
        "gemini_enabled": gemini_model is not None,
    }


@app.post("/morph/preset")
async def morph_preset(face: UploadFile, body_type: str = Form(default="athletic")):
    """Generate a morph using a preset body type."""
    try:
        face_bytes = await face.read()

        if body_type not in BODY_PRESETS:
            return JSONResponse(status_code=400, content={
                "success": False,
                "error": f"Invalid body type. Choose from: {list(BODY_PRESETS.keys())}",
            })

        source_img, source_face, gender = analyze_face(face_bytes)
        print(f"Detected gender: {gender}")

        config = BODY_PRESETS[body_type]
        prompt = config["prompt_m"] if gender == "M" else config["prompt_f"]
        print(f"Prompt: {prompt[:80]}...")

        body_cv2 = generate_body(prompt, config["seed"])
        result = do_face_swap(source_face, body_cv2)

        return JSONResponse(content={
            "success": True,
            "body_type": body_type,
            "detected_gender": gender,
            "image": img_to_base64(result),
        })

    except ValueError as e:
        return JSONResponse(status_code=400, content={"success": False, "error": str(e)})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@app.post("/morph/custom")
async def morph_custom(face: UploadFile, target: UploadFile):
    """Swap the user's face onto any target physique photo they upload."""
    try:
        face_bytes = await face.read()
        target_bytes = await target.read()

        source_img, source_face, gender = analyze_face(face_bytes)
        target_img = decode_image_bytes(target_bytes)

        # Resize if too large (avoid OOM)
        h, w = target_img.shape[:2]
        if max(h, w) > 1024:
            scale = 1024 / max(h, w)
            target_img = cv2.resize(target_img, (int(w * scale), int(h * scale)))

        result = do_face_swap(source_face, target_img)

        return JSONResponse(content={
            "success": True,
            "body_type": "custom",
            "image": img_to_base64(result),
        })

    except ValueError as e:
        return JSONResponse(status_code=400, content={"success": False, "error": str(e)})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@app.post("/plan")
async def generate_plan(
    height: float = Form(...),
    weight: float = Form(...),
    body_fat: float = Form(...),
    body_type: str = Form(default="athletic"),
    goal: str = Form(default=""),
):
    """Generate a personalized workout + meal plan via Gemini."""
    if gemini_model is None:
        return JSONResponse(status_code=503, content={
            "success": False,
            "error": "Gemini API not configured. Set GEMINI_API_KEY env var.",
        })

    try:
        bmi = round(weight / ((height / 100) ** 2), 1)
        lean_mass = round(weight * (1 - body_fat / 100), 1)
        fat_mass = round(weight * body_fat / 100, 1)

        prompt = f"""You are an expert fitness coach and nutritionist. Create a personalized 8-week transformation plan.

USER STATS:
- Height: {height} cm
- Weight: {weight} kg
- Body Fat: {body_fat}%
- Target Body Type: {body_type}
- Additional Goal: {goal if goal else "General fitness transformation"}

CALCULATED:
- BMI: {bmi}
- Lean Mass: {lean_mass} kg
- Fat Mass: {fat_mass} kg

Generate the following in JSON format (and ONLY JSON, no markdown backticks):
{{
    "summary": "Brief 2-sentence assessment of current state and realistic goal",
    "timeline": "Estimated weeks to reach target",
    "workout_plan": {{
        "split": "Training split name",
        "frequency": "Days per week",
        "focus_areas": ["Top 3 priority muscle groups"],
        "week_1_4": [
            {{"day": "Day 1 - Push", "exercises": [
                {{"name": "Exercise", "sets": 4, "reps": "8-10", "notes": "Brief form note"}}
            ]}}
        ],
        "week_5_8_changes": "How the program progresses"
    }},
    "meal_plan": {{
        "daily_calories": 0,
        "protein_g": 0,
        "carbs_g": 0,
        "fat_g": 0,
        "meals": [
            {{"meal": "Breakfast", "description": "Brief meal description", "calories": 0}}
        ],
        "supplements": ["List of recommended supplements"],
        "hydration": "Daily water intake recommendation"
    }},
    "key_tips": ["3-4 important tips specific to this person"]
}}"""

        response = gemini_client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
        plan_text = response.text.strip()

        # Strip markdown fences if Gemini adds them
        if plan_text.startswith("```"):
            plan_text = plan_text.split("\n", 1)[1]
        if plan_text.endswith("```"):
            plan_text = plan_text.rsplit("```", 1)[0]
        plan_text = plan_text.strip()

        plan_data = json.loads(plan_text)
        return JSONResponse(content={"success": True, "plan": plan_data})

    except json.JSONDecodeError:
        return JSONResponse(content={
            "success": True,
            "plan": {"raw_text": response.text, "parse_error": "Could not parse as JSON"},
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@app.post("/morph/full")
async def morph_full(
    face:        UploadFile,
    target:      UploadFile,
    height:      float = Form(...),
    weight:      float = Form(...),
    body_fat:    float = Form(...),
    goal:        str   = Form(default=""),
    person_name: str   = Form(default=""),
    lang:        str   = Form(default="en"),
):
    """
    Full pipeline in one call:
      1. Face swap user's face onto the target physique photo (inswapper)
      2. MediaPipe Pose → body proportion ratios from the target photo
      3. Gemini Vision → structured physique analysis of the target photo
      4. Reality Score → how achievable the target is given current stats
      5. Personalised workout + diet plan using all of the above as context
    """
    try:
        face_bytes   = await face.read()
        target_bytes = await target.read()

        # --- 1. decode & face-swap ---
        source_img, source_face, gender = analyze_face(face_bytes)
        target_img = decode_image_bytes(target_bytes)

        h, w = target_img.shape[:2]
        if max(h, w) > 1024:
            scale = 1024 / max(h, w)
            target_img = cv2.resize(target_img, (int(w * scale), int(h * scale)))

        morphed_img = do_face_swap(source_face, target_img)

        # --- 2. MediaPipe body proportions ---
        proportions = extract_body_proportions(target_img)

        # --- 3. Gemini Vision physique analysis ---
        physique_analysis = analyze_physique_with_gemini(target_bytes, person_name=person_name, lang=lang)

        # --- 4. Reality score ---
        reality = compute_reality_score(body_fat, physique_analysis, lang=lang)

        # --- 5. Personalised plan ---
        plan = await _generate_full_plan(
            height=height, weight=weight, body_fat=body_fat,
            gender=gender, goal=goal,
            physique_analysis=physique_analysis,
            proportions=proportions,
            person_name=person_name,
            lang=lang,
        )

        return JSONResponse(content={
            "success": True,
            "image": img_to_base64(morphed_img),
            "target_analysis": {
                "physique":     physique_analysis,
                "proportions":  proportions,
            },
            "reality_score": reality,
            "plan": plan,
        })

    except ValueError as e:
        return JSONResponse(status_code=400, content={"success": False, "error": str(e)})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


# Legacy endpoint — same as /morph/preset
@app.post("/morph")
async def morph_legacy(face: UploadFile, body_type: str = Form(default="athletic")):
    return await morph_preset(face=face, body_type=body_type)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)