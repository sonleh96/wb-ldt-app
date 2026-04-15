from src.analytics.gap_analysis import GapInput, compute_indicator_gaps


def test_compute_indicator_gaps_handles_lower_is_better() -> None:
    gaps = compute_indicator_gaps(
        [
            GapInput(
                indicator_id="pm25",
                indicator_name="PM 2.5 concentration",
                municipality_value=18.0,
                national_value=14.0,
                higher_is_better=False,
                priority_weight=1.5,
            )
        ]
    )

    assert len(gaps) == 1
    assert gaps[0].gap_value == 4.0
    assert round(gaps[0].gap_percent, 3) == round(4.0 / 14.0, 3)


def test_compute_indicator_gaps_handles_higher_is_better() -> None:
    gaps = compute_indicator_gaps(
        [
            GapInput(
                indicator_id="waste_points",
                indicator_name="Waste disposal points per 10000",
                municipality_value=9.5,
                national_value=10.0,
                higher_is_better=True,
                priority_weight=1.0,
            )
        ]
    )

    assert len(gaps) == 1
    assert gaps[0].gap_value == 0.5
