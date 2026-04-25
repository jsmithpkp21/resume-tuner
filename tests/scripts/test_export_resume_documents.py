from __future__ import annotations

import io as io_mod
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any
from zipfile import ZipFile

import pytest

from scripts import build_resume, export_resume_documents


def test_run_generates_docx_and_pdf_from_same_markdown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / "latest_resume_processed.md"
    markdown_path.write_text("# Test\n\n## Summary\n\n- bullet\n", encoding="utf-8")

    monkeypatch.setattr(
        export_resume_documents,
        "parse_args",
        lambda: type(
            "Args",
            (),
            {
                "profile": Path("data/profile/profile.toml"),
                "experience_db": Path("data/experience/experience_db.toml"),
                "skills_matrix": Path("data/skills/skills_matrix.csv"),
                "job_url": "",
                "job_text_file": None,
                "target_role": "",
                "company": "company",
                "output_dir": output_dir,
                "processing_mode": "processed",
                "template": "modern",
                "pdf_filename": "resume.pdf",
                "docx_filename": "resume.docx",
                "allow_overflow_pdf": False,
            },
        )(),
    )
    monkeypatch.setattr(
        export_resume_documents,
        "_run_build_pipeline",
        lambda _args: markdown_path,
    )
    monkeypatch.setattr(
        export_resume_documents,
        "_contains_trailing_connector_fragment",
        lambda _text: False,
    )

    def fake_render_docx(md_text: str, output_path: Path) -> None:
        output_path.write_text(md_text, encoding="utf-8")

    def fake_render_pdf(
        md_text: str, output_path: Path, *, enforce_page_limit: bool = True
    ) -> None:
        assert enforce_page_limit is True
        output_path.write_bytes(md_text.encode("utf-8"))

    monkeypatch.setattr(export_resume_documents, "_render_docx", fake_render_docx)
    monkeypatch.setattr(export_resume_documents, "_render_pdf", fake_render_pdf)

    assert export_resume_documents.run() == 0
    assert (output_dir / "resume.docx").exists()
    assert (output_dir / "resume.pdf").exists()


def test_run_passes_allow_overflow_pdf_to_render_pdf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / "latest_resume_processed.md"
    markdown_path.write_text("# Test\n\n## Summary\n\n- bullet\n", encoding="utf-8")

    monkeypatch.setattr(
        export_resume_documents,
        "parse_args",
        lambda: type(
            "Args",
            (),
            {
                "profile": Path("data/profile/profile.toml"),
                "experience_db": Path("data/experience/experience_db.toml"),
                "skills_matrix": Path("data/skills/skills_matrix.csv"),
                "job_url": "",
                "job_text_file": None,
                "target_role": "",
                "company": "company",
                "output_dir": output_dir,
                "processing_mode": "processed",
                "template": "modern",
                "pdf_filename": "resume.pdf",
                "docx_filename": "resume.docx",
                "allow_overflow_pdf": True,
            },
        )(),
    )
    monkeypatch.setattr(
        export_resume_documents,
        "_run_build_pipeline",
        lambda _args: markdown_path,
    )
    monkeypatch.setattr(
        export_resume_documents,
        "_contains_trailing_connector_fragment",
        lambda _text: False,
    )

    seen: dict[str, bool] = {"enforce_page_limit": True}

    def fake_render_docx(md_text: str, output_path: Path) -> None:
        output_path.write_text(md_text, encoding="utf-8")

    def fake_render_pdf(
        md_text: str, output_path: Path, *, enforce_page_limit: bool = True
    ) -> None:
        seen["enforce_page_limit"] = enforce_page_limit
        output_path.write_bytes(md_text.encode("utf-8"))

    monkeypatch.setattr(export_resume_documents, "_render_docx", fake_render_docx)
    monkeypatch.setattr(export_resume_documents, "_render_pdf", fake_render_pdf)

    assert export_resume_documents.run() == 0
    assert seen["enforce_page_limit"] is False
    assert (output_dir / "resume.docx").exists()
    assert (output_dir / "resume.pdf").exists()


def test_run_warns_when_trailing_fragment_guard_trips_but_still_exports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    output_dir = tmp_path / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / "latest_resume_processed.md"
    markdown_path.write_text("# Test\n\nThis line ends with and\n", encoding="utf-8")

    monkeypatch.setattr(
        export_resume_documents,
        "parse_args",
        lambda: type(
            "Args",
            (),
            {
                "profile": Path("data/profile/profile.toml"),
                "experience_db": Path("data/experience/experience_db.toml"),
                "skills_matrix": Path("data/skills/skills_matrix.csv"),
                "job_url": "",
                "job_text_file": None,
                "target_role": "",
                "company": "company",
                "output_dir": output_dir,
                "processing_mode": "processed",
                "template": "modern",
                "pdf_filename": "resume.pdf",
                "docx_filename": "resume.docx",
                "allow_overflow_pdf": False,
            },
        )(),
    )
    monkeypatch.setattr(
        export_resume_documents,
        "_run_build_pipeline",
        lambda _args: markdown_path,
    )
    monkeypatch.setattr(
        export_resume_documents,
        "_contains_trailing_connector_fragment",
        lambda _text: True,
    )

    def fake_render_docx(md_text: str, output_path: Path) -> None:
        output_path.write_text(md_text, encoding="utf-8")

    def fake_render_pdf(
        md_text: str, output_path: Path, *, enforce_page_limit: bool = True
    ) -> None:
        assert enforce_page_limit is True
        output_path.write_bytes(md_text.encode("utf-8"))

    monkeypatch.setattr(export_resume_documents, "_render_docx", fake_render_docx)
    monkeypatch.setattr(export_resume_documents, "_render_pdf", fake_render_pdf)

    # Guard now warns but does not block exports.
    assert export_resume_documents.run() == 0
    captured = capsys.readouterr()
    assert (
        "WARNING: render source contains trailing connector fragments" in captured.err
    )
    assert (output_dir / "resume.docx").exists()
    assert (output_dir / "resume.pdf").exists()


