// Behaviour tests for the Scrambled Echo DSP core and map loader.
// Expected values are worked by hand from the tap-mapping spec in README.md, not recomputed from the code.
#include "ScrambledEchoCore.hpp"
#include "MapBank.hpp"

#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

static int g_failed = 0, g_checks = 0;
#define CHECK(cond, ...) do { ++g_checks; if (!(cond)) { ++g_failed; std::printf("FAIL %s:%d: ", __FILE__, __LINE__); std::printf(__VA_ARGS__); std::printf("\n"); } } while (0)
static bool near(float a, float b, float tol = 1e-4f) { return std::fabs(a - b) <= tol; }

static se::TapMap twoTapMap()
{
    se::TapMap m;
    m.name = "two"; m.nSites = 3; m.depth = 2; m.kickSite = 1;
    m.taps = { {0, 1, 0.5f, 0.f}, {2, 2, -1.f, 0.f} };
    return m;
}

struct Rendered { std::vector<float> l, r; };

static Rendered impulse(se::Core& core, int n, int block = 64)
{
    std::vector<float> inL(n, 0.f), inR(n, 0.f);
    inL[0] = inR[0] = 1.f;
    Rendered out{std::vector<float>(n), std::vector<float>(n)};
    for (int i = 0; i < n; i += block) {
        int len = std::min(block, n - i);
        core.process(inL.data() + i, inR.data() + i, out.l.data() + i, out.r.data() + i, len);
    }
    return out;
}

static void test_impulse_lands_on_measured_taps()
{
    se::Core core;
    core.prepare(1000.0);
    core.setMaps(twoTapMap(), twoTapMap());
    core.setParams({1000.f, 1.f, 0.f, 1.f, 1.f});
    auto o = impulse(core, 1500);
    // step = 1000 ms / depth 2 = 500 samples; makeup = 1/sqrt(0.5^2 + 1^2) = 0.894427
    CHECK(near(o.l[500], 0.447214f), "site0 step1 left = %f", o.l[500]);
    CHECK(near(o.r[500], 0.f), "site0 is hard left, right = %f", o.r[500]);
    CHECK(near(o.r[1000], -0.894427f), "site2 step2 inverted right = %f", o.r[1000]);
    CHECK(near(o.l[1000], 0.f), "site2 is hard right, left = %f", o.l[1000]);
    float stray = 0.f;
    for (int i = 0; i < 1500; ++i)
        if (i != 500 && i != 1000) stray = std::max(stray, std::max(std::fabs(o.l[i]), std::fabs(o.r[i])));
    CHECK(stray < 1e-5f, "no energy outside taps, max stray %f", stray);
}

static void test_scramble_interpolates_F_on_shared_grid()
{
    se::TapMap a, b;
    a.nSites = b.nSites = 3; a.depth = b.depth = 2;
    a.taps = { {1, 1, 1.f, 0.f} };
    b.taps = { {1, 1, -1.f, 0.f} };
    {
        se::Core core; core.prepare(1000.0); core.setMaps(a, b);
        core.setParams({1000.f, 1.f, 0.f, 0.5f, 1.f});
        auto o = impulse(core, 1200);
        float peak = 0.f;
        for (int i = 0; i < 1200; ++i) peak = std::max(peak, std::fabs(o.l[i]) + std::fabs(o.r[i]));
        CHECK(peak < 1e-6f && std::isfinite(peak), "F=+1 and F=-1 cancel at scramble 0.5, peak %f", peak);
    }
    {
        se::Core core; core.prepare(1000.0); core.setMaps(a, b);
        core.setParams({1000.f, 1.f, 0.f, 0.25f, 1.f});
        auto o = impulse(core, 1200);
        // F = 0.75 - 0.25 = +0.5, single tap normalised to 1, centre pan -> cos(pi/4)
        CHECK(near(o.l[500], 0.707107f) && near(o.r[500], 0.707107f), "centre tap %f %f", o.l[500], o.r[500]);
    }
}

static void test_width_zero_is_mono()
{
    se::Core core; core.prepare(1000.0);
    core.setMaps(twoTapMap(), twoTapMap());
    core.setParams({1000.f, 1.f, 0.f, 1.f, 0.f});
    auto o = impulse(core, 1200);
    CHECK(near(o.l[1000], o.r[1000]) && near(o.l[500], o.r[500]), "width 0 collapses pan");
}

