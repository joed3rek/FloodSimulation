// Ground (built-in render pipeline). In the 2D plan: vertex colours by height over the park's range (a map).
// In 3D: soft natural colours — lawn in patches of lighter and darker green, planted NbS beds, bare basins, gravel
// round wells — darker while it rains. Both show contour lines from the true ground level in TEXCOORD1.x
// (metres, not exaggerated), computed per pixel so they lie exactly on the surface; every fifth line is a stronger
// major contour. TEXCOORD1.y = 1 on the park's own ground (contours and lawn only there). TEXCOORD2.x: what covers it
// (0 lawn, 1 planted NbS, 2 basin or pond, 3 well).
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
            #include "LowPoly.cginc"
            float _Interval, _Opacity;
            fixed4 _LineColor;
            struct appdata { float4 vertex : POSITION; float3 normal : NORMAL; float4 color : COLOR; float2 level : TEXCOORD1; float2 kind : TEXCOORD2; };
            struct v2f
            {
                float4 pos : SV_POSITION;
                float4 color : COLOR;
                float3 n : TEXCOORD0;
                float2 level : TEXCOORD1;
                float3 wpos : TEXCOORD2;
                float kind : TEXCOORD3;
                SHADOW_COORDS(4)
                UNITY_FOG_COORDS(5)
            };
            v2f vert(appdata v)
            {
                v2f o;
                o.pos = UnityObjectToClipPos(v.vertex);
                o.n = UnityObjectToWorldNormal(v.normal);
                o.color = v.color;
                o.level = v.level;
                o.kind = v.kind.x;
                o.wpos = mul(unity_ObjectToWorld, v.vertex).xyz;
                TRANSFER_SHADOW(o);
                UNITY_TRANSFER_FOG(o, o.pos);
                return o;
            }
            float contour(float level, float interval, float widthPx)
            {
                float f = level / interval;
                float d = abs(frac(f + 0.5) - 0.5) / max(fwidth(f), 1e-5);
                return 1 - saturate(d - widthPx * 0.5 + 0.5);
            }
            fixed4 frag(v2f i) : SV_Target
            {
                float park = step(0.5, i.level.y);
                // 3D: colours by what covers the ground, in soft patches
                float k = i.kind;
                float jitter = Noise2(i.wpos.xz * 0.12) * 0.7 + Noise2(i.wpos.xz * 1.3) * 0.3 - 0.5;
                fixed3 lawn = fixed3(0.47, 0.64, 0.30) * (1 + 0.12 * jitter);
                fixed3 bed = fixed3(0.40, 0.30, 0.20) * (1 + 0.1 * jitter);
                fixed3 basin = fixed3(0.52, 0.44, 0.32) * (1 + 0.08 * jitter);
                fixed3 gravel = fixed3(0.66, 0.64, 0.60) * (1 + 0.08 * jitter);
                fixed3 low = k < 0.5 ? lawn : k < 1.5 ? bed : k < 2.5 ? basin : gravel;
                low = lerp(i.color.rgb, low, park);   // beyond the park: the plain base
                fixed3 albedo = lerp(Wetten(low, _Wet), i.color.rgb, _PlanView);
                float3 n = normalize(i.n);
                fixed3 col = LowPolyLight(albedo, n, SHADOW_ATTENUATION(i));
                // contours (derivatives outside any branch; mask and opacity only scale the result)
                float interval = max(_Interval, 1e-3);
                float minor = contour(i.level.x, interval, 1.6);
                float major = contour(i.level.x, interval * 5, 3.0);
                float a = max(minor * 0.7, major) * _Opacity * park * lerp(0.7, 1, _PlanView);
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
            v2f vert(appdata_base v) { v2f o; TRANSFER_SHADOW_CASTER_NORMALOFFSET(o) return o; }
            float4 frag(v2f i) : SV_Target { SHADOW_CASTER_FRAGMENT(i) }
            ENDCG
        }
    }
}
