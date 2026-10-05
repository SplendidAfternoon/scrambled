// Tap-map loader: accepts a bundled preset, a raw otoc-echo-v1 job result / cached moth.run record,
// or any JSON with a "taps" array of {site, depth|step, F_re, F_im} or {site, depth|step, level, polarity}.
#pragma once

#include "ScrambledEchoCore.hpp"

#include <cmath>
#include <cstdlib>
#include <string>
#include <utility>
#include <vector>

namespace se {

// Every cell becomes a tap read on every sample; the largest Atlas run (16 qubits, depth 32) is 512 cells.
constexpr int kMaxMapCells = 1024;

struct JVal {
    enum Type { Null, Bool, Num, Str, Arr, Obj } type = Null;
    double num = 0.0;
    std::string str;
    std::vector<JVal> arr;
    std::vector<std::pair<std::string, JVal>> obj;

    const JVal* get(const char* key) const
    {
        if (type != Obj) return nullptr;
        for (const auto& kv : obj)
            if (kv.first == key) return &kv.second;
        return nullptr;
    }
};

class JsonParser {
public:
    explicit JsonParser(const std::string& text) : s(text) {}

    bool parse(JVal& out, std::string& err)
    {
        if (!value(out, 0)) { err = "invalid JSON near byte " + std::to_string(i); return false; }
        ws();
        if (i != s.size()) { err = "trailing characters after JSON"; return false; }
        return true;
    }

private:
    const std::string& s;
    size_t i = 0;

    void ws() { while (i < s.size() && (s[i] == ' ' || s[i] == '\n' || s[i] == '\r' || s[i] == '\t')) ++i; }
    bool lit(const char* w)
    {
        size_t n = std::char_traits<char>::length(w);
        if (s.compare(i, n, w) != 0) return false;
        i += n;
        return true;
    }

    bool string(std::string& out)
    {
        if (i >= s.size() || s[i] != '"') return false;
        ++i;
        while (i < s.size() && s[i] != '"') {
            char c = s[i++];
            if (c == '\\') {
                if (i >= s.size()) return false;
                char e = s[i++];
                switch (e) {
                    case 'n': out += '\n'; break;
                    case 't': out += '\t'; break;
                    case 'r': out += '\r'; break;
                    case 'b': out += '\b'; break;
                    case 'f': out += '\f'; break;
                    case 'u': {
                        if (i + 4 > s.size()) return false;
                        unsigned cp = (unsigned) std::strtoul(s.substr(i, 4).c_str(), nullptr, 16);
                        i += 4;
                        if (cp < 0x80) out += (char) cp;
                        else if (cp < 0x800) { out += (char) (0xC0 | (cp >> 6)); out += (char) (0x80 | (cp & 0x3F)); }
                        else { out += (char) (0xE0 | (cp >> 12)); out += (char) (0x80 | ((cp >> 6) & 0x3F)); out += (char) (0x80 | (cp & 0x3F)); }
                        break;
                    }
                    default: out += e;
                }
            } else {
                out += c;
            }
        }
        if (i >= s.size()) return false;
        ++i;
        return true;
    }

