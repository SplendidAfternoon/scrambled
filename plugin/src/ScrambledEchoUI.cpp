#include "DistrhoUI.hpp"

#include "EggRenderer.hpp"
#include "EggView.hpp"
#include "MapBank.hpp"

#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>

#ifdef _WIN32
extern "C" __declspec(dllimport) unsigned long __stdcall GetEnvironmentVariableA(const char*, char*, unsigned long);
#endif

START_NAMESPACE_DISTRHO

const se::Telemetry* scrambledEchoTelemetry(void* pluginInstance);

namespace {

constexpr float kBaseW = DISTRHO_UI_DEFAULT_WIDTH;
constexpr float kBaseH = DISTRHO_UI_DEFAULT_HEIGHT;
constexpr float kPi = 3.14159265f;
constexpr float kHeaderH = 58.f;
constexpr float kStripH = 124.f;

struct Rect {
    float x = 0, y = 0, w = 0, h = 0;
    bool contains(double px, double py) const { return px >= x && px < x + w && py >= y && py < y + h; }
};

const Color kText(232, 234, 242);
const Color kMuted(132, 140, 164);
const Color kDim(84, 92, 116);
const Color kPanel(18, 21, 32, 235);
const Color kEdge(52, 60, 84);
const Color kGold(255, 196, 84);     // brand accent, F > 0
const Color kCyan(92, 196, 255);     // F < 0, inverted echo
const Color kAmber(255, 158, 56);    // C view / cracks
const Color kMeasured(120, 220, 190);

std::string envString(const char* name)
{
#ifdef _WIN32
    char buf[1024];
    const unsigned long n = GetEnvironmentVariableA(name, buf, sizeof(buf));
    if (n > 0 && n < sizeof(buf)) return std::string(buf, n);
#else
    if (const char* v = std::getenv(name)) return v;
#endif
    return std::string();
}

float clampf(float v, float lo, float hi) { return v < lo ? lo : v > hi ? hi : v; }

// Vertical drag <-> site gain: up to +6 dB above the shell, down to -24 dB below.
float gainToLift(float db) { return db >= 0.f ? db / se::kMaxSiteGainDb : -db / se::kMinSiteGainDb; }
float liftToGain(float lift) { return lift >= 0.f ? lift * se::kMaxSiteGainDb : -lift * se::kMinSiteGainDb; }

double nowSeconds()
{
    using namespace std::chrono;
    static const steady_clock::time_point t0 = steady_clock::now();
    return duration<double>(steady_clock::now() - t0).count();
}

struct KnobSpec { uint32_t param; const char* label; };
const KnobSpec kKnobs[] = {
    {kParamTimeMs, "TIME"}, {kParamMix, "MIX"}, {kParamFeedback, "FEEDBACK"},
    {kParamScramble, "SCRAMBLE"}, {kParamWidth, "WIDTH"}, {kParamSplit, "SPLIT"},
};
constexpr int kNumKnobs = 6;
constexpr float kKnobR = 20.f;

}  // namespace

class ScrambledEchoUI : public UI
{
public:
    ScrambledEchoUI()
        : UI(DISTRHO_UI_DEFAULT_WIDTH, DISTRHO_UI_DEFAULT_HEIGHT, false),
          fPresets(se::loadEmbeddedPresets())
    {
        loadSharedResources();
        const double sf = getScaleFactor();
        setGeometryConstraints((uint) (720 * sf), (uint) (520 * sf), false, false);
        std::fill(fValues, fValues + kParamCount, 0.f);
        fValues[kParamMap] = se::kDefaultPreset;
        fValues[kParamTimeMs] = 1600.f;
        fValues[kParamDivision] = 2.f;
        fValues[kParamMix] = 40.f;
        fValues[kParamFeedback] = 30.f;
        fValues[kParamScramble] = 100.f;
        fValues[kParamWidth] = 100.f;
        fTel = scrambledEchoTelemetry(getPluginInstancePointer());

        fSnapshotPath = envString("SE_UI_SNAPSHOT");
        const std::string fixedT = envString("SE_UI_T");
        if (!fixedT.empty()) fFixedT = (float) std::atof(fixedT.c_str());
        const std::string fixedTime = envString("SE_UI_TIME");
        if (!fixedTime.empty()) { fFixedTime = (float) std::atof(fixedTime.c_str()); fSnapAlways = true; }
        const std::string view = envString("SE_UI_VIEW");
        if (!view.empty()) se::decodeEggView(view, fView);
        loadDemo(envString("SE_UI_DEMO"));
    }

protected:
    // ------------------------------------------------------------------------------------------ host -> UI

    void parameterChanged(uint32_t index, float value) override
    {
        if (index < kParamCount) { fValues[index] = value; repaint(); }
    }

    void stateChanged(const char* key, const char* value) override
    {
        if (std::strcmp(key, SE_STATE_EGG_VIEW) == 0) {
            if (value && value[0] && envString("SE_UI_VIEW").empty()) se::decodeEggView(value, fView);
            repaint();
            return;
        }
        if (std::strcmp(key, SE_STATE_CUSTOM_MAP) != 0) return;
        fCustomError.clear();
        fHasCustom = false;
        if (value && value[0]) {
            se::TapMap m;
            std::string err;
            if (se::loadMapFile(value, m, err)) { fCustom = std::move(m); fHasCustom = true; }
            else fCustomError = err;
        }
        repaint();
    }

    // ------------------------------------------------------------------------------------------ drawing

    void onNanoDisplay() override
    {
        const double now = fFixedTime >= 0.f ? fFixedTime : nowSeconds();
        const float dt = fLastFrame < 0 ? 0.f : clampf((float) (now - fLastFrame), 0.f, 0.1f);
        fLastFrame = now;
        updateAnimation((float) now, dt);

        const float s = uiScale();
        const float LW = getWidth() / s, LH = getHeight() / s;

        if (!fEggTried) {
            fEggTried = true;
            if (!fEgg.init()) d_stderr("Scrambled Echo: 3D egg disabled (%s)", fEgg.error().c_str());
        }
        se::EggCamera cam = camera();
        if (fEgg.ready()) {
            se::EggFrame frame;
            frame.cam = cam;
            frame.time = (float) now;
            frame.heat = fHeat;
            for (int b = 0; b < se::kBands; ++b) frame.band[b] = fBand[b];
            fEgg.draw(frame);
        }

        save();
        scale(s, s);
        fontFace(NANOVG_DEJAVU_SANS_TTF);
        if (!fEgg.ready()) {
            beginPath();
            rect(0, 0, LW, LH);
            fillColor(Color(10, 12, 20));
            fill();
            fontSize(13);
            fillColor(kMuted);
            textAlign(ALIGN_CENTER | ALIGN_MIDDLE);
            text(LW * 0.5f, LH * 0.45f, ("3D view unavailable: " + fEgg.error()).c_str(), nullptr);
        }
        drawNodes(cam, s);
        drawEggOverlay(LW, LH);
        drawHeader(LW);
        drawStrip(LW, LH);
        restore();
        fFramesDrawn++;
    }

