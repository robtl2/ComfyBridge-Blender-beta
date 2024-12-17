"""
我知道cycles有自己的烘培, 但我就喜欢这么干
"""

import bpy
from .event import EventMan
import io
import threading
from .utils import get_mesh_data_for_gpu
from .gpu_render import OffScreenCommandBuffer, ShaderBatch


def bake(listener, args):
    obj = listener["obj"]
    if obj != args["object"]:
        return

    EventMan.Remove("mesh_data_for_gpu_ready", bake, listener)

    baker_vs = io.open("./glsl/baker.vs", "r").read()
    baker_fs = io.open("./glsl/baker.fs", "r").read()

    expand_vs = io.open("./glsl/expand.vs", "r").read()
    expand_fs = io.open("./glsl/expand.fs", "r").read()

    # input parameters
    size = listener["size"]
    modelMatrix = listener["modelMatrix"]
    camera_pos = listener["camera_pos"]
    camera_dir = listener["camera_dir"]
    base_image = listener["base_image"]
    proj_image = listener["proj_image"]
    blend = listener["blend"]

    mesh_data = args["data"]
    vertices = mesh_data["pos"]
    uvs = mesh_data["uv"]
    uv_proj = mesh_data["attributes"]["uv_proj"]
    normals = mesh_data["normal"]
    indices = mesh_data["indices"]

    baker_batch = ShaderBatch()
    baker_batch.define_shader(
        "baker",
        uniforms = [
            ('VEC4', 'camera_pos', camera_pos),
            ('VEC4', 'camera_dir', camera_dir),
            ('VEC2', 'blend', blend),
            ('TEX_2D', 'ProjTexture', proj_image),
            ('TEX_2D', 'BaseTexture', base_image)
        ], 
        vert_in={
            'position':'VEC3',
            'normal':'VEC3',
            'uv':'VEC2',
            'uv_proj':'VEC2'    
        }, 
        vert_out={
            'uvInterp':'VEC2',
            'uv2Interp':'VEC2',
            'posWorldInterp':'VEC3',
            'normalInterp':'VEC3'
        }, 
        frag_out={
            'FragColor':'VEC4'
        }, 
        vs=baker_vs, 
        fs=baker_fs
    )

    baker_batch.add_batch(
        "baker",
        {
            'position': vertices,
            'normal': normals,
            'uv': uvs,
            'uv_proj': uv_proj
        }, 
        indices=indices,
        matrix=modelMatrix
    )

    expand_batch = ShaderBatch()
    expand_batch.define_shader(
        "expand",
        uniforms = [
            ('FLOAT','p', 1.0/size),
            ('TEX_2D', 'BaseTexture', proj_image)
        ], 
        vert_in={
            'vert':'VEC4',
        }, 
        vert_out={
            'uv':'VEC2'
        }, 
        frag_out={
            'FragColor':'VEC4'
        }, 
        vs=expand_vs, 
        fs=expand_fs
    )

    expand_batch.add_batch(
        "expand",
        {
            'vert': [(-1.0, -1.0, 0.0, 0.0), (3.0, -1.0, 2.0, 0.0), (-1.0, 3.0, 0.0, 2.0)]
        }
    )

    # 一顿骚操作就是为了在这里享受一下
    cmb = OffScreenCommandBuffer((size, size))
    cmb.clear()
    cmb.matrix_push()
    cmb.draw(baker_batch)
    # 向外扩展4象素，免得有UV接缝
    for _ in range(4): 
        cmb.fetch(lambda texture: expand_batch.update_uniform("expand","BaseTexture", texture))
        cmb.swap()
        cmb.clear()
        cmb.draw(expand_batch)
    cmb.matrix_pop()
    buffer = cmb.execute()
    
    # 保存图像
    image_name = f"{obj.name}_baked"
    if image_name not in bpy.data.images:
        bpy.data.images.new(image_name, size, size)
    image = bpy.data.images[image_name]
    image.scale(size, size)

    image.pixels = [v / 255 for v in buffer]

    EventMan.Trigger("gpu_baker_done", {
        "obj": obj,
        "image": image
    })
        
def StartBake(active_obj, size=1024):
    """
    这一堆的代码全都只是在赋值
    """
    if not active_obj or active_obj.type != 'MESH':
        return
    
    uv_layer = active_obj.data.uv_layers.active
    if not uv_layer:
        return  
    
    modifier = next((mod for mod in active_obj.modifiers if mod.type == 'NODES' and mod.node_group.name == "CameraProjection"), None)
    if not modifier:
        return
    
    material = active_obj.data.materials[0]
    if not material:
        return
    
    mat_labels = ["Is_Ortho", "Camera_Pos", "Camera_Dir", "Base Texture", "Projection Texture"]
    mat_nodes = [next((n for n in material.node_tree.nodes if n.label == label), None) for label in mat_labels]
    if any(node is None for node in mat_nodes):
        return
    
    modelMatrix = active_obj.matrix_world
    
    is_ortho = mat_nodes[0].outputs[0].default_value
    camera_pos = mat_nodes[1].inputs[0].default_value
    camera_dir = mat_nodes[2].inputs[0].default_value
    base_image = mat_nodes[3].image
    proj_image = mat_nodes[4].image

    camera_pos = (camera_pos[0], camera_pos[1], camera_pos[2], is_ortho)
    camera_dir = (camera_dir[0], camera_dir[1], camera_dir[2], 1)

    if not base_image:
        black_img = bpy.data.images.get("temp_image_black")
        if not black_img:
            black_img = bpy.data.images.new("temp_image_black", 16, 16)
            black_img.pixels = [0, 0, 0, 1] * 16 * 16
        base_image = black_img

    if not proj_image:
        white_img = bpy.data.images.get("temp_image_white")
        if not white_img:
            white_img = bpy.data.images.new("temp_image_white", 16, 16)
            white_img.pixels = [1, 1, 1, 1] * 16 * 16
        proj_image = white_img

    blend_offset = active_obj.projection_props.offset
    blend_range = active_obj.projection_props.blend
    
    EventMan.Add("mesh_data_for_gpu_ready", bake, {
        "obj": active_obj,
        "size": size,
        "modelMatrix": modelMatrix,
        "camera_pos": camera_pos,
        "camera_dir": camera_dir,
        "base_image": base_image,
        "proj_image": proj_image,
        "blend": (blend_offset, blend_range),
    })

    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_mesh = active_obj.evaluated_get(depsgraph)
    eval_mesh_data = eval_mesh.data

    def get_mesh_data_thread():
        mesh_data = get_mesh_data_for_gpu(eval_mesh, eval_mesh_data, attribute_names=["uv_proj"])
        EventMan.Trigger("mesh_data_for_gpu_ready", {"object": active_obj, "data": mesh_data})
    
    thread = threading.Thread(
        target=get_mesh_data_thread
    )
    thread.start()


    