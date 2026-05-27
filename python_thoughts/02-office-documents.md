# 02 — Office Documents: DOCX, PPTX, XLSX

**Status:** Research Complete | **Owner:** Mnemosyne Python Satellite Layer
**Last Updated:** 2026-05-27

---

## Executive Summary

The Rust ecosystem for Office document parsing is structurally empty. While `office_oxide` (2026) claims 100x speedup over Python libraries for text extraction, it is a new entrant with unproven semantic reconstruction capabilities. The established, battle-tested path runs through Python: **`python-docx`** for Word documents, **`python-pptx`** for PowerPoint presentations, and **`openpyxl`** (or **`pandas`**) for Excel spreadsheets. These libraries have 10+ years of production use, handle the full complexity of the Office Open XML spec, and produce structured output that Mnemosyne's compilation engine can consume.

This document breaks down extraction quality, heading/structure detection, table handling, performance, dependencies, licensing, and integration fit for each format.

---

## 1. The Rust Landscape: Effectively Empty

| Crate / Tool | Maturity | DOCX | PPTX | XLSX | Heading Detection | Table Extraction | Verdict |
|---|---|---|---|---|---|---|---|
| `docx-rs` | Moderate | Read/Write | No | No | Manual style parsing | Basic cell iteration | Building block only |
| `calamine` | Mature | No | No | Read-only | N/A | Good (sheet->DataFrame) | XLSX only; no formatting |
| `office_oxide` | Emerging (2026) | Read | Read | Read | Unknown | Unknown | Speed claims; semantics untested |
| `msoffcrypto-tool` (Python) | Mature | Decrypt | Decrypt | Decrypt | N/A | N/A | Password-protected files only |

**The structural problem:** Office Open XML (OOXML) is a 6,000+ page specification. `python-docx`, `python-pptx`, and `openpyxl` are not thin wrappers — they are deep implementations that handle edge cases: nested tables, merged cells, style inheritance, theme fonts, content controls, comments, revision tracking, and more. Rust has no equivalent depth.

> **Mnemosyne Decision:** Python satellite for all Office document ingestion. No Rust-native Office extraction in Phase 1.

---

## 2. DOCX: `python-docx` + `mammoth`

### 2.1 `python-docx` — The Deep Parser

**What it is:** The canonical Python library for reading and writing Word documents. Provides object-model access to paragraphs, runs, tables, styles, sections, headers, footers, and the full OOXML tree.

**Key Capabilities:**

| Feature | Detail |
|---|---|
| **Heading detection** | Native: `paragraph.style.name` returns `'Heading 1'` through `'Heading 9'`, `'Title'`, `'Subtitle'`, `'TOC Heading'`. Style-based, not font-size heuristic. |
| **Paragraph structure** | Full access: `paragraph.text`, `paragraph.style`, `paragraph.alignment`, `paragraph.runs` (for bold/italic/underline/font changes within a paragraph) |
| **Table extraction** | `document.tables` -> `table.rows` -> `row.cells` -> `cell.paragraphs`. Handles merged cells via `gridSpan`/`vMerge` XML attributes. |
| **Lists** | Detected via `paragraph.style.name` (`'List Bullet'`, `'List Number'`, `'List Bullet 2'`, etc.) or `paragraph._p.getchildren()` for numPr analysis |
| **Images** | `document.inline_shapes` and `document.part.related_parts` for embedded images; `shape.image.blob` for extraction |
| **Headers/footers** | `section.header`, `section.footer` access |
| **Comments** | `document.part.element` XPath to comment ranges |
| **Track changes** | XML-level access via `paragraph._p` |
| **License** | MIT |

**Heading Detection in Detail:**

```python
from docx import Document

doc = Document('report.docx')

for para in doc.paragraphs:
    style = para.style.name
    if style.startswith('Heading'):
        level = int(style.split()[-1])  # 'Heading 3' -> 3
        print(f"{'#' * level} {para.text}")
    elif style == 'Title':
        print(f"# {para.text}")
    elif style.startswith('List'):
        prefix = '- ' if 'Bullet' in style else '1. '
        print(f'{prefix}{para.text}')
    else:
        print(para.text)
```

**Table Extraction with Merged Cell Handling:**

