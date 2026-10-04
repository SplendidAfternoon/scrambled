#include "DistrhoUI.hpp"

#include "MapBank.hpp"

#include <cmath>
#include <cstdio>

#ifdef _WIN32
extern "C" __declspec(dllimport) unsigned long __stdcall GetEnvironmentVariableA(const char*, char*, unsigned long);
#endif

START_NAMESPACE_DISTRHO

namespace {

constexpr float kW = DISTRHO_UI_DEFAULT_WIDTH;
constexpr float kH = DISTRHO_UI_DEFAULT_HEIGHT;
constexpr float kPi = 3.14159265f;

struct Rect {
    float x, y, w, h;
    bool contains(double px, double py) const { return px >= x && px < x + w && py >= y && py < y + h; }
};

const Rect kPrevMap{24, 66, 30, 30};
const Rect kMapName{58, 66, 268, 30};
const Rect kNextMap{330, 66, 30, 30};
const Rect kView{372, 66, 96, 30};
const Rect kLoad{478, 66, 100, 30};
const Rect kSync{588, 66, 60, 30};
const Rect kDivision{654, 66, 82, 30};
const Rect kHeat{24, 110, 712, 150};

const Color kBgTop(14, 16, 22);
const Color kBgBottom(22, 26, 38);
const Color kPanel(28, 33, 46);
const Color kEdge(58, 66, 88);
const Color kText(226, 230, 240);
const Color kMuted(140, 148, 170);
const Color kPos(64, 214, 196);   // F > 0
const Color kNeg(255, 96, 92);    // F < 0, inverted echo
const Color kSpread(255, 184, 64); // C = (1 - Re F) / 2

struct KnobSpec { uint32_t param; const char* label; float cx; };
const KnobSpec kKnobs[] = {
    {kParamTimeMs, "TIME", 104},
    {kParamMix, "MIX", 242},
    {kParamFeedback, "FEEDBACK", 380},
    {kParamScramble, "SCRAMBLE", 518},
    {kParamWidth, "WIDTH", 656},
};
constexpr float kKnobY = 394, kKnobR = 30;

}  // namespace

class ScrambledEchoUI : public UI
{
public:
    ScrambledEchoUI()
        : UI(DISTRHO_UI_DEFAULT_WIDTH, DISTRHO_UI_DEFAULT_HEIGHT, true),
          fPresets(se::loadEmbeddedPresets())
    {
        loadSharedResources();
        fValues[kParamMap] = se::kDefaultPreset;
        fValues[kParamSync] = 0.f;
        fValues[kParamTimeMs] = 1600.f;
        fValues[kParamDivision] = 2.f;
        fValues[kParamMix] = 40.f;
        fValues[kParamFeedback] = 30.f;
        fValues[kParamScramble] = 100.f;
        fValues[kParamWidth] = 100.f;
        fValues[kParamView] = 0.f;
    }

protected:
    void parameterChanged(uint32_t index, float value) override
    {
        if (index < kParamCount) { fValues[index] = value; repaint(); }
    }

