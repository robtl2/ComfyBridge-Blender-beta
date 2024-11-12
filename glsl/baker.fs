// uniform vec4 camera_pos;
// uniform vec4 camera_dir;
// uniform vec2 blend;
// uniform sampler2D ProjTexture;
// uniform sampler2D BaseTexture;

// in vec2 uvInterp;
// in vec2 uv2Interp;
// in vec3 posWorldInterp;
// in vec3 normalInterp;

// out vec4 FragColor;

void main()
{
    float is_ortho = camera_pos.w;
    vec3 pos_world = posWorldInterp;
    vec3 normal = normalize(normalInterp);

    vec3 V1 = normalize(camera_pos.xyz - pos_world);
    vec3 V2 = normalize(camera_dir.xyz);
    vec3 V = is_ortho?V2:V1;
    vec3 N = normalize(normal);
    float NoV = dot(N, V);

    float edge_0 = 1.0 + blend.y*0.5;
    float edge_1 = 1.0 - blend.y*0.5;
    float x = 1.0-NoV-blend.x;

    float blend_factor = smoothstep(edge_0, edge_1, x);

    vec4 proj_color = texture(ProjTexture, uvInterp);
    vec4 base_color = texture(BaseTexture, uv2Interp);

    vec4 color = mix(base_color, proj_color, blend_factor);

    color.rgb = pow(color.rgb, vec3(1.0/2.2));  
    FragColor = color;
}
