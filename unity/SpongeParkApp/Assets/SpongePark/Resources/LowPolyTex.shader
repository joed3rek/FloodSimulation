// The low-poly packs' models (Synty POLYGON, Simple Nature Pack, Low Poly Tree Pack) as the app draws them: each
// pack's colour-palette texture with the app's own sun, sky light, shadows and haze, darker while it rains, so the
// packs and the app's models sit in one light. _Clip = 1 cuts out leaf edges (alpha below 0.5). _Unlit = 1 is the
// sky dome: its own colours, no light or haze, greyer under rain clouds.
Shader "SpongePark/LowPolyTex"
{
    Properties
    {
        _MainTex ("Palette", 2D) = "white" {}
        _Color ("Tint", Color) = (1, 1, 1, 1)
        _Clip ("Cut out", Float) = 0
        _Unlit ("Sky (unlit)", Float) = 0
    }
    SubShader
    {
        Tags { "RenderType"="Opaque" }
        Cull Off
        Pass
        {
            Tags { "LightMode"="ForwardBase" }
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_fwdbase
            #pragma multi_compile_fog
            #pragma multi_compile_instancing
            #include "LowPoly.cginc"
            sampler2D _MainTex;
            float4 _MainTex_ST;
            fixed4 _Color;
            float _Clip, _Unlit;
            struct appdata { float4 vertex : POSITION; float3 normal : NORMAL; float2 uv : TEXCOORD0; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct v2f { float4 pos : SV_POSITION; float2 uv : TEXCOORD0; float3 n : TEXCOORD1; SHADOW_COORDS(2) UNITY_FOG_COORDS(3) };
            v2f vert(appdata v)
            {
                UNITY_SETUP_INSTANCE_ID(v);
                v2f o;
                o.pos = UnityObjectToClipPos(v.vertex);
                o.uv = TRANSFORM_TEX(v.uv, _MainTex);
                o.n = UnityObjectToWorldNormal(v.normal);
                TRANSFER_SHADOW(o);
                UNITY_TRANSFER_FOG(o, o.pos);
                return o;
            }
            fixed4 frag(v2f i, fixed facing : VFACE) : SV_Target
            {
                fixed4 t = tex2D(_MainTex, i.uv) * _Color;
                if (_Clip > 0.5) clip(t.a - 0.5);
                if (_Unlit > 0.5)
                {
                    float grey = dot(t.rgb, float3(0.3, 0.59, 0.11));
                    return fixed4(lerp(t.rgb, grey * float3(0.85, 0.87, 0.9), _Overcast * 0.85), 1);
                }
                float3 n = normalize(i.n) * (facing > 0 ? 1 : -1);
                fixed3 albedo = lerp(Wetten(t.rgb, _Wet), t.rgb, _PlanView);
                fixed3 col = LowPolyLight(albedo, n, SHADOW_ATTENUATION(i));
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
            #pragma multi_compile_instancing
            #include "UnityCG.cginc"
            sampler2D _MainTex;
            float4 _MainTex_ST;
            float _Clip;
            struct v2f { V2F_SHADOW_CASTER; float2 uv : TEXCOORD1; };
            v2f vert(appdata_base v) { v2f o; TRANSFER_SHADOW_CASTER_NORMALOFFSET(o) o.uv = TRANSFORM_TEX(v.texcoord, _MainTex); return o; }
            float4 frag(v2f i) : SV_Target
            {
                if (_Clip > 0.5) clip(tex2D(_MainTex, i.uv).a - 0.5);
                SHADOW_CASTER_FRAGMENT(i)
            }
            ENDCG
        }
    }
}
