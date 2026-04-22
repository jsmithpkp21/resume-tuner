#!/usr/bin/env python3
"""Resume template system supporting multiple layout designs.
Each template defines:
- CSS styling
- HTML structure for all resume sections
- How to render name, headline, contact, skills, experience, education, etc.
Templates can be extended to support different layouts:
- default: left-justified, clean, minimal styling
- modern: centered headers, modern styling (WebAI Resume style)
"""

from __future__ import annotations

import html
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class TemplateContext:
    """Data passed to template for rendering."""

    name: str
    headline: str
    contact_html: str
    target_role: str
    target_company: str
    resume_title: str
    summary: str
    skills_html: list[str]  # Pre-rendered skill category lines
    experiences_html: list[str]  # Pre-rendered experience sections
    education_html: list[str]  # Pre-rendered education items
    leadership_html: list[str]  # Pre-rendered leadership items


class ResumeTemplate(ABC):
    """Base class for resume templates."""

    def _normalize_heading_text(self, value: str) -> str:
        """Normalize text for deduplication, preserving semantic intent.

        - Converts c++ to cpp, c# to csharp for consistent comparison
        - Normalizes spaces, punctuation, and case
        - Ensures that c++, cpp, C++, CPP all normalize to the same key
        """
        normalized = value.strip().lower()
        # Semantic normalizations: c++ → cpp, c# → csharp
        normalized = re.sub(r"c\+\+", "cpp", normalized)
        normalized = re.sub(r"c#", "csharp", normalized)
        # Then normalize punctuation and spacing
        normalized = normalized.replace("|", " ").replace("/", " ")
        return re.sub(r"[^a-z0-9]+", " ", normalized).strip()

    def _render_headline(self, context: TemplateContext) -> str:
        headline = context.headline.strip()
        if not headline:
            return ""
        headline_norm = self._normalize_heading_text(headline)
        title_norm = self._normalize_heading_text(context.resume_title)
        # Suppress headline when it is equal to or a prefix/substring of the resume
        # title (e.g. headline="Senior SDET", title="Senior SDET / Framework Architect")
        # so the header never shows redundant role lines.
        if headline_norm and title_norm and headline_norm in title_norm:
            return ""
        return f'<p class="headline">{html.escape(headline)}</p>'

    def _render_title_summary(self, context: TemplateContext) -> list[str]:
        return [
            (
                f'  <p class="resume-title"><strong>{html.escape(context.resume_title)}</strong></p>'
                if context.resume_title.strip()
                else ""
            ),
            (
                f'  <p class="summary-text">{html.escape(context.summary)}</p>'
                if context.summary.strip()
                else ""
            ),
        ]

    def _render_sections(self, context: TemplateContext) -> list[str]:
        sections = [
            "  <h2>Key Skills and Expertise</h2>",
            *context.skills_html,
            "  <h2>Professional Experience</h2>",
            *context.experiences_html,
        ]
        if context.education_html:
            sections.extend(
                [
                    "  <h2>Education</h2>",
                    *context.education_html,
                ]
            )
        if context.leadership_html:
            sections.extend(
                [
                    "  <h2>Leadership &amp; Community</h2>",
                    *context.leadership_html,
                ]
            )
        return sections

    @abstractmethod
    def get_css(self) -> str:
        """Return CSS styles for this template."""
        pass

    @abstractmethod
    def render(self, context: TemplateContext) -> str:
        """Render complete HTML resume from context."""
        pass


