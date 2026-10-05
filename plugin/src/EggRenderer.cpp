#include "EggRenderer.hpp"
#include "ShellLut.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>

#ifdef _WIN32
# ifndef WIN32_LEAN_AND_MEAN
#  define WIN32_LEAN_AND_MEAN
# endif
# ifndef NOMINMAX
#  define NOMINMAX
# endif
# include <windows.h>
#endif
#include <GL/gl.h>
#include <GL/glext.h>

namespace se {

namespace {

constexpr float kPi = 3.14159265f;

// ------------------------------------------------------------------------------------------------ GL 2.0 entry points

struct GLApi {
    PFNGLCREATESHADERPROC CreateShader = nullptr;
    PFNGLSHADERSOURCEPROC ShaderSource = nullptr;
    PFNGLCOMPILESHADERPROC CompileShader = nullptr;
    PFNGLGETSHADERIVPROC GetShaderiv = nullptr;
    PFNGLGETSHADERINFOLOGPROC GetShaderInfoLog = nullptr;
    PFNGLDELETESHADERPROC DeleteShader = nullptr;
    PFNGLCREATEPROGRAMPROC CreateProgram = nullptr;
    PFNGLATTACHSHADERPROC AttachShader = nullptr;
    PFNGLBINDATTRIBLOCATIONPROC BindAttribLocation = nullptr;
    PFNGLLINKPROGRAMPROC LinkProgram = nullptr;
    PFNGLGETPROGRAMIVPROC GetProgramiv = nullptr;
    PFNGLGETPROGRAMINFOLOGPROC GetProgramInfoLog = nullptr;
    PFNGLDELETEPROGRAMPROC DeleteProgram = nullptr;
    PFNGLUSEPROGRAMPROC UseProgram = nullptr;
    PFNGLGETUNIFORMLOCATIONPROC GetUniformLocation = nullptr;
    PFNGLUNIFORM1FPROC Uniform1f = nullptr;
    PFNGLUNIFORM1IPROC Uniform1i = nullptr;
    PFNGLUNIFORM2FPROC Uniform2f = nullptr;
    PFNGLUNIFORM3FPROC Uniform3f = nullptr;
    PFNGLUNIFORM4FVPROC Uniform4fv = nullptr;
    PFNGLUNIFORMMATRIX4FVPROC UniformMatrix4fv = nullptr;
    PFNGLENABLEVERTEXATTRIBARRAYPROC EnableVertexAttribArray = nullptr;
    PFNGLDISABLEVERTEXATTRIBARRAYPROC DisableVertexAttribArray = nullptr;
    PFNGLVERTEXATTRIBPOINTERPROC VertexAttribPointer = nullptr;
    PFNGLGENBUFFERSPROC GenBuffers = nullptr;
    PFNGLBINDBUFFERPROC BindBuffer = nullptr;
    PFNGLBUFFERDATAPROC BufferData = nullptr;
    PFNGLDELETEBUFFERSPROC DeleteBuffers = nullptr;
    PFNGLACTIVETEXTUREPROC ActiveTexture = nullptr;
    // optional (supersampling)
    PFNGLGENFRAMEBUFFERSPROC GenFramebuffers = nullptr;
    PFNGLBINDFRAMEBUFFERPROC BindFramebuffer = nullptr;
    PFNGLFRAMEBUFFERTEXTURE2DPROC FramebufferTexture2D = nullptr;
    PFNGLGENRENDERBUFFERSPROC GenRenderbuffers = nullptr;
    PFNGLBINDRENDERBUFFERPROC BindRenderbuffer = nullptr;
    PFNGLRENDERBUFFERSTORAGEPROC RenderbufferStorage = nullptr;
    PFNGLFRAMEBUFFERRENDERBUFFERPROC FramebufferRenderbuffer = nullptr;
    PFNGLCHECKFRAMEBUFFERSTATUSPROC CheckFramebufferStatus = nullptr;
    PFNGLDELETEFRAMEBUFFERSPROC DeleteFramebuffers = nullptr;
    PFNGLDELETERENDERBUFFERSPROC DeleteRenderbuffers = nullptr;

    template <class T> static bool get(T& fn, const char* name)
    {
#ifdef _WIN32
        PROC p = wglGetProcAddress(name);
        fn = reinterpret_cast<T>(reinterpret_cast<void*>(p));
#else
        fn = nullptr;
#endif
        return fn != nullptr;
    }

    bool load(std::string& missing)
    {
        bool ok = true;
#define SE_GL(fn) if (!get(fn, "gl" #fn)) { ok = false; missing += "gl" #fn " "; }
        SE_GL(CreateShader) SE_GL(ShaderSource) SE_GL(CompileShader) SE_GL(GetShaderiv) SE_GL(GetShaderInfoLog)
        SE_GL(DeleteShader) SE_GL(CreateProgram) SE_GL(AttachShader) SE_GL(BindAttribLocation) SE_GL(LinkProgram)
        SE_GL(GetProgramiv) SE_GL(GetProgramInfoLog) SE_GL(DeleteProgram) SE_GL(UseProgram) SE_GL(GetUniformLocation)
        SE_GL(Uniform1f) SE_GL(Uniform1i) SE_GL(Uniform2f) SE_GL(Uniform3f) SE_GL(Uniform4fv) SE_GL(UniformMatrix4fv)
        SE_GL(EnableVertexAttribArray) SE_GL(DisableVertexAttribArray) SE_GL(VertexAttribPointer) SE_GL(GenBuffers)
        SE_GL(BindBuffer) SE_GL(BufferData) SE_GL(DeleteBuffers) SE_GL(ActiveTexture)
#undef SE_GL
        return ok;
    }