    void stateChanged(const char* key, const char* value) override
    {
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

    void onNanoDisplay() override
    {
        beginPath();
        rect(0, 0, kW, kH);
        fillPaint(linearGradient(0, 0, 0, kH, kBgTop, kBgBottom));
        fill();

        fontFace(NANOVG_DEJAVU_SANS_TTF);
        textAlign(ALIGN_LEFT | ALIGN_BASELINE);
        fontSize(22);
        fillColor(kText);
        text(24, 40, "SCRAMBLED ECHO", nullptr);
        fontSize(12);
        fillColor(kMuted);
        textAlign(ALIGN_RIGHT | ALIGN_BASELINE);
        text(kW - 24, 32, "taps = measured OTOC F(site, t)", nullptr);
        text(kW - 24, 48, "Moth Atlas otoc-echo-v1 · aer emulator", nullptr);

        drawSelector();
        drawHeatmap();
        for (const KnobSpec& k : kKnobs) drawKnob(k);
    }

    // Docs/CI hook: SE_UI_SNAPSHOT=<file.ppm> renders the editor into that file once (screen capture is not
    // available on headless sessions).
    void uiIdle() override
    {
#ifdef _WIN32
        if (fSnapshotDone) return;
        fSnapshotDone = true;
        char path[1024];
        const unsigned long n = GetEnvironmentVariableA("SE_UI_SNAPSHOT", path, sizeof(path));
        if (n > 0 && n < sizeof(path)) {
            getWindow().renderToPicture(path);
            repaint();
        }
#endif
    }

    bool onMouse(const MouseEvent& ev) override
    {
        if (ev.button != 1) return false;
        const double x = ev.pos.getX() / scale(), y = ev.pos.getY() / scale();
        if (!ev.press) {
            if (fDragParam >= 0) { editParameter((uint32_t) fDragParam, false); fDragParam = -1; return true; }
            return false;
        }
        const int nMaps = se::kCustomMapIndex + 1;
        const int map = (int) (fValues[kParamMap] + 0.5f);
        if (kPrevMap.contains(x, y)) { setParam(kParamMap, (float) ((map + nMaps - 1) % nMaps)); return true; }
        if (kNextMap.contains(x, y) || kMapName.contains(x, y)) { setParam(kParamMap, (float) ((map + 1) % nMaps)); return true; }
        if (kLoad.contains(x, y)) { requestStateFile(SE_STATE_CUSTOM_MAP); setParam(kParamMap, (float) se::kCustomMapIndex); return true; }
        if (kView.contains(x, y)) { setParam(kParamView, fValues[kParamView] > 0.5f ? 0.f : 1.f); return true; }
        if (kSync.contains(x, y)) { setParam(kParamSync, fValues[kParamSync] > 0.5f ? 0.f : 1.f); return true; }
        if (kDivision.contains(x, y)) {
            const int d = (int) (fValues[kParamDivision] + 0.5f);
            setParam(kParamDivision, (float) ((d + 1) % se::kNumDivisions));
            return true;
        }
        for (const KnobSpec& k : kKnobs) {
            const float dx = (float) x - k.cx, dy = (float) y - kKnobY;
            if (dx * dx + dy * dy <= (kKnobR + 10) * (kKnobR + 10)) {
                fDragParam = (int) knobParam(k);
                fDragStartY = y;
                fDragStartNorm = toNorm(knobParam(k), fValues[knobParam(k)]);
                editParameter((uint32_t) fDragParam, true);
                return true;
            }
        }
        return false;
    }

    bool onMotion(const MotionEvent& ev) override
    {
        if (fDragParam < 0) return false;
        const double y = ev.pos.getY() / scale();
        const float sens = (ev.mod & kModifierShift) ? 1000.f : 200.f;
        float n = fDragStartNorm + (float) (fDragStartY - y) / sens;
        n = std::fmin(1.f, std::fmax(0.f, n));
        const uint32_t p = (uint32_t) fDragParam;
        float v = fromNorm(p, n);
        if (p == kParamDivision) v = std::round(v);
        if (v != fValues[p]) { fValues[p] = v; setParameterValue(p, v); repaint(); }
        return true;
    }

    bool onScroll(const ScrollEvent& ev) override
    {
        const double x = ev.pos.getX() / scale(), y = ev.pos.getY() / scale();
        for (const KnobSpec& k : kKnobs) {
            const float dx = (float) x - k.cx, dy = (float) y - kKnobY;
            if (dx * dx + dy * dy <= (kKnobR + 10) * (kKnobR + 10)) {
                const uint32_t p = knobParam(k);
                float v;
                if (p == kParamDivision) {
                    v = std::fmin(se::kNumDivisions - 1.f, std::fmax(0.f, fValues[p] + (ev.delta.getY() > 0 ? 1.f : -1.f)));
                } else {
                    const float n = std::fmin(1.f, std::fmax(0.f, toNorm(p, fValues[p]) + (float) ev.delta.getY() * 0.02f));
                    v = fromNorm(p, n);
                }
                editParameter(p, true);
                setParam(p, v);
                editParameter(p, false);
                return true;
            }
        }
        return false;
    }

private:
    double scale() const { return getWidth() / (double) kW; }

    void setParam(uint32_t p, float v)
    {
        fValues[p] = v;
        setParameterValue(p, v);
        repaint();
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

    const se::TapMap* selectedMap() const
    {
        const int idx = (int) (fValues[kParamMap] + 0.5f);
        if (idx == se::kCustomMapIndex) return fHasCustom ? &fCustom : nullptr;
        if (idx >= 0 && idx < (int) fPresets.size()) return &fPresets[idx];
        return nullptr;
    }

    void button(const Rect& r, const char* label, bool active = false)
    {
        beginPath();
        roundedRect(r.x, r.y, r.w, r.h, 6);
        fillColor(active ? kPos.withAlpha(0.22f) : kPanel);
        fill();
        strokeColor(active ? kPos : kEdge);
        strokeWidth(1);
        stroke();
        fontSize(13);
        fillColor(active ? kPos : kText);
        textAlign(ALIGN_CENTER | ALIGN_MIDDLE);
        text(r.x + r.w * 0.5f, r.y + r.h * 0.5f + 1, label, nullptr);
    }

    void drawSelector()
    {
        button(kPrevMap, "<");
        button(kNextMap, ">");
        const int idx = (int) (fValues[kParamMap] + 0.5f);
        const se::TapMap* m = selectedMap();
        std::string name;
        if (idx == se::kCustomMapIndex)
            name = fHasCustom ? "Custom: " + fCustom.name : "Custom JSON (none: Scrambling)";
        else
            name = m ? m->name : "?";
        char buf[160];
        std::snprintf(buf, sizeof(buf), "MAP  %d/%d   %s", idx + 1, se::kCustomMapIndex + 1, name.c_str());
        button(kMapName, buf);
        button(kView, fValues[kParamView] > 0.5f ? "VIEW: C" : "VIEW: F", fValues[kParamView] > 0.5f);
        button(kLoad, "Load JSON...");
        button(kSync, "SYNC", fValues[kParamSync] > 0.5f);
        const int d = (int) (fValues[kParamDivision] + 0.5f);
        button(kDivision, se::kDivisions[std::min(std::max(d, 0), se::kNumDivisions - 1)].label, fValues[kParamSync] > 0.5f);
    }

    void drawHeatmap()
    {
        beginPath();
        roundedRect(kHeat.x - 6, kHeat.y - 6, kHeat.w + 12, kHeat.h + 60, 8);
        fillColor(kPanel);
        fill();

        const se::TapMap& control = fPresets[se::kControlPreset];
        const se::TapMap* sel = selectedMap();
        if (!sel) sel = &fPresets[se::kDefaultPreset];
        const float s = fValues[kParamScramble] * 0.01f;
        const bool shared = sel->nSites == control.nSites && sel->depth == control.depth;
        const int nS = std::max(1, sel->nSites), nT = std::max(1, sel->depth);

        const bool cView = fValues[kParamView] > 0.5f;
        // F view: signed |F|.  C view: (1 - Re F) / 2, with cells missing from the tap list taken as F = 0.
        auto value = [cView](const se::Tap& t) {
            if (cView) return std::fmin(1.f, std::fmax(0.f, (1.f - t.re) * 0.5f));
            const float m = std::sqrt(t.re * t.re + t.im * t.im);
            return t.re < 0 ? -m : m;
        };
        const float empty = cView ? 0.5f : 0.f;
        std::vector<float> grid((size_t) nS * nT, empty), ctl((size_t) nS * nT, empty);
        for (const se::Tap& t : sel->taps)
            if (t.site < nS && t.step >= 1 && t.step <= nT) grid[(size_t) t.site * nT + t.step - 1] = value(t);
        if (shared)
            for (const se::Tap& t : control.taps)
                if (t.site < nS && t.step >= 1 && t.step <= nT) ctl[(size_t) t.site * nT + t.step - 1] = value(t);

        const float cw = kHeat.w / nT, ch = kHeat.h / nS;
        for (int site = 0; site < nS; ++site)
            for (int t = 0; t < nT; ++t) {
                float f = grid[(size_t) site * nT + t];
                f = shared ? (1.f - s) * ctl[(size_t) site * nT + t] + s * f : f * s;
                const float a = std::fmin(1.f, std::fabs(f));
                beginPath();
                rect(kHeat.x + t * cw + 0.5f, kHeat.y + site * ch + 0.5f, cw - 1.f, ch - 1.f);
                fillColor((cView ? kSpread : f >= 0 ? kPos : kNeg).withAlpha(0.06f + 0.94f * a));
                fill();
            }
        beginPath();
        rect(kHeat.x, kHeat.y + sel->kickSite * ch, 3, ch);
        fillColor(kText);
        fill();

        fontSize(11);
        fillColor(kMuted);
        textAlign(ALIGN_LEFT | ALIGN_TOP);
        char info[256];
        std::snprintf(info, sizeof(info), "x: echo step t = 1..%d (delay)   y: site 0..%d (pan L-R)   |   kick site %d   |   job %s",
                      nT, nS - 1, sel->kickSite, sel->jobId.empty() ? "n/a" : sel->jobId.substr(0, 8).c_str());
        text(kHeat.x, kHeat.y + kHeat.h + 6, info, nullptr);
        fillColor(kText.withAlpha(0.85f));
        const std::string desc = !fCustomError.empty() ? "Custom map not loaded: " + fCustomError : sel->description;
        textBox(kHeat.x, kHeat.y + kHeat.h + 22, kHeat.w, desc.c_str(), nullptr);

        textAlign(ALIGN_RIGHT | ALIGN_TOP);
        if (cView) {
            fillColor(kSpread);
            text(kHeat.x + kHeat.w, kHeat.y + kHeat.h + 6, "C = (1 - Re F)/2: operator spread", nullptr);
        } else {
            fillColor(kPos);
            text(kHeat.x + kHeat.w - 100, kHeat.y + kHeat.h + 6, "F > 0", nullptr);
            fillColor(kNeg);
            text(kHeat.x + kHeat.w, kHeat.y + kHeat.h + 6, "F < 0 (inverted)", nullptr);
        }
    }

    void drawKnob(const KnobSpec& k)
    {
        const uint32_t p = knobParam(k);
        const float n = std::fmin(1.f, std::fmax(0.f, toNorm(p, fValues[p])));
        const float a0 = 0.75f * kPi, a1 = 2.25f * kPi, a = a0 + (a1 - a0) * n;

        beginPath();
        circle(k.cx, kKnobY, kKnobR);
        fillPaint(radialGradient(k.cx, kKnobY - 8, 4, kKnobR, Color(46, 52, 70), Color(24, 28, 38)));
        fill();
        beginPath();
        arc(k.cx, kKnobY, kKnobR + 6, a0, a1, CW);
        strokeColor(kEdge);
        strokeWidth(4);
        lineCap(ROUND);
        stroke();
        beginPath();
        arc(k.cx, kKnobY, kKnobR + 6, a0, std::fmax(a, a0 + 0.001f), CW);
        strokeColor(k.param == kParamScramble ? kNeg.withAlpha(0.6f + 0.4f * n) : kPos);
        stroke();
        beginPath();
        moveTo(k.cx + std::cos(a) * 10, kKnobY + std::sin(a) * 10);
        lineTo(k.cx + std::cos(a) * (kKnobR - 4), kKnobY + std::sin(a) * (kKnobR - 4));
        strokeColor(kText);
        strokeWidth(3);
        stroke();

        fontSize(12);
        fillColor(kMuted);
        textAlign(ALIGN_CENTER | ALIGN_BOTTOM);
        text(k.cx, kKnobY - kKnobR - 12, k.label, nullptr);

        char buf[64];
        if (p == kParamDivision) {
            const int d = std::min(std::max((int) (fValues[p] + 0.5f), 0), se::kNumDivisions - 1);
            std::snprintf(buf, sizeof(buf), "%s (sync)", se::kDivisions[d].label);
        } else if (p == kParamTimeMs) {
            std::snprintf(buf, sizeof(buf), fValues[p] >= 1000 ? "%.2f s" : "%.0f ms", fValues[p] >= 1000 ? fValues[p] / 1000 : fValues[p]);
        } else {
            std::snprintf(buf, sizeof(buf), "%.0f %%", fValues[p]);
        }
        fontSize(13);
        fillColor(kText);
        textAlign(ALIGN_CENTER | ALIGN_TOP);
        text(k.cx, kKnobY + kKnobR + 12, buf, nullptr);
    }

    float fValues[kParamCount];
    std::vector<se::TapMap> fPresets;
    se::TapMap fCustom;
    bool fHasCustom = false;
    std::string fCustomError;
    int fDragParam = -1;
    double fDragStartY = 0;
    float fDragStartNorm = 0;
    bool fSnapshotDone = false;

    DISTRHO_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(ScrambledEchoUI)
};

UI* createUI()
{
    return new ScrambledEchoUI();
}

END_NAMESPACE_DISTRHO
