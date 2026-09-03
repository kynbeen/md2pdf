# md2pdf

> **출판 품질의 조판과 지능형 이미지 배치를 제공하는 마크다운-PDF 변환기**  
> High-fidelity Markdown to PDF renderer with refined typography and smart figure layout.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.9+](https://img.shields.io/badge/Python-3.9%2B-brightgreen.svg)](https://www.python.org/)
[![Engine: Playwright](https://img.shields.io/badge/Engine-Playwright%20Chromium-orange.svg)](https://playwright.dev/)

`md2pdf`는 복잡한 LaTeX이나 무거운 외부 툴체인 없이, **마크다운(`.md`) 파일 하나로 세련된 A4 출판용 PDF를 생성**하는 독립 도구입니다. `summary.ai`의 고품질 문서화 파이프라인에서 핵심 렌더러를 추출하여 단독으로 사용할 수 있도록 패키징했습니다.

---

## ✨ 핵심 특징 (Key Features)

### 1. 섬세한 타이포그래피 (Refined Typography)
- **한글 + 영문 듀얼 폰트 시스템**: 한글은 가독성이 뛰어난 **Pretendard**, 영문·숫자·기호는 **Open Sans**로 자동 분기 렌더링됩니다.
- **코드 및 수식 블록**: `D2Coding` 및 `Consolas` 기반의 미려하고 정갈한 코드 펜스를 지원합니다.
- **어절 단위 줄바꿈**: `word-break: keep-all` 적용으로 단어가 어색하게 끊어지지 않아 문단이 깔끔합니다.

### 2. 지능형 이미지 피겨 배치 엔진 (Smart 40% Figure Layout)
일반적인 PDF 변환 도구는 페이지 하단에 이미지가 걸치면 그림이 반으로 잘리거나 캡션만 다음 페이지로 밀려나는 문제가 있습니다.
- `md2pdf`는 헤드리스 Chromium과 `PyMuPDF`를 통해 페이지 여백을 멀티패스로 정밀 측정합니다.
- **40% 규칙**: 페이지 잔여 공간이 40% 이상이면 이미지를 안전 여유를 두고 축소하여 현재 페이지에 배치하고, 40% 미만이면 그림과 캡션을 세트로 다음 페이지 시작 위치로 넘깁니다.

### 3. 출판용 규격 레이아웃 (Publication-Ready A4 Layout)
- **A4 정규 여백**: 상단 18mm, 하단 16mm, 좌우 15mm.
- **러닝 헤더/푸터**: 상단 중앙에 문서 제목(`title`), 하단 중앙에 깔끔한 페이지 번호(`현재 / 전체`)가 자동 삽입됩니다.
- **표(Table) 분할 방어**: 표의 머리행(`thead`)은 페이지가 바뀌어도 자동 반복되며, 행(`tr`) 중간이 쪼개지지 않습니다.

### 4. 간편한 자산 자립성 (Self-Contained & Relative Paths)
- Pretendard, Open Sans 폰트와 Typora 기반 커스텀 테마(`typora.css`)가 패키지 내부에 번들링되어 있습니다.
- 마크다운 파일의 위치를 기준으로 로컬 상대 경로 이미지(`![alt](./images/fig1.png)`)가 완벽하게 로드됩니다.

---

## 🚀 빠른 시작 (Quick Start)

### 1. 설치 (Installation)

```bash
# 1. 저장소 복제
git clone https://github.com/kynbeen/md2pdf.git
cd md2pdf

# 2. 의존성 설치
pip install -r requirements.txt

# 3. Playwright Chromium 브라우저 설치 (최초 1회)
playwright install chromium
```

> **선택사항**: 로컬 패키지로 설치하여 터미널 어디서든 `md2pdf` 명령어를 사용하려면:
> ```bash
> pip install -e .
> ```

---

## 💻 사용법 (Usage)

### CLI 명령줄 도구

```bash
# 기본 사용법: 입력과 같은 이름의 .pdf 생성
md2pdf document.md

# 출력 파일 경로 지정
md2pdf document.md -o output.pdf

# 헤더에 들어갈 문서 제목 지정 (미지정 시 첫 # H1 제목 또는 파일명 자동 감지)
md2pdf document.md --title "2026 연례 연구 보고서"

# 테마 선택 ('custom' 기본값 또는 'github')
md2pdf document.md --theme github

# 전처리(리스트 들여쓰기 4칸 정규화 등) 비활성화
md2pdf document.md --no-preprocess
```

### Python API

Python 코드 내에서 직접 마크다운을 PDF로 변환할 수 있습니다:

```python
from md2pdf import render, build_html

# 마크다운 파일 변환
pdf_path = render(
    input_path="document.md",
    output_path="report.pdf",
    title="시스템 사양서",
    theme="custom"  # 또는 "github"
)
print(f"생성 완료: {pdf_path}")
```

---

## 📂 프로젝트 구조 (Project Structure)

```
md2pdf/
├── src/
│   └── md2pdf/
│       ├── __init__.py        # 모듈 진입점
│       ├── cli.py             # CLI 커맨드라인 도구
│       ├── renderer.py        # PDF 변환 & 지능형 피겨 레이아웃 엔진
│       ├── preprocess.py      # 리스트 들여쓰기/블록 여백 정규화기
│       └── assets/
│           ├── typora.css     # 출판용 메인 스타일시트
│           ├── fonts/         # Pretendard 폰트 파일
│           └── themes/        # GitHub 테마 및 Open Sans woff2
├── examples/
│   ├── sample.md              # 다채로운 조판 요소를 담은 예제 문서
│   └── architecture.svg       # 예제용 다이어그램
├── tests/
│   └── test_renderer.py       # 단위 및 통합 테스트
├── pyproject.toml             # 패키징 설정
├── requirements.txt           # 의존성 목록
└── LICENSE                    # MIT 라이선스
```

---

## 🎨 테마 비교 (Themes)

| 테마명 | 특징 |
| :--- | :--- |
| **`custom` (기본)** | Pretendard + Open Sans 폰트, 회색 톤 그리드 표, 박스형 코드펜스, 인쇄에 최적화된 서식 |
| **`github`** | GitHub Flavored Markdown 스타일을 충실하게 재현한 깔끔한 문서 서식 |

---

## 📜 라이선스 및 글꼴 출처 (License & Fonts)

- **Source Code**: [MIT License](LICENSE)
- **Pretendard Font**: [SIL Open Font License 1.1](https://github.com/orioncactus/pretendard) (자유로운 상업적/비상업적 이용 가능)
- **Open Sans Font**: [Apache License 2.0](https://fonts.google.com/specimen/Open+Sans)