    bool loadFbo()
    {
        return get(GenFramebuffers, "glGenFramebuffers") && get(BindFramebuffer, "glBindFramebuffer")
            && get(FramebufferTexture2D, "glFramebufferTexture2D") && get(GenRenderbuffers, "glGenRenderbuffers")
            && get(BindRenderbuffer, "glBindRenderbuffer") && get(RenderbufferStorage, "glRenderbufferStorage")
            && get(FramebufferRenderbuffer, "glFramebufferRenderbuffer")
            && get(CheckFramebufferStatus, "glCheckFramebufferStatus")
            && get(DeleteFramebuffers, "glDeleteFramebuffers") && get(DeleteRenderbuffers, "glDeleteRenderbuffers");
    }
};

// ------------------------------------------------------------------------------------------------ small math

struct V3 {
    float x = 0, y = 0, z = 0;
    V3() = default;
    V3(float a, float b, float c) : x(a), y(b), z(c) {}
    V3 operator+(const V3& o) const { return {x + o.x, y + o.y, z + o.z}; }
    V3 operator-(const V3& o) const { return {x - o.x, y - o.y, z - o.z}; }
    V3 operator*(float s) const { return {x * s, y * s, z * s}; }
};
inline float dot(const V3& a, const V3& b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
inline V3 cross(const V3& a, const V3& b) { return {a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x}; }
inline V3 normalize(const V3& a) { const float l = std::sqrt(dot(a, a)); return l > 1e-12f ? a * (1.f / l) : V3(0, 1, 0); }

struct M4 { float m[16]; };  // column-major
inline M4 mul(const M4& a, const M4& b)
{
    M4 r;
    for (int c = 0; c < 4; ++c)
        for (int rr = 0; rr < 4; ++rr) {
            float s = 0;
            for (int k = 0; k < 4; ++k) s += a.m[k * 4 + rr] * b.m[c * 4 + k];
            r.m[c * 4 + rr] = s;
        }
    return r;
}

struct CamMats { M4 vp; V3 eye, right; };

constexpr float kFovY = 30.f * kPi / 180.f;
constexpr float kBaseDistance = 3.45f;

CamMats cameraMatrices(const EggCamera& c)
{
    const float dist = kBaseDistance / std::clamp(c.zoom, 0.3f, 3.f);
    const float cp = std::cos(c.pitch), sp = std::sin(c.pitch);
    const V3 target(0.f, 0.f, 0.f);
    const V3 eye = target + V3(cp * std::sin(c.yaw), sp, cp * std::cos(c.yaw)) * dist;
    const V3 f = normalize(target - eye);
    const V3 s = normalize(cross(f, V3(0, 1, 0)));
    const V3 u = cross(s, f);
    M4 view = {{s.x, u.x, -f.x, 0, s.y, u.y, -f.y, 0, s.z, u.z, -f.z, 0,
                -dot(s, eye), -dot(u, eye), dot(f, eye), 1}};
    const float aspect = (float) std::max(1, c.widthPx) / (float) std::max(1, c.heightPx);
    const float t = 1.f / std::tan(kFovY * 0.5f), zn = 0.1f, zf = 20.f;
    M4 proj = {{t / aspect, 0, 0, 0, 0, t, 0, 0, 0, 0, (zf + zn) / (zn - zf), -1, 0, 0, 2 * zf * zn / (zn - zf), 0}};
    // lens shift: the egg centre lands on (centerX, centerY) of the framebuffer
    const float sx = c.centerX * 2.f - 1.f, sy = 1.f - c.centerY * 2.f;
    M4 shift = {{1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, sx, sy, 0, 1}};
    return {mul(shift, mul(proj, view)), eye, s};
}

// ------------------------------------------------------------------------------------------------ egg profile

// Huegelschaeffer egg, as three/egg_mesh.py: length 1 along y, pointed end up.
constexpr double kL = 1.0, kB = 0.74, kWp = 0.085;
double eggRadius(double y)
{
    const double num = kL * kL - 4.0 * y * y;
    if (num <= 0.0) return 0.0;
    return 0.5 * kB * std::sqrt(num / (kL * kL + 8.0 * kWp * y + 4.0 * kWp * kWp));
}

struct Profile {
    static constexpr int N = 4096;
    double ys[N + 1], rs[N + 1], arc[N + 1];
    double total = 0;
    Profile()
    {
        for (int k = 0; k <= N; ++k) {
            ys[k] = 0.5 * std::cos(3.14159265358979 * k / N);   // dense at both tips
            rs[k] = eggRadius(ys[k]);
            arc[k] = k == 0 ? 0.0 : arc[k - 1] + std::hypot(rs[k] - rs[k - 1], ys[k] - ys[k - 1]);
        }
        total = arc[N];
    }
    // u = arc-length fraction from the top tip (0) to the bottom tip (1)
    void at(double u, double& y, double& r) const
    {
        const double s = std::clamp(u, 0.0, 1.0) * total;
        int lo = 0, hi = N;
        while (hi - lo > 1) { const int mid = (lo + hi) / 2; (arc[mid] <= s ? lo : hi) = mid; }
        const double span = arc[hi] - arc[lo];
        const double f = span > 1e-15 ? (s - arc[lo]) / span : 0.0;
        y = ys[lo] + (ys[hi] - ys[lo]) * f;
        r = rs[lo] + (rs[hi] - rs[lo]) * f;
    }
    // outward normal in the (r, y) meridian plane
    void normal(double u, double& nr, double& ny) const
    {
        const double e = 1e-4;
        double y0, r0, y1, r1;
        at(std::max(0.0, u - e), y0, r0);
        at(std::min(1.0, u + e), y1, r1);
        const double dr = r1 - r0, dy = y1 - y0, l = std::hypot(dr, dy);
        nr = l > 0 ? -dy / l : 1.0;
        ny = l > 0 ? dr / l : 0.0;
    }
};

const Profile& profile()
{
    static const Profile p;
    return p;
}

V3 surfacePoint(double u, double phi)
{
    double y, r;
    profile().at(u, y, r);
    return {(float) (r * std::cos(phi)), (float) y, (float) (r * std::sin(phi))};
}

V3 surfaceNormal(double u, double phi)
{
    double nr, ny;
    profile().normal(std::clamp(u, 1e-3, 1.0 - 1e-3), nr, ny);
    return normalize(V3((float) (nr * std::cos(phi)), (float) ny, (float) (nr * std::sin(phi))));
}

// Deterministic hash noise
inline float hash01(uint32_t a)
{
    a ^= a >> 16; a *= 0x7feb352dU; a ^= a >> 15; a *= 0x846ca68bU; a ^= a >> 16;
    return (float) (a & 0xFFFFFF) / (float) 0x1000000;
}

// Band boundary k (0..12) at azimuth phi, as an arc-length fraction. Interior boundaries wander like a crack.
double boundaryU(int k, double phi)
{
    if (k <= 0) return 0.0;
    if (k >= kBands) return 1.0;
    const double j = 0.45 * std::sin(3 * phi + 1.7 * k) + 0.30 * std::sin(7 * phi + 2.9 * k)
                   + 0.17 * std::sin(13 * phi + 0.7 * k) + 0.08 * std::sin(29 * phi + 4.1 * k);
    return (double) k / kBands + 0.02 * j;
}

double bandMidU(int b) { return (b + 0.5) / kBands; }

struct Vertex { float pos[3], nrm[3], cen[3], info[4]; };

struct MeshBuilder {
    std::vector<Vertex> v;
    std::vector<uint32_t> idx;

    uint32_t add(const V3& p, const V3& n, const V3& c, float band, float seed, float edge, float side)
    {
        v.push_back({{p.x, p.y, p.z}, {n.x, n.y, n.z}, {c.x, c.y, c.z}, {band, seed, edge, side}});
        return (uint32_t) v.size() - 1;
    }
    // Triangle wound counter-clockwise as seen from the side `facing` points to.
    void tri(uint32_t a, uint32_t b, uint32_t c, const V3& facing)
    {
        const V3 pa(v[a].pos[0], v[a].pos[1], v[a].pos[2]);
        const V3 pb(v[b].pos[0], v[b].pos[1], v[b].pos[2]);
        const V3 pc(v[c].pos[0], v[c].pos[1], v[c].pos[2]);
        const V3 n = cross(pb - pa, pc - pa);
        if (dot(n, n) < 1e-16f) return;
        if (dot(n, facing) >= 0) { idx.push_back(a); idx.push_back(b); idx.push_back(c); }
        else { idx.push_back(a); idx.push_back(c); idx.push_back(b); }
    }
};

constexpr float kShellThickness = 0.013f;

void buildShell(MeshBuilder& mb)
{
    const Profile& pr = profile();
    const double bandArc = pr.total / kBands;
    for (int b = 0; b < kBands; ++b) {
        double ym, rm;
        pr.at(bandMidU(b), ym, rm);
        const double nIdeal = 2 * kPi * rm / (1.05 * bandArc) * (0.8 + 0.4 * hash01(555u + b));
        const int n = std::clamp((int) std::lround(nIdeal), 3, 18);
        const double offset = hash01(1000u + b) * 2 * kPi;
        std::vector<double> base(n + 1), slant(n + 1);
        for (int j = 0; j < n; ++j) {
            base[j] = offset + 2 * kPi * (j + 0.42 * (hash01(77u * b + 13u * j + 5u) - 0.5)) / n;
            slant[j] = (hash01(911u * b + 31u * j + 3u) - 0.5) * 1.3 * (2 * kPi / n);
        }
        base[n] = base[0] + 2 * kPi;
        slant[n] = slant[0];
        const double umid = bandMidU(b);
        auto cut = [&](int j, double u) {
            const double w = (std::sin(u * 90.0 + j * 1.3 + b) * 0.08 + std::sin(u * 210.0 + j * 2.1) * 0.035) * (2 * kPi / n);
            return base[j] + slant[j] * (u - umid) * kBands + w;
        };

        for (int j = 0; j < n; ++j) {
            const int ns = 7, nv = 6;
            V3 P[ns][nv], N[ns][nv];
            float edge[ns][nv];
            for (int i = 0; i < ns; ++i)
                for (int k = 0; k < nv; ++k) {
                    const double s = (double) i / (ns - 1), vv = (double) k / (nv - 1);
                    const double phi0 = cut(j, umid) + (cut(j + 1, umid) - cut(j, umid)) * s;
                    const double uEst = boundaryU(b, phi0) + (boundaryU(b + 1, phi0) - boundaryU(b, phi0)) * vv;
                    const double phi = cut(j, uEst) + (cut(j + 1, uEst) - cut(j, uEst)) * s;
                    const double u0 = boundaryU(b, phi), u1 = boundaryU(b + 1, phi);
                    const double u = u0 + (u1 - u0) * vv;
                    P[i][k] = surfacePoint(u, phi);
                    N[i][k] = surfaceNormal(u, phi);
                    double y, r;
                    pr.at(u, y, r);
                    const double wWorld = r * (cut(j + 1, u) - cut(j, u)), hWorld = (u1 - u0) * pr.total;
                    edge[i][k] = (float) std::min(std::min(s, 1 - s) * wWorld, std::min(vv, 1 - vv) * hWorld);
                }
            V3 c;
            for (int i = 0; i < ns; ++i)
                for (int k = 0; k < nv; ++k) c = c + P[i][k];
            c = c * (1.f / (ns * nv));
            const float seed = hash01(4099u * b + 17u * j + 1u);
            const float band = (float) b;

            uint32_t outer[ns][nv], inner[ns][nv];
            for (int i = 0; i < ns; ++i)
                for (int k = 0; k < nv; ++k) {
                    outer[i][k] = mb.add(P[i][k], N[i][k], c, band, seed, edge[i][k], 0.f);
                    inner[i][k] = mb.add(P[i][k] - N[i][k] * kShellThickness, N[i][k] * -1.f, c, band, seed, edge[i][k], 1.f);
                }
            for (int i = 0; i + 1 < ns; ++i)
                for (int k = 0; k + 1 < nv; ++k) {
                    const V3 nOut = N[i][k] + N[i + 1][k + 1];
                    mb.tri(outer[i][k], outer[i + 1][k], outer[i + 1][k + 1], nOut);
                    mb.tri(outer[i][k], outer[i + 1][k + 1], outer[i][k + 1], nOut);
                    mb.tri(inner[i][k], inner[i + 1][k], inner[i + 1][k + 1], nOut * -1.f);
                    mb.tri(inner[i][k], inner[i + 1][k + 1], inner[i][k + 1], nOut * -1.f);
                }
            // fracture walls along the four edges, flat-shaded, facing away from the shard
            auto wall = [&](int i0, int k0, int i1, int k1) {
                const V3 a = P[i0][k0], bb = P[i1][k1];
                const V3 nrm = (N[i0][k0] + N[i1][k1]) * 0.5f;
                const V3 mid = (a + bb) * 0.5f;
                V3 out = cross(bb - a, nrm);
                if (dot(out, mid - c) < 0) out = out * -1.f;
                out = normalize(out);
                const uint32_t q0 = mb.add(a, out, c, band, seed, 0.f, 2.f);
                const uint32_t q1 = mb.add(bb, out, c, band, seed, 0.f, 2.f);
                const uint32_t q2 = mb.add(bb - N[i1][k1] * kShellThickness, out, c, band, seed, 0.f, 2.f);
                const uint32_t q3 = mb.add(a - N[i0][k0] * kShellThickness, out, c, band, seed, 0.f, 2.f);
                mb.tri(q0, q1, q2, out);
                mb.tri(q0, q2, q3, out);
            };
            for (int i = 0; i + 1 < ns; ++i) { wall(i, 0, i + 1, 0); wall(i, nv - 1, i + 1, nv - 1); }
            for (int k = 0; k + 1 < nv; ++k) { wall(0, k, 0, k + 1); wall(ns - 1, k, ns - 1, k + 1); }
        }
    }
}

void buildSphere(MeshBuilder& mb, const V3& center, float radius, int nu, int nv)
{
    const uint32_t first = (uint32_t) mb.v.size();
    for (int k = 0; k <= nv; ++k)
        for (int i = 0; i <= nu; ++i) {
            const float th = kPi * k / nv, ph = 2 * kPi * i / nu;
            const V3 n(std::sin(th) * std::cos(ph), std::cos(th), std::sin(th) * std::sin(ph));
            mb.add(center + n * radius, n, n, 0, 0, 0, 0);
        }
    for (int k = 0; k < nv; ++k)
        for (int i = 0; i < nu; ++i) {
            const uint32_t a = first + k * (nu + 1) + i, b = a + 1, c = a + (nu + 1), d = c + 1;
            const V3 n(mb.v[a].nrm[0], mb.v[a].nrm[1], mb.v[a].nrm[2]);
            mb.tri(a, c, d, n);
            mb.tri(a, d, b, n);
        }
}

// ------------------------------------------------------------------------------------------------ shaders

const char* kCommonGlsl = R"(
#version 120
const float PI = 3.14159265;
const float ET_PI_2 = 1.5707963267948966;
const float ET_TWO_PI = 6.283185307179586;
float disc(vec3 d, vec3 c, float r, float soft) { return smoothstep(cos(r + soft), cos(r), dot(d, normalize(c))); }
// studio environment of three/web/main.js
vec3 studio(vec3 d) {
  vec3 c = mix(vec3(0.015, 0.018, 0.03), vec3(0.09, 0.11, 0.17), smoothstep(-0.3, 0.9, d.y));
  c += vec3(7.0, 6.8, 6.4) * disc(d, vec3(-0.55, 0.75, 0.45), 0.33, 0.12);
  c += vec3(2.0, 2.6, 3.4) * disc(d, vec3(0.95, 0.25, -0.35), 0.16, 0.10);
  c += vec3(2.2, 1.4, 0.8) * disc(d, vec3(-0.7, 0.05, -0.75), 0.30, 0.20);
  c += vec3(1.2) * disc(d, vec3(0.3, 0.95, -0.1), 0.6, 0.4);
  c *= mix(0.25, 1.0, smoothstep(-0.25, 0.05, d.y));
  return c;
}
vec3 tonemap(vec3 c) {            // ACES filmic (Narkowicz) + sRGB, exposure as main.js
  c *= 1.05;
  c = clamp((c * (2.51 * c + 0.03)) / (c * (2.43 * c + 0.59) + 0.14), 0.0, 1.0);
  return pow(c, vec3(1.0 / 2.2));
}
const vec3 kAmber = vec3(1.0, 0.62, 0.22);
const vec3 kGold = vec3(1.0, 0.74, 0.30);
const vec3 kCyan = vec3(0.30, 0.78, 1.0);
)";

const char* kShellVs = R"(
attribute vec3 aPos; attribute vec3 aNrm; attribute vec3 aCen; attribute vec4 aInfo;
uniform mat4 uVP; uniform vec4 uBandA[12]; uniform vec4 uBandB[12]; uniform float uTime;
varying vec3 vN; varying vec3 vW; varying vec4 vInfo; varying vec4 vBand; varying vec2 vFx;
vec3 rot(vec3 v, vec3 k, float a) { float c = cos(a), s = sin(a); return v * c + cross(k, v) * s + k * dot(k, v) * (1.0 - c); }
void main() {
  int b = int(aInfo.x + 0.5);
  vec4 A = uBandA[b];   // open, split, lift, flash
  vec4 B = uBandB[b];   // polarity
  float open = A.x, split = A.y, lift = A.z, seed = aInfo.y;
  vec3 c = aCen;
  vec3 radial = normalize(vec3(c.x, c.y * 0.3, c.z) + vec3(1e-5, 0.0, 0.0));
  vec3 axis = normalize(cross(vec3(0.0, 1.0, 0.0), radial) + vec3(0.0, 0.0, 1e-5));
  float wob = 0.5 + 0.5 * sin(uTime * 0.8 + seed * 40.0);
  // a few fragments per band lift well clear (like the web egg), the rest open hairline-to-finger gaps
  float loose = smoothstep(0.78, 0.95, seed);
  float tilt = (seed - 0.5) * (0.5 * open + 0.45 * split) + 0.9 * loose * open * (fract(seed * 13.0) - 0.5) + 0.06 * open * (wob - 0.5);
  float shrink = 1.0 - 0.06 * open - 0.05 * split;
  vec3 p = rot(aPos - c, axis, tilt) * shrink;
  vec3 n = rot(aNrm, axis, tilt);
  float push = (0.012 + 0.05 * seed * seed + 0.13 * loose) * open + 0.010 * open * wob + 0.42 * split;
  vec3 w = c + p + radial * push + vec3(0.0, 0.16 * lift - 0.04 * loose * open * open, 0.0);
  vW = w; vN = n; vInfo = aInfo; vBand = A; vFx = vec2(A.w, B.x);
  gl_Position = uVP * vec4(w, 1.0);
}
)";

const char* kShellFs = R"(
uniform sampler2D uLut; uniform vec3 uEye; uniform float uLutScale; uniform float uHeat;
varying vec3 vN; varying vec3 vW; varying vec4 vInfo; varying vec4 vBand; varying vec2 vFx;
void main() {
  float side = vInfo.w, edge = vInfo.z;
  float open = vBand.x, split = vBand.y, flash = vFx.x, pol = vFx.y;
  float act = max(open, split);
  vec3 N = normalize(vN); vec3 V = normalize(uEye - vW);
  if (dot(N, V) < 0.0) N = -N;
  vec3 flashCol = mix(kCyan, kGold, clamp(pol * 0.5 + 0.5, 0.0, 1.0)) * flash;
  vec3 L = normalize(vec3(-0.55, 0.75, 0.45));
  vec3 col; float alpha;
  if (side < 0.5) {
    // ---- entanglement-shader-v1 (engine LUTs, same maths as three/web/main.js) ----
    float cosTheta = abs(dot(N, V));
    float theta = acos(clamp(cosTheta, 0.0, 1.0));
    float D = -2.0 * ET_TWO_PI * 500.0 * cosTheta;
    vec3 wl = vec3(650.0, 530.0, 470.0);
    float s0 = mod(D / wl.r, ET_TWO_PI) / ET_TWO_PI;
    float s1 = mod(D / wl.g, ET_TWO_PI) / ET_TWO_PI;
    float s2 = mod(D / wl.b, ET_TWO_PI) / ET_TWO_PI;
    float t = theta / ET_PI_2;
    vec4 l0 = texture2D(uLut, vec2(s0, t)), l1 = texture2D(uLut, vec2(s1, t)), l2 = texture2D(uLut, vec2(s2, t));
    vec3 Rf = vec3(l0.r, l1.r, l2.r) * uLutScale;
    vec3 Tf = vec3(l0.g, l1.g, l2.g) * uLutScale;
    vec3 refl = studio(reflect(-V, N));
    vec3 base = vec3(0.93, 0.86, 0.76) * (0.10 + 0.55 * max(dot(N, L), 0.0));
    col = Rf * refl + base * Rf * 0.35;
    float glow = exp(-pow(edge / 0.005, 2.0)) * smoothstep(0.03, 0.45, act);
    col += kAmber * glow * 1.1;
    col += flashCol * (0.10 + 1.2 * glow);
    // light from the yolk scattering through the thin shell
    col += vec3(1.0, 0.55, 0.2) * uHeat * 0.2 * dot(Tf, vec3(0.333));
    float fres = pow(1.0 - cosTheta, 2.0);
    alpha = clamp(0.16 + 0.75 * fres + 0.45 * dot(col, vec3(0.3333)), 0.14, 1.0);
    alpha = max(alpha, glow * 0.9);
  } else if (side < 1.5) {
    float wrap = clamp(dot(N, -L) * 0.5 + 0.5, 0.0, 1.0);
    col = vec3(0.98, 0.86, 0.68) * (0.015 + 0.07 * wrap) + kAmber * 0.10 * act + flashCol * 0.25;
    alpha = 0.45;
  } else {
    if (act < 0.015) discard;
    float k = smoothstep(0.0, 0.3, act);
    col = vec3(1.0, 0.52, 0.14) * (0.45 + 1.6 * flash) * k + flashCol * 0.7;
    alpha = 0.9 * k;
  }
  gl_FragColor = vec4(tonemap(col) * alpha, alpha);
}
)";

