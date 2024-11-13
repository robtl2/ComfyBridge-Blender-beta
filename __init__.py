import bpy
import blf
import tempfile
import os
from .comfy_bridge import Connect, Disconnect, Connect_Info
from .event import EventMan
from .utils import GetCameraVPMatrix, GetViewVector
from .renderTool import CreateProjectionTexture
from .cb_props import CBProps, ReceiverNameGroup, SenderNameGroup, ProjectionProps, SimpleNameGroup
from .queue_prompt import ExecuteQueuePrompt, on_receiver_changed
from .tmp_setting import TmpSetting
from .gpu_baker import StartBake
from .utils import Test


bl_info = {
    "name" : "ComfyBridge-Blender",
    "author" : "robtl2@icloud.com",
    "description" : "ComfyUI-ComfyBridge's Blender plugin",
    "blender" : (4, 2, 1),
    "version" : (0, 1, 1),
    "location" : "",
    "warning" : "",
    "category" : "Generic"
}

class CBPreferences(bpy.types.AddonPreferences):
    bl_idname = __name__  # 使用当前模块名

    port: bpy.props.IntProperty(
        name="Port",
        description="The port of ComfyUI-ComfyBridge",
        default=17777,
    ) # type: ignore

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "port", text="Port")

def on_image_received(pack):
    cb_props = bpy.context.scene.comfy_bridge_props
    tmp_dir = tempfile.gettempdir()
    request_name = pack['name']
    image_data = pack['data']
    file_path = os.path.join(tmp_dir, f'{request_name}.png')

    cb_props.progress = 0
    
    with open(file_path, 'wb') as f:
        f.write(image_data)

    is_new = False
    if request_name not in bpy.data.images:
        bpy.data.images.new(request_name, 16, 16)
        is_new = True

    image = bpy.data.images[request_name]
    image.filepath = file_path
    image.source = 'FILE'
    image.reload()

    if is_new:
        if TmpSetting.space_2D:
            TmpSetting.space_2D.image = image

    cb_props.progress = 0
    cb_props.info = ''
    print(f'image received: {request_name}')
    if request_name in TmpSetting.request_names:
        TmpSetting.request_names.remove(request_name)

def on_progress(args):
    if len(TmpSetting.request_names) == 0:
        return
    
    _p = args['progress']
    _m = args['max']
    value = _p / _m
    cb_props = bpy.context.scene.comfy_bridge_props
    cb_props.progress = value

    if TmpSetting.area_3D:
        TmpSetting.area_3D.tag_redraw()

def do_connect():
    cb_props = bpy.context.scene.comfy_bridge_props
    EventMan.Add('on_image_received', on_image_received)
    EventMan.Add('on_progress', on_progress)
    prefs = bpy.context.preferences.addons[__name__].preferences
    port = prefs.port
    Connect(cb_props.server_host, port)

@bpy.app.handlers.persistent
def do_disconnect(dummy=None):
    if not Connect_Info['isConnected']:
        return
    
    print('disconnecting...')
    cb_props = bpy.context.scene.comfy_bridge_props
    cb_props.progress = 0
    cb_props.info = ''
    EventMan.Remove('on_image_received', on_image_received)
    EventMan.Remove('on_progress', on_progress)
    Disconnect()

def is_in_camera(context):
    for area in context.window.screen.areas:
        if area.type == 'VIEW_3D':
            space_3D = area.spaces.active
            if space_3D.region_3d.view_perspective == 'CAMERA':
                return True
    return False

def remove_geometry_node(obj, node_name):
    for modifier in obj.modifiers:
        if modifier.type == 'NODES' and modifier.node_group and modifier.node_group.name == node_name:
            obj.modifiers.remove(modifier)

class ConnectOperator(bpy.types.Operator):
    bl_idname = "cb.connect"
    bl_label = ""
    bl_description = "Connect to ComfyUI-ComfyBridge"
    
    def execute(self, context):
        cb_props = context.scene.comfy_bridge_props
        if not Connect_Info['isConnected']:
            cb_props.show_info = True
            do_connect()
        else:
            cb_props.show_info = False
            do_disconnect()

        return {'FINISHED'}

