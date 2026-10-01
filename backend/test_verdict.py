"""Unit tests for every rule in verdict.py. Run with:
    backend/.venv/Scripts/python -m pytest backend/test_verdict.py -v
or plainly:
    backend/.venv/Scripts/python backend/test_verdict.py
"""

from verdict import ATEEQQ_WEIGHT, PLATFORM_MAX_CONFIDENCE, SDXL_WEIGHT, verdict


def frame(ateeqq, sdxl):
    return {"ateeqq": ateeqq, "sdxl_detector": sdxl}


def weighted(ateeqq, sdxl):
    """content_ai for a single frame under the current model weights, for test expectations."""
    return ATEEQQ_WEIGHT * ateeqq + SDXL_WEIGHT * sdxl


def test_disclosed_always_wins():
    r = verdict([frame(0.1, 0.1)], disclosed=True)
    assert r["verdict"] == "AI-Generated (creator disclosed)"
    assert r["confidence"] == 95


def test_image_likely_real():
    r = verdict([frame(0.1, 0.15)])
    assert r["verdict"] == "Likely Real"
    assert r["confidence"] == min(95, round((1 - weighted(0.1, 0.15)) * 100))


def test_image_likely_ai():
    r = verdict([frame(0.9, 0.85)])
    assert r["verdict"] == "Likely AI-Generated"
    assert r["confidence"] == min(95, round(weighted(0.9, 0.85) * 100))


def test_image_close_call_leans_ai():
    # content_ai exactly 0.5 -> a tie leans AI-generated, with low confidence and a caveat.
    r = verdict([frame(0.5, 0.5)])
    assert r["verdict"] == "Likely AI-Generated"
    assert r["confidence"] == 50
    assert any("close call" in reason for reason in r["reasons"])


def test_image_close_call_leans_real():
    # content_ai = 0.4 -> closer to real, decisive lean rather than "Unsure".
    r = verdict([frame(0.4, 0.4)])
    assert r["verdict"] == "Likely Real"
    assert r["confidence"] == 60
    assert any("close call" in reason for reason in r["reasons"])


def test_image_single_frame_model_disagreement():
    # |0.9 - 0.2| = 0.7 > 0.6 -> still Unsure, this is genuinely extreme disagreement.
    r = verdict([frame(0.9, 0.2)])
    assert r["verdict"] == "Unsure"
    assert r["confidence"] is None


def test_image_moderate_disagreement_no_longer_unsure():
    # |0.8 - 0.3| = 0.5, under the new 0.6 threshold -> decisive call, not "Unsure".
    r = verdict([frame(0.8, 0.3)])
    assert r["verdict"] != "Unsure"


def test_video_three_frames_all_ai():
    frames = [frame(0.8, 0.85), frame(0.9, 0.88), frame(0.95, 0.9)]
    r = verdict(frames)
    assert r["verdict"] == "Likely AI-Generated"
    assert r["confidence"] is not None
    assert r["confidence"] <= 95


def test_video_three_frames_all_real():
    frames = [frame(0.05, 0.1), frame(0.1, 0.05), frame(0.15, 0.1)]
    r = verdict(frames)
    assert r["verdict"] == "Likely Real"


def test_video_genuine_model_disagreement():
    # Both models consistently disagree with each other across all 3 frames
    # (ateeqq median 0.9 vs sdxl median 0.1) -> genuine disagreement, Unsure.
    frames = [frame(0.9, 0.1), frame(0.85, 0.15), frame(0.95, 0.05)]
    r = verdict(frames)
    assert r["verdict"] == "Unsure"
    assert any("disagreed overall" in reason for reason in r["reasons"])


def test_video_single_noisy_frame_does_not_flip_verdict():
    # Matches a real pattern found via the feed-auditor: ateeqq spikes on one frame
    # (0.99) while sdxl and ateeqq's own other frames stay low/consistent. Taking each
    # model's median across frames absorbs the one-off spike instead of forcing "Unsure".
    frames = [frame(0.05, 0.08), frame(0.99, 0.02), frame(0.06, 0.05)]
    r = verdict(frames)
    # ateeqq median = 0.06, sdxl median = 0.05 -> models agree overall, despite frame 2.
    assert r["verdict"] == "Likely Real"
    assert r["verdict"] != "Unsure"


def test_confidence_never_above_95():
    r = verdict([frame(1.0, 1.0)])
    assert r["confidence"] <= 95
    r2 = verdict([frame(0.0, 0.0)])
    assert r2["confidence"] <= 95


def test_instagram_platform_confidence_cap():
    # A real audit of 8 Reels from a logged-in account (2026-09-30) found both detectors
    # agree confidently (95%+) on content later confirmed to likely be real — Instagram
    # gets a lower confidence ceiling as a result, without changing the label itself.
    ig_cap = PLATFORM_MAX_CONFIDENCE["instagram-reel"]
    r = verdict([frame(1.0, 1.0)], platform="instagram-reel")
    assert r["verdict"] == "Likely AI-Generated"
    assert r["confidence"] == ig_cap
    assert any("capped" in reason for reason in r["reasons"])

    # The same scores on an unspecified platform still get the normal, higher cap.
    r2 = verdict([frame(1.0, 1.0)])
    assert r2["confidence"] == 95


def test_default_cap_does_not_falsely_claim_platform_testing():
    # Regression test: hitting the ordinary 95% ceiling (no platform override at all)
    # must NOT say "real testing on this platform found..." — that claim is only true
    # when an actual platform-specific cap from PLATFORM_MAX_CONFIDENCE applied.
    r = verdict([frame(1.0, 1.0)])
    assert r["confidence"] == 95
    assert not any("platform" in reason.lower() for reason in r["reasons"])


def test_instagram_disclosed_confidence_unaffected_by_platform_cap():
    # Disclosure isn't a detector reading, so the platform's lower ceiling doesn't apply.
    r = verdict([frame(0.1, 0.1)], disclosed=True, platform="instagram-reel")
    assert r["confidence"] == 95


def test_factcheck_flag_added_when_false():
    r = verdict([frame(0.9, 0.9)], factcheck={"rating": "False", "url": "http://example.com/x"})
    assert r["factcheck"] is not None
    assert r["factcheck"]["label"] == "Fact-checked: False"
    assert r["factcheck"]["url"] == "http://example.com/x"


def test_factcheck_flag_absent_when_true_or_missing():
    r = verdict([frame(0.9, 0.9)], factcheck={"rating": "True", "url": "http://example.com/x"})
    assert r["factcheck"] is None
    r2 = verdict([frame(0.9, 0.9)], factcheck=None)
    assert r2["factcheck"] is None


def test_reason_always_present():
    for frames in (
        [frame(0.1, 0.1)],
        [frame(0.9, 0.9)],
        [frame(0.5, 0.5)],
        [frame(0.9, 0.1)],
    ):
        r = verdict(frames)
        assert len(r["reasons"]) >= 1


if __name__ == "__main__":
    import sys
    import inspect

    test_funcs = [
        (name, func)
        for name, func in list(globals().items())
        if name.startswith("test_") and inspect.isfunction(func)
    ]
    failed = 0
    for name, func in test_funcs:
        try:
            func()
            print(f"PASS: {name}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL: {name} - {e}")
    print(f"\n{len(test_funcs) - failed}/{len(test_funcs)} tests passed")
    sys.exit(1 if failed else 0)
