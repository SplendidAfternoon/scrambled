#include "DistrhoPlugin.hpp"

#include "MapBank.hpp"
#include "ScrambledEchoCore.hpp"

START_NAMESPACE_DISTRHO

class ScrambledEchoPlugin : public Plugin
{
public:
    ScrambledEchoPlugin()
        : Plugin(kParamCount, 0, 2),
          fPresets(se::loadEmbeddedPresets())
    {
        std::fill(fValues, fValues + kParamCount, 0.f);
        fValues[kParamMap] = se::kDefaultPreset;
        fValues[kParamSync] = 0.f;
        fValues[kParamTimeMs] = 1600.f;
        fValues[kParamDivision] = 2.f;
        fValues[kParamMix] = 40.f;
        fValues[kParamFeedback] = 30.f;
        fValues[kParamScramble] = 100.f;
        fValues[kParamWidth] = 100.f;
        fValues[kParamView] = 0.f;
        fCore.prepare(getSampleRate());
        applyMaps();
    }

protected:
    const char* getLabel() const override { return "ScrambledEcho"; }
    const char* getDescription() const override
    {
        return "Multi-tap delay whose taps are a measured OTOC map F(site, t) from Moth Atlas otoc-echo-v1: "
               "delay = echo step, gain = |F|, polarity = sign of F, pan = site.";
    }
    const char* getMaker() const override { return "Moth Hack 2026 / SCRAMBLED"; }
    const char* getHomePage() const override { return DISTRHO_PLUGIN_URI; }
    const char* getLicense() const override { return "ISC"; }
    uint32_t getVersion() const override { return d_version(2, 0, 0); }

    void initAudioPort(bool input, uint32_t index, AudioPort& port) override
    {
        port.groupId = kPortGroupStereo;
        Plugin::initAudioPort(input, index, port);
    }

    void initParameter(uint32_t index, Parameter& p) override
    {
        p.hints = kParameterIsAutomatable;
        switch (index) {
        case kParamMap: {
            p.name = "Map"; p.symbol = "map";
            p.hints |= kParameterIsInteger;
            p.ranges.min = 0.f; p.ranges.max = (float) se::kCustomMapIndex; p.ranges.def = se::kDefaultPreset;
            const int n = se::kCustomMapIndex + 1;
            ParameterEnumerationValue* ev = new ParameterEnumerationValue[n];
            for (int i = 0; i < se::kNumPresets; ++i) {
                ev[i].value = (float) i;
                ev[i].label = i < (int) fPresets.size() ? fPresets[i].name.c_str() : "?";
            }
            ev[se::kCustomMapIndex].value = (float) se::kCustomMapIndex;
            ev[se::kCustomMapIndex].label = "Custom JSON";
            p.enumValues.count = n; p.enumValues.restrictedMode = true; p.enumValues.values = ev;
            break;
        }
        case kParamSync:
            p.name = "Sync"; p.symbol = "sync";
            p.hints |= kParameterIsBoolean | kParameterIsInteger;
            p.ranges.min = 0.f; p.ranges.max = 1.f; p.ranges.def = 0.f;
            break;
        case kParamTimeMs:
            p.name = "Time"; p.symbol = "time"; p.unit = "ms";
            p.hints |= kParameterIsLogarithmic;
            p.ranges.min = 50.f; p.ranges.max = 8000.f; p.ranges.def = 1600.f;
            break;
        case kParamDivision: {
            p.name = "Division"; p.symbol = "division";
            p.hints |= kParameterIsInteger;
            p.ranges.min = 0.f; p.ranges.max = (float) (se::kNumDivisions - 1); p.ranges.def = 2.f;
            ParameterEnumerationValue* ev = new ParameterEnumerationValue[se::kNumDivisions];
            for (int i = 0; i < se::kNumDivisions; ++i) { ev[i].value = (float) i; ev[i].label = se::kDivisions[i].label; }
            p.enumValues.count = se::kNumDivisions; p.enumValues.restrictedMode = true; p.enumValues.values = ev;
            break;
        }
        case kParamMix:
            p.name = "Mix"; p.symbol = "mix"; p.unit = "%";
            p.ranges.min = 0.f; p.ranges.max = 100.f; p.ranges.def = 40.f;
            break;
        case kParamFeedback:
            p.name = "Feedback"; p.symbol = "feedback"; p.unit = "%";
            p.ranges.min = 0.f; p.ranges.max = 95.f; p.ranges.def = 30.f;
            break;
        case kParamScramble:
            p.name = "Scramble"; p.symbol = "scramble"; p.unit = "%";
            p.ranges.min = 0.f; p.ranges.max = 100.f; p.ranges.def = 100.f;
            break;
        case kParamWidth:
            p.name = "Width"; p.symbol = "width"; p.unit = "%";
            p.ranges.min = 0.f; p.ranges.max = 100.f; p.ranges.def = 100.f;
            break;
        case kParamView: {
            p.name = "View"; p.symbol = "view";
            p.hints |= kParameterIsInteger;
            p.ranges.min = 0.f; p.ranges.max = 1.f; p.ranges.def = 0.f;
            ParameterEnumerationValue* ev = new ParameterEnumerationValue[2];
            ev[0].value = 0.f; ev[0].label = "F (echo survives)";
            ev[1].value = 1.f; ev[1].label = "C (operator spread)";
            p.enumValues.count = 2; p.enumValues.restrictedMode = true; p.enumValues.values = ev;
            break;
        }
        case kParamSplit:
            p.name = "Split"; p.symbol = "split"; p.unit = "%";
            p.ranges.min = 0.f; p.ranges.max = 100.f; p.ranges.def = 0.f;
            break;
        default:
            if (index >= (uint32_t) kParamSiteSplit0 && index < (uint32_t) kParamSiteSplit0 + se::kBands) {
                const int s = (int) index - kParamSiteSplit0;
                p.name = String("Site ") + String(s) + " split";
                p.shortName = String("S") + String(s) + " split";
                p.symbol = String("site") + String(s) + "_split";
                p.unit = "%";
                p.ranges.min = 0.f; p.ranges.max = 100.f; p.ranges.def = 0.f;
            } else if (index >= (uint32_t) kParamSiteGain0 && index < (uint32_t) kParamSiteGain0 + se::kBands) {
                const int s = (int) index - kParamSiteGain0;
                p.name = String("Site ") + String(s) + " gain";
                p.shortName = String("S") + String(s) + " gain";
                p.symbol = String("site") + String(s) + "_gain";
                p.unit = "dB";
                p.ranges.min = se::kMinSiteGainDb; p.ranges.max = se::kMaxSiteGainDb; p.ranges.def = 0.f;
            }
            break;
        }
    }

