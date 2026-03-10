"""Tests for ai-tailor.py — YAML helpers, URL fetching, atomic writes."""

import importlib
import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest

# Import the module from scripts/
ai_tailor = importlib.import_module("ai-tailor")


# ---------------------------------------------------------------------------
# extract_yaml_block
# ---------------------------------------------------------------------------

class TestExtractYamlBlock:
    def test_plain_yaml(self):
        text = "personal:\n  name: Jane Doe\nprofile: test"
        result = ai_tailor.extract_yaml_block(text)
        assert "personal:" in result
        assert "Jane Doe" in result

    def test_yaml_in_markdown_fences(self):
        text = "Here is the YAML:\n```yaml\npersonal:\n  name: Jane\n```\nDone."
        result = ai_tailor.extract_yaml_block(text)
        assert "personal:" in result
        assert "```" not in result

    def test_yaml_in_generic_fences(self):
        text = "```\npersonal:\n  name: Jane\n```"
        result = ai_tailor.extract_yaml_block(text)
        assert "personal:" in result
        assert "```" not in result

    def test_fixes_bold_yaml_values(self):
        text = "title: **My Bold Title**"
        result = ai_tailor.extract_yaml_block(text)
        # fix_yaml_bold should quote the value
        assert "**My Bold Title**" in result


# ---------------------------------------------------------------------------
# fix_yaml_bold
# ---------------------------------------------------------------------------

class TestFixYamlBold:
    def test_quotes_bold_value(self):
        text = "title: **Bold Title**"
        result = ai_tailor.fix_yaml_bold(text)
        assert '"**Bold Title**"' in result

    def test_leaves_normal_values(self):
        text = "title: Normal Title"
        result = ai_tailor.fix_yaml_bold(text)
        assert result == text

    def test_handles_list_items(self):
        text = "  - text: **Achievement** with metrics"
        result = ai_tailor.fix_yaml_bold(text)
        assert "**Achievement**" in result


# ---------------------------------------------------------------------------
# _atomic_write
# ---------------------------------------------------------------------------

class TestAtomicWrite:
    def test_writes_content(self, tmp_path):
        path = str(tmp_path / "test.yml")
        ai_tailor._atomic_write(path, "hello: world\n")
        with open(path) as f:
            assert f.read() == "hello: world\n"

    def test_overwrites_existing(self, tmp_path):
        path = str(tmp_path / "test.yml")
        with open(path, "w") as f:
            f.write("old content")
        ai_tailor._atomic_write(path, "new content")
        with open(path) as f:
            assert f.read() == "new content"

    def test_no_partial_write_on_error(self, tmp_path):
        path = str(tmp_path / "test.yml")
        with open(path, "w") as f:
            f.write("original")

        class FakeError(Exception):
            pass

        with patch("os.fdopen", side_effect=FakeError("boom")):
            with pytest.raises(FakeError):
                ai_tailor._atomic_write(path, "should not appear")

        with open(path) as f:
            assert f.read() == "original"


# ---------------------------------------------------------------------------
# count_pdf_pages
# ---------------------------------------------------------------------------

class TestCountPdfPages:
    def test_missing_file(self):
        assert ai_tailor.count_pdf_pages("/nonexistent/file.pdf") == -1

    def test_regex_fallback(self, tmp_path):
        # Create a minimal fake PDF with /Pages /Count
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4\n/Type /Pages /Count 2\n")
        assert ai_tailor.count_pdf_pages(str(pdf)) == 2


# ---------------------------------------------------------------------------
# fetch_url_text
# ---------------------------------------------------------------------------