    // Snapshot hook for docs/CI (screen capture is unavailable on headless sessions):
    // SE_UI_SNAPSHOT=<file.ppm> renders the editor into that file once, after a few warm-up frames.
    void uiIdle() override
    {
        if (fDemoActive) { demoIdle(); return; }
        if (!fSnapshotPath.empty() && !fSnapshotDone) {
            if (fFramesDrawn >= 3 && !fSnapshotRequested) {
                fSnapshotRequested = true;
                fSnapshotAtFrame = fFramesDrawn;
                getWindow().renderToPicture(fSnapshotPath.c_str());
            } else if (fSnapshotRequested && fFramesDrawn > fSnapshotAtFrame) {
                fSnapshotDone = true;
            }
            repaint();
            return;
        }
        // Full frame rate while audio runs, a drag is active or the egg is still settling; otherwise the idle
        // breathing is drawn at 24 fps to keep the host's GPU/CPU load low.
        const double now = nowSeconds();
        const bool busy = fAudioActive || fDragMode != DragNone || fMotion > 0.02f;
        if (busy || now - fLastFrame > 1.0 / 24.0) repaint();
    }

    // ------------------------------------------------------------------------------------------ demo renderer
    // SE_UI_DEMO=<dir>: offline video frames. <dir>/input.f32 is stereo interleaved float32 at 48 kHz,
    // <dir>/params.txt one line per frame with every parameter value followed by camera yaw, pitch, zoom.
    // Each frame runs the next 1/fps of audio through a private DSP core with that frame's parameters (the
    // same core and order as the plugin, so its telemetry matches the audio rendered through the VST3) and
    // writes <dir>/frames/fNNNNN.ppm; <dir>/done marks the end.

    static constexpr int kDemoFps = 24;
    static constexpr int kDemoRate = 48000;

    void loadDemo(const std::string& dir)
    {
        if (dir.empty()) return;
        std::FILE* f = std::fopen((dir + "/input.f32").c_str(), "rb");
        if (!f) return;
        float buf[4096];
        size_t n;
        while ((n = std::fread(buf, sizeof(float), 4096, f)) > 0) fDemoInput.insert(fDemoInput.end(), buf, buf + n);
        std::fclose(f);
        std::FILE* p = std::fopen((dir + "/params.txt").c_str(), "r");
        if (!p) return;
        char line[8192];
        while (std::fgets(line, sizeof line, p)) {
            std::vector<float> row;
            char* s = line;
            char* end = nullptr;
            for (float v = std::strtof(s, &end); end != s; v = std::strtof(s, &end)) { row.push_back(v); s = end; }
            if ((int) row.size() >= kParamCount + 3) fDemoRows.push_back(row);
        }
        std::fclose(p);
        if (fDemoRows.empty() || fDemoInput.empty()) return;
        fDemoDir = dir;
        fDemoCore.prepare(kDemoRate);
        fTel = &fDemoCore.telemetry();
        fDemoActive = true;
    }

    void demoIdle()
    {
        if (fDemoPending) {
            if (fFramesDrawn <= fDemoReqDrawn) {
                // an expose can get lost (e.g. the session locks); ask for the same frame again
                if (nowSeconds() - fDemoReqTime > 2.0) {
                    fDemoReqTime = nowSeconds();
                    char path[64];
                    std::snprintf(path, sizeof path, "/frames/f%05d.ppm", fDemoFrame);
                    getWindow().renderToPicture((fDemoDir + path).c_str());
                }
                repaint();
                return;
            }
            fDemoPending = false;
            ++fDemoFrame;
        }
        if (fDemoFrame >= (int) fDemoRows.size()) {
            if (std::FILE* f = std::fopen((fDemoDir + "/done").c_str(), "w")) std::fclose(f);
            fDemoActive = false;
            return;
        }
        const std::vector<float>& row = fDemoRows[(size_t) fDemoFrame];
        for (int i = 0; i < kParamCount; ++i) fValues[i] = row[(size_t) i];
        fView.yaw = row[(size_t) kParamCount];
        fView.pitch = row[(size_t) kParamCount + 1];
        fView.zoom = row[(size_t) kParamCount + 2];
        const int mapIdx = (int) (fValues[kParamMap] + 0.5f);
        if (mapIdx != fDemoMap) { fDemoMap = mapIdx; fDemoCore.setMaps(fPresets[se::kControlPreset], selectedMap()); }

        se::Params prm;
        prm.trainMs = fValues[kParamSync] > 0.5f ? se::syncedTrainMs((int) (fValues[kParamDivision] + 0.5f), 120.0) : fValues[kParamTimeMs];
        prm.mix = fValues[kParamMix] * 0.01f;
        prm.feedback = fValues[kParamFeedback] * 0.01f;
        prm.scramble = fValues[kParamScramble] * 0.01f;
        prm.width = fValues[kParamWidth] * 0.01f;
        prm.commutator = fValues[kParamView] > 0.5f;
        prm.split = fValues[kParamSplit] * 0.01f;
        for (int s = 0; s < se::kBands; ++s) { prm.siteSplit[s] = fValues[kParamSiteSplit0 + s] * 0.01f; prm.siteGainDb[s] = fValues[kParamSiteGain0 + s]; }
        fDemoCore.setParams(prm);
        const int n = kDemoRate / kDemoFps;
        std::vector<float> l(n, 0.f), r(n, 0.f), ol(n), orr(n);
        for (int i = 0; i < n; ++i) {
            const size_t k = ((size_t) fDemoFrame * n + i) * 2;
            if (k + 1 < fDemoInput.size()) { l[i] = fDemoInput[k]; r[i] = fDemoInput[k + 1]; }
        }
        fDemoCore.process(l.data(), r.data(), ol.data(), orr.data(), n);
        fFixedTime = (float) (fDemoFrame + 1) / kDemoFps;

        char path[64];
        std::snprintf(path, sizeof path, "/frames/f%05d.ppm", fDemoFrame);
        fDemoReqDrawn = fFramesDrawn;
        fDemoReqTime = nowSeconds();
        fDemoPending = true;
        getWindow().renderToPicture((fDemoDir + path).c_str());
    }