class DefaultTemplate(ResumeTemplate):
    """Default left-justified layout with PDF-safe width and split contact lines."""

    def get_css(self) -> str:
        return """    body { font-family: Carlito, Calibri, Arial, sans-serif; margin: 16px auto; width: 510pt; font-size: 11pt; line-height: 1.22; color: #111; }
    .header { margin: 0; }
    h1 { margin: 0; font-size: 18pt; font-weight: 700; line-height: 1.0; }
    .headline { margin: 0; font-size: 11pt; }
    .contact { display: grid; grid-template-columns: 1fr; gap: 0; margin: 0; font-size: 10.5pt; line-height: 1.0; }
    .contact-line { margin: 0; line-height: 1.0; }
    .target-role { margin: 1px 0 0 0; font-size: 10.5pt; }
    .header-divider { border: 0; border-top: 1px solid #000; margin: -1px 0 16px 0; }
    .resume-title { margin: 0; font-size: 11.5pt; font-weight: 700; text-decoration: none; }
    .summary-text { margin: 2px 0 6px 0; font-size: 10.5pt; text-decoration: none; }
    h2 { font-size: 12pt; font-weight: 700; text-transform: none; letter-spacing: 0; margin: 12px 0 16px 0; border-bottom: 1px solid #ccc; padding-bottom: 0px; }
    .company-line { margin: 0; display: flex; justify-content: space-between; align-items: baseline; font-size: 10.5pt; line-height: 1.15; }
    .company-line span { margin-left: auto; text-align: right; font-size: 10pt; color: #222; font-weight: 700; }
    h3 { margin: 0; font-size: 11pt; font-weight: 700; }
    h3.job-title-line { display: flex; justify-content: space-between; align-items: baseline; line-height: 1.15; }
    h3.job-title-line:not(:first-of-type) { margin-top: 6px; }
    h3 span { font-weight: 400; color: #222; text-align: right; margin-left: auto; font-size: 10pt; }
    .dates { margin: 0; font-size: 10pt; color: #444; text-align: right; }
    .role-summary { margin: 1px 0; font-size: 10.5pt; }
    .related-skills { display: none; }
    .skills-category { margin: 0 0 3px 0; font-size: 10.5pt; }
    ul { margin: 1px 0 0 16px; padding: 0; }
    li { margin: 1px 0; font-size: 10.5pt; }
    .experience-item { margin-bottom: 6px; }
    .info-item { margin-bottom: 6px; font-size: 10.5pt; text-align: left; }
    .info-item p { margin: 1px 0; }"""

    def render(self, context: TemplateContext) -> str:
        # Split contact info: location/email first line, LinkedIn/GitHub on second line
        contact_parts = context.contact_html.split(" | ")
        contact_lines = []
        links = []
        for part in contact_parts:
            part = part.strip()
            if "linkedin.com" in part or "github.com" in part:
                links.append(part)
            else:
                contact_lines.append(part)
        contact_line_1 = " | ".join(contact_lines)
        contact_html_formatted = '  <div class="contact">\n'
        contact_html_formatted += f'    <p class="contact-line">{contact_line_1}</p>\n'
        if links:
            links_line = " | ".join(links)
            contact_html_formatted += f'    <p class="contact-line">{links_line}</p>\n'
        contact_html_formatted += "  </div>"
        headline_html = self._render_headline(context)
        return "\n".join(
            [
                "<!doctype html>",
                '<html lang="en">',
                "<head>",
                '  <meta charset="utf-8" />',
                '  <meta name="viewport" content="width=device-width, initial-scale=1" />',
                f"  <title>{html.escape(context.name)} - Resume</title>",
                "  <style>",
                self.get_css(),
                "  </style>",
                "</head>",
                "<body>",
                f"  <h1>{html.escape(context.name)}</h1>",
                f"  {headline_html}" if headline_html else "",
                contact_html_formatted.rstrip(),
                '  <hr class="header-divider" />',
                *self._render_title_summary(context),
                *self._render_sections(context),
                "</body>",
                "</html>",
                "",
            ]
        )


