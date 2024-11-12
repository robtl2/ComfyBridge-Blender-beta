
void main()
{
    vec3 normalWorld = mat3(transpose(inverse(modelMatrix))) * normal;
    normalView = mat3(vMatrix) * normalWorld;
    gl_Position = vpMatrix * modelMatrix * vec4(pos, 1.0);
}