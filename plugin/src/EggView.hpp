// Camera / selection state of the 3D egg editor, saved with the host project as the "egg_view" state string.
// The audio edits themselves (Split macro, per-site split and gain) are plugin parameters, so hosts save and
// automate them directly; this string only restores how the egg was being looked at.
#pragma once

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>

#include "ScrambledEchoCore.hpp"

namespace se {

struct EggView {
    float yaw = 0.55f;    // radians around the egg's long axis
    float pitch = 0.18f;  // radians, camera elevation
    float zoom = 1.f;     // 1 = default framing
    int selected = -1;    // last grabbed site, -1 = none
};

inline EggView clampView(EggView v)
{
    if (!std::isfinite(v.yaw)) v.yaw = 0.55f;
    v.yaw = std::remainder(v.yaw, 6.28318531f);
    v.pitch = std::isfinite(v.pitch) ? std::clamp(v.pitch, -1.3f, 1.3f) : 0.18f;
    v.zoom = std::isfinite(v.zoom) ? std::clamp(v.zoom, 0.5f, 2.5f) : 1.f;
    v.selected = std::clamp(v.selected, -1, kBands - 1);
    return v;
}

inline std::string encodeEggView(const EggView& v)
{
    char buf[128];
    std::snprintf(buf, sizeof buf, "yaw=%.5f;pitch=%.5f;zoom=%.5f;sel=%d", v.yaw, v.pitch, v.zoom, v.selected);
    return buf;
}

// Returns false (leaving `out` untouched) unless at least one known key parses.
inline bool decodeEggView(const std::string& s, EggView& out)
{
    EggView v = out;
    int found = 0;
    size_t pos = 0;
    while (pos < s.size()) {
        size_t end = s.find(';', pos);
        if (end == std::string::npos) end = s.size();
        const std::string item = s.substr(pos, end - pos);
        const size_t eq = item.find('=');
        if (eq != std::string::npos) {
            const std::string key = item.substr(0, eq), val = item.substr(eq + 1);
            char* stop = nullptr;
            const double d = std::strtod(val.c_str(), &stop);
            if (stop != val.c_str()) {
                if (key == "yaw") { v.yaw = (float) d; ++found; }
                else if (key == "pitch") { v.pitch = (float) d; ++found; }
                else if (key == "zoom") { v.zoom = (float) d; ++found; }
                else if (key == "sel") { v.selected = (int) std::lround(d); ++found; }
            }
        }
        pos = end + 1;
    }
    if (!found) return false;
    out = clampView(v);
    return true;
}

}  // namespace se
