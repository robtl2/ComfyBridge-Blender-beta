
void main()
{
    vec3 pos_local = pos.xyz;
    vec3 normal_local = normal.xyz;
    float offset = normal.w;

    mat4 mvp = vpMatrix * modelMatrix;
    vec4 clipPos = mvp * vec4(pos_local, 1.0);
    vec4 clipNormal = normalize(mvp * vec4(normal_local, 0.0));
    clipPos.xy += clipNormal.xy * aspectRatio * offset * clipPos.w;

    color_out = pos.www;
    gl_Position = clipPos;
}