class SenderOperator(bpy.types.Operator):
    bl_idname = "cb.set_sender"
    bl_label = ""
    bl_description = "添加或删除一个发送向ComfyUI的Collection"
    option: bpy.props.EnumProperty(items=(
        ('ADD', '', ''),
        ('REM', '', ''),
    )) # type: ignore

    def execute(self, context):
        cb_props = context.scene.comfy_bridge_props
        list = cb_props.sender_list
        index = cb_props.sender_index
        operate = self.option

        count = len(list)

        if operate == 'ADD':
            list.add()
            index = count - 1
            cb_props.sender_index = index
        elif operate == 'REM':
            list.remove(index)
            index = min(max(0, index - 1), count - 1)
            cb_props.sender_index = index

        return {'FINISHED'}

class ReceiverOperator(bpy.types.Operator):
    bl_idname = "cb.set_receiver"
    bl_label = ""
    bl_description = "添加或删除一个接收至ComfyUI的Image"
    option: bpy.props.EnumProperty(items=(
        ('ADD', '', ''),
        ('REM', '', ''),
    )) # type: ignore

    def execute(self, context):
        cb_props = context.scene.comfy_bridge_props
        list = cb_props.receiver_list
        index = cb_props.receiver_index

        operate = self.option
        count = len(list)

        if operate == 'ADD':
            item = list.add()
            item.text = "image name" # 这里会触发on_text_changed，所以不用加on_receiver_changed
            index = count - 1
            cb_props.receiver_index = index
        elif operate == 'REM':
            list.remove(index)
            index = min(max(0, index - 1), count - 1)
            cb_props.receiver_index = index

            max_index = len(list) - 1
            if cb_props.background_index > max_index:
                cb_props.background_index = -1

            on_receiver_changed(context)

        return {'FINISHED'}

class QueuePromptOperator(bpy.types.Operator):
    bl_idname = "cb.queue_onece"
    bl_label = "Queue Prompt"
    bl_description = "建议给cb.queue_onece添加一个快捷键"

    def execute(self, context):
        if not Connect_Info['isConnected']:
            return {'FINISHED'} # 未连接则不执行
        
        cb_props = context.scene.comfy_bridge_props
        senders = [item for item in cb_props.sender_list if item.enabled]
        receivers = [item for item in cb_props.receiver_list if item.enabled]
        TmpSetting.request_names = [item.text for item in receivers]
        ExecuteQueuePrompt(context, senders, receivers)

        return {'FINISHED'}

class AddProjectionOperator(bpy.types.Operator):
    bl_idname = "cb.add_projection"
    bl_label = "Add Projection"
    bl_description = "Projection texture to active mesh"
    index: bpy.props.IntProperty() # type: ignore

    def execute(self, context):
        cb_props = context.scene.comfy_bridge_props
        receiver = cb_props.receiver_list[self.index]
        image = bpy.data.images.get(receiver.text)
        if not image:
            return {'FINISHED'}

        camera = bpy.context.scene.camera
        if not camera:
            self.report({'ERROR'}, "No camera found in scene or 3D view.")
            return {'FINISHED'}
        
        mode = bpy.context.object.mode
        bpy.ops.object.mode_set(mode='OBJECT')
        
        vp_matrix, is_ortho, view_matrix, proj_matrix = GetCameraVPMatrix(camera)
        camera_pos, camera_dir = GetViewVector(camera)

        active_obj = bpy.context.active_object
        if active_obj and active_obj.type == 'MESH':
            props = active_obj.projection_props
            if not props.enabled:
                CreateProjectionTexture(active_obj, vp_matrix, camera_pos, camera_dir, is_ortho, image)
                props.display = True
            else:
                self.report({'ERROR'}, "Projection is already enabled")

        bpy.ops.object.mode_set(mode=mode)    
        return {'FINISHED'}

class RemoveProjectionOperator(bpy.types.Operator):
    bl_idname = "cb.remove_projection"
    bl_label = "Remove Projection"
    bl_description = "Remove projection texture from active mesh"

    def execute(self, context):
        active_obj = context.active_object
        if not active_obj or active_obj.type != 'MESH':
            return {'FINISHED'}
        
        remove_geometry_node(active_obj, 'CameraProjection')

        props = active_obj.projection_props
        props.enabled = False
        if all(mat.text in bpy.data.materials for mat in props.origin_materials) and len(props.origin_materials) == len(active_obj.data.materials):
            active_obj.data.materials.clear()
            for mat in props.origin_materials:
                if mat.text == "":
                    continue
                origin_mat = bpy.data.materials.get(mat.text)
                if origin_mat and origin_mat.node_tree:
                    weight_node = next((node for node in origin_mat.node_tree.nodes 
                                    if node.label == "Use_Projection"), None)
                    if weight_node:
                        weight_node.outputs[0].default_value = 0
                    active_obj.data.materials.append(origin_mat)
        else:
            active_obj.data.materials.clear()
            active_obj.data.materials.append(bpy.data.materials.new(name="Default_Material"))
            
        return {'FINISHED'}    

