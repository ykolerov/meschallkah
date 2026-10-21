import numpy as np
import pytest

from disc_rate import crossing_times, rate_from_crossings


def test_synthetic_600_rpm_240fps():
    fps = 240
    t = np.arange(0, 8, 1 / fps)
    # 10 revolutions/s -> 600 rpm; 24 video frames/revolution
    signal = 100 + 80 * np.sin(2 * np.pi * 10 * t)
    edges = crossing_times(signal, fps)
    rpm, standard_error, max_residual = rate_from_crossings(edges)
    assert rpm == pytest.approx(600, abs=0.2)
    assert standard_error >= 0
    assert max_residual < 0.005


def test_no_video_contrast():
    with pytest.raises(ValueError):
        crossing_times(np.ones(100), 240)


def test_insufficient_crossings():
    with pytest.raises(ValueError):
        rate_from_crossings([0.1])
