import numpy as np

from dsp import SR, loudness, master, tap_ir, true_peak_db


def test_tap_ir_places_signed_taps_at_each_step():
    F = np.ones((4, 3))
    F[1] = -1
    ir = tap_ir(F, step_s=0.01, sr=1000)
    assert ir.shape == (31, 2)
    assert np.allclose(ir[0], 0)
    # constant-power panning: L^2 + R^2 of each tap equals (1/n)^2; sum of signed amplitudes is (4-2)/4
    mono = np.array([F[s, 0] / 4 * np.cos(s / 3 * np.pi / 2) for s in range(4)]).sum()
    assert np.isclose(ir[10, 0], mono)
    assert np.count_nonzero(np.abs(ir).sum(axis=1)) == 3


def test_scrambled_ir_is_quieter_than_regular():
    rng = np.random.default_rng(0)
    regular = tap_ir(np.ones((12, 32)), 0.01, sr=1000)
    scrambled = tap_ir(rng.uniform(-0.3, 0.3, (12, 32)), 0.01, sr=1000)
    assert np.abs(scrambled).sum() < 0.5 * np.abs(regular).sum()


def test_master_hits_target_without_clipping():
    rng = np.random.default_rng(1)
    t = np.arange(SR * 10) / SR
    x = np.stack([np.sin(2 * np.pi * 220 * t), np.sin(2 * np.pi * 330 * t)], 1) * 0.05
    x[SR * 3:SR * 3 + 200] += rng.standard_normal((200, 2)) * 2  # transient that must be limited
    y = master(x)
    assert abs(loudness(y) + 14) < 0.6
    assert true_peak_db(y) <= -0.9