    // ------------------------------------------------------------------------------------------ input

    bool onMouse(const MouseEvent& ev) override
    {
        const float s = uiScale();
        const double x = ev.pos.getX() / s, y = ev.pos.getY() / s;
        const float LW = getWidth() / s, LH = getHeight() / s;

        if (!ev.press) {
            if (fDragMode == DragKnob && fDragParam >= 0) editParameter((uint32_t) fDragParam, false);
            if (fDragMode == DragNode && fDragNode >= 0) {
                editParameter(kParamSiteSplit0 + fDragNode, false);
                editParameter(kParamSiteGain0 + fDragNode, false);
                saveView();
            }
            if (fDragMode == DragOrbit) saveView();
            const bool had = fDragMode != DragNone;
            fDragMode = DragNone; fDragParam = -1; fDragNode = -1;
            return had;
        }

        if (ev.button == 1) {
            const bool dbl = (ev.time - fLastClickTime) < 350 && std::fabs(x - fLastClickX) < 6 && std::fabs(y - fLastClickY) < 6;
            fLastClickTime = ev.time; fLastClickX = x; fLastClickY = y;

            if (headerClick(x, y, LW) || stripClick(x, y, LW, LH)) return true;

            const int node = hitNode(x, y);
            if (node >= 0) {
                if (dbl) { resetSite(node); return true; }
                fDragMode = DragNode;
                fDragNode = node;
                fView.selected = node;
                fDragStartX = x; fDragStartY = y;
                fDragStartSplit = fValues[kParamSiteSplit0 + node];
                fDragStartLift = gainToLift(fValues[kParamSiteGain0 + node]);
                editParameter(kParamSiteSplit0 + node, true);
                editParameter(kParamSiteGain0 + node, true);
                repaint();
                return true;
            }
            if (y > kHeaderH && y < LH - kStripH) {
                if (dbl) { fView.yaw = 0.55f; fView.pitch = 0.18f; fView.zoom = 1.f; saveView(); repaint(); return true; }
                startOrbit(x, y);
                return true;
            }
            return false;
        }
        if (ev.button == 2 || ev.button == 3) {
            if (y > kHeaderH && y < LH - kStripH) { startOrbit(x, y); return true; }
        }
        return false;
    }

    bool onMotion(const MotionEvent& ev) override
    {
        const float s = uiScale();
        const double x = ev.pos.getX() / s, y = ev.pos.getY() / s;
        const int hover = fDragMode == DragNone ? hitNode(x, y) : fDragNode;
        if (hover != fHoverNode) { fHoverNode = hover; repaint(); }

        switch (fDragMode) {
        case DragKnob: {
            const float sens = (ev.mod & kModifierShift) ? 1000.f : 200.f;
            const float n = clampf(fDragStartNorm + (float) (fDragStartY - y) / sens, 0.f, 1.f);
            const uint32_t p = (uint32_t) fDragParam;
            float v = fromNorm(p, n);
            if (p == kParamDivision) v = std::round(v);
            if (v != fValues[p]) { fValues[p] = v; setParameterValue(p, v); repaint(); }
            return true;
        }
        case DragNode: {
            const se::EggCamera cam = camera();
            const float ppu = fEgg.pixelsPerUnit(cam) / s;  // logical px per world unit
            const float fine = (ev.mod & kModifierShift) ? 0.25f : 1.f;
            const float split = clampf(fDragStartSplit * 0.01f + fine * (float) (x - fDragStartX) / (ppu * se::EggRenderer::kSplitDistance), 0.f, 1.f);
            const float lift = clampf(fDragStartLift - fine * (float) (y - fDragStartY) / (ppu * se::EggRenderer::kLiftDistance), -1.f, 1.f);
            setParam(kParamSiteSplit0 + fDragNode, split * 100.f);
            setParam(kParamSiteGain0 + fDragNode, liftToGain(lift));
            return true;
        }
        case DragOrbit:
            fView.yaw = fOrbitYaw - (float) (x - fDragStartX) * 0.01f;
            fView.pitch = clampf(fOrbitPitch + (float) (y - fDragStartY) * 0.006f, -1.2f, 1.2f);
            repaint();
            return true;
        default:
            return false;
        }
    }

    bool onScroll(const ScrollEvent& ev) override
    {
        const float s = uiScale();
        const double x = ev.pos.getX() / s, y = ev.pos.getY() / s;
        const float LW = getWidth() / s, LH = getHeight() / s;
        for (int i = 0; i < kNumKnobs; ++i) {
            float cx, cy;
            knobCenter(i, LW, LH, cx, cy);
            const float dx = (float) x - cx, dy = (float) y - cy;
            if (dx * dx + dy * dy <= (kKnobR + 12) * (kKnobR + 12)) {
                const uint32_t p = knobParam(kKnobs[i]);
                float v;
                if (p == kParamDivision)
                    v = clampf(fValues[p] + (ev.delta.getY() > 0 ? 1.f : -1.f), 0.f, se::kNumDivisions - 1.f);
                else
                    v = fromNorm(p, clampf(toNorm(p, fValues[p]) + (float) ev.delta.getY() * 0.02f, 0.f, 1.f));
                editParameter(p, true);
                setParam(p, v);
                editParameter(p, false);
                return true;
            }
        }
        if (y > kHeaderH && y < LH - kStripH) {
            if (std::fabs(ev.delta.getX()) > 1e-6 || (ev.mod & (kModifierShift | kModifierControl))) {
                // horizontal two-finger swipe (or modifier + wheel) orbits
                const float dxs = (float) ev.delta.getX(), dys = (float) ev.delta.getY();
                if (ev.mod & kModifierControl) fView.pitch = clampf(fView.pitch + dys * 0.06f, -1.2f, 1.2f);
                else fView.yaw += (std::fabs(dxs) > 1e-6f ? dxs : dys) * 0.08f;
            } else {
                fView.zoom = clampf(fView.zoom * std::pow(1.1f, (float) ev.delta.getY()), 0.5f, 2.5f);
            }
            saveView();
            repaint();
            return true;
        }
        return false;
    }

private:
    enum DragMode { DragNone, DragKnob, DragNode, DragOrbit };

