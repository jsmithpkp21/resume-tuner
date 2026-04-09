#!/usr/bin/env python3
"""Resume template system supporting multiple layout designs.
Each template defines:
- CSS styling
- HTML structure for all resume sections
- How to render name, headline, contact, skills, experience, education, etc.
Templates can be extended to support different layouts:
- default: left-justified, clean, minimal styling
- modern: centered headers, modern styling (WebAI Resume style)
- compact: space-optimized for two-page PDF
"""

from __future__ import annotations

import html
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

    def _render_sections(self, context: TemplateContext) -> list[str]:
        sections = [
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
            "  <h2>Skills</h2>",
            *context.skills_html,
            "  <h2>Experience</h2>",
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
    """Default left-justified layout.
    Clean, minimal styling with:
    - Left-aligned body text
    - Simple section headers with bottom border
    - Standard margins and spacing
    """

    def get_css(self) -> str:
        return """    body { font-family: Arial, sans-serif; margin: 24px auto; max-width: 960px; line-height: 1.4; }
    h1 { margin-bottom: 4px; }
    h2 { border-bottom: 1px solid #ccc; margin-top: 20px; padding-bottom: 4px; }
    h3 { margin-bottom: 2px; }
    h3 span { font-weight: normal; color: #333; }
    .headline, .contact, .target-role, .dates, .role-summary, .related-skills { margin: 4px 0; }
    .resume-title { margin: 10px 0 4px 0; font-size: 16px; }
    .summary-text { margin: 4px 0 12px 0; }
    .skills-category { margin: 0; }
    ul { margin-top: 6px; }
    .experience-item { margin-bottom: 16px; }
    .info-item { margin-bottom: 10px; }"""

    def render(self, context: TemplateContext) -> str:
        target_role_line = (
            f'  <p class="target-role">Target role: {html.escape(context.target_role)}</p>'
            if context.target_role.strip()
            else ""
        )
        target_company_line = (
            f'  <p class="target-role">Target company: {html.escape(context.target_company)}</p>'
            if context.target_company.strip()
            else ""
        )
        sections = self._render_sections(context)
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
                f'  <p class="headline">{html.escape(context.headline)}</p>',
                f'  <p class="contact">{context.contact_html}</p>',
                target_role_line,
                target_company_line,
                *sections,
                "</body>",
                "</html>",
                "",
            ]
        )


class ModernTemplate(ResumeTemplate):
    """Modern centered layout inspired by WebAI Resume.
    Professional styling with:
    - Centered name and contact info (header block)
    - Modern section headers (no bottom border, clean styling)
    - Elegant spacing and typography
    - Left-aligned body content
    """

    def get_css(self) -> str:
        return """    body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 20px auto; max-width: 900px; line-height: 1.5; color: #1a1a1a; }
    .header { text-align: center; margin-bottom: 16px; }
    h1 { margin: 0; font-size: 24px; font-weight: 700; }
    .headline { margin: 6px 0 0 0; font-size: 14px; color: #555; }
    .contact { margin: 8px 0; font-size: 13px; color: #666; }
    .target-role { margin: 6px 0; font-size: 13px; color: #555; }
    .resume-title { margin: 6px 0 2px 0; font-size: 16px; font-weight: 700; text-align: center; }
    .summary-text { margin: 0 0 12px 0; text-align: center; font-size: 13px; color: #444; }
    h2 { font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.6px; margin-top: 18px; margin-bottom: 10px; padding-bottom: 0; border-bottom: none; }
    h3 { margin-bottom: 4px; font-size: 13px; font-weight: 600; }
    h3 span { font-weight: 400; color: #666; }
    .dates { margin: 2px 0; font-size: 12px; color: #666; }
    .role-summary { margin: 6px 0; font-size: 13px; }
    .related-skills { margin: 6px 0; font-size: 12px; color: #555; }
    .skills-category { margin: 0 0 8px 0; font-size: 13px; }
    ul { margin: 8px 0 0 20px; padding: 0; }
    li { margin: 4px 0; font-size: 13px; }
    .experience-item { margin-bottom: 14px; }
    .info-item { margin-bottom: 10px; font-size: 13px; }
    .info-item p { margin: 3px 0; }"""

    def render(self, context: TemplateContext) -> str:
        target_role_line = (
            f'  <p class="target-role">Target role: {html.escape(context.target_role)}</p>'
            if context.target_role.strip()
            else ""
        )
        target_company_line = (
            f'  <p class="target-role">Target company: {html.escape(context.target_company)}</p>'
            if context.target_company.strip()
            else ""
        )
        sections = self._render_sections(context)
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
                f'    <p class="headline">{html.escape(context.headline)}</p>',
                f'    <p class="contact">{context.contact_html}</p>',
                "  </div>",
                target_role_line,
                target_company_line,
                *sections,
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
    """Get a template instance by name.
    Args:
        name: Template name (e.g., "default", "modern")
    Returns:
        ResumeTemplate instance
    Raises:
        ValueError: If template name is not found
    """
    if name not in TEMPLATES:
        available = ", ".join(sorted(TEMPLATES.keys()))
        raise ValueError(f"Template '{name}' not found. Available: {available}")
    return TEMPLATES[name]()
