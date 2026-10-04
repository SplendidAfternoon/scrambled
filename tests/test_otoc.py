import json
import math
from pathlib import Path

import numpy as np
import pytest

from scrambled import otoc

ROOT = Path(__file__).resolve().parents[1]
PROBES = ROOT / "probes"


def _rec(name):
    return json.loads((PROBES / f"otoc_{name}.json").read_text(encoding="utf-8"))


def test_parse_record_gives_12x32_complex_map_with_centre_kick():
    m = otoc.parse_record(_rec("scrambling"))
    assert m.F.shape == (12, 32)
    assert np.iscomplexobj(m.F)
    assert m.kick_site == 6
    assert m.source == "atlas"
    assert m.job_id == "8df5cfa2-e57c-43a8-a93a-63975efd252c"


def test_clifford_control_flips_only_the_kicked_site():
    m = otoc.parse_record(_rec("control_clifford"))
    expected = np.ones((12, 32))
    expected[6] = -1
    np.testing.assert_allclose(m.F, expected, atol=1e-9)


def test_light_cone_matches_engine_light_cone():
    rec = _rec("scrambling")
    m = otoc.parse_record(rec)
    engine_cone = np.array(rec["response"]["result"]["output"]["extras"]["light_cone"], dtype=bool)
    np.testing.assert_array_equal(otoc.light_cone(m.F), engine_cone)
    # one site per echo step on each side of the kick
    assert list(otoc.arrival_steps(m.F)) == [6, 5, 4, 3, 2, 1, 1, 1, 2, 3, 4, 5]


def test_classical_simulation_reproduces_the_atlas_emulator_measurement():
    params = otoc.OTOCParams()  # defaults = the measured scrambling run
    sim = otoc.simulate(params)
    atlas = otoc.parse_record(_rec("scrambling"))
    assert sim.source == "classical"
    np.testing.assert_allclose(sim.F, atlas.F, atol=1e-9)


def test_classical_simulation_of_clifford_control():
    sim = otoc.simulate(otoc.OTOCParams(theta_zz=math.pi))
    atlas = otoc.parse_record(_rec("control_clifford"))
    np.testing.assert_allclose(sim.F, atlas.F, atol=1e-9)


def test_classical_mode_refuses_unverified_conventions():
    with pytest.raises(NotImplementedError):
        otoc.simulate(otoc.OTOCParams(theta_z=0.1))
    with pytest.raises(NotImplementedError):
        otoc.simulate(otoc.OTOCParams(disorder=0.2))


def test_default_engine_params_hit_the_existing_measurement_cache():
    from scrambled.client import cache_key
    key = cache_key("otoc-echo-v1", otoc.OTOCParams().engine_params())
    assert (ROOT / "cache" / "otoc-echo-v1" / f"{key}.json").exists()
    key_c = cache_key("otoc-echo-v1", otoc.OTOCParams(theta_zz=math.pi).engine_params())
    assert (ROOT / "cache" / "otoc-echo-v1" / f"{key_c}.json").exists()


def test_map_roundtrips_through_json(tmp_path):
    m = otoc.parse_record(_rec("scrambling"))
    p = tmp_path / "map.json"
    m.save(p)
    back = otoc.load(p)
    np.testing.assert_allclose(back.F, m.F)
    assert back.kick_site == m.kick_site and back.source == "atlas" and back.job_id == m.job_id
    # a raw job record loads too
    raw = otoc.load(PROBES / "otoc_scrambling.json")
    np.testing.assert_allclose(raw.F, m.F)


def test_parse_angle_accepts_pi_multiples():
    assert otoc.parse_angle("0.3pi") == pytest.approx(0.3 * math.pi)
    assert otoc.parse_angle("pi") == pytest.approx(math.pi)
    assert otoc.parse_angle("0.5") == 0.5
    with pytest.raises(ValueError):
        otoc.parse_angle("abc")
