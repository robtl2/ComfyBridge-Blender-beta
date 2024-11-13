"""
与comfyUI那边的comfyBridge通信的client
"""

import socket
from .event import EventMan
import threading
import time



'''
-------------------------------------------------------------
--OpCodes--
'''
HANDSHAKE = 101
HEARTBEAT = 102

SEND_IMAGE = 201
REQUEST_IMAGE = 202
QUEUE_PROMPT = 203
RESPONSED_IMAGE = 204

PROGRESS = 301

ERROR = 404
OK = 666
'''
-------------------------------------------------------------
'''

Connect_Info = {
    'isConnected': False,
    'isClosing': False,
    'isConnecting': False
}

_connected = False

op_lock = threading.Lock()
op_queues = []
client_socket = None
client_thread = None

reader_lock = threading.Lock()
writer_lock = threading.Lock()

def connectToComfyBridge(host, port):
    global client_socket
    try:
        if Connect_Info['isConnected'] or client_socket is not None:
            return False
        
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.connect((host, port))
        return True
    except Exception as e:
        print(f'Error in connectToComfyBridge: {e}')
        return False

def sendInt(opCode):
    if not _connected or client_socket is None:
        return
    with writer_lock:
        client_socket.sendall(opCode.to_bytes(4, byteorder='big'))

def sendString(string):
    if not _connected or client_socket is None:
        return
    string_bytes = string.encode('utf-8')
    length_bytes = len(string_bytes).to_bytes(4, byteorder='big')
    with writer_lock:
        client_socket.sendall(length_bytes)
        client_socket.sendall(string_bytes)

def sendImage(image_data):
    if not _connected or client_socket is None:
        return
    image_length_bytes = len(image_data).to_bytes(4, byteorder='big')
    with writer_lock:
        client_socket.sendall(image_length_bytes)
        client_socket.sendall(image_data)

def receiveInt():
    if not _connected or client_socket is None:
        return ERROR
    with reader_lock:
        int_bytes = client_socket.recv(4)
        return int.from_bytes(int_bytes, byteorder='big')

def receiveString():
    if not _connected or client_socket is None:
        return ERROR
    
    length = receiveInt()
    
    with reader_lock:
        string_bytes = client_socket.recv(length)
    result = string_bytes.decode('utf-8')
    return result

def receiveImage():
    if not _connected or client_socket is None:
        return ERROR
    
    image_length = receiveInt()
    with reader_lock:   
        image_data = b''
        while len(image_data) < image_length:
            packet = client_socket.recv(min(4096, image_length - len(image_data)))
            image_data += packet
    return image_data

def heartbeat():
    step = 0.5
    delay = 10
    
    def delayDo():
        tick = 0
        while _connected:
            time.sleep(step)
            tick += step
            if not _connected:
                return
            if tick >= delay:
                sendInt(HEARTBEAT)
                tick = 0
                return

    threading.Thread(target=delayDo).start()


'''
-------------------------------------------------------------
--Operations--
'''
def op_sendImages(names, image_datas):
    if len(names) != len(image_datas):
        return False
    
    sendInt(SEND_IMAGE)
    sendInt(len(names))

    for i in range(len(names)):
        sendString(names[i])
        sendImage(image_datas[i])

def op_sendRequestNames(names):
    sendInt(REQUEST_IMAGE)
    sendInt(len(names))
    for name in names:
        sendString(name)

def op_queuePrompt():
    sendInt(QUEUE_PROMPT)

def addOperation(op, *args):
    global op_queues
    with op_lock:
        op_queues.append({'op':op, 'args':args})

'''
-------------------------------------------------------------
--socket loop--
'''
def sender_loop():
    global _connected
    while _connected:
        try:
            with op_lock:
                if len(op_queues) > 0:
                    operation = op_queues.pop(0)
                    op = operation['op']
                    args = operation['args']
                    op(*args)
                else:
                    time.sleep(0.025)
        except Exception as e:
            _connected = False
            print(f'~~~~~~~~~sender error:{e}')

def receiver_loop():
    global _connected
    while _connected:
        try:
            code = receiveInt()
            if code == HEARTBEAT:
                heartbeat()
            elif code == RESPONSED_IMAGE:
                name = receiveString()
                image_data = receiveImage()
                is_ok = receiveInt()
                if is_ok == OK:
                    EventMan.Trigger('on_image_received', {'name':name, 'data':image_data})
                else:
                    print(f'~~~~~~~~~receive image error:{is_ok}')
            elif code == PROGRESS:
                progress = receiveInt()
                max = receiveInt()
                EventMan.Trigger('on_progress', {'progress':progress, 'max':max})
            elif code == OK:
                continue
            elif code == ERROR:
                print(f'~~~~~~~~~receive error:{code}')
                _connected = False
            else:
                print(f'~~~~~~~~~unknown operation:{code}')
                time.sleep(1)
        except Exception as e:
            _connected = False
            print(f'~~~~~~~~~receive error:{e}')

def client_loop(host, port):
    global _connected
    global op_queues
    Connect_Info['isConnecting'] = True

    _connected = False
    if not connectToComfyBridge(host, port):
        return
    _connected = True

    sendInt(HANDSHAKE)
    opCode = receiveInt()

    sender_thread = threading.Thread(target=sender_loop)
    receiver_thread = threading.Thread(target=receiver_loop)
    if opCode == HANDSHAKE:
        print('ComfyBridge Handshake success')
        Connect_Info['isConnected'] = True
        Connect_Info['isConnecting'] = False

        sendInt(HEARTBEAT)

        sender_thread.start()
        receiver_thread.start()
    else:
        print('ComfyBridge Handshake failed')
        return
    
    sender_thread.join()
    receiver_thread.join()

    Connect_Info['isConnected'] = False
    Connect_Info['isClosing'] = False
    EventMan.stop()
    print('~~~~~~~~~Disconnected')

'''
-------------------------------------------------------------
--Public Functions--
'''
def Connect(host, port=17777):
    global client_thread
    client_thread = threading.Thread(target=client_loop, args=(host, port))
    client_thread.daemon = True
    client_thread.start()

def Disconnect():
    global _connected
    global client_thread
    global client_socket
    _connected = False
    Connect_Info['isClosing'] = True

    if client_socket is not None:
        client_socket.close()
        client_socket = None

    if client_thread is not None:
        client_thread.join()
        client_thread = None

def SendImages(image_names, image_datas):
    addOperation(op_sendImages, image_names, image_datas)

def SendRequestNames(names):
    addOperation(op_sendRequestNames, names)

def QueuePrompt():
    addOperation(op_queuePrompt)