const char* kYolkVs = R"(
attribute vec3 aPos; attribute vec3 aNrm;
uniform mat4 uVP;
varying vec3 vN; varying vec3 vW; varying vec3 vO;
void main() { vO = aPos; vW = aPos; vN = aNrm; gl_Position = uVP * vec4(aPos, 1.0); }
)";

const char* kYolkFs = R"(
uniform vec3 uEye; uniform float uHeat;
varying vec3 vN; varying vec3 vW; varying vec3 vO;
float h3(vec3 p) { return fract(sin(dot(p, vec3(127.1, 311.7, 74.7))) * 43758.5453); }
float vnoise(vec3 p) { vec3 i = floor(p), f = fract(p); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(mix(h3(i), h3(i + vec3(1,0,0)), f.x), mix(h3(i + vec3(0,1,0)), h3(i + vec3(1,1,0)), f.x), f.y),
             mix(mix(h3(i + vec3(0,0,1)), h3(i + vec3(1,0,1)), f.x), mix(h3(i + vec3(0,1,1)), h3(i + vec3(1,1,1)), f.x), f.y), f.z); }
void main() {
  float n = vnoise(vO * 14.0) * 0.6 + vnoise(vO * 31.0) * 0.4;
  vec3 N = normalize(normalize(vN) + 0.25 * (vec3(vnoise(vO * 9.0 + 3.1), vnoise(vO * 9.0 + 7.7), vnoise(vO * 9.0 + 1.3)) - 0.5));
  vec3 V = normalize(uEye - vW);
  vec3 L = normalize(vec3(-0.55, 0.75, 0.45));
  vec3 yolk = mix(vec3(1.0, 0.62, 0.12), vec3(1.0, 0.86, 0.50), smoothstep(0.35, 0.8, n));
  float wrap = clamp((dot(N, L) + 0.45) / 1.45, 0.0, 1.0);
  vec3 col = yolk * (0.10 + 0.9 * wrap) + yolk * vec3(1.0, 0.5, 0.2) * pow(1.0 - abs(dot(N, V)), 2.0) * 0.7;
  col += studio(reflect(-V, N)) * 0.05;
  col += vec3(1.0, 0.45, 0.12) * uHeat * 0.9;
  gl_FragColor = vec4(tonemap(col), 1.0);
}
)";

