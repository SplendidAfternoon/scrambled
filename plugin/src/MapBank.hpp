// Bundled tap maps (measured on Moth Atlas, embedded at build time) plus file loading for custom maps.
#pragma once

#include "MapJson.hpp"
#include "Presets.hpp"

#include <cstdio>
#include <string>
#include <vector>

namespace se {

static constexpr int kControlPreset = 0;    // Control (Clifford): the Scramble = 0 end
static constexpr int kDefaultPreset = 3;    // Scrambling
static constexpr int kCustomMapIndex = kNumPresets;

inline std::vector<TapMap> loadEmbeddedPresets()
{
    std::vector<TapMap> maps;
    for (const EmbeddedPreset& p : kPresets) {
        TapMap m;
        std::string err;
        if (parseMapJson(p.json, m, err)) maps.push_back(std::move(m));
    }
    return maps;
}

inline bool readTextFile(const std::string& path, std::string& out)
{
    FILE* f = std::fopen(path.c_str(), "rb");
    if (!f) return false;
    char buf[65536];
    size_t n;
    out.clear();
    while ((n = std::fread(buf, 1, sizeof(buf), f)) > 0) {
        out.append(buf, n);
        if (out.size() > (64u << 20)) { std::fclose(f); return false; }
    }
    std::fclose(f);
    return true;
}

inline bool loadMapFile(const std::string& path, TapMap& out, std::string& err)
{
    std::string text;
    if (!readTextFile(path, text)) { err = "cannot read " + path; return false; }
    if (!parseMapJson(text, out, err)) return false;
    if (out.name.empty()) {
        size_t slash = path.find_last_of("/\\");
        out.name = path.substr(slash == std::string::npos ? 0 : slash + 1);
    }
    return true;
}

struct Division { const char* label; float beats; };
static const Division kDivisions[] = {
    {"1/4", 1.f}, {"1/2", 2.f}, {"1 bar", 4.f}, {"2 bars", 8.f}, {"4 bars", 16.f},
};
static constexpr int kNumDivisions = (int) (sizeof(kDivisions) / sizeof(kDivisions[0]));

inline float syncedTrainMs(int division, double bpm)
{
    if (division < 0) division = 0;
    if (division >= kNumDivisions) division = kNumDivisions - 1;
    if (!(bpm > 1.0)) bpm = 120.0;
    return (float) (kDivisions[division].beats * 60000.0 / bpm);
}

}  // namespace se