    float uiScale() const { return std::fmin(getWidth() / kBaseW, getHeight() / kBaseH); }

    se::EggCamera camera() const
    {
        se::EggCamera c;
        c.yaw = fView.yaw; c.pitch = fView.pitch; c.zoom = fView.zoom;
        c.widthPx = (int) getWidth(); c.heightPx = (int) getHeight();
        const float s = uiScale();
        const float LH = getHeight() / s;
        c.centerX = 0.47f;
        c.centerY = (kHeaderH + (LH - kStripH - kHeaderH) * 0.53f) / LH;
        c.scale = s;
        return c;
    }

    void saveView() { setState(SE_STATE_EGG_VIEW, se::encodeEggView(fView).c_str()); }

    void setParam(uint32_t p, float v)
    {
        fValues[p] = v;
        setParameterValue(p, v);
        repaint();
    }

    void resetSite(int site)
    {
        for (uint32_t p : {(uint32_t) (kParamSiteSplit0 + site), (uint32_t) (kParamSiteGain0 + site)}) {
            editParameter(p, true);
            setParam(p, 0.f);
            editParameter(p, false);
        }
    }

    void resetAllEdits()
    {
        std::vector<uint32_t> ps = {(uint32_t) kParamSplit};
        for (int i = 0; i < se::kBands; ++i) { ps.push_back(kParamSiteSplit0 + i); ps.push_back(kParamSiteGain0 + i); }
        for (uint32_t p : ps) {
            if (fValues[p] == 0.f) continue;
            editParameter(p, true);
            setParam(p, 0.f);
            editParameter(p, false);
        }
    }

    void startOrbit(double x, double y)
    {
        fDragMode = DragOrbit;
        fDragStartX = x; fDragStartY = y;
        fOrbitYaw = fView.yaw; fOrbitPitch = fView.pitch;
    }

    bool isEdited() const
    {
        se::Params p;
        p.split = fValues[kParamSplit] * 0.01f;
        for (int i = 0; i < se::kBands; ++i) { p.siteSplit[i] = fValues[kParamSiteSplit0 + i] * 0.01f; p.siteGainDb[i] = fValues[kParamSiteGain0 + i]; }
        return se::isEdited(p);
    }

    float effectiveSplit(int b) const { return clampf(fValues[kParamSplit] * 0.01f + fValues[kParamSiteSplit0 + b] * 0.01f, 0.f, 1.f); }

    // ------------------------------------------------------------------------------------------ map data

    const se::TapMap& selectedMap() const
    {
        const int idx = (int) (fValues[kParamMap] + 0.5f);
        if (idx == se::kCustomMapIndex && fHasCustom) return fCustom;
        if (idx >= 0 && idx < (int) fPresets.size()) return fPresets[idx];
        return fPresets[se::kDefaultPreset];
    }

    static float signedMag(const se::Tap& t)
    {
        const float m = std::sqrt(t.re * t.re + t.im * t.im);
        return t.re < 0 ? -m : m;
    }

    // Dense F grid of a map (cells missing from the tap list are F = 0), cached per map pointer.
    struct Grid { const se::TapMap* map = nullptr; size_t taps = 0; int nS = 1, nT = 1; std::vector<float> f; };

    static void fillGrid(Grid& g, const se::TapMap& m)
    {
        if (g.map == &m && g.taps == m.taps.size()) return;
        g.map = &m; g.taps = m.taps.size();
        g.nS = std::max(1, m.nSites); g.nT = std::max(1, m.depth);
        g.f.assign((size_t) g.nS * g.nT, 0.f);
        for (const se::Tap& t : m.taps)
            if (t.site >= 0 && t.site < g.nS && t.step >= 1 && t.step <= g.nT) g.f[(size_t) t.site * g.nT + t.step - 1] = signedMag(t);
    }

    // F of a grid at a pan position (0..1) and train fraction (0..1), linear in time between echo steps.
    static float sampleGrid(const Grid& g, float pan, float frac)
    {
        const int site = std::min(g.nS - 1, std::max(0, (int) std::lround(pan * (g.nS - 1))));
        const float t = clampf(frac * g.nT, 1.f, (float) g.nT) - 1.f;
        const int t0 = (int) t, t1 = std::min(g.nT - 1, t0 + 1);
        const float a = t - t0;
        return g.f[(size_t) site * g.nT + t0] * (1.f - a) + g.f[(size_t) site * g.nT + t1] * a;
    }

    float effectiveF(int band, float frac)
    {
        const float s = fValues[kParamScramble] * 0.01f;
        const float pan = (float) band / (se::kBands - 1);
        return (1.f - s) * sampleGrid(fCtlGrid, pan, frac) + s * sampleGrid(fSelGrid, pan, frac);
    }

    // ------------------------------------------------------------------------------------------ animation