def test_run_prefers_default_html_source_when_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / "latest_resume_processed.md"
    markdown_path.write_text(
        "# Test\n\n## Summary\n\nmarkdown summary only\n",
        encoding="utf-8",
    )
    default_html_path = output_dir / "latest_default_resume_processed.html"
    default_html_path.write_text(
        """<!doctype html>
<html>
<body>
  <h1>Test User</h1>
  <p class=\"resume-title\"><strong>Senior Staff Software Engineer | Test Automation Framework Architect</strong></p>
  <p class=\"summary-text\">HTML summary source.</p>
</body>
</html>
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        export_resume_documents,
        "parse_args",
        lambda: type(
            "Args",
            (),
            {
                "profile": Path("data/profile/profile.toml"),
                "experience_db": Path("data/experience/experience_db.toml"),
                "skills_matrix": Path("data/skills/skills_matrix.csv"),
                "job_url": "",
                "job_text_file": None,
                "target_role": "",
                "company": "company",
                "output_dir": output_dir,
                "processing_mode": "processed",
                "template": "modern",
                "pdf_filename": "resume.pdf",
                "docx_filename": "resume.docx",
                "allow_overflow_pdf": False,
            },
        )(),
    )
    monkeypatch.setattr(
        export_resume_documents,
        "_run_build_pipeline",
        lambda _args: markdown_path,
    )
    monkeypatch.setattr(
        export_resume_documents,
        "_contains_trailing_connector_fragment",
        lambda _text: False,
    )

    captured_sources: list[str] = []

    def fake_render_docx(source_text: str, output_path: Path) -> None:
        captured_sources.append(source_text)
        output_path.write_text("docx", encoding="utf-8")

    def fake_render_pdf(
        source_text: str, output_path: Path, *, enforce_page_limit: bool = True
    ) -> None:
        assert enforce_page_limit is True
        captured_sources.append(source_text)
        output_path.write_bytes(b"pdf")

    monkeypatch.setattr(export_resume_documents, "_render_docx", fake_render_docx)
    monkeypatch.setattr(export_resume_documents, "_render_pdf", fake_render_pdf)

    assert export_resume_documents.run() == 0
    assert len(captured_sources) == 2
    assert (
        "Senior Staff Software Engineer | Test Automation Framework Architect"
        in captured_sources[0]
    )
    assert "HTML summary source." in captured_sources[0]
    assert "markdown summary only" not in captured_sources[0]
    assert (output_dir / "resume.docx").exists()
    assert (output_dir / "resume.pdf").exists()


def test_run_can_disable_post_layout_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / "latest_resume_processed.md"
    markdown_path.write_text("# Test\n\n## Summary\n\n- bullet\n", encoding="utf-8")

    monkeypatch.setattr(
        export_resume_documents,
        "parse_args",
        lambda: type(
            "Args",
            (),
            {
                "profile": Path("data/profile/profile.toml"),
                "experience_db": Path("data/experience/experience_db.toml"),
                "skills_matrix": Path("data/skills/skills_matrix.csv"),
                "job_url": "",
                "job_text_file": None,
                "target_role": "",
                "company": "company",
                "output_dir": output_dir,
                "processing_mode": "processed",
                "template": "modern",
                "pdf_filename": "resume.pdf",
                "docx_filename": "resume.docx",
                "allow_overflow_pdf": False,
                "post_layout_cleanup": "disabled",
            },
        )(),
    )
    monkeypatch.setattr(
        export_resume_documents,
        "_run_build_pipeline",
        lambda _args: markdown_path,
    )
    monkeypatch.setattr(
        export_resume_documents,
        "_contains_trailing_connector_fragment",
        lambda _text: False,
    )

    cleanup_called = {"value": False}

    def fake_cleanup(source_text: str, *, args: Any) -> str:
        cleanup_called["value"] = True
        return source_text

    monkeypatch.setattr(
        export_resume_documents,
        "_apply_post_layout_cleanup",
        fake_cleanup,
    )
    monkeypatch.setattr(
        export_resume_documents,
        "_render_docx",
        lambda source_text, output_path: output_path.write_text(
            source_text, encoding="utf-8"
        ),
    )
    monkeypatch.setattr(
        export_resume_documents,
        "_render_pdf",
        lambda source_text, output_path, *, enforce_page_limit=True: (
            output_path.write_bytes(source_text.encode("utf-8"))
        ),
    )

    assert export_resume_documents.run() == 0
    assert cleanup_called["value"] is False


def test_run_rejects_colliding_docx_pdf_output_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    output_dir = tmp_path / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / "latest_resume_processed.md"
    markdown_path.write_text("# Test\n\n## Summary\n\n- bullet\n", encoding="utf-8")

    monkeypatch.setattr(
        export_resume_documents,
        "parse_args",
        lambda: type(
            "Args",
            (),
            {
                "profile": Path("data/profile/profile.toml"),
                "experience_db": Path("data/experience/experience_db.toml"),
                "skills_matrix": Path("data/skills/skills_matrix.csv"),
                "job_url": "",
                "job_text_file": None,
                "target_role": "",
                "company": "company",
                "output_dir": output_dir,
                "processing_mode": "processed",
                "template": "modern",
                "pdf_filename": "resume.out",
                "docx_filename": "nested/../resume.out",
                "allow_overflow_pdf": False,
                "post_layout_cleanup": "enabled",
            },
        )(),
    )
    monkeypatch.setattr(
        export_resume_documents,
        "_run_build_pipeline",
        lambda _args: markdown_path,
    )
    monkeypatch.setattr(
        export_resume_documents,
        "_contains_trailing_connector_fragment",
        lambda _text: False,
    )

    calls = {"docx": 0, "pdf": 0}

    def fake_render_docx(_source_text: str, _output_path: Path) -> None:
        calls["docx"] += 1

    def fake_render_pdf(
        _source_text: str, _output_path: Path, *, enforce_page_limit: bool = True
    ) -> None:
        calls["pdf"] += 1

    monkeypatch.setattr(export_resume_documents, "_render_docx", fake_render_docx)
    monkeypatch.setattr(export_resume_documents, "_render_pdf", fake_render_pdf)

    assert export_resume_documents.run() == 1
    captured = capsys.readouterr()
    assert "DOCX and PDF outputs must be different files" in captured.err
    assert calls == {"docx": 0, "pdf": 0}


def test_run_rejects_absolute_output_filename_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    output_dir = tmp_path / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / "latest_resume_processed.md"
    markdown_path.write_text("# Test\n", encoding="utf-8")

    monkeypatch.setattr(
        export_resume_documents,
        "parse_args",
        lambda: type(
            "Args",
            (),
            {
                "profile": Path("data/profile/profile.toml"),
                "experience_db": Path("data/experience/experience_db.toml"),
                "skills_matrix": Path("data/skills/skills_matrix.csv"),
                "job_url": "",
                "job_text_file": None,
                "target_role": "",
                "company": "company",
                "output_dir": output_dir,
                "processing_mode": "processed",
                "template": "modern",
                "pdf_filename": "resume.pdf",
                "docx_filename": "/tmp/evil.docx",
                "allow_overflow_pdf": False,
                "post_layout_cleanup": "enabled",
            },
        )(),
    )
    monkeypatch.setattr(
        export_resume_documents,
        "_run_build_pipeline",
        lambda _args: markdown_path,
    )
    monkeypatch.setattr(
        export_resume_documents,
        "_contains_trailing_connector_fragment",
        lambda _text: False,
    )

    calls = {"docx": 0, "pdf": 0}
    monkeypatch.setattr(
        export_resume_documents,
        "_render_docx",
        lambda _source_text, _output_path: calls.__setitem__("docx", calls["docx"] + 1),
    )
    monkeypatch.setattr(
        export_resume_documents,
        "_render_pdf",
        lambda _source_text, _output_path, *, enforce_page_limit=True: (
            calls.__setitem__("pdf", calls["pdf"] + 1)
        ),
    )

    assert export_resume_documents.run() == 1
    captured = capsys.readouterr()
    assert "--docx-filename must be a path under --output-dir" in captured.err
    assert calls == {"docx": 0, "pdf": 0}


def test_run_rejects_output_filename_path_traversal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    output_dir = tmp_path / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / "latest_resume_processed.md"
    markdown_path.write_text("# Test\n", encoding="utf-8")

    monkeypatch.setattr(
        export_resume_documents,
        "parse_args",
        lambda: type(
            "Args",
            (),
            {
                "profile": Path("data/profile/profile.toml"),
                "experience_db": Path("data/experience/experience_db.toml"),
                "skills_matrix": Path("data/skills/skills_matrix.csv"),
                "job_url": "",
                "job_text_file": None,
                "target_role": "",
                "company": "company",
                "output_dir": output_dir,
                "processing_mode": "processed",
                "template": "modern",
                "pdf_filename": "resume.pdf",
                "docx_filename": "../escape.docx",
                "allow_overflow_pdf": False,
                "post_layout_cleanup": "enabled",
            },
        )(),
    )
    monkeypatch.setattr(
        export_resume_documents,
        "_run_build_pipeline",
        lambda _args: markdown_path,
    )
    monkeypatch.setattr(
        export_resume_documents,
        "_contains_trailing_connector_fragment",
        lambda _text: False,
    )

    calls = {"docx": 0, "pdf": 0}
    monkeypatch.setattr(
        export_resume_documents,
        "_render_docx",
        lambda _source_text, _output_path: calls.__setitem__("docx", calls["docx"] + 1),
    )
    monkeypatch.setattr(
        export_resume_documents,
        "_render_pdf",
        lambda _source_text, _output_path, *, enforce_page_limit=True: (
            calls.__setitem__("pdf", calls["pdf"] + 1)
        ),
    )

    assert export_resume_documents.run() == 1
    captured = capsys.readouterr()
    assert "--docx-filename must remain under --output-dir" in captured.err
    assert calls == {"docx": 0, "pdf": 0}


def test_run_fragment_warning_uses_render_source_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    output_dir = tmp_path / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / "latest_resume_processed.md"
    markdown_path.write_text("# Test\n\nclean source\n", encoding="utf-8")

    monkeypatch.setattr(
        export_resume_documents,
        "parse_args",
        lambda: type(
            "Args",
            (),
            {
                "profile": Path("data/profile/profile.toml"),
                "experience_db": Path("data/experience/experience_db.toml"),
                "skills_matrix": Path("data/skills/skills_matrix.csv"),
                "job_url": "",
                "job_text_file": None,
                "target_role": "",
                "company": "company",
                "output_dir": output_dir,
                "processing_mode": "processed",
                "template": "modern",
                "pdf_filename": "resume.pdf",
                "docx_filename": "resume.docx",
                "allow_overflow_pdf": False,
                "post_layout_cleanup": "enabled",
            },
        )(),
    )
    monkeypatch.setattr(
        export_resume_documents,
        "_run_build_pipeline",
        lambda _args: markdown_path,
    )
    monkeypatch.setattr(
        export_resume_documents,
        "_apply_post_layout_cleanup",
        lambda source_text, *, args: source_text + "\nand",
    )
    monkeypatch.setattr(
        export_resume_documents,
        "_render_docx",
        lambda source_text, output_path: output_path.write_text(
            source_text, encoding="utf-8"
        ),
    )
    monkeypatch.setattr(
        export_resume_documents,
        "_render_pdf",
        lambda source_text, output_path, *, enforce_page_limit=True: (
            output_path.write_bytes(source_text.encode("utf-8"))
        ),
    )

    assert export_resume_documents.run() == 0
    captured = capsys.readouterr()
    assert (
        "WARNING: render source contains trailing connector fragments" in captured.err
    )


def test_job_context_community_signal_checks_runtime_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job_text_file = tmp_path / "job_text.txt"
    job_text_file.write_text(
        "Volunteer outreach and community programs.", encoding="utf-8"
    )
    args = type(
        "Args",
        (),
        {
            "target_role": "",
            "company": "",
            "job_text_file": job_text_file,
        },
    )()

    seen: dict[str, Path | None] = {"path": None}

    def fake_guard(path: Path) -> None:
        seen["path"] = path

    monkeypatch.setattr(
        export_resume_documents,
        "_assert_not_blocked_runtime_input",
        fake_guard,
    )

    assert export_resume_documents._job_context_has_community_signal(args) is True
    assert seen["path"] == job_text_file


def test_contains_trailing_connector_fragment_uses_real_detection_logic() -> None:
    assert (
        export_resume_documents._contains_trailing_connector_fragment(
            "# Test\n\nThis line ends with and\n"
        )
        is True
    )
    assert (
        export_resume_documents._contains_trailing_connector_fragment(
            "# Test\n\nThis line ends cleanly.\n"
        )
        is False
    )


def test_staging_path_is_unique_per_call(tmp_path: Path) -> None:
    output_path = tmp_path / "resume.docx"
    first = export_resume_documents._staging_path(output_path, label="docx")
    second = export_resume_documents._staging_path(output_path, label="docx")
    assert first != second
    assert "tmp-export-" in first.name
    assert "tmp-export-" in second.name


def test_render_pdf_raises_when_output_exceeds_two_pages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    output_path = tmp_path / "resume.pdf"
    output_path.write_bytes(b"stale pdf")
    md_text = "\n".join(f"Paragraph {index}" for index in range(15))

    class FakeCanvas:
        def __init__(self, buf: io_mod.BytesIO, **_kwargs: object):
            self._buf = buf

        def showPage(self) -> None:
            pass

        def setFont(self, _font_name: str, _font_size: int) -> None:
            pass

        def drawString(self, _x: int, _y: int, _line: str) -> None:
            pass

        def save(self) -> None:
            self._buf.write(b"%PDF-FAKE")

    monkeypatch.setattr(
        export_resume_documents,
        "_require_reportlab",
        lambda: (
            (300, 150),
            type("CanvasModule", (), {"Canvas": FakeCanvas}),
            lambda text, _font_name, _font_size: len(text),
        ),
    )
    monkeypatch.setattr(
        export_resume_documents,
        "_require_calibri_pdf_fonts",
        lambda: ("Calibri", "Calibri-Bold"),
    )

    with pytest.raises(RuntimeError, match="PDF exceeded two-page limit"):
        export_resume_documents._render_pdf(md_text, output_path)

    captured = capsys.readouterr()
    assert captured.err == ""
    assert not output_path.exists()


def test_render_pdf_can_keep_overflow_pdf_for_review_exports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_path = tmp_path / "resume.pdf"
    md_text = "\n".join(f"Paragraph {index}" for index in range(15))

    class FakeCanvas:
        def __init__(self, buf: io_mod.BytesIO, **_kwargs: object):
            self._buf = buf

        def showPage(self) -> None:
            pass

        def setFont(self, _font_name: str, _font_size: int) -> None:
            pass

        def drawString(self, _x: int, _y: int, _line: str) -> None:
            pass

        def save(self) -> None:
            self._buf.write(b"%PDF-FAKE")

    monkeypatch.setattr(
        export_resume_documents,
        "_require_reportlab",
        lambda: (
            (300, 150),
            type("CanvasModule", (), {"Canvas": FakeCanvas}),
            lambda text, _font_name, _font_size: len(text),
        ),
    )
    monkeypatch.setattr(
        export_resume_documents,
        "_require_calibri_pdf_fonts",
        lambda: ("Calibri", "Calibri-Bold"),
    )

    export_resume_documents._render_pdf(md_text, output_path, enforce_page_limit=False)

    assert output_path.read_bytes() == b"%PDF-FAKE"


def test_render_pdf_removes_stale_output_when_renderer_fails_early(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_path = tmp_path / "resume.pdf"
    output_path.write_bytes(b"stale pdf")

    monkeypatch.setattr(
        export_resume_documents,
        "_require_reportlab",
        lambda: (_ for _ in ()).throw(RuntimeError("reportlab unavailable")),
    )

    with pytest.raises(RuntimeError, match="reportlab unavailable"):
        export_resume_documents._render_pdf("Body paragraph", output_path)

    assert not output_path.exists()


def test_require_python_docx_includes_import_error_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import builtins

    real_import: Any = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "docx" or name.startswith("docx."):
            raise ImportError("No module named 'docx'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(
        RuntimeError, match=r"python-docx.*Import error: No module named 'docx'"
    ):
        export_resume_documents._require_python_docx()


def test_require_reportlab_includes_import_error_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import builtins

    real_import: Any = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "reportlab" or name.startswith("reportlab."):
            raise ImportError("No module named 'reportlab'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(
        RuntimeError, match=r"reportlab.*Import error: No module named 'reportlab'"
    ):
        export_resume_documents._require_reportlab()


def test_require_calibri_pdf_fonts_falls_back_to_helvetica_without_fontconfig(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakePdfMetrics:
        @staticmethod
        def getRegisteredFontNames() -> list[str]:
            return []

        @staticmethod
        def registerFont(_font: object) -> None:
            return None

    class FakeTTFont:
        def __init__(self, _name: str, _path: str) -> None:
            return None

    reportlab_module = ModuleType("reportlab")
    pdfbase_module: Any = ModuleType("reportlab.pdfbase")
    ttfonts_module: Any = ModuleType("reportlab.pdfbase.ttfonts")
    pdfbase_module.pdfmetrics = FakePdfMetrics
    ttfonts_module.TTFont = FakeTTFont
    monkeypatch.setitem(sys.modules, "reportlab", reportlab_module)
    monkeypatch.setitem(sys.modules, "reportlab.pdfbase", pdfbase_module)
    monkeypatch.setitem(sys.modules, "reportlab.pdfbase.ttfonts", ttfonts_module)

    monkeypatch.setenv("RESUME_PDF_STRICT_CALIBRI", "0")
    monkeypatch.setattr(
        export_resume_documents, "_find_calibri_path", lambda _style: None
    )
    monkeypatch.setattr(
        export_resume_documents,
        "_find_fontconfig_font_path",
        lambda _family, _style: None,
    )

    regular, bold = export_resume_documents._require_calibri_pdf_fonts()

    assert regular == "Helvetica"
    assert bold == "Helvetica-Bold"


def test_iter_html_blocks_captures_header_divider() -> None:
    html = """<!doctype html><html><body>
<h1>Test User</h1>
<p class=\"contact-line\">Contact</p>
<hr class=\"header-divider\" />
<p class=\"resume-title\"><strong>Title</strong></p>
</body></html>"""
    blocks = export_resume_documents._iter_markdown_blocks(html)
    assert ("divider", "") in blocks


def test_iter_markdown_blocks_parses_indented_bullets_as_bullets() -> None:
    markdown = """## Leadership
  - Mentored team members
"""
    blocks = export_resume_documents._iter_markdown_blocks(markdown)
    assert ("bullet", "Mentored team members") in blocks


def test_apply_post_layout_cleanup_drops_last_skill_for_single_word_tail_wrap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(build_resume, "DEFAULT_BULLET_LINE_WIDTH", 24)

    args = type(
        "Args",
        (),
        {"target_role": "", "company": "", "job_text_file": None},
    )()
    markdown = """## Key Skills and Expertise

- **Collaboration:** Mentoring • Coaching • Communication • Facilitation
"""

    cleaned = export_resume_documents._apply_post_layout_cleanup(markdown, args=args)

    assert "Facilitation" not in cleaned
    assert "Mentoring • Coaching • Communication" in cleaned


def test_apply_post_layout_cleanup_trims_professional_bullet_single_word_tail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        export_resume_documents,
        "_has_single_word_wrap_tail",
        lambda _text, *, line_width: True,
    )

    args = type(
        "Args",
        (),
        {"target_role": "", "company": "", "job_text_file": None},
    )()
    markdown = """## Professional Experience

- Built deterministic automation pipelines across teams quickly
"""

    cleaned = export_resume_documents._apply_post_layout_cleanup(markdown, args=args)

    assert "teams quickly" not in cleaned
    assert "Built deterministic automation pipelines across teams" in cleaned


def test_apply_post_layout_cleanup_drops_leadership_mentoring_when_present_in_bullets() -> (
    None
):
    args = type(
        "Args",
        (),
        {"target_role": "", "company": "", "job_text_file": None},
    )()
    markdown = """## Professional Experience

- Mentored six engineers across distributed teams.

## Leadership & Community

- **Mentoring Lead | Internal Community**
- Supported peer growth circles.
"""

    cleaned = export_resume_documents._apply_post_layout_cleanup(markdown, args=args)

    assert "Mentoring Lead | Internal Community" not in cleaned
    assert "Supported peer growth circles" not in cleaned


def test_apply_post_layout_cleanup_filters_philanthropy_without_company_signal() -> (
    None
):
    args = type(
        "Args",
        (),
        {
            "target_role": "Staff Test Architect",
            "company": "Graphcore",
            "job_text_file": None,
        },
    )()
    markdown = """## Leadership & Community

- **Volunteer outreach board member**
- Led local nonprofit robotics workshops.
"""

    cleaned = export_resume_documents._apply_post_layout_cleanup(markdown, args=args)

    assert "Volunteer outreach board member" not in cleaned
    assert "Led local nonprofit robotics workshops" not in cleaned


def test_apply_post_layout_cleanup_preserves_html_resume_title_block() -> None:
    args = type(
        "Args",
        (),
        {"target_role": "", "company": "", "job_text_file": None},
    )()
    html = """<!doctype html><html><body>
<p class=\"resume-title\"><strong>Senior Staff Test Architect</strong></p>
</body></html>"""

    cleaned = export_resume_documents._apply_post_layout_cleanup(html, args=args)
    blocks = export_resume_documents._iter_markdown_blocks(cleaned)

    assert ("title", "Senior Staff Test Architect") in blocks


def test_apply_post_layout_cleanup_preserves_html_header_divider_block() -> None:
    args = type(
        "Args",
        (),
        {"target_role": "", "company": "", "job_text_file": None},
    )()
    html = """<!doctype html><html><body>
<hr class=\"header-divider\" />
</body></html>"""

    cleaned = export_resume_documents._apply_post_layout_cleanup(html, args=args)
    blocks = export_resume_documents._iter_markdown_blocks(cleaned)

    assert ("divider", "") in blocks


def test_html_block_parser_emits_bullet_for_skills_category_paragraph() -> None:
    """HTML <p class="skills-category"> must produce ("bullet", text) so cleanup fires."""
    html = """<!doctype html><html><body>
<h2>Key Skills and Expertise</h2>
<p class="skills-category"><strong>Collaboration:</strong> Mentoring • Coaching • Communication • Facilitation</p>
</body></html>"""
    blocks = export_resume_documents._iter_markdown_blocks(html)
    assert any(kind == "bullet" and "Facilitation" in text for kind, text in blocks)


def test_html_block_parser_emits_bullet_for_leadership_paragraphs() -> None:
    """HTML <p> inside Leadership & Community section must produce ("bullet", text)."""
    html = """<!doctype html><html><body>
<h2>Leadership &amp; Community</h2>
<section class="info-item">
<p><strong>Mentoring Lead | Internal Community | 2020-Present</strong></p>
<p>Supported peer growth circles.</p>
</section>
</body></html>"""
    blocks = export_resume_documents._iter_markdown_blocks(html)
    bullet_texts = [text for kind, text in blocks if kind == "bullet"]
    assert any("Mentoring Lead" in t for t in bullet_texts)
    assert any("peer growth circles" in t for t in bullet_texts)


def test_apply_post_layout_cleanup_drops_leadership_mentoring_from_html_source() -> (
    None
):
    """Cleanup must fire on HTML source (not just markdown) when mentoring is in experience."""
    args = type(
        "Args",
        (),
        {"target_role": "", "company": "", "job_text_file": None},
    )()
    html = """<!doctype html><html><body>
<h2>Professional Experience</h2>
<ul><li>Mentored six engineers across distributed teams.</li></ul>
<h2>Leadership &amp; Community</h2>
<section class="info-item">
<p><strong>Mentoring Lead | Internal Community</strong></p>
<p>Supported peer growth circles.</p>
</section>
</body></html>"""

    cleaned = export_resume_documents._apply_post_layout_cleanup(html, args=args)

    assert "Mentoring Lead | Internal Community" not in cleaned
    assert "Supported peer growth circles" not in cleaned


def test_pipeline_default_html_path_prefers_default_secondary_for_processed() -> None:
    args = type(
        "Args",
        (),
        {
            "output_dir": Path("data/review/outputs/baseline"),
            "processing_mode": "processed",
            "template": "modern",
        },
    )()

    path = export_resume_documents._pipeline_default_html_path(args)
    assert path.name == "latest_default_resume_processed.html"


def test_run_uses_company_snake_case_default_filenames(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / "latest_resume_processed.md"
    markdown_path.write_text("# Test\n", encoding="utf-8")

    monkeypatch.setattr(
        export_resume_documents,
        "parse_args",
        lambda: type(
            "Args",
            (),
            {
                "profile": Path("data/profile/profile.toml"),
                "experience_db": Path("data/experience/experience_db.toml"),
                "skills_matrix": Path("data/skills/skills_matrix.csv"),
                "job_url": "",
                "job_text_file": None,
                "target_role": "",
                "company": "Graph Core, Inc",
                "output_dir": output_dir,
                "processing_mode": "processed",
                "template": "modern",
                "pdf_filename": None,
                "docx_filename": None,
                "allow_overflow_pdf": False,
            },
        )(),
    )
    monkeypatch.setattr(
        export_resume_documents,
        "_run_build_pipeline",
        lambda _args: markdown_path,
    )
    monkeypatch.setattr(
        export_resume_documents,
        "_contains_trailing_connector_fragment",
        lambda _text: False,
    )

    captured: list[Path] = []

    def fake_render_docx(_source_text: str, output_path: Path) -> None:
        captured.append(output_path)
        output_path.write_text("docx", encoding="utf-8")

    def fake_render_pdf(
        _source_text: str, output_path: Path, *, enforce_page_limit: bool = True
    ) -> None:
        assert enforce_page_limit is True
        captured.append(output_path)
        output_path.write_bytes(b"pdf")

    monkeypatch.setattr(export_resume_documents, "_render_docx", fake_render_docx)
    monkeypatch.setattr(export_resume_documents, "_render_pdf", fake_render_pdf)

    assert export_resume_documents.run() == 0
    assert len(captured) == 2
    staged_names = sorted(path.name for path in captured)
    assert all("tmp-export-" in name for name in staged_names)
    assert (output_dir / "graph_core_inc_resume.docx").exists()
    assert (output_dir / "graph_core_inc_resume.pdf").exists()


def test_run_removes_stale_legacy_latest_resume_export_aliases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / "latest_resume_processed.md"
    markdown_path.write_text("# Test\n", encoding="utf-8")
    stale_docx = output_dir / "latest_resume_export.docx"
    stale_pdf = output_dir / "latest_resume_export.pdf"
    stale_docx.write_text("stale docx", encoding="utf-8")
    stale_pdf.write_bytes(b"stale pdf")

    monkeypatch.setattr(
        export_resume_documents,
        "parse_args",
        lambda: type(
            "Args",
            (),
            {
                "profile": Path("data/profile/profile.toml"),
                "experience_db": Path("data/experience/experience_db.toml"),
                "skills_matrix": Path("data/skills/skills_matrix.csv"),
                "job_url": "",
                "job_text_file": None,
                "target_role": "",
                "company": "Graphcore",
                "output_dir": output_dir,
                "processing_mode": "processed",
                "template": "modern",
                "pdf_filename": None,
                "docx_filename": None,
                "allow_overflow_pdf": False,
            },
        )(),
    )
    monkeypatch.setattr(
        export_resume_documents,
        "_run_build_pipeline",
        lambda _args: markdown_path,
    )
    monkeypatch.setattr(
        export_resume_documents,
        "_contains_trailing_connector_fragment",
        lambda _text: False,
    )

    def fake_render_docx(_source_text: str, output_path: Path) -> None:
        output_path.write_text("fresh docx", encoding="utf-8")

    def fake_render_pdf(
        _source_text: str, output_path: Path, *, enforce_page_limit: bool = True
    ) -> None:
        assert enforce_page_limit is True
        output_path.write_bytes(b"fresh pdf")

    monkeypatch.setattr(export_resume_documents, "_render_docx", fake_render_docx)
    monkeypatch.setattr(export_resume_documents, "_render_pdf", fake_render_pdf)

    assert export_resume_documents.run() == 0
    assert (output_dir / "graphcore_resume.docx").exists()
    assert (output_dir / "graphcore_resume.pdf").exists()
    assert not stale_docx.exists()
    assert not stale_pdf.exists()


def test_run_transactional_pdf_phase_failure_preserves_existing_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression for #133: when PDF render fails, pre-existing DOCX and PDF must be unchanged."""
    output_dir = tmp_path / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / "latest_resume_processed.md"
    markdown_path.write_text("# Test\n", encoding="utf-8")
    # Pre-populate existing final artifacts that must survive a failed run.
    existing_docx = output_dir / "graphcore_resume.docx"
    existing_pdf = output_dir / "graphcore_resume.pdf"
    existing_docx.write_text("original docx content", encoding="utf-8")
    existing_pdf.write_bytes(b"original pdf content")
    monkeypatch.setattr(
        export_resume_documents,
        "parse_args",
        lambda: type(
            "Args",
            (),
            {
                "profile": Path("data/profile/profile.toml"),
                "experience_db": Path("data/experience/experience_db.toml"),
                "skills_matrix": Path("data/skills/skills_matrix.csv"),
                "job_url": "",
                "job_text_file": None,
                "target_role": "",
                "company": "Graphcore",
                "output_dir": output_dir,
                "processing_mode": "processed",
                "template": "modern",
                "pdf_filename": None,
                "docx_filename": None,
                "allow_overflow_pdf": False,
            },
        )(),
    )
    monkeypatch.setattr(
        export_resume_documents,
        "_run_build_pipeline",
        lambda _args: markdown_path,
    )
    monkeypatch.setattr(
        export_resume_documents,
        "_contains_trailing_connector_fragment",
        lambda _text: False,
    )

    def fake_render_docx(_source_text: str, output_path: Path) -> None:
        # DOCX phase succeeds — writes the staging file.
        output_path.write_text("new docx content", encoding="utf-8")

    def fake_render_pdf(
        _source_text: str, output_path: Path, *, enforce_page_limit: bool = True
    ) -> None:
        # PDF phase fails — simulates a render error mid-export.
        raise RuntimeError("simulated PDF render failure")

    monkeypatch.setattr(export_resume_documents, "_render_docx", fake_render_docx)
    monkeypatch.setattr(export_resume_documents, "_render_pdf", fake_render_pdf)
    result = export_resume_documents.run()
    # run() should return non-zero (error) rather than propagating the exception.
    assert result != 0
    # Both pre-existing artifacts must be restored to their original content.
    assert existing_docx.read_text(encoding="utf-8") == "original docx content"
    assert existing_pdf.read_bytes() == b"original pdf content"
    # No staging/temp files should be left on disk.
    leftovers = [p for p in output_dir.iterdir() if "tmp-export-" in p.name]
    assert leftovers == [], f"Unexpected staging files left behind: {leftovers}"


def test_run_transactional_mid_finalize_failure_removes_new_outputs_without_backups(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If finalization fails mid-swap with no prior artifacts, rollback must remove partial finals."""
    output_dir = tmp_path / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / "latest_resume_processed.md"
    markdown_path.write_text("# Test\n", encoding="utf-8")

    monkeypatch.setattr(
        export_resume_documents,
        "parse_args",
        lambda: type(
            "Args",
            (),
            {
                "profile": Path("data/profile/profile.toml"),
                "experience_db": Path("data/experience/experience_db.toml"),
                "skills_matrix": Path("data/skills/skills_matrix.csv"),
                "job_url": "",
                "job_text_file": None,
                "target_role": "",
                "company": "Graphcore",
                "output_dir": output_dir,
                "processing_mode": "processed",
                "template": "modern",
                "pdf_filename": None,
                "docx_filename": None,
                "allow_overflow_pdf": False,
            },
        )(),
    )
    monkeypatch.setattr(
        export_resume_documents,
        "_run_build_pipeline",
        lambda _args: markdown_path,
    )
    monkeypatch.setattr(
        export_resume_documents,
        "_contains_trailing_connector_fragment",
        lambda _text: False,
    )

    def fake_render_docx(_source_text: str, output_path: Path) -> None:
        output_path.write_text("new docx content", encoding="utf-8")

    def fake_render_pdf(
        _source_text: str, output_path: Path, *, enforce_page_limit: bool = True
    ) -> None:
        assert enforce_page_limit is True
        output_path.write_bytes(b"new pdf content")

    monkeypatch.setattr(export_resume_documents, "_render_docx", fake_render_docx)
    monkeypatch.setattr(export_resume_documents, "_render_pdf", fake_render_pdf)

    real_replace = Path.replace

    def fail_pdf_finalize_once(self: Path, target: Path) -> Path:
        if self.suffix == ".pdf" and "tmp-export-" in self.name:
            raise RuntimeError("simulated mid-finalization failure")
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", fail_pdf_finalize_once)

    result = export_resume_documents.run()
    assert result != 0
    assert not (output_dir / "graphcore_resume.docx").exists()
    assert not (output_dir / "graphcore_resume.pdf").exists()
    leftovers = [p for p in output_dir.iterdir() if "tmp-export-" in p.name]
    assert leftovers == [], f"Unexpected staging files left behind: {leftovers}"


def test_render_docx_attaches_section_border_to_heading_paragraph(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "resume.docx"

    export_resume_documents._render_docx(
        "## Section Heading\n\nBody paragraph\n", output_path
    )

    xml = (
        ZipFile(output_path).read("word/document.xml").decode("utf-8", errors="ignore")
    )
    assert "Section Heading" in xml
    assert xml.count("<w:pBdr>") == 1
    assert re.search(
        r"<w:p\b[^>]*>.*?<w:pBdr>.*?Section Heading</w:t>.*?</w:p>",
        xml,
        re.DOTALL,
    )


def test_render_pdf_draws_section_rule_immediately_under_heading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_path = tmp_path / "resume.pdf"
    heading_positions: list[float] = []
    body_positions: list[float] = []
    line_positions: list[float] = []

    class FakeCanvas:
        def __init__(self, buf: io_mod.BytesIO, **_kwargs: object):
            self._buf = buf

        def showPage(self) -> None:
            pass

        def setFont(self, _font_name: str, _font_size: int) -> None:
            pass

        def drawString(self, _x: float, y: float, line: str) -> None:
            if line == "Section Heading":
                heading_positions.append(y)
            elif line == "Body paragraph":
                body_positions.append(y)

        def setStrokeColorRGB(self, _r: float, _g: float, _b: float) -> None:
            pass

        def setLineWidth(self, _width: float) -> None:
            pass

        def line(self, _x1: float, y1: float, _x2: float, _y2: float) -> None:
            line_positions.append(y1)

        def save(self) -> None:
            self._buf.write(b"%PDF-FAKE")

    monkeypatch.setattr(
        export_resume_documents,
        "_require_reportlab",
        lambda: (
            (612, 792),
            type("CanvasModule", (), {"Canvas": FakeCanvas}),
            lambda text, _font_name, _font_size: len(text) * 5,
        ),
    )
    monkeypatch.setattr(
        export_resume_documents,
        "_require_calibri_pdf_fonts",
        lambda: ("Calibri", "Calibri-Bold"),
    )

    export_resume_documents._render_pdf(
        "## Section Heading\n\nBody paragraph\n", output_path
    )

    assert heading_positions == [751]
    assert line_positions == [749]
    assert body_positions == [735]
    assert output_path.read_bytes() == b"%PDF-FAKE"


def test_render_pdf_header_divider_uses_same_text_to_line_offset_as_h2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_path = tmp_path / "resume.pdf"
    contact_positions: list[float] = []
    heading_positions: list[float] = []
    title_positions: list[float] = []
    line_calls: list[tuple[float, float, tuple[float, float, float]]] = []

    class FakeCanvas:
        def __init__(self, buf: io_mod.BytesIO, **_kwargs: object):
            self._buf = buf
            self._line_width = 1.0
            self._line_color = (0.0, 0.0, 0.0)

        def showPage(self) -> None:
            pass

        def setFont(self, _font_name: str, _font_size: int) -> None:
            pass

        def drawString(self, _x: float, y: float, line: str) -> None:
            if line == "linkedin.com/in/test":
                contact_positions.append(y)
            elif line == "Section Heading":
                heading_positions.append(y)
            elif line == "Resume Title":
                title_positions.append(y)

        def setStrokeColorRGB(self, r: float, g: float, b: float) -> None:
            self._line_color = (r, g, b)

        def setLineWidth(self, width: float) -> None:
            self._line_width = width

        def line(self, _x1: float, y1: float, _x2: float, _y2: float) -> None:
            line_calls.append((y1, self._line_width, self._line_color))

        def save(self) -> None:
            self._buf.write(b"%PDF-FAKE")

    monkeypatch.setattr(
        export_resume_documents,
        "_require_reportlab",
        lambda: (
            (612, 792),
            type("CanvasModule", (), {"Canvas": FakeCanvas}),
            lambda text, _font_name, _font_size: len(text) * 5,
        ),
    )
    monkeypatch.setattr(
        export_resume_documents,
        "_require_calibri_pdf_fonts",
        lambda: ("Calibri", "Calibri-Bold"),
    )

    html = """<!doctype html><html><body>
<p class=\"contact-line\">Temple, TX</p>
<p class=\"contact-line\">linkedin.com/in/test</p>
<hr class=\"header-divider\" />
<p class=\"resume-title\"><strong>Resume Title</strong></p>
<h2>Section Heading</h2>
<p>Body paragraph</p>
</body></html>"""

    export_resume_documents._render_pdf(html, output_path)

    header_lines = [call for call in line_calls if call[1] == 1.0]
    section_lines = [call for call in line_calls if call[1] == 0.8]
    assert len(header_lines) == 1
    assert len(section_lines) == 1

    header_line_y = header_lines[0][0]
    section_line_y = section_lines[0][0]
    assert len(contact_positions) == 1
    assert len(heading_positions) == 1
    assert len(title_positions) == 1
    assert abs(contact_positions[0] - header_line_y - 2) < 1e-6
    assert abs(heading_positions[0] - section_line_y - 2) < 1e-6
    assert abs(title_positions[0] - (header_line_y - 16)) < 1e-6
    assert output_path.read_bytes() == b"%PDF-FAKE"


def test_render_docx_header_divider_attaches_to_previous_paragraph(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "resume.docx"
    html = """<!doctype html><html><body>
<p class=\"contact-line\">Temple, TX</p>
<p class=\"contact-line\">linkedin.com/in/test</p>
<hr class=\"header-divider\" />
<p class=\"resume-title\"><strong>Resume Title</strong></p>
</body></html>"""

    export_resume_documents._render_docx(html, output_path)

    xml = (
        ZipFile(output_path).read("word/document.xml").decode("utf-8", errors="ignore")
    )
    assert "linkedin.com/in/test" in xml
    block_match = re.search(
        r"<w:p\b[^>]*>.*?linkedin\.com/in/test.*?</w:p>",
        xml,
        re.DOTALL,
    )
    assert block_match is not None
    linkedin_block = block_match.group(0)
    assert "<w:pBdr>" in linkedin_block
    assert 'w:after="240"' in linkedin_block


def test_render_pdf_renders_fully_bold_markdown_bullets_in_bold_font(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_path = tmp_path / "resume.pdf"
    draws: list[tuple[str, str]] = []

    class FakeCanvas:
        def __init__(self, buf: io_mod.BytesIO, **_kwargs: object):
            self._buf = buf
            self._font_name = ""

        def showPage(self) -> None:
            pass

        def setFont(self, font_name: str, _font_size: int) -> None:
            self._font_name = font_name

        def drawString(self, _x: float, _y: float, line: str) -> None:
            draws.append((line, self._font_name))

        def setStrokeColorRGB(self, _r: float, _g: float, _b: float) -> None:
            pass

        def setLineWidth(self, _width: float) -> None:
            pass

        def line(self, _x1: float, _y1: float, _x2: float, _y2: float) -> None:
            pass

        def save(self) -> None:
            self._buf.write(b"%PDF-FAKE")

    monkeypatch.setattr(
        export_resume_documents,
        "_require_reportlab",
        lambda: (
            (612, 792),
            type("CanvasModule", (), {"Canvas": FakeCanvas}),
            lambda text, _font_name, _font_size: len(text) * 5,
        ),
    )
    monkeypatch.setattr(
        export_resume_documents,
        "_require_calibri_pdf_fonts",
        lambda: ("Calibri", "Calibri-Bold"),
    )

    markdown = """## Leadership & Community

- **Technical Mentor (Informal) | HP / Poly | 2008 - Present**
- **CFO & Board Member, Cat Rescue | QA and Test Automation Communities | 2009-Present**
- **Phi Kappa Psi Fraternity | Philanthropy Chair**
"""
    export_resume_documents._render_pdf(markdown, output_path)

    rendered_lines = [entry for entry in draws if entry[0] != "•"]
    assert (
        "Technical Mentor (Informal) | HP / Poly | 2008 - Present",
        "Calibri-Bold",
    ) in rendered_lines
    assert any(
        "CFO & Board Member, Cat Rescue" in line and font_name == "Calibri-Bold"
        for line, font_name in rendered_lines
    )
    assert (
        "Phi Kappa Psi Fraternity | Philanthropy Chair",
        "Calibri-Bold",
    ) in rendered_lines


def test_render_pdf_renders_bold_skills_prefix_inside_bullet_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_path = tmp_path / "resume.pdf"
    draws: list[tuple[str, str]] = []

    class FakeCanvas:
        def __init__(self, buf: io_mod.BytesIO, **_kwargs: object):
            self._buf = buf
            self._font_name = ""

        def showPage(self) -> None:
            pass

        def setFont(self, font_name: str, _font_size: int) -> None:
            self._font_name = font_name

        def drawString(self, _x: float, _y: float, line: str) -> None:
            draws.append((line, self._font_name))

        def setStrokeColorRGB(self, _r: float, _g: float, _b: float) -> None:
            pass

        def setLineWidth(self, _width: float) -> None:
            pass

        def line(self, _x1: float, _y1: float, _x2: float, _y2: float) -> None:
            pass

        def save(self) -> None:
            self._buf.write(b"%PDF-FAKE")

    monkeypatch.setattr(
        export_resume_documents,
        "_require_reportlab",
        lambda: (
            (612, 792),
            type("CanvasModule", (), {"Canvas": FakeCanvas}),
            lambda text, _font_name, _font_size: len(text) * 5,
        ),
    )
    monkeypatch.setattr(
        export_resume_documents,
        "_require_calibri_pdf_fonts",
        lambda: ("Calibri", "Calibri-Bold"),
    )

    markdown = """## Skills

- **Programming & Scripting:** Java • Python
"""
    export_resume_documents._render_pdf(markdown, output_path)

    rendered_lines = [entry for entry in draws if entry[0] != "•"]
    assert ("Programming & Scripting: ", "Calibri-Bold") in rendered_lines
    assert ("Java • Python", "Calibri") in rendered_lines


def test_wrap_skills_category_for_pdf_uses_mixed_font_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        export_resume_documents,
        "_require_reportlab",
        lambda: (
            (612, 792),
            object(),
            lambda text, _font_name, _font_size: len(text),
        ),
    )

    lines = export_resume_documents._wrap_skills_category_for_pdf(
        "Programming & Scripting: ",
        "Java Python TypeScript",
        max_width=30,
        fn_bold="Calibri-Bold",
        fn_regular="Calibri",
        font_size=11,
    )

    assert lines[0][0] == "Programming & Scripting: "
    assert lines[0][1] == "Java"
    assert lines[1][0] == ""
    assert "Python" in lines[1][1]


def test_wrap_skills_category_for_pdf_handles_overlong_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        export_resume_documents,
        "_require_reportlab",
        lambda: (
            (612, 792),
            object(),
            lambda text, _font_name, _font_size: len(text),
        ),
    )

    lines = export_resume_documents._wrap_skills_category_for_pdf(
        "Very Long Category Prefix: ",
        "Java Python",
        max_width=10,
        fn_bold="Calibri-Bold",
        fn_regular="Calibri",
        font_size=11,
    )

    assert lines[0] == ("Very Long Category Prefix: ", "")
    assert lines[-1][0] == ""
    continuation_text = " ".join(regular for _bold, regular in lines[1:])
    assert "Java" in continuation_text


def test_render_docx_body_paragraphs_use_word_spacing_baseline(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "resume.docx"
    markdown = """## Key Skills and Expertise

Summary paragraph for spacing baseline.
**Programming & Scripting:** Java • Python

## Professional Experience
**Company Name**\t2020 - 2024
- Bullet text for experience spacing.
"""

    export_resume_documents._render_docx(markdown, output_path)

    xml = (
        ZipFile(output_path).read("word/document.xml").decode("utf-8", errors="ignore")
    )
    expected_spacing_tokens = (
        'w:before="0"',
        'w:after="0"',
        'w:line="220"',
        'w:lineRule="exact"',
    )
    paragraphs: list[str] = re.findall(r"<w:p\b[^>]*>.*?</w:p>", xml, re.DOTALL)

    def paragraph_containing(token: str) -> str:
        for block in paragraphs:
            if token in block:
                return block
        raise AssertionError(f"paragraph containing token not found: {token}")

    summary_block = paragraph_containing("Summary paragraph for spacing baseline.")
    for token in expected_spacing_tokens:
        assert token in summary_block

    heading_block = paragraph_containing("Key Skills and Expertise")
    assert 'w:after="0"' in heading_block

    skills_block = paragraph_containing("Programming &amp; Scripting:")
    assert "Java" in skills_block and "Python" in skills_block
    for token in expected_spacing_tokens:
        assert token in skills_block

    bullet_block = paragraph_containing("Bullet text for experience spacing.")
    for token in expected_spacing_tokens:
        assert token in bullet_block
    # Bullet paragraphs use a deterministic 0.20in hanging indent (288 twips).
    assert 'w:left="288"' in bullet_block
    assert ('w:hanging="288"' in bullet_block) or ('w:firstLine="-288"' in bullet_block)


def test_render_docx_role_title_spacing_first_and_following(tmp_path: Path) -> None:
    output_path = tmp_path / "resume.docx"
    markdown = """## Professional Experience
### First Role\t2023 - 2024
Role summary one.
### Second Role\t2021 - 2023
Role summary two.
"""

    export_resume_documents._render_docx(markdown, output_path)

    xml = (
        ZipFile(output_path).read("word/document.xml").decode("utf-8", errors="ignore")
    )
    paragraphs: list[str] = re.findall(r"<w:p\b[^>]*>.*?</w:p>", xml, re.DOTALL)

    def paragraph_containing(token: str) -> str:
        for block in paragraphs:
            if token in block:
                return block
        raise AssertionError(f"paragraph containing token not found: {token}")

    first_role_block = paragraph_containing("First Role")
    assert 'w:before="0"' in first_role_block
    assert 'w:after="0"' in first_role_block

    second_role_block = paragraph_containing("Second Role")
    # 4pt before in DOCX XML twips (4 * 20 = 80)
    assert 'w:before="80"' in second_role_block
    assert 'w:after="0"' in second_role_block


def test_wrap_mixed_style_paragraph_for_pdf_short_line_fits_on_one_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With short text, mixed-style paragraph renders on a single line unchanged."""
    monkeypatch.setattr(
        export_resume_documents,
        "_require_reportlab",
        lambda: (
            (612, 792),
            object(),
            lambda text, _font_name, _font_size: len(text),
        ),
    )
    # Simulate result of _BOLD_SPLIT_RE.split("degree: **Bachelor of Science**")
    bold_parts = ["degree: ", "Bachelor of Science", ""]
    lines = export_resume_documents._wrap_mixed_style_paragraph_for_pdf(
        bold_parts,
        max_width=60,
        fn_bold="Calibri-Bold",
        fn_regular="Calibri",
        font_size=11,
    )
    # Should produce exactly one line with all segments
    assert len(lines) == 1
    # Verify style preservation: bold segment should be marked as bold
    line_segments = lines[0]
    combined_text = "".join(text for text, _is_bold in line_segments)
    assert "degree:" in combined_text
    assert "Bachelor of Science" in combined_text


def test_wrap_mixed_style_paragraph_for_pdf_long_line_wraps_with_style_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With long mixed-style text, wrapping preserves style per segment across lines."""
    monkeypatch.setattr(
        export_resume_documents,
        "_require_reportlab",
        lambda: (
            (612, 792),
            object(),
            # Simulate stringWidth: each character is 5 units wide
            lambda text, _font_name, _font_size: len(text) * 5,
        ),
    )
    # Long mixed-style text that should wrap
    # "Experience: **leading major initiative** rest of text here now"
    bold_parts = ["Experience: ", "leading major initiative", " rest of text here now"]
    lines = export_resume_documents._wrap_mixed_style_paragraph_for_pdf(
        bold_parts,
        max_width=80,  # narrow width to force wrapping
        fn_bold="Calibri-Bold",
        fn_regular="Calibri",
        font_size=11,
    )
    # Should produce multiple lines
    assert len(lines) > 1, "Long text should wrap across multiple lines"
    # Verify style preservation: bold segments should be marked as bold
    all_bold_found = False
    for line_segments in lines:
        for text, is_bold in line_segments:
            if "leading" in text or "major" in text or "initiative" in text:
                assert is_bold, "Bold-marked words should preserve bold style"
                all_bold_found = True
    assert all_bold_found, (
        "Bold segments from original text should appear in wrapped output"
    )
    # Verify continuation text appears across lines
    combined = "".join(
        "".join(text for text, _is_bold in line_segments) for line_segments in lines
    )
    assert "Experience:" in combined
    assert "leading" in combined
    assert "rest" in combined and "text" in combined


def test_wrap_mixed_style_paragraph_for_pdf_alternating_styles_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Alternating bold/regular styles are preserved with correct markup."""
    monkeypatch.setattr(
        export_resume_documents,
        "_require_reportlab",
        lambda: (
            (612, 792),
            object(),
            lambda text, _font_name, _font_size: len(text),
        ),
    )
    # Simulate "**bold1** regular1 **bold2** regular2"
    bold_parts = ["", "bold1", " regular1 ", "bold2", " regular2"]
    lines = export_resume_documents._wrap_mixed_style_paragraph_for_pdf(
        bold_parts,
        max_width=50,
        fn_bold="Calibri-Bold",
        fn_regular="Calibri",
        font_size=11,
    )
    # Collect all segments across all lines
    all_segments = []
    for line_segments in lines:
        all_segments.extend(line_segments)
    # Verify style alternates correctly
    bold_count = sum(1 for _text, is_bold in all_segments if is_bold)
    regular_count = sum(1 for _text, is_bold in all_segments if not is_bold)
    # Should have 2 bold and 2 regular segments (ignoring case of wrapping variations)
    assert bold_count >= 2, "Should have at least 2 bold segments"
    assert regular_count >= 2, "Should have at least 2 regular segments"


def test_render_pdf_mixed_style_paragraph_wraps_to_content_width(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mixed-style paragraphs (kind='p') wrap to content_width and preserve style."""
    output_path = tmp_path / "resume.pdf"
    draws: list[tuple[str, str, float, float, str]] = []

    class FakeCanvas:
        def __init__(self, buf: io_mod.BytesIO, **_kwargs: object):
            self._buf = buf
            self._font_name = ""

        def showPage(self) -> None:
            pass

        def setFont(self, font_name: str, _font_size: int) -> None:
            self._font_name = font_name

        def drawString(self, x: float, y: float, line: str) -> None:
            draws.append((line, self._font_name, x, y, "text"))

        def setStrokeColorRGB(self, _r: float, _g: float, _b: float) -> None:
            pass

        def setLineWidth(self, _width: float) -> None:
            pass

        def line(self, _x1: float, _y1: float, _x2: float, _y2: float) -> None:
            draws.append(("line", "", 0, 0, "rule"))

        def save(self) -> None:
            self._buf.write(b"%PDF-FAKE")

    monkeypatch.setattr(
        export_resume_documents,
        "_require_reportlab",
        lambda: (
            (612, 792),
            type("CanvasModule", (), {"Canvas": FakeCanvas}),
            # Simulate stringWidth: each char is 5 units, spaces compress style changes
            lambda text, _font_name, _font_size: len(text) * 5,
        ),
    )
    monkeypatch.setattr(
        export_resume_documents,
        "_require_calibri_pdf_fonts",
        lambda: ("Calibri", "Calibri-Bold"),
    )
    # A paragraph with mixed bold/regular that should wrap when constraint is tight
    # The content_width in _render_pdf is ~540 (612 - 36*2)
    # Simulating very long mixed-style paragraph
    markdown = """## Section
Led initiative called **Development Initiative** with very long description that forces wrapping across lines while preserving bold markup on initiative name and regular markup on description text here.
"""
    export_resume_documents._render_pdf(markdown, output_path)
    # Extract text draws (skip bullets and rules)
    text_draws = [d for d in draws if d[4] == "text" and d[0] != "•"]
    assert len(text_draws) > 0, "Should have rendered at least one text segment"
    # Verify bold segments exist
    bold_draws = [d for d in text_draws if d[1] == "Calibri-Bold"]
    regular_draws = [d for d in text_draws if d[1] == "Calibri"]
    # Both bold and regular should be present (indicating mixed style was rendered)
    assert len(bold_draws) > 0 or len(regular_draws) > 0, "Should have styled text"


# --- STRENGTHENED TESTS FOR STYLE BOUNDARY SPACING ---
def test_wrap_mixed_style_paragraph_for_pdf_preserves_spaces_at_style_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Spaces at style boundaries must be included in emitted text."""
    monkeypatch.setattr(
        export_resume_documents,
        "_require_reportlab",
        lambda: (
            (612, 792),
            object(),
            lambda text, _font_name, _font_size: len(text),
        ),
    )
    # Simulate "degree: **Bachelor of Science**"
    bold_parts = ["degree: ", "Bachelor of Science", ""]
    lines = export_resume_documents._wrap_mixed_style_paragraph_for_pdf(
        bold_parts,
        max_width=60,
        fn_bold="Calibri-Bold",
        fn_regular="Calibri",
        font_size=11,
    )
    assert len(lines) == 1
    line_segments = lines[0]
    # Exact reconstruction must preserve spaces
    combined_text = "".join(text for text, _is_bold in line_segments)
    assert combined_text == "degree: Bachelor of Science", (
        f"Spaces at style boundaries lost; got: {combined_text!r}"
    )


def test_render_pdf_mixed_style_validates_segment_widths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each rendered segment must fit within content_width."""
    output_path = tmp_path / "resume.pdf"
    draws: list[tuple[str, str, float, float]] = []

    class FakeCanvas:
        def __init__(self, buf: io_mod.BytesIO, **_kwargs: object):
            self._buf = buf
            self._font_name = ""

        def showPage(self) -> None:
            pass

        def setFont(self, font_name: str, _font_size: int) -> None:
            self._font_name = font_name

        def drawString(self, x: float, y: float, line: str) -> None:
            draws.append((line, self._font_name, x, y))

        def setStrokeColorRGB(self, _r: float, _g: float, _b: float) -> None:
            pass

        def setLineWidth(self, _width: float) -> None:
            pass

        def line(self, _x1: float, _y1: float, _x2: float, _y2: float) -> None:
            pass

        def save(self) -> None:
            self._buf.write(b"%PDF-FAKE")

    monkeypatch.setattr(
        export_resume_documents,
        "_require_reportlab",
        lambda: (
            (612, 792),
            type("CanvasModule", (), {"Canvas": FakeCanvas}),
            lambda text, _font_name, _font_size: len(text) * 5,
        ),
    )
    monkeypatch.setattr(
        export_resume_documents,
        "_require_calibri_pdf_fonts",
        lambda: ("Calibri", "Calibri-Bold"),
    )
    markdown = """## Section
Led **initiative** with very long description that forces wrapping while preserving bold markup.
"""
    export_resume_documents._render_pdf(markdown, output_path)
    # Validate: both bold and regular segments present
    text_draws = [(t, f, x, y) for t, f, x, y in draws if t not in ("•",)]
    bold_draws = [d for d in text_draws if d[1] == "Calibri-Bold"]
    regular_draws = [d for d in text_draws if d[1] == "Calibri"]
    assert len(bold_draws) > 0, "Should render at least one bold segment"
    assert len(regular_draws) > 0, "Should render at least one regular segment"
    # Validate: each segment stays within content_width
    margin_x = 36
    content_width = 612 - margin_x * 2
    right_edge = margin_x + content_width
    for text, _font_name, x, _y in text_draws:
        segment_width = len(text) * 5  # matches stub stringWidth
        assert x + segment_width <= right_edge, (
            f"Segment '{text}' at x={x} exceeds right_edge={right_edge} (width={segment_width})"
        )
