// Scrambled Echo DSP core: a multi-tap delay whose taps are a measured OTOC map F(site, t).
// Header-only, no framework dependencies; shared by the VST3 plugin, the offline renderer and the tests.
//
// Mapping (per tap of the map):  delay = t / depth * train length,  gain = |F| (sign of Re F = polarity),
// pan = site / (n_sites - 1).  Scramble interpolates F between the Control map and the selected map.
#pragma once

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdint>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

namespace se {

struct Tap {
    int site = 0;
    int step = 1;  // echo step t = 1..depth
    float re = 0.f;
    float im = 0.f;
};

struct TapMap {
    std::string name, description, jobId;
    int nSites = 0, depth = 0, kickSite = 0;
    std::vector<Tap> taps;
};

// The egg has 12 latitude bands, one per qubit site; taps of maps with another site count go to the band
// nearest their pan position.
constexpr int kBands = 12;
constexpr float kMinSiteGainDb = -60.f, kMaxSiteGainDb = 12.f;  // the bottom of the range mutes the site
constexpr float kSplitPan = 1.f;      // full split moves a site all the way to its stereo edge
constexpr float kSplitDelay = 1.f;    // full split doubles a site's delays, centre and edge alike

struct Params {
    float trainMs = 1000.f;  // length of the whole echo train (t = depth lands here)
    float mix = 0.5f;        // 0 dry .. 1 wet
    float feedback = 0.f;    // 0 .. 0.98, re-injects the t = depth echo so the whole train replays
    float scramble = 1.f;    // 0 = Control map, 1 = selected map
    float width = 1.f;       // 0 mono .. 1 full site->pan spread
    bool commutator = false; // false: gain = |F| (signed); true: gain = C = (1 - Re F) / 2, the normalised
                             // squared commutator, loud only where the kicked operator has spread
    float split = 0.f;                // global Split macro, added to every site's split
    float siteSplit[kBands] = {};     // 0 = on the shell (measured), 1 = dragged fully out
    float siteGainDb[kBands] = {};    // vertical drag, kMinSiteGainDb .. kMaxSiteGainDb
};

inline bool isEdited(const Params& p)
{
    if (std::fabs(p.split) > 1e-4f) return true;
    for (int i = 0; i < kBands; ++i)
        if (std::fabs(p.siteSplit[i]) > 1e-4f || std::fabs(p.siteGainDb[i]) > 1e-3f) return true;
    return false;
}

inline int bandOfPan(float pan) { return std::clamp((int) std::lround(pan * (kBands - 1)), 0, kBands - 1); }

// Written by the audio thread once per block with relaxed atomics, read by the UI at frame rate.
struct Telemetry {
    std::atomic<float> bandPos[kBands];  // recent activity of the band's in-phase taps (peak-held, decaying)
    std::atomic<float> bandNeg[kBands];  // ... and of its inverted (F < 0) taps
    std::atomic<float> phase;            // train lengths elapsed since the last input onset
    std::atomic<float> level;            // wet output peak, decaying
    std::atomic<uint32_t> blocks;        // incremented every processed block
    Telemetry() { clear(); }
    void clear()
    {
        for (int i = 0; i < kBands; ++i) { bandPos[i].store(0.f, std::memory_order_relaxed); bandNeg[i].store(0.f, std::memory_order_relaxed); }
        phase.store(1e3f, std::memory_order_relaxed);
        level.store(0.f, std::memory_order_relaxed);
        blocks.store(0, std::memory_order_relaxed);
    }
};

class Core {
public:
    static constexpr float kMaxSeconds = 8.f;
    static constexpr float kMinTrainMs = 10.f;

    void prepare(double sampleRate)
    {
        sr = (float) sampleRate;
        size_t need = (size_t) (kMaxSeconds * (1.f + kSplitDelay) * sr) + 8, size = 1;
        while (size < need) size <<= 1;
        buf.assign(size, 0.f);
        mask = size - 1;
        const float fc = std::min(12000.f, 0.45f * sr);
        lpCoef = 1.f - std::exp(-2.f * 3.14159265f * fc / sr);
        hpCoef = std::exp(-2.f * 3.14159265f * 20.f / sr);
        trainCoef = 1.f - std::exp(-1.f / (0.08f * sr));
        mixCoef = 1.f - std::exp(-1.f / (0.02f * sr));
        fadeLen = std::max(1, (int) (0.02f * sr));
        envAtk = 1.f - std::exp(-1.f / (0.001f * sr));
        envRel = 1.f - std::exp(-1.f / (0.03f * sr));
        envSlowCoef = 1.f - std::exp(-1.f / (0.3f * sr));
        reset();
    }