const char* kFloorVs = R"(
attribute vec3 aPos; attribute vec3 aCen;
uniform mat4 uVP;
varying vec2 vUv;
void main() { vUv = aCen.xy; gl_Position = uVP * vec4(aPos, 1.0); }
)";

const char* kFloorFs = R"(
uniform float uGlow;
varying vec2 vUv;
void main() {
  float r = length(vUv - 0.5) * 2.0;
  float shadow = exp(-r * r * 40.0) * 0.8 + exp(-r * r * 7.0) * 0.35;
  vec3 glow = vec3(1.0, 0.6, 0.25) * exp(-r * r * 12.0) * uGlow;
  float a = clamp(shadow + length(glow), 0.0, 1.0);
  gl_FragColor = vec4(glow, a);
}
)";

const char* kBackVs = R"(
attribute vec3 aPos;
varying vec2 vP;
void main() { vP = aPos.xy * 0.5 + 0.5; gl_Position = vec4(aPos.xy, 0.0, 1.0); }
)";

const char* kBackFs = R"(
uniform vec2 uRes; uniform vec2 uCenter; uniform float uRadius; uniform float uHeat;
varying vec2 vP;
void main() {
  vec2 px = vP * uRes;
  vec3 col = mix(vec3(0.012, 0.014, 0.024), vec3(0.035, 0.045, 0.075), vP.y);
  float d = length((px - uCenter) / uRadius);
  col += vec3(0.07, 0.085, 0.14) * exp(-d * d * 0.9);
  col += vec3(0.20, 0.11, 0.04) * exp(-d * d * 2.2) * (0.25 + uHeat);
  vec2 q = vP - 0.5;
  col *= 1.0 - 0.55 * dot(q, q);
  gl_FragColor = vec4(col, 1.0);
}
)";

