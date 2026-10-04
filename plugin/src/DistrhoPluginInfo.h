#ifndef DISTRHO_PLUGIN_INFO_H_INCLUDED
#define DISTRHO_PLUGIN_INFO_H_INCLUDED

#define DISTRHO_PLUGIN_BRAND   "Moth Hack 2026"
#define DISTRHO_PLUGIN_NAME    "Scrambled Echo"
#define DISTRHO_PLUGIN_URI     "https://github.com/moth-hack/scrambled-echo"
#define DISTRHO_PLUGIN_CLAP_ID "moth.hack.scrambled-echo"

#define DISTRHO_PLUGIN_BRAND_ID  MthH
#define DISTRHO_PLUGIN_UNIQUE_ID ScEc

#define DISTRHO_PLUGIN_HAS_UI          1
#define DISTRHO_PLUGIN_IS_RT_SAFE      1
#define DISTRHO_PLUGIN_NUM_INPUTS      2
#define DISTRHO_PLUGIN_NUM_OUTPUTS     2
#define DISTRHO_PLUGIN_WANT_TIMEPOS    1
#define DISTRHO_PLUGIN_WANT_STATE      1
#define DISTRHO_PLUGIN_WANT_FULL_STATE 1
#define DISTRHO_UI_USE_NANOVG          1
#define DISTRHO_UI_FILE_BROWSER        1
#define DISTRHO_UI_USER_RESIZABLE      0
#define DISTRHO_UI_DEFAULT_WIDTH       760
#define DISTRHO_UI_DEFAULT_HEIGHT      470

#define DISTRHO_PLUGIN_VST3_CATEGORIES "Fx|Delay|Stereo"

enum ScrambledEchoParams {
    kParamMap = 0,
    kParamSync,
    kParamTimeMs,
    kParamDivision,
    kParamMix,
    kParamFeedback,
    kParamScramble,
    kParamWidth,
    kParamView,
    kParamCount
};

#define SE_STATE_CUSTOM_MAP "custom_map"

#endif
