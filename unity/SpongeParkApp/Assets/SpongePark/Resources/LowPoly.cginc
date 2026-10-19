// Shared by the app's low-poly shaders (built-in render pipeline): flat facets, flat colours, sun with soft
// shadows, sky light from above and bounce from the ground, haze; and the weather the app sets each frame:
//   _PlanView  1 in the 2D plan (map colours), 0 in 3D (the low-poly look)
//   _Wet       0 dry .. 1 soaked (ground and models darker while it rains)
//   _Overcast  0 clear .. 1 under rain clouds (flatter, greyer light)
#ifndef SPONGE_LOWPOLY
#define SPONGE_LOWPOLY

#include "UnityCG.cginc"
#include "Lighting.cginc"
#include "AutoLight.cginc"

float _PlanView, _Wet, _Overcast;

float Hash21(float2 p) { return frac(sin(dot(p, float2(12.9898, 78.233))) * 43758.5453); }

float Noise2(float2 p)
{
    float2 i = floor(p), f = frac(p);
    f = f * f * (3 - 2 * f);
    return lerp(lerp(Hash21(i), Hash21(i + float2(1, 0)), f.x), lerp(Hash21(i + float2(0, 1)), Hash21(i + 1), f.x), f.y);
}

// the facet's own normal (one per triangle), from the surface's screen-space derivatives
float3 FacetNormal(float3 worldPos)
{
    return normalize(cross(ddy(worldPos), ddx(worldPos)));
}

// sun (with its shadow) and a sky light that greys and flattens under cloud
fixed3 LowPolyLight(fixed3 albedo, float3 n, float shadow)
{
    float3 L = normalize(_WorldSpaceLightPos0.xyz);
    float sun = saturate(dot(n, L)) * shadow;
    float3 sky = lerp(float3(0.74, 0.80, 0.86), float3(0.72, 0.74, 0.76), _Overcast);
    float3 ground = lerp(float3(0.50, 0.47, 0.40), float3(0.55, 0.55, 0.55), _Overcast);
    float3 ambient = lerp(ground, sky, n.y * 0.5 + 0.5) * lerp(0.62, 0.8, _Overcast);
    return albedo * (ambient + _LightColor0.rgb * sun * 0.72);
}

fixed3 Wetten(fixed3 albedo, float amount) { return albedo * (1 - 0.3 * amount); }

#endif