class BakeTextureOperator(bpy.types.Operator):
    bl_idname = "cb.bake_texture"
    bl_label = "Bake Texture"
    bl_description = "Bake texture"

    def execute(self, context):
        active_obj = context.active_object
        if not active_obj or active_obj.type != 'MESH':
            return {'FINISHED'}
        
        if not active_obj.active_material:
            self.report({'ERROR'}, "Active object has no material to bake")
            return {'FINISHED'}
        
        props = active_obj.projection_props

        mode = bpy.context.object.mode
        bpy.ops.object.mode_set(mode='OBJECT')
        
        def on_bake_finished(pack):
            bpy.ops.object.mode_set(mode=mode)
            obj = pack['obj']
            image = pack['image']
            if obj == active_obj:
                EventMan.Remove('gpu_baker_done', on_bake_finished)
                material = obj.active_material
                base_texture_node = next((node for node in material.node_tree.nodes 
                                  if node.label == "Base Texture"), None)
                if base_texture_node:
                    base_texture_node.image = image

                weight_node = next((node for node in material.node_tree.nodes 
                                  if node.label == "Use_Projection"), None)
                if weight_node:
                    weight_node.outputs[0].default_value = 0

                props.enabled = False
                remove_geometry_node(obj, 'CameraProjection')
        
        size = int(props.bake_size)
        EventMan.Add('gpu_baker_done', on_bake_finished)
        StartBake(active_obj, size)

        return {'FINISHED'}

class Resume_CameraOperator(bpy.types.Operator):
    bl_idname = "cb.resume_camera"
    bl_label = "Resume Camera"
    bl_description = "Resume Camera"

    def execute(self, context):
        camera = context.scene.camera
        if not camera:
            return {'FINISHED'}
        
        cb_props = context.scene.comfy_bridge_props
        receiver = cb_props.receiver_list[cb_props.receiver_index]
        if receiver.camera_mark:
            camera.location = receiver.location
            camera.rotation_euler = receiver.rotation
            camera.data.angle = receiver.fov

        return {'FINISHED'}

class SenderList(bpy.types.UIList):
    bl_idname = "CB_UL_SENDER_LIST"
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row()
        row.label(icon='OUTLINER_COLLECTION', text="Collection")  # 添加图标
        row.prop(item, "collection_name", text="")
        row.prop(item, "enabled", text="")

class ReceiverList(bpy.types.UIList):
    bl_idname = "CB_UL_RECEIVER_LIST"
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        in_camera_view = is_in_camera(context)
        
        cb_props = context.scene.comfy_bridge_props
        row = layout.row()
        row.label(icon='IMAGE_DATA')  # 添加图标
        row.prop(item, "text", text="", emboss=False)
        
        if in_camera_view:  
            icon = 'OUTLINER_OB_IMAGE' if cb_props.background_index == index else 'IMAGE_BACKGROUND'
            row.prop(item, "show_background", text="", icon=icon, toggle=True)
            
            show_projection = False
            active_obj = context.active_object
            if active_obj and active_obj.type == 'MESH':
                props = active_obj.projection_props
                if not props.enabled:
                    show_projection = True

            if show_projection: 
                row.operator(AddProjectionOperator.bl_idname, icon='MOD_UVPROJECT', text="").index = index
        
        row.prop(item, "enabled", text="")

class TestOperator(bpy.types.Operator):
    bl_idname = "cb.test"
    bl_label = "Test"
    bl_description = "Test"

    def execute(self, context):
        Test(context)
        return {'FINISHED'}

