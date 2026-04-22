"""Unit tests for resume_templates.py template utilities."""

from __future__ import annotations

from typing import Any

import pytest

from scripts.resume_templates import (
    DefaultTemplate,
    ModernTemplate,
    ResumeTemplate,
    TemplateContext,
)


def _make_context(**kwargs: Any) -> TemplateContext:
    """Return a minimal TemplateContext with sane defaults overridden by kwargs."""
    defaults: dict[str, Any] = dict(
        name="Jane Doe",
        headline="",
        contact_html="City, ST | jane@example.com",
        target_role="",
        target_company="",
        resume_title="",
        summary="",
        skills_html=[],
        experiences_html=[],
        education_html=[],
        leadership_html=[],
    )
    defaults.update(kwargs)
    return TemplateContext(**defaults)


@pytest.mark.parametrize("TemplateClass", [DefaultTemplate, ModernTemplate])
class TestRenderHeadline:
    """_render_headline() suppression rules apply identically across templates."""

    def test_empty_headline_renders_nothing(
        self, TemplateClass: type[ResumeTemplate]
    ) -> None:
        tmpl = TemplateClass()
        ctx = _make_context(headline="", resume_title="Software Engineer")
        assert tmpl._render_headline(ctx) == ""

    def test_headline_exact_equal_to_title_is_suppressed(
        self, TemplateClass: type[ResumeTemplate]
    ) -> None:
        tmpl = TemplateClass()
        ctx = _make_context(
            headline="Software Engineer",
            resume_title="Software Engineer",
        )
        assert tmpl._render_headline(ctx) == ""

    def test_headline_prefix_of_longer_title_is_suppressed(
        self, TemplateClass: type[ResumeTemplate]
    ) -> None:
        """Headline that is a leading substring of the title must not render.
        Regression guard for the case where derive_resume_title() appends a
        specialization suffix (e.g. ' / Framework Architect') so the title is
        longer than the bare-role headline.
        """
        tmpl = TemplateClass()
        ctx = _make_context(
            headline="Senior SDET",
            resume_title="Senior SDET / Test Automation Framework Architect",
        )
        assert tmpl._render_headline(ctx) == ""

    def test_headline_prefix_of_bullet_separated_title_is_suppressed(
        self, TemplateClass: type[ResumeTemplate]
    ) -> None:
        """Headline prefix is suppressed when title uses a bullet separator."""
        tmpl = TemplateClass()
        ctx = _make_context(
            headline="QA Engineer",
            resume_title="QA Engineer • Automation & CI/CD",
        )
        assert tmpl._render_headline(ctx) == ""

    def test_distinct_headline_is_rendered(
        self, TemplateClass: type[ResumeTemplate]
    ) -> None:
        """A headline that is not part of the title must still render."""
        tmpl = TemplateClass()
        ctx = _make_context(
            headline="Staff Platform Engineer",
            resume_title="Senior Software Engineer / Cloud Infrastructure",
        )
        result = tmpl._render_headline(ctx)
        assert '<p class="headline">Staff Platform Engineer</p>' == result

    def test_cpp_and_csharp_normalize_consistently(
        self, TemplateClass: type[ResumeTemplate]
    ) -> None:
        """Language tokens c++ and c# are normalized so dedupe still works."""
        tmpl = TemplateClass()
        # headline uses c++ but title spells it out as cpp -- should still match
        ctx = _make_context(
            headline="C++ Engineer",
            resume_title="cpp engineer",
        )
        assert tmpl._render_headline(ctx) == ""


class TestNormalizeHeadingText:
    """_normalize_heading_text() semantic normalizations."""

    def setup_method(self) -> None:
        self.tmpl = DefaultTemplate()

    def test_cpp_normalized_to_cpp(self) -> None:
        assert self.tmpl._normalize_heading_text("C++") == "cpp"

    def test_csharp_normalized_to_csharp(self) -> None:
        assert self.tmpl._normalize_heading_text("C#") == "csharp"

    def test_case_insensitive(self) -> None:
        assert self.tmpl._normalize_heading_text("CPP") == "cpp"

    def test_punctuation_stripped(self) -> None:
        result = self.tmpl._normalize_heading_text("A | B / C")
        assert result == "a b c"

    def test_extra_whitespace_collapsed(self) -> None:
        result = self.tmpl._normalize_heading_text("  Senior   Engineer  ")
        assert result == "senior engineer"


def test_header_divider_has_blank_line_before_resume_title() -> None:
    for template_class in (DefaultTemplate, ModernTemplate):
        css = template_class().get_css()
        normalized_css = "\n".join(line.lstrip() for line in css.splitlines())
        assert (
            ".header-divider { border: 0; border-top: 1px solid #000; margin: -1px 0 16px 0; }"
            in normalized_css
        )