```python
from docx import Document

def iter_unique_cells(row):
    # Yield each physical cell once, skipping grid-span duplicates
    prior_tc = None
    for cell in row.cells:
        this_tc = cell._tc
        if this_tc is prior_tc:
            continue
        prior_tc = this_tc
        yield cell

def table_to_markdown(table):
    # Convert a python-docx Table to GitHub-flavored Markdown
    rows = []
    for row in table.rows:
        cells = list(iter_unique_cells(row))
        row_text = [' '.join(p.text for p in cell.paragraphs) for cell in cells]
        rows.append(row_text)
    
    if not rows:
        return ''
    
    md = '| ' + ' | '.join(rows[0]) + ' |\n'
    md += '|' + '|'.join('---' for _ in rows[0]) + '|\n'
    for row in rows[1:]:
        md += '| ' + ' | '.join(row) + ' |\n'
    return md
```

**Strengths for Mnemosyne:**
- **Style-native heading detection:** Uses Word's built-in style system (`Heading 1`-`9`), not fragile font-size heuristics. This is more reliable than PDF heading detection.
- **Full document structure:** Sections, headers, footers, footnotes, endnotes — all accessible for provenance.
- **MIT license** — zero friction.
- **Mature ecosystem:** 10+ years, 50M+ downloads, maintained by Steve Canny (Microsoft alumnus).

**Weaknesses:**
- **Merged cell duplication:** `row.cells` returns grid cells, not physical cells. Merged cells appear multiple times. Requires `iter_unique_cells()` workaround.
- **No built-in markdown output:** You assemble structure yourself (but this is also a strength — full control).
- **Style loss edge case:** Some documents have 'named styles lost' where `Heading 1` paragraphs report as `Normal`. Requires fallback to font-size heuristics.
- **Nested tables:** Supported but complex to flatten into markdown.

### 2.2 `mammoth` — The Semantic Converter

**What it is:** A semantic DOCX->HTML/Markdown converter. Focuses on *meaning* (heading, list, table) rather than *appearance* (fonts, colors, exact spacing).

**Key Capabilities:**

| Feature | Detail |
|---|---|
| **Conversion** | `convert_to_html()`, `convert_to_markdown()`, `extract_raw_text()` |
| **Style mapping** | Custom style maps: `p.Heading1 => h1`, `p.MyCustomHeading => h2` |
| **Image handling** | Configurable image converter (embed base64, save to file, etc.) |
| **Table support** | HTML `<table>` output; `--md_table` flag for pipe tables (header line fixed to `#`) |
| **License** | BSD-2-Clause |

**Usage:**

```python
import mammoth

with open('document.docx', 'rb') as f:
    result = mammoth.convert_to_markdown(f)
    md = result.value
    messages = result.messages  # warnings about unsupported features
```

**Strengths for Mnemosyne:**
- One-line DOCX->Markdown conversion.
- Semantic focus aligns with knowledge extraction (ignores visual noise).
- BSD-2-Clause license — fully compatible.

**Weaknesses:**
- **Markdown support is deprecated** — maintainers recommend HTML->Markdown via separate library.
- Limited control over table output (header row always `#` in md_table mode).
- No access to raw OOXML for provenance metadata.
- Less granular than `python-docx` for custom extraction logic.

### 2.3 DOCX: Recommended Strategy

**Primary:** `python-docx` for full control, provenance, and custom logic.
**Fallback:** `mammoth` for quick-and-dirty DOCX->Markdown when structure is simple and speed matters.

---

## 3. PPTX: `python-pptx`

### 3.1 `python-pptx` — The Deep Parser

**What it is:** The canonical Python library for reading and writing PowerPoint presentations. Provides object-model access to slides, shapes, text frames, tables, images, notes, and masters.

**Key Capabilities:**