class ModernTemplate(ResumeTemplate):
    """Modern centered layout with PDF-safe width and split contact lines."""

    def get_css(self) -> str:
        return """    body { font-family: Carlito, Calibri, Arial, sans-serif; margin: 16px auto; width: 510pt; font-size: 11pt; line-height: 1.22; color: #111; }
    .header { text-align: center; margin: 0; }
    h1 { margin: 0; font-size: 18pt; font-weight: 700; line-height: 1.0; text-align: center; }
    .headline { margin: 0; font-size: 11pt; text-align: center; }
    .contact { display: grid; grid-template-columns: 1fr; gap: 0; margin: 0; font-size: 10.5pt; text-align: center; line-height: 1.0; }
    .contact-line { margin: 0; line-height: 1.0; }
    .target-role { margin: 1px 0 0 0; font-size: 10.5pt; text-align: center; }
    .header-divider { border: 0; border-top: 1px solid #000; margin: -1px 0 16px 0; }
    .resume-title { margin: 0; font-size: 11.5pt; font-weight: 700; text-align: center; text-decoration: none; }
    .summary-text { margin: 2px 0 6px 0; font-size: 10.5pt; text-align: center; text-decoration: none; }
    h2 { font-size: 12pt; font-weight: 700; text-transform: none; letter-spacing: 0; margin: 12px 0 16px 0; border-bottom: 1px solid #ccc; padding-bottom: 0px; text-align: center; width: 100%; display: block; }
    .company-line { margin: 0; display: flex; justify-content: space-between; align-items: baseline; font-size: 10.5pt; text-align: left; line-height: 1.15; }
    .company-line span { margin-left: auto; text-align: right; font-size: 10pt; color: #222; font-weight: 700; }
    h3 { margin: 0; font-size: 11pt; font-weight: 700; }
    h3.job-title-line { display: flex; justify-content: space-between; align-items: baseline; line-height: 1.15; }
    h3.job-title-line:not(:first-of-type) { margin-top: 6px; }
    h3 span { font-weight: 400; color: #222; text-align: right; margin-left: auto; font-size: 10pt; }
    .dates { margin: 0; font-size: 10pt; color: #444; text-align: right; }
    .role-summary { margin: 1px 0; font-size: 10.5pt; }
    .related-skills { display: none; }
    .skills-category { margin: 0 0 3px 0; font-size: 10.5pt; text-align: center; }
    ul { margin: 1px 0 0 16px; padding: 0; }
    li { margin: 1px 0; font-size: 10.5pt; }
    .experience-item { margin-bottom: 6px; }
    .info-item { margin-bottom: 6px; font-size: 10.5pt; text-align: left; }
    .info-item p { margin: 1px 0; }"""

    def render(self, context: TemplateContext) -> str:
        # Split contact info: location/email first line, LinkedIn/GitHub on second line
        contact_parts = context.contact_html.split(" | ")
        contact_lines = []
        links = []
        for part in contact_parts:
            part = part.strip()
            if "linkedin.com" in part or "github.com" in part:
                links.append(part)
            else:
                contact_lines.append(part)
        contact_line_1 = " | ".join(contact_lines)
        contact_html_formatted = '    <div class="contact">\n'
        contact_html_formatted += (
            f'      <p class="contact-line">{contact_line_1}</p>\n'
        )
        if links:
            links_line = " | ".join(links)
            contact_html_formatted += (
                f'      <p class="contact-line">{links_line}</p>\n'
            )
        contact_html_formatted += "    </div>"
        headline_html = self._render_headline(context)
        return "\n".join(
            [
                "<!doctype html>",
                '<html lang="en">',
                "<head>",
                '  <meta charset="utf-8" />',
                '  <meta name="viewport" content="width=device-width, initial-scale=1" />',
                f"  <title>{html.escape(context.name)} - Resume</title>",
                "  <style>",
                self.get_css(),
                "  </style>",
                "</head>",
                "<body>",
                '  <div class="header">',
                f"    <h1>{html.escape(context.name)}</h1>",
                f"    {headline_html}" if headline_html else "",
                contact_html_formatted.rstrip(),
                "  </div>",
                '  <hr class="header-divider" />',
                *self._render_title_summary(context),
                *self._render_sections(context),
                "</body>",
                "</html>",
                "",
            ]
        )


# Template registry
TEMPLATES: dict[str, type[ResumeTemplate]] = {
    "default": DefaultTemplate,
    "modern": ModernTemplate,
}


def get_template(name: str) -> ResumeTemplate:
    """Get a template instance by name."""
    if name not in TEMPLATES:
        available = ", ".join(sorted(TEMPLATES.keys()))
        raise ValueError(f"Template '{name}' not found. Available: {available}")
    return TEMPLATES[name]()