const char* kResolveFs = R"(
uniform sampler2D uTex;
varying vec2 vP;
void main() { gl_FragColor = vec4(texture2D(uTex, vP).rgb, 1.0); }
)";

}  // namespace

// ------------------------------------------------------------------------------------------------ renderer

struct EggRenderer::Impl {
    GLApi gl;
    GLuint shellProg = 0, yolkProg = 0, floorProg = 0, backProg = 0, resolveProg = 0;
    GLuint vbo = 0, ibo = 0, lutTex = 0;
    GLsizei shellCount = 0, yolkCount = 0, floorCount = 0, backCount = 0;
    size_t shellFirst = 0, yolkFirst = 0, floorFirst = 0, backFirst = 0;
    bool fbo = false;
    GLuint fb = 0, fbTex = 0, fbDepth = 0;
    int fbW = 0, fbH = 0;

    GLuint compile(GLenum type, const char* body, std::string& err)
    {
        const GLuint s = gl.CreateShader(type);
        const char* parts[2] = {kCommonGlsl, body};
        gl.ShaderSource(s, 2, parts, nullptr);
        gl.CompileShader(s);
        GLint ok = 0;
        gl.GetShaderiv(s, GL_COMPILE_STATUS, &ok);
        if (!ok) {
            char log[2048] = {};
            gl.GetShaderInfoLog(s, sizeof log, nullptr, log);
            err += log;
            gl.DeleteShader(s);
            return 0;
        }
        return s;
    }