class TestFetchUrlText:
    def test_rejects_non_http(self):
        with pytest.raises(ValueError, match="Unsupported URL scheme"):
            ai_tailor.fetch_url_text("ftp://example.com/job")

    @patch("urllib.request.urlopen")
    def test_strips_html(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"<html><body><p>Job description</p></body></html>"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = ai_tailor.fetch_url_text("https://example.com/job")
        assert "Job description" in result
        assert "<p>" not in result

    @patch("urllib.request.urlopen")
    def test_truncates_long_text(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = ("x" * 20000).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = ai_tailor.fetch_url_text("https://example.com/job")
        assert len(result) <= 15000


# ---------------------------------------------------------------------------
# tailor_cv (mocked AI)
# ---------------------------------------------------------------------------

class TestTailorCv:
    def test_dry_run_no_file_written(self, tmp_path):
        app_dir = str(tmp_path)
        cv_path = tmp_path / "cv.yml"
        cv_path.write_text("personal:\n  first_name: Jane\n  last_name: Doe\n")

        mock_yaml = "personal:\n  first_name: Jane\n  last_name: Doe\nprofile: tailored"
        with patch.object(ai_tailor, "call_ai", return_value=mock_yaml):
            result = ai_tailor.tailor_cv(
                app_dir, "https://example.com", "job text",
                "fake-key", "gemini", cv_data_path=str(cv_path),
                dry_run=True,
            )

        assert result is None
        assert not (tmp_path / "cv-tailored.yml").exists()

    def test_writes_file_on_success(self, tmp_path):
        app_dir = str(tmp_path)
        cv_path = tmp_path / "cv.yml"
        cv_path.write_text("personal:\n  first_name: Jane\n  last_name: Doe\n")

        mock_yaml = "personal:\n  first_name: Jane\n  last_name: Doe\nprofile: tailored"
        with patch.object(ai_tailor, "call_ai", return_value=mock_yaml):
            result = ai_tailor.tailor_cv(
                app_dir, "https://example.com", "job text",
                "fake-key", "gemini", cv_data_path=str(cv_path),
            )

        assert result is not None
        assert (tmp_path / "cv-tailored.yml").exists()

    def test_invalid_yaml_returns_none(self, tmp_path):
        app_dir = str(tmp_path)
        cv_path = tmp_path / "cv.yml"
        cv_path.write_text("personal:\n  first_name: Jane\n  last_name: Doe\n")

        with patch.object(ai_tailor, "call_ai", return_value="not: valid: yaml: ["):
            result = ai_tailor.tailor_cv(
                app_dir, "https://example.com", "job text",
                "fake-key", "gemini", cv_data_path=str(cv_path),
            )

        assert result is None


# ---------------------------------------------------------------------------
# generate_cover_letter (mocked AI)
# ---------------------------------------------------------------------------

class TestGenerateCoverLetter:
    def test_writes_file_on_success(self, tmp_path):
        app_dir = tmp_path / "2026-03-acme"
        app_dir.mkdir()
        cv_path = tmp_path / "cv.yml"
        cv_path.write_text("personal:\n  first_name: Jane\n  last_name: Doe\n")

        mock_yaml = (
            "recipient:\n  name: Hiring Manager\n  company: Acme\n"
            "sections:\n  - title: About Me\n    content: Hello\n"
        )
        with patch.object(ai_tailor, "call_ai", return_value=mock_yaml):
            result = ai_tailor.generate_cover_letter(
                str(app_dir), "https://example.com", "job text",
                "fake-key", "gemini", cv_data_path=str(cv_path),
            )

        assert result is not None
        assert (app_dir / "coverletter.yml").exists()

    def test_dry_run_no_file(self, tmp_path):
        app_dir = tmp_path / "2026-03-acme"
        app_dir.mkdir()
        cv_path = tmp_path / "cv.yml"
        cv_path.write_text("personal:\n  first_name: Jane\n")

        mock_yaml = "sections:\n  - title: Test\n    content: Hello\n"
        with patch.object(ai_tailor, "call_ai", return_value=mock_yaml):
            result = ai_tailor.generate_cover_letter(
                str(app_dir), "https://example.com", "job text",
                "fake-key", "gemini", cv_data_path=str(cv_path),
                dry_run=True,
            )

        assert result is None
        assert not (app_dir / "coverletter.yml").exists()
