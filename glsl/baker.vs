
void main()
{
    normalInterp = mat3(transpose(inverse(modelMatrix))) * normal;
    uvInterp = uv_proj;
    uv2Interp = uv;
    
    vec4 pos_world = modelMatrix * vec4(position, 1.0);
    posWorldInterp = pos_world.xyz;

    vec2 pos = uv * 2.0 - 1.0;
    gl_Position = vec4(pos, 0.0, 1.0);
}