    void updateAnimation(float now, float dt)
    {
        fillGrid(fCtlGrid, fPresets[se::kControlPreset]);
        fillGrid(fSelGrid, selectedMap());

        // audio activity: telemetry block counter advancing
        bool active = false;
        float phase = 1e3f, level = 0.f;
        if (fTel) {
            const uint32_t blocks = fTel->blocks.load(std::memory_order_relaxed);
            if (blocks != fLastBlocks) { fLastBlocks = blocks; fLastBlockTime = now; }
            level = fTel->level.load(std::memory_order_relaxed);
            phase = fTel->phase.load(std::memory_order_relaxed);
            active = (now - fLastBlockTime) < 0.3f && level > 1e-4f;
        }
        fAudioActive = active;

        // time cursor in train fractions: sweeps from the last onset, replays with feedback, rests when idle
        float frac;
        if (fFixedT >= 0.f) frac = fFixedT / std::max(1, fSelGrid.nT);
        else if (active && phase < 1e3f) frac = (fValues[kParamFeedback] > 0.5f && phase > 1.f) ? std::fmod(phase, 1.f) : std::fmin(phase, 1.f);
        else frac = 0.72f + 0.08f * std::sin(2.f * kPi * now / 7.f);
        fCursor = frac;

        // tap activity -> flashes, with a slowly adapting reference so quiet and loud inputs both read
        float act[se::kBands], pol[se::kBands], peak = 0.f;
        for (int b = 0; b < se::kBands; ++b) {
            float p = 0.f, n = 0.f;
            if (fTel && active) { p = fTel->bandPos[b].load(std::memory_order_relaxed); n = fTel->bandNeg[b].load(std::memory_order_relaxed); }
            act[b] = p + n;
            pol[b] = act[b] > 1e-9f ? (p - n) / act[b] : 0.f;
            peak = std::fmax(peak, act[b]);
        }
        fActRef = std::fmax(peak, fActRef * std::exp(-dt / 2.5f));
        const bool snap = fFirstFrame || fSnapAlways;
        fFirstFrame = false;
        const float kOpen = snap ? 1.f : 1.f - std::exp(-dt / 0.06f);
        const float kMove = snap ? 1.f : 1.f - std::exp(-dt / 0.05f);
        const float kFlashUp = snap ? 1.f : 1.f - std::exp(-dt / 0.015f), kFlashDown = 1.f - std::exp(-dt / 0.18f);
        float heat = 0.f, motion = 0.f;
        for (int b = 0; b < se::kBands; ++b) {
            const float F = effectiveF(b, frac);
            const float open = clampf(1.f - std::fabs(F), 0.f, 1.f);
            se::BandVisual& v = fBand[b];
            const float split = effectiveSplit(b), lift = gainToLift(fValues[kParamSiteGain0 + b]);
            motion += std::fabs(open - v.open) + std::fabs(split - v.split) + std::fabs(lift - v.lift);
            v.open += (open - v.open) * kOpen;
            v.split += (split - v.split) * kMove;
            v.lift += (lift - v.lift) * kMove;
            const float target = fActRef > 1e-9f ? std::pow(clampf(act[b] / fActRef, 0.f, 1.f), 0.7f) : 0.f;
            const float base = F < -0.05f ? 0.4f * std::fmin(1.f, -F * 2.f) : 0.f;  // inverted sites keep a cool tint
            const float goal = std::fmax(base, target);
            v.flash += (goal - v.flash) * (goal > v.flash ? kFlashUp : kFlashDown);
            v.polarity = target > 0.05f ? pol[b] : (F < 0.f ? -1.f : 1.f);
            heat += v.flash;
        }
        fMotion = motion;
        const float heatGoal = clampf(heat / se::kBands * 1.4f, 0.f, 1.f);
        fHeat += (heatGoal - fHeat) * (snap ? 1.f : 1.f - std::exp(-dt / 0.25f));
    }

    // ------------------------------------------------------------------------------------------ nodes

    void nodeScreen(const se::EggCamera& cam, int b, bool rest, float& x, float& y) const
    {
        float w[3];
        fEgg.nodeWorld(cam, b, rest ? 0.f : fBand[b].split, rest ? 0.f : fBand[b].lift, w);
        float px = 0, py = 0;
        fEgg.project(cam, w, px, py);
        x = px / cam.scale; y = py / cam.scale;
    }

    int hitNode(double x, double y) const
    {
        if (!fEgg.ready()) return -1;
        const se::EggCamera cam = camera();
        int best = -1;
        float bestD = 12.f * 12.f;
        for (int b = 0; b < se::kBands; ++b) {
            float nx, ny;
            nodeScreen(cam, b, false, nx, ny);
            const float d = (float) ((nx - x) * (nx - x) + (ny - y) * (ny - y));
            if (d < bestD) { bestD = d; best = b; }
        }
        return best;
    }

    void drawNodes(const se::EggCamera& cam, float)
    {
        if (!fEgg.ready()) return;
        const int kick = selectedMap().kickSite;
        const int kickBand = selectedMap().nSites > 1 ? (int) std::lround((float) kick / (selectedMap().nSites - 1) * (se::kBands - 1)) : -1;
        for (int b = 0; b < se::kBands; ++b) {
            float rx, ry, nx, ny;
            nodeScreen(cam, b, true, rx, ry);
            nodeScreen(cam, b, false, nx, ny);
            const bool moved = fValues[kParamSiteSplit0 + b] > 0.05f || std::fabs(fValues[kParamSiteGain0 + b]) > 0.05f || fValues[kParamSplit] > 0.05f;
            const bool hot = b == fHoverNode || b == fDragNode;
            const se::BandVisual& v = fBand[b];
            const Color tint = v.polarity < 0 ? kCyan : kGold;

            if (moved) {
                beginPath();
                moveTo(rx, ry);
                lineTo(nx, ny);
                strokeColor(kGold.withAlpha(0.55f));
                strokeWidth(1.2f);
                stroke();
                beginPath();
                circle(rx, ry, 2.2f);
                fillColor(kText.withAlpha(0.45f));
                fill();
            }
            if (v.flash > 0.2f) {
                beginPath();
                circle(nx, ny, 7.f + 9.f * v.flash);
                fillPaint(radialGradient(nx, ny, 2.f, 7.f + 9.f * v.flash, tint.withAlpha(0.45f * v.flash), tint.withAlpha(0.f)));
                fill();
            }
            beginPath();
            circle(nx, ny, hot ? 7.5f : 5.5f);
            fillColor(moved ? kGold.withAlpha(0.95f) : Color(14, 16, 26, 220));
            fill();
            strokeColor(moved ? Color(255, 236, 190) : (hot ? kText : kText.withAlpha(0.75f)));
            strokeWidth(hot ? 2.f : 1.4f);
            stroke();

            fontSize(10.5f);
            textAlign(ALIGN_LEFT | ALIGN_MIDDLE);
            fillColor(hot ? kText : kMuted.withAlpha(0.9f));
            char label[32];
            std::snprintf(label, sizeof label, b == kickBand ? "%d  kick" : "%d", b);
            text(nx + 11.f, ny + 0.5f, label, nullptr);

            if (hot) {
                char info[96];
                std::snprintf(info, sizeof info, "site %d   split %.0f %%   %+.1f dB   F %.2f", b,
                              effectiveSplit(b) * 100.f, fValues[kParamSiteGain0 + b], effectiveF(b, fCursor));
                fontSize(11.f);
                const float tw = 236.f;
                beginPath();
                roundedRect(nx + 12.f, ny - 30.f, tw, 18.f, 4.f);
                fillColor(Color(10, 12, 20, 220));
                fill();
                fillColor(kText);
                textAlign(ALIGN_LEFT | ALIGN_MIDDLE);
                text(nx + 18.f, ny - 21.f, info, nullptr);
            }
        }
    }

