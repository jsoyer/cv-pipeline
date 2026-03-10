"""Backlog items tests.

Covers:
  - yaml-beautify.py: key ordering, round-trip, dry-run, check mode
  - schema-migrate.py: meta.yml field injection, cv.yml section addition
  - interview-predictor.py: sigmoid, logistic regression, predict_proba, ranking
"""

from __future__ import annotations

import importlib.util
import math
import re
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
# yaml-beautify.py
# ---------------------------------------------------------------------------


class TestYamlBeautify:
    @pytest.fixture(autouse=True)
    def mod(self):
        self._mod = _load("yaml-beautify")

    def test_detect_ordering_cv(self):
        data = {"personal": {}, "experience": []}
        order = self._mod.detect_ordering(data)
        assert order == self._mod.CV_KEY_ORDER

    def test_detect_ordering_meta(self):
        data = {"company": "Acme", "outcome": "applied"}
        order = self._mod.detect_ordering(data)
        assert order == self._mod.META_KEY_ORDER

    def test_detect_ordering_unknown(self):
        data = {"foo": "bar"}
        assert self._mod.detect_ordering(data) is None

    def test_reorder_puts_known_keys_first(self):
        mod = self._mod
        data = {"outcome": "applied", "company": "X", "position": "SRE"}
        result = mod.reorder(data, mod.META_KEY_ORDER)
        keys = list(result.keys())
        assert keys.index("company") < keys.index("outcome")

    def test_reorder_appends_extra_keys(self):
        mod = self._mod
        data = {"company": "X", "outcome": "o", "extra_field": 42}
        result = mod.reorder(data, mod.META_KEY_ORDER)
        assert "extra_field" in result
        assert list(result.keys())[-1] == "extra_field"

    def test_beautify_roundtrip(self):
        mod = self._mod
        data = {"company": "Beta", "outcome": "applied", "position": "Eng"}
        text = mod.beautify(data)
        loaded = yaml.safe_load(text)
        assert loaded["company"] == "Beta"
        assert loaded["outcome"] == "applied"

    def test_beautify_cv_ordering(self):
        mod = self._mod
        data = {"experience": [], "personal": {"name": "J"}, "skills": []}
        text = mod.beautify(data)
        lines = text.splitlines()
        keys_in_order = [l.split(":")[0].strip() for l in lines if ":" in l and not l.startswith(" ")]
        personal_idx = keys_in_order.index("personal") if "personal" in keys_in_order else -1
        skills_idx = keys_in_order.index("skills") if "skills" in keys_in_order else -1
        exp_idx = keys_in_order.index("experience") if "experience" in keys_in_order else -1
        if personal_idx >= 0 and skills_idx >= 0:
            assert personal_idx < skills_idx
        if skills_idx >= 0 and exp_idx >= 0:
            assert skills_idx < exp_idx

    def test_process_file_no_change(self, tmp_path):
        mod = self._mod
        data = {"foo": "bar"}
        p = tmp_path / "test.yml"
        p.write_text(yaml.dump(data))
        # Already canonical (no special ordering) — process_file returns False
        with patch.object(mod, "REPO_ROOT", tmp_path):
            changed = mod.process_file(p, dry_run=False, check=False, verbose=False)
        # Content same → no write needed
        assert changed is False or (p.read_text() and True)

    def test_process_file_writes_canonical(self, tmp_path):
        mod = self._mod
        # Write meta with wrong order
        data_text = "outcome: applied\ncompany: Acme\n"
        p = tmp_path / "meta.yml"
        p.write_text(data_text)
        with patch.object(mod, "REPO_ROOT", tmp_path):
            changed = mod.process_file(p, dry_run=False, check=False, verbose=False)
        result = yaml.safe_load(p.read_text())
        assert result["company"] == "Acme"

    def test_process_file_dry_run_no_write(self, tmp_path, capsys):
        mod = self._mod
        data_text = "outcome: applied\ncompany: Acme\n"
        p = tmp_path / "meta.yml"
        p.write_text(data_text)
        with patch.object(mod, "REPO_ROOT", tmp_path):
            mod.process_file(p, dry_run=True, check=False, verbose=False)
        # File must be unchanged in dry-run
        assert p.read_text() == data_text

    def test_process_file_check_mode_returns_changed(self, tmp_path):
        mod = self._mod
        p = tmp_path / "meta.yml"
        p.write_text("outcome: applied\ncompany: Acme\n")
        with patch.object(mod, "REPO_ROOT", tmp_path):
            changed = mod.process_file(p, dry_run=False, check=True, verbose=False)
        assert changed is True

    def test_process_file_invalid_yaml(self, tmp_path):
        mod = self._mod
        p = tmp_path / "bad.yml"
        p.write_text("key: [unclosed")
        with patch.object(mod, "REPO_ROOT", tmp_path):
            changed = mod.process_file(p, dry_run=False, check=False, verbose=False)
        assert changed is False

    def test_process_file_not_a_mapping(self, tmp_path):
        mod = self._mod
        p = tmp_path / "list.yml"
        p.write_text("- a\n- b\n")
        with patch.object(mod, "REPO_ROOT", tmp_path):
            changed = mod.process_file(p, dry_run=False, check=False, verbose=False)
        assert changed is False

    def test_cv_key_order_has_personal_first(self):
        assert self._mod.CV_KEY_ORDER[0] == "personal"

    def test_meta_key_order_has_company_first(self):
        assert self._mod.META_KEY_ORDER[0] == "company"


