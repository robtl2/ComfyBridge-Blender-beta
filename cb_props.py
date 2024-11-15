import bpy
from .queue_prompt import on_receiver_changed

class SenderNameGroup(bpy.types.PropertyGroup):
    collection_name: bpy.props.EnumProperty(
        name="Collection",
        items= lambda self, context: [(col.name, col.name, "") for col in bpy.data.collections],
        description="Select a collection"
    ) # type: ignore
    samples: bpy.props.IntProperty(
        name='samples', 
        default=1, 
        min=1,
        description='Temp EEVEE viewport samples for color channel'
    )# type: ignore

    output_viewport: bpy.props.BoolProperty(
        default=True,
        description='Output color channel to comfyUI'
    ) # type: ignore

    output_more: bpy.props.BoolProperty(default=False) # type: ignore
    output_depth: bpy.props.BoolProperty(
        default=False,
        description='Output depth channel to comfyUI'
    ) # type: ignore
    output_normal: bpy.props.BoolProperty(
        default=False,
        description='Output normal channel to comfyUI'
    ) # type: ignore
    output_lineart: bpy.props.BoolProperty(
        default=False,
        description='Output lineart channel to comfyUI'
    ) # type: ignore
    output_mask: bpy.props.BoolProperty(
        default=False,
        description='Output mask channel to comfyUI'
    ) # type: ignore
    
    enabled: bpy.props.BoolProperty(default=True) # type: ignore

class ReceiverNameGroup(bpy.types.PropertyGroup):
    _updating = False # 避免show_background互斥回调

    def on_text_changed(self, context):
        on_receiver_changed(context)

    text: bpy.props.StringProperty(update=on_text_changed)# type: ignore

    def on_show_background_toggled(self, context):  
        if ReceiverNameGroup._updating:
            return
        ReceiverNameGroup._updating = True

        try:
            cb_props = context.scene.comfy_bridge_props

            for i, receiver in enumerate(cb_props.receiver_list):
                if receiver.text == self.text:
                    cb_props.background_index = i if self.show_background else -1
                else:
                    receiver.show_background = False
            
            camera = context.scene.camera
            if not camera:
                return

            id = cb_props.background_index
            if id == -1:
                camera.data.show_background_images = False
                return 

            image = bpy.data.images.get(self.text)
            if not image:
                return 
            
            camera.data.show_background_images = True
            if len(camera.data.background_images) == 0:
                camera.data.background_images.new()
            camera.data.background_images[0].image = image
                
        finally:
            ReceiverNameGroup._updating = False

    # 是否显示背景
    show_background: bpy.props.BoolProperty(
        default=False, 
        update=on_show_background_toggled
    ) # type: ignore

    camera_mark: bpy.props.BoolProperty(default=False) # type: ignore
    
    # 记录相机位置
    location: bpy.props.FloatVectorProperty(
        name="Camera Location",
        description="Location of the camera",
        default=(0.0, 0.0, 0.0),
        size=3  # 3D空间中的x, y, z坐标
    )# type: ignore

    # 记录相机旋转
    rotation: bpy.props.FloatVectorProperty(
        name="Camera Rotation",
        description="Rotation of the camera in Euler angles",
        default=(0.0, 0.0, 0.0),
        size=3  # 3D空间中的x, y, z旋转
    )# type: ignore

    fov: bpy.props.FloatProperty(
        name="FOV",
        description="Field of view of the camera",
        default=45.0,
        min=0.1,
        max=179.9
    )# type: ignore

    enabled: bpy.props.BoolProperty(
        default=True,
        update=on_text_changed
    ) # type: ignore

class SimpleNameGroup(bpy.types.PropertyGroup):
    text: bpy.props.StringProperty()# type: ignore