| Feature | Detail |
|---|---|
| **Slide iteration** | `prs.slides` — each slide has `slide.shapes` |
| **Text extraction** | `shape.has_text_frame` -> `shape.text_frame.text` ; `shape.text` convenience property |
| **Heading detection** | **No native heading styles.** Must infer from: font size, shape position (title placeholder at top), or `shape.placeholder_format.type` (`TITLE` = 1, `BODY` = 2) |
| **Tables** | `shape.has_table` -> `shape.table` -> `table.rows` -> `row.cells` -> `cell.text_frame.paragraphs` |
| **Images** | `shape.shape_type == MSO_SHAPE_TYPE.PICTURE` -> `shape.image.blob` |
| **Notes** | `slide.has_notes_slide` -> `notes_slide.notes_text_frame.text` |
| **Slide masters/layouts** | `slide.slide_layout`, `slide.slide_master` — background images and inherited shapes live here |
| **License** | MIT |

**Text Extraction with Structure Inference:**

```python
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

prs = Presentation('deck.pptx')

for slide_num, slide in enumerate(prs.slides, 1):
    print(f'\n--- Slide {slide_num} ---')
    
    for shape in slide.shapes:
        # Title detection via placeholder type
        is_title = False
        if shape.is_placeholder:
            ph_type = shape.placeholder_format.type
            is_title = ph_type == 1  # TITLE
        
        if shape.has_text_frame:
            text = shape.text_frame.text.strip()
            if text:
                if is_title:
                    print(f'# {text}')
                else:
                    print(text)
        
        # Extract images
        if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
            image = shape.image
            with open(f'slide{slide_num}_img.{image.ext}', 'wb') as f:
                f.write(image.blob)
        
        # Extract tables
        if shape.has_table:
            table = shape.table
            for row in table.rows:
                row_text = [cell.text for cell in row.cells]
                print('| ' + ' | '.join(row_text) + ' |')
    
    # Notes
    if slide.has_notes_slide:
        notes = slide.notes_slide.notes_text_frame.text
        if notes.strip():
            print(f'\n> **Notes:** {notes}')
```

**Strengths for Mnemosyne:**
- **MIT license** — zero friction.
- **Notes extraction** — presenter notes are often the richest source of context in a deck.
- **Slide-level provenance** — each slide is a natural chunk for the `pages` table.
- **Image extraction** — diagrams, charts, screenshots can be saved and described.

**Weaknesses:**
- **No heading hierarchy** — PowerPoint has no semantic heading model. Title/body distinction is positional, not structural.
- **Background images** — images on slide masters/layouts don't appear in `slide.shapes`; must iterate masters separately.
- **SmartArt / grouped shapes** — complex nested shapes require recursive traversal.
- **No built-in markdown output** — assemble structure yourself.

### 3.2 PPTX: Recommended Strategy

**Primary:** `python-pptx` for all extraction. No viable alternative in Python or Rust.
**Heuristic layer:** Title = largest font or `placeholder_format.type == TITLE`. Body = everything else. Notes = always included.

---

## 4. XLSX: `openpyxl` vs `pandas`

### 4.1 `openpyxl` — The Deep Parser

**What it is:** The canonical Python library for reading and writing Excel 2010+ files (xlsx/xlsm/xltx/xltm). Provides cell-level access to values, formulas, formatting, comments, merged cells, charts, and named ranges.

**Key Capabilities:**

| Feature | Detail |
|---|---|
| **Cell values** | `ws['A1'].value` — returns raw value, formula result, or formula string |
| **Formulas** | `data_only=True` (read calculated values) vs `data_only=False` (read formula strings) |
| **Merged cells** | `ws.merged_cells.ranges` — returns `MergeRange` objects |
| **Tables** | `ws.tables` — Excel 'structured tables' (ListObjects) with headers and auto-filters |
| **Named ranges** | `wb.defined_names` — access named cells/ranges |
| **Comments** | `cell.comment.text` |
| **Hyperlinks** | `cell.hyperlink.target` |
| **Styles** | `cell.font`, `cell.fill`, `cell.border`, `cell.number_format` |
| **Read-only mode** | `load_workbook(filename, read_only=True)` — memory-efficient for large files |
| **License** | MIT |

**Reading with Merged Cell Expansion:**

