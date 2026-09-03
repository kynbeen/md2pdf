"""
High-fidelity Markdown to PDF renderer (Chromium/Playwright).

Features:
- Typora-inspired refined styling with Pretendard & Open Sans typography
- Running header (document title) and footer (page numbers)
- Dynamic figure layout engine that adjusts images & captions to prevent awkward page breaks
- Relative asset path support via HTML <base> tag
"""
from __future__ import annotations
import argparse
import re
import sys
import tempfile
from pathlib import Path
from typing import Callable

import markdown as md

from md2pdf.preprocess import extract_title, preprocess_markdown

# Extensions: preserve single linebreaks (nl2br), tables/fences (extra), sane list handling
MD_EXTENSIONS = ["extra", "sane_lists", "toc", "nl2br"]

ASSETS = Path(__file__).resolve().parent / "assets"
FONTS = ASSETS / "fonts"
THEMES = ASSETS / "themes"
THEME_CHOICES = ("custom", "github")

# A4 (297mm) - top margin (18mm) - bottom margin (16mm) = 263mm content height
PAGE_CONTENT_MM = 263.0
CSS_PX_PER_MM = 96.0 / 25.4
PAGE_CONTENT_PX = PAGE_CONTENT_MM * CSS_PX_PER_MM
CURRENT_PAGE_MIN_REMAINING_RATIO = 0.40
PAGE_MARGIN_TOP_PT = 18.0 * 72.0 / 25.4
PAGE_MARGIN_BOTTOM_PT = 16.0 * 72.0 / 25.4
MAX_FIGURE_LAYOUT_PASSES = 12
CURRENT_PAGE_FIT_GUARD_PX = 24.0
_FIGURE_ANCHOR_PREFIX = "SFANCHOR"
_FIGURE_CONTENT_PREFIX = "SFFIGURE"

_SUMMARY_IMAGE_CSS = """
figure.summary-figure {
  position: relative;
  margin: 7px 0 11px;
  text-align: center;
  break-inside: avoid;
  page-break-inside: avoid;
  overflow: hidden;
}
figure.summary-figure img {
  display: block;
  width: auto;
  height: auto;
  max-width: 100%;
  margin: 0 auto;
  background: #fff;
}
figure.summary-figure figcaption {
  margin-top: 5px;
  color: #5f6368;
  font-size: 9.2pt;
  line-height: 1.45;
}
.summary-layout-anchor {
  position: absolute;
  right: 0;
  bottom: 0;
  margin: 0;
  padding: 0;
  overflow: visible;
  white-space: nowrap;
  color: #fff;
  font: 1px/1px monospace;
}
.summary-figure-marker {
  position: absolute;
  right: 0;
  top: 0;
  color: #fff;
  font: 1px/1px monospace;
  white-space: nowrap;
}
"""

_GITHUB_OVERRIDES = """
body { font-family:'Open Sans','Pretendard','Malgun Gothic',sans-serif; }
h1, h2 { border-bottom: none; padding-bottom: 0; }
hr { display: none; }
table { border-collapse: collapse; table-layout: auto; }
thead { display: table-header-group; }
tbody { break-inside: auto; }
tr, th, td { break-inside: avoid; }
td, th { vertical-align: middle; }
pre { background:#f8f8f8; border:1px solid #e7eaed; border-radius:3px;
      padding:10px 12px; white-space:pre; overflow-x:auto;
      font-family:'D2Coding','Consolas',monospace; font-size:9.2pt; break-inside:avoid; }
pre code { background:none; border:none; padding:0; font-size:inherit; }
"""


