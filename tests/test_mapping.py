from pathlib import Path

import numpy as np
import pytest

from scrambled import mapping, otoc

ROOT = Path(__file__).resolve().parents[1]


def _map(name):
    return otoc.load(ROOT / "probes" / f"otoc_{name}.json")


def test_control_run_flips_only_the_kick_strip_and_nothing_blurs():
    m = _map("control_clifford")
    for t in np.linspace(1, m.depth, 40):
        states = mapping.strip_states(m.F, t)
        assert [s.flipped for s in states] == [i == m.kick_site for i in range(m.n_sites)]
        assert all(s.blur == 0 and s.morph == 0 for s in states)


def test_unit_modulus_echo_is_sharp():
    F = np.exp(1j * np.zeros((5, 8)))
    F[2, 3:] = -1
    for t in (1, 3.5, 8):
        for s in mapping.strip_states(F, t):
            assert s.blur == 0 and s.morph == 0


def test_scrambling_run_starts_sharp_and_ends_scrambled_outside_nothing():
    m = _map("scrambling")
    first = mapping.strip_states(m.F, 1)
    # at t=1 only the kick and its two neighbours are inside the light cone
    assert [s.blur > 0.01 for s in first] == [i in (5, 6, 7) for i in range(12)]
    last = mapping.strip_states(m.F, m.depth)
    assert all(s.morph > 0.5 for s in last), "every strip should be well into the scramble by the last echo step"


def test_scramble_progress_is_monotone_and_bounded():
    m = _map("scrambling")
    ts = np.linspace(1, m.depth, 200)
    prog = np.array([mapping.scramble_progress(m.F, t) for t in ts])
    assert (np.diff(prog, axis=0) >= -1e-12).all()
    assert prog.min() >= 0 and prog.max() <= 1
    assert np.allclose(prog[0], 0)


def test_F_at_interpolates_between_echo_steps_and_clamps():
    F = np.array([[1, -1, 0.5]], dtype=complex)
    assert mapping.F_at(F, 1)[0] == pytest.approx(1)
    assert mapping.F_at(F, 1.4)[0] == pytest.approx(1)      # a clean flip keeps |F| = 1
    assert mapping.F_at(F, 1.6)[0] == pytest.approx(-1)
    assert abs(mapping.F_at(F, 2.5)[0]) == pytest.approx(0.75)
    assert mapping.F_at(F, 3)[0] == pytest.approx(0.5)
    assert mapping.F_at(F, 99)[0] == pytest.approx(0.5) and mapping.F_at(F, -3)[0] == pytest.approx(1)


def test_strip_edges_cover_the_width_exactly():
    e = mapping.strip_edges(406, 12)
    assert e[0] == 0 and e[-1] == 406 and len(e) == 13 and (np.diff(e) > 0).all()
