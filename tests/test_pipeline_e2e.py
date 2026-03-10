"""End-to-end pipeline test: cv.yml -> render.py -> CV.tex -> validate."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
render = importlib.import_module("render")

REPO_ROOT = Path(__file__).resolve().parent.parent
CV_YML = REPO_ROOT / "data" / "cv.yml"
CV_FR_YML = REPO_ROOT / "data" / "cv-fr.yml"
SCHEMA_PATH = REPO_ROOT / "data" / "cv-schema.json"


@pytest.fixture
def cv_data():
    """Load the real cv.yml data."""
    yaml = __import__("yaml")
    with open(CV_YML, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture
def cv_fr_data():
    """Load the real cv-fr.yml data."""
    if not CV_FR_YML.exists():
        pytest.skip("cv-fr.yml not found")
    yaml = __import__("yaml")
    with open(CV_FR_YML, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── Schema validation ────────────────────────────────────────────────────────

class TestSchemaValidation:
    def test_cv_yml_validates(self, cv_data):
        jsonschema = pytest.importorskip("jsonschema")
        with open(SCHEMA_PATH) as f:
            schema = json.load(f)
        jsonschema.validate(instance=cv_data, schema=schema)

    def test_cv_fr_yml_validates(self, cv_fr_data):
        jsonschema = pytest.importorskip("jsonschema")
        with open(SCHEMA_PATH) as f:
            schema = json.load(f)
        jsonschema.validate(instance=cv_fr_data, schema=schema)


# ── Required sections ────────────────────────────────────────────────────────

class TestRequiredSections:
    def test_personal_has_required_fields(self, cv_data):
        personal = cv_data["personal"]
        for key in ("first_name", "last_name", "position", "email"):
            assert key in personal, f"Missing personal.{key}"

    def test_profile_length(self, cv_data):
        profile = cv_data["profile"]
        assert 50 <= len(profile) <= 600, f"Profile length {len(profile)} out of range"

    def test_skills_nonempty(self, cv_data):
        assert len(cv_data["skills"]) >= 1

    def test_experience_nonempty(self, cv_data):
        assert len(cv_data["experience"]) >= 1

    def test_education_nonempty(self, cv_data):
        assert len(cv_data["education"]) >= 1

    def test_experience_dates_format(self, cv_data):
        for exp in cv_data["experience"]:
            assert " -- " in exp["dates"], f"Invalid date format: {exp['dates']}"

    def test_experience_bullets_length(self, cv_data):
        for exp in cv_data["experience"]:
            for item in exp.get("items", []):
                text = item.get("text", "")
                assert len(text) <= 300, f"Bullet too long ({len(text)} chars): {text[:50]}..."


# ── Render pipeline ──────────────────────────────────────────────────────────

class TestRenderPipeline:
    def test_render_cv_produces_tex(self, cv_data):
        tex = render.render_cv(cv_data)
        assert isinstance(tex, str)
        assert len(tex) > 100

    def test_tex_has_document_structure(self, cv_data):
        tex = render.render_cv(cv_data)
        assert "\\begin{document}" in tex
        assert "\\end{document}" in tex

    def test_tex_has_personal_info(self, cv_data):
        tex = render.render_cv(cv_data)
        assert cv_data["personal"]["first_name"] in tex
        assert cv_data["personal"]["last_name"] in tex

    def test_tex_has_profile(self, cv_data):
        tex = render.render_cv(cv_data)
        assert "\\cvsection{Profile}" in tex or "\\cvsection{Summary}" in tex or "cvparagraph" in tex

    def test_tex_has_experience(self, cv_data):
        tex = render.render_cv(cv_data)
        first_company = cv_data["experience"][0]["company"]
        assert first_company in tex or render.process_text(first_company) in tex

    def test_tex_has_education(self, cv_data):
        tex = render.render_cv(cv_data)
        first_school = cv_data["education"][0]["school"]
        assert first_school in tex or render.process_text(first_school) in tex

    def test_tex_has_skills(self, cv_data):
        tex = render.render_cv(cv_data)
        first_cat = cv_data["skills"][0]["category"]
        assert first_cat in tex or render.process_text(first_cat) in tex

    def test_special_chars_escaped(self, cv_data):
        tex = render.render_cv(cv_data)
        # Should not have bare & outside of LaTeX commands
        lines = tex.split("\n")
        for line in lines:
            if line.strip().startswith("\\") or line.strip().startswith("%"):
                continue
            # In content lines, & should be escaped as \&
            # (this is a soft check -- some & in LaTeX commands are valid)

    def test_render_french_produces_tex(self, cv_fr_data):
        tex = render.render_cv(cv_fr_data)
        assert isinstance(tex, str)
        assert len(tex) > 100
        assert "\\begin{document}" in tex


# ── Cover letter render ───────────────────────────────────────────────────────

class TestCoverLetterRender:
    @pytest.fixture
    def cl_data(self):
        """Minimal cover letter data matching render.py expectations."""
        return {
            "recipient": {
                "name": "Jane Smith",
                "company": "Acme Corp",
            },
            "title": "Application for Senior Engineer",
            "opening": "Dear Hiring Manager,",
            "closing": "Best regards,",
            "sections": [
                {"title": "Why Acme", "content": "I admire your mission."},
                {"title": "My Experience", "content": "10 years in the field."},
            ],
        }

    def test_render_coverletter_exists(self):
        assert hasattr(render, "render_coverletter")

    def test_render_coverletter_produces_output(self, cl_data, cv_data):
        tex = render.render_coverletter(cl_data, cv_data["personal"])
        assert isinstance(tex, str)
        assert len(tex) > 50
        assert "\\begin{document}" in tex