```python
from openpyxl import load_workbook

def expand_merged_cells(ws):
    # Fill merged cell ranges with the top-left value
    for merged_range in ws.merged_cells.ranges:
        top_left = ws.cell(row=merged_range.min_row, column=merged_range.min_col)
        value = top_left.value
        for row in ws.iter_rows(
            min_row=merged_range.min_row, max_row=merged_range.max_row,
            min_col=merged_range.min_col, max_col=merged_range.max_col
        ):
            for cell in row:
                cell.value = value

wb = load_workbook('data.xlsx', data_only=True)
ws = wb.active

expand_merged_cells(ws)

# Convert to markdown table
rows = []
for row in ws.iter_rows(values_only=True):
    rows.append([str(cell) if cell is not None else '' for cell in row])

if rows:
    md = '| ' + ' | '.join(rows[0]) + ' |\n'
    md += '|' + '|'.join('---' for _ in rows[0]) + '|\n'
    for row in rows[1:]:
        md += '| ' + ' | '.join(row) + ' |\n'
    print(md)
```

**Strengths for Mnemosyne:**
- **MIT license** — zero friction.
- **Formula vs value choice** — `data_only=True` gives you the computed values (what you usually want for knowledge extraction); `data_only=False` preserves formulas for audit.
- **Merged cell handling** — explicit API for detecting and expanding merged ranges.
- **Read-only mode** — memory-efficient for large spreadsheets.
- **Sheet-level provenance** — each sheet becomes a page or section in the wiki.

**Weaknesses:**
- **Slow for very large files** — pure Python, not C-backed. 1000x200k cell files take ~30 min.
- **No heading detection** — Excel has no heading styles. Must infer from: first row = headers, bold formatting, or named ranges.
- **Charts as images** — `openpyxl` can detect chart presence but not extract them as images (need `xlsx2img` or screenshot).

### 4.2 `pandas` — The DataFrame Path

**What it is:** High-level data analysis library. `pd.read_excel()` wraps `openpyxl` (or `calamine`/`xlsxwriter`) and returns a DataFrame.

**Key Capabilities:**

| Feature | Detail |
|---|---|
| **One-liner** | `df = pd.read_excel('data.xlsx', sheet_name=None)` — returns dict of DataFrames |
| **Header inference** | `header=0` (default) treats first row as column names |
| **Type inference** | Auto-detects numeric, string, datetime, boolean |
| **Large files** | Uses `openpyxl` under the hood; same performance ceiling |
| **License** | BSD-3-Clause |

**Usage:**

```python
import pandas as pd

# All sheets
sheets = pd.read_excel('data.xlsx', sheet_name=None, engine='openpyxl')

for sheet_name, df in sheets.items():
    md = df.to_markdown(index=False)
    print(f'\n## Sheet: {sheet_name}\n\n{md}')
```

**Strengths for Mnemosyne:**
- **One-line sheet->Markdown** via `df.to_markdown()`.
- **Type-aware** — preserves numeric precision, dates, booleans.
- **Multi-sheet handling** — `sheet_name=None` loads all sheets.

**Weaknesses:**
- **Less control** — `pandas` abstracts away cell-level details (formulas, comments, hyperlinks, merged cells).
- **Same performance ceiling** — delegates to `openpyxl` for .xlsx files.
- **Header inference is heuristic** — can fail on multi-header rows or data starting below row 1.

### 4.3 XLSX: Recommended Strategy

**Primary:** `openpyxl` for full control, provenance, and edge cases (merged cells, formulas, comments).
**Convenience:** `pandas` for quick sheet->Markdown conversion when structure is simple and speed matters.
**Large files:** `openpyxl` read-only mode, or convert to CSV first if feasible.

---

## 5. Comparative Matrix

| Factor | `python-docx` | `python-pptx` | `openpyxl` | `pandas` (XLSX) |
|---|---|---|---|---|
| **Heading detection** | ★★★★★ Style-native (`Heading 1`-`9`) | ★★ Positional heuristic | ★ None (heuristic: first row) | ★★ `header=0` heuristic |
| **Table extraction** | ★★★★ Good (merged cell workaround) | ★★★★ Good (shape tables) | ★★★★★ Excellent (merged cells, formulas) | ★★★★ Good (DataFrame->Markdown) |
| **List detection** | ★★★★ Style-native (`List Bullet`) | ★ None | N/A | N/A |
| **Image extraction** | ★★★★ Inline shapes + related parts | ★★★★★ Full image blob access | N/A | N/A |
| **Speed** | Fast (pure Python, small files) | Fast | Moderate (pure Python) | Moderate (delegates to openpyxl) |
| **Markdown output** | ★ Build yourself | ★ Build yourself | ★ Build yourself | ★★★★ `to_markdown()` |
| **Provenance** | ★★★★★ Full OOXML access | ★★★★ Slide/shape/placeholder | ★★★★ Cell-level coordinates | ★★ DataFrame-level |
| **License** | MIT ✅ | MIT ✅ | MIT ✅ | BSD-3-Clause ✅ |
| **Dependencies** | Light | Light | Light | Moderate (numpy, etc.) |

