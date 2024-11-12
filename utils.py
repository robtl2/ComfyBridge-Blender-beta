import bpy
from .event import EventMan

def get_mesh_data_for_gpu(mesh_obj, add_uv_names=[], vertex_group_names=[], attribute_names=[]):
    """
    符合GPU绘制时使用的mesh数据, 几乎花了一整天时间, 我尽力了
    add_uv_names: 附加的UV层名称, 别把active的UV层也写进去了

    好了, 该准备的都准备好了, 哪家好人拿个normal还用matcap, 拿个depth还后处理啊
    """
    # mesh = mesh_obj.data

    # attributes里的数据很可能是geometry node之类的修改器生成的, 
    # 所以先evaluated_get, 相当于把数据塌陷一下, 不然拿到的是基础mesh的数据
    depsgraph = bpy.context.evaluated_depsgraph_get()
    eval_mesh = mesh_obj.evaluated_get(depsgraph).data
    uv_layer = eval_mesh.uv_layers.active.data if eval_mesh.uv_layers.active else None

    pos_data = []
    normal_data = []
    uv_data = []
    indices = []

    in_uv_datas = {}
    out_uv_datas = {}
    for name in add_uv_names:
        uv_layer = eval_mesh.uv_layers.get(name)
        if uv_layer:
            out_uv_datas[name] = []
            in_uv_datas[name] = uv_layer.data

    in_weight_datas = {}
    out_weight_datas = {}
    for name in vertex_group_names:
        data = mesh_obj.vertex_groups.get(name)
        if data:    
            out_weight_datas[name] = []
            in_weight_datas[name] = data

    in_attributes_data = {}
    in_attributes_type = {}
    out_attributes_data = {}
    for name in attribute_names:
        attribute_data = eval_mesh.attributes.get(name)
        
        out_attributes_data[name] = []
        in_attributes_data[name] = attribute_data.data
        in_attributes_type[name] = attribute_data.data_type

    vertex_dict = {}
    for loop_tri in eval_mesh.loop_triangles:
        for loop_index in loop_tri.loops:
            loop = eval_mesh.loops[loop_index]
            vertex = eval_mesh.vertices[loop.vertex_index]

            pos = tuple(vertex.co)
            normal = tuple(loop.normal)
            uv = (0, 0)
            if uv_layer:
                uv = tuple(uv_layer[loop_index].uv)

            uvs = {}
            uv_values = []
            for name in in_uv_datas:
                uvs[name] = tuple(in_uv_datas[name][loop_index].uv)
                uv_values.append(uvs[name]) 

            weights = {}
            for name in in_weight_datas:
                try:
                    weight = in_weight_datas[name].weight(vertex.index)
                except RuntimeError:
                    weight = 0.0
                weights[name] = weight

            values = {}
            for name in in_attributes_data:
                attribute_data = in_attributes_data[name]
                data_type = in_attributes_type[name]
                
                # 只支持Domain为Vertex的数据
                values[name] = 0
                if data_type == 'FLOAT':
                    values[name] = attribute_data[vertex.index].value
                elif data_type == 'VECTOR':
                    values[name] = tuple(attribute_data[vertex.index].vector)
                elif data_type == 'FLOAT_VECTOR':
                    values[name] = tuple(attribute_data[vertex.index].vector)
                elif data_type == 'COLOR':
                    values[name] = tuple(attribute_data[vertex.index].color)
                # 其它的？不好意思, 懒癌犯了
            
            # 优化重复的数据
            key = (pos, normal, uv, tuple(uv_values))
            if key not in vertex_dict:
                # 记录新的索引值
                vertex_dict[key] = len(pos_data)

                pos_data.append(pos)
                normal_data.append(normal)
                uv_data.append(uv)

                for name in in_uv_datas:
                    out_uv_datas[name].append(uvs[name])

                for name in in_weight_datas:
                    out_weight_datas[name].append(weights[name])

                for name in in_attributes_data:
                    out_attributes_data[name].append(values[name])
    
    for loop_tri in eval_mesh.loop_triangles:
        triangle = []
        for loop_index in loop_tri.loops:
            loop = eval_mesh.loops[loop_index]
            vertex = eval_mesh.vertices[loop.vertex_index]

            pos = tuple(vertex.co)
            normal = tuple(loop.normal)
            uv = (0, 0)
            if uv_layer:
                uv = tuple(uv_layer[loop_index].uv)

            uvs = {}
            uv_values = []
            for name in in_uv_datas:
                uvs[name] = tuple(in_uv_datas[name][loop_index].uv)
                uv_values.append(uvs[name]) 
            
            key = (pos, normal, uv, tuple(uv_values))
            triangle.append(vertex_dict[key])
        
        indices.append((triangle[0], triangle[1], triangle[2]))

    out = {
        "pos": pos_data,
        "normal": normal_data,
        "uv": uv_data,
        "indices": indices,
        "add_uvs": out_uv_datas,
        "weights": out_weight_datas,
        "attributes": out_attributes_data
    }

    # EventMan.Trigger("mesh_data_for_gpu_ready", {"object": mesh_obj, "data": out})
    return out

# TODO: 罗里吧嗦的，需要优化
def GetCameraVPMatrix(camera=None):
    vp_matrix = None
    view_matrix = None
    proj_matrix = None
    
    if camera:
        # Calculate camera matrices
        depsgraph = bpy.context.evaluated_depsgraph_get()
        view_matrix = camera.matrix_world.inverted()  # 视图矩阵

        is_ortho = 1 if camera.data.type == 'ORTHO' else 0
        # 检查相机类型并获取投影矩阵
        if is_ortho:
            # 对于正交相机，需要考虑正交缩放
            ortho_scale = camera.data.ortho_scale
            proj_matrix = camera.calc_matrix_camera(
                depsgraph,
                x=bpy.context.scene.render.resolution_x,
                y=bpy.context.scene.render.resolution_y,
                scale_x=bpy.context.scene.render.pixel_aspect_x * ortho_scale,
                scale_y=bpy.context.scene.render.pixel_aspect_y * ortho_scale,
            )
        else:
            # 透视相机保持原有计算方式
            proj_matrix = camera.calc_matrix_camera(
                depsgraph,
                x=bpy.context.scene.render.resolution_x,
                y=bpy.context.scene.render.resolution_y,
                scale_x=bpy.context.scene.render.pixel_aspect_x,
                scale_y=bpy.context.scene.render.pixel_aspect_y,
            )
        
        vp_matrix = proj_matrix @ view_matrix
    else:
        view3d = None
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                view3d = area.spaces.active
                break
        if view3d:
            region3d = view3d.region_3d
            view_matrix = region3d.view_matrix.inverted()
            proj_matrix = region3d.window_matrix
            vp_matrix = proj_matrix @ view_matrix
            is_ortho = region3d.is_orthographic_side_view or region3d.view_perspective == 'ORTHO'
    
    return vp_matrix, is_ortho, view_matrix, proj_matrix
    
def GetViewVector(camera):
    pos = camera.matrix_world.translation
    dir = -camera.matrix_world.to_3x3().col[2]
    return pos, dir

def Test(contex):
    print("test")