    GLuint program(const char* vs, const char* fs, std::string& err)
    {
        const GLuint v = compile(GL_VERTEX_SHADER, vs, err), f = compile(GL_FRAGMENT_SHADER, fs, err);
        if (!v || !f) return 0;
        const GLuint p = gl.CreateProgram();
        gl.AttachShader(p, v);
        gl.AttachShader(p, f);
        gl.BindAttribLocation(p, 0, "aPos");
        gl.BindAttribLocation(p, 1, "aNrm");
        gl.BindAttribLocation(p, 2, "aCen");
        gl.BindAttribLocation(p, 3, "aInfo");
        gl.LinkProgram(p);
        gl.DeleteShader(v);
        gl.DeleteShader(f);
        GLint ok = 0;
        gl.GetProgramiv(p, GL_LINK_STATUS, &ok);
        if (!ok) {
            char log[2048] = {};
            gl.GetProgramInfoLog(p, sizeof log, nullptr, log);
            err += log;
            gl.DeleteProgram(p);
            return 0;
        }
        return p;
    }

    void bindAttribs()
    {
        gl.BindBuffer(GL_ARRAY_BUFFER, vbo);
        gl.BindBuffer(GL_ELEMENT_ARRAY_BUFFER, ibo);
        const GLsizei stride = sizeof(Vertex);
        gl.VertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, stride, (const void*) offsetof(Vertex, pos));
        gl.VertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, stride, (const void*) offsetof(Vertex, nrm));
        gl.VertexAttribPointer(2, 3, GL_FLOAT, GL_FALSE, stride, (const void*) offsetof(Vertex, cen));
        gl.VertexAttribPointer(3, 4, GL_FLOAT, GL_FALSE, stride, (const void*) offsetof(Vertex, info));
        for (GLuint i = 0; i < 4; ++i) gl.EnableVertexAttribArray(i);
    }

    void unbindAttribs()
    {
        for (GLuint i = 0; i < 4; ++i) gl.DisableVertexAttribArray(i);
        gl.BindBuffer(GL_ARRAY_BUFFER, 0);
        gl.BindBuffer(GL_ELEMENT_ARRAY_BUFFER, 0);
    }

    void drawRange(size_t first, GLsizei count)
    {
        glDrawElements(GL_TRIANGLES, count, GL_UNSIGNED_INT, (const void*) (first * sizeof(uint32_t)));
    }

    void ensureFbo(int w, int h)
    {
        if (!fbo || (w == fbW && h == fbH && fb)) return;
        if (fb) { gl.DeleteFramebuffers(1, &fb); gl.DeleteRenderbuffers(1, &fbDepth); glDeleteTextures(1, &fbTex); fb = 0; }
        glGenTextures(1, &fbTex);
        glBindTexture(GL_TEXTURE_2D, fbTex);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, nullptr);
        glBindTexture(GL_TEXTURE_2D, 0);
        gl.GenRenderbuffers(1, &fbDepth);
        gl.BindRenderbuffer(GL_RENDERBUFFER, fbDepth);
        gl.RenderbufferStorage(GL_RENDERBUFFER, GL_DEPTH_COMPONENT24, w, h);
        gl.BindRenderbuffer(GL_RENDERBUFFER, 0);
        gl.GenFramebuffers(1, &fb);
        gl.BindFramebuffer(GL_FRAMEBUFFER, fb);
        gl.FramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, fbTex, 0);
        gl.FramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER, fbDepth);
        const GLenum status = gl.CheckFramebufferStatus(GL_FRAMEBUFFER);
        gl.BindFramebuffer(GL_FRAMEBUFFER, 0);
        if (status != GL_FRAMEBUFFER_COMPLETE) {
            gl.DeleteFramebuffers(1, &fb); gl.DeleteRenderbuffers(1, &fbDepth); glDeleteTextures(1, &fbTex);
            fb = fbTex = fbDepth = 0;
            fbo = false;
            return;
        }
        fbW = w; fbH = h;
    }
};

EggRenderer::EggRenderer() : d(new Impl) {}