    bool value(JVal& v, int depth)
    {
        if (depth > 64) return false;
        ws();
        if (i >= s.size()) return false;
        char c = s[i];
        if (c == '{') {
            v.type = JVal::Obj; ++i; ws();
            if (i < s.size() && s[i] == '}') { ++i; return true; }
            for (;;) {
                ws();
                std::pair<std::string, JVal> kv;
                if (!string(kv.first)) return false;
                ws();
                if (i >= s.size() || s[i] != ':') return false;
                ++i;
                if (!value(kv.second, depth + 1)) return false;
                v.obj.push_back(std::move(kv));
                ws();
                if (i < s.size() && s[i] == ',') { ++i; continue; }
                if (i < s.size() && s[i] == '}') { ++i; return true; }
                return false;
            }
        }
        if (c == '[') {
            v.type = JVal::Arr; ++i; ws();
            if (i < s.size() && s[i] == ']') { ++i; return true; }
            for (;;) {
                JVal e;
                if (!value(e, depth + 1)) return false;
                v.arr.push_back(std::move(e));
                ws();
                if (i < s.size() && s[i] == ',') { ++i; continue; }
                if (i < s.size() && s[i] == ']') { ++i; return true; }
                return false;
            }
        }
        if (c == '"') { v.type = JVal::Str; return string(v.str); }
        if (lit("true")) { v.type = JVal::Bool; v.num = 1; return true; }
        if (lit("false")) { v.type = JVal::Bool; v.num = 0; return true; }
        if (lit("null")) { v.type = JVal::Null; return true; }
        const char* start = s.c_str() + i;
        char* end = nullptr;
        double d = std::strtod(start, &end);
        if (end == start) return false;
        v.type = JVal::Num; v.num = d;
        i += (size_t) (end - start);
        return true;
    }
};

namespace detail {

inline bool isTapList(const JVal& v)
{
    return v.type == JVal::Arr && !v.arr.empty() && v.arr[0].get("site") && (v.arr[0].get("depth") || v.arr[0].get("step"));
}

inline const JVal* findTaps(const JVal& v, int depth = 0)
{
    if (depth > 16) return nullptr;
    if (const JVal* t = v.get("taps"))
        if (isTapList(*t)) return t;
    for (const auto& kv : v.obj)
        if (const JVal* r = findTaps(kv.second, depth + 1)) return r;
    return nullptr;
}

// First numeric `key` found depth-first, skipping tap objects (they also carry "depth").
inline const JVal* findNum(const JVal& v, const char* key, int depth = 0)
{
    if (depth > 16 || v.type != JVal::Obj || v.get("site")) return nullptr;
    if (const JVal* n = v.get(key))
        if (n->type == JVal::Num) return n;
    for (const auto& kv : v.obj)
        if (const JVal* r = findNum(kv.second, key, depth + 1)) return r;
    return nullptr;
}

inline double num(const JVal* v, double fallback) { return v && v->type == JVal::Num ? v->num : fallback; }
inline int count(const JVal* v, int fallback)
{
    const double d = num(v, fallback);
    return std::isfinite(d) ? (int) std::clamp(d, -1.0, 1e6) : fallback;
}
inline std::string str(const JVal* v) { return v && v->type == JVal::Str ? v->str : std::string(); }

}  // namespace detail

inline bool parseMapJson(const std::string& text, TapMap& out, std::string& err)
{
    JVal root;
    if (!JsonParser(text).parse(root, err)) return false;
    if (root.type != JVal::Obj) { err = "top level must be a JSON object"; return false; }
    const JVal* taps = detail::findTaps(root);
    if (!taps) { err = "no \"taps\" array with {site, depth, F_re/F_im or level/polarity} found"; return false; }

    TapMap m;
    int maxSite = -1, maxStep = 0;
    for (const JVal& t : taps->arr) {
        if (t.type != JVal::Obj) continue;
        Tap tap;
        tap.site = detail::count(t.get("site"), -1);
        tap.step = detail::count(t.get("depth") ? t.get("depth") : t.get("step"), 0);
        if (t.get("F_re")) {
            tap.re = (float) detail::num(t.get("F_re"), 0.0);
            tap.im = (float) detail::num(t.get("F_im"), 0.0);
        } else {
            const double level = std::fabs(detail::num(t.get("level"), 0.0));
            tap.re = (float) (detail::num(t.get("polarity"), 1.0) < 0 ? -level : level);
        }
        if (tap.site < 0 || tap.step < 1 || !std::isfinite(tap.re) || !std::isfinite(tap.im)) continue;
        maxSite = std::max(maxSite, tap.site);
        maxStep = std::max(maxStep, tap.step);
        m.taps.push_back(tap);
    }
    if (m.taps.empty()) { err = "tap list has no valid taps"; return false; }

    m.nSites = std::max(maxSite + 1, detail::count(detail::findNum(root, "n_sites"), 0));
    m.depth = std::max(maxStep, detail::count(detail::findNum(root, "depth"), 0));
    if ((int64_t) m.nSites * m.depth > kMaxMapCells) {
        err = "map too large to play: " + std::to_string(m.nSites) + " sites x " + std::to_string(m.depth) +
              " steps (limit " + std::to_string(kMaxMapCells) + " cells)";
        return false;
    }
    m.kickSite = (int) detail::num(detail::findNum(root, "kick_site"), m.nSites / 2);
    m.name = detail::str(root.get("name"));
    m.description = detail::str(root.get("description"));
    m.jobId = detail::str(root.get("job_id"));
    if (m.jobId.empty())
        if (const JVal* src = root.get("source")) m.jobId = detail::str(src->get("job_id"));
    out = std::move(m);
    return true;
}

}  // namespace se