class ComfyBridgePanel(bpy.types.Panel):
    bl_label = 'cÖmfyBridge'
    bl_idname = "COMFY_PT_BRIDGE_PANEL"
    bl_space_type = 'VIEW_3D'
    bl_region_type= 'UI'
    bl_category = 'cÖmfyBridge'

    def draw_header_preset(self, context): 
        layout = self.layout
        row= layout.row()
        row.operator('wm.url_open', text = '', icon = 'HOME').url = "https://github.com/robtl2/ComfyBridge-Blender-beta"

    def draw(self, context):
        layout = self.layout
        cb_props = context.scene.comfy_bridge_props

        row = layout.row()
        if not Connect_Info['isConnected']:
            row.prop(cb_props, 'server_host', text='ServerIP')
        else:
            info = f'Connected to {cb_props.server_host}'
            if Connect_Info['isClosing']:
                info = ' Disconnecting...'
            row.label(text=info)


        icon = "LINKED" if Connect_Info['isConnected'] else "UNLINKED"
        row.operator(ConnectOperator.bl_idname, text='', icon=icon, depress=Connect_Info['isConnected'])

        if Connect_Info['isConnected']:
            row = layout.row()
            row.operator(QueuePromptOperator.bl_idname, text=QueuePromptOperator.bl_label) 

        col = layout.column()
        row = col.row()
        icon = 'DOWNARROW_HLT' if cb_props.show_senders else 'RIGHTARROW'
        row.prop(cb_props, "show_senders", text="Send to ImageReceive੭˚⁺", emboss=False, icon=icon)
        if cb_props.show_senders:
            col.prop(cb_props, 'resolution')

            if cb_props.resolution == 'custom':
                row = col.row()
                row.prop(cb_props, 'custom_resolution_x', text='Width')
                row.prop(cb_props, 'custom_resolution_y', text='Height')

            row = col.row()
            row.template_list(SenderList.bl_idname,"", cb_props, "sender_list", cb_props, "sender_index", rows=2)

            col = row.column(align=True)
            col.operator(SenderOperator.bl_idname, icon='ADD', text="").option = 'ADD'
            col.operator(SenderOperator.bl_idname, icon='REMOVE', text="").option = 'REM'
            
            sender_prop = None
            if len(cb_props.sender_list)>0:
                sender_prop = cb_props.sender_list[cb_props.sender_index]
            if sender_prop and sender_prop.enabled: 
                collection_name = sender_prop.collection_name
                box = layout.box()
                
                row = box.row()
                split = row.split(factor=0.7)  # 70% 给左边的label, 30% 给右边的more按钮
                split.label(text=f'ImageReceive੭˚⁺ input name')
                split.prop(sender_prop, "output_more", text="more", icon='MOD_OPACITY', toggle=True)
                
                row = box.row()
                row.prop(sender_prop, "output_viewport", text=f"{collection_name}_C")
                if sender_prop.output_viewport:
                    row.prop(sender_prop, "samples", text="samples")
                
                if sender_prop.output_more:   
                    row = box.row()
                    row.prop(sender_prop, "output_depth", text=f"{collection_name}_D")
                    row.prop(sender_prop, "output_normal", text=f"{collection_name}_N")
                    row.prop(sender_prop, "output_lineart", text=f"{collection_name}_L")


        col = layout.column()
        row = col.row()
        icon = 'DOWNARROW_HLT' if cb_props.show_receiver else 'RIGHTARROW'
        row.prop(cb_props, "show_receiver", text="Receive from ImageSende੭⁺˚", emboss=False, icon=icon)
        if cb_props.show_receiver:
            row = col.row()
            row.template_list(ReceiverList.bl_idname,"", cb_props, "receiver_list", cb_props, "receiver_index", rows=2)

            col = row.column(align=True)
            col.operator(ReceiverOperator.bl_idname, icon='ADD', text="").option = 'ADD'
            col.operator(ReceiverOperator.bl_idname, icon='REMOVE', text="").option = 'REM'

            if cb_props.background_index != -1 and is_in_camera(context):
                camera = context.scene.camera
                row = layout.row()
                prop = camera.data.background_images[0]
                split = row.split(factor=0.6)  # Adjust the factor to control the width of the alpha slider
                split.prop(prop, "alpha", text="Opacity", slider=True)
                split.row().prop(prop, "display_depth", expand=True)
                row.operator(Resume_CameraOperator.bl_idname, text="", icon='SCREEN_BACK')
                

        active_obj = context.active_object
        if active_obj and active_obj.type == 'MESH':
            props = active_obj.projection_props
            if props.enabled:
                col = layout.column()
                row = col.row()
                icon = 'DOWNARROW_HLT' if props.show else 'RIGHTARROW'
                row.prop(props, "show", text="Projection", emboss=False, icon=icon)

                if props.show:
                    box = col.box()
                    row = box.row()
                    row.label(text=f'Projection on "{active_obj.name}"')
                    icon = 'OUTLINER_OB_LIGHT' if props.display else 'LIGHT_DATA'
                    row.prop(props, "display", text="", icon=icon, toggle=True)
                    row.operator(RemoveProjectionOperator.bl_idname, text="", icon='TRASH')
                    row = box.row()
                    row.prop(props, "offset", text="Offset", slider=True)
                    row.prop(props, "blend", text="Blend", slider=True)
                    box = col.box()
                    box.label(text='Bake to Texture')
                    row = box.row()
                    split = row.split(factor=0.5)  # Adjust the factor to control the width
                    col = split.column()
                    col.prop(props, "bake_size", text="Size:")
                    col = split.column()  # Use the remaining space for the button
                    col.operator(BakeTextureOperator.bl_idname, text="Bake")
                    