def _font_face_css() -> str:
    reg = (FONTS / "Pretendard-Regular.ttf").resolve().as_uri()
    bold = (FONTS / "Pretendard-Bold.ttf").resolve().as_uri()
    return (
        f"@font-face {{ font-family:'Pretendard'; font-weight:400; src:url('{reg}'); }}\n"
        f"@font-face {{ font-family:'Pretendard'; font-weight:700; src:url('{bold}'); }}\n"
    )


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _abs_github_font_urls(css: str) -> str:
    font_dir = (THEMES / "github").resolve().as_uri()
    return re.sub(
        r"url\(\s*['\"]?\./github/([^'\")]+)['\"]?\s*\)",
        lambda m: f"url('{font_dir}/{m.group(1)}')",
        css,
    )


def _open_sans_face_css() -> str:
    css_file = THEMES / "github.css"
    if not css_file.exists():
        return ""
    css = css_file.read_text(encoding="utf-8")
    faces = re.findall(r"@font-face\s*\{[^}]*\}", css, re.S)
    return _abs_github_font_urls("\n".join(faces))


def _github_css() -> str:
    css_file = THEMES / "github.css"
    if not css_file.exists():
        return ""
    return _abs_github_font_urls(css_file.read_text(encoding="utf-8"))


def _theme_css(theme: str) -> str:
    if theme == "github":
        return _font_face_css() + "\n" + _github_css() + "\n" + _GITHUB_OVERRIDES
    typora_css = (ASSETS / "typora.css").read_text(encoding="utf-8")
    return _font_face_css() + "\n" + _open_sans_face_css() + "\n" + typora_css


_IMAGE_PARAGRAPH_RE = re.compile(
    r"<p>\s*(<img\b[^>]*>)\s*</p>"
    r"(?:\s*<p>\s*<em>((?:(?!</?p\b).)*?)</em>\s*</p>)?",
    re.S | re.I,
)


def _wrap_summary_images(body: str) -> str:
    """Group markdown images and subsequent italicized captions into a single figure unit."""
    index = 0

    def repl(match: re.Match) -> str:
        nonlocal index
        index += 1
        image, caption = match.group(1), match.group(2)
        caption_html = f"<figcaption><em>{caption}</em></figcaption>" if caption else ""
        anchor = f"{_FIGURE_ANCHOR_PREFIX}{index:04d}"
        marker = f"{_FIGURE_CONTENT_PREFIX}{index:04d}"
        return (
            f'<span class="summary-layout-anchor" data-summary-index="{index}">{anchor}</span>'
            f'<figure class="summary-figure" data-summary-index="{index}">'
            f'<span class="summary-figure-marker">{marker}</span>'
            f"{image}{caption_html}</figure>"
        )

    return _IMAGE_PARAGRAPH_RE.sub(repl, body)


_APPLY_FIGURE_LAYOUT_JS = """
({pageHeight, layouts}) => {
  const figures = [...document.querySelectorAll('figure.summary-figure')];
  for (const figure of figures) {
    const image = figure.querySelector('img');
    if (!image) continue;
    const index = Number(figure.dataset.summaryIndex);
    const layout = layouts[String(index)] || {
      placement: 'auto', targetHeight: pageHeight, remainingRatio: 1, page: 0
    };
    if (layout.placement === 'next') {
      figure.style.breakBefore = 'page';
      figure.style.pageBreakBefore = 'always';
    } else {
      figure.style.breakBefore = 'auto';
      figure.style.pageBreakBefore = 'auto';
    }

    const target = Math.max(0.01, Number(layout.targetHeight) || pageHeight);
    const style = getComputedStyle(figure);
    const margin = parseFloat(style.marginTop || '0') + parseFloat(style.marginBottom || '0');
    const caption = figure.querySelector('figcaption');
    if (caption) {
      caption.style.fontSize = '';
      caption.style.lineHeight = '';
      caption.style.overflowWrap = 'anywhere';
      let fontSize = parseFloat(getComputedStyle(caption).fontSize || '12');
      for (let i = 0; i < 64 && margin + caption.getBoundingClientRect().height + 9 > target; i++) {
        fontSize *= 0.8;
        caption.style.fontSize = `${fontSize}px`;
        caption.style.lineHeight = '1.15';
      }
    }
    const captionHeight = caption ? caption.getBoundingClientRect().height : 0;
    const maxImageHeight = Math.max(0.01, target - margin - captionHeight - 8);
    image.style.maxHeight = `${maxImageHeight}px`;
    figure.style.breakInside = 'avoid';
    figure.style.pageBreakInside = 'avoid';
    figure.dataset.summaryPlacement = layout.placement;
    figure.dataset.summaryRemainingRatio = Number(layout.remainingRatio || 0).toFixed(4);
    figure.dataset.summaryMaxImageHeight = maxImageHeight.toFixed(2);
    figure.dataset.summaryMarkerPage = String(layout.page || 0);
  }
  return figures.map(figure => ({
    index: Number(figure.dataset.summaryIndex),
    placement: figure.dataset.summaryPlacement,
    remainingRatio: Number(figure.dataset.summaryRemainingRatio),
    height: figure.getBoundingClientRect().height,
    maxImageHeight: Number(figure.dataset.summaryMaxImageHeight),
    markerPage: Number(figure.dataset.summaryMarkerPage),
  }));
}
"""