EggRenderer::~EggRenderer()
{
    // GL objects die with the context (DPF destroys it with the window); nothing to release safely here.
    delete d;
}

bool EggRenderer::init()
{
    if (fReady) return true;
    std::string missing;
    if (!d->gl.load(missing)) { fError = "OpenGL 2.0 not available: " + missing; return false; }
    d->fbo = d->gl.loadFbo();

    std::string err;
    d->shellProg = d->program(kShellVs, kShellFs, err);
    d->yolkProg = d->program(kYolkVs, kYolkFs, err);
    d->floorProg = d->program(kFloorVs, kFloorFs, err);
    d->backProg = d->program(kBackVs, kBackFs, err);
    d->resolveProg = d->program(kBackVs, kResolveFs, err);
    if (!d->shellProg || !d->yolkProg || !d->floorProg || !d->backProg || !d->resolveProg) {
        fError = "shader build failed: " + err;
        return false;
    }

    MeshBuilder mb;
    buildShell(mb);
    d->shellFirst = 0;
    d->shellCount = (GLsizei) mb.idx.size();
    d->yolkFirst = mb.idx.size();
    buildSphere(mb, V3(0.f, -0.06f, 0.f), 0.19f, 64, 40);
    d->yolkCount = (GLsizei) (mb.idx.size() - d->yolkFirst);
    {
        d->floorFirst = mb.idx.size();
        const float y = -0.505f, s = 0.9f;
        const uint32_t a = mb.add(V3(-s, y, -s), V3(0, 1, 0), V3(0, 0, 0), 0, 0, 0, 0);
        const uint32_t b = mb.add(V3(s, y, -s), V3(0, 1, 0), V3(1, 0, 0), 0, 0, 0, 0);
        const uint32_t c = mb.add(V3(s, y, s), V3(0, 1, 0), V3(1, 1, 0), 0, 0, 0, 0);
        const uint32_t e = mb.add(V3(-s, y, s), V3(0, 1, 0), V3(0, 1, 0), 0, 0, 0, 0);
        mb.tri(a, b, c, V3(0, 1, 0));
        mb.tri(a, c, e, V3(0, 1, 0));
        d->floorCount = 6;
    }
    {
        d->backFirst = mb.idx.size();
        const uint32_t a = mb.add(V3(-1, -1, 0), V3(0, 0, 1), V3(), 0, 0, 0, 0);
        const uint32_t b = mb.add(V3(1, -1, 0), V3(0, 0, 1), V3(), 0, 0, 0, 0);
        const uint32_t c = mb.add(V3(1, 1, 0), V3(0, 0, 1), V3(), 0, 0, 0, 0);
        const uint32_t e = mb.add(V3(-1, 1, 0), V3(0, 0, 1), V3(), 0, 0, 0, 0);
        mb.tri(a, b, c, V3(0, 0, 1));
        mb.tri(a, c, e, V3(0, 0, 1));
        d->backCount = 6;
    }

    d->gl.GenBuffers(1, &d->vbo);
    d->gl.GenBuffers(1, &d->ibo);
    d->gl.BindBuffer(GL_ARRAY_BUFFER, d->vbo);
    d->gl.BufferData(GL_ARRAY_BUFFER, (GLsizeiptr) (mb.v.size() * sizeof(Vertex)), mb.v.data(), GL_STATIC_DRAW);
    d->gl.BindBuffer(GL_ELEMENT_ARRAY_BUFFER, d->ibo);
    d->gl.BufferData(GL_ELEMENT_ARRAY_BUFFER, (GLsizeiptr) (mb.idx.size() * sizeof(uint32_t)), mb.idx.data(), GL_STATIC_DRAW);
    d->gl.BindBuffer(GL_ARRAY_BUFFER, 0);
    d->gl.BindBuffer(GL_ELEMENT_ARRAY_BUFFER, 0);

    glGenTextures(1, &d->lutTex);
    glBindTexture(GL_TEXTURE_2D, d->lutTex);
    glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, kLutW, kLutH, 0, GL_RGBA, GL_UNSIGNED_BYTE, kShellLut);
    glBindTexture(GL_TEXTURE_2D, 0);

    fReady = true;
    return true;
}

