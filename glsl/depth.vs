
void main()
{
    vec4 posWorld = modelMatrix * vec4(pos, 1.0);
    posView = (vMatrix * posWorld).xyz;

    gl_Position = vpMatrix * posWorld;
}