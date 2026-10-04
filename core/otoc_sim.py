"""Independent numpy statevector OTOC for the kicked-Ising Floquet chain (classical cross-check of otoc-echo-v1).

Model (as inferred from the engine's documented params and its returned X_kick / X_ref observables):
    |psi0> = |+>^n
    one Floquet layer L = RZ(theta_z)^n . RX(theta_x)^n . RZZ(theta_zz) on every nearest-neighbour bond   (order="zz_x")
                    or  RZ . RZZ . RX                                                                   (order="x_zz")
    U(t) = L^t,  W(t) = U(t)^dag Z_k U(t)
    F_i(t) = <psi0| W(t) X_i W(t) |psi0> / <psi0| X_i |psi0>         (denominator = 1 for |+>^n)
Qiskit conventions: RX(a) = exp(-i a X / 2), RZZ(a) = exp(-i a Z Z / 2), RZ(a) = exp(-i a Z / 2).
"""
import numpy as np


def _zz_phase(n, theta_zz):
    idx = np.arange(2 ** n)
    bits = (idx[:, None] >> (n - 1 - np.arange(n))) & 1   # bits[:, q] = state of qubit q (qubit 0 = leftmost axis)
    z = 1 - 2 * bits
    s = (z[:, :-1] * z[:, 1:]).sum(axis=1)
    return np.exp(-0.5j * theta_zz * s), z


def _apply_1q(psi, n, m):
    """Apply the same 2x2 matrix m to every qubit of a flat statevector."""
    psi = psi.reshape((2,) * n)
    for q in range(n):
        psi = np.moveaxis(np.tensordot(m, psi, axes=([1], [q])), 0, q)
    return psi.reshape(-1)


def _rx(a):
    c, s = np.cos(a / 2), np.sin(a / 2)
    return np.array([[c, -1j * s], [-1j * s, c]])


def otoc_F(n, depth, theta_x, theta_zz, theta_z=0.0, kick_site=None, order="zz_x"):
    """Return complex F[site, t] with t = 1..depth, shape (n, depth)."""
    k = n // 2 if kick_site is None else kick_site
    zz, z = _zz_phase(n, theta_zz)
    rz = np.exp(-0.5j * theta_z * z.sum(axis=1))
    RX, RXd = _rx(theta_x), _rx(-theta_x)

    def layer(psi):
        if order == "zz_x":
            return rz * _apply_1q(zz * psi, n, RX)
        return rz * (zz * _apply_1q(psi, n, RX))

    def layer_dag(psi):
        psi = np.conj(rz) * psi
        if order == "zz_x":
            return np.conj(zz) * _apply_1q(psi, n, RXd)
        return _apply_1q(np.conj(zz) * psi, n, RXd)

    psi0 = np.full(2 ** n, 2 ** (-n / 2), dtype=complex)
    kick = z[:, k].astype(float)
    F = np.empty((n, depth), dtype=complex)
    fwd = psi0.copy()
    for t in range(1, depth + 1):
        fwd = layer(fwd)
        psi = kick * fwd
        for _ in range(t):
            psi = layer_dag(psi)
        F[:, t - 1] = _expect_x(psi, n)
    return F


def _expect_x(psi, n):
    """<X_q> for every qubit q."""
    t = psi.reshape((2,) * n)
    out = np.empty(n, dtype=complex)
    for q in range(n):
        flipped = np.flip(t, axis=q)
        out[q] = np.vdot(t, flipped)
    return out
