// ---------------------------------------------------------------------------
// EntanglementTexture — HLSL pixel shader (Direct3D 11 / SM 5.0)
//
// Place R_lut.exr and T_lut.exr in your texture slots:
//   t0 = R_lut.exr,  t1 = T_lut.exr
// Bind a SamplerState at s0 with AddressU=Wrap, AddressV=Clamp,
// Filter=MIN_MAG_MIP_LINEAR.
// ---------------------------------------------------------------------------

Texture2D<float> R_texture : register(t0);
Texture2D<float> T_texture : register(t1);
SamplerState     lut_sampler : register(s0);

cbuffer Material : register(b0)
{
    float thickness;  // interlayer spacing in nm, default 500
    float3 _pad;
};

static const float ET_PI_2   = 1.5707963267948966f;
static const float ET_TWO_PI = 6.283185307179586f;

struct FragInput
{
    float4 position : SV_Position;
    float3 normal   : NORMAL;
    float3 view_dir : TEXCOORD0;
};

struct FragOutput
{
    float4 reflectance   : SV_Target0;
    float4 transmittance : SV_Target1;
};

// fmod in HLSL follows C semantics (result sign matches dividend), so a
// negative D requires a correction to land in [0, 1).
float phase_s(float D, float wl)
{
    float s = fmod(D / wl, ET_TWO_PI) / ET_TWO_PI;
    return s < 0.0f ? s + 1.0f : s;
}

FragOutput main(FragInput input)
{
    static const float3 wavelength = float3(650.0f, 530.0f, 470.0f);

    float cos_theta = abs(dot(normalize(input.normal), normalize(-input.view_dir)));
    float theta     = acos(clamp(cos_theta, 0.0f, 1.0f));
    float D         = -2.0f * ET_TWO_PI * thickness * cos_theta;

    float s0 = phase_s(D, wavelength.r);
    float s1 = phase_s(D, wavelength.g);
    float s2 = phase_s(D, wavelength.b);

    float t = theta / ET_PI_2;

    FragOutput output;
    output.reflectance = float4(
        R_texture.Sample(lut_sampler, float2(s0, t)),
        R_texture.Sample(lut_sampler, float2(s1, t)),
        R_texture.Sample(lut_sampler, float2(s2, t)),
        1.0f
    );
    output.transmittance = float4(
        T_texture.Sample(lut_sampler, float2(s0, t)),
        T_texture.Sample(lut_sampler, float2(s1, t)),
        T_texture.Sample(lut_sampler, float2(s2, t)),
        1.0f
    );
    return output;
}
