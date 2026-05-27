# 01 — PDF Extraction: `pymupdf` vs `pdfplumber` vs `unstructured`

**Status:** Research Complete | **Owner:** Mnemosyne Python Satellite Layer
**Last Updated:** 2026-05-27

---

## Executive Summary

The Rust ecosystem for PDF parsing is structurally thin. While crates like `pdf-extract`, `lopdf`, and `pdf_oxide` exist, none match the depth, battle-testing, or semantic awareness of Python's dominant trio: **`pymupdf`/`pymupdf4llm`**, **`pdfplumber`**, and **`unstructured`**. For Mnemosyne's ingestion engine — which must produce structured markdown with heading hierarchies, table fidelity, and provenance metadata — Python is not merely convenient; it is the only viable path.

This document breaks down every factor: extraction quality, heading detection, table handling, performance, dependencies, licensing, and integration fit for the Rust→Python satellite model.

---

## 1. The Rust Landscape: Why It Falls Short

| Crate | Maturity | Text Extraction | Table Extraction | Heading Detection | OCR | Verdict |
|---|---|---|---|---|---|---|
| `pdf-extract` | Moderate | Basic, linear | None | None | No | Too primitive for knowledge OS |
| `lopdf` | Mature (low-level) | Manual | Manual | Manual | No | Building block, not product |
| `pdf_oxide` | Emerging (2026) | Fast (0.8ms mean) | Unknown | Unknown | No | Speed champion, semantics untested |
| `pdfium` (bindings) | Good | Good | Limited | None | Via Tesseract | Viable fallback, not leader |

**The structural problem:** Rust PDF crates excel at *parsing* (object manipulation, rendering) but lack *semantic reconstruction*. They can extract text blocks and bounding boxes, but building heading hierarchies, detecting tables as tables (not text soup), and reconstructing reading order across multi-column layouts requires years of heuristic refinement that Python libraries have accumulated.

> **Mnemosyne Decision:** Rust core spawns Python satellite for all PDF ingestion. No Rust-native PDF extraction in Phase 1.

---

## 2. The Python Contenders: Deep Comparison

### 2.1 PyMuPDF / PyMuPDF4LLM

**What it is:** Python bindings to the MuPDF C engine (Artifex), with `pymupdf4llm` as a lightweight extension that converts PDFs to structured Markdown, JSON, or plain text — purpose-built for LLM/RAG pipelines.

**Key Capabilities:**

| Feature | Detail |
|---|---|
| **Heading detection** | Maps font sizes to `#`–`######` levels automatically; supports TOC-driven headers and custom callable logic |
| **Table extraction** | Converts tables to GitHub-flavored Markdown pipe tables; includes `find_tables()` API for programmatic access |
| **Multi-column** | Reconstructs natural reading order across columns |
| **OCR** | Hybrid: auto-detects pages needing OCR (image-based or garbled text), applies Tesseract/RapidOCR only where needed |
| **Image extraction** | Embeds as `![alt](path)` or base64; configurable DPI, format, size limits |
| **Output formats** | Markdown, JSON (with bboxes), plain text, LlamaIndex/LangChain integrations |
| **Page chunks** | `page_chunks=True` returns per-page dicts with metadata, TOC items, tables, images, graphics |
| **Headers/footers** | ML-trained detection; can omit via `header=False`, `footer=False` |
| **License** | PyMuPDF: AGPL-3.0 (or commercial); PyMuPDF4LLM: Same |

**Heading Detection in Detail:**

```python
import pymupdf4llm

# Automatic: font size → heading level
md = pymupdf4llm.to_markdown("paper.pdf")
# Produces: "# Title", "## Section", "### Subsection" based on size hierarchy

# Custom callable for fine-grained control
def my_headers(span, page=None):
    if span["size"] > 16:
        return "# "
    elif span["size"] > 12:
        return "## "
    return ""

md = pymupdf4llm.to_markdown("paper.pdf", hdr_info=my_headers)

# TOC-driven: use document's internal outline
import pymupdf
doc = pymupdf.open("paper.pdf")
toc_headers = pymupdf4llm.TocHeaders(doc)
md = pymupdf4llm.to_markdown(doc, hdr_info=toc_headers)
```

**Performance:** ~0.14s per page for markdown extraction (benchmarked on academic papers). 10–250× cheaper than vision-LLM approaches.

**Strengths for Mnemosyne:**
- One-line API: `to_markdown()` produces exactly the format our compilation engine consumes.
- Heading hierarchy is first-class — critical for wiki page structure and link graph generation.
- JSON output with bounding boxes enables provenance tracking (`provenance` field in `pages` table).
- No GPU required; runs on CPU-only Foundry node.
- Page chunks align naturally with our per-page ingestion model.