    void reset()
    {
        std::fill(buf.begin(), buf.end(), 0.f);
        w = 0; fbState = lpState = hpIn = hpOut = 0.f;
        envFast = envSlow = 0.f;
        sinceOnset = 1e9f;
        holdoff = 0;
        onsetArmed = true;
        snap = true;
        tel.clear();
    }

    const Telemetry& telemetry() const { return tel; }

    // Message thread. Compiles both maps into one merged tap set and hands it to the audio thread.
    void setMaps(const TapMap& control, const TapMap& target)
    {
        TapSet fresh = compile(control, target);
        lock();
        std::swap(pending, fresh);
        hasPending = true;
        unlock();
        // `fresh` now holds whatever was pending before (or an empty set) and is freed here, off the audio thread.
    }

    void setParams(const Params& p) { params = p; }

    size_t activeTapCount() const { return active.taps.size(); }

    void process(const float* inL, const float* inR, float* outL, float* outR, int n)
    {
        if (n <= 0 || buf.empty()) return;
        if (tryLock()) {
            if (hasPending) {
                std::swap(previous, active);
                std::swap(active, pending);
                hasPending = false;
                fadePos = (previous.taps.empty() || snap) ? fadeLen : 0;
                active.primed = false;
            }
            unlock();
        }

        const float targetTrain = std::clamp(params.trainMs, kMinTrainMs, kMaxSeconds * 1000.f - 20.f) * 0.001f * sr;
        const float targetMix = std::clamp(params.mix, 0.f, 1.f);
        if (snap) { train = targetTrain; mix = targetMix; }

        // Per-site edits glide with a 30 ms one-pole per block; taps then ramp linearly inside the block.
        const float macro = std::clamp(params.split, 0.f, 1.f);
        const float bandCoef = snap ? 1.f : 1.f - std::exp(-(float) n / (0.03f * sr));
        for (int b = 0; b < kBands; ++b) {
            const float e = std::clamp(macro + std::clamp(params.siteSplit[b], 0.f, 1.f), 0.f, 1.f);
            const float db = std::isfinite(params.siteGainDb[b]) ? std::clamp(params.siteGainDb[b], kMinSiteGainDb, kMaxSiteGainDb) : 0.f;
            const float g = db <= kMinSiteGainDb ? 0.f : std::pow(10.f, db / 20.f);
            bandSplit[b] += (e - bandSplit[b]) * bandCoef;
            bandGain[b] += (g - bandGain[b]) * bandCoef;
        }

        updateGains(active, n);
        if (fadePos < fadeLen) updateGains(previous, n);
        snap = false;

        const float maxDelay = (float) (buf.size() - 4);
        float peak = 0.f;
        for (int i = 0; i < n; ++i) {
            train += (targetTrain - train) * trainCoef;
            mix += (targetMix - mix) * mixCoef;
            const float dryL = inL[i], dryR = inR[i];
            const float mono = 0.5f * (dryL + dryR);
            // Onset follower for the UI time cursor (not part of the audio path).
            const float a = std::fabs(mono);
            envFast += (a - envFast) * (a > envFast ? envAtk : envRel);
            envSlow += (a - envSlow) * envSlowCoef;
            sinceOnset += 1.f;
            if (holdoff > 0) --holdoff;
            if (!onsetArmed) onsetArmed = envFast < 1.5f * envSlow + 1e-3f;
            else if (holdoff == 0 && envFast > 2.5f * envSlow + 1e-3f && envFast > 0.01f) {
                sinceOnset = 0.f;
                holdoff = (int) (0.12f * sr);
                onsetArmed = false;
            }
            buf[w] = mono + fbState;

            float wl = 0.f, wr = 0.f, wm = 0.f;
            runTaps(active, train, maxDelay, wl, wr, wm);
            if (fadePos < fadeLen) {
                const float f = (float) fadePos / (float) fadeLen;
                float pl = 0.f, pr = 0.f, pm = 0.f;
                runTaps(previous, train, maxDelay, pl, pr, pm);
                wl = f * wl + (1.f - f) * pl;
                wr = f * wr + (1.f - f) * pr;
                wm = f * wm + (1.f - f) * pm;
                ++fadePos;
            }

            lpState += (wm - lpState) * lpCoef;
            const float hp = hpCoef * (hpOut + lpState - hpIn);
            hpIn = lpState; hpOut = hp;
            fbState = std::tanh(hp);

            outL[i] = dryL * (1.f - mix) + wl * mix;
            outR[i] = dryR * (1.f - mix) + wr * mix;
            peak = std::max(peak, std::max(std::fabs(wl), std::fabs(wr)));
            w = (w + 1) & mask;
        }
        publish(n, peak);
    }

private:
    struct CTap {
        float frac;  // t / depth
        float pan;   // 0 left .. 1 right
        float gA;    // signed |F| in the Control map
        float gB;    // signed |F| in the selected map
        float cA;    // C = (1 - Re F) / 2 in the Control map
        float cB;    // C in the selected map
        bool regen;  // t == depth: this echo is re-injected by Feedback
        int band = 0;          // egg band (site) this tap belongs to
        float gl = 0.f, gr = 0.f, gm = 0.f;  // current per-sample gains (left, right, feedback)
        float dl = 0.f, dr = 0.f, dm = 0.f;  // per-sample ramp increments for this block
        float st = 1.f, dst = 0.f;           // delay stretch from the site's split, and its ramp
        float shown = 0.f;     // signed effective gain this block (telemetry)
        float acc = 0.f;       // sum of |delayed signal| this block (telemetry)
    };
    struct TapSet {
        std::vector<CTap> taps;
        bool primed = false;
    };

