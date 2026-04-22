#!/usr/bin/env python3
"""Generate DOCX and PDF resume artifacts from the assembled resume output.
This command runs the existing build pipeline once, then exports both formats in a
deterministic order, preferring processed default-template HTML when available and
falling back to the assembled markdown artifact otherwise.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    import build_resume
else:
    from scripts import build_resume


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=build_resume.DEFAULT_PROFILE)
    parser.add_argument(
        "--experience-db", type=Path, default=build_resume.DEFAULT_EXPERIENCE_DB
    )
    parser.add_argument(
        "--skills-matrix", type=Path, default=build_resume.DEFAULT_SKILLS_MATRIX
    )
    parser.add_argument("--job-url", type=str, default="")
    parser.add_argument("--job-text-file", type=Path, default=None)
    parser.add_argument("--target-role", type=str, default="")
    parser.add_argument(
        "--company",
        type=str,
        default="company",
        help="Company slug source for canonical output names (<company>_resume.*).",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=build_resume.DEFAULT_OUTPUT_DIR
    )
    parser.add_argument(
        "--processing-mode",
        choices=("raw", "processed"),
        default="processed",
        help="Use processed mode by default for submission-ready output.",
    )
    parser.add_argument(
        "--template",
        type=str,
        default="modern",
        help="Secondary template pass-through for build pipeline consistency.",
    )
    parser.add_argument(
        "--pdf-filename",
        type=str,
        default=None,
        help="Optional PDF file name override under --output-dir.",
    )
    parser.add_argument(
        "--docx-filename",
        type=str,
        default=None,
        help="Optional DOCX file name override under --output-dir.",
    )
    return parser.parse_args()


def _snake_case(value: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "_", value.strip().lower())
    token = token.strip("_")
    return token or "company"


def _canonical_export_filename(company: str, extension: str) -> str:
    ext = extension.lower().lstrip(".")
    return f"{_snake_case(company)}_resume.{ext}"


def _remove_stale_legacy_exports(output_dir: Path, keep_paths: set[Path]) -> list[Path]:
    """Remove outdated legacy export aliases that can mask the current outputs."""
    removed: list[Path] = []
    for legacy_name in ("latest_resume_export.docx", "latest_resume_export.pdf"):
        legacy_path = output_dir / legacy_name
        if legacy_path in keep_paths or not legacy_path.exists():
            continue
        legacy_path.unlink()
        removed.append(legacy_path)
    return removed


def _require_python_docx() -> tuple[Any, Any, Any]:
    try:
        from docx import Document
        from docx.shared import Inches, Pt
    except ImportError as exc:
        raise RuntimeError(
            "python-docx is required for DOCX export. "
            f"Install dependencies from requirements.txt. Import error: {exc}"
        ) from exc
    return Document, Pt, Inches


def _require_reportlab() -> tuple[Any, Any, Any]:
    try:
        from reportlab.lib.pagesizes import LETTER
        from reportlab.pdfbase.pdfmetrics import stringWidth
        from reportlab.pdfgen import canvas
    except ImportError as exc:
        raise RuntimeError(
            "reportlab is required for PDF export. "
            f"Install dependencies from requirements.txt. Import error: {exc}"
        ) from exc
    return LETTER, canvas, stringWidth


def _find_carlito_path(style: str = "Regular") -> Path | None:
    """Locate Carlito TTF via fontconfig, then common Linux font paths."""
    try:
        result = subprocess.run(
            [
                "fc-list",
                f":family=Carlito:style={style}",
                "--format=%{file}\n",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in result.stdout.splitlines():
            path = Path(line.strip())
            if path.exists():
                return path
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    file_map = {
        "Regular": "Carlito-Regular.ttf",
        "Bold": "Carlito-Bold.ttf",
    }
    expected_file = file_map.get(style)
    if not expected_file:
        return None
    for base in (
        Path("/usr/share/fonts/truetype/crosextra"),
        Path("/usr/share/fonts/truetype/carlito"),
    ):
        candidate = base / expected_file
        if candidate.exists():
            return candidate
    return None


def _require_carlito_pdf_fonts() -> tuple[str, str]:
    """Register and return ReportLab font names for Carlito Regular/Bold."""
    regular_path = _find_carlito_path("Regular")
    bold_path = _find_carlito_path("Bold")
    if regular_path is None or bold_path is None:
        raise FileNotFoundError(
            "Carlito font not found for PDF export.\n"
            "This renderer requires exact Carlito metrics; no fallback fonts are allowed.\n\n"
            "Fix:\n"
            "  1) Install fontconfig and Carlito fonts:\n"
            "     apt-get update && apt-get install -y fontconfig fonts-crosextra-carlito\n"
            "     fc-cache -fv\n"
            "  2) Verify discovery:\n"
            "     fc-list ':family=Carlito' --format='%{file}\\n'\n"
            "  3) Re-run PDF export."
        )

    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "reportlab is required for PDF export. Install dependencies from requirements.txt"
        ) from exc

    regular_name = "Carlito"
    bold_name = "Carlito-Bold"
    registered = set(pdfmetrics.getRegisteredFontNames())
    if regular_name not in registered:
        pdfmetrics.registerFont(TTFont(regular_name, str(regular_path)))
    if bold_name not in registered:
        pdfmetrics.registerFont(TTFont(bold_name, str(bold_path)))
    return regular_name, bold_name


def _pipeline_markdown_path(output_dir: Path, processing_mode: str) -> Path:
    suffix = "processed" if processing_mode == "processed" else "raw"
    return output_dir / f"latest_resume_{suffix}.md"


def _pipeline_default_html_path(args: argparse.Namespace) -> Path:
    """Return the left-justified default-template HTML path from build output."""
    # Keep naming local to avoid coupling to build_resume private helpers.
    output_prefix = f"latest_resume_{args.processing_mode}"
    primary_template = "modern" if args.processing_mode == "processed" else "default"
    if primary_template == "default":
        return Path(args.output_dir) / f"{output_prefix}.html"

    secondary_template = args.template
    if secondary_template == primary_template:
        secondary_template = "default"
    if secondary_template == "default":
        secondary_prefix = f"latest_default_resume_{args.processing_mode}"
        return Path(args.output_dir) / f"{secondary_prefix}.html"

    # Fallback for custom template invocations: default to primary HTML.
    return Path(args.output_dir) / f"{output_prefix}.html"


def _run_build_pipeline(args: argparse.Namespace) -> Path:
    pipeline_args = argparse.Namespace(
        profile=args.profile,
        experience_db=args.experience_db,
        skills_matrix=args.skills_matrix,
        job_url=args.job_url,
        job_text_file=args.job_text_file,
        target_role=args.target_role,
        output_dir=args.output_dir,
        processing_mode=args.processing_mode,
        skip_markdown=False,
        template=args.template,
    )
    rc = build_resume.run_pipeline(pipeline_args)
    if rc != 0:
        raise RuntimeError(f"build pipeline failed with exit code {rc}")
    md_path = _pipeline_markdown_path(args.output_dir, args.processing_mode)
    if not md_path.exists():
        raise RuntimeError(f"expected markdown output not found: {md_path}")
    return md_path


# ---------------------------------------------------------------------------
# Shared markdown block parser
# ---------------------------------------------------------------------------
_SKIP_LINE_RE = re.compile(r"^Related skills:", re.IGNORECASE)
_BOLD_SPLIT_RE = re.compile(r"\*\*(.+?)\*\*")
_HIDDEN_HTML_CLASS_TOKENS = {"related-skills"}


class _ResumeHtmlBlockParser(HTMLParser):
    """Extract visible heading/paragraph/list blocks in DOM order."""

    def __init__(self) -> None:
        super().__init__()
        self.blocks: list[tuple[str, str]] = []
        self._capture_stack: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # Inline elements: inject bold markers / tab separator into current block
        if tag == "strong" and self._capture_stack:
            self._capture_stack[-1]["parts"].append("**")
            return
        if tag == "span" and self._capture_stack:
            self._capture_stack[-1]["parts"].append("	")
            return
        attrs_map = {name: (value or "") for name, value in attrs}
        class_tokens = [token for token in attrs_map.get("class", "").split() if token]
        if tag == "hr" and "header-divider" in class_tokens:
            self.blocks.append(("divider", ""))
            return
        if tag not in {"h1", "h2", "h3", "p", "li"}:
            return
        self._capture_stack.append({"tag": tag, "class": class_tokens, "parts": []})

    def handle_data(self, data: str) -> None:
        if not self._capture_stack:
            return
        self._capture_stack[-1]["parts"].append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "strong" and self._capture_stack:
            self._capture_stack[-1]["parts"].append("**")
            return
        if tag == "span":
            return  # span content already captured via handle_data
        if not self._capture_stack or self._capture_stack[-1]["tag"] != tag:
            return
        captured = self._capture_stack.pop()
        raw = "".join(captured["parts"])
        # Preserve \t separators injected from <span> tags; only normalize other whitespace.
        if "	" in raw:
            text = "	".join(
                " ".join(seg.split()) for seg in raw.split("	")
            ).strip()
        else:
            text = " ".join(raw.split()).strip()
        if not text:
            return

        class_tokens: list[str] = captured["class"]
        if any(token in _HIDDEN_HTML_CLASS_TOKENS for token in class_tokens):
            return
        if tag == "h1":
            self.blocks.append(("h1", text))
        elif tag == "h2":
            self.blocks.append(("h2", text))
        elif tag == "h3":
            self.blocks.append(("h3", text))
        elif tag == "li":
            self.blocks.append(("bullet", text))
        elif "resume-title" in class_tokens:
            self.blocks.append(("title", text))
        else:
            self.blocks.append(("p", text))


def _iter_html_blocks(html_text: str) -> list[tuple[str, str]]:
    parser = _ResumeHtmlBlockParser()
    parser.feed(html_text)
    parser.close()
    return parser.blocks


def _iter_markdown_blocks(md_text: str) -> list[tuple[str, str]]:
    """Return (kind, text) pairs from markdown or HTML source text."""
    if "<html" in md_text.lower() or "<!doctype html" in md_text.lower():
        return _iter_html_blocks(md_text)

    blocks: list[tuple[str, str]] = []
    for raw in md_text.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        if _SKIP_LINE_RE.match(line):
            continue
        if line.startswith("# "):
            blocks.append(("h1", line[2:].strip()))
        elif line.startswith("## "):
            blocks.append(("h2", line[3:].strip()))
        elif line.startswith("### "):
            blocks.append(("h3", line[4:].strip()))
        elif re.match(r"^\s*-\s+", line):
            blocks.append(("bullet", re.sub(r"^\s*-\s+", "", line, count=1).strip()))
        else:
            blocks.append(("p", line))
    return blocks


# ---------------------------------------------------------------------------
# DOCX renderer
# ---------------------------------------------------------------------------
def _add_rich_runs(
    paragraph: Any, text: str, base_size_pt: float, bold_base: bool = False
) -> None:
    """Add runs to a paragraph, honouring **bold** markers, stripping link syntax."""
    _, Pt, _ = _require_python_docx()
    text = _MD_LINK_RE.sub(r"\1", text)
    text = _MD_CODE_RE.sub(r"\1", text)
    parts = _BOLD_SPLIT_RE.split(text)
    for i, part in enumerate(parts):
        if not part:
            continue
        run = paragraph.add_run(part)
        run.font.size = Pt(base_size_pt)
        # odd-indexed splits are the captured bold groups
        run.bold = bold_base or (i % 2 == 1)


def _render_docx(md_text: str, output_path: Path) -> None:
    Document, Pt, Inches = _require_python_docx()
    from docx.enum.text import WD_LINE_SPACING

    divider_after_pt = 12

    doc = Document()
    # Narrow margins to match HTML template (0.5in each side)
    for section in doc.sections:
        section.left_margin = Inches(0.5)
        section.right_margin = Inches(0.5)
        section.top_margin = Inches(0.5)
        section.bottom_margin = Inches(0.5)
    # Base style
    normal = doc.styles["Normal"]
    normal.font.name = "Carlito"
    normal.font.size = Pt(11)

    def add_paragraph_bottom_border(
        paragraph: Any, *, color: str, size: int, space: int = 1
    ) -> None:
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn

        p_pr = paragraph._p.get_or_add_pPr()
        p_bdr = p_pr.find(qn("w:pBdr"))
        if p_bdr is None:
            p_bdr = OxmlElement("w:pBdr")
            p_pr.append(p_bdr)
        bottom = OxmlElement("w:bottom")
        bottom.set(qn("w:val"), "single")
        bottom.set(qn("w:sz"), str(size))
        bottom.set(qn("w:space"), str(space))
        bottom.set(qn("w:color"), color)
        p_bdr.append(bottom)

    def add_horizontal_rule(
        *, color: str, size: int, before_pt: float, after_pt: float
    ) -> None:
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(before_pt)
        p.paragraph_format.space_after = Pt(after_pt)
        p.add_run("")
        add_paragraph_bottom_border(p, color=color, size=size)

    def apply_word_body_paragraph_settings(paragraph: Any) -> None:
        """Match Word paragraph settings used in the approved sample output."""
        paragraph.paragraph_format.space_before = Pt(0)
        paragraph.paragraph_format.space_after = Pt(0)
        paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.AT_LEAST
        paragraph.paragraph_format.line_spacing = Pt(11)

    previous_paragraph: Any | None = None
    seen_role_title = False

    for kind, text in _iter_markdown_blocks(md_text):
        if kind == "h1":
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            run = p.add_run(text)
            run.bold = True
            run.font.name = "Carlito"
            run.font.size = Pt(18)
            previous_paragraph = p
        elif kind == "h2":
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(12)
            p.paragraph_format.space_after = Pt(0)
            run = p.add_run(text)
            run.bold = True
            run.font.name = "Carlito"
            run.font.size = Pt(12)
            add_paragraph_bottom_border(p, color="CCCCCC", size=8, space=0)
            previous_paragraph = p
        elif kind == "h3":
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(0 if not seen_role_title else 6)
            p.paragraph_format.space_after = Pt(0)
            if "	" in text:
                title_part, date_part = text.split("	", 1)
                title_plain = _strip_markdown_markup(title_part).strip()
                date_plain = _strip_markdown_markup(date_part).strip()
                run = p.add_run(title_plain)
                run.bold = True
                run.font.name = "Carlito"
                run.font.size = Pt(11)
                # Right tab stop at content width (7.5 in = 10800 twips)
                from docx.oxml import OxmlElement
                from docx.oxml.ns import qn

                pPr = p._p.get_or_add_pPr()
                tabs_el = OxmlElement("w:tabs")
                tab_el = OxmlElement("w:tab")
                tab_el.set(qn("w:val"), "right")
                tab_el.set(qn("w:pos"), "10800")
                tabs_el.append(tab_el)
                pPr.append(tabs_el)
                date_run = p.add_run("	" + date_plain)
                date_run.bold = False
                date_run.font.name = "Carlito"
                date_run.font.size = Pt(11)
            else:
                run = p.add_run(text)
                run.bold = True
                run.font.name = "Carlito"
                run.font.size = Pt(11)
            seen_role_title = True
            previous_paragraph = p
        elif kind == "title":
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(2)
            run = p.add_run(_strip_markdown_markup(text))
            run.bold = True
            run.font.name = "Carlito"
            run.font.size = Pt(11)
            previous_paragraph = p
        elif kind == "bullet":
            p = doc.add_paragraph(style="List Bullet")
            apply_word_body_paragraph_settings(p)
            # Override list-style hanging/negative indent so bullets align to 0.
            p.paragraph_format.left_indent = Pt(0)
            p.paragraph_format.first_line_indent = Pt(0)
            _add_rich_runs(p, text, 11)
            previous_paragraph = p
        elif kind == "divider":
            if previous_paragraph is None:
                add_horizontal_rule(
                    color="000000", size=12, before_pt=0, after_pt=divider_after_pt
                )
            else:
                add_paragraph_bottom_border(
                    previous_paragraph, color="000000", size=12, space=0
                )
                previous_paragraph.paragraph_format.space_after = Pt(divider_after_pt)
        else:  # p — contact line, date line, role summary, company line, skills
            p = doc.add_paragraph()
            apply_word_body_paragraph_settings(p)
            if "	" in text:
                # Company line: "**Company, Location**	Date Range"
                left_part, right_part = text.split("	", 1)
                left_plain = _strip_markdown_markup(left_part).strip()
                right_plain = _strip_markdown_markup(right_part).strip()
                run = p.add_run(left_plain)
                run.bold = True
                run.font.name = "Carlito"
                run.font.size = Pt(11)
                from docx.oxml import OxmlElement
                from docx.oxml.ns import qn

                pPr = p._p.get_or_add_pPr()
                tabs_el = OxmlElement("w:tabs")
                tab_el = OxmlElement("w:tab")
                tab_el.set(qn("w:val"), "right")
                tab_el.set(qn("w:pos"), "10800")
                tabs_el.append(tab_el)
                pPr.append(tabs_el)
                date_run = p.add_run("	" + right_plain)
                date_run.bold = True
                date_run.font.name = "Carlito"
                date_run.font.size = Pt(11)
            elif (skills_parts := _split_skills_category_line(text)) is not None:
                category, skills = skills_parts
                cat_run = p.add_run(f"{category} ")
                cat_run.bold = True
                cat_run.font.name = "Carlito"
                cat_run.font.size = Pt(11)
                skills_run = p.add_run(skills)
                skills_run.bold = False
                skills_run.font.name = "Carlito"
                skills_run.font.size = Pt(11)
            else:
                _add_rich_runs(p, text, 11)
            previous_paragraph = p
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_path)


# ---------------------------------------------------------------------------
# PDF renderer
# ---------------------------------------------------------------------------
def _wrap_text_for_pdf(
    text: str, max_width: float, font_name: str, font_size: int
) -> list[str]:
    _LETTER, _canvas, string_width = _require_reportlab()
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if string_width(candidate, font_name, font_size) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _wrap_skills_category_for_pdf(
    bold_prefix: str,
    regular_text: str,
    max_width: float,
    fn_bold: str,
    fn_regular: str,
    font_size: int,
) -> list[tuple[str, str]]:
    """Wrap a skills-category line using the correct font per segment.
    Returns a list of (bold_part, regular_part) tuples, one per output line.
    The bold_prefix is measured with fn_bold; remaining words with fn_regular,
    so wrap points reflect the actual rendered glyph widths.
    """
    _LETTER, _canvas, sw = _require_reportlab()
    prefix_w = sw(bold_prefix, fn_bold, font_size)
    words = regular_text.split()
    lines: list[tuple[str, str]] = []
    # --- First line: starts with bold prefix ---
    current_regular = ""
    current_w = prefix_w
    for i, word in enumerate(words):
        sep = " " if current_regular else ""
        word_w = sw(sep + word, fn_regular, font_size)
        if current_w + word_w <= max_width:
            current_regular += sep + word
            current_w += word_w
        else:
            lines.append((bold_prefix, current_regular))
            remaining = words[i:]
            break
    else:
        # All words fit on first line
        lines.append((bold_prefix, current_regular))
        return lines
    # --- Subsequent lines: all regular ---
    if remaining:
        current = remaining[0]
        for word in remaining[1:]:
            candidate = f"{current} {word}"
            if sw(candidate, fn_regular, font_size) <= max_width:
                current = candidate
            else:
                lines.append(("", current))
                current = word
        lines.append(("", current))
    return lines


_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_MD_CODE_RE = re.compile(r"`([^`]+)`")
_SKILLS_CATEGORY_RE = re.compile(r"^\*\*(.+?:)\*\*\s*(.+)$")


def _strip_markdown_markup(text: str) -> str:
    """Strip bold, links, and inline code markers for plain-text renderers."""
    text = _BOLD_SPLIT_RE.sub(r"\1", text)
    text = _MD_LINK_RE.sub(r"\1", text)
    text = _MD_CODE_RE.sub(r"\1", text)
    return text


def _split_skills_category_line(text: str) -> tuple[str, str] | None:
    """Return (category, skills) for lines like '**Category:** skill1 • skill2'."""
    match = _SKILLS_CATEGORY_RE.match(text.strip())
    if not match:
        return None
    return match.group(1).strip(), match.group(2).strip()


def _render_pdf(md_text: str, output_path: Path) -> None:
    import io as _io

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.unlink(missing_ok=True)

    LETTER, canvas_mod, _sw = _require_reportlab()
    fn_regular, fn_bold = _require_carlito_pdf_fonts()
    buf = _io.BytesIO()
    pdf = canvas_mod.Canvas(buf, pagesize=LETTER)
    width, height = LETTER
    # Keep near-HTML width while preserving a stable two-page PDF envelope.
    margin_x: float = 46
    margin_top: float = 32
    margin_bottom: float = 32
    y: float = height - margin_top
    page_count = 1
    content_width = width - 2 * margin_x
    seen_divider = False
    last_text_baseline_y: float | None = None

    def new_page() -> None:
        nonlocal y, page_count
        pdf.showPage()
        page_count += 1
        y = height - margin_top

    def ensure_space(needed_pts: float) -> None:
        if y - needed_pts < margin_bottom:
            new_page()

    def ensure_line_space(line_height: float) -> None:
        ensure_space(line_height)

    def draw_horizontal_rule(
        *, before_pts: float, after_pts: float, width: float = 1.0, gray: float = 0.0
    ) -> None:
        """Draw a rule in its own vertical row so it never overlaps text."""
        nonlocal y
        ensure_space(before_pts + 1 + after_pts)
        y -= before_pts
        pdf.setStrokeColorRGB(gray, gray, gray)
        pdf.setLineWidth(width)
        pdf.line(margin_x, y, margin_x + content_width, y)
        y -= after_pts

    for kind, text in _iter_markdown_blocks(md_text):
        plain = _strip_markdown_markup(text)
        if kind == "h1":
            fn, fs, lh = fn_bold, 18, 15.2
            ensure_space(lh + 4)
            pdf.setFont(fn, fs)
            pdf.drawString(margin_x, y, plain)
            last_text_baseline_y = y
            y -= lh
        elif kind == "h2":
            fn, fs, lh = fn_bold, 12, 15
            ensure_space(lh + 18)
            y -= 6
            pdf.setFont(fn, fs)
            heading_y = y
            pdf.drawString(margin_x, heading_y, plain)
            last_text_baseline_y = heading_y
            line_y = heading_y - 2
            pdf.setStrokeColorRGB(0.8, 0.8, 0.8)
            pdf.setLineWidth(0.8)
            pdf.line(margin_x, line_y, margin_x + content_width, line_y)
            y = line_y - 16
        elif kind == "h3":
            fn_bold_name, fn_reg_name, fs, lh = fn_bold, fn_regular, 11, 13.2
            ensure_space(lh + 3)
            y -= 2  # space before job title
            if "	" in text:
                title_part, date_part = text.split("	", 1)
                title_plain = _strip_markdown_markup(title_part).strip()
                date_plain = _strip_markdown_markup(date_part).strip()
            else:
                title_plain = plain
                date_plain = None
            pdf.setFont(fn_bold_name, fs)
            pdf.drawString(margin_x, y, title_plain)
            last_text_baseline_y = y
            if date_plain:
                _sw = _require_reportlab()[2]
                dw = _sw(date_plain, fn_reg_name, 11)
                pdf.setFont(fn_reg_name, 11)
                pdf.drawString(margin_x + content_width - dw, y, date_plain)
            y -= lh
        elif kind == "title":
            fn, fs, lh = fn_bold, 11, 13
            ensure_space(lh + 2)
            pdf.setFont(fn, fs)
            pdf.drawString(margin_x, y, plain)
            last_text_baseline_y = y
            y -= lh
        elif kind == "divider":
            seen_divider = True
            # Match h2 behavior: line sits just under the preceding text and leaves 16pt after.
            if last_text_baseline_y is None:
                draw_horizontal_rule(before_pts=0, after_pts=16, width=1.0, gray=0.0)
            else:
                line_y = last_text_baseline_y - 2
                pdf.setStrokeColorRGB(0.0, 0.0, 0.0)
                pdf.setLineWidth(1.0)
                pdf.line(margin_x, line_y, margin_x + content_width, line_y)
                y = line_y - 16
        elif kind == "bullet":
            fn, fn_bold_name, fs, lh = fn_regular, fn_bold, 11, 12.2
            bullet_x = margin_x + 1
            text_x = margin_x + 14
            avail = content_width - (text_x - margin_x)
            lines: list[str]
            if (skills_parts := _split_skills_category_line(text)) is not None:
                category, skills = skills_parts
                category_with_space = f"{category} "
                _sw = _require_reportlab()[2]
                category_w = _sw(category_with_space, fn_bold_name, fs)
                skills_w = _sw(skills, fn, fs)
                if category_w + skills_w <= avail:
                    ensure_space(lh + 1)
                    ensure_line_space(lh)
                    pdf.drawString(bullet_x, y, "•")
                    pdf.setFont(fn_bold_name, fs)
                    pdf.drawString(text_x, y, category_with_space)
                    pdf.setFont(fn, fs)
                    pdf.drawString(text_x + category_w, y, skills)
                    last_text_baseline_y = y
                    y -= lh
                else:
                    wrapped_lines = _wrap_skills_category_for_pdf(
                        category_with_space,
                        skills,
                        avail,
                        fn_bold_name,
                        fn,
                        fs,
                    )
                    ensure_space(len(wrapped_lines) * lh + 1)
                    for i, (bold_text, regular_text) in enumerate(wrapped_lines):
                        ensure_line_space(lh)
                        if i == 0:
                            pdf.drawString(bullet_x, y, "•")
                        if bold_text:
                            pdf.setFont(fn_bold_name, fs)
                            pdf.drawString(text_x, y, bold_text)
                        if regular_text:
                            bold_w = (
                                _sw(bold_text, fn_bold_name, fs) if bold_text else 0
                            )
                            pdf.setFont(fn, fs)
                            pdf.drawString(text_x + bold_w, y, regular_text)
                        last_text_baseline_y = y
                        y -= lh
                y -= 0.4
            else:
                text_font = fn
                if "**" in text:
                    bold_parts = _BOLD_SPLIT_RE.split(text)
                    # Fully-bold markdown bullet line: **...**
                    if (
                        len(bold_parts) == 3
                        and not bold_parts[0].strip()
                        and not bold_parts[2].strip()
                    ):
                        text_font = fn_bold_name
                        bullet_text = _strip_markdown_markup(bold_parts[1])
                        lines = _wrap_text_for_pdf(bullet_text, avail, text_font, fs)
                    else:
                        lines = _wrap_text_for_pdf(plain, avail, text_font, fs)
                else:
                    lines = _wrap_text_for_pdf(plain, avail, text_font, fs)
                ensure_space(len(lines) * lh + 1)
                pdf.setFont(text_font, fs)
                for i, line in enumerate(lines):
                    ensure_line_space(lh)
                    if i == 0:
                        pdf.drawString(bullet_x, y, "•")
                    pdf.drawString(text_x, y, line)
                    last_text_baseline_y = y
                    y -= lh
                y -= 0.4
        else:  # p — contact, date, role summary, company line, skills
            fn, fn_bold_name, fs, lh = fn_regular, fn_bold, 11, 11.2
            post_gap = 0 if not seen_divider else 0.4
            if "	" in text:
                # Company line: "**Company, Location**	Date Range"
                left_part, right_part = text.split("	", 1)
                left_plain = _strip_markdown_markup(left_part).strip()
                right_plain = _strip_markdown_markup(right_part).strip()
                ensure_space(lh + 1)
                _sw = _require_reportlab()[2]
                rw = _sw(right_plain, fn_bold_name, 11)
                pdf.setFont(fn_bold_name, fs)
                pdf.drawString(margin_x, y, left_plain)
                last_text_baseline_y = y
                pdf.setFont(fn_bold_name, 11)
                pdf.drawString(margin_x + content_width - rw, y, right_plain)
                y -= lh
                y -= post_gap
            elif (skills_parts := _split_skills_category_line(text)) is not None:
                category, skills = skills_parts
                category_with_space = f"{category} "
                _sw = _require_reportlab()[2]
                category_w = _sw(category_with_space, fn_bold_name, fs)
                skills_w = _sw(skills, fn, fs)
                ensure_space(lh + 1)
                if category_w + skills_w <= content_width:
                    pdf.setFont(fn_bold_name, fs)
                    pdf.drawString(margin_x, y, category_with_space)
                    pdf.setFont(fn, fs)
                    pdf.drawString(margin_x + category_w, y, skills)
                    last_text_baseline_y = y
                    y -= lh
                else:
                    wrapped_lines = _wrap_skills_category_for_pdf(
                        category_with_space,
                        skills,
                        content_width,
                        fn_bold_name,
                        fn,
                        fs,
                    )
                    ensure_space(len(wrapped_lines) * lh + 1)
                    for bold_text, regular_text in wrapped_lines:
                        ensure_line_space(lh)
                        if bold_text:
                            pdf.setFont(fn_bold_name, fs)
                            pdf.drawString(margin_x, y, bold_text)
                        if regular_text:
                            bold_w = (
                                _sw(bold_text, fn_bold_name, fs) if bold_text else 0
                            )
                            pdf.setFont(fn, fs)
                            pdf.drawString(margin_x + bold_w, y, regular_text)
                        last_text_baseline_y = y
                        y -= lh
                y -= post_gap
            else:
                # Check for inline bold markers (e.g. degree line: **Bachelor of Science...**)
                if "**" in text:
                    _sw_fn = _require_reportlab()[2]
                    # Split on bold markers: odd-indexed parts are bold
                    bold_parts = _BOLD_SPLIT_RE.split(text)
                    # If entirely bold (single bold group wrapping all content), render bold
                    if (
                        len(bold_parts) == 3
                        and not bold_parts[0].strip()
                        and not bold_parts[2].strip()
                    ):
                        bold_text = _strip_markdown_markup(bold_parts[1])
                        lines = _wrap_text_for_pdf(
                            bold_text, content_width, fn_bold_name, fs
                        )
                        ensure_space(len(lines) * lh + 1)
                        pdf.setFont(fn_bold_name, fs)
                        for line in lines:
                            ensure_line_space(lh)
                            pdf.drawString(margin_x, y, line)
                            last_text_baseline_y = y
                            y -= lh
                    else:
                        # Mixed bold/regular: render on a single line (no wrapping for mixed)
                        ensure_space(lh + 1)
                        x_cursor = margin_x
                        for i, part in enumerate(bold_parts):
                            if not part:
                                continue
                            part_plain = _strip_markdown_markup(part)
                            is_bold = i % 2 == 1
                            cur_fn = fn_bold_name if is_bold else fn
                            pw = _sw_fn(part_plain, cur_fn, fs)
                            pdf.setFont(cur_fn, fs)
                            pdf.drawString(x_cursor, y, part_plain)
                            x_cursor += pw
                        last_text_baseline_y = y
                        y -= lh
                    y -= post_gap
                else:
                    lines = _wrap_text_for_pdf(plain, content_width, fn, fs)
                    ensure_space(len(lines) * lh + 1)
                    pdf.setFont(fn, fs)
                    for line in lines:
                        ensure_line_space(lh)
                        pdf.drawString(margin_x, y, line)
                        last_text_baseline_y = y
                        y -= lh
                    y -= post_gap
    pdf.save()
    if page_count > 2:
        output_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"PDF exceeded two-page limit ({page_count} pages): {output_path}"
        )
    output_path.write_bytes(buf.getvalue())


# ---------------------------------------------------------------------------
# Fragment quality guard
# ---------------------------------------------------------------------------
def _contains_trailing_connector_fragment(md_text: str) -> bool:
    bad_tail = {"and", "or", "to", "with", "for", "of", "in", "a", "an", "the"}
    for _kind, text in _iter_markdown_blocks(md_text):
        words = re.findall(r"[A-Za-z]+", text.lower())
        if words and words[-1] in bad_tail:
            return True
    return False


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def run() -> int:
    args = parse_args()
    try:
        markdown_path = _run_build_pipeline(args)
        md_text = markdown_path.read_text(encoding="utf-8")
        render_source_text = md_text
        using_html_source = False
        html_source_path = _pipeline_default_html_path(args)
        if html_source_path.exists():
            render_source_text = html_source_path.read_text(encoding="utf-8")
            using_html_source = True
        if _contains_trailing_connector_fragment(md_text):
            print(
                "WARNING: assembled content contains trailing connector fragments; review final DOCX/PDF for awkward wraps",
                file=sys.stderr,
            )
        docx_name = args.docx_filename or _canonical_export_filename(
            args.company, "docx"
        )
        pdf_name = args.pdf_filename or _canonical_export_filename(args.company, "pdf")
        docx_output = Path(args.output_dir) / docx_name
        pdf_output = Path(args.output_dir) / pdf_name
        _render_docx(render_source_text, docx_output)
        _render_pdf(render_source_text, pdf_output)
        removed_legacy_outputs = _remove_stale_legacy_exports(
            Path(args.output_dir), {docx_output, pdf_output}
        )
        print("Resume exports written:")
        print(f"  {docx_output}")
        print(f"  {pdf_output}")
        if removed_legacy_outputs:
            print("  removed stale legacy exports:")
            for removed_path in removed_legacy_outputs:
                print(f"    {removed_path}")
        print(f"  source markdown: {markdown_path}")
        if using_html_source:
            print(f"  source html: {html_source_path}")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
