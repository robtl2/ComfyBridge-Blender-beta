

void main()
{
    vec4 color = texture(BaseTexture, uv);

    if (color.a > 0.5) {
        FragColor = color;
        return;
    }

    vec2 offsets[8] = vec2[](
        vec2(p, 0.0), vec2(-p, 0.0), vec2(0.0, p), vec2(0.0, -p),
        vec2(p, p), vec2(p, -p), vec2(-p, p), vec2(-p, -p)
    );

    float weights[8] = float[](1.0, 1.0, 1.0, 1.0, 0.7071, 0.7071, 0.7071, 0.7071);

    vec3 rgb = vec3(0.0);
    float a = 0.0;

    for (int i = 0; i < 8; ++i) {
        vec4 color = texture(BaseTexture, uv + offsets[i]);
        color.a *= weights[i];
        if (color.a > 0.0) {
            a += color.a;
        }
        rgb += color.rgb * color.a;
    }

    rgb /= (a>0.0?a:1.0);
    a = a>0.0?1.0:0.0;

    color.rgb = rgb;
    color.a = a;

    FragColor = color;
}