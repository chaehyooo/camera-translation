"""Local Flask backend for the camera-based easy Korean translation prototype.

Run from the project directory with:
    python app.py
"""
from __future__ import annotations

import io
import os
import re
import threading
from pathlib import Path
from typing import Any

import cv2
import easyocr
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.exceptions import RequestEntityTooLarge
from google import genai

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

MAX_IMAGE_BYTES = 8 * 1024 * 1024
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}
TERM_COL = "어려운 단어"
EXPLAIN_COL = "쉬운 단어"
DICTIONARY_PATH = Path(os.getenv("DICTIONARY_PATH", "data/dictionary.xlsx"))
if not DICTIONARY_PATH.is_absolute():
    DICTIONARY_PATH = BASE_DIR / DICTIONARY_PATH

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite").strip()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_IMAGE_BYTES

# The camera demo and API are served from the same local origin, so CORS is not needed.
# If using a separate frontend dev server, configure CORS for that exact origin only.

_reader = None
_reader_lock = threading.Lock()


def normalize(text: Any) -> str:
    """Normalize searchable text by removing whitespace and lowercasing."""
    return re.sub(r"\s+", "", str(text).strip()).lower()


def load_dictionary(path: Path) -> tuple[dict[str, dict[str, str]], str | None]:
    """Load difficult-word definitions from an Excel workbook.

    Required column names are exactly '어려운 단어' and '쉬운 단어'.
    """
    if not path.exists():
        return {}, (
            f"단어장 파일을 찾을 수 없습니다: {path}\n"
            "엑셀 파일을 data/dictionary.xlsx 위치에 넣어 주세요."
        )

    try:
        frame = pd.read_excel(path)
    except Exception as exc:
        return {}, f"엑셀 파일을 읽지 못했습니다: {exc}"

    missing = [col for col in (TERM_COL, EXPLAIN_COL) if col not in frame.columns]
    if missing:
        return {}, (
            f"엑셀에 필요한 열이 없습니다: {missing}. "
            f"현재 열: {frame.columns.tolist()}"
        )

    dictionary: dict[str, dict[str, str]] = {}
    for _, row in frame.iterrows():
        term_value = row[TERM_COL]
        explanation_value = row[EXPLAIN_COL]

        if pd.isna(term_value) or pd.isna(explanation_value):
            continue

        term = str(term_value).strip()
        explanation = str(explanation_value).strip()
        key = normalize(term)

        if not term or not explanation or len(key) < 2:
            continue

        # Keep the first definition if duplicate normalized terms are present.
        dictionary.setdefault(key, {"용어": term, "쉬운 설명": explanation})

    return dictionary, None


dictionary, dictionary_warning = load_dictionary(DICTIONARY_PATH)
sorted_terms = sorted(dictionary.keys(), key=len, reverse=True)


def find_matches(ocr_text: str) -> list[dict[str, str]]:
    """Find dictionary terms in OCR text, preferring longer terms first."""
    normalized_ocr = normalize(ocr_text)
    matches = []
    seen = set()

    for key in sorted_terms:
        item = dictionary[key]
        term = item["용어"]
        if key in normalized_ocr and term not in seen:
            matches.append({"용어": term, "쉬운 설명": item["쉬운 설명"]})
            seen.add(term)

    return matches


def get_reader():
    """Create the EasyOCR reader on first use to avoid slow app startup."""
    global _reader
    if _reader is None:
        with _reader_lock:
            if _reader is None:
                app.logger.info("Loading EasyOCR Korean/English models...")
                _reader = easyocr.Reader(["ko", "en"], gpu=False)
    return _reader


def extract_text_from_image(image_bytes: bytes) -> str:
    """Decode and preprocess image bytes, then run EasyOCR."""
    if not image_bytes:
        raise ValueError("빈 이미지 파일입니다.")
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ValueError("이미지는 8MB 이하로 업로드해 주세요.")

    try:
        image = Image.open(io.BytesIO(image_bytes))
        source_format = image.format
        if source_format not in ALLOWED_IMAGE_FORMATS:
            raise ValueError("JPG, PNG, WEBP 형식의 이미지만 지원합니다.")
        image = ImageOps.exif_transpose(image).convert("RGB")
    except ValueError:
        raise
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("이미지를 열 수 없습니다. 파일 형식을 확인해 주세요.") from exc

    img = np.array(image)
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

    # Keep the original notebook's 1.5x enlargement for OCR.
    gray = cv2.resize(
        gray, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC
    )

    results = get_reader().readtext(gray, detail=1)
    return " ".join(text.strip() for _box, text, _confidence in results if text).strip()


