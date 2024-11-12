"""
简简单单最好了, 复杂了脑壳痛
"""

import bpy
import gpu
from mathutils import Matrix
from gpu_extras.batch import batch_for_shader

class ShaderBatch:
    """
    给blender中gpu shader做一层封装, 
    能让我这种有unity shader开发经验的人上手舒服些

    可以定义多个shader, 多个batch
    类似unity shader的pass ......我都用不上, 干嘛要写这么多呢, 初心都忘记了
    """
    def __init__(self):
        self.shaders = {}
        self.batches = []
        self.uniforms = {}

    def define_shader(self, shader_name, uniforms, vert_in, vert_out, frag_out, vs, fs):
        """
        shader_name: str
        定义shader的名字

        uniforms: list[tuple[str, str, Any]]
        shader的uniform参数

        vert_in: dict[str, str]
        在batch里需要传入的顶点数据

        vert_out: dict[str, str]
        在vs里需要输出的插值数据

        frag_out: dict[str, str]
        在fs里需要输出的片元数据

        vs: str     
        vs代码

        fs: str
        fs代码
        """

        shader_info = gpu.types.GPUShaderCreateInfo()
        vert_out_info = gpu.types.GPUStageInterfaceInfo("interface")

        shader_info.push_constant('MAT4', "modelMatrix")
        
        self.uniforms[shader_name] = {}

        index = 0
        for uniform in uniforms:
            type, name, value = uniform
            self.uniforms[shader_name][name] = value

            if type == "TEX_2D":
                shader_info.sampler(index, 'FLOAT_2D', name)
                index += 1
            else:
                shader_info.push_constant(type, name)

        index = 0
        for key, value in vert_in.items():
            shader_info.vertex_in(index, value, key)
            index += 1

        for key, value in vert_out.items():
            vert_out_info.smooth(value, key)

        index = 0
        for key, value in frag_out.items():
            shader_info.fragment_out(index, value, key)
            index += 1

        shader_info.vertex_out(vert_out_info)
        shader_info.vertex_source(vs)
        shader_info.fragment_source(fs)

        # 创建shader
        # https://projects.blender.org/Brainzman/blender/src/commit/e016c21db1512164c882a7a96f62f900647da653/doc/python_api/examples/gpu.7.py
        # 上面的范例中明明可以直接用vs和fs创建shader的，但我就是测试shader会编译报错，错了个毛线。好气哦，只好用shader_info创建   
        # 给shader_info push个constant还有大小警告，128 bytes?两个mat4就满了，蛇精病一样。UBO合适的参考球都找不到, 摆烂当没看见
        self.shaders[shader_name] = gpu.shader.create_from_info(shader_info)
        del vert_out_info
        del shader_info

    def update_uniform(self, shader_name, name, value):
        """
        更新shader的uniform值, 如果没在define_shader里定义, 则不起作用

        name: str
        需要更新的uniform参数名

        value: Any
        需要更新的uniform值
        """
        if shader_name in self.uniforms:
            self.uniforms[shader_name][name] = value
    
    def add_batch(self, shader_name, content, indices=None, matrix=Matrix.Identity(4), depth_test='LESS_EQUAL', depth_write=True, culling='NONE', blend='NONE'):
        """
        添加一个batch

        shader_name: str
        需要使用的shader名(在define_shader里定义)

        content: dict[str, list[Any]]
        需要绘制的顶点数据, 数据名与类型来自define_shader里的vert_in

        indices: list[(int, int, int)]
        三角面索引

        matrix: Matrix
        模型的local to world矩阵

        depth_test: str
        NONE, ALWAYS, LESS, LESS_EQUAL, EQUAL, GREATER, GREATER_EQUAL

        depth_write: bool

        culling: str 
        NONE, FRONT, BACK

        blend: str
        NONE, ALPHA, ALPHA_PREMULT, ADDITIVE, ADDITIVE_PREMULT, MULTIPLY, SUBTRACT, INVERT
        """

        shader = self.shaders[shader_name]
        batch = batch_for_shader(
            shader, 'TRIS',
            content,
            indices=indices
        )

        self.batches.append({
            "shader_name": shader_name,
            "batch": batch,
            "matrix": matrix,
            "depth_test": depth_test,
            "depth_write": depth_write,
            "culling": culling,
            "blend": blend
        })

    def clear_batches(self):
        self.batches = []

    def draw(self):
        """
        别调用这个, 应该使用OffScreenCommandBuffer里的draw
        """
        if len(self.batches) == 0:
            return
        
        for batch in self.batches:
            shader_name = batch['shader_name']
            shader = self.shaders[shader_name]

            shader.bind()
            shader.uniform_float("modelMatrix", batch["matrix"])
            for key, value in self.uniforms[shader_name].items():
                if isinstance(value, bpy.types.Image):
                    texture = gpu.texture.from_image(value)
                    shader.uniform_sampler(key, texture)
                elif isinstance(value, gpu.types.GPUTexture):
                    shader.uniform_sampler(key, value)
                else:
                    shader.uniform_float(key, value)
            
            gpu.state.depth_test_set(batch["depth_test"])
            gpu.state.depth_mask_set(batch["depth_write"])
            gpu.state.face_culling_set(batch["culling"])
            gpu.state.blend_set(batch["blend"])
            batch["batch"].draw(shader)

