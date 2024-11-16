import bpy
from .event import EventMan
from .utils import get_mesh_data_for_gpu
import threading
from .gpu_render import ShaderBatch, OffScreenCommandBuffer
from .utils import GetCameraVPMatrix
from mathutils import Vector
import os
import tempfile

class DepthNormalRenderer:
    def __init__(self, context, collection_name, debug=False):
        self.debug = debug
        cb_props = context.scene.comfy_bridge_props
        resolution = cb_props.resolution
        if resolution == "custom":
            resolution = (cb_props.custom_resolution_x, cb_props.custom_resolution_y)
        else:
            resolution = resolution.split(",")
            resolution = (int(resolution[0]), int(resolution[1]))

        self.vp_matrix, self.is_ortho, self.view_matrix, self.proj_matrix = GetCameraVPMatrix()
        self.mesh_data = {}
        self.size = resolution
        self.collection_name = collection_name
        self.in_loading = False
        self.data_ready = False
        
        collection = bpy.data.collections.get(self.collection_name)
        if collection:
            self.objects = [obj for obj in collection.objects if obj.type == 'MESH']
        else:
            self.objects = []

        min_distance = float('inf')
        max_distance = float('-inf')
        for obj in self.objects:
            bbox_corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
            for corner in bbox_corners:
                distance = (self.view_matrix @ corner).z
                min_distance = min(min_distance, distance)
                max_distance = max(max_distance, distance)

        self.range = (min_distance, max_distance)
        self.objects.sort(key=lambda obj: (self.view_matrix @ obj.location).z)

    def render_depth(self):
        self._request_render(self._render_depth)

    def render_normal(self):
        self._request_render(self._render_normal)

    def render_lineart(self):
        self._request_render(self._render_lineart)

    def render_mask(self):
        self._request_render(self._render_mask) 
        
    #----------------------------------
    '''private methods'''
    def _request_render(self, callback):
        if len(self.objects) == 0:
            return

        if not self.data_ready:
            self._get_mesh_data(callback)
        else:
            callback() 

    def _on_mesh_data_ready(self, listener, data):
        self.mesh_data[data["object"]] = data["data"]

        self.data_ready = True
        for obj in self.objects:
            if obj not in self.mesh_data:
                self.data_ready = False
                break

        if self.data_ready:
            EventMan.Remove("mesh_data_for_gpu_ready", self._on_mesh_data_ready, listener)
            if listener["fn"]:
                listener["fn"]()

    def _get_mesh_data(self, callback):
        EventMan.Add("mesh_data_for_gpu_ready", self._on_mesh_data_ready, {"fn": callback})

        if self.in_loading:
            return

        self.in_loading = True

        def get_mesh_data_thread(obj, eval_mesh, eval_mesh_data):
            data = get_mesh_data_for_gpu(eval_mesh, eval_mesh_data)
            EventMan.Trigger("mesh_data_for_gpu_ready", {"object": obj, "data": data})

        for obj in self.objects:
            # 这一步丢thread里会在非Camera视图时闪退
            depsgraph = bpy.context.evaluated_depsgraph_get()
            eval_mesh = obj.evaluated_get(depsgraph)
            eval_mesh_data = eval_mesh.data

            thread = threading.Thread(
                target=get_mesh_data_thread,
                args=(obj, eval_mesh, eval_mesh_data, )
            )
            thread.start()

    def _encode_png(self, image_name, buffer):
        if image_name not in bpy.data.images:
            bpy.data.images.new(image_name, self.size[0], self.size[1])
        image = bpy.data.images[image_name]
        image.scale(self.size[0], self.size[1])
        image.pixels = [v / 255 for v in buffer]
        tmp_path = os.path.join(tempfile.gettempdir(), f'{image_name}.png')
        image.filepath_raw = tmp_path
        image.file_format = 'PNG'
        image.save()

        def encode_png_thread():
            with open(tmp_path, 'rb') as f:
                image_data = f.read()
                
            if not self.debug:
                os.remove(tmp_path)
            EventMan.Trigger("image_ready_to_send", {"name": image_name, "data": image_data, "cleanup": not self.debug, "image": image})

        thread = threading.Thread(target=encode_png_thread)
        thread.start()

    def _render_depth(self):
        depth_vs = open("./glsl/depth.vs").read()
        depth_fs = open("./glsl/depth.fs").read()   

        depth_batch = ShaderBatch()
        depth_batch.define_shader(
            "depth",
            uniforms = [
                ('MAT4', 'vpMatrix', self.vp_matrix),
                ('MAT4', 'vMatrix', self.view_matrix),
                ('VEC2', 'range', self.range)
            ], 
            vert_in={
                'pos':'VEC3'
            }, 
            vert_out={
                'posView':'VEC3'
            }, 
            frag_out={
                'FragColor':'VEC4'
            }, 
            vs=depth_vs, 
            fs=depth_fs
        )

        for obj in self.objects:
            mesh_data = self.mesh_data[obj]
            depth_batch.add_batch(
                "depth",
                {
                    'pos': mesh_data['pos'],
                }, 
                indices=mesh_data['indices'],
                matrix=obj.matrix_world
            )

        cmb = OffScreenCommandBuffer(self.size)
        cmb.clear((0,0,0,1))
        cmb.matrix_push()
        cmb.draw(depth_batch)
        cmb.matrix_pop()
        buffer = cmb.execute()

        image_name = f"{self.collection_name}_D"
        self._encode_png(image_name, buffer)

    def _render_normal(self):
        normal_vs = open("./glsl/normal.vs").read()
        normal_fs = open("./glsl/normal.fs").read()

        normal_batch = ShaderBatch()
        normal_batch.define_shader(
            "normal",
            uniforms = [
                ('MAT4', 'vpMatrix', self.vp_matrix),
                ('MAT4', 'vMatrix', self.view_matrix),
            ], 
            vert_in={
                'pos':'VEC3',
                'normal':'VEC3',
            }, 
            vert_out={
                'normalView':'VEC3'
            }, 
            frag_out={
                'FragColor':'VEC4'
            }, 
            vs=normal_vs, 
            fs=normal_fs
        )

        for obj in self.objects:
            mesh_data = self.mesh_data[obj]
            normal_batch.add_batch(
                "normal",
                {
                    'pos': mesh_data['pos'],
                    'normal': mesh_data['normal'],
                }, 
                indices=mesh_data['indices'],
                matrix=obj.matrix_world
            )

        cmb = OffScreenCommandBuffer(self.size)
        cmb.clear((0.5,0.5,1,1))
        cmb.matrix_push()
        cmb.draw(normal_batch)
        cmb.matrix_pop()
        buffer = cmb.execute()

        image_name = f"{self.collection_name}_N"
        self._encode_png(image_name, buffer)

    def _render_lineart(self):
        lineart_vs = open("./glsl/lineart.vs").read()
        lineart_fs = open("./glsl/lineart.fs").read()

        lineart_batch = ShaderBatch()
        lineart_batch.define_shader(
            "lineart",
            uniforms = [
                ('MAT4', 'vpMatrix', self.vp_matrix),
                ('VEC2', 'aspectRatio', (self.size[1] / self.size[0], 1.0)),
            ], 
            vert_in={
                'pos':'VEC4',
                'normal':'VEC4'
            }, 
            vert_out={
                'color_out':'VEC3'
            }, 
            frag_out={
                'FragColor':'VEC4'
            }, 
            vs=lineart_vs, 
            fs=lineart_fs
        )

        for obj in self.objects:
            mesh_data = self.mesh_data[obj]
            pos = [(x, y, z, 0.0) for x, y, z in mesh_data['pos']]
            normal = [(x, y, z, 0.0) for x, y, z in mesh_data['normal']]
            lineart_batch.add_batch(
                "lineart",
                {
                    'pos': pos,
                    'normal': normal,
                }, 
                indices=mesh_data['indices'],
                matrix=obj.matrix_world
            )
            # 试一试两个pass, 嗯，好使
            pos = [(x, y, z, 1.0) for x, y, z in mesh_data['pos']]
            offset = 10.0/self.size[1]
            normal = [(x, y, z, offset) for x, y, z in mesh_data['normal']]
            lineart_batch.add_batch(
                "lineart",
                {
                    'pos': pos,
                    'normal': normal,
                }, 
                indices=mesh_data['indices'],
                matrix=obj.matrix_world,
                culling = 'FRONT',
                depth_write=False
            )

        cmb = OffScreenCommandBuffer(self.size)
        cmb.clear((0,0,0,1))
        cmb.matrix_push()
        cmb.draw(lineart_batch)
        cmb.matrix_pop()
        buffer = cmb.execute()
        
        image_name = f"{self.collection_name}_L"
        self._encode_png(image_name, buffer)

    def _render_mask(self):
        # 就填充个白色，没必要再写一个shader
        lineart_vs = open("./glsl/lineart.vs").read()
        lineart_fs = open("./glsl/lineart.fs").read()

        mask_batch = ShaderBatch()
        mask_batch.define_shader(
            "mask",
            uniforms = [
                ('MAT4', 'vpMatrix', self.vp_matrix),
                ('VEC2', 'aspectRatio', (self.size[1] / self.size[0], 1.0)),
            ], 
            vert_in={
                'pos':'VEC4',
                'normal':'VEC4'
            }, 
            vert_out={
                'color_out':'VEC3'
            }, 
            frag_out={
                'FragColor':'VEC4'
            }, 
            vs=lineart_vs, 
            fs=lineart_fs
        )

        for obj in self.objects:
            mesh_data = self.mesh_data[obj]
            pos = [(x, y, z, 1.0) for x, y, z in mesh_data['pos']]
            normal = [(x, y, z, 0.0) for x, y, z in mesh_data['normal']]
            mask_batch.add_batch(
                "mask",
                {
                    'pos': pos,
                    'normal': normal,
                }, 
                indices=mesh_data['indices'],
                matrix=obj.matrix_world
            )

        cmb = OffScreenCommandBuffer(self.size)
        cmb.clear((0,0,0,1))
        cmb.matrix_push()
        cmb.draw(mask_batch)
        cmb.matrix_pop()
        buffer = cmb.execute()
        
        image_name = f"{self.collection_name}_M"
        self._encode_png(image_name, buffer)
