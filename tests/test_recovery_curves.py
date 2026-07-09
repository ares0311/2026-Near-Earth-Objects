from __future__ import annotations

from recovery_curves import recovery_curve_report


def test_recovery_curve_report_bins_rates_by_parameter() -> None:
    records = [
        {
            "mag": 18.5,
            "motion_arcsec_per_hr": 0.8,
            "n_observations": 6,
            "n_nights": 3,
            "detected": True,
            "linked": True,
            "scored": True,
        },
        {
            "mag": 19.5,
            "motion_arcsec_per_hr": 3.0,
            "n_observations": 6,
            "n_nights": 3,
            "detected": True,
            "linked": False,
            "scored": False,
        },
    ]

    report = recovery_curve_report(records)
    mag_bins = {row["bin"]: row for row in report["curves"]["mag"]}
    obs_bins = {row["bin"]: row for row in report["curves"]["n_observations"]}

    assert report["passed"] is True
    assert mag_bins["[18,20)"]["n"] == 2
    assert mag_bins["[18,20)"]["detection_rate"] == 1.0
    assert mag_bins["[18,20)"]["link_rate"] == 0.5
    assert obs_bins["[6,9)"]["score_rate"] == 0.5


def test_recovery_curve_report_fails_empty_or_missing_dimension() -> None:
    empty = recovery_curve_report([])
    missing = recovery_curve_report([{"mag": 18.0, "detected": True}])

    assert empty["passed"] is False
    assert "mag" in empty["missing_dimensions"]
    assert missing["passed"] is False
    assert "motion_arcsec_per_hr" in missing["missing_dimensions"]


def test_recovery_curve_report_ignores_out_of_range_and_nonfinite_values() -> None:
    report = recovery_curve_report(
        [
            {
                "mag": float("nan"),
                "motion_arcsec_per_hr": 1.0,
                "n_observations": 6,
                "n_nights": 3,
                "detected": True,
                "linked": True,
                "scored": True,
            }
        ]
    )
    out_of_range = recovery_curve_report(
        [
            {
                "mag": 30.0,
                "motion_arcsec_per_hr": 1.0,
                "n_observations": 6,
                "n_nights": 3,
                "detected": True,
                "linked": True,
                "scored": True,
            }
        ]
    )

    assert report["passed"] is False
    assert "mag" in report["missing_dimensions"]
    assert "mag" in out_of_range["missing_dimensions"]


def test_recovery_curve_report_includes_final_upper_edge() -> None:
    report = recovery_curve_report(
        [
            {
                "mag": 22.0,
                "motion_arcsec_per_hr": 60.0,
                "n_observations": 12,
                "n_nights": 4,
                "detected": True,
                "linked": True,
                "scored": True,
            }
        ]
    )
    mag_bins = {row["bin"]: row for row in report["curves"]["mag"]}

    assert mag_bins["[20,22)"]["n"] == 1