class OffScreenCommandBuffer:
    """
    一个简陋的gpu offscreen渲染流程, 现在是用到哪写到哪
    抗锯齿什么的? 人家comfyUI那边在意吗?
    """
    def __init__(self, render_size):
        self.render_size = render_size
        self.offscreen_A = gpu.types.GPUOffScreen(render_size[0], render_size[1])
        self.offscreen_B = gpu.types.GPUOffScreen(render_size[0], render_size[1])
        self.offscreen = self.offscreen_A
        self.commands = []
        self.fb = None

        self.functions = {
            "matrix_push": self._matrix_push,   
            "matrix_pop": self._matrix_pop,
            "clear": self._clear,
            "swap": self._swap,
            "draw": self._draw,
            "fetch": self._fetch 
        }

    def clear(self, color=(0.0, 0.0, 0.0, 0.0)):
        """
        清屏
        这可不是把加了的操作清空的意思
        """
        self.commands.append({
            "fn": "clear",
            "value": color
        })

    def swap(self):
        """
        两个fbo交换着用, 
        避免读写冲突
        """
        self.commands.append({
            "fn": "swap",
            "value": None
        })

    def matrix_push(self, V=Matrix.Identity(4), P=Matrix.Identity(4)):
        self.commands.append({
            "fn": "matrix_push",
            "value": {"V":V, "P":P}
        })

    def matrix_pop(self):
        self.commands.append({
            "fn": "matrix_pop",
            "value": None
        })

    def draw(self, shaderBatch):
        self.commands.append({
            "fn": "draw",
            "value": shaderBatch
        })

    def fetch(self, callback):
        self.commands.append({
            "fn": "fetch",
            "value": callback
        })

    def execute(self):
        """
        执行所有操作, 返回最后画出来的图像buffer
        buffer好啊, 进可留image, 退可转bytes
        """
        self.offscreen.bind()
        self.fb = gpu.state.active_framebuffer_get()

        while len(self.commands) > 0:
            command = self.commands.pop(0)
            self.functions[command["fn"]](command["value"])

        # 不整回来blender的UI搞不好都会画错, 那还不得哭鼻子
        gpu.state.depth_mask_set(False)
        gpu.state.face_culling_set('NONE')
        gpu.state.blend_set('NONE')

        buffer = self.offscreen.texture_color.read()
        buffer.dimensions = self.render_size[0] * self.render_size[1] * 4
        self.offscreen.unbind()
        self.offscreen_A.free()
        self.offscreen_B.free()

        return buffer

    # ------------------------------------------------------------
    '''private functions'''
    def _matrix_push(self, value):
        gpu.matrix.push()
        V, P = value["V"], value["P"]
        gpu.matrix.load_matrix(V)
        gpu.matrix.load_projection_matrix(P)

    def _matrix_pop(self, value=None):
        gpu.matrix.pop()

    def _clear(self, color=(0.0, 0.0, 0.0, 0.0)):
        self.fb.clear(color=color)

    def _swap(self, value=None):
        self.offscreen.unbind()
        self.offscreen = self.offscreen_B if self.offscreen == self.offscreen_A else self.offscreen_A
        self.offscreen.bind()
        self.fb = gpu.state.active_framebuffer_get()

    def _draw(self, shader_batch):
        shader_batch.draw()

    def _fetch(self, callback):
        callback(self.offscreen.texture_color)

    