class ProjectionProps(bpy.types.PropertyGroup):
    enabled: bpy.props.BoolProperty(default=False) # type: ignore

    show: bpy.props.BoolProperty(default=True) # type: ignore

    def on_display_toggled(self, context):
        active_obj = context.active_object
        if active_obj and active_obj.type == 'MESH':
            material = active_obj.active_material
            display_node = next((node for node in material.node_tree.nodes
                                  if node.label == "Use_Projection"), None)
            if display_node:
                display_node.outputs[0].default_value = 1 if self.display else 0
    
    display: bpy.props.BoolProperty(
        default=True,
        update=on_display_toggled
    ) # type: ignore

    origin_materials: bpy.props.CollectionProperty(
        type = SimpleNameGroup
    ) # type: ignore

    bake_size_list = [
        ('512', '512', ''),
        ('1024', '1024', ''),
        ('2048', '2048', ''),
        ('4096', '4096', ''),
    ]

    bake_size: bpy.props.EnumProperty(
        items=bake_size_list,
        default='1024',
        name="bake size",  
        description='Bake Size',
    ) # type: ignore
    
    def on_offset_changed(self, context):
        active_obj = context.active_object
        if active_obj and active_obj.type == 'MESH':
            material = active_obj.active_material
            offset_node = next((node for node in material.node_tree.nodes
                                  if node.label == "Blend_Offset"), None)
            if offset_node:
                offset_node.outputs[0].default_value = self.offset

    def on_blend_changed(self, context):
        active_obj = context.active_object
        if active_obj and active_obj.type == 'MESH':
            material = active_obj.active_material
            blend_node = next((node for node in material.node_tree.nodes
                                  if node.label == "Blend_Range"), None)
            if blend_node:
                blend_node.outputs[0].default_value = self.blend

    # 偏移量
    offset: bpy.props.FloatProperty(
        name="offset",
        description="blend area offset",
        default=0.0,
        min=-1.0,
        max=1.0,
        update=on_offset_changed
    ) # type: ignore

    blend: bpy.props.FloatProperty(
        name="blend",
        description="blend area size",
        default=0.1,
        min=0.01,
        max=1.0,
        update=on_blend_changed
    ) # type: ignore

class CBProps(bpy.types.PropertyGroup):

    server_host: bpy.props.StringProperty(
        name = 'Server Host', default = '127.0.0.1',
    ) # type: ignore

    show_info: bpy.props.BoolProperty(
        name = '', default=True,
    ) # type: ignore

    info: bpy.props.StringProperty(
        name = '', default = '',
    ) # type: ignore

    progress: bpy.props.FloatProperty(
        name="Progress",
        description="Progress of the current operation",
        default=0.0,
        min=0.0,
        max=1.0
    ) # type: ignore

    show_senders: bpy.props.BoolProperty(
        name = '', default=True,
    ) # type: ignore

    background_index: bpy.props.IntProperty(
        default=-1,
    ) # type: ignore

    resolution_names = [
        ('768,768', '768 x 768 (XL square)', ''),
        ('1024,1024', '1024 x 1024 (XL square)', ''),
        ('1216,1216', '1216 x 1216 (XL square)', ''),
        ('1344,768', '1344 x 768 (XL landscape)', ''),
        ('1216,832', '1216 x 832 (XL landscape)', ''),
        ('1152,896', '1152 x 896 (XL landscape)', ''),
        ('896,1152', '896 x 1152 (XL portrait)', ''),
        ('832,1216', '832 x 1216 (XL portrait)', ''),
        ('768,1344', '768 x 1344 (XL portrait)', ''),
        ('512,512', '512 x 512 (SD15 square)', ''),
        ('640,640', '640 x 640 (SD15 square)', ''),
        ('768,512', '768 x 512 (SD15 landscape)', ''),
        ('768,640', '768 x 640 (SD15 landscape)', ''),
        ('512,768', '512 x 768 (SD15 portrait)', ''),
        ('640,960', '640 x 960 (SD15 portrait)', ''),
        ('custom', 'custom', ''),
    ]

    def on_resolution_changed(self, context):
        width = self.custom_resolution_x
        height = self.custom_resolution_y
        width = int(width/64)*64
        height = int(height/64)*64
        
        if self.resolution != 'custom':
            width_str, height_str = self.resolution.split(',')
            width = int(width_str)
            height = int(height_str)

        bpy.context.scene.render.resolution_x = width
        bpy.context.scene.render.resolution_y = height
        print("set resolution: ",width, height)

    resolution: bpy.props.EnumProperty(
        items=resolution_names,
        name="resolution",  
        description='Resolution',
        update=on_resolution_changed,
    ) # type: ignore

    custom_resolution_x : bpy.props.IntProperty(
        default=640,
        update=on_resolution_changed,
        description='会被强制调整为64的倍数',
    )# type: ignore
    custom_resolution_y : bpy.props.IntProperty(
        default=640,
        update=on_resolution_changed,
        description='会被强制调整为64的倍数',
    )# type: ignore

    show_receiver: bpy.props.BoolProperty(
        name = '', default=True,
    ) # type: ignore

    sender_index: bpy.props.IntProperty(
        description='快速渲染Collection并发送向ComfyUI',
    ) # type: ignore
    sender_list: bpy.props.CollectionProperty(
        type = SenderNameGroup
    ) # type: ignore

    receiver_index: bpy.props.IntProperty(
        description='接收ComfyUI的渲染结果到图像的名称',
    ) # type: ignore
    receiver_list: bpy.props.CollectionProperty(
        type = ReceiverNameGroup
    ) # type: ignore

    keep_queueing: bpy.props.BoolProperty(
        name = 'Keep Queueing', default=False, description='Keep Queueing for Realtime Repainting.\n ! Not recommended yet !'
    ) # type: ignore
    