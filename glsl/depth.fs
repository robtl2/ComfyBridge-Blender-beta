
void main()
{
    float z = posView.z;
    z = clamp(z, range.x, range.y);
    z = (z - range.x) / (range.y - range.x);

    FragColor = vec4(z, z, z, 1.0);
}