    static float signedMag(const Tap& t)
    {
        const float m = std::sqrt(t.re * t.re + t.im * t.im);
        return t.re < 0.f ? -m : m;
    }

    static TapSet compile(const TapMap& a, const TapMap& b)
    {
        TapSet set;
        std::unordered_map<int64_t, size_t> index;
        auto add = [&](const TapMap& m, bool isB) {
            if (m.depth <= 0 || m.nSites <= 0 || (int64_t) m.nSites * m.depth > (1 << 16)) return;
            // Dense grid: cells absent from the tap list have F = 0 (and so C = 0.5).
            std::vector<Tap> grid((size_t) m.nSites * m.depth);
            for (int s = 0; s < m.nSites; ++s)
                for (int t = 1; t <= m.depth; ++t) grid[(size_t) s * m.depth + t - 1] = {s, t, 0.f, 0.f};
            for (const Tap& t : m.taps)
                if (t.step >= 1 && t.step <= m.depth && t.site >= 0 && t.site < m.nSites && std::isfinite(t.re) && std::isfinite(t.im))
                    grid[(size_t) t.site * m.depth + t.step - 1] = t;
            for (const Tap& t : grid) {
                const float g = signedMag(t);
                const float c = std::clamp((1.f - t.re) * 0.5f, 0.f, 1.f);
                if (std::fabs(g) < 1e-4f && c < 1e-4f) continue;
                const float frac = (float) t.step / (float) m.depth;
                const float pan = m.nSites > 1 ? (float) t.site / (float) (m.nSites - 1) : 0.5f;
                const int64_t key = (int64_t) std::llround(frac * 1e6) * 4000000 + std::llround(pan * 1e6);
                auto it = index.find(key);
                if (it == index.end()) {
                    it = index.emplace(key, set.taps.size()).first;
                    CTap fresh{frac, pan, 0.f, 0.f, 0.f, 0.f, t.step == m.depth};
                    fresh.band = bandOfPan(pan);
                    set.taps.push_back(fresh);
                }
                CTap& ct = set.taps[it->second];
                if (std::fabs(g) >= 1e-4f) (isB ? ct.gB : ct.gA) += g;
                (isB ? ct.cB : ct.cA) += c;
            }
        };
        add(a, false);
        add(b, true);
        return set;
    }

