import tempfile
import unittest
from pathlib import Path

from md2pdf.preprocess import extract_title, normalize_list_indent, pad_blocks, preprocess_markdown
from md2pdf.renderer import build_html, render


class PreprocessTests(unittest.TestCase):
    def test_normalize_list_indent(self):
        text = "- Item 1\n  - Subitem 1.1\n    - Subitem 1.1.1\n- Item 2"
        normalized = normalize_list_indent(text)
        self.assertIn("    - Subitem 1.1", normalized)
        self.assertIn("        - Subitem 1.1.1", normalized)

    def test_pad_blocks_table_and_fence(self):
        text = "Paragraph\n| H1 | H2 |\n| --- | --- |\n| A | B |\nText after"
        padded = pad_blocks(text)
        self.assertIn("Paragraph\n\n| H1 | H2 |", padded)
        self.assertIn("| A | B |\n\nText after", padded)

    def test_extract_title(self):
        text = "Intro\n\n# Document Title\n\nBody"
        self.assertEqual(extract_title(text), "Document Title")
        self.assertEqual(extract_title("No heading", fallback="Default"), "Default")


class HtmlBuilderTests(unittest.TestCase):
    def test_build_html_contains_fonts_and_figures(self):
        md_text = "# Sample\n\n![Image](test.png)\n\n*A diagram caption*"
        html = build_html(md_text, title="Test Doc", theme="custom")

        self.assertIn("Pretendard", html)
        self.assertIn("Open Sans", html)
        self.assertIn("<title>Test Doc</title>", html)
        self.assertIn('class="summary-figure"', html)
        self.assertIn("<figcaption><em>A diagram caption</em></figcaption>", html)

    def test_build_html_with_base_dir(self):
        md_text = "![Local](pic.png)"
        base_path = Path("/workspace/docs")
        html = build_html(md_text, base_dir=base_path)
        self.assertIn("<base href=", html)

    def test_github_theme_selection(self):
        html = build_html("Hello World", theme="github")
        self.assertIn("Pretendard", html)
        self.assertIn("--side-bar-bg-color", html)


class PdfRenderIntegrationTests(unittest.TestCase):
    def test_render_minimal_markdown(self):
        with tempfile.TemporaryDirectory() as td:
            md_file = Path(td) / "test.md"
            pdf_file = Path(td) / "test.pdf"

            md_file.write_text(
                "# Minimal Document\n\nThis is a test paragraph.\n\n- Item 1\n- Item 2\n",
                encoding="utf-8",
            )

            out_path = render(md_file, pdf_file, title="Test Document", log=lambda *_: None)
            self.assertTrue(out_path.exists())
            self.assertGreater(out_path.stat().st_size, 2000)


if __name__ == "__main__":
    unittest.main()