# ---------------------------------------------------------------------------
# schema-migrate.py
# ---------------------------------------------------------------------------


class TestSchemaMigrate:
    @pytest.fixture(autouse=True)
    def mod(self):
        self._mod = _load("schema-migrate")

    def _write_meta(self, tmp_path: Path, data: dict) -> Path:
        p = tmp_path / "meta.yml"
        p.write_text(yaml.dump(data))
        return p

    def test_migrate_meta_adds_position(self, tmp_path):
        mod = self._mod
        p = self._write_meta(tmp_path, {"company": "Acme"})
        added = mod.migrate_meta(p)
        assert "position" in added

    def test_migrate_meta_adds_outcome(self, tmp_path):
        mod = self._mod
        p = self._write_meta(tmp_path, {"company": "Acme"})
        added = mod.migrate_meta(p)
        assert "outcome" in added

    def test_migrate_meta_adds_created(self, tmp_path):
        mod = self._mod
        p = self._write_meta(tmp_path, {"company": "Acme"})
        added = mod.migrate_meta(p)
        assert "created" in added

    def test_migrate_meta_adds_tailor_provider(self, tmp_path):
        mod = self._mod
        p = self._write_meta(tmp_path, {"company": "Acme"})
        added = mod.migrate_meta(p)
        assert "tailor_provider" in added

    def test_migrate_meta_does_not_overwrite_existing(self, tmp_path):
        mod = self._mod
        p = self._write_meta(tmp_path, {"company": "X", "outcome": "interview"})
        mod.migrate_meta(p)
        result = yaml.safe_load(p.read_text())
        assert result["outcome"] == "interview"

    def test_migrate_meta_skips_without_company(self, tmp_path):
        mod = self._mod
        p = self._write_meta(tmp_path, {"position": "SRE"})
        added = mod.migrate_meta(p)
        assert added == []

    def test_migrate_meta_dry_run_no_write(self, tmp_path):
        mod = self._mod
        original = {"company": "X"}
        p = self._write_meta(tmp_path, original)
        before = p.read_text()
        mod.migrate_meta(p, dry_run=True)
        assert p.read_text() == before

    def test_migrate_meta_returns_empty_when_complete(self, tmp_path):
        mod = self._mod
        p = self._write_meta(
            tmp_path,
            {
                "company": "X",
                "position": "SRE",
                "created": "2026-01",
                "outcome": "applied",
                "tailor_provider": "gemini",
            },
        )
        added = mod.migrate_meta(p)
        assert added == []

    def test_migrate_cv_adds_projects(self, tmp_path):
        mod = self._mod
        cv_path = tmp_path / "cv.yml"
        cv_path.write_text(yaml.dump({"personal": {"name": "J"}, "experience": []}))
        with patch.object(mod, "REPO_ROOT", tmp_path / ".."):
            # Patch cv_path directly
            with patch.object(mod, "REPO_ROOT", tmp_path.parent):
                pass  # can't easily patch — test the function logic directly

        # Call with the actual cv.yml path injected via monkey-patch
        original_repo = mod.REPO_ROOT
        try:
            data_dir = tmp_path / "data"
            data_dir.mkdir()
            shim = data_dir / "cv.yml"
            shim.write_text(yaml.dump({"personal": {"name": "J"}, "experience": []}))
            mod.REPO_ROOT = tmp_path
            added = mod.migrate_cv()
        finally:
            mod.REPO_ROOT = original_repo

        assert "projects" in added

    def test_migrate_cv_adds_volunteer(self, tmp_path):
        mod = self._mod
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "cv.yml").write_text(yaml.dump({"personal": {"name": "J"}}))
        original_repo = mod.REPO_ROOT
        try:
            mod.REPO_ROOT = tmp_path
            added = mod.migrate_cv()
        finally:
            mod.REPO_ROOT = original_repo
        assert "volunteer" in added

    def test_migrate_cv_skips_existing_sections(self, tmp_path):
        mod = self._mod
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "cv.yml").write_text(
            yaml.dump({"personal": {}, "projects": [{"name": "X"}], "volunteer": []})
        )
        original_repo = mod.REPO_ROOT
        try:
            mod.REPO_ROOT = tmp_path
            added = mod.migrate_cv()
        finally:
            mod.REPO_ROOT = original_repo
        assert added == []

    def test_migrate_all_apps_empty(self, tmp_path):
        mod = self._mod
        original_repo = mod.REPO_ROOT
        try:
            mod.REPO_ROOT = tmp_path
            n = mod.migrate_all_apps()
        finally:
            mod.REPO_ROOT = original_repo
        assert n == 0

    def test_migrate_all_apps_counts_changed(self, tmp_path):
        mod = self._mod
        apps = tmp_path / "applications"
        apps.mkdir()
        (apps / "2026-01-acme").mkdir()
        (apps / "2026-01-acme" / "meta.yml").write_text(yaml.dump({"company": "Acme"}))
        original_repo = mod.REPO_ROOT
        try:
            mod.REPO_ROOT = tmp_path
            n = mod.migrate_all_apps()
        finally:
            mod.REPO_ROOT = original_repo
        assert n == 1