_PREPARE_FIGURE_ANCHORS_JS = """
() => {
  const anchors = [...document.querySelectorAll('.summary-layout-anchor')];
  for (const anchor of anchors) {
    if (anchor.dataset.summaryPrepared === 'yes') continue;
    const previous = anchor.previousElementSibling;
    if (!previous) {
      anchor.dataset.summaryPrepared = 'yes';
      continue;
    }
    const walker = document.createTreeWalker(previous, NodeFilter.SHOW_TEXT);
    let node = null;
    let lastText = null;
    while ((node = walker.nextNode())) {
      const parent = node.parentElement;
      if (node.nodeValue.trim() && parent && !parent.matches('.summary-figure-marker, .summary-layout-anchor')) {
        lastText = node;
      }
    }
    if (lastText) {
      Object.assign(anchor.style, {
        position: 'static', display: 'inline-block', width: 'auto', height: '1px',
        color: '#fff', font: '1px/1px monospace', whiteSpace: 'nowrap', overflow: 'visible'
      });
      lastText.parentNode.insertBefore(anchor, lastText.nextSibling);
    } else {
      if (getComputedStyle(previous).position === 'static') {
        previous.style.position = 'relative';
      }
      Object.assign(anchor.style, {
        position: 'absolute', right: '0', bottom: '0', width: 'auto', height: 'auto',
        color: '#fff', font: '1px/1px monospace', whiteSpace: 'nowrap'
      });
      previous.appendChild(anchor);
    }
    anchor.dataset.summaryPrepared = 'yes';
  }
}
"""

_USE_LAYOUT_PLACEHOLDERS_JS = """
async () => {
  const images = [...document.querySelectorAll('figure.summary-figure img')];
  if (window.__summaryOriginalImages) return window.__summaryOriginalImages.length;
  window.__summaryOriginalImages = images.map(image => ({
    image,
    src: image.getAttribute('src'),
    srcset: image.getAttribute('srcset'),
    width: Math.max(1, image.naturalWidth || image.width || 1),
    height: Math.max(1, image.naturalHeight || image.height || 1),
  }));
  const waits = window.__summaryOriginalImages.map(record => {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${record.width}" height="${record.height}" viewBox="0 0 ${record.width} ${record.height}"><rect width="100%" height="100%" fill="white"/></svg>`;
    record.image.removeAttribute('srcset');
    record.image.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
    if (record.image.complete && record.image.naturalWidth > 0) return Promise.resolve();
    return new Promise((resolve, reject) => {
      record.image.addEventListener('load', resolve, {once:true});
      record.image.addEventListener('error', () => reject(new Error('layout placeholder load failed')), {once:true});
    });
  });
  await Promise.all(waits);
  return window.__summaryOriginalImages.length;
}
"""

