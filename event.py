"""
习惯了用自己写的事件系统, 简单有用就够了
不同thread间互相传也不会要人命
"""

import bpy
import queue

FPS = 30

class EventMan:
    is_running = False
    delay = 1.0 / FPS
    event_dict = {}
    GLOBAL_LISTENER = 'GlobalListener'
    event_queue = queue.Queue()  # Thread-safe queue for events

    @classmethod
    def clear(cls):
        cls.event_dict = {}

    @classmethod
    def process_events(cls):
        delay_events = []
        while not cls.event_queue.empty():
            event_name, args, target = cls.event_queue.get()
            if event_name in cls.event_dict:
                for event in reversed(cls.event_dict[event_name]):
                    if event['listener'] == target or target is None:
                        for handler in event['handler']:
                            if 'delay' in args and args['delay'] > 0:
                                delay_events.append((event_name, args, event['listener']))
                            else:
                                # print(f"trigger event: {event_name}")
                                if event['listener'] == cls.GLOBAL_LISTENER:
                                    handler(args)
                                else:
                                    handler(event['listener'], args)
        
        for event in delay_events:
            event[1]['delay'] -= 1;
            cls.Trigger(*event)
        
        if cls.event_queue.empty() and len(cls.event_dict) == 0:
            cls.stop()
        
        return cls.delay
    
    @classmethod
    def start(cls):
        if cls.is_running:
            return
        
        # print("start event")
        cls.is_running = True
        cls.delay = 1.0 / FPS
        bpy.app.timers.register(EventMan.process_events, first_interval=cls.delay)

    @classmethod
    def stop(cls):
        if not cls.is_running:
            return
        
        # print("stop event")
        cls.is_running = False  
        cls.delay = None
        cls.clear()

    # ------public methods------
    @classmethod
    def Add(cls, event_name, callback, listener=None):
        # print(f"add event: {event_name}")
        if event_name not in cls.event_dict:
            cls.event_dict[event_name] = []

        if listener is None:
            listener = cls.GLOBAL_LISTENER

        registered = False
        for event in cls.event_dict[event_name]:
            if event['listener'] == listener:
                event['handler'].append(callback)
                registered = True
                break

        if not registered:
            cls.event_dict[event_name].append({'listener': listener, 'handler': [callback]})
        
        cls.start()

    @classmethod
    def Remove(cls, event_name, callback, listener=None):
        if listener is None:
            listener = cls.GLOBAL_LISTENER

        if event_name in cls.event_dict:
            for i in range(len(cls.event_dict[event_name]) - 1, -1, -1):
                event_args = cls.event_dict[event_name][i]
                if event_args['listener'] == listener:
                    if callback in event_args['handler']:
                        event_args['handler'].remove(callback)

                    if not event_args['handler']:
                        cls.event_dict[event_name].pop(i)

                    if len(cls.event_dict[event_name]) == 0:
                        cls.event_dict.pop(event_name)

    @classmethod
    def Trigger(cls, event_name, args=None, target=None):
        if event_name in cls.event_dict:
            cls.event_queue.put((event_name, args, target))

    

