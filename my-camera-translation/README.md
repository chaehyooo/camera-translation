# 카메라 번역기 — VS Code 로컬 실행 버전

이 프로젝트는 `카메라_번역.ipynb`의 핵심 흐름을 VS Code에서 실행할 수 있도록 옮긴 버전입니다.

- 카메라 촬영 또는 이미지 업로드
- EasyOCR을 이용한 한국어/영어 텍스트 인식
- 엑셀 단어장과 비교해 어려운 단어 검색
- Gemini를 이용해 쉬운 한국어 설명 생성
- Flask API (`POST /api/translate`) 제공

## 1. 준비물

- 권장 Python: **3.11**
- VS Code
- Google Gemini API 키
- 엑셀 단어장 (필수 컬럼명: `어려운 단어`, `쉬운 단어`)

> 이 버전은 Colab 전용 `google.colab.files`, `google.colab.userdata`, Colab JavaScript 웹캠 코드를 사용하지 않습니다. VS Code에서 로컬 Python 서버를 켜고 브라우저에서 카메라를 사용합니다.

## 2. 프로젝트 열기

1. ZIP 파일 압축을 풉니다.
2. VS Code에서 `camera-translation-vscode` 폴더 전체를 엽니다.
3. 메뉴에서 **Terminal → New Terminal**을 선택합니다.

## 3. 가상환경 만들기 및 라이브러리 설치 (Windows PowerShell)

터미널에서 아래 명령어를 한 줄씩 실행하세요.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

PowerShell이 가상환경 실행을 차단하면 활성화 단계는 건너뛰고 다음처럼 가상환경 Python을 직접 사용해도 됩니다.

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

EasyOCR은 처음 OCR을 실행할 때 모델 파일을 다운로드합니다. 첫 실행은 인터넷 연결과 디스크 공간이 필요하고, 모델 로딩이 느릴 수 있습니다.

## 4. API 키 설정

1. 프로젝트 폴더에서 `.env.example` 파일을 복사합니다.
2. 복사한 파일 이름을 `.env`로 바꿉니다.
3. `.env` 파일의 `GOOGLE_API_KEY` 값을 실제 API 키로 바꿉니다.

**실제 API 키를 `app.py`에 직접 붙여 넣거나 GitHub에 올리지 마세요.** `.env`는 `.gitignore`에 포함돼 있습니다.

## 5. 엑셀 단어장 넣기

`data` 폴더에 엑셀 파일을 넣고 이름을 `dictionary.xlsx`로 지정합니다.

엑셀에는 아래 두 열이 있어야 합니다.

| 어려운 단어 | 쉬운 단어 |
|---|---|
| 수급권자 | 지원을 받을 수 있는 권리가 있는 사람 |
| 비급여 | 건강보험에서 비용을 지원하지 않는 항목 |

위 표는 형식 예시입니다. 실제 프로젝트에서 사용하는 단어장으로 교체하세요. 단어장을 제공하지 않아도 서버가 시작되지만, 사전 검색 결과는 비어 있게 됩니다. 로컬 데이터에는 민감한 정보가 없고 공개해도 되는지 확인하기 전까지 GitHub에 올리지 마세요.

## 6. 실행

```powershell
python app.py
```

브라우저에서 아래 주소를 엽니다.

- 웹 화면: http://127.0.0.1:5000
- 상태 확인: http://127.0.0.1:5000/api/status
- 헬스 체크: http://127.0.0.1:5000/health
- 번역 API: `POST http://127.0.0.1:5000/api/translate`

웹 화면에서 **카메라 켜기 → 사진 촬영 후 번역**을 누르거나 이미지 파일을 선택하면 됩니다. 카메라 사용 권한을 허용해야 합니다.

## 7. API 요청 형식

프론트엔드에서 `multipart/form-data`로 전송하고, 이미지 필드명은 `image`로 지정합니다.

```javascript
const formData = new FormData();
formData.append("image", imageFile);

const response = await fetch("http://127.0.0.1:5000/api/translate", {
  method: "POST",
  body: formData
});
const data = await response.json();
```

응답 필드는 원래 Colab API에서 쓰던 이름을 유지합니다.

- `ocr_text`: OCR로 읽은 원문
- `matches`: 단어장에 있는 어려운 단어 및 쉬운 설명
- `easy_text`: Gemini가 생성한 쉬운 말 결과

## 8. 팀 앱과의 관계

이 프로젝트는 개인 개발/테스트용 로컬 버전입니다. 팀 서비스 `hanunne`의 백엔드에 자동으로 연결되거나 Render에 배포하지 않습니다. 팀 앱에 통합할 때는 기존 API 응답 형식과 백엔드 구조를 확인한 후 필요한 함수만 통합하세요.

## 문제 해결

- **`GOOGLE_API_KEY` 오류:** `.env` 파일이 프로젝트 루트에 있는지, 키 이름과 값을 확인하세요.
- **단어장이 안 잡힘:** `data/dictionary.xlsx` 경로와 두 컬럼명을 확인하세요.
- **카메라가 안 켜짐:** 브라우저 권한을 허용하거나 이미지 파일 업로드 방식으로 테스트하세요.
- **EasyOCR 설치 오류:** Python 3.11 가상환경을 사용하고, VS Code의 Python Interpreter가 `.venv`인지 확인하세요.
- **Gemini 모델/API 오류:** API 키와 해당 모델 접근 권한을 확인하세요. 필요하면 `.env`의 `GEMINI_MODEL` 값을 계정에서 사용할 수 있는 모델명으로 변경하세요.
