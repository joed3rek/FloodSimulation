// Vertex-coloured and see-through (built-in render pipeline): the analysis pools, so the ground and the flow lines
// under them stay visible. The vertex colour's alpha is the opacity. Lit like SpongePark/VertexLit, without
// shadows (see-through surfaces do not receive them here); drawn after the solid models, without writing depth.
Shader "SpongePark/VertexLitAlpha"
{
    SubShader
    {
        Tags { "Queue"="Transparent" "RenderType"="Transparent" "IgnoreProjector"="True" }
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
            struct appdata { float4 vertex : POSITION; float3 normal : NORMAL; float4 color : COLOR; };
            struct v2f
            {
                float4 pos : SV_POSITION;
                float4 color : COLOR;
                float3 n : TEXCOORD0;
                UNITY_FOG_COORDS(1)
            };
            v2f vert(appdata v)
            {
                v2f o;
                o.pos = UnityObjectToClipPos(v.vertex);
                o.n = UnityObjectToWorldNormal(v.normal);
                o.color = v.color;
                UNITY_TRANSFER_FOG(o, o.pos);
                return o;
            }
            fixed4 frag(v2f i) : SV_Target
            {
                fixed3 albedo = lerp(Wetten(i.color.rgb, _Wet), i.color.rgb, _PlanView);
                fixed3 col = LowPolyLight(albedo, normalize(i.n), 1);
                UNITY_APPLY_FOG(i.fogCoord, col);
                return fixed4(col, i.color.a);
            }
            ENDCG
        }
    }
}