    float getParameterValue(uint32_t index) const override
    {
        return index < kParamCount ? fValues[index] : 0.f;
    }

    void setParameterValue(uint32_t index, float value) override
    {
        if (index >= kParamCount) return;
        fValues[index] = value;
        if (index == kParamMap) applyMaps();
    }

    void initState(uint32_t index, State& state) override
    {
        if (index == 1) {
            state.key = SE_STATE_EGG_VIEW;
            state.label = "Egg view";
            state.description = "camera of the 3D egg editor";
            state.defaultValue = "";
            return;
        }
        if (index != 0) return;
        state.key = SE_STATE_CUSTOM_MAP;
        state.label = "Custom map JSON";
        state.description = "otoc-echo-v1 result, cached job record, or any JSON with a taps list";
        state.defaultValue = "";
        state.hints = kStateIsFilenamePath;
    }

    void setState(const char* key, const char* value) override
    {
        if (std::strcmp(key, SE_STATE_EGG_VIEW) == 0) { fEggView = value; return; }
        if (std::strcmp(key, SE_STATE_CUSTOM_MAP) != 0) return;
        fCustomPath = value;
        if (value == nullptr || value[0] == '\0') {
            fHasCustom = false;
        } else {
            se::TapMap m;
            std::string err;
            if (!se::loadMapFile(value, m, err)) {
                d_stderr("Scrambled Echo: %s", err.c_str());
                return;
            }
            fCustom = std::move(m);
            fHasCustom = true;
        }
        applyMaps();
    }

    String getState(const char* key) const override
    {
        if (std::strcmp(key, SE_STATE_EGG_VIEW) == 0) return fEggView;
        return std::strcmp(key, SE_STATE_CUSTOM_MAP) == 0 ? fCustomPath : String();
    }

public:
    // Direct access for the UI (same process): lock-free, read-only.
    const se::Telemetry& telemetry() const { return fCore.telemetry(); }

protected:

    void sampleRateChanged(double newSampleRate) override
    {
        fCore.prepare(newSampleRate);
    }

    void activate() override { fCore.reset(); }

    void run(const float** inputs, float** outputs, uint32_t frames) override
    {
        se::Params p;
        if (fValues[kParamSync] > 0.5f) {
            const TimePosition& pos = getTimePosition();
            p.trainMs = se::syncedTrainMs((int) (fValues[kParamDivision] + 0.5f), pos.bbt.valid ? pos.bbt.beatsPerMinute : 120.0);
        } else {
            p.trainMs = fValues[kParamTimeMs];
        }
        p.mix = fValues[kParamMix] * 0.01f;
        p.feedback = fValues[kParamFeedback] * 0.01f;
        p.scramble = fValues[kParamScramble] * 0.01f;
        p.width = fValues[kParamWidth] * 0.01f;
        p.commutator = fValues[kParamView] > 0.5f;
        p.split = fValues[kParamSplit] * 0.01f;
        for (int s = 0; s < se::kBands; ++s) {
            p.siteSplit[s] = fValues[kParamSiteSplit0 + s] * 0.01f;
            p.siteGainDb[s] = fValues[kParamSiteGain0 + s];
        }
        fCore.setParams(p);
        fCore.process(inputs[0], inputs[1], outputs[0], outputs[1], (int) frames);
    }

private:
    const se::TapMap& selectedMap() const
    {
        const int idx = (int) (fValues[kParamMap] + 0.5f);
        if (idx == se::kCustomMapIndex && fHasCustom) return fCustom;
        if (idx >= 0 && idx < (int) fPresets.size()) return fPresets[idx];
        return fPresets[se::kDefaultPreset];
    }

    void applyMaps()
    {
        if (fPresets.empty()) return;
        fCore.setMaps(fPresets[se::kControlPreset], selectedMap());
    }

    float fValues[kParamCount];
    std::vector<se::TapMap> fPresets;
    se::TapMap fCustom;
    bool fHasCustom = false;
    String fCustomPath, fEggView;
    se::Core fCore;

    DISTRHO_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(ScrambledEchoPlugin)
};

Plugin* createPlugin()
{
    return new ScrambledEchoPlugin();
}

const se::Telemetry* scrambledEchoTelemetry(void* pluginInstance)
{
    return pluginInstance != nullptr ? &static_cast<ScrambledEchoPlugin*>(static_cast<Plugin*>(pluginInstance))->telemetry() : nullptr;
}

END_NAMESPACE_DISTRHO
