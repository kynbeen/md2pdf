"""
md2pdf - High-fidelity Markdown to PDF renderer.
"""
from md2pdf.renderer import build_html, render
from md2pdf.preprocess import preprocess_markdown, extract_title

__version__ = "0.1.0"
__all__ = ["render", "build_html", "preprocess_markdown", "extract_title"]