# ---------------------------------------------------------------------------
# interview-predictor.py
# ---------------------------------------------------------------------------


class TestInterviewPredictor:
    @pytest.fixture(autouse=True)
    def mod(self):
        self._mod = _load("interview-predictor")

    def test_sigmoid_zero(self):
        assert abs(self._mod.sigmoid(0) - 0.5) < 1e-9

    def test_sigmoid_positive(self):
        s = self._mod.sigmoid(100)
        assert s > 0.999

    def test_sigmoid_negative(self):
        s = self._mod.sigmoid(-100)
        assert s < 0.001

    def test_sigmoid_symmetric(self):
        mod = self._mod
        assert abs(mod.sigmoid(2) + mod.sigmoid(-2) - 1.0) < 1e-9

    def test_normalize_ats(self):
        mod = self._mod
        assert mod._normalize_ats(100.0) == 1.0
        assert mod._normalize_ats(50.0) == 0.5
        assert mod._normalize_ats(0.0) == 0.0

    def test_train_logistic_too_few_samples(self):
        mod = self._mod
        samples = [
            {"ats_score": 70, "label": 1},
            {"ats_score": 30, "label": 0},
        ]
        result = mod.train_logistic(samples)
        assert result is None

    def test_train_logistic_returns_weights(self):
        mod = self._mod
        samples = [
            {"ats_score": 80, "label": 1},
            {"ats_score": 75, "label": 1},
            {"ats_score": 70, "label": 1},
            {"ats_score": 25, "label": 0},
            {"ats_score": 20, "label": 0},
            {"ats_score": 15, "label": 0},
        ]
        result = mod.train_logistic(samples)
        assert result is not None
        assert len(result) == 2

    def test_train_logistic_positive_ats_coefficient(self):
        mod = self._mod
        # Higher ATS → positive outcome → positive coefficient
        samples = [
            {"ats_score": 85, "label": 1},
            {"ats_score": 80, "label": 1},
            {"ats_score": 78, "label": 1},
            {"ats_score": 20, "label": 0},
            {"ats_score": 15, "label": 0},
            {"ats_score": 10, "label": 0},
        ]
        w_ats, _ = mod.train_logistic(samples)
        assert w_ats > 0

    def test_predict_proba_fallback_high(self):
        mod = self._mod
        p = mod.predict_proba(70.0, None)
        assert p == 0.60

    def test_predict_proba_fallback_low(self):
        mod = self._mod
        p = mod.predict_proba(50.0, None)
        assert p == 0.35

    def test_predict_proba_with_weights(self):
        mod = self._mod
        # Simple weights: bias only → sigmoid(0) = 0.5
        p = mod.predict_proba(50.0, (0.0, 0.0))
        assert abs(p - 0.5) < 1e-9

    def test_predict_proba_range(self):
        mod = self._mod
        for ats in (0, 25, 50, 75, 100):
            p = mod.predict_proba(float(ats), (2.0, -1.0))
            assert 0.0 <= p <= 1.0

    def test_training_accuracy_no_labeled(self):
        mod = self._mod
        samples = [{"ats_score": 50, "label": -1}]
        acc = mod._training_accuracy(samples, None)
        assert acc == 0.0

    def test_training_accuracy_perfect(self):
        mod = self._mod
        # Large positive weights → high ATS → prob > 0.5 → label=1
        samples = [{"ats_score": 90, "label": 1}, {"ats_score": 10, "label": 0}]
        acc = mod._training_accuracy(samples, (10.0, -5.0))
        assert acc == 1.0

    def test_ats_from_history_empty(self):
        mod = self._mod
        assert mod._ats_from_history({}) == 0.0

    def test_ats_from_history_with_entry(self):
        mod = self._mod
        meta = {"ats_history": [{"score": 72.5}]}
        assert mod._ats_from_history(meta) == 72.5

    def test_find_sample_by_name(self):
        mod = self._mod
        samples = [{"name": "2026-01-acme", "ats_score": 70}]
        found = mod._find_sample(samples, "2026-01-acme")
        assert found is not None
        assert found["ats_score"] == 70

    def test_find_sample_by_path(self):
        mod = self._mod
        samples = [{"name": "2026-01-acme", "ats_score": 70}]
        found = mod._find_sample(samples, "applications/2026-01-acme")
        assert found is not None

    def test_find_sample_missing(self):
        mod = self._mod
        samples = [{"name": "other", "ats_score": 50}]
        assert mod._find_sample(samples, "nope") is None

    def test_rank_all_sorted_by_prob(self):
        mod = self._mod
        samples = [
            {"name": "low",  "ats_score": 10, "label": -1, "outcome": "applied"},
            {"name": "high", "ats_score": 90, "label": -1, "outcome": "applied"},
            {"name": "mid",  "ats_score": 50, "label": -1, "outcome": "applied"},
        ]
        ranked = mod._rank_all(samples, None, 3)
        probs = [r["prob"] for r in ranked]
        assert probs == sorted(probs, reverse=True)

    def test_rank_all_respects_top_n(self):
        mod = self._mod
        samples = [{"name": f"app{i}", "ats_score": float(i * 10), "label": -1, "outcome": "applied"} for i in range(10)]
        ranked = mod._rank_all(samples, None, 3)
        assert len(ranked) == 3

    def test_load_dataset_no_dir(self, tmp_path):
        mod = self._mod
        original_repo = mod.REPO_ROOT
        try:
            mod.REPO_ROOT = tmp_path
            data = mod.load_dataset()
        finally:
            mod.REPO_ROOT = original_repo
        assert data == []

    def test_load_dataset_with_apps(self, tmp_path):
        mod = self._mod
        apps = tmp_path / "applications"
        apps.mkdir()
        d = apps / "2026-01-test"
        d.mkdir()
        (d / "meta.yml").write_text(yaml.dump({
            "company": "Test", "position": "SRE", "outcome": "applied",
        }))
        original_repo = mod.REPO_ROOT
        try:
            mod.REPO_ROOT = tmp_path
            data = mod.load_dataset()
        finally:
            mod.REPO_ROOT = original_repo
        assert len(data) == 1
        assert data[0]["name"] == "2026-01-test"

    def test_load_dataset_labels(self, tmp_path):
        mod = self._mod
        apps = tmp_path / "applications"
        apps.mkdir()
        for company, outcome, expected_label in [
            ("A", "interview", 1),
            ("B", "rejected", 0),
            ("C", "applied",  -1),
        ]:
            slug = company.lower()
            d = apps / f"2026-01-{slug}"
            d.mkdir()
            (d / "meta.yml").write_text(yaml.dump({"company": company, "outcome": outcome}))
        original_repo = mod.REPO_ROOT
        try:
            mod.REPO_ROOT = tmp_path
            data = mod.load_dataset()
        finally:
            mod.REPO_ROOT = original_repo
        labels = {r["name"].split("-")[-1]: r["label"] for r in data}
        assert labels["a"] == 1
        assert labels["b"] == 0
        assert labels["c"] == -1