static void test_dry_passes_at_mix_zero()
{
    se::Core core; core.prepare(1000.0);
    core.setMaps(twoTapMap(), twoTapMap());
    core.setParams({1000.f, 0.f, 0.f, 1.f, 1.f});
    auto o = impulse(core, 1200);
    CHECK(near(o.l[0], 1.f) && near(o.r[0], 1.f) && near(o.l[500], 0.f), "mix 0 is dry only");
}

static void test_feedback_repeats_the_train_and_decays()
{
    se::TapMap m; m.nSites = 1; m.depth = 1; m.taps = { {0, 1, 1.f, 0.f} };
    se::Core core; core.prepare(48000.0); core.setMaps(m, m);
    core.setParams({100.f, 1.f, 0.5f, 1.f, 1.f});
    auto o = impulse(core, 48000 * 1);
    auto peakIn = [&](int a, int b) { float p = 0; for (int i = a; i < b; ++i) p = std::max(p, std::fabs(o.l[i])); return p; };
    float e1 = peakIn(4700, 4900), e2 = peakIn(9500, 9900), e3 = peakIn(14300, 14700);
    CHECK(e1 > 0.5f, "first echo present %f", e1);
    CHECK(e2 > 0.3f * e1 && e2 < 0.55f * e1, "second echo ~ feedback 0.5 x first: %f vs %f", e2, e1);
    CHECK(e3 < e2, "third echo decays %f < %f", e3, e2);
}

static void test_only_the_final_step_regenerates()
{
    se::TapMap m; m.nSites = 1; m.depth = 2; m.taps = { {0, 1, 1.f, 0.f} };
    se::Core core; core.prepare(48000.0); core.setMaps(m, m);
    core.setParams({200.f, 1.f, 0.9f, 1.f, 1.f});
    auto o = impulse(core, 48000);
    float first = 0, later = 0;
    for (int i = 4700; i < 4900; ++i) first = std::max(first, std::fabs(o.l[i]));
    for (int i = 5000; i < 48000; ++i) later = std::max(later, std::fabs(o.l[i]));
    CHECK(first > 0.5f && later < 1e-4f, "a map with an empty t=depth column has no regeneration: %f then %f", first, later);
}

static void test_dense_uniform_map_still_regenerates()
{
    // Control (Clifford) shape: every tap |F| = 1, one site inverted. Final column sums to 10 of 12.
    se::TapMap m; m.nSites = 12; m.depth = 32;
    for (int s = 0; s < 12; ++s)
        for (int t = 1; t <= 32; ++t) m.taps.push_back({s, t, s == 6 ? -1.f : 1.f, 0.f});
    se::Core core; core.prepare(48000.0); core.setMaps(m, m);
    core.setParams({100.f, 1.f, 0.8f, 1.f, 0.f});
    auto o = impulse(core, 48000);
    auto peakIn = [&](int a, int b) { float p = 0; for (int i = a; i < b; ++i) p = std::max(p, std::fabs(o.l[i])); return p; };
    float train1 = peakIn(100, 4900), train2 = peakIn(4900 + 100, 9700);
    CHECK(train2 > 0.25f * train1, "second pass of the train is audible: %f vs %f", train2, train1);
}

static void test_max_feedback_on_dense_map_stays_bounded()
{
    se::TapMap m; m.nSites = 12; m.depth = 32;
    for (int s = 0; s < 12; ++s)
        for (int t = 1; t <= 32; ++t) m.taps.push_back({s, t, ((s * 7 + t * 3) % 5 - 2) * 0.4f, 0.f});
    se::Core core; core.prepare(48000.0); core.setMaps(m, m);
    core.setParams({250.f, 1.f, 0.98f, 1.f, 1.f});
    const int n = 48000 * 20;
    std::vector<float> in(n, 0.f), l(n), r(n);
    for (int i = 0; i < 4800; ++i) in[i] = std::sin(i * 0.05f);
    for (int i = 0; i < n; i += 512) core.process(in.data() + i, in.data() + i, l.data() + i, r.data() + i, std::min(512, n - i));
    float peak = 0, lastRms = 0;
    for (int i = 0; i < n; ++i) peak = std::max(peak, std::fabs(l[i]) + std::fabs(r[i]));
    for (int i = n - 48000; i < n; ++i) lastRms += l[i] * l[i];
    lastRms = std::sqrt(lastRms / 48000);
    CHECK(std::isfinite(peak) && peak < 8.f, "bounded, peak %f", peak);
    CHECK(lastRms < 1e-3f, "tail decays by 20 s, rms %g", lastRms);
}

