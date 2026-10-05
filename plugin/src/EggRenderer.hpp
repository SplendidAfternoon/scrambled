// Real-time 3D egg for the Scrambled Echo editor (raw OpenGL 2.1 / GLSL 1.20, drawn under the NanoVG overlay).
//
// The egg is the tap map: a Huegelschaeffer egg (same profile as three/egg_mesh.py) cut into 12 latitude bands,
// one per qubit site (site 0 at the pointed top, kick site 6 just below the equator), each band split into
// shell shards. Per band the UI feeds how far the band is cracked open (1 - |F(site, t)|), how far it was
// dragged out, its vertical drag, and how brightly its taps are firing.
#pragma once

#include "ScrambledEchoCore.hpp"

#include <string>
#include <vector>

namespace se {

struct BandVisual {
    float open = 0.f;      // 0 whole .. 1 cracked (1 - |F| at the time cursor)
    float split = 0.f;     // 0 on the shell .. 1 dragged fully out
    float lift = 0.f;      // vertical drag, -1 .. 1 (from the site gain)
    float flash = 0.f;     // 0 .. 1 tap activity
    float polarity = 1.f;  // -1 inverted taps dominate .. +1 in-phase
};

struct EggCamera {
    float yaw = 0.55f, pitch = 0.18f, zoom = 1.f;
    int widthPx = 900, heightPx = 640;      // framebuffer size
    float centerX = 0.5f, centerY = 0.4f;   // where the egg centre lands, as a fraction of the framebuffer (y down)
    float scale = 1.f;                      // framebuffer pixels per layout pixel
};

struct EggFrame {
    EggCamera cam;
    BandVisual band[kBands];
    float time = 0.f;   // seconds, for gentle idle motion
    float heat = 0.f;   // overall activity, warms the yolk
};

class EggRenderer {
public:
    EggRenderer();
    ~EggRenderer();

    // Must be called with the GL context current. Returns false (with error()) if OpenGL 2 shaders are missing.
    bool init();
    void draw(const EggFrame& frame);
    bool ready() const { return fReady; }
    const std::string& error() const { return fError; }

    // CPU-side geometry shared with the UI for the grab nodes.
    // Site node anchor in world space: on the band's mid latitude, on the silhouette to the camera's right,
    // moved outward by `split` and up/down by `lift` exactly like the band's shards.
    void nodeWorld(const EggCamera& cam, int band, float split, float lift, float out[3]) const;
    // World -> framebuffer pixels (y down). Returns false behind the camera.
    bool project(const EggCamera& cam, const float world[3], float& px, float& py) const;
    // Screen-space length (pixels) of one world unit at the egg centre: maps mouse drags to split / lift.
    float pixelsPerUnit(const EggCamera& cam) const;

    static constexpr float kSplitDistance = 0.42f;  // world units a fully split band moves out
    static constexpr float kLiftDistance = 0.16f;   // world units for lift = +-1

private:
    struct Impl;
    Impl* d;
    bool fReady = false;
    std::string fError;
};

}  // namespace se
