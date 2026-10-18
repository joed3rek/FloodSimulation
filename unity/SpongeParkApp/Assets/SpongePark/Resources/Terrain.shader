// Ground: vertex colours (by height over the park's range) with sun, soft shadows, sky light and haze, a fine
// grass texture, and contour lines drawn from the true ground level carried in TEXCOORD1.x (metres, not
// exaggerated). Lines are computed per pixel, so they always lie exactly on the surface; every fifth line is a
// stronger major contour. TEXCOORD1.y = 1 on the park's own ground (contours and grass only there).
Shader "SpongePark/Terrain"
{
    Properties
    {
        _Interval ("Contour interval (m)", Float) = 0.1
        _Opacity ("Contour opacity", Range(0, 1)) = 0.85
        _LineColor ("Contour colour", Color) = (0.24, 0.16, 0.09, 1)
    }
    SubShader
    {
        Tags { "RenderType"="Opaque" }
        Pass
        {
            Tags { "LightMode"="ForwardBase" }
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma target 3.0
            #pragma multi_compile_fwdbase
            #pragma multi_compile_fog
            #include "UnityCG.cginc"
            #include "Lighting.cginc"
            #include "AutoLight.cginc"
            float _Interval, _Opacity;
            fixed4 _LineColor;
            struct appdata { float4 vertex : POSITION; float3 normal : NORMAL; float4 color : COLOR; float2 level : TEXCOORD1; };
            struct v2f
            {
                float4 pos : SV_POSITION;
                float4 color : COLOR;
                float3 n : TEXCOORD0;
                float2 level : TEXCOORD1;
                float3 wpos : TEXCOORD2;
                SHADOW_COORDS(3)
                UNITY_FOG_COORDS(4)
            };
            v2f vert (appdata v)
            {
                v2f o;
                o.pos = UnityObjectToClipPos(v.vertex);
                o.n = UnityObjectToWorldNormal(v.normal);
                o.color = v.color;
                o.level = v.level;
                o.wpos = mul(unity_ObjectToWorld, v.vertex).xyz;
                TRANSFER_SHADOW(o);
                UNITY_TRANSFER_FOG(o, o.pos);
                return o;
            }
            float hash(float2 p) { return frac(sin(dot(p, float2(12.9898, 78.233))) * 43758.5453); }
            float noise(float2 p)
            {
                float2 i = floor(p), f = frac(p);
                f = f * f * (3 - 2 * f);
                return lerp(lerp(hash(i), hash(i + float2(1, 0)), f.x), lerp(hash(i + float2(0, 1)), hash(i + 1), f.x), f.y);
            }
            float contour(float level, float interval, float widthPx)
            {
                float f = level / interval;
                float d = abs(frac(f + 0.5) - 0.5) / max(fwidth(f), 1e-5);
                return 1 - saturate(d - widthPx * 0.5 + 0.5);
            }
            fixed4 frag (v2f i) : SV_Target
            {
                float3 n = normalize(i.n);
                float3 L = normalize(_WorldSpaceLightPos0.xyz);
                float sun = saturate(dot(n, L)) * SHADOW_ATTENUATION(i);
                float3 ambient = lerp(float3(0.50, 0.47, 0.40), float3(0.74, 0.80, 0.86), n.y * 0.5 + 0.5);
                // grass: patches a few metres across and a fine grain, on the park only
                float park = step(0.5, i.level.y);
                float g = noise(i.wpos.xz * 0.35) * 0.6 + noise(i.wpos.xz * 2.7) * 0.4;
                float3 base = i.color.rgb * lerp(1, 0.86 + 0.26 * g, park);
                float3 col = base * (ambient * 0.62 + _LightColor0.rgb * sun * 0.72);
                // contours (derivatives outside any branch; mask and opacity only scale the result)
                float interval = max(_Interval, 1e-3);
                float minor = contour(i.level.x, interval, 1.6);
                float major = contour(i.level.x, interval * 5, 3.0);
                float a = max(minor * 0.7, major) * _Opacity * park;
                col = lerp(col, _LineColor.rgb, a);
                UNITY_APPLY_FOG(i.fogCoord, col);
                return fixed4(col, 1);
            }
            ENDCG
        }
        Pass
        {
            Tags { "LightMode"="ShadowCaster" }
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_shadowcaster
            #include "UnityCG.cginc"
            struct v2f { V2F_SHADOW_CASTER; };
            v2f vert (appdata_base v)
            {
                v2f o;
                TRANSFER_SHADOW_CASTER_NORMALOFFSET(o)
                return o;
            }
            float4 frag (v2f i) : SV_Target { SHADOW_CASTER_FRAGMENT(i) }
            ENDCG
        }
    }
}
