// Upgrade NOTE: replaced 'mul(UNITY_MATRIX_MVP,*)' with 'UnityObjectToClipPos(*)'

Shader "Unlit/PortalShader"
{
    Properties
    {
        _PrimaryColor ("Portal Color", Color) = (1, 0.1, 0.2, 1)
        _BorderThreshold ("Border Threshold", Float) = 10
        [NoScaleOffset] _MainTex ("Texture", 2D) = "white" {}
    }
    SubShader
    {
        Pass
        {
            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag

            struct app2v
            {
                float4 vertex : POSITION;
                float2 uv : TEXCOORD0;
            };

            struct v2f
            {
                float2 uv : TEXCOORD0;
                float4 vertex : SV_POSITION;
            };

            v2f vert (app2v v)
            {
                v2f o;
                o.vertex = UnityObjectToClipPos(v.vertex);
                o.uv = v.uv;
                return o;
            }
            
            sampler2D _MainTex;
            float4 _MainTex_TexelSize;
            fixed4 _PrimaryColor;
            float _BorderThreshold;

            fixed4 frag (v2f i) : SV_Target
            {
                // sample the texture
                fixed4 col = tex2D(_MainTex,
                    i.uv + float2(_Time[1], 0)
                    ) * _PrimaryColor;

                
                if (i.uv.x < _MainTex_TexelSize.x * _BorderThreshold ||
                    i.uv.x > 1 - _MainTex_TexelSize.x * _BorderThreshold ||
                    i.uv.y < _MainTex_TexelSize.x * _BorderThreshold ||
                    i.uv.y > 1 - _MainTex_TexelSize.x * _BorderThreshold )
                    col = (1,1,1,1);
                
                return col;
            }
            ENDCG
        }
    }
}