def make_easy_text(ocr_text: str, matches: list[dict[str, str]]) -> str:
    """Use Gemini to produce easy Korean while preserving important details."""
    if not GOOGLE_API_KEY:
        raise RuntimeError(
            "GOOGLE_API_KEY가 설정되지 않았습니다. .env 파일에 API 키를 등록해 주세요."
        )

    known_terms = "\n".join(
        f"- {item['용어']}: {item['쉬운 설명']}" for item in matches
    ) or "일치하는 데이터셋 용어 없음"

    prompt = f"""
당신은 어르신을 위한 쉬운 말 변환 도우미입니다.

[원문]
{ocr_text}

[기존 데이터셋에서 찾은 어려운 단어와 설명]
{known_terms}

다음 기준에 따라 한국어로 답하세요.
1. 기존 데이터셋에 등록된 단어는 제공된 쉬운 설명을 우선 활용하세요.
2. 데이터셋에 없는 다른 어려운 단어도 찾아 쉬운 말로 설명하세요.
3. 원문의 의미를 유지하면서 전체 문장을 어르신이 이해하기 쉬운 한국어로 바꿔 주세요.
4. 금액, 날짜, 신청 조건, 전화번호, 기관명 및 부정 표현을 임의로 바꾸거나 생략하지 마세요.
5. 원문에 없는 정보를 추가하지 마세요.
6. OCR 결과가 불분명한 부분은 추측하지 말고 [원문 확인 필요]라고 표시하세요.
7. 결과에서 '어려운 단어 설명'과 '쉬워진 문장'을 구분해 주세요.
"""
    client = genai.Client(api_key=GOOGLE_API_KEY)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )
    result = (response.text or "").strip()
    if not result:
        raise RuntimeError("AI가 비어 있는 결과를 반환했습니다.")
    return result


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True})


@app.route("/api/status", methods=["GET"])
def api_status():
    return jsonify({
        "ok": True,
        "gemini_configured": bool(GOOGLE_API_KEY),
        "dictionary_loaded": bool(dictionary),
        "dictionary_terms": len(dictionary),
        "dictionary_warning": dictionary_warning,
    })


@app.errorhandler(RequestEntityTooLarge)
def handle_too_large(_error):
    return jsonify({"error": "이미지는 8MB 이하로 업로드해 주세요."}), 413


@app.route("/api/translate", methods=["POST"])
def translate_image():
    if "image" not in request.files:
        return jsonify({"error": "사진 파일이 없습니다. 'image' 필드로 보내 주세요."}), 400

    image_file = request.files["image"]
    if not image_file.filename:
        return jsonify({"error": "선택된 파일이 없습니다."}), 400

    if not GOOGLE_API_KEY:
        return jsonify({
            "error": "GOOGLE_API_KEY가 설정되지 않았습니다. 프로젝트의 .env 파일을 확인해 주세요."
        }), 503

    try:
        image_bytes = image_file.read(MAX_IMAGE_BYTES + 1)
        ocr_text = extract_text_from_image(image_bytes)

        if not ocr_text:
            return jsonify({
                "error": "글자를 인식하지 못했어요. 글자가 선명하게 보이도록 다시 촬영해 주세요."
            }), 422

        matches = find_matches(ocr_text)
        easy_text = make_easy_text(ocr_text, matches)

        # Keep the response fields used in the original Colab API.
        return jsonify({
            "ocr_text": ocr_text,
            "matches": matches,
            "easy_text": easy_text,
        })

    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        app.logger.exception("번역 처리 오류")
        return jsonify({
            "error": "사진 처리 또는 번역 중 오류가 발생했습니다. 터미널 로그를 확인해 주세요."
        }), 500


if __name__ == "__main__":
    print("카메라 번역기 로컬 서버를 시작합니다.")
    print("브라우저에서 http://127.0.0.1:5000 을 열어 주세요.")
    if dictionary_warning:
        print("\n[단어장 안내]")
        print(dictionary_warning)
    if not GOOGLE_API_KEY:
        print("\n[API 키 안내] .env 파일에 GOOGLE_API_KEY를 설정해 주세요.")
    app.run(host="127.0.0.1", port=5000, debug=True)