static void test_time_sweep_is_finite_and_continuous()
{
    auto m = twoTapMap();
    se::Core core; core.prepare(48000.0); core.setMaps(m, m);
    const int n = 48000 * 2;
    std::vector<float> in(n), l(n), r(n);
    for (int i = 0; i < n; ++i) in[i] = std::sin(i * 2 * 3.14159265f * 220 / 48000);
    for (int i = 0; i < n; i += 256) {
        core.setParams({200.f + 1800.f * i / n, 0.5f, 0.3f, 1.f, 1.f});
        core.process(in.data() + i, in.data() + i, l.data() + i, r.data() + i, std::min(256, n - i));
    }
    float maxJump = 0;
    for (int i = 1; i < n; ++i) maxJump = std::max(maxJump, std::fabs(l[i] - l[i - 1]));
    CHECK(std::isfinite(maxJump) && maxJump < 0.25f, "no clicks while sweeping time, max step %f", maxJump);
}

static void test_map_swap_ramps_without_click()
{
    se::TapMap a; a.nSites = 1; a.depth = 1; a.taps = { {0, 1, 1.f, 0.f} };
    se::TapMap b = a; b.taps[0].re = -1.f;
    se::Core core; core.prepare(48000.0); core.setMaps(a, a);
    core.setParams({10.f, 1.f, 0.f, 1.f, 1.f});
    const int n = 9600;
    std::vector<float> in(n, 0.5f), l(n), r(n);
    core.process(in.data(), in.data(), l.data(), r.data(), 4800);
    core.setMaps(b, b);
    core.process(in.data() + 4800, in.data() + 4800, l.data() + 4800, r.data() + 4800, 4800);
    float maxJump = 0;
    for (int i = 4801; i < n; ++i) maxJump = std::max(maxJump, std::fabs(l[i] - l[i - 1]));
    CHECK(maxJump < 0.05f, "polarity flip of whole map is ramped, max step %f", maxJump);
    CHECK(l[n - 1] < -0.3f, "new map took effect %f", l[n - 1]);
}

static void test_scramble_move_ramps_without_click()
{
    se::TapMap a; a.nSites = 1; a.depth = 1; a.taps = { {0, 1, 1.f, 0.f} };
    se::TapMap b = a; b.taps[0].re = -1.f;
    se::Core core; core.prepare(48000.0); core.setMaps(a, b);
    core.setParams({10.f, 1.f, 0.f, 0.f, 1.f});
    const int n = 2048;
    std::vector<float> in(n, 0.5f), l(n), r(n);
    core.process(in.data(), in.data(), l.data(), r.data(), 1024);
    core.setParams({10.f, 1.f, 0.f, 1.f, 1.f});
    core.process(in.data() + 1024, in.data() + 1024, l.data() + 1024, r.data() + 1024, 1024);
    float maxJump = 0;
    for (int i = 1001; i < n; ++i) maxJump = std::max(maxJump, std::fabs(l[i] - l[i - 1]));
    CHECK(maxJump < 0.01f, "scramble 0 -> 1 is ramped across the block, max step %f", maxJump);
    CHECK(near(l[n - 1], -0.353553f, 1e-3f), "lands on the selected map %f", l[n - 1]);
}

static void test_commutator_view_plays_where_the_operator_spread()
{
    // C = (1 - Re F) / 2: F = +1 -> silent, F = -1 -> full, cell missing from the list (F = 0) -> 0.5.
    se::TapMap m; m.nSites = 3; m.depth = 1;
    m.taps = { {0, 1, 1.f, 0.f}, {2, 1, -1.f, 0.f} };
    se::Params prm{1000.f, 1.f, 0.f, 1.f, 1.f};
    prm.commutator = true;
    se::Core core; core.prepare(1000.0); core.setMaps(m, m); core.setParams(prm);
    auto o = impulse(core, 1200);
    // taps: site1 (centre) C = 0.5, site2 (right) C = 1.0; makeup = 1/sqrt(1.25)
    CHECK(near(o.l[1000], 0.5f * 0.894427f * 0.707107f), "centre C=0.5 left %f", o.l[1000]);
    CHECK(near(o.r[1000], 0.5f * 0.894427f * 0.707107f + 0.894427f), "centre + right C=1 %f", o.r[1000]);
}

