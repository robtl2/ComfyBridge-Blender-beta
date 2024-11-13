import bpy

class TmpSetting():
    '''
    记录在渲染过程中需要改动和恢复的设置
    '''

    render_filepath = ''
    file_format = 'PNG'
    color_mode = 'RGB'
    film_transparent = False
    viewport_samples = 1

    collection_names = []
    request_names = []
    collections = {}

    area_3D = None
    space_3D = None
    space_2D = None
    show_overlays = True

    @classmethod
    def record(cls):
        
        def record_render_settings():
            cls.render_filepath = bpy.context.scene.render.filepath
            cls.viewport_samples = bpy.context.scene.eevee.taa_samples
            cls.file_format = bpy.context.scene.render.image_settings.file_format
            cls.color_mode = bpy.context.scene.render.image_settings.color_mode
            cls.film_transparent = bpy.context.scene.render.film_transparent

            bpy.context.scene.render.image_settings.file_format = 'PNG'
            bpy.context.scene.render.image_settings.color_mode = 'RGB'
            bpy.context.scene.render.film_transparent = False

        def record_collection_settings():
            cb_props = bpy.context.scene.comfy_bridge_props
            
            cls.collections = {}
            for collection in bpy.data.collections:
                cls.collections[collection.name] = {
                    'collection': collection,
                    'hide': collection.hide_viewport
                }
            
            cls.collection_names = [item.collection_name for item in cb_props.sender_list if item.enabled]
            for name in cls.collection_names:
                collection = cls.collections.get(name)
                if collection:
                    collection['collection'].hide_viewport = False

        def record_viewport_settings():
            cls.area_3D = None
            cls.space_3D = None
            cls.space_2D = None
            cls.show_overlays = True
            for area in bpy.context.window.screen.areas:
                if area.type == 'VIEW_3D':
                    cls.area_3D = area
                    cls.space_3D = area.spaces.active
                    cls.show_overlays = cls.space_3D.overlay.show_overlays
                    cls.space_3D.overlay.show_overlays = False  
                if area.type == 'IMAGE_EDITOR':
                    cls.space_2D = area.spaces.active

        record_render_settings()
        record_collection_settings()
        record_viewport_settings()
        
    @classmethod
    def restore(cls):
        def restore_render_settings():
            bpy.context.scene.eevee.taa_samples = cls.viewport_samples
            bpy.context.scene.render.filepath = cls.render_filepath
            bpy.context.scene.render.image_settings.file_format = cls.file_format
            bpy.context.scene.render.image_settings.color_mode = cls.color_mode
            bpy.context.scene.render.film_transparent = cls.film_transparent
            bpy.context.scene.comfy_bridge_props.show_info = True

        def restore_collection_settings():
            for name in cls.collection_names:
                collection = cls.collections.get(name)
            if collection:
                collection['collection'].hide_viewport = collection['hide']

        def restore_viewport_settings():
            if cls.space_3D:
                cls.space_3D.overlay.show_overlays = cls.show_overlays

        restore_render_settings()
        restore_collection_settings()
        restore_viewport_settings()
            