---

## 6. Mnemosyne Integration Design

### 6.1 Unified Satellite CLI Contract

```bash
# DOCX
python -m mnemosyne_py.extract docx \
    --input 'report.docx' \
    --output '/tmp/result.json' \
    --include-images \
    --provenance full

# PPTX
python -m mnemosyne_py.extract pptx \
    --input 'presentation.pptx' \
    --output '/tmp/result.json' \
    --include-images \
    --include-notes \
    --provenance full

# XLSX
python -m mnemosyne_py.extract xlsx \
    --input 'data.xlsx' \
    --output '/tmp/result.json' \
    --expand-merged \
    --data-only \
    --provenance full
```

### 6.2 Output JSON Schema (`RawDocument`)

```json
{
  "source_file": "report.docx",
  "source_type": "docx",
  "extractor": "python-docx",
  "extractor_version": "1.2.0",
  "sections": [
    {
      "type": "heading",
      "level": 1,
      "text": "Executive Summary",
      "style": "Heading 1",
      "paragraph_index": 3
    },
    {
      "type": "paragraph",
      "text": "This report analyzes...",
      "style": "Normal",
      "runs": [
        {"text": "This report ", "bold": false, "italic": false},
        {"text": "analyzes", "bold": true, "italic": false}
      ]
    },
    {
      "type": "table",
      "markdown": "| Metric | Value |\n|---|---|\n| Revenue | $1.2M |",
      "rows": 5,
      "cols": 2,
      "has_merged_cells": true
    },
    {
      "type": "image",
      "path": "/tmp/extracted/report-img0.png",
      "description": null,
      "paragraph_index": 12
    }
  ],
  "metadata": {
    "title": "Q3 Financial Report",
    "author": "Jane Smith",
    "created": "2026-03-15T09:00:00Z",
    "modified": "2026-03-20T14:30:00Z",
    "page_count": null,
    "word_count": 4520,
    "has_tables": true,
    "has_images": true
  },
  "provenance": {
    "paragraph_count": 142,
    "table_count": 3,
    "image_count": 5,
    "heading_count": 8,
    "style_map": {
      "Heading 1": 3,
      "Heading 2": 5,
      "List Bullet": 12
    }
  }
}
```

### 6.3 PPTX-Specific Schema

```json
{
  "source_type": "pptx",
  "slides": [
    {
      "slide_number": 1,
      "layout": "Title Slide",
      "title": "Project Roadmap",
      "body": "Overview of Q3 deliverables...",
      "tables": [...],
      "images": [...],
      "notes": "Presenter: emphasize timeline risks",
      "shapes_count": 7
    }
  ]
}
```

### 6.4 XLSX-Specific Schema

```json
{
  "source_type": "xlsx",
  "sheets": [
    {
      "name": "Revenue",
      "row_count": 150,
      "col_count": 8,
      "has_headers": true,
      "header_row": ["Quarter", "Region", "Revenue", "Growth"],
      "markdown": "| Quarter | Region | Revenue | Growth |\n|---|---|---|---|\n| Q1 | NA | 1.2 | 5% |",
      "tables": [
        {
          "name": "Table1",
          "range": "A1:D50",
          "has_headers": true
        }
      ],
      "named_ranges": ["RevenueTotal", "GrowthRate"],
      "merged_cells": ["A1:B1", "C10:D10"]
    }
  ]
}
```

---

## 7. Provenance Mapping to `state.db`

The `pages` table's `provenance` JSON field stores:

```json
[
  {
    "source_file": "report.docx",
    "extractor": "python-docx",
    "extractor_version": "1.2.0",
    "paragraph_count": 142,
    "heading_count": 8,
    "table_count": 3,
    "image_count": 5,
    "style_distribution": {
      "Heading 1": 3,
      "Heading 2": 5,
      "Normal": 124,
      "List Bullet": 12
    },
    "merged_cell_count": 4,
    "formula_count": 0
  }
]
```

---

## 8. Licensing & Compliance

| Library | License | Mnemosyne Impact |
|---|---|---|
| `python-docx` | MIT | Zero friction |
| `python-pptx` | MIT | Zero friction |
| `openpyxl` | MIT | Zero friction |
| `pandas` | BSD-3-Clause | Zero friction |
| `mammoth` | BSD-2-Clause | Zero friction |
| `lxml` (dep) | BSD-3-Clause | Zero friction |
| `Pillow` (dep) | HPND | Zero friction |

**All Office extraction libraries are permissively licensed.** No AGPL concerns like with PyMuPDF.

---

## 9. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `python-docx` style loss (named styles missing) | Medium | Medium | Fallback to font-size heuristics; warn in extraction log |
| `python-pptx` title detection fails on non-standard layouts | Medium | Medium | Multi-criteria: placeholder type + font size + position |
| `openpyxl` slow on very large files (>100k rows) | Medium | Medium | Read-only mode; sheet-by-sheet streaming; CSV conversion fallback |
| Merged cell data loss in tables | Low | High | Always expand merged cells before markdown conversion |
| Password-protected files | Low | Medium | `msoffcrypto-tool` for decryption; fail gracefully with clear error |
| Embedded macros (XLSM) | Low | Low | Extract data only; do not execute macros |
| Python satellite startup latency | Low | Low | Warm pool or long-running daemon |

---

## 10. Decision Log

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-27 | Python satellite for all Office document extraction | Rust ecosystem lacks mature OOXML parsers |
| 2026-05-27 | `python-docx` as DOCX primary | Style-native heading detection; full OOXML access; MIT license |
| 2026-05-27 | `mammoth` as DOCX quick fallback | One-line semantic conversion; BSD-2-Clause |
| 2026-05-27 | `python-pptx` as PPTX only viable path | No Rust alternative; MIT license; notes extraction critical |
| 2026-05-27 | `openpyxl` as XLSX primary | Full cell-level control; merged cell handling; formula/value choice |
| 2026-05-27 | `pandas` as XLSX convenience layer | One-line DataFrame->Markdown; good for simple sheets |
| 2026-05-27 | Unified `RawDocument` JSON schema across all three formats | Rust core consumes one schema regardless of source format |

---

## 11. Open Questions

1. **Should we extract revision/track-changes from DOCX?** Word documents with tracked changes contain multiple versions of text. Do we extract 'final' only, or annotate with change metadata?
2. **PowerPoint animation sequences:** Should we extract step-by-step animation text (e.g., 'Click 1: Point A', 'Click 2: Point B') or flatten to single slide?
3. **Excel chart extraction:** `openpyxl` detects charts but cannot render them. Do we use `xlsx2img` or screenshot for chart images?
4. **Formula audit trail:** For XLSX, do we store both `data_only` values and formula strings in provenance for audit purposes?
5. **Legacy formats (DOC, XLS, PPT):** These require `antiword`, `catdoc`, `xlrd`, or LibreOffice headless conversion. Out of scope for Phase 1?

---

## 12. References

- [python-docx Documentation](https://python-docx.readthedocs.io/) — Official docs
- [python-docx GitHub](https://github.com/python-openxml/python-docx) — Source code
- [python-pptx Documentation](https://python-pptx.readthedocs.io/) — Official docs
- [python-pptx GitHub](https://github.com/scanny/python-pptx) — Source code
- [openpyxl Documentation](https://openpyxl.readthedocs.io/) — Official docs
- [openpyxl GitHub](https://github.com/chronossc/openpyxl) — Source code
- [mammoth GitHub](https://github.com/mwilliamson/python-mammoth) — DOCX->HTML/Markdown converter
- [docx2md PyPI](https://pypi.org/project/docx2md/) — Alternative DOCX->Markdown tool
- [Office Oxide (Rust)](https://lib.rs/crates/office_oxide) — Emerging Rust Office library (2026)