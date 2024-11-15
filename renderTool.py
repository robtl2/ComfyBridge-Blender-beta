import bpy
import tempfile
import os
import threading
from .event import EventMan
from .tmp_setting import TmpSetting
from mathutils import Vector
from .gpu_depth_normal import DepthNormalRenderer

def RenderCollection(context, sender):
    names = []
    image_datas = []
    names_in_list = []

    sender_name = sender.collection_name

    # print(f"render collection: {sender.collection_name}")

    def render_color():
        tmp_path = os.path.join(tempfile.gettempdir(), f'{sender_name}_C.png')
        bpy.context.scene.eevee.taa_samples = sender.samples
        bpy.context.scene.render.filepath = tmp_path
        bpy.ops.render.opengl(write_still=True, view_context=True)
        TmpSetting.restore()

        def file_thread():
            if os.path.exists(tmp_path):
                with open(tmp_path, 'rb') as f:
                    image_data = f.read()
                os.remove(tmp_path)
                EventMan.Trigger("image_ready_to_send", {'name': f"{sender_name}_C", 'data': image_data, 'cleanup': False})

        thread = threading.Thread(target=file_thread)
        thread.start()

    def on_image_ready_to_send(data):
        if data['cleanup']:
            bpy.data.images.remove(data['image'])

        img_name = data['name']
        names.append(img_name)
        image_datas.append(data['data'])

        if img_name in names_in_list:
            names_in_list.remove(img_name)

        if len(names_in_list) == 0:
            EventMan.Remove("image_ready_to_send", on_image_ready_to_send)
            EventMan.Trigger("render_complete", {'sender': sender, 'names': names, 'image_datas': image_datas})

    def prepare_render():
        TmpSetting.record()
        more_channels = False
        # 设置集合可见性
        for _name in TmpSetting.collection_names:
            collection = TmpSetting.collections.get(_name)
            if collection:
                collection['collection'].hide_viewport = _name != sender_name

        if sender.output_viewport:
            names_in_list.append(f"{sender_name}_C")

        if sender.output_more:
            if sender.output_depth:
                more_channels = True
                names_in_list.append(f"{sender_name}_D")
            if sender.output_normal:
                more_channels = True
                names_in_list.append(f"{sender_name}_N")
            if sender.output_lineart:
                more_channels = True
                names_in_list.append(f"{sender_name}_L")
            if sender.output_mask:
                more_channels = True
                names_in_list.append(f"{sender_name}_M")

        return more_channels

    def render(more_channels):
        EventMan.Add("image_ready_to_send", on_image_ready_to_send)

        if sender.output_viewport:
            render_color()
        else:
            TmpSetting.restore()

        if more_channels:
            depth_normal_renderer = DepthNormalRenderer(context, sender_name)
            if sender.output_depth:
                depth_normal_renderer.render_depth()
            if sender.output_normal:
                depth_normal_renderer.render_normal()
            if sender.output_lineart:
                depth_normal_renderer.render_lineart()
            if sender.output_mask:
                depth_normal_renderer.render_mask()

    more_channels = prepare_render()
    render(more_channels)


def LoadProjectionAssets():
    addon_dir = os.path.dirname(os.path.realpath(__file__))
    blend_path = os.path.join(addon_dir, "nodes", "nodes.blend")
    
    # if "CameraProjection" in bpy.data.node_groups:
    #     bpy.data.node_groups.remove(bpy.data.node_groups["CameraProjection"])
    # if "Projection_Mat" in bpy.data.materials:
    #     bpy.data.materials.remove(bpy.data.materials["Projection_Mat"])

    if "CameraProjection" not in bpy.data.node_groups:
        bpy.ops.wm.append(
            filename="CameraProjection",  # 节点组名称
            directory=blend_path + "/NodeTree/",  # 指定数据类型
            link=False  # False表示复制，True表示链接
        )
    if "Projection_Mat" not in bpy.data.materials:
        bpy.ops.wm.append(
            filename="Projection_Mat",
            directory=blend_path + "/Material/",
            link=False
        )

    geometry_node = bpy.data.node_groups.get("CameraProjection")
    material = bpy.data.materials.get("Projection_Mat")
    return geometry_node, material

def CreateProjectionTexture(obj, vp_matrix, camera_pos, camera_dir, is_ortho, image):
    # 加载节点组
    geometry_node, base_material = LoadProjectionAssets()
    if not geometry_node or not base_material:
        return
    
    mat_name = f"{obj.name}_Projection"
    if mat_name in bpy.data.materials:
        material = bpy.data.materials[mat_name]
    else:
        material = base_material.copy()
        material.name = mat_name
    
    proj_props = obj.projection_props
    proj_props.enabled = True
    
    modifier = obj.modifiers.new(name="Camera Projection", type='NODES')
    modifier.node_group = geometry_node
    if "uv_proj" not in obj.data.attributes:
        obj.data.attributes.new(name="uv_proj", type='FLOAT_VECTOR', domain='POINT')

    proj_props.origin_materials.clear()
    if obj.data.materials:
        for i in range(len(obj.data.materials)):
            origin_material = obj.data.materials[i]
            item = proj_props.origin_materials.add()
            item.text = origin_material.name if origin_material else ""
            obj.data.materials[i] = material
    else:
        obj.data.materials.append(material)

    # 赋值参数 ------------------------------------------------------------
    nodes = modifier.node_group.nodes
    vp_node = next((n for n in nodes if n.label == 'CameraVP'), None)
    if vp_node:
        for i in range(4):
            for j in range(4):
                vp_node.inputs[j * 4 + i].default_value = vp_matrix[i][j] 

    projection_texture_node = next((node for node in material.node_tree.nodes 
                                  if node.label == "Projection Texture"), None)
    if projection_texture_node:
        projection_texture_node.image = image

    weight_node = next((node for node in material.node_tree.nodes 
                                  if node.label == "Use_Projection"), None)
    if weight_node:
        weight_node.outputs[0].default_value = 1

    camera_pos_node = next((node for node in material.node_tree.nodes
                                  if node.label == "Camera_Pos"), None)
    if camera_pos_node:
        camera_pos_node.inputs[0].default_value = Vector(camera_pos)

    camera_dir_node = next((node for node in material.node_tree.nodes
                                  if node.label == "Camera_Dir"), None)
    if camera_dir_node:
        camera_dir_node.inputs[0].default_value = Vector(camera_dir)

    is_ortho_node = next((node for node in material.node_tree.nodes
                                  if node.label == "Is_Ortho"), None)
    if is_ortho_node:
        is_ortho_node.outputs[0].default_value = is_ortho
    # ---------------------------------------------------------------------

    


    


