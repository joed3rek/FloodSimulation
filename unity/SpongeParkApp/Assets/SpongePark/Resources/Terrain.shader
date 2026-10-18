// Ground: vertex colours with simple directional lighting (as VertexLit), plus contour lines drawn from
// the true ground level carried in TEXCOORD1.x (metres, not exaggerated). Lines are computed per pixel,
// so they always lie exactly on the surface; every fifth line is a stronger major contour.
Shader "SpongePark/Terrain"
{
    Properties
    {
        _Interval ("Contour interval (m)", Float) = 0.1
        _Opacity ("Contour opacity", Range(0, 1)) = 0.55
        _LineColor ("Contour colour", Color) = (0.35, 0.24, 0.14, 1)
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
            #include "UnityCG.cginc"
            #include "Lighting.cginc"
            float _Interval, _Opacity;
            fixed4 _LineColor;
            struct appdata { float4 vertex : POSITION; float3 normal : NORMAL; float4 color : COLOR; float2 level : TEXCOORD1; };
            struct v2f { float4 pos : SV_POSITION; float4 color : COLOR; float3 n : TEXCOORD0; float2 level : TEXCOORD1; };
            v2f vert (appdata v)
            {
                v2f o;
                o.pos = UnityObjectToClipPos(v.vertex);
                o.n = UnityObjectToWorldNormal(v.normal);
                o.color = v.color;
                o.level = v.level;
                return o;
            }
            float contour(float level, float interval, float widthPx)
            {
                float f = level / interval;
                float d = abs(frac(f + 0.5) - 0.5) / max(fwidth(f), 1e-5);
                return 1 - saturate(d - widthPx * 0.5 + 0.5);
            }
            fixed4 frag (v2f i) : SV_Target
            {
                float3 L = normalize(_WorldSpaceLightPos0.xyz);
                float lambert = saturate(dot(normalize(i.n), L));
                float3 col = i.color.rgb * (0.45 + 0.55 * lambert);
                // derivatives outside any branch; the park mask (level.y) and opacity only scale the result
                float interval = max(_Interval, 1e-3);
                float minor = contour(i.level.x, interval, 1.0);
                float major = contour(i.level.x, interval * 5, 2.0);
                float a = max(minor * 0.6, major) * _Opacity * step(0.5, i.level.y);
                col = lerp(col, _LineColor.rgb, a);
                return fixed4(col, 1);
            }
            ENDCG
        }
    }
}