_RESTORE_LAYOUT_IMAGES_JS = """
async () => {
  const records = window.__summaryOriginalImages || [];
  const waits = records.map(record => {
    if (record.srcset === null) record.image.removeAttribute('srcset');
    else record.image.setAttribute('srcset', record.srcset);
    if (record.src === null) record.image.removeAttribute('src');
    else record.image.setAttribute('src', record.src);
    if (record.image.complete && record.image.naturalWidth > 0) return Promise.resolve();
    return new Promise((resolve, reject) => {
      record.image.addEventListener('load', resolve, {once:true});
      record.image.addEventListener('error', () => reject(new Error('original image restore failed')), {once:true});
    });
  });
  await Promise.all(waits);
  delete window.__summaryOriginalImages;
  return records.length;
}
"""


def _read_figure_markers(draft_pdf: Path) -> tuple[dict[int, dict], dict[int, int]]:
    """Inspect draft PDF to locate text anchors and figure marker page positions."""
    try:
        import pymupdf
    except ImportError:
        raise ImportError(
            "pymupdf is required for image layout measurement. "
            "Install it via `pip install pymupdf`."
        )

    anchors: dict[int, dict] = {}
    figures: dict[int, int] = {}
    with pymupdf.open(draft_pdf) as doc:
        for page_no, pdf_page in enumerate(doc, start=1):
            content_height = pdf_page.rect.height - PAGE_MARGIN_TOP_PT - PAGE_MARGIN_BOTTOM_PT
            content_bottom = pdf_page.rect.height - PAGE_MARGIN_BOTTOM_PT
            for word in pdf_page.get_text("words"):
                token = word[4]
                anchor_match = re.search(re.escape(_FIGURE_ANCHOR_PREFIX) + r"(\d{4})", token)
                figure_match = re.search(re.escape(_FIGURE_CONTENT_PREFIX) + r"(\d{4})", token)
                if anchor_match:
                    index = int(anchor_match.group(1))
                    remaining_pt = max(0.0, min(content_height, content_bottom - word[3]))
                    anchors[index] = {
                        "page": page_no,
                        "remainingRatio": remaining_pt / content_height if content_height else 0.0,
                        "remainingHeight": remaining_pt * 96.0 / 72.0,
                    }
                elif figure_match:
                    index = int(figure_match.group(1))
                    figures[index] = page_no
    return anchors, figures