void EggRenderer::draw(const EggFrame& f)
{
    if (!fReady) return;
    GLApi& gl = d->gl;
    const int W = std::max(1, f.cam.widthPx), H = std::max(1, f.cam.heightPx);
    const CamMats cm = cameraMatrices(f.cam);

    // 2x supersampling into an offscreen target (there is no MSAA on the host window)
    const float ss = std::min(2.f, 4096.f / (float) std::max(W, H));
    const int sw = (int) (W * ss), sh = (int) (H * ss);
    d->ensureFbo(sw, sh);
    const bool useFbo = d->fbo && d->fb && ss > 1.01f;
    if (useFbo) {
        gl.BindFramebuffer(GL_FRAMEBUFFER, d->fb);
        glViewport(0, 0, sw, sh);
    } else {
        glViewport(0, 0, W, H);
    }

    float bandA[kBands * 4], bandB[kBands * 4];
    float heat = std::clamp(f.heat, 0.f, 1.f);
    for (int b = 0; b < kBands; ++b) {
        const BandVisual& bv = f.band[b];
        bandA[b * 4 + 0] = std::clamp(bv.open, 0.f, 1.f);
        bandA[b * 4 + 1] = std::clamp(bv.split, 0.f, 1.f);
        bandA[b * 4 + 2] = std::clamp(bv.lift, -1.f, 1.f);
        bandA[b * 4 + 3] = std::clamp(bv.flash, 0.f, 1.f);
        bandB[b * 4 + 0] = std::clamp(bv.polarity, -1.f, 1.f);
        bandB[b * 4 + 1] = bandB[b * 4 + 2] = bandB[b * 4 + 3] = 0.f;
    }

    glDisable(GL_SCISSOR_TEST);
    glDisable(GL_STENCIL_TEST);
    glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
    glDisable(GL_CULL_FACE);
    glDisable(GL_DEPTH_TEST);
    glDisable(GL_BLEND);
    d->bindAttribs();

    // backdrop
    {
        float cx, cy;
        const float origin[3] = {0, 0, 0};
        project(f.cam, origin, cx, cy);
        gl.UseProgram(d->backProg);
        gl.Uniform2f(gl.GetUniformLocation(d->backProg, "uRes"), (float) W, (float) H);
        gl.Uniform2f(gl.GetUniformLocation(d->backProg, "uCenter"), cx, (float) H - cy);
        gl.Uniform1f(gl.GetUniformLocation(d->backProg, "uRadius"), 0.42f * pixelsPerUnit(f.cam));
        gl.Uniform1f(gl.GetUniformLocation(d->backProg, "uHeat"), heat);
        d->drawRange(d->backFirst, d->backCount);
    }

    glEnable(GL_DEPTH_TEST);
    glDepthFunc(GL_LEQUAL);
    glDepthMask(GL_TRUE);
    glClearDepth(1.0);
    glClear(GL_DEPTH_BUFFER_BIT);

    // floor shadow and glow
    glEnable(GL_BLEND);
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
    glDepthMask(GL_FALSE);
    gl.UseProgram(d->floorProg);
    gl.UniformMatrix4fv(gl.GetUniformLocation(d->floorProg, "uVP"), 1, GL_FALSE, cm.vp.m);
    gl.Uniform1f(gl.GetUniformLocation(d->floorProg, "uGlow"), 0.15f + 0.6f * heat);
    d->drawRange(d->floorFirst, d->floorCount);

    // yolk (opaque)
    glDisable(GL_BLEND);
    glDepthMask(GL_TRUE);
    gl.UseProgram(d->yolkProg);
    gl.UniformMatrix4fv(gl.GetUniformLocation(d->yolkProg, "uVP"), 1, GL_FALSE, cm.vp.m);
    gl.Uniform3f(gl.GetUniformLocation(d->yolkProg, "uEye"), cm.eye.x, cm.eye.y, cm.eye.z);
    gl.Uniform1f(gl.GetUniformLocation(d->yolkProg, "uHeat"), heat);
    d->drawRange(d->yolkFirst, d->yolkCount);

    // shell: far faces first without depth writes, then near faces (premultiplied alpha)
    gl.UseProgram(d->shellProg);
    gl.UniformMatrix4fv(gl.GetUniformLocation(d->shellProg, "uVP"), 1, GL_FALSE, cm.vp.m);
    gl.Uniform4fv(gl.GetUniformLocation(d->shellProg, "uBandA"), kBands, bandA);
    gl.Uniform4fv(gl.GetUniformLocation(d->shellProg, "uBandB"), kBands, bandB);
    gl.Uniform1f(gl.GetUniformLocation(d->shellProg, "uTime"), f.time);
    gl.Uniform3f(gl.GetUniformLocation(d->shellProg, "uEye"), cm.eye.x, cm.eye.y, cm.eye.z);
    gl.Uniform1f(gl.GetUniformLocation(d->shellProg, "uLutScale"), kLutScale);
    gl.Uniform1f(gl.GetUniformLocation(d->shellProg, "uHeat"), heat);
    gl.Uniform1i(gl.GetUniformLocation(d->shellProg, "uLut"), 0);
    gl.ActiveTexture(GL_TEXTURE0);
    glBindTexture(GL_TEXTURE_2D, d->lutTex);
    glEnable(GL_BLEND);
    glBlendFunc(GL_ONE, GL_ONE_MINUS_SRC_ALPHA);
    glEnable(GL_CULL_FACE);
    glFrontFace(GL_CCW);
    glCullFace(GL_FRONT);
    glDepthMask(GL_FALSE);
    d->drawRange(d->shellFirst, d->shellCount);
    glCullFace(GL_BACK);
    glDepthMask(GL_TRUE);
    d->drawRange(d->shellFirst, d->shellCount);
    glBindTexture(GL_TEXTURE_2D, 0);

    glDisable(GL_CULL_FACE);
    glDisable(GL_DEPTH_TEST);
    glDisable(GL_BLEND);

    if (useFbo) {
        gl.BindFramebuffer(GL_FRAMEBUFFER, 0);
        glViewport(0, 0, W, H);
        gl.UseProgram(d->resolveProg);
        gl.Uniform1i(gl.GetUniformLocation(d->resolveProg, "uTex"), 0);
        gl.ActiveTexture(GL_TEXTURE0);
        glBindTexture(GL_TEXTURE_2D, d->fbTex);
        d->drawRange(d->backFirst, d->backCount);
        glBindTexture(GL_TEXTURE_2D, 0);
    }

    d->unbindAttribs();
    gl.UseProgram(0);
    glDepthMask(GL_TRUE);
    glEnable(GL_BLEND);
    glBlendFunc(GL_ONE, GL_ONE_MINUS_SRC_ALPHA);
}

void EggRenderer::nodeWorld(const EggCamera& cam, int band, float split, float lift, float out[3]) const
{
    double y, r;
    profile().at(bandMidU(std::clamp(band, 0, kBands - 1)), y, r);
    const V3 right(std::cos(cam.yaw), 0.f, -std::sin(cam.yaw));
    const V3 base = right * (float) r + V3(0.f, (float) y, 0.f);
    const V3 radial = normalize(right * (float) r + V3(0.f, 0.3f * (float) y, 0.f));
    const V3 p = base + radial * (kSplitDistance * split) + V3(0.f, kLiftDistance * lift, 0.f);
    out[0] = p.x; out[1] = p.y; out[2] = p.z;
}

bool EggRenderer::project(const EggCamera& cam, const float w[3], float& px, float& py) const
{
    const CamMats cm = cameraMatrices(cam);
    const float* m = cm.vp.m;
    const float x = m[0] * w[0] + m[4] * w[1] + m[8] * w[2] + m[12];
    const float y = m[1] * w[0] + m[5] * w[1] + m[9] * w[2] + m[13];
    const float ww = m[3] * w[0] + m[7] * w[1] + m[11] * w[2] + m[15];
    if (ww <= 1e-6f) return false;
    px = (x / ww * 0.5f + 0.5f) * (float) cam.widthPx;
    py = (1.f - (y / ww * 0.5f + 0.5f)) * (float) cam.heightPx;
    return true;
}

float EggRenderer::pixelsPerUnit(const EggCamera& cam) const
{
    // vertical extent of the projection at the target distance
    const float dist = kBaseDistance / std::clamp(cam.zoom, 0.3f, 3.f);
    return (float) cam.heightPx * 0.5f / (dist * std::tan(kFovY * 0.5f));
}

}  // namespace se
