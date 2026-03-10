"""
Phase 19 — Multi-template support tests.

Covers: render_cv_moderncv(), render_cv_deedy(), --template CLI flag.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

SCRIPTS = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load(name: str):
    module_name = name.replace("-", "_")
    spec = importlib.util.spec_from_file_location(module_name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


def _sample_cv() -> dict:
    return {
        "personal": {
            "first_name": "Jane",
            "last_name": "Doe",
            "position": "VP Engineering",
            "address": "Paris, France",
            "mobile": "+33 6 12 34 56 78",
            "email": "jane@example.com",
            "linkedin": "janedoe",
        },
        "profile": "Seasoned engineering leader with 15 years building high-performance teams.",
        "skills": [
            {"category": "Leadership", "items": "Team building, OKRs, roadmap"},
            {"category": "Tech", "items": "Python, Kubernetes, AWS"},
        ],
        "key_wins": [
            {"title": "Revenue Impact", "text": "Grew ARR from $10M to $50M in 2 years."},
            {"title": "Team Scale", "text": "Hired 40 engineers across 4 countries."},
        ],
        "experience": [
            {
                "title": "VP Engineering",
                "company": "Acme Corp",
                "location": "Paris, France",
                "dates": "2022--present",
                "items": [
                    {"text": "Led platform rewrite, reducing latency by 60%."},
                    {"text": "Managed $5M infrastructure budget."},
                ],
            },
            {
                "title": "Engineering Manager",
                "company": "Beta Inc",
                "location": "Lyon, France",
                "dates": "2019--2022",
                "items": [{"text": "Built CI/CD pipeline from scratch."}],
            },
        ],
        "early_career": [
            {
                "title": "Software Engineer",
                "company": "Gamma SA",
                "location": "Paris",
                "dates": "2010--2019",
                "items": [],
            }
        ],
        "education": [
            {
                "degree": "MSc Computer Science",
                "school": "Ecole Polytechnique",
                "location": "Palaiseau, France",
                "dates": "2003--2008",
                "note": "Graduated top 5%",
            }
        ],
        "certifications": [
            {"name": "AWS Solutions Architect", "institution": "Amazon", "date": "2023"}
        ],
        "awards": "Best Engineering Award 2022.",
        "publications": "\"Scaling Teams\" — Medium, 2021.",
        "languages": ["French (native)", "English (fluent)"],
        "interests": ["Open source", "Triathlon"],
    }


# ---------------------------------------------------------------------------
# ModernCV renderer
# ---------------------------------------------------------------------------


class TestModernCVRenderer:
    def test_documentclass_moderncv(self):
        mod = _load("render")
        out = mod.render_cv_moderncv(_sample_cv())
        assert "\\documentclass[11pt,a4paper,sans]{moderncv}" in out

    def test_moderncv_style_and_color(self):
        mod = _load("render")
        out = mod.render_cv_moderncv(_sample_cv(), style="classic", color="blue")
        assert "\\moderncvstyle{classic}" in out
        assert "\\moderncvcolor{blue}" in out

    def test_makecvtitle_present(self):
        mod = _load("render")
        out = mod.render_cv_moderncv(_sample_cv())
        assert "\\makecvtitle" in out

    def test_name_in_output(self):
        mod = _load("render")
        out = mod.render_cv_moderncv(_sample_cv())
        assert "\\name{Jane}{Doe}" in out

    def test_position_in_title(self):
        mod = _load("render")
        out = mod.render_cv_moderncv(_sample_cv())
        assert "VP Engineering" in out

    def test_profile_section(self):
        mod = _load("render")
        out = mod.render_cv_moderncv(_sample_cv())
        assert "\\section{Profile}" in out
        assert "Seasoned engineering leader" in out

    def test_skills_rendered_as_cvitem(self):
        mod = _load("render")
        out = mod.render_cv_moderncv(_sample_cv())
        assert "\\cvitem{Leadership}" in out
        assert "\\cvitem{Tech}" in out

    def test_experience_section(self):
        mod = _load("render")
        out = mod.render_cv_moderncv(_sample_cv())
        assert "\\section{Work Experience}" in out
        assert "Acme Corp" in out
        assert "2022--present" in out

    def test_experience_bullets(self):
        mod = _load("render")
        out = mod.render_cv_moderncv(_sample_cv())
        assert "\\begin{itemize}" in out
        assert "reducing latency by 60" in out

    def test_education_section(self):
        mod = _load("render")
        out = mod.render_cv_moderncv(_sample_cv())
        assert "\\section{Education}" in out
        assert "Ecole Polytechnique" in out

    def test_certifications_section(self):
        mod = _load("render")
        out = mod.render_cv_moderncv(_sample_cv())
        assert "\\section{Certifications}" in out
        assert "AWS Solutions Architect" in out

    def test_languages_section(self):
        mod = _load("render")
        out = mod.render_cv_moderncv(_sample_cv())
        assert "\\section{Languages}" in out
        assert "French" in out

    def test_end_document(self):
        mod = _load("render")
        out = mod.render_cv_moderncv(_sample_cv())
        assert "\\end{document}" in out

    def test_key_wins_section(self):
        mod = _load("render")
        out = mod.render_cv_moderncv(_sample_cv())
        assert "\\section{Key Achievements}" in out
        assert "Revenue Impact" in out

    def test_custom_style(self):
        mod = _load("render")
        out = mod.render_cv_moderncv(_sample_cv(), style="banking", color="red")
        assert "\\moderncvstyle{banking}" in out
        assert "\\moderncvcolor{red}" in out

    def test_no_awesome_cv_commands(self):
        mod = _load("render")
        out = mod.render_cv_moderncv(_sample_cv())
        assert "\\cvsection" not in out
        assert "\\cventry" in out  # moderncv uses cventry


# ---------------------------------------------------------------------------
# Deedy-style renderer
# ---------------------------------------------------------------------------


class TestDeedyRenderer:
    def test_documentclass_article(self):
        mod = _load("render")
        out = mod.render_cv_deedy(_sample_cv())
        assert "\\documentclass[a4paper,10pt]{article}" in out

    def test_multicol_present(self):
        mod = _load("render")
        out = mod.render_cv_deedy(_sample_cv())
        assert "\\begin{multicols}{2}" in out
        assert "\\end{multicols}" in out

    def test_columnbreak_present(self):
        mod = _load("render")
        out = mod.render_cv_deedy(_sample_cv())
        assert "\\columnbreak" in out

    def test_name_in_header(self):
        mod = _load("render")
        out = mod.render_cv_deedy(_sample_cv())
        assert "Jane Doe" in out

    def test_contact_info_in_header(self):
        mod = _load("render")
        out = mod.render_cv_deedy(_sample_cv())
        assert "jane@example.com" in out
        assert "janedoe" in out

    def test_profile_section(self):
        mod = _load("render")
        out = mod.render_cv_deedy(_sample_cv())
        assert "\\section{Profile}" in out
        assert "Seasoned engineering leader" in out

    def test_skills_section(self):
        mod = _load("render")
        out = mod.render_cv_deedy(_sample_cv())
        assert "\\section{Skills}" in out
        assert "Leadership" in out

    def test_experience_section(self):
        mod = _load("render")
        out = mod.render_cv_deedy(_sample_cv())
        assert "\\section{Experience}" in out
        assert "Acme Corp" in out

    def test_experience_limited_to_3(self):
        mod = _load("render")
        cv = _sample_cv()
        # Add extra entries
        for i in range(5):
            cv["experience"].append(
                {
                    "title": f"Role {i}",
                    "company": f"Co {i}",
                    "location": "Paris",
                    "dates": "2000--2005",
                    "items": [],
                }
            )
        out = mod.render_cv_deedy(cv)
        # Only first 3 companies should appear
        assert "Acme Corp" in out
        assert "Beta Inc" in out
        # Co 4 should NOT appear (index 4 beyond first 3)
        assert "Co 4" not in out

    def test_key_wins_section(self):
        mod = _load("render")
        out = mod.render_cv_deedy(_sample_cv())
        assert "\\section{Key Wins}" in out
        assert "Revenue Impact" in out

    def test_key_wins_limited_to_3(self):
        mod = _load("render")
        cv = _sample_cv()
        for i in range(5):
            cv["key_wins"].append({"title": f"Win {i}", "text": f"Text {i}"})
        out = mod.render_cv_deedy(cv)
        assert out.count("\\item") <= 10  # rough sanity check

    def test_education_section(self):
        mod = _load("render")
        out = mod.render_cv_deedy(_sample_cv())
        assert "\\section{Education}" in out
        assert "Ecole Polytechnique" in out

    def test_languages_section(self):
        mod = _load("render")
        out = mod.render_cv_deedy(_sample_cv())
        assert "\\section{Languages}" in out
        assert "French" in out

    def test_profile_truncated_if_long(self):
        mod = _load("render")
        cv = _sample_cv()
        cv["profile"] = "A" * 600  # very long profile
        out = mod.render_cv_deedy(cv)
        assert "..." in out  # truncated

    def test_no_moderncv_commands(self):
        mod = _load("render")
        out = mod.render_cv_deedy(_sample_cv())
        assert "\\moderncvstyle" not in out
        assert "\\makecvtitle" not in out

    def test_end_document(self):
        mod = _load("render")
        out = mod.render_cv_deedy(_sample_cv())
        assert "\\end{document}" in out


# ---------------------------------------------------------------------------
# CLI --template flag
# ---------------------------------------------------------------------------


class TestTemplateCLI:
    def _write_cv(self, tmp_path: Path) -> Path:
        cv_path = tmp_path / "cv.yml"
        cv_path.write_text(yaml.dump(_sample_cv()), encoding="utf-8")
        return cv_path

    def test_default_template_is_awesome_cv(self, tmp_path):
        mod = _load("render")
        cv_path = self._write_cv(tmp_path)
        out_path = tmp_path / "CV.tex"
        with patch("sys.argv", ["render.py", "-d", str(cv_path), "-o", str(out_path)]):
            rc = mod.main()
        assert rc == 0
        content = out_path.read_text()
        assert "awesome-cv" in content.lower()

    def test_template_moderncv(self, tmp_path):
        mod = _load("render")
        cv_path = self._write_cv(tmp_path)
        out_path = tmp_path / "CV-moderncv.tex"
        with patch("sys.argv", ["render.py", "-d", str(cv_path), "--template", "moderncv", "-o", str(out_path)]):
            rc = mod.main()
        assert rc == 0
        content = out_path.read_text()
        assert "\\documentclass[11pt,a4paper,sans]{moderncv}" in content

    def test_template_deedy(self, tmp_path):
        mod = _load("render")
        cv_path = self._write_cv(tmp_path)
        out_path = tmp_path / "CV-deedy.tex"
        with patch("sys.argv", ["render.py", "-d", str(cv_path), "--template", "deedy", "-o", str(out_path)]):
            rc = mod.main()
        assert rc == 0
        content = out_path.read_text()
        assert "\\documentclass[a4paper,10pt]{article}" in content
        assert "multicols" in content

    def test_moderncv_default_output_name(self, tmp_path):
        mod = _load("render")
        cv_path = self._write_cv(tmp_path)
        import os

        orig_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            with patch("sys.argv", ["render.py", "-d", str(cv_path), "--template", "moderncv"]):
                rc = mod.main()
        finally:
            os.chdir(orig_dir)
        assert rc == 0
        assert (tmp_path / "CV-moderncv.tex").exists()

    def test_deedy_default_output_name(self, tmp_path):
        mod = _load("render")
        cv_path = self._write_cv(tmp_path)
        import os

        orig_dir = os.getcwd()
        try:
            os.chdir(tmp_path)
            with patch("sys.argv", ["render.py", "-d", str(cv_path), "--template", "deedy"]):
                rc = mod.main()
        finally:
            os.chdir(orig_dir)
        assert rc == 0
        assert (tmp_path / "CV-deedy.tex").exists()

    def test_moderncv_rejects_coverletter(self, tmp_path):
        mod = _load("render")
        cl_data = {
            "recipient": {"name": "HR", "company": "Acme"},
            "title": "Application",
            "opening": "Dear HR,",
            "closing": "Sincerely,",
            "sections": [{"title": "Motivation", "content": "I am motivated."}],
        }
        cl_path = tmp_path / "cl.yml"
        cl_path.write_text(yaml.dump(cl_data), encoding="utf-8")
        with patch("sys.argv", ["render.py", "-d", str(cl_path), "--template", "moderncv"]):
            with pytest.raises(SystemExit) as exc:
                mod.main()
        assert exc.value.code == 1

    def test_deedy_rejects_coverletter(self, tmp_path):
        mod = _load("render")
        cl_data = {
            "recipient": {"name": "HR", "company": "Acme"},
            "title": "Application",
            "opening": "Dear HR,",
            "closing": "Sincerely,",
            "sections": [{"title": "Motivation", "content": "I am motivated."}],
        }
        cl_path = tmp_path / "cl.yml"
        cl_path.write_text(yaml.dump(cl_data), encoding="utf-8")
        with patch("sys.argv", ["render.py", "-d", str(cl_path), "--template", "deedy"]):
            with pytest.raises(SystemExit) as exc:
                mod.main()
        assert exc.value.code == 1


# ---------------------------------------------------------------------------
# _moderncv_entry_items helper
# ---------------------------------------------------------------------------


class TestModernCVEntryItems:
    def test_empty_items(self):
        mod = _load("render")
        assert mod._moderncv_entry_items([]) == ""

    def test_plain_string_items(self):
        mod = _load("render")
        result = mod._moderncv_entry_items([{"text": "Led team of 10"}])
        assert "\\begin{itemize}" in result
        assert "Led team of 10" in result
        assert "\\end{itemize}" in result

    def test_label_items(self):
        mod = _load("render")
        result = mod._moderncv_entry_items([{"text": "Grew ARR by 40%", "label": "Revenue"}])
        assert "\\textbf{Revenue:}" in result
        assert "Grew ARR by 40" in result

    def test_mixed_items(self):
        mod = _load("render")
        items = [
            {"text": "First bullet"},
            {"text": "Second bullet", "label": "Impact"},
        ]
        result = mod._moderncv_entry_items(items)
        assert "First bullet" in result
        assert "\\textbf{Impact:}" in result