def _fit_summary_figures(page, draft_pdf: Path, doc_title: str, log: Callable = lambda *_: None) -> list[dict]:
    """Measure draft PDF iteratively to adjust figures according to the 40% rule."""
    figure_count = page.locator("figure.summary-figure").count()
    wrapped_image_count = page.locator("figure.summary-figure img").count()
    total_image_count = page.locator("body img").count()
    if not figure_count and not total_image_count:
        return []
    if not (figure_count == wrapped_image_count == total_image_count):
        raise ValueError(
            f"PDF figure mismatch: figure={figure_count}, inner image={wrapped_image_count}, total={total_image_count}"
        )
    count = figure_count
    page.wait_for_function(
        "[...document.images].every(img => img.complete && img.naturalWidth > 0)",
        timeout=15_000,
    )
    page.evaluate(_PREPARE_FIGURE_ANCHORS_JS)
    page.evaluate(_USE_LAYOUT_PLACEHOLDERS_JS)
    log(f"[md2pdf] Measuring layout for {count} figure(s)...")
    try:
        layouts: dict[str, dict] = {}
        page.evaluate(_APPLY_FIGURE_LAYOUT_JS, {"pageHeight": PAGE_CONTENT_PX, "layouts": layouts})

        previous_signature = None
        applied_layouts: dict[str, dict] = {}
        fit_adjustments: dict[int, float] = {}
        result: list[dict] = []
        for pass_number in range(1, MAX_FIGURE_LAYOUT_PASSES + 1):
            _emit_pdf(page, draft_pdf, doc_title)
            anchors, figure_pages = _read_figure_markers(draft_pdf)
            expected = set(range(1, count + 1))
            missing_anchors = sorted(expected - set(anchors))
            missing_figures = sorted(expected - set(figure_pages))
            if missing_anchors or missing_figures:
                raise ValueError(
                    f"Figure markers not found in draft PDF: text={missing_anchors}, figures={missing_figures}"
                )

            for index, anchor in anchors.items():
                previous = applied_layouts.get(str(index))
                if previous and previous["placement"] == "current" and figure_pages[index] != anchor["page"]:
                    fit_adjustments[index] = fit_adjustments.get(index, 0.0) + max(
                        16.0, anchor["remainingHeight"] * 0.03
                    )

            layouts = {}
            for index, anchor in anchors.items():
                use_current = anchor["remainingRatio"] >= CURRENT_PAGE_MIN_REMAINING_RATIO
                layouts[str(index)] = {
                    "placement": "current" if use_current else "next",
                    "targetHeight": (
                        max(
                            0.01,
                            anchor["remainingHeight"] - CURRENT_PAGE_FIT_GUARD_PX - fit_adjustments.get(index, 0.0),
                        )
                        if use_current
                        else PAGE_CONTENT_PX
                    ),
                    "remainingRatio": anchor["remainingRatio"],
                    "page": anchor["page"],
                }
            signature = tuple(
                (index, item["placement"], round(item["targetHeight"], 1), item["page"])
                for index, item in sorted((int(key), value) for key, value in layouts.items())
            )
            result = page.evaluate(_APPLY_FIGURE_LAYOUT_JS, {"pageHeight": PAGE_CONTENT_PX, "layouts": layouts})
            current_figures_fit = all(
                item["placement"] != "current" or figure_pages[index] == anchors[index]["page"]
                for index, item in ((int(key), value) for key, value in applied_layouts.items())
            )
            converged = signature == previous_signature and current_figures_fit
            current_count = sum(1 for item in layouts.values() if item["placement"] == "current")
            log(
                f"[md2pdf] Layout pass {pass_number}/{MAX_FIGURE_LAYOUT_PASSES} - "
                f"current page: {current_count}, next page: {count - current_count}"
                + (" (converged)" if converged else "")
            )
            if converged:
                break
            previous_signature = signature
            applied_layouts = layouts
        else:
            unresolved = sorted(
                index
                for index, item in ((int(key), value) for key, value in applied_layouts.items())
                if item["placement"] == "current" and figure_pages[index] != anchors[index]["page"]
            )
            raise ValueError(f"Figure layout did not converge within {MAX_FIGURE_LAYOUT_PASSES} passes: {unresolved}")
    finally:
        page.evaluate(_RESTORE_LAYOUT_IMAGES_JS)
        page.wait_for_function(
            "[...document.images].every(img => img.complete && img.naturalWidth > 0)",
            timeout=30_000,
        )

    # Erase layout markers so they do not appear in selectable text
    page.locator(".summary-layout-anchor, .summary-figure-marker").evaluate_all(
        "els => els.forEach(el => { el.textContent = ''; })"
    )
    return result


_HF_STYLE = (
    "font-family:'Malgun Gothic','Pretendard',sans-serif;"
    "font-size:10px;color:#9aa0a6;width:100%;"
    "padding:0 15mm;-webkit-print-color-adjust:exact;"
)


def _header_template(title: str) -> str:
    return f'<div style="{_HF_STYLE}text-align:center;">{_esc(title)}</div>'


def _footer_template() -> str:
    return (
        f'<div style="{_HF_STYLE}text-align:center;">'
        '<span class="pageNumber"></span> / <span class="totalPages"></span>'
        "</div>"
    )


def _emit_pdf(page, path: Path, doc_title: str) -> None:
    page.pdf(
        path=str(path),
        format="A4",
        print_background=True,
        display_header_footer=True,
        header_template=_header_template(doc_title),
        footer_template=_footer_template(),
        margin={"top": "18mm", "right": "15mm", "bottom": "16mm", "left": "15mm"},
    )


