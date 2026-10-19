// Water surface (built-in render pipeline). TEXCOORD0.x = water depth (m, true, not exaggerated). In the 2D plan: the
// depth colours from the vertex colour (a map). In 3D: clear blue-green water, deeper and more opaque where it is
// deeper, gentle moving waves with a sun glint, livelier while it rains (_RainRate, mm/h). Thin water fades out at
// its edge.
Shader "SpongePark/Water"
{
    SubShader
    {
        Tags { "Queue"="Transparent" "RenderType"="Transparent" }
        ZWrite Off
        Blend SrcAlpha OneMinusSrcAlpha
        Pass
        {
            Tags { "LightMode"="ForwardBase" }
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_fog
            #include "LowPoly.cginc"
            float _RainRate;
            struct appdata { float4 vertex : POSITION; float3 normal : NORMAL; float4 color : COLOR; float2 uv : TEXCOORD0; };
            struct v2f { float4 pos : SV_POSITION; float4 color : COLOR; float3 wpos : TEXCOORD0; float depth : TEXCOORD1; float3 n : TEXCOORD3; UNITY_FOG_COORDS(2) };
            v2f vert(appdata v)
            {
                v2f o;
                float3 w = mul(unity_ObjectToWorld, v.vertex).xyz;
                // gentle facets that move; livelier in rain (3D only)
                float amp = (0.015 + 0.03 * saturate(_RainRate / 30)) * (1 - _PlanView) * saturate(v.uv.x * 20);
                w.y += amp * (sin(w.x * 1.7 + _Time.y * 1.3) + sin(w.z * 2.3 - _Time.y * 1.1));
                // the waves' own slope, for smooth light on them
                o.n = normalize(float3(-amp * 1.7 * cos(w.x * 1.7 + _Time.y * 1.3), 1, -amp * 2.3 * cos(w.z * 2.3 - _Time.y * 1.1)));
                o.wpos = w;
                o.pos = mul(UNITY_MATRIX_VP, float4(w, 1));
                o.color = v.color;
                o.depth = v.uv.x;
                UNITY_TRANSFER_FOG(o, o.pos);
                return o;
            }
            fixed4 frag(v2f i) : SV_Target
            {
                fixed4 plan = i.color;
                float d = i.depth;
                float3 n = normalize(i.n);
                fixed3 shallow = fixed3(0.36, 0.72, 0.78), deep = fixed3(0.10, 0.36, 0.58);
                fixed3 water = lerp(shallow, deep, saturate(d / 0.6));
                fixed3 col = LowPolyLight(water, n, 1);
                float3 v = normalize(_WorldSpaceCameraPos - i.wpos);
                float3 h = normalize(normalize(_WorldSpaceLightPos0.xyz) + v);
                col += _LightColor0.rgb * pow(saturate(dot(n, h)), 60) * 0.6 * (1 - _Overcast);
                fixed4 low = fixed4(col, lerp(0.55, 0.9, saturate(d / 0.5)) * saturate(d / 0.03));
                fixed4 c = lerp(low, plan, _PlanView);
                UNITY_APPLY_FOG(i.fogCoord, c.rgb);
                return c;
            }
            ENDCG
        }
    }
}