**Weaknesses:**
- AGPL-3.0 license is viral. Mnemosyne is MIT-bound for code. **Mitigation:** PyMuPDF Pro offers commercial licensing; or we accept AGPL for the satellite layer (it's a subprocess, not linked).
- Multi-column layout can occasionally scramble reading order on complex magazine-style layouts.
- Table extraction is good but not perfect on borderless or heavily styled tables.

---

### 2.2 pdfplumber

**What it is:** Built on `pdfminer.six`, provides per-character, per-word, per-line access to PDF content with precise spatial coordinates. The gold standard for *programmatic* extraction where you need to build your own logic.

**Key Capabilities:**

| Feature | Detail |
|---|---|
| **Granularity** | Access to every `char` object: fontname, size, bbox, color, matrix |
| **Table extraction** | Best-in-class: detects explicit lines, implied alignments, or explicit coordinates; outputs list-of-lists or Pandas DataFrame |
| **Text extraction** | `extract_text(layout=True)` attempts visual layout mimicry; `extract_words()` for word-level bboxes |
| **Heading detection** | **Not automatic.** You build it from font size thresholds, coordinate analysis, or marked content tags |
| **OCR** | No built-in OCR; assumes text layer exists |
| **Visual debugging** | `.to_image()` renders page with detected elements highlighted |
| **License** | MIT |

**Heading Detection (Manual Build):**

```python
import pdfplumber

with pdfplumber.open("paper.pdf") as pdf:
    page = pdf.pages[0]
    chars = page.chars

    # Build heading detection from font size distribution
    sizes = [c["size"] for c in chars]
    # Threshold logic: top 10% of sizes = H1, next 20% = H2, etc.
    # This is what pymupdf4llm does internally — you do it yourself here
```

**Table Extraction (Best-in-Class):**

```python
with pdfplumber.open("report.pdf") as pdf:
    page = pdf.pages[0]

    # Auto-detect all tables
    tables = page.find_tables()
    for table in tables:
        df = table.to_pandas()  # or table.extract()

    # Fine-tuned settings for complex tables
    table = page.find_table({
        "vertical_strategy": "text",
        "horizontal_strategy": "lines",
        "snap_tolerance": 3,
        "join_tolerance": 3,
    })
```

**Strengths for Mnemosyne:**
- MIT license — no friction with our MIT core.
- Unmatched table extraction accuracy for financial reports, academic papers, forms.
- Full coordinate access enables precise provenance: "this claim came from page 3, lines 45–48."
- Visual debugging accelerates extractor development and troubleshooting.

**Weaknesses:**
- No automatic heading detection — you must implement the heuristic layer.
- No built-in markdown output; you assemble the structure yourself.
- No OCR support; fails on scanned documents.
- Slower than pymupdf for bulk text extraction (Python loop over characters vs. C engine).
- Multi-column reading order reconstruction is manual.

---

### 2.3 Unstructured

**What it is:** An open-source ETL framework for unstructured documents, not merely a PDF extractor. Partitions documents into typed elements (`Title`, `NarrativeText`, `Table`, `ListItem`, etc.) with ML-powered layout analysis.

**Key Capabilities:**

| Feature | Detail |
|---|---|
| **Element typing** | Returns semantically typed elements: `Title`, `Header`, `NarrativeText`, `Table`, `ListItem`, `PageBreak`, etc. |
| **Strategies** | `fast` (pdfminer + heuristics, seconds per doc), `hi_res` (Chipper/DETR layout model, GPU-optional), `ocr_only` |
| **Table extraction** | `strategy="hi_res"` + `skip_infer_table_types=False` populates `text_as_html` on Table elements |
| **Heading detection** | ML-based: `Title` vs `Header` vs `NarrativeText` classification |
| **OCR** | Built-in via Tesseract; `hi_res` handles scanned docs |
| **Chunking** | Element-aware chunking (`by_title`, `by_page`, semantic) for RAG pipelines |
| **Connectors** | 40+ sources: S3, Gmail, Jira, SharePoint, etc. |
| **License** | Apache-2.0 |

**Partition Example:**

```python
from unstructured.partition.pdf import partition_pdf

elements = partition_pdf(
    "paper.pdf",
    strategy="hi_res",
    skip_infer_table_types=False,
    max_partition=1500,
)

for el in elements:
    print(f"{el.category}: {el.text[:100]}")
    if el.category == "Table":
        print(el.metadata.text_as_html)  # HTML table representation
```

**Strengths for Mnemosyne:**
- Semantic element typing aligns perfectly with our compilation engine's need to distinguish headings, body, lists, tables.
- `text_as_html` for tables preserves structure better than markdown pipe tables for complex tables.
- Apache-2.0 license — fully compatible with MIT.
- Ecosystem: chunking, embedding, vector store connectors ready-made.
- `hi_res` strategy with layout ML handles complex magazine layouts better than rule-based approaches.

**Weaknesses:**
- Heavy dependencies: `detectron2`, `transformers`, `tesseract` — installation is brittle.
- `hi_res` is slow (seconds per page) and GPU-optional but recommended for accuracy.
- `fast` strategy loses table structure and heading accuracy — a false economy for knowledge extraction.
- Overkill if you only need PDF→Markdown; the ETL pipeline adds complexity.
- Heading classification (`Title` vs `Header`) sometimes mislabels — requires post-filtering.

---

## 3. Comparative Matrix

| Factor | PyMuPDF4LLM | pdfplumber | Unstructured (hi_res) |
|---|---|---|---|
| **Heading detection** | ⭐⭐⭐⭐⭐ Automatic, font-size hierarchy | ⭐⭐ Manual build required | ⭐⭐⭐⭐ ML-based, occasional mislabels |
| **Table extraction** | ⭐⭐⭐⭐ Good pipe tables | ⭐⭐⭐⭐⭐ Best explicit/implicit line detection | ⭐⭐⭐⭐ HTML output, needs `hi_res` |
| **Multi-column handling** | ⭐⭐⭐⭐⭐ Reading order reconstruction | ⭐⭐ Manual | ⭐⭐⭐⭐ Layout ML handles well |
| **OCR / scanned docs** | ⭐⭐⭐⭐⭐ Hybrid, auto-detect | ⭐ None | ⭐⭐⭐⭐ Built-in Tesseract |
| **Speed (per page)** | ~0.14s | ~0.3–1s | ~2–5s (hi_res) |
| **Markdown output** | ⭐⭐⭐⭐⭐ Native, clean | ⭐ None (build yourself) | ⭐⭐ Via element concatenation |
| **Provenance (coordinates)** | ⭐⭐⭐⭐ JSON mode | ⭐⭐⭐⭐⭐ Per-char coordinates | ⭐⭐⭐ Element-level bboxes |
| **Dependencies** | Moderate (MuPDF C lib) | Light (pure Python + pdfminer) | Heavy (PyTorch, Detectron2, Tesseract) |
| **License** | AGPL-3.0 ⚠️ | MIT ✅ | Apache-2.0 ✅ |
| **Best for Mnemosyne** | **Default path** | Table-heavy docs, custom logic | Complex layouts, semantic chunking |

---

## 4. Mnemosyne Integration Design

### 4.1 Recommended Strategy: Tiered Extraction

Not all PDFs are equal. Mnemosyne should route PDFs to the right extractor based on heuristics:

```
PDF Ingested
    │
    ▼
┌─────────────────┐
│ Quick Inspect   │  ← PyMuPDF: page count, has_text?, has_images?
│ (PyMuPDF)       │     table_density, scan_detected
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌────────┐  ┌─────────────┐  ┌─────────────┐
│ Simple │  │ Table-Heavy │  │ Complex/Scan│
│ Digital│  │ Financial/  │  │ Magazine/   │
│ Text   │  │ Academic    │  │ Scanned     │
└───┬────┘  └──────┬──────┘  └──────┬──────┘
    │              │                │
    ▼              ▼                ▼
┌────────┐  ┌─────────────┐  ┌─────────────┐
│PyMuPDF4│  │ pdfplumber  │  │ Unstructured│
│LLM     │  │ (tables) +  │  │ (hi_res)    │
│        │  │ PyMuPDF4LLM │  │             │
│        │  │ (headings)  │  │             │
└────────┘  └─────────────┘  └─────────────┘
```

### 4.2 Satellite CLI Contract

The Rust core spawns the Python satellite via subprocess:

```bash
python -m mnemosyne_py.extract pdf     --input "path/to/paper.pdf"     --output "/tmp/result.json"     --strategy auto     --include-images     --provenance full
```

**Output JSON schema (`RawDocument`):**

```json
{
  "source_file": "paper.pdf",
  "source_type": "pdf",
  "extractor": "pymupdf4llm",
  "extractor_version": "0.1.0",
  "pages": [
    {
      "page_number": 1,
      "text": "# Attention Is All You Need

**Ashish Vaswani**...",
      "headings": [
        {"level": 1, "text": "Attention Is All You Need", "bbox": [100, 50, 400, 80]}
      ],
      "tables": [
        {
          "markdown": "| Layer | Type | Hidden Size |
|---|---|---|
| ...",
          "bbox": [50, 200, 550, 400],
          "rows": 6,
          "cols": 4
        }
      ],
      "images": [
        {
          "path": "/tmp/extracted/paper-p1-i0.png",
          "bbox": [100, 300, 400, 600],
          "description": null
        }
      ],
      "provenance": {
        "chars_extracted": 1842,
        "ocr_applied": false,
        "font_sizes": [9.0, 10.0, 12.0, 18.0]
      }
    }
  ],
  "metadata": {
    "title": "Attention Is All You Need",
    "author": "Vaswani et al.",
    "page_count": 15,
    "has_text_layer": true,
    "scan_detected": false
  }
}
```

### 4.3 Provenance Mapping to `state.db`

The `pages` table's `provenance` JSON field stores:

```json
[
  {
    "source_file": "paper.pdf",
    "page_start": 1,
    "page_end": 15,
    "extractor": "pymupdf4llm",
    "extractor_version": "0.1.0",
    "extraction_strategy": "auto",
    "ocr_pages": [],
    "heading_count": 8,
    "table_count": 3,
    "image_count": 2
  }
]
```

---

## 5. Licensing & Compliance

| Library | License | Mnemosyne Impact |
|---|---|---|
| PyMuPDF | AGPL-3.0 | Subprocess isolation means no linking → no viral infection. But AGPL still requires source availability if we *distribute* the satellite. **Mitigation:** Use PyMuPDF Pro (commercial) for distributed builds; keep AGPL path for self-builders. |
| PyMuPDF4LLM | AGPL-3.0 | Same as above. |
| pdfplumber | MIT | Zero friction. |
| Unstructured | Apache-2.0 | Zero friction. |
| pdfminer.six | MIT | Zero friction. |

**Recommendation:** Default to `pdfplumber` + `pymupdf4llm` (AGPL subprocess) for maximum extraction quality. Provide a pure-MIT fallback path using only `pdfplumber` + `pypdf` for users who cannot accept AGPL in any form.

---

## 6. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| PyMuPDF AGPL contamination | Low | High | Subprocess isolation; commercial license option |
| Unstructured dependency hell | Medium | Medium | Pin versions; Docker container for satellite |
| Table extraction fails on borderless tables | Medium | Medium | Fallback to `pdfplumber` explicit line detection |
| OCR quality poor on low-res scans | Medium | Medium | Configurable OCR DPI; Tesseract language packs |
| Multi-column reading order scrambled | Low | Medium | `unstructured hi_res` fallback for magazine layouts |
| Python satellite startup latency | Low | Low | Warm pool of subprocesses; or long-running daemon |

---

## 7. Decision Log

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-27 | Python satellite for all PDF extraction | Rust ecosystem lacks semantic reconstruction depth |
| 2026-05-27 | PyMuPDF4LLM as default extractor | Best heading detection + markdown output + speed |
| 2026-05-27 | pdfplumber as table specialist | Best table extraction; MIT license; coordinate precision |
| 2026-05-27 | Unstructured as complex-layout fallback | Layout ML handles magazines/scans; Apache-2.0 |
| 2026-05-27 | Tiered extraction strategy | Not all PDFs need the same tool; optimize for common case |
| 2026-05-27 | JSON-over-stdout/stdout contract | Rust core ↔ Python satellite communication |

---

## 8. Open Questions

1. **Should we pre-extract images and run them through a vision model for figure captions?** This would enrich the `images[].description` field but adds latency and GPU cost.
2. **How do we handle PDFs with form fields (AcroForm)?** `pymupdf` can read form values; `pdfplumber` cannot. Do we flatten or preserve?
3. **Redaction / sensitive content:** Should the extraction satellite support PII detection before writing to `state.db`?
4. **Streaming extraction for very large PDFs (>1000 pages):** Current approach loads full JSON into memory. Consider chunked streaming.

---

## 9. References

- [PyMuPDF GitHub](https://github.com/pymupdf/pymupdf) — MuPDF C engine bindings
- [PyMuPDF4LLM GitHub](https://github.com/pymupdf/pymupdf4llm) — LLM-optimized extraction layer
- [PyMuPDF4LLM Documentation](https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/) — API reference
- [pdfplumber GitHub](https://github.com/jsvine/pdfplumber) — Spatial PDF analysis
- [Unstructured Documentation](https://docs.unstructured.io/) — ETL framework docs
- [A Comparative Study of PDF Parsing Tools](https://arxiv.org/html/2410.09871v1) — Academic benchmark (2024)
- [I Tested 7 Python PDF Extractors](https://onlyoneaman.medium.com/i-tested-7-python-pdf-extractors-so-you-dont-have-to-2025-edition-c88013922257) — Practical benchmark (2025)
