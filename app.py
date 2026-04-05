import streamlit as st
import anthropic
import pdfplumber
import base64
import json
import re
import os
import time
import random
import hashlib
import tempfile
from pathlib import Path
import fitz

# ─── PAGE CONFIG ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI PDF Cleaner",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── CUSTOM CSS ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
  /* Global font */
  html, body, [class*="css"] { font-family: 'Inter', 'Segoe UI', sans-serif; }

  /* Header gradient bar */
  .app-header {
    background: linear-gradient(135deg, #1F4E79 0%, #2E75B6 60%, #5BA3D9 100%);
    border-radius: 12px;
    padding: 32px 36px 24px 36px;
    margin-bottom: 28px;
    color: white;
  }
  .app-header h1 { color: white; margin: 0 0 6px 0; font-size: 2.1rem; font-weight: 800; }
  .app-header p  { color: rgba(255,255,255,0.85); margin: 0; font-size: 1rem; }

  /* Stage pipeline pills */
  .pipeline-row { display: flex; gap: 6px; flex-wrap: wrap; margin: 12px 0 20px 0; }
  .stage-pill {
    background: #EAF2FB; color: #1F4E79;
    border-radius: 20px; padding: 5px 14px;
    font-size: 0.78rem; font-weight: 600; border: 1.5px solid #2E75B6;
    white-space: nowrap;
  }
  .stage-pill.active { background: #2E75B6; color: white; }

  /* Confidence badge colours */
  .badge {
    display: inline-block; padding: 3px 12px; border-radius: 12px;
    font-size: 0.82rem; font-weight: 700; letter-spacing: 0.3px;
  }
  .badge-high   { background: #D4EDDA; color: #155724; }
  .badge-medium { background: #FFF3CD; color: #856404; }
  .badge-low    { background: #FFE0B2; color: #BF5700; }
  .badge-very-low { background: #F8D7DA; color: #721C24; }

  /* Chunk card */
  .chunk-card {
    background: #FAFCFF; border: 1px solid #D0E4F5;
    border-left: 5px solid #2E75B6;
    border-radius: 8px; padding: 16px 18px; margin-bottom: 14px;
  }
  .chunk-card.high    { border-left-color: #28A745; }
  .chunk-card.medium  { border-left-color: #FFC107; }
  .chunk-card.low     { border-left-color: #FF7043; }
  .chunk-card.very-low{ border-left-color: #DC3545; }

  /* Stat card */
  .stat-box {
    background: white; border: 1px solid #D6E4F0;
    border-radius: 10px; padding: 18px 20px; text-align: center;
  }
  .stat-box .stat-value { font-size: 2rem; font-weight: 800; color: #1F4E79; }
  .stat-box .stat-label { font-size: 0.78rem; color: #666; margin-top: 2px; }

  /* Progress bar custom */
  .stProgress > div > div > div { background: linear-gradient(90deg, #2E75B6, #5BA3D9); }

  /* Sidebar polish */
  section[data-testid="stSidebar"] { background: #F0F6FC; }

  /* Info/warning boxes */
  .info-box {
    background: #EAF2FB; border-left: 4px solid #2E75B6;
    border-radius: 6px; padding: 12px 16px; margin: 10px 0; font-size: 0.9rem;
  }
  .warn-box {
    background: #FFF8E1; border-left: 4px solid #FFC107;
    border-radius: 6px; padding: 12px 16px; margin: 10px 0; font-size: 0.9rem;
  }
</style>
""", unsafe_allow_html=True)

# ─── HEADER ──────────────────────────────────────────────────────────────────
st.markdown("""
<div class="app-header">
  <h1>📄 AI PDF Cleaning & Enhancement Pipeline</h1>
  <p>Upload a poor-quality PDF → extract text & images → clean with AI → get confidence-scored results</p>
</div>
""", unsafe_allow_html=True)

# Pipeline stage pills
st.markdown("""
<div class="pipeline-row">
  <span class="stage-pill">① Ingest & Triage</span>
  <span>→</span>
  <span class="stage-pill">② Text Extraction</span>
  <span>→</span>
  <span class="stage-pill">③ Image Rasterization</span>
  <span>→</span>
  <span class="stage-pill">④ AI Cleaning</span>
  <span>→</span>
  <span class="stage-pill">⑤ Confidence Scoring</span>
</div>
""", unsafe_allow_html=True)

# ─── SIDEBAR ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Configuration")

    api_key = st.text_input(
        "Anthropic API Key",
        type="password",
        placeholder="sk-ant-...",
        help="Get your key at console.anthropic.com"
    )

    st.markdown("---")
    st.markdown("### 📐 Text Splitting")
    chunk_size = st.slider("Max chunk size (chars)", 500, 4000, 2000, 100)
    overlap    = st.slider("Chunk overlap (chars)",   50,  500,  200,  25)

    st.markdown("### 🖼️ Image Quality")
    dpi = st.selectbox("Rasterization DPI", [100, 150, 200, 300], index=2,
                       help="Higher DPI = better quality but slower & more tokens")

    st.markdown("### 🎯 Confidence Thresholds")
    st.markdown("""
    <div style="font-size:0.82rem; line-height:1.9;">
      <span class="badge badge-high">HIGH</span> &nbsp;0.85 – 1.0 &nbsp;Auto-accept<br>
      <span class="badge badge-medium">MEDIUM</span> &nbsp;0.60 – 0.84 &nbsp;Spot-check<br>
      <span class="badge badge-low">LOW</span> &nbsp;0.30 – 0.59 &nbsp;Human review<br>
      <span class="badge badge-very-low">VERY LOW</span> &nbsp;0.0 – 0.29 &nbsp;Unreadable
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    min_conf = st.slider("Filter: show chunks ≥ confidence", 0.0, 1.0, 0.0, 0.05)

    st.markdown("---")
    st.markdown("### ℹ️ About")
    st.markdown("""
    <div style="font-size:0.8rem; color:#555; line-height:1.6;">
    This app uses <b>Claude AI</b> (no ML training) to:<br>
    • Read scanned image pages via vision<br>
    • Clean garbled/noisy extracted text<br>
    • Score output quality (0–1)<br>
    • Split text into coherent chunks
    </div>
    """, unsafe_allow_html=True)

# ─── HELPERS ─────────────────────────────────────────────────────────────────

CACHE = {}

def cache_key(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:20]

def confidence_label(score: float):
    if score >= 0.85: return "high",     "HIGH",     "badge-high"
    if score >= 0.60: return "medium",   "MEDIUM",   "badge-medium"
    if score >= 0.30: return "low",      "LOW",      "badge-low"
    return               "very-low", "VERY LOW", "badge-very-low"

def heuristic_score(text: str) -> float:
    if not text or len(text) < 10:
        return 0.0
    printable   = sum(1 for c in text if c.isprintable())
    ratio       = printable / len(text)
    specials    = len(re.findall(r'[^a-zA-Z0-9\s.,;:!?\-\'"()\[\]{}@#%&*+=/<>]', text))
    spec_ratio  = specials / max(len(text), 1)
    return min(1.0, max(0.0, ratio - spec_ratio * 2))

def combined_confidence(ai_score: float, text: str) -> float:
    h = heuristic_score(text)
    return round((ai_score * 0.70) + (h * 0.30), 3)

# ─── STAGE 1: PAGE TRIAGE ────────────────────────────────────────────────────

def classify_pages(pdf_path: str) -> dict:
    page_map = {}
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            page_map[i] = "text" if len(text.strip()) >= 20 else "image"
    return page_map

# ─── STAGE 2: TEXT EXTRACTION + SPLITTING ────────────────────────────────────

def extract_text_pages(pdf_path: str, page_map: dict) -> dict:
    extracted = {}
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            if page_map.get(i) == "text":
                extracted[i] = page.extract_text() or ""
    return extracted

def split_text(text: str, max_chars: int = 2000, overlap: int = 200) -> list[str]:
    paragraphs = re.split(r'\n{2,}', text)
    chunks, current = [], ""
    for p in paragraphs:
        if len(current) + len(p) > max_chars and current:
            chunks.append(current.strip())
            current = current[-overlap:] + "\n\n" + p
        else:
            current += ("\n\n" if current else "") + p
    if current.strip():
        chunks.append(current.strip())
    return chunks or [text]

# ─── STAGE 3: RASTERIZE ──────────────────────────────────────────────────────

def rasterize_pages(pdf_path: str, page_map: dict, dpi: int = 200) -> dict:
    images = {}
    tmp_dir = tempfile.mkdtemp()
    doc = fitz.open(pdf_path)
    for page_num, ptype in page_map.items():
        if ptype == "image":
            page = doc.load_page(page_num)
            pix = page.get_pixmap(dpi=dpi)
            out_path = os.path.join(tmp_dir, f"page_{page_num}.jpg")
            pix.save(out_path)
            images[page_num] = out_path
    return images

# ─── STAGE 4: AI CLEANING ────────────────────────────────────────────────────

def clean_text_chunk(client: anthropic.Anthropic, raw_chunk: str) -> dict:
    ck = cache_key(raw_chunk)
    if ck in CACHE:
        return CACHE[ck]

    prompt = f"""You are a document restoration expert. This text was extracted from a poor-quality PDF.
It may contain garbled characters, broken words, odd spacing, repeated headers, or incomplete sentences.

Your task:
1. Fix spelling and character errors
2. Restore sentence structure and paragraph flow
3. Remove noise (duplicate headers, page numbers, watermark artifacts)
4. Return a JSON object ONLY — no markdown, no preamble:

{{
  "cleaned_text": "<the fully cleaned text>",
  "confidence": <float 0.0–1.0>,
  "issues_found": ["list of specific problems you detected and fixed"]
}}

Confidence guide:
- 1.0 = pristine, no issues
- 0.85 = minor fixes, clearly readable
- 0.65 = moderate noise, mostly recovered
- 0.40 = significant corruption, best-effort
- 0.15 = mostly unreadable

Raw extracted text:
\"\"\"
{raw_chunk}
\"\"\"
"""
    for attempt in range(3):
        try:
            response = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = response.content[0].text.strip()
            raw = re.sub(r'^```json\s*', '', raw)
            raw = re.sub(r'```$', '', raw).strip()
            result = json.loads(raw)
            result["confidence"] = float(result.get("confidence", 0.5))
            CACHE[ck] = result
            return result
        except json.JSONDecodeError:
            # Fallback: return plain text with mid confidence
            result = {"cleaned_text": raw, "confidence": 0.5, "issues_found": ["JSON parse error — raw output returned"]}
            CACHE[ck] = result
            return result
        except anthropic.APIError:
            raise
        except Exception as e:
            if attempt == 2:
                return {"cleaned_text": raw_chunk, "confidence": 0.2, "issues_found": [f"API error: {str(e)}"]}
            time.sleep(2 ** attempt + random.uniform(0, 0.5))

def transcribe_image_page(client: anthropic.Anthropic, image_path: str) -> dict:
    ck = cache_key(image_path + str(os.path.getmtime(image_path)))
    if ck in CACHE:
        return CACHE[ck]

    with open(image_path, "rb") as f:
        img_data = base64.standard_b64encode(f.read()).decode("utf-8")

    for attempt in range(3):
        try:
            response = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=3000,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": "image/jpeg", "data": img_data}
                        },
                        {
                            "type": "text",
                            "text": """This is a page from a scanned or photographed document that may be poor quality.
Please transcribe ALL visible text accurately.
- Preserve headings, paragraphs, and list structures
- Render tables as plain text with | separators
- Mark illegible words as [unclear]
- Note if large portions are unreadable

Then return a JSON object ONLY — no markdown, no preamble:
{
  "transcribed": "<full transcribed text>",
  "confidence": <float 0.0–1.0>,
  "issues_found": ["list of quality issues observed"]
}

Confidence guide:
- 1.0 = crystal clear scan
- 0.75 = mostly readable, minor issues
- 0.50 = significant blur/noise but recoverable
- 0.25 = severely degraded, partial recovery only"""
                        }
                    ]
                }]
            )
            raw = response.content[0].text.strip()
            raw = re.sub(r'^```json\s*', '', raw)
            raw = re.sub(r'```$', '', raw).strip()
            result = json.loads(raw)
            result["confidence"] = float(result.get("confidence", 0.6))
            result["cleaned_text"] = result.pop("transcribed", "")
            CACHE[ck] = result
            return result
        except json.JSONDecodeError:
            result = {"cleaned_text": raw, "confidence": 0.5, "issues_found": ["JSON parse error"]}
            CACHE[ck] = result
            return result
        except anthropic.APIError:
            raise
        except Exception as e:
            if attempt == 2:
                return {"cleaned_text": "", "confidence": 0.1, "issues_found": [f"Vision API error: {str(e)}"]}
            time.sleep(2 ** attempt + random.uniform(0, 0.5))

# ─── MAIN PIPELINE ───────────────────────────────────────────────────────────

def run_pipeline(pdf_path: str, api_key: str, chunk_size: int, overlap: int, dpi: int):
    client = anthropic.Anthropic(api_key=api_key)
    results = []

    # ── Stage 1 ──────────────────────────────────────────────────────────────
    status = st.status("⚙️ Running pipeline...", expanded=True)
    with status:
        st.write("**Stage 1:** Triaging pages...")
        page_map = classify_pages(pdf_path)
        n_text  = sum(1 for v in page_map.values() if v == "text")
        n_image = sum(1 for v in page_map.values() if v == "image")
        st.write(f"→ {len(page_map)} pages found: **{n_text} text**, **{n_image} image/scan**")

        # ── Stage 2 ──────────────────────────────────────────────────────────
        st.write("**Stage 2:** Extracting text from text-based pages...")
        text_pages = extract_text_pages(pdf_path, page_map)

        total_chunks = sum(len(split_text(t, chunk_size, overlap)) for t in text_pages.values())
        st.write(f"→ {len(text_pages)} text pages → ~{total_chunks} chunks")

        # ── Stage 3 ──────────────────────────────────────────────────────────
        image_pages = {}
        if n_image > 0:
            st.write(f"**Stage 3:** Rasterizing {n_image} image page(s) at {dpi} DPI...")
            image_pages = rasterize_pages(pdf_path, page_map, dpi)
            st.write(f"→ {len(image_pages)} page images ready")

        # ── Stage 4 + 5 ──────────────────────────────────────────────────────
        st.write("**Stage 4 & 5:** AI cleaning + confidence scoring...")
        progress = st.progress(0)
        processed = 0
        total_work = total_chunks + len(image_pages)

        # Text chunks
        for page_num, raw_text in text_pages.items():
            chunks = split_text(raw_text, chunk_size, overlap)
            for ci, chunk in enumerate(chunks):
                result = clean_text_chunk(client, chunk)
                ai_conf = result.get("confidence", 0.5)
                final_conf = combined_confidence(ai_conf, result.get("cleaned_text", ""))
                results.append({
                    "page":       page_num + 1,
                    "chunk":      ci + 1,
                    "type":       "📝 Text",
                    "content":    result.get("cleaned_text", chunk),
                    "raw":        chunk,
                    "confidence": final_conf,
                    "ai_conf":    ai_conf,
                    "issues":     result.get("issues_found", []),
                })
                processed += 1
                progress.progress(processed / max(total_work, 1))

        # Image pages
        for page_num, img_path in image_pages.items():
            result = transcribe_image_page(client, img_path)
            ai_conf = result.get("confidence", 0.6)
            final_conf = combined_confidence(ai_conf, result.get("cleaned_text", ""))
            results.append({
                "page":       page_num + 1,
                "chunk":      1,
                "type":       "🖼️ Image/Scan",
                "content":    result.get("cleaned_text", ""),
                "raw":        "",
                "confidence": final_conf,
                "ai_conf":    ai_conf,
                "issues":     result.get("issues_found", []),
            })
            processed += 1
            progress.progress(processed / max(total_work, 1))

        progress.progress(1.0)
        status.update(label="✅ Pipeline complete!", state="complete")

    results.sort(key=lambda x: (x["page"], x["chunk"]))
    return results

# ─── RESULTS DISPLAY ─────────────────────────────────────────────────────────

def show_confidence_chart(results: list):
    import statistics
    scores = [r["confidence"] for r in results]
    if not scores:
        return
    avg = statistics.mean(scores)
    high   = sum(1 for s in scores if s >= 0.85)
    medium = sum(1 for s in scores if 0.60 <= s < 0.85)
    low    = sum(1 for s in scores if 0.30 <= s < 0.60)
    vlow   = sum(1 for s in scores if s < 0.30)

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.markdown(f"""
        <div class="stat-box">
          <div class="stat-value">{len(scores)}</div>
          <div class="stat-label">Total Chunks</div>
        </div>""", unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div class="stat-box">
          <div class="stat-value" style="color:#2E75B6">{avg:.2f}</div>
          <div class="stat-label">Avg Confidence</div>
        </div>""", unsafe_allow_html=True)
    with col3:
        st.markdown(f"""
        <div class="stat-box">
          <div class="stat-value" style="color:#28A745">{high}</div>
          <div class="stat-label">High (≥0.85)</div>
        </div>""", unsafe_allow_html=True)
    with col4:
        st.markdown(f"""
        <div class="stat-box">
          <div class="stat-value" style="color:#FFC107">{medium}</div>
          <div class="stat-label">Medium (0.60–0.84)</div>
        </div>""", unsafe_allow_html=True)
    with col5:
        st.markdown(f"""
        <div class="stat-box">
          <div class="stat-value" style="color:#DC3545">{low + vlow}</div>
          <div class="stat-label">Low / Very Low</div>
        </div>""", unsafe_allow_html=True)

def show_results(results: list, min_conf: float):
    filtered = [r for r in results if r["confidence"] >= min_conf]

    st.markdown(f"### 📋 Results — {len(filtered)} chunk(s) shown")
    if len(filtered) < len(results):
        st.caption(f"({len(results) - len(filtered)} chunk(s) hidden by confidence filter)")

    for r in filtered:
        level, label, badge_cls = confidence_label(r["confidence"])
        bar_color = {"high": "#28A745", "medium": "#FFC107", "low": "#FF7043", "very-low": "#DC3545"}[level]
        bar_pct   = int(r["confidence"] * 100)

        with st.expander(
            f"Page {r['page']} · Chunk {r['chunk']} · {r['type']} · "
            f"Confidence: {r['confidence']:.3f}",
            expanded=(level in ("high", "medium"))
        ):
            # Confidence bar
            st.markdown(f"""
            <div style="display:flex; align-items:center; gap:10px; margin-bottom:10px;">
              <span class="badge {badge_cls}">{label}</span>
              <div style="flex:1; background:#E9ECEF; border-radius:6px; height:10px; overflow:hidden;">
                <div style="width:{bar_pct}%; background:{bar_color}; height:100%; border-radius:6px;
                            transition:width 0.4s ease;"></div>
              </div>
              <span style="font-size:0.85rem; font-weight:700; color:{bar_color}; min-width:38px;">
                {r['confidence']:.0%}
              </span>
            </div>
            <div style="font-size:0.78rem; color:#666; margin-bottom:8px;">
              AI confidence: {r['ai_conf']:.3f} &nbsp;|&nbsp; Heuristic blend applied
            </div>
            """, unsafe_allow_html=True)

            # Issues
            if r["issues"]:
                with st.container():
                    st.markdown("**⚠️ Issues detected & fixed:**")
                    for issue in r["issues"]:
                        st.markdown(f"- {issue}")

            # Tabs: cleaned / raw
            if r["raw"]:
                tab_clean, tab_raw = st.tabs(["✅ Cleaned Output", "📄 Raw Extracted"])
                with tab_clean:
                    st.text_area("", r["content"], height=200, key=f"clean_{r['page']}_{r['chunk']}")
                with tab_raw:
                    st.text_area("", r["raw"], height=200, key=f"raw_{r['page']}_{r['chunk']}")
            else:
                st.text_area("✅ AI Transcription", r["content"], height=200,
                             key=f"trans_{r['page']}_{r['chunk']}")

            # Copy action hint
            st.caption("💡 Click inside the text box and Ctrl+A to select all, then copy.")

def build_download(results: list) -> str:
    lines = ["AI PDF Cleaning Pipeline — Export", "=" * 60, ""]
    for r in results:
        level, label, _ = confidence_label(r["confidence"])
        lines += [
            f"Page {r['page']} | Chunk {r['chunk']} | {r['type']}",
            f"Confidence: {r['confidence']:.3f} [{label}]",
            "-" * 40,
            r["content"],
            "",
        ]
    return "\n".join(lines)

# ─── MAIN UI ─────────────────────────────────────────────────────────────────

uploaded = st.file_uploader(
    "Upload a PDF (scanned, poor quality, or mixed)",
    type=["pdf"],
    help="Works best with scanned documents, photographed pages, or PDFs with garbled text"
)

if not api_key:
    st.markdown("""
    <div class="warn-box">
    ⚠️ <b>API key required.</b> Enter your Anthropic API key in the sidebar to begin.
    Get one free at <a href="https://console.anthropic.com" target="_blank">console.anthropic.com</a>
    </div>
    """, unsafe_allow_html=True)

if uploaded and api_key:
    # Save to temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded.read())
        tmp_path = tmp.name

    st.markdown(f"""
    <div class="info-box">
    📂 <b>{uploaded.name}</b> uploaded — {uploaded.size // 1024} KB
    </div>
    """, unsafe_allow_html=True)

    col_btn, col_info = st.columns([1, 3])
    with col_btn:
        run_btn = st.button("🚀 Run Pipeline", type="primary", use_container_width=True)
    with col_info:
        st.caption(f"Chunk size: {chunk_size} chars | Overlap: {overlap} | DPI: {dpi}")

    if run_btn or "results" in st.session_state:
        if run_btn:
            st.session_state.pop("results", None)

        if "results" not in st.session_state:
            try:
                results = run_pipeline(tmp_path, api_key, chunk_size, overlap, dpi)
                st.session_state["results"] = results
            except anthropic.AuthenticationError:
                st.error("🔑 **Invalid Anthropic API Key!** Please check your key in the sidebar.")
                st.stop()
            except anthropic.APIError as e:
                st.error(f"⚠️ **Anthropic API Error:** {e}")
                st.stop()
            except Exception as e:
                st.error(f"Pipeline error: {e}")
                st.stop()

        results = st.session_state.get("results", [])

        if results:
            st.markdown("---")
            st.markdown("## 📊 Confidence Overview")
            show_confidence_chart(results)

            st.markdown("---")

            # Download button
            dl_text = build_download(results)
            st.download_button(
                "⬇️ Download All Cleaned Text",
                data=dl_text,
                file_name=f"cleaned_{Path(uploaded.name).stem}.txt",
                mime="text/plain"
            )

            st.markdown("---")
            show_results(results, min_conf)

    # Cleanup
    try:
        os.unlink(tmp_path)
    except Exception:
        pass

elif not uploaded:
    st.markdown("""
    <div style="text-align:center; padding:48px 24px; color:#888;">
      <div style="font-size:3.5rem; margin-bottom:12px;">📄</div>
      <div style="font-size:1.1rem; font-weight:600; color:#555;">Upload a PDF to get started</div>
      <div style="font-size:0.9rem; margin-top:8px;">
        Works with scanned documents, photographed pages, mixed-content PDFs, and anything hard to read.
      </div>
    </div>
    """, unsafe_allow_html=True)
