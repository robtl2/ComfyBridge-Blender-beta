from .comfy_bridge import SendImages, SendRequestNames, QueuePrompt
from .event import EventMan
from .renderTool import RenderCollection
import bpy

def ExecuteQueuePrompt(context, senders, receivers):
    cb_props = context.scene.comfy_bridge_props
    cb_props.info = 'comfyUI in progress...'
    cb_props.progress = 0.01
    undo_steps = bpy.context.preferences.edit.undo_steps
    sender_count = len(senders)
    request_count = len(receivers)

    def send_queue_prompt():
        if request_count > 0:
            bpy.context.preferences.edit.undo_steps = undo_steps
            QueuePrompt()

    def on_render_done(data):
        SendImages(data['names'], data['image_datas'])

        if len(senders) == 0:
            EventMan.Remove("render_complete", on_render_done)
            send_queue_prompt()
        else:
            sender = senders.pop(0)
            RenderCollection(context, sender)

    if request_count > 0:
        def record_camera():
            """
            记录当前摄像机的状态, 方便以后恢复
            """
            camera = context.scene.camera
            if camera:
                pos = camera.location.copy()
                rot = camera.rotation_euler.copy()
                fov = camera.data.angle

                for receiver in receivers:
                    receiver.camera_mark = True
                    receiver.location = pos
                    receiver.rotation = rot
                    receiver.fov = fov

        record_camera()
        request_names = [item.text for item in receivers]
        SendRequestNames(request_names)
    else:
        SendRequestNames(["None"])

    if sender_count > 0:
        bpy.context.preferences.edit.undo_steps = 0
        EventMan.Add("render_complete", on_render_done)
        sender = senders.pop(0)
        RenderCollection(context, sender)
    else:
        send_queue_prompt()

def on_receiver_changed(context):
    cb_props = context.scene.comfy_bridge_props
    receiver_names = [item.text for item in cb_props.receiver_list if item.enabled]
    if len(receiver_names) == 0:
        receiver_names = ["None"]
    SendRequestNames(receiver_names)
    print(f"receiver changed")

