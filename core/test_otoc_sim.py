import numpy as np
import pytest

from otoc_sim import otoc_F


def test_no_transverse_field_only_the_kicked_site_flips():
    F = otoc_F(6, 4, theta_x=0.0, theta_zz=0.7)
    expected = np.ones(6)
    expected[3] = -1
    assert np.allclose(F, expected[:, None])


@pytest.mark.parametrize("order", ["zz_x", "x_zz"])
def test_clifford_coupling_never_spreads(order):
    F = otoc_F(8, 10, theta_x=0.3 * np.pi, theta_zz=np.pi, order=order)
    off = np.delete(F, 4, axis=0)
    assert np.allclose(off, 1)


def test_light_cone_one_site_per_step():
    F = otoc_F(10, 6, theta_x=0.3 * np.pi, theta_zz=0.35 * np.pi, order="zz_x")
    k = 5
    for i in range(10):
        for t in range(1, 7):
            if abs(i - k) > t:
                assert abs(F[i, t - 1] - 1) < 1e-12


def test_real_when_theta_z_zero_and_bounded():
    F = otoc_F(8, 8, theta_x=0.3 * np.pi, theta_zz=0.35 * np.pi)
    assert np.abs(F.imag).max() < 1e-12
    assert np.abs(F).max() <= 1 + 1e-12
