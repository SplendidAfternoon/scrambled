// ---------------------------------------------------------------------------
// EntanglementTexture — GLSL fragment shader (OpenGL 3.3+ / GLSL 330)
//
// Bind R_lut.exr to texture unit 0 and T_lut.exr to texture unit 1.
//   glUniform1i(glGetUniformLocation(prog, "uRTexture"), 0);
//   glUniform1i(glGetUniformLocation(prog, "uTTexture"), 1);
//
// Sampler settings:
//   TEXTURE_WRAP_S = GL_REPEAT          (phase axis, periodic)
//   TEXTURE_WRAP_T = GL_CLAMP_TO_EDGE   (angle axis)
//   TEXTURE_MIN_FILTER = GL_LINEAR
//   TEXTURE_MAG_FILTER = GL_LINEAR
//
// LUT layout (load with GL_R32F; do NOT flip vertically when uploading):
//   s-axis: phase coordinate, periodic — maps to [0, 1)
//   t-axis: incident angle — t=0 at texture bottom = theta=0, t=1 = theta=π/2
//   (row 0 of the EXR goes to t=0 when glTexImage2D receives the data row-major)
//
// Values above 1.0 are preserved; output is HDR.
// ---------------------------------------------------------------------------
#version 330 core

uniform sampler2D uRTexture;   // reflectance LUT  — bind to unit 0
uniform sampler2D uTTexture;   // transmittance LUT — bind to unit 1
uniform float     uThickness;  // interlayer spacing in nm, default 500

in  vec3 vNormal;    // interpolated surface normal (world/view space, need not be unit)
in  vec3 vViewDir;   // direction from surface to camera (same space as vNormal)

layout(location = 0) out vec4 outReflectance;
layout(location = 1) out vec4 outTransmittance;

const float ET_PI_2   = 1.5707963267948966;
const float ET_TWO_PI = 6.283185307179586;

void main()
{
    float cosTheta = abs(dot(normalize(vNormal), normalize(vViewDir)));
    float theta    = acos(clamp(cosTheta, 0.0, 1.0));
    float D        = -2.0 * ET_TWO_PI * uThickness * cosTheta;

    const vec3 wavelength = vec3(650.0, 530.0, 470.0); // R, G, B in nm

    // GLSL mod() returns a non-negative value for a positive divisor,
    // so no correction is needed even when D < 0.
    float s0 = mod(D / wavelength.r, ET_TWO_PI) / ET_TWO_PI;
    float s1 = mod(D / wavelength.g, ET_TWO_PI) / ET_TWO_PI;
    float s2 = mod(D / wavelength.b, ET_TWO_PI) / ET_TWO_PI;

    // OpenGL convention: t=0 is the bottom of the texture.
    // The LUT is uploaded without vertical flip so row 0 (theta=0) lands at t=0.
    float t = theta / ET_PI_2;

    outReflectance = vec4(
        texture(uRTexture, vec2(s0, t)).r,
        texture(uRTexture, vec2(s1, t)).r,
        texture(uRTexture, vec2(s2, t)).r,
        1.0
    );
    outTransmittance = vec4(
        texture(uTTexture, vec2(s0, t)).r,
        texture(uTTexture, vec2(s1, t)).r,
        texture(uTTexture, vec2(s2, t)).r,
        1.0
    );
}