static void test_parse_otoc_record()
{
    const char* json = R"({"job_id":"abc","response":{"result":{"output":{"extras":{
        "kick_site":6,"params":{"n_sites":12,"depth":32},
        "taps":[{"site":0,"depth":6,"F_re":0.96,"F_im":0,"level":0.96,"polarity":1},
                {"site":11,"depth":32,"F_re":-0.25,"F_im":0.1,"level":0.27,"polarity":-1}]}}}}})";
    se::TapMap m; std::string err;
    CHECK(se::parseMapJson(json, m, err), "parses otoc record: %s", err.c_str());
    CHECK(m.nSites == 12 && m.depth == 32 && m.kickSite == 6, "grid %d x %d kick %d", m.nSites, m.depth, m.kickSite);
    CHECK(m.taps.size() == 2 && m.taps[1].site == 11 && m.taps[1].step == 32 && near(m.taps[1].re, -0.25f) && near(m.taps[1].im, 0.1f), "taps");
    CHECK(m.jobId == "abc", "job id '%s'", m.jobId.c_str());
}

static void test_parse_preset_and_infer_grid()
{
    const char* json = R"({"name":"Hand map","taps":[{"site":3,"depth":5,"level":0.5,"polarity":-1},{"site":1,"depth":2,"F_re":1e-1,"F_im":0}]})";
    se::TapMap m; std::string err;
    CHECK(se::parseMapJson(json, m, err), "parses: %s", err.c_str());
    CHECK(m.name == "Hand map" && m.nSites == 4 && m.depth == 5, "inferred grid %d x %d", m.nSites, m.depth);
    CHECK(near(m.taps[0].re, -0.5f), "level+polarity -> F_re %f", m.taps[0].re);
}

static void test_parse_rejects_garbage()
{
    se::TapMap m; std::string err;
    CHECK(!se::parseMapJson("{\"hello\": [1,2", m, err), "truncated JSON rejected");
    CHECK(!se::parseMapJson("{\"hello\": 1}", m, err) && !err.empty(), "JSON without taps rejected: %s", err.c_str());
}

// Real files passed on the command line: "<path>=<n_sites>x<depth>" must load with that grid.
static void test_real_files(int argc, char** argv)
{
    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        const size_t eq = arg.rfind('=');
        const std::string path = arg.substr(0, eq);
        int ns = 0, d = 0;
        std::sscanf(arg.c_str() + eq + 1, "%dx%d", &ns, &d);
        se::TapMap m; std::string err;
        const bool ok = se::loadMapFile(path, m, err);
        CHECK(ok && m.nSites == ns && m.depth == d && !m.taps.empty(),
              "%s loads as %dx%d (got %dx%d, %zu taps, job '%s') %s", path.c_str(), ns, d, m.nSites, m.depth,
              m.taps.size(), m.jobId.c_str(), err.c_str());
    }
}

int main(int argc, char** argv)
{
    test_impulse_lands_on_measured_taps();
    test_scramble_interpolates_F_on_shared_grid();
    test_width_zero_is_mono();
    test_dry_passes_at_mix_zero();
    test_feedback_repeats_the_train_and_decays();
    test_only_the_final_step_regenerates();
    test_dense_uniform_map_still_regenerates();
    test_max_feedback_on_dense_map_stays_bounded();
    test_time_sweep_is_finite_and_continuous();
    test_map_swap_ramps_without_click();
    test_scramble_move_ramps_without_click();
    test_commutator_view_plays_where_the_operator_spread();
    test_parse_otoc_record();
    test_parse_preset_and_infer_grid();
    test_parse_rejects_garbage();
    test_real_files(argc, argv);
    std::printf("%d/%d checks passed\n", g_checks - g_failed, g_checks);
    return g_failed ? 1 : 0;
}
