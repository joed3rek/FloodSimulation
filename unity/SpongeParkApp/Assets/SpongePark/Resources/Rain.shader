// Falling rain (built-in render pipeline): thin streaks in a box in front of the camera, moved on the GPU. Each
// streak is a quad whose vertices carry a random spot in the box (POSITION, 0..1), which corner it is (TEXCOORD0)
// and an id (TEXCOORD1.x); streaks whose id is above _Density are hidden, so the rain thickens with the storm.
Shader "SpongePark/Rain"
{
    SubShader
    {
        Tags { "Queue"="Transparent+10" "RenderType"="Transparent" }
        ZWrite Off
        Cull Off
        Blend SrcAlpha OneMinusSrcAlpha
        Pass
        {
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #include "UnityCG.cginc"
            float3 _BoxCentre, _BoxSize, _Wind;
            float _Density, _StreakLength, _StreakWidth, _FallSpeed;
            fixed4 _RainColour;
            struct appdata { float4 vertex : POSITION; float2 corner : TEXCOORD0; float2 id : TEXCOORD1; };
            struct v2f { float4 pos : SV_POSITION; float2 corner : TEXCOORD0; float alpha : TEXCOORD1; };
            v2f vert(appdata v)
            {
                v2f o;
                float3 r = v.vertex.xyz;
                float y = frac(r.y - _Time.y * _FallSpeed / _BoxSize.y);
                float3 dir = normalize(float3(_Wind.x, -1, _Wind.z));
                float3 local = float3(r.x, y, r.z) - 0.5;
                float3 p = _BoxCentre + local * _BoxSize;
                p.xz += dir.xz / dir.y * (y - 0.5) * _BoxSize.y;   // drift with the wind as they fall
                float3 toCam = normalize(_WorldSpaceCameraPos - p);
                float3 side = normalize(cross(dir, toCam));
                float len = _StreakLength * (0.7 + 0.6 * frac(v.id.x * 17.3));
                p += dir * len * v.corner.y + side * _StreakWidth * v.corner.x;
                float shown = step(v.id.x, _Density);
                float edge = saturate(min(y, 1 - y) * 8) * saturate((0.5 - max(abs(local.x), abs(local.z))) * 8);
                o.pos = shown > 0 ? mul(UNITY_MATRIX_VP, float4(p, 1)) : float4(0, 0, -10, 1);   // hidden: outside the view
                o.corner = v.corner;
                o.alpha = edge * shown;
                return o;
            }
            fixed4 frag(v2f i) : SV_Target
            {
                float across = 1 - abs(i.corner.x);
                float along = sin(saturate(i.corner.y) * UNITY_PI);
                return fixed4(_RainColour.rgb, across * along * i.alpha * 0.25);
            }
            ENDCG
        }
    }
}
