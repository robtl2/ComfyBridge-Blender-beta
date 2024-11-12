
void main()
{
    vec3 N = normalize(normalView);
    N = N * 0.5 + 0.5;
    FragColor = vec4(N, 1.0);
}