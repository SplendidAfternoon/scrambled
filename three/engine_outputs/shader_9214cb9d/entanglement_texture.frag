/*
    EntanglementTexture — Marmoset Toolbag 4 custom shader

    Install:  copy into  <Toolbag 4>/data/shader/mat/custom/ , pick it as the
    material's Custom shader, and assign  R_lut.exr -> "R LUT" , T_lut.exr -> "T LUT".

    This overrides only two slots, mirroring the OSL BSDF
    (Reflectance * GGX + Transmittance * transparent — no diffuse term):
        R -> Reflectivity   (specular colour)
        T -> Transmissivity  (transmission colour)

    Material setup:
      Keep ON  : Reflection = GGX (low roughness for a sharp reflection);
                 Transparency = Refraction (required, or T won't show).
      Turn OFF : Albedo/diffuse (set albedo black), sheen, emissive, occlusion.
      Ignore   : the Reflectivity / Fresnel UI fields — this shader overwrites them.
*/

//provides FragmentState 's'
#include "../state.frag"

uniform float uThickness;  //name "Thickness (nm)"  default 500  min 0  max 1000

USE_TEXTURE2D(tRTexture);  //name "R LUT"
USE_TEXTURE2D(tTTexture);  //name "T LUT"

#define ET_PI_2   1.5707963267948966
#define ET_TWO_PI 6.283185307179586

// Compute per-channel phase coordinates and the angle coordinate.
void etCoords( in FragmentState s,
               out float s0, out float s1, out float s2, out float t_lut )
{
    float cosTheta = abs( dot( normalize( s.normal ), normalize( s.vertexEye ) ) );
    float theta    = acos( clamp( cosTheta, 0.0, 1.0 ) );

    const vec3 wavelength = vec3( 650.0, 530.0, 470.0 );
    float D = -2.0 * ET_TWO_PI * uThickness * cosTheta;
    s0 = mod( D / wavelength.r, ET_TWO_PI ) / ET_TWO_PI;
    s1 = mod( D / wavelength.g, ET_TWO_PI ) / ET_TWO_PI;
    s2 = mod( D / wavelength.b, ET_TWO_PI ) / ET_TWO_PI;

    t_lut = theta / ET_PI_2;
}

void EntanglementReflectivity( inout FragmentState s )
{
    float s0, s1, s2, t_lut;
    etCoords( s, s0, s1, s2, t_lut );

    s.reflectivity = vec3(
        texture2D( tRTexture, vec2( s0, t_lut ) ).r,
        texture2D( tRTexture, vec2( s1, t_lut ) ).r,
        texture2D( tRTexture, vec2( s2, t_lut ) ).r
    );
    s.fresnel = s.reflectivity;
}

#ifdef Reflectivity
    #undef Reflectivity
#endif
#define Reflectivity    EntanglementReflectivity

void EntanglementTransmissivity( inout FragmentState s )
{
    float s0, s1, s2, t_lut;
    etCoords( s, s0, s1, s2, t_lut );

    s.transmissivity = vec3(
        texture2D( tTTexture, vec2( s0, t_lut ) ).r,
        texture2D( tTTexture, vec2( s1, t_lut ) ).r,
        texture2D( tTTexture, vec2( s2, t_lut ) ).r
    );
}

#ifdef Transmissivity
    #undef Transmissivity
#endif
#define Transmissivity    EntanglementTransmissivity
