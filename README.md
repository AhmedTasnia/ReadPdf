# 📄 AI PDF Cleaning & Enhancement Pipeline

A Streamlit app that uses **Claude AI** (no ML training) to clean, reconstruct, and confidence-score content from poor-quality PDFs.

## Features
- **Page triage** — auto-detects text vs scanned/image pages
- **Text extraction + splitting** — pdfplumber + configurable overlap chunking  
- **Image rasterization** — pdftoppm converts scanned pages to PNG at configurable DPI
- **AI cleaning** — Claude cleans garbled text and transcribes image pages via vision
- **Confidence scoring** — 0–1 score (AI self-assessment blended with heuristics)
- **Confidence range display** — HIGH / MEDIUM / LOW / VERY LOW with colour coding
- **Downloadable output** — all cleaned text as a single file

## Deploy to Streamlit Community Cloud (Free)

### Step 1 — Push to GitHub
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/pdf-cleaner.git
git push -u origin main
```

### Step 2 — Deploy on Streamlit Cloud
1. Go to **https://share.streamlit.io**
2. Click **"New app"**
3. Select your GitHub repository
4. Set **Main file path** to `app.py`
5. Click **"Deploy"**

### Step 3 — Add your API key (Secrets)
In Streamlit Cloud dashboard → your app → **Settings** → **Secrets**, add:
```toml
ANTHROPIC_API_KEY = "sk-ant-your-key-here"
```

> **Note:** The app also accepts the key via the sidebar UI at runtime, so secrets are optional — users can paste their own key.

## Run Locally

```bash
pip install -r requirements.txt
sudo apt-get install poppler-utils   # Linux
brew install poppler                  # macOS

streamlit run app.py
```

## File Structure
```
pdf-cleaner/
├── app.py                  # Main Streamlit application
├── requirements.txt        # Python dependencies
├── packages.txt            # System dependencies (poppler-utils)
├── .streamlit/
│   └── config.toml         # Theme and server config
└── README.md
```

## Pipeline Stages
| Stage | What happens |
|-------|-------------|
| 1. Ingest & Triage | Classify each page: text-extractable vs image/scan |
| 2. Text Extraction | pdfplumber extracts raw text; split into overlapping chunks |
| 3. Rasterization | pdftoppm converts image pages to JPEG at chosen DPI |
| 4. AI Cleaning | Claude cleans text chunks and transcribes image pages via vision |
| 5. Confidence Scoring | AI score (70%) + heuristic score (30%) = final 0–1 score |

## Confidence Ranges
| Range | Label | Recommended Action |
|-------|-------|--------------------|
| 0.85 – 1.0 | HIGH | Auto-accept |
| 0.60 – 0.84 | MEDIUM | Spot-check review |
| 0.30 – 0.59 | LOW | Human review required |
| 0.00 – 0.29 | VERY LOW | Mark unreadable / escalate |

## Requirements
- Python 3.10+
- Anthropic API key (get one at console.anthropic.com)
- poppler-utils (system package — automatically installed on Streamlit Cloud via packages.txt)