classes = (
    ComfyBridgePanel, QueuePromptOperator, TestOperator, CBPreferences, 
    ConnectOperator, SenderOperator, ReceiverOperator, Resume_CameraOperator,
    AddProjectionOperator, BakeTextureOperator, RemoveProjectionOperator,
    SenderList, ReceiverList, SimpleNameGroup,
    ReceiverNameGroup, SenderNameGroup, CBProps, ProjectionProps
)

def draw_comfybridge_info(): 
    cb_props = bpy.context.scene.comfy_bridge_props
    if not cb_props.show_info:
        return

    progress = cb_props.progress

    if not Connect_Info['isConnected']:
        return
    
    info = 'cÖmfyBridge connected'
    
    region = None
    
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            for region in area.regions:
                if region.type == 'WINDOW':
                    region = region
                    break

    if region is None:
        return
    
    # 设置文字属性
    font_id = 0
    
    blf.color(font_id, 1, 1, 1, 1)

    if progress>0:
        blf.size(font_id, 12)
        progress_int = int(progress * 40)
        
        text = f"{'█' * progress_int}{'░' * (40 - progress_int)}"
        
        # 计算文字宽度以实现居中
        text_width, _ = blf.dimensions(font_id, text)
        
        # 计算文字位置 (底部居中)
        x = (region.width - text_width) / 2  # 水平居中
        y = 12  # 距离底部60像素
        
        # 绘制文字
        blf.position(font_id, x, y, 0)
        blf.enable(font_id, blf.SHADOW)  # 启用阴影
        blf.shadow(font_id, 5, 0.0, 0.0, 0.0, 1.0)  # 设置阴影
        blf.shadow_offset(font_id, 1, -1)
        blf.draw(font_id, text)

    blf.size(font_id, 24)
    text = cb_props.info if cb_props.info != '' else info

    text_width, _ = blf.dimensions(font_id, text)
    x = (region.width - text_width) / 2  # 水平居中
    y = 36  # 距离底部60像素
    blf.position(font_id, x, y, 0)
    blf.enable(font_id, blf.SHADOW)  # 启用阴影
    blf.shadow(font_id, 5, 0.0, 0.0, 0.0, 1.0)  # 设置阴影
    blf.shadow_offset(font_id, 1, -1)
    blf.draw(font_id, text)


def register():
    bpy.app.handlers.load_pre.append(do_disconnect)

    if not hasattr(bpy.types.SpaceView3D, "cb_draw_handler"):
        bpy.types.SpaceView3D.cb_draw_handler = bpy.types.SpaceView3D.draw_handler_add(
            draw_comfybridge_info, (), 'WINDOW', 'POST_PIXEL'
        )
    
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Object.projection_props = bpy.props.PointerProperty(type=ProjectionProps)
    bpy.types.Scene.comfy_bridge_props = bpy.props.PointerProperty(type=CBProps)
    

def unregister():
    do_disconnect()

    del bpy.types.Object.projection_props
    del bpy.types.Scene.comfy_bridge_props

    for cls in classes:
        bpy.utils.unregister_class(cls)

    # 确保在卸载插件时移除 draw handler
    if hasattr(bpy.types.SpaceView3D, "cb_draw_handler"):
        bpy.types.SpaceView3D.draw_handler_remove(bpy.types.SpaceView3D.cb_draw_handler, 'WINDOW')
        del bpy.types.SpaceView3D.cb_draw_handler

if __name__ == "__main__":
    register()
 