    void updateGains(TapSet& set, int n)
    {
        const float s = std::clamp(params.scramble, 0.f, 1.f);
        const float width = std::clamp(params.width, 0.f, 1.f);
        const float fb = std::clamp(params.feedback, 0.f, 0.98f);
        const bool cv = params.commutator;
        auto gain = [&](const CTap& t) { return cv ? (1.f - s) * t.cA + s * t.cB : (1.f - s) * t.gA + s * t.gB; };
        float sumSq = 0.f, sumAbs = 0.f;
        for (const CTap& t : set.taps) {
            const float g = gain(t);
            sumSq += g * g;  // makeup follows the measured map, so a dragged gain stays audible
            if (t.regen) sumAbs += std::fabs(g * bandGain[t.band]);
        }
        const float makeup = sumSq > 1e-12f ? 1.f / std::sqrt(sumSq) : 0.f;
        // Only the final echo step (t = depth) is fed back, one train length later; normalising by its
        // summed |g| (including site gains) keeps the loop gain <= feedback.
        const float fbScale = fb / std::max(1.f, sumAbs);
        const bool jump = snap || !set.primed;
        const float inv = 1.f / (float) n;
        for (CTap& t : set.taps) {
            const float e = bandSplit[t.band];
            const float g = gain(t) * bandGain[t.band];
            const float p0 = 0.5f + (t.pan - 0.5f) * width;
            const float edge = t.band < kBands / 2 ? 0.f : 1.f;
            const float p = p0 + (edge - p0) * kSplitPan * e;
            const float angle = p * 1.57079633f;
            const float tl = g * makeup * std::cos(angle), tr = g * makeup * std::sin(angle), tm = t.regen ? g * fbScale : 0.f;
            const float ts = 1.f + kSplitDelay * e;
            t.shown = g * makeup;
            if (jump) { t.gl = tl; t.gr = tr; t.gm = tm; t.st = ts; t.dl = t.dr = t.dm = t.dst = 0.f; }
            else { t.dl = (tl - t.gl) * inv; t.dr = (tr - t.gr) * inv; t.dm = (tm - t.gm) * inv; t.dst = (ts - t.st) * inv; }
        }
        set.primed = true;
    }

    void publish(int n, float peak)
    {
        float pos[kBands] = {}, neg[kBands] = {};
        const float inv = 1.f / (float) n;
        for (CTap& t : active.taps) {
            const float a = std::fabs(t.shown) * t.acc * inv;
            (t.shown >= 0.f ? pos : neg)[t.band] += a;
            t.acc = 0.f;
        }
        for (CTap& t : previous.taps) t.acc = 0.f;
        const float decay = std::exp(-(float) n / (0.08f * sr));
        for (int b = 0; b < kBands; ++b) {
            tel.bandPos[b].store(std::max(pos[b], tel.bandPos[b].load(std::memory_order_relaxed) * decay), std::memory_order_relaxed);
            tel.bandNeg[b].store(std::max(neg[b], tel.bandNeg[b].load(std::memory_order_relaxed) * decay), std::memory_order_relaxed);
        }
        tel.level.store(std::max(peak, tel.level.load(std::memory_order_relaxed) * decay), std::memory_order_relaxed);
        tel.phase.store(std::min(sinceOnset / std::max(1.f, train), 1e3f), std::memory_order_relaxed);
        tel.blocks.store(tel.blocks.load(std::memory_order_relaxed) + 1, std::memory_order_relaxed);
    }

    void runTaps(TapSet& set, float trainSamples, float maxDelay, float& wl, float& wr, float& wm)
    {
        const float* b = buf.data();
        for (CTap& t : set.taps) {
            const float d = std::clamp(t.frac * t.st * trainSamples, 1.f, maxDelay);
            const int di = (int) d;
            const float fr = d - (float) di;
            const float v0 = b[(w - (size_t) di) & mask];
            const float v1 = b[(w - (size_t) di - 1) & mask];
            const float v = v0 + (v1 - v0) * fr;
            wl += t.gl * v; wr += t.gr * v; wm += t.gm * v;
            t.acc += std::fabs(v);
            t.gl += t.dl; t.gr += t.dr; t.gm += t.dm; t.st += t.dst;
        }
    }

    void lock() { while (flag.test_and_set(std::memory_order_acquire)) {} }
    bool tryLock() { return !flag.test_and_set(std::memory_order_acquire); }
    void unlock() { flag.clear(std::memory_order_release); }

    float sr = 48000.f;
    std::vector<float> buf;
    size_t mask = 0, w = 0;
    float lpCoef = 1.f, hpCoef = 1.f, trainCoef = 1.f, mixCoef = 1.f;
    float fbState = 0.f, lpState = 0.f, hpIn = 0.f, hpOut = 0.f;
    float train = 48000.f, mix = 0.5f;
    int fadeLen = 1, fadePos = 1;
    bool snap = true;
    float bandSplit[kBands] = {};
    float bandGain[kBands] = {1.f, 1.f, 1.f, 1.f, 1.f, 1.f, 1.f, 1.f, 1.f, 1.f, 1.f, 1.f};
    float envAtk = 1.f, envRel = 1.f, envSlowCoef = 1.f, envFast = 0.f, envSlow = 0.f, sinceOnset = 1e9f;
    int holdoff = 0;
    bool onsetArmed = true;
    Telemetry tel;
    Params params;
    TapSet active, previous, pending;
    bool hasPending = false;
    std::atomic_flag flag = ATOMIC_FLAG_INIT;
};

}  // namespace se