    // ------------------------------------------------------------------------------------------ overlays

    void drawEggOverlay(float LW, float LH)
    {
        const float top = kHeaderH + 14.f, left = 24.f;
        const se::TapMap& m = selectedMap();
        const int nT = fSelGrid.nT, nS = fSelGrid.nS;

        // scrims keep the text readable when shards fly over it
        const float eggBottom = LH - kStripH;
        beginPath();
        rect(0, kHeaderH, 300.f, eggBottom - kHeaderH);
        fillPaint(linearGradient(150.f, 0, 300.f, 0, Color(7, 8, 14, 205), Color(7, 8, 14, 0)));
        fill();
        beginPath();
        rect(0, eggBottom - 40.f, LW, 40.f);
        fillPaint(linearGradient(0, eggBottom - 40.f, 0, eggBottom - 14.f, Color(7, 8, 14, 0), Color(7, 8, 14, 190)));
        fill();

        fontSize(10.5f);
        fillColor(kMuted);
        textAlign(ALIGN_LEFT | ALIGN_TOP);
        text(left, top, "OTOC ECHO STEP", nullptr);
        char buf[96];
        std::snprintf(buf, sizeof buf, "t = %.0f / %d", clampf(fCursor * nT, 1.f, (float) nT), nT);
        fontSize(24.f);
        fillColor(kText);
        text(left, top + 14.f, buf, nullptr);

        // live F(site, t) map at the current Scramble, with the time cursor
        const float hx = left, hy = top + 48.f, hw = 196.f, hh = 64.f;
        const float s = fValues[kParamScramble] * 0.01f;
        const bool cView = fValues[kParamView] > 0.5f;
        const float cw = hw / nT, ch = hh / nS;
        beginPath();
        rect(hx - 1, hy - 1, hw + 2, hh + 2);
        fillColor(Color(6, 8, 14, 200));
        fill();
        for (int site = 0; site < nS; ++site)
            for (int t = 0; t < nT; ++t) {
                const float pan = nS > 1 ? (float) site / (nS - 1) : 0.5f;
                const float frac = (t + 1.f) / nT;
                float f = (1.f - s) * sampleGrid(fCtlGrid, pan, frac) + s * fSelGrid.f[(size_t) site * nT + t];
                float a;
                Color c;
                if (cView) { a = clampf((1.f - f) * 0.5f, 0.f, 1.f); c = kAmber; }
                else { a = std::fmin(1.f, std::fabs(f)); c = f >= 0 ? kGold : kCyan; }
                beginPath();
                rect(hx + t * cw, hy + site * ch, cw - 0.4f, ch - 0.4f);
                fillColor(c.withAlpha(0.05f + 0.9f * a));
                fill();
            }
        const float cx = hx + clampf(fCursor, 0.f, 1.f) * hw;
        beginPath();
        rect(cx - 1.f, hy - 3.f, 2.f, hh + 6.f);
        fillColor(kText);
        fill();
        fontSize(9.5f);
        fillColor(kDim);
        textAlign(ALIGN_LEFT | ALIGN_TOP);
        text(hx, hy + hh + 4.f, cView ? "C(site, t)" : "F(site, t)", nullptr);
        textAlign(ALIGN_RIGHT | ALIGN_TOP);
        std::snprintf(buf, sizeof buf, "%d sites x %d steps", nS, nT);
        text(hx + hw, hy + hh + 4.f, buf, nullptr);

        fontSize(11.f);
        fillColor(kMuted);
        textAlign(ALIGN_LEFT | ALIGN_TOP);
        const char* legend = "12 bands = 12 qubit sites.\nCrack = 1 - |F(site, t)|.\nShards flash as their taps fire:\ngold in phase, blue inverted.";
        textBox(left, hy + hh + 22.f, 200.f, legend, nullptr);
        float lb[4];
        textBoxBounds(left, hy + hh + 22.f, 200.f, legend, nullptr, lb);

        // map description under the legend
        if (!fCustomError.empty() || !m.description.empty()) {
            const std::string desc = !fCustomError.empty() ? "Custom map not loaded: " + fCustomError : m.description;
            fontSize(10.5f);
            fillColor(kDim);
            textBox(left, lb[3] + 12.f, 200.f, desc.c_str(), nullptr);
        }

        // provenance, top right
        textAlign(ALIGN_RIGHT | ALIGN_TOP);
        fontSize(10.f);
        fillColor(kDim);
        const std::string job = m.jobId.empty() ? std::string("no job id") : "otoc-echo-v1 " + m.jobId.substr(0, 8);
        text(LW - 24.f, top, ("Moth Atlas  " + job).c_str(), nullptr);
        text(LW - 24.f, top + 14.f, "shell: entanglement-shader-v1 9214cb9d", nullptr);
        text(LW - 24.f, top + 28.f, "emulator (aer)", nullptr);

        // interaction hint, bottom left of the egg area
        fontSize(10.5f);
        fillColor(kDim);
        textAlign(ALIGN_LEFT | ALIGN_BOTTOM);
        text(left, LH - kStripH - 10.f, "drag a site node: out = split (pan + delay spread), up/down = gain  |  double-click resets  |  right-drag orbit, wheel zoom", nullptr);
    }

    Rect prevRect(float LW) const { return {LW * 0.5f - 210.f, 15.f, 28.f, 28.f}; }
    Rect nameRect(float LW) const { return {LW * 0.5f - 178.f, 15.f, 268.f, 28.f}; }
    Rect nextRect(float LW) const { return {LW * 0.5f + 94.f, 15.f, 28.f, 28.f}; }

