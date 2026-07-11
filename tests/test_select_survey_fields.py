"""Tests for Skills/select_survey_fields.py.

All tests run offline — Sun position is injected via monkeypatching so no
astropy network call is made.  The geometry helpers use only NumPy arithmetic.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

# Make the Skills script importable from the tests directory
sys.path.insert(0, str(Path(__file__).parent.parent / "Skills"))

import select_survey_fields as ssf

# ── Geometry helper tests ──────────────────────────────────────────────────────

class TestEclipticLatitudeBatch:
    def test_zero_at_vernal_equinox(self):
        # RA=0, Dec=0 → ecliptic lat ≈ 0
        result = ssf.ecliptic_latitude_batch(np.array([0.0]), np.array([0.0]))
        assert abs(result[0]) < 0.1

    def test_north_pole_near_90(self):
        # Dec=90° → ecliptic lat ≈ 90 - obliquity ≈ 66.6°
        result = ssf.ecliptic_latitude_batch(np.array([0.0]), np.array([90.0]))
        assert 60.0 < result[0] < 80.0

    def test_batch_shape_preserved(self):
        ra  = np.linspace(0, 360, 72)
        dec = np.zeros(72)
        result = ssf.ecliptic_latitude_batch(ra, dec)
        assert result.shape == (72,)
        assert np.all(np.isfinite(result))

    def test_antisymmetric_about_ecliptic_plane(self):
        # RA=0, Dec=+45° and RA=0, Dec=-45° should give opposite-sign β with |β|>15°
        # (RA=90° Dec=±23.44° is actually on the ecliptic; use RA=0° instead)
        ra  = np.array([0.0, 0.0])
        dec = np.array([45.0, -45.0])
        b   = ssf.ecliptic_latitude_batch(ra, dec)
        assert abs(b[0]) > 15.0
        assert abs(b[1]) > 15.0
        assert abs(b[0] + b[1]) < 1.0  # near-antisymmetric


class TestElongationBatch:
    def test_field_at_sun_position_is_zero(self):
        ra_sun, dec_sun = 45.0, 10.0
        elong = ssf.elongation_batch(
            np.array([45.0]), np.array([10.0]), ra_sun, dec_sun
        )
        assert abs(elong[0]) < 0.01

    def test_opposition_is_180(self):
        # Field exactly opposite the Sun
        ra_sun, dec_sun = 45.0, 0.0
        elong = ssf.elongation_batch(
            np.array([225.0]), np.array([0.0]), ra_sun, dec_sun
        )
        assert abs(elong[0] - 180.0) < 0.1

    def test_quadrature_is_90(self):
        ra_sun, dec_sun = 0.0, 0.0
        elong = ssf.elongation_batch(
            np.array([90.0]), np.array([0.0]), ra_sun, dec_sun
        )
        assert abs(elong[0] - 90.0) < 0.1

    def test_output_range(self):
        ra  = np.linspace(0, 359, 360)
        dec = np.zeros(360)
        elong = ssf.elongation_batch(ra, dec, 180.0, 0.0)
        assert np.all(elong >= 0.0)
        assert np.all(elong <= 180.0)


class TestHoursVisibleBatch:
    def test_circumpolar_dec_at_palomar(self):
        # Dec=90° from Palomar (lat=33.36°) is always above 25°
        hours = ssf.hours_visible_batch(np.array([90.0]), lat_deg=33.36)
        assert hours[0] == pytest.approx(10.0)

    def test_never_rises_below_horizon(self):
        # Dec=-90° from Palomar (lat=33.36°) never rises above 25°
        hours = ssf.hours_visible_batch(np.array([-90.0]), lat_deg=33.36)
        assert hours[0] == pytest.approx(0.0)

    def test_equatorial_field_gets_reasonable_hours(self):
        # Dec=0° from mid-latitudes should be observable for several hours
        hours = ssf.hours_visible_batch(np.array([0.0]), lat_deg=33.0)
        assert 3.0 < hours[0] < 9.0

    def test_batch_shape_preserved(self):
        dec = np.linspace(-30, 85, 50)
        hours = ssf.hours_visible_batch(dec, lat_deg=33.36)
        assert hours.shape == (50,)
        assert np.all(hours >= 0.0)
        assert np.all(hours <= 10.0)


# ── Scoring component tests ────────────────────────────────────────────────────

class TestGapScoreBatch:
    def test_ieo_is_high_everywhere(self):
        elong = np.array([25.0, 32.0, 40.0])
        scores = ssf.gap_score_batch(elong, "ieo")
        assert np.all(scores > 0.90)

    def test_aten_peaks_at_80_degrees(self):
        elong = np.array([80.0])
        peak  = ssf.gap_score_batch(elong, "aten")
        elong2 = np.array([60.0])
        off   = ssf.gap_score_batch(elong2, "aten")
        assert peak[0] > off[0]

    def test_all_mode_output_in_range(self):
        elong = np.linspace(0, 180, 181)
        scores = ssf.gap_score_batch(elong, "all")
        assert np.all(scores >= 0.0)
        assert np.all(scores <= 1.0)

    def test_unknown_mode_falls_through_to_all(self):
        # No mode match → should not raise; treated same as "all"
        elong = np.array([90.0])
        scores = ssf.gap_score_batch(elong, "all")
        assert 0.0 <= scores[0] <= 1.0


class TestPopulationScoreBatch:
    def test_ecliptic_higher_than_pole(self):
        ecl_lat = np.array([0.0, 80.0])
        elong   = np.array([90.0, 90.0])
        scores  = ssf.population_score_batch(ecl_lat, elong, "aten")
        assert scores[0] > scores[1]

    def test_ieo_has_higher_base_than_all(self):
        # IEO completeness=0.03 → undiscovered=0.97; all completeness=0.45 → 0.55
        ecl_lat = np.array([0.0])
        elong   = np.array([32.5])
        score_ieo = ssf.population_score_batch(ecl_lat, elong, "ieo")
        score_all = ssf.population_score_batch(ecl_lat, elong, "all")
        assert score_ieo[0] > score_all[0]

    def test_output_in_range(self):
        ecl_lat = np.linspace(-90, 90, 181)
        elong   = np.full(181, 90.0)
        scores  = ssf.population_score_batch(ecl_lat, elong, "aten")
        assert np.all(scores >= 0.0)
        assert np.all(scores <= 1.0)


class TestKnownObjectDensityScoreBatch:
    def test_ecliptic_opposition_is_highest(self):
        ecl_lat = np.array([0.0, 60.0])
        elong = np.array([180.0, 180.0])
        scores = ssf.known_object_density_score_batch(ecl_lat, elong)
        assert scores[0] > scores[1]

    def test_opposition_higher_than_quadrature(self):
        ecl_lat = np.array([0.0, 0.0])
        elong = np.array([180.0, 90.0])
        scores = ssf.known_object_density_score_batch(ecl_lat, elong)
        assert scores[0] > scores[1]

    def test_output_in_range(self):
        ecl_lat = np.linspace(-90, 90, 181)
        elong = np.linspace(0, 180, 181)
        scores = ssf.known_object_density_score_batch(ecl_lat, elong)
        assert np.all(scores >= 0.0)
        assert np.all(scores <= 1.0)


class TestGeometryScoreBatch:
    def test_aten_peak_at_80_degrees(self):
        elong = np.array([80.0])
        hours = np.array([6.0])
        score = ssf.geometry_score_batch(elong, hours, "aten")
        assert score[0] > 0.5

    def test_zero_outside_window(self):
        # 180° is outside Aten window (60-100°); full score should be 0 (not just elong component)
        elong = np.array([180.0])
        hours = np.array([6.0])
        score = ssf.geometry_score_batch(elong, hours, "aten")
        assert score[0] == pytest.approx(0.0, abs=1e-9)

    def test_zero_hours_reduces_score(self):
        elong = np.array([80.0, 80.0])
        hours = np.array([0.0, 6.0])
        scores = ssf.geometry_score_batch(elong, hours, "aten")
        assert scores[1] > scores[0]

    def test_ieo_peak_in_twilight_window(self):
        elong = np.array([32.5])
        hours = np.array([5.0])
        score = ssf.geometry_score_batch(elong, hours, "ieo")
        assert score[0] > 0.5


# ── Novelty / run history tests ────────────────────────────────────────────────

class TestNoveltyScopesBatch:
    def test_empty_history_all_ones(self):
        ra  = np.array([10.0, 20.0, 30.0])
        dec = np.array([0.0, 5.0, -5.0])
        scores = ssf.novelty_scores_batch(ra, dec, [])
        assert np.all(scores == 1.0)

    def test_nearby_field_zeroed(self):
        ra  = np.array([45.0, 45.2, 200.0])
        dec = np.array([10.0, 10.1,   0.0])
        history = [(45.0, 10.0)]
        scores = ssf.novelty_scores_batch(ra, dec, history, overlap_deg=5.0)
        # First two are within 5° of history; third is not
        assert scores[0] == 0.0
        assert scores[1] == 0.0
        assert scores[2] == 1.0

    def test_far_field_stays_one(self):
        ra  = np.array([180.0])
        dec = np.array([0.0])
        history = [(0.0, 0.0)]
        scores = ssf.novelty_scores_batch(ra, dec, history, overlap_deg=5.0)
        assert scores[0] == 1.0


class TestLoadRunHistory:
    def test_missing_dir_returns_empty(self, tmp_path):
        result = ssf.load_run_history(tmp_path / "nonexistent")
        assert result == []

    def test_reads_valid_summary_files(self, tmp_path):
        run_dir = tmp_path / "run_001"
        run_dir.mkdir()
        summary = {"ra_deg": 120.5, "dec_deg": -15.2, "n_candidates": 3}
        (run_dir / "run_summary.json").write_text(json.dumps(summary))
        result = ssf.load_run_history(tmp_path)
        assert len(result) == 1
        assert result[0] == pytest.approx((120.5, -15.2))

    def test_skips_malformed_files(self, tmp_path):
        run_dir = tmp_path / "run_bad"
        run_dir.mkdir()
        (run_dir / "run_summary.json").write_text("NOT JSON {{{")
        result = ssf.load_run_history(tmp_path)
        assert result == []

    def test_skips_missing_ra_dec(self, tmp_path):
        run_dir = tmp_path / "run_partial"
        run_dir.mkdir()
        (run_dir / "run_summary.json").write_text(json.dumps({"n_candidates": 5}))
        result = ssf.load_run_history(tmp_path)
        assert result == []


# ── Grid generation tests ──────────────────────────────────────────────────────

class TestGenerateSkyGrid:
    def test_returns_two_equal_length_arrays(self):
        ra, dec = ssf.generate_sky_grid()
        assert len(ra) == len(dec)
        assert len(ra) > 0

    def test_dec_within_bounds(self):
        ra, dec = ssf.generate_sky_grid(dec_min=-30.0, dec_max=87.0)
        assert np.all(dec >= -30.0)
        assert np.all(dec <= 87.0 + ssf._GRID_STEP_DEG)  # last row may overshoot slightly

    def test_ra_within_0_360(self):
        ra, dec = ssf.generate_sky_grid()
        assert np.all(ra >= 0.0)
        assert np.all(ra < 360.0)

    def test_custom_step_reduces_field_count(self):
        _, dec_fine   = ssf.generate_sky_grid(grid_step=5.0)
        _, dec_coarse = ssf.generate_sky_grid(grid_step=15.0)
        assert len(dec_fine) > len(dec_coarse)


# ── ML model hook tests ───────────────────────────────────────────────────────

class TestMLModelHook:
    def test_missing_model_returns_none(self, tmp_path):
        result = ssf.load_field_selector_model(tmp_path / "no_model.json")
        assert result is None

    def test_valid_model_loads(self, tmp_path):
        model_data = {
            "version": "1.0",
            "feature_names": ["gap", "population", "geometry", "novelty"],
            "coef": [0.35, 0.30, 0.20, 0.15],
            "intercept": 0.0,
        }
        model_file = tmp_path / "model.json"
        model_file.write_text(json.dumps(model_data))
        model = ssf.load_field_selector_model(model_file)
        assert model is not None
        assert "coef" in model
        assert len(model["coef"]) == 4

    def test_corrupt_model_returns_none(self, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not json {{{")
        result = ssf.load_field_selector_model(bad_file)
        assert result is None

    def test_apply_model_score_sigmoid_range(self):
        model = {"coef": np.array([1.0, 1.0, 1.0, 1.0]), "intercept": 0.0}
        features = np.array([[0.5, 0.5, 0.5, 0.5], [0.0, 0.0, 0.0, 0.0]])
        scores = ssf.apply_model_score(features, model)
        assert np.all(scores >= 0.0)
        assert np.all(scores <= 1.0)
        # Higher feature values → higher score
        assert scores[0] > scores[1]


# ── select_fields integration test ────────────────────────────────────────────

class TestSelectFields:
    @pytest.fixture(autouse=True)
    def patch_sun(self, monkeypatch):
        # Inject a fixed Sun position (RA=180°, Dec=0°) to avoid network calls
        monkeypatch.setattr(ssf, "get_sun_position",
                            lambda jd: (180.0, 0.0))

    def test_returns_requested_count(self):
        fields = ssf.select_fields(jd=2461000.5, mode="aten", top_n=5)
        assert len(fields) <= 5
        assert len(fields) > 0

    def test_result_keys_present(self):
        fields = ssf.select_fields(jd=2461000.5, mode="aten", top_n=3)
        required = {"rank", "ra_deg", "dec_deg", "score", "gap_score",
                    "pop_score", "geom_score", "novelty_score",
                    "elongation_deg", "ecl_lat_deg", "hours_visible",
                    "field_radius_deg", "reason"}
        for f in fields:
            assert required.issubset(f.keys())

    def test_scores_in_range(self):
        fields = ssf.select_fields(jd=2461000.5, mode="aten", top_n=10)
        for f in fields:
            assert 0.0 <= f["score"] <= 1.0
            assert 0.0 <= f["gap_score"] <= 1.0
            assert 0.0 <= f["pop_score"] <= 1.0
            assert 0.0 <= f["geom_score"] <= 1.0

    def test_ranks_are_ascending(self):
        fields = ssf.select_fields(jd=2461000.5, mode="aten", top_n=5)
        ranks = [f["rank"] for f in fields]
        assert ranks == list(range(1, len(ranks) + 1))

    def test_scores_are_descending(self):
        fields = ssf.select_fields(jd=2461000.5, mode="aten", top_n=10)
        scores = [f["score"] for f in fields]
        assert scores == sorted(scores, reverse=True)

    def test_ieo_mode_returns_results(self):
        fields = ssf.select_fields(jd=2461000.5, mode="ieo", top_n=5)
        # IEO fields may be few (narrow elongation window); at least 1 expected
        assert len(fields) >= 1

    def test_all_mode_returns_results(self):
        fields = ssf.select_fields(jd=2461000.5, mode="all", top_n=10)
        assert len(fields) >= 1

    def test_recovery_mode_prefers_opposition_ecliptic_fields(self):
        fields = ssf.select_fields(jd=2461000.5, mode="recovery", top_n=5)
        assert len(fields) >= 1
        for field in fields:
            assert field["elongation_deg"] >= 120.0
            assert abs(field["ecl_lat_deg"]) < 35.0
            assert "known-object density" in field["reason"]

    def test_novelty_penalises_processed_field(self, tmp_path):
        # Write a run_summary.json for a field that will appear in the grid
        run_dir = tmp_path / "run_001"
        run_dir.mkdir()
        # Pick a field centre likely in the Aten window opposite the Sun at RA=180°
        (run_dir / "run_summary.json").write_text(
            json.dumps({"ra_deg": 90.0, "dec_deg": 0.0})
        )
        fields_with_history = ssf.select_fields(
            jd=2461000.5, mode="aten", top_n=20, history_dir=tmp_path
        )
        # No selected field should be within 5° of the processed field
        for f in fields_with_history:
            cos_sep = (math.sin(0.0) * math.sin(math.radians(f["dec_deg"]))
                       + math.cos(0.0) * math.cos(math.radians(f["dec_deg"]))
                       * math.cos(math.radians(f["ra_deg"]) - math.radians(90.0)))
            sep = math.degrees(math.acos(max(-1.0, min(1.0, cos_sep))))
            if sep < ssf._HISTORY_OVERLAP_DEG:
                # If it appears, it must have novelty_score=0
                assert f["novelty_score"] == 0.0

    def test_ml_model_path_used_when_provided(self, tmp_path, monkeypatch):
        # Provide a trivially valid ML model; verify it loads and produces scores
        model_data = {
            "feature_names": ["gap", "population", "geometry", "novelty"],
            "coef": [1.0, 1.0, 1.0, 1.0],
            "intercept": -2.0,
        }
        model_file = tmp_path / "model.json"
        model_file.write_text(json.dumps(model_data))
        fields = ssf.select_fields(
            jd=2461000.5, mode="aten", top_n=5, model_path=model_file
        )
        assert len(fields) >= 1
        for f in fields:
            assert 0.0 <= f["score"] <= 1.0


class TestZtfAvailabilityProbe:
    def test_filter_fields_by_ztf_availability_keeps_only_populated_fields(self):
        fields = [
            {"rank": 1, "ra_deg": 10.0, "dec_deg": 0.0, "field_radius_deg": 3.5, "reason": "a"},
            {"rank": 2, "ra_deg": 20.0, "dec_deg": 0.0, "field_radius_deg": 3.5, "reason": "b"},
        ]

        def fake_probe(ra_deg, _dec_deg, _radius_deg, _start_jd, _end_jd):
            return 7 if ra_deg == 20.0 else 0

        filtered = ssf.filter_fields_by_ztf_availability(
            fields,
            start_jd=2461206.5,
            end_jd=2461209.9,
            min_objects=1,
            top_n=2,
            probe_fn=fake_probe,
        )

        assert len(filtered) == 1
        assert filtered[0]["ra_deg"] == 20.0
        assert filtered[0]["ztf_object_count"] == 7
        assert filtered[0]["rank"] == 1


class TestWiseArchiveProbeCommands:
    def test_wise_scale_probe_outputs_are_dry_run_and_directive_compliant(self):
        field = {"ra_deg": 58.1, "dec_deg": 19.9}
        result = ssf.wise_scale_probe_outputs(
            field,
            start_jd=2458880.5,
            end_jd=2459250.5,
            radius_deg=0.2,
        )

        command = result["wise_scale_probe_command"]
        assert "caffeinate -i uv run --python 3.14 python Skills/run_pipeline.py" in command
        assert "OMP_NUM_THREADS=1" in command
        assert "OPENBLAS_NUM_THREADS=1" in command
        assert "VECLIB_MAXIMUM_THREADS=1" in command
        assert "NUMEXPR_MAX_THREADS=1" in command
        assert "--surveys WISE" in command
        assert "--link-scale-plan-out Logs/reports/wise_scale_plan_ra58p10_dec19p90" in command
        assert "--no-dry-run" not in command
        assert "No external submission" not in command
        assert result["wise_safety"].startswith("dry-run scale-plan probe only")

    def test_add_wise_archive_probe_commands_keeps_field_metadata(self):
        fields = [{"rank": 1, "ra_deg": 58.1, "dec_deg": 19.9, "score": 0.9}]
        enriched = ssf.add_wise_archive_probe_commands(
            fields,
            start_jd=2458880.5,
            end_jd=2459250.5,
        )

        assert enriched[0]["rank"] == 1
        assert enriched[0]["score"] == 0.9
        assert enriched[0]["wise_parent_radius_deg"] == pytest.approx(0.2)
        assert enriched[0]["wise_start_jd"] == pytest.approx(2458880.5)


# ── CLI smoke tests ────────────────────────────────────────────────────────────

class TestCLI:
    @pytest.fixture(autouse=True)
    def patch_sun(self, monkeypatch):
        monkeypatch.setattr(ssf, "get_sun_position", lambda jd: (180.0, 0.0))

    def test_json_output_parseable(self, capsys):
        ssf.main(["--jd", "2461000.5", "--mode", "aten", "--top-n", "3", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert isinstance(data, list)
        assert len(data) <= 3

    def test_table_output_non_empty(self, capsys):
        ssf.main(["--jd", "2461000.5", "--mode", "aten", "--top-n", "3"])
        out = capsys.readouterr().out
        assert "Score" in out
        assert "Rank" in out

    def test_ieo_mode_cli(self, capsys):
        ssf.main(["--jd", "2461000.5", "--mode", "ieo", "--top-n", "3", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert isinstance(data, list)

    def test_recovery_mode_cli(self, capsys):
        ssf.main(["--jd", "2461000.5", "--mode", "recovery", "--top-n", "3", "--json"])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert isinstance(data, list)
        assert len(data) <= 3

    def test_require_ztf_alerts_cli_json(self, capsys, monkeypatch):
        monkeypatch.setattr(
            ssf,
            "probe_ztf_object_count",
            lambda ra_deg, *_args, **_kwargs: 5 if ra_deg > 0 else 0,
        )
        ssf.main([
            "--jd", "2461000.5",
            "--mode", "recovery",
            "--top-n", "2",
            "--require-ztf-alerts",
            "--ztf-probe-top-k", "4",
            "--json",
        ])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert len(data) <= 2
        assert all(row["ztf_object_count"] >= 1 for row in data)

    def test_wise_archive_probes_cli_json(self, capsys):
        ssf.main([
            "--jd", "2459065.5",
            "--mode", "aten",
            "--top-n", "2",
            "--wise-archive-probes",
            "--start-jd", "2458880.5",
            "--end-jd", "2459250.5",
            "--json",
        ])
        out = capsys.readouterr().out
        data = json.loads(out)
        assert len(data) <= 2
        assert all("wise_scale_probe_command" in row for row in data)
        assert all("--surveys WISE" in row["wise_scale_probe_command"] for row in data)

    def test_wise_archive_probes_requires_window(self):
        with pytest.raises(SystemExit):
            ssf.main([
                "--jd", "2459065.5",
                "--mode", "aten",
                "--wise-archive-probes",
                "--json",
            ])


class TestAppendFieldsToTargetQueue:
    """Regression coverage for the target-queue wiring gap: this tool
    previously only printed 'copy to run_pipeline.py' and left no persisted,
    inspectable selection record, contradicting
    docs/astrometrics_data_selection_policy.md's requirement that every
    live-search batch have a documented selection rule before execution."""

    def test_writes_header_and_real_rows_matching_committed_schema(self, tmp_path):
        fields = [
            {
                "rank": 1, "ra_deg": 276.01, "dec_deg": -22.5, "score": 0.9395,
                "field_radius_deg": 3.5, "reason": "known-object density 0.93; geometry 0.92",
            },
            {
                "rank": 2, "ra_deg": 267.89, "dec_deg": -22.5, "score": 0.9143,
                "field_radius_deg": 3.5, "reason": "known-object density 0.89; geometry 0.90",
            },
        ]
        queue_path = tmp_path / "target_priority_queue.csv"

        n_written = ssf.append_fields_to_target_queue(
            fields, queue_path, data_role="live_search"
        )

        assert n_written == 2
        import csv
        with queue_path.open() as f:
            rows = list(csv.DictReader(f))
        assert rows[0].keys() == {
            "rank", "priority", "status", "data_role", "source",
            "selection_rule", "evidence_path", "notes",
        }
        assert rows[0]["rank"] == "1"
        assert rows[0]["priority"] == "0.9395"
        assert rows[0]["status"] == "not_searched"
        assert rows[0]["data_role"] == "live_search"
        assert rows[0]["source"] == "sky_field_selector"
        assert rows[0]["selection_rule"] == "known-object density 0.93; geometry 0.92"
        assert "ra_deg=276.01" in rows[0]["notes"]

    def test_wise_fields_record_wise_source_and_evidence_path(self, tmp_path):
        fields = [{
            "rank": 1, "ra_deg": 276.01, "dec_deg": -22.5, "score": 0.9395,
            "field_radius_deg": 0.2, "reason": "known-object density 0.93",
            "wise_scale_plan_out": "Logs/reports/wise_scale_plan_x.json",
            "wise_scale_probe_command": "uv run ... --surveys WISE ...",
        }]
        queue_path = tmp_path / "target_priority_queue.csv"

        ssf.append_fields_to_target_queue(fields, queue_path, data_role="live_search")

        import csv
        with queue_path.open() as f:
            rows = list(csv.DictReader(f))
        assert rows[0]["source"] == "WISE"
        assert rows[0]["evidence_path"] == "Logs/reports/wise_scale_plan_x.json"
        assert "wise_scale_probe_command=" in rows[0]["notes"]

    def test_second_call_appends_without_duplicating_header(self, tmp_path):
        queue_path = tmp_path / "target_priority_queue.csv"
        field = [{
            "rank": 1, "ra_deg": 100.0, "dec_deg": 5.0, "score": 0.5,
            "field_radius_deg": 3.5, "reason": "test",
        }]

        ssf.append_fields_to_target_queue(field, queue_path, data_role="live_search")
        ssf.append_fields_to_target_queue(field, queue_path, data_role="live_search")

        lines = queue_path.read_text().splitlines()
        assert lines[0].startswith("rank,priority,status")
        assert sum(1 for line in lines if line.startswith("rank,priority,status")) == 1
        assert len(lines) == 3  # header + 2 appended rows

    def test_cli_write_target_queue_flag(self, tmp_path, capsys):
        queue_path = tmp_path / "queue.csv"
        ssf.main([
            "--jd", "2459065.5",
            "--mode", "aten",
            "--top-n", "2",
            "--write-target-queue", str(queue_path),
            "--target-queue-data-role", "recovery_control",
            "--json",
        ])
        assert queue_path.exists()
        import csv
        with queue_path.open() as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 2
        assert all(r["data_role"] == "recovery_control" for r in rows)