def build_html(
    markdown_text: str,
    title: str = "",
    theme: str = "custom",
    base_dir: Path | str | None = None,
) -> str:
    """Convert Markdown to HTML with embedded styling and smart image wrapping."""
    body = md.markdown(markdown_text, extensions=MD_EXTENSIONS)
    body = _wrap_summary_images(body)

    base_tag = ""
    if base_dir:
        resolved_base = Path(base_dir).resolve()
        # Trailing slash is necessary for relative URL resolution
        base_uri = resolved_base.as_uri() + "/"
        base_tag = f'<base href="{base_uri}">'

    return (
        "<!DOCTYPE html><html lang='ko'><head><meta charset='utf-8'>"
        f"{base_tag}"
        f"<title>{_esc(title)}</title><style>\n{_theme_css(theme)}\n"
        f"{_SUMMARY_IMAGE_CSS}\n</style>"
        f"</head><body>{body}</body></html>"
    )


def render(
    input_path: str | Path,
    output_path: str | Path | None = None,
    title: str = "",
    theme: str = "custom",
    preprocess: bool = True,
    log: Callable = print,
) -> Path:
    """Render a Markdown file into a PDF.

    Parameters:
        input_path: Path to the source markdown file.
        output_path: Path to the target PDF. Defaults to [input_name].pdf.
        title: Document title for running headers. If empty, extracted from markdown or filename.
        theme: 'custom' (default typora-like) or 'github'.
        preprocess: Whether to normalize list indentations and block margins.
        log: Logging callback function.
    """
    input_file = Path(input_path).resolve()
    if not input_file.is_file():
        raise FileNotFoundError(f"Input markdown file not found: {input_file}")

    if output_path is None:
        output_file = input_file.with_suffix(".pdf")
    else:
        output_file = Path(output_path).resolve()

    output_file.parent.mkdir(parents=True, exist_ok=True)

    raw_md = input_file.read_text(encoding="utf-8")
    if not raw_md.strip():
        raise ValueError(f"Input markdown is empty: {input_file}")

    if preprocess:
        processed_md = preprocess_markdown(raw_md)
    else:
        processed_md = raw_md

    doc_title = title or extract_title(processed_md, fallback=input_file.stem)
    if theme not in THEME_CHOICES:
        theme = "custom"

    html = build_html(processed_md, title=doc_title, theme=theme, base_dir=input_file.parent)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise ImportError(
            "playwright is required to render PDFs. "
            "Please run `pip install playwright && playwright install chromium`."
        )

    with tempfile.TemporaryDirectory() as td:
        temp_dir = Path(td)
        tmp_html = temp_dir / "render.html"
        draft_pdf = temp_dir / "draft.layout.pdf"
        tmp_html.write_text(html, encoding="utf-8")

        try:
            with sync_playwright() as p:
                try:
                    browser = p.chromium.launch(headless=True)
                except Exception as err:
                    if "Executable doesn't exist" in str(err) or "playwright install" in str(err).lower():
                        raise RuntimeError(
                            "Chromium is not installed for Playwright. "
                            "Please run: `playwright install chromium` in your shell."
                        ) from err
                    raise

                try:
                    page = browser.new_page()
                    page.goto(tmp_html.as_uri(), wait_until="networkidle")
                    page.emulate_media(media="print")

                    _fit_summary_figures(page, draft_pdf, doc_title, log=log)
                    log(f"[md2pdf] Generating final PDF: {output_file.name}...")
                    _emit_pdf(page, output_file, doc_title)
                finally:
                    browser.close()
        except Exception:
            raise

    size = output_file.stat().st_size
    if size < 500:
        raise ValueError(f"Generated PDF appears corrupted (only {size} bytes): {output_file}")

    log(f"[md2pdf] Successfully generated: {output_file} ({size / (1024 * 1024):.2f} MB)")
    return output_file