    void drawHeader(float LW)
    {
        beginPath();
        rect(0, 0, LW, kHeaderH);
        fillPaint(linearGradient(0, 0, 0, kHeaderH, Color(8, 9, 16, 235), Color(8, 9, 16, 0)));
        fill();

        fontSize(21.f);
        fillColor(kGold);
        textAlign(ALIGN_LEFT | ALIGN_BASELINE);
        text(24.f, 31.f, "SCRAMBLED ECHO", nullptr);
        fontSize(10.5f);
        fillColor(kMuted);
        text(24.f, 46.f, "the egg is the tap map", nullptr);

        button(prevRect(LW), "<");
        button(nextRect(LW), ">");
        const int idx = (int) (fValues[kParamMap] + 0.5f);
        std::string name;
        if (idx == se::kCustomMapIndex) name = fHasCustom ? "Custom: " + fCustom.name : "Custom JSON (none loaded)";
        else name = selectedMap().name;
        char buf[160];
        std::snprintf(buf, sizeof buf, "%d/%d  %s", idx + 1, se::kCustomMapIndex + 1, name.c_str());
        button(nameRect(LW), buf);

        // honesty label
        const bool edited = isEdited();
        const bool custom = idx == se::kCustomMapIndex && fHasCustom;
        std::string label;
        if (custom) label = edited ? "edited from custom map" : "custom map: " + fCustom.name;
        else label = edited ? "edited from measured map" : "measured on Moth Atlas (otoc-echo-v1, aer)";
        const Color c = edited ? kGold : kMeasured;
        fontSize(11.5f);
        Rectangle<float> bounds;
        textBounds(0, 0, label.c_str(), nullptr, bounds);
        const float tw = bounds.getWidth();
        const float pw = tw + 30.f, px = LW - 24.f - pw;
        beginPath();
        roundedRect(px, 16.f, pw, 26.f, 13.f);
        fillColor(c.withAlpha(0.10f));
        fill();
        strokeColor(c.withAlpha(0.55f));
        strokeWidth(1.f);
        stroke();
        beginPath();
        circle(px + 13.f, 29.f, 3.5f);
        fillColor(c);
        fill();
        fillColor(c);
        textAlign(ALIGN_LEFT | ALIGN_MIDDLE);
        text(px + 22.f, 29.5f, label.c_str(), nullptr);
    }

    void knobCenter(int i, float LW, float LH, float& cx, float& cy) const
    {
        const float span = std::fmin(LW - 410.f, 560.f);
        cx = 52.f + span * i / (kNumKnobs - 1);
        cy = LH - kStripH + 62.f;
    }

    Rect stripButton(int i, float LW, float LH) const
    {
        // two rows on the right: [SYNC][DIV][VIEW] / [LOAD JSON][RESET EDITS]
        const float x0 = LW - 24.f - 270.f, y0 = LH - kStripH + 30.f;
        switch (i) {
        case 0: return {x0, y0, 64.f, 28.f};
        case 1: return {x0 + 70.f, y0, 84.f, 28.f};
        case 2: return {x0 + 160.f, y0, 110.f, 28.f};
        case 3: return {x0, y0 + 36.f, 130.f, 28.f};
        default: return {x0 + 136.f, y0 + 36.f, 134.f, 28.f};
        }
    }

    void drawStrip(float LW, float LH)
    {
        const float y0 = LH - kStripH;
        beginPath();
        rect(0, y0, LW, kStripH);
        fillPaint(linearGradient(0, y0, 0, LH, Color(12, 14, 22, 236), Color(8, 9, 15, 250)));
        fill();
        beginPath();
        moveTo(0, y0 + 0.5f);
        lineTo(LW, y0 + 0.5f);
        strokeColor(Color(255, 196, 84, 40));
        strokeWidth(1.f);
        stroke();

        for (int i = 0; i < kNumKnobs; ++i) drawKnob(i, LW, LH);

        const bool sync = fValues[kParamSync] > 0.5f;
        const int d = std::min(std::max((int) (fValues[kParamDivision] + 0.5f), 0), se::kNumDivisions - 1);
        button(stripButton(0, LW, LH), "SYNC", sync);
        button(stripButton(1, LW, LH), se::kDivisions[d].label, sync);
        button(stripButton(2, LW, LH), fValues[kParamView] > 0.5f ? "VIEW: C" : "VIEW: F", fValues[kParamView] > 0.5f);
        button(stripButton(3, LW, LH), "Load JSON...");
        button(stripButton(4, LW, LH), "Reset edits", isEdited());
    }

    void drawKnob(int i, float LW, float LH)
    {
        float cx, cy;
        knobCenter(i, LW, LH, cx, cy);
        const KnobSpec& k = kKnobs[i];
        const uint32_t p = knobParam(k);
        const float n = clampf(toNorm(p, fValues[p]), 0.f, 1.f);
        const float a0 = 0.75f * kPi, a1 = 2.25f * kPi, a = a0 + (a1 - a0) * n;
        const Color accent = k.param == kParamSplit ? kAmber : kGold;

        beginPath();
        circle(cx, cy, kKnobR);
        fillPaint(radialGradient(cx, cy - 6, 3, kKnobR, Color(44, 50, 68), Color(20, 23, 33)));
        fill();
        beginPath();
        arc(cx, cy, kKnobR + 5, a0, a1, CW);
        strokeColor(kEdge);
        strokeWidth(3);
        lineCap(ROUND);
        stroke();
        beginPath();
        arc(cx, cy, kKnobR + 5, a0, std::fmax(a, a0 + 0.001f), CW);
        strokeColor(accent);
        stroke();
        beginPath();
        moveTo(cx + std::cos(a) * 7, cy + std::sin(a) * 7);
        lineTo(cx + std::cos(a) * (kKnobR - 4), cy + std::sin(a) * (kKnobR - 4));
        strokeColor(kText);
        strokeWidth(2.5f);
        stroke();

        fontSize(10.5f);
        fillColor(kMuted);
        textAlign(ALIGN_CENTER | ALIGN_BOTTOM);
        text(cx, cy - kKnobR - 9, k.label, nullptr);

        char buf[64];
        if (p == kParamDivision) {
            const int dv = std::min(std::max((int) (fValues[p] + 0.5f), 0), se::kNumDivisions - 1);
            std::snprintf(buf, sizeof buf, "%s sync", se::kDivisions[dv].label);
        } else if (p == kParamTimeMs) {
            std::snprintf(buf, sizeof buf, fValues[p] >= 1000 ? "%.2f s" : "%.0f ms", fValues[p] >= 1000 ? fValues[p] / 1000 : fValues[p]);
        } else {
            std::snprintf(buf, sizeof buf, "%.0f %%", fValues[p]);
        }
        fontSize(11.5f);
        fillColor(kText);
        textAlign(ALIGN_CENTER | ALIGN_TOP);
        text(cx, cy + kKnobR + 8, buf, nullptr);
    }

