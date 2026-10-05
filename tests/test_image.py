import numpy as np

from scrambled import image
from scrambled.mapping import StripState

H = W = 140


def _picture():
    y, x = np.mgrid[0:H, 0:W]
    return np.stack([x * 1.5, y * 1.5, (x + y) * 0.7], axis=-1).astype(np.float32)


def _ladders(img):
    return image.Ladders(blur=[np.full_like(img, 128.0)], morph=[np.zeros_like(img)], source="classical")


def _states(n, at):
    return [at.get(s, StripState(0.0, 0.0, False)) for s in range(n)]


def _radius_fraction():
    y, x = np.mgrid[0:H, 0:W]
    r = np.hypot(x + 0.5 - W / 2, y + 0.5 - H / 2)
    return r / r.max()


def test_strips_is_the_default_layout():
    img = _picture()
    st = _states(12, {5: StripState(1.0, 0.0, True)})
    assert np.array_equal(image.compose(img, _ladders(img), st), image.compose(img, _ladders(img), st, layout="strips"))


def test_rings_flip_only_the_kicked_disc_by_rotating_it():
    # 12 sites, kick at 6: rings at distance 0..6 from the kick, so the kicked site owns the inner 1/7 of the radius.
    img = _picture()
    out = image.compose(img, _ladders(img), _states(12, {6: StripState(0.0, 0.0, True)}), layout="rings", kick=6)
    rf = _radius_fraction()
    inner, outer = rf < 1 / 7 - 0.02, rf > 1 / 7 + 0.02
    assert np.array_equal(out[outer], img[outer])
    assert np.array_equal(out[inner], img[::-1, ::-1][inner])


def test_rings_blur_only_the_annulus_of_sites_two_away_from_the_kick():
    img = _picture()
    st = _states(12, {4: StripState(1.0, 0.0, False), 8: StripState(1.0, 0.0, False)})
    out = image.compose(img, _ladders(img), st, layout="rings", kick=6)
    rf = _radius_fraction()
    ring2 = (rf > 2 / 7 + 0.02) & (rf < 3 / 7 - 0.02)
    rest = (rf < 2 / 7 - 0.02) | (rf > 3 / 7 + 0.02)
    assert np.allclose(out[ring2], 128.0)
    assert np.array_equal(out[rest], img[rest])


def test_rings_from_an_edge_kick_give_one_ring_per_site():
    img = _picture()
    st = _states(12, {11: StripState(1.0, 0.0, False)})
    out = image.compose(img, _ladders(img), st, layout="rings", kick=0)
    rf = _radius_fraction()
    assert np.allclose(out[rf > 11 / 12 + 0.01], 128.0)
    assert np.array_equal(out[rf < 11 / 12 - 0.01], img[rf < 11 / 12 - 0.01])