    void button(const Rect& r, const char* label, bool active = false)
    {
        beginPath();
        roundedRect(r.x, r.y, r.w, r.h, 6);
        fillColor(active ? kGold.withAlpha(0.16f) : Color(22, 26, 38, 220));
        fill();
        strokeColor(active ? kGold.withAlpha(0.8f) : kEdge);
        strokeWidth(1);
        stroke();
        fontSize(12);
        fillColor(active ? kGold : kText);
        textAlign(ALIGN_CENTER | ALIGN_MIDDLE);
        text(r.x + r.w * 0.5f, r.y + r.h * 0.5f + 1, label, nullptr);
    }

    bool headerClick(double x, double y, float LW)
    {
        const int nMaps = se::kCustomMapIndex + 1;
        const int map = (int) (fValues[kParamMap] + 0.5f);
        if (prevRect(LW).contains(x, y)) { pulse(kParamMap, (float) ((map + nMaps - 1) % nMaps)); return true; }
        if (nextRect(LW).contains(x, y) || nameRect(LW).contains(x, y)) { pulse(kParamMap, (float) ((map + 1) % nMaps)); return true; }
        return false;
    }

    bool stripClick(double x, double y, float LW, float LH)
    {
        if (y < LH - kStripH) return false;
        if (stripButton(0, LW, LH).contains(x, y)) { pulse(kParamSync, fValues[kParamSync] > 0.5f ? 0.f : 1.f); return true; }
        if (stripButton(1, LW, LH).contains(x, y)) {
            pulse(kParamDivision, (float) (((int) (fValues[kParamDivision] + 0.5f) + 1) % se::kNumDivisions));
            return true;
        }
        if (stripButton(2, LW, LH).contains(x, y)) { pulse(kParamView, fValues[kParamView] > 0.5f ? 0.f : 1.f); return true; }
        if (stripButton(3, LW, LH).contains(x, y)) {
            requestStateFile(SE_STATE_CUSTOM_MAP);
            pulse(kParamMap, (float) se::kCustomMapIndex);
            return true;
        }
        if (stripButton(4, LW, LH).contains(x, y)) { resetAllEdits(); return true; }
        for (int i = 0; i < kNumKnobs; ++i) {
            float cx, cy;
            knobCenter(i, LW, LH, cx, cy);
            const float dx = (float) x - cx, dy = (float) y - cy;
            if (dx * dx + dy * dy <= (kKnobR + 12) * (kKnobR + 12)) {
                const uint32_t p = knobParam(kKnobs[i]);
                fDragMode = DragKnob;
                fDragParam = (int) p;
                fDragStartY = y;
                fDragStartNorm = toNorm(p, fValues[p]);
                editParameter(p, true);
                return true;
            }
        }
        return true;  // swallow clicks on the strip background
    }

    void pulse(uint32_t p, float v)
    {
        editParameter(p, true);
        setParam(p, v);
        editParameter(p, false);
    }

    uint32_t knobParam(const KnobSpec& k) const
    {
        return (k.param == kParamTimeMs && fValues[kParamSync] > 0.5f) ? (uint32_t) kParamDivision : k.param;
    }

    static float toNorm(uint32_t p, float v)
    {
        switch (p) {
        case kParamTimeMs: return std::log(v / 50.f) / std::log(8000.f / 50.f);
        case kParamDivision: return v / (se::kNumDivisions - 1);
        case kParamFeedback: return v / 95.f;
        default: return v / 100.f;
        }
    }

    static float fromNorm(uint32_t p, float n)
    {
        switch (p) {
        case kParamTimeMs: return 50.f * std::pow(8000.f / 50.f, n);
        case kParamDivision: return n * (se::kNumDivisions - 1);
        case kParamFeedback: return n * 95.f;
        default: return n * 100.f;
        }
    }

    float fValues[kParamCount];
    std::vector<se::TapMap> fPresets;
    se::TapMap fCustom;
    bool fHasCustom = false;
    std::string fCustomError;

    se::EggRenderer fEgg;
    bool fEggTried = false;
    se::EggView fView;
    const se::Telemetry* fTel = nullptr;
    Grid fCtlGrid, fSelGrid;
    se::BandVisual fBand[se::kBands];
    float fCursor = 0.75f, fHeat = 0.f, fActRef = 0.f, fMotion = 1.f;
    uint32_t fLastBlocks = 0;
    float fLastBlockTime = -10.f;
    bool fAudioActive = false, fFirstFrame = true;
    double fLastFrame = -1.0;
    float fFixedT = -1.f, fFixedTime = -1.f;
    bool fSnapAlways = false;

    std::string fDemoDir;
    bool fDemoActive = false, fDemoPending = false;
    int fDemoFrame = 0, fDemoMap = -1;
    uint32_t fDemoReqDrawn = 0;
    double fDemoReqTime = 0.0;
    std::vector<float> fDemoInput;
    std::vector<std::vector<float>> fDemoRows;
    se::Core fDemoCore;

    DragMode fDragMode = DragNone;
    int fDragParam = -1, fDragNode = -1, fHoverNode = -1;
    double fDragStartX = 0, fDragStartY = 0;
    float fDragStartNorm = 0, fDragStartSplit = 0, fDragStartLift = 0, fOrbitYaw = 0, fOrbitPitch = 0;
    uint fLastClickTime = 0;
    double fLastClickX = -100, fLastClickY = -100;

    std::string fSnapshotPath;
    bool fSnapshotRequested = false, fSnapshotDone = false;
    uint32_t fFramesDrawn = 0, fSnapshotAtFrame = 0;

    DISTRHO_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(ScrambledEchoUI)
};

UI* createUI()
{
    return new ScrambledEchoUI();
}

END_NAMESPACE_DISTRHO
