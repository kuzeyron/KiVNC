import pickle
import struct
from io import BytesIO
from pickle import loads
from socket import AF_INET, SOCK_STREAM, socket
from struct import calcsize, unpack
from threading import Thread

from kivy.clock import Clock, mainthread
from kivy.config import Config
from kivy.core.image import Image as CoreImage
from kivy.core.window import Window
from kivy.lang import Builder
from kivy.properties import (BooleanProperty, ListProperty, NumericProperty,
                             ObjectProperty, StringProperty)
# from kivy.uix.scatter import Scatter
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.widget import Widget
from PIL import Image as Pimage

Config.set('input', 'mouse', 'mouse,disable_multitouch')
Window.softinput_mode = "below_target"
Builder.load_string('''
<FeedReceiver>:
    canvas.before:
        Color:
            rgb: 1, 1, 1
        Rectangle:
            texture: self.texture
            size: self.size
            pos: self.pos
        Color:
            rgba: 1, 1, 1, int(self.show_cursor)
        Rectangle:
            size:
                self.cursor_size, \
                self.cursor_size
            pos: self.cursor_pos
            source: self.cursor_icon

<Controllers>:
    pos_hint: {'center_x': .5, 'center_y': .5}
    orientation: 'vertical'
    padding: 5, 5
    spacing: 5

    FeedReceiver:
        id: transport
        host: ('192.168.x.2', 6666)

    BoxLayout:
        id: box
        size_hint_y: .1
        padding: 0, 5

        TextInput:
            multiline: False
            id: message
            pos_hint: {'center_x': .5, 'center_y': .5}
            size_hint_y: .8
            hint_text: 'What to be sent'
            on_text_validate:
                transport.dispatch('on_send_text', self.text)

        Button:
            size_hint_x: .2
            text: 'Send'
            on_release:
                transport.dispatch('on_send_text', message.text)
''')


def coordinates_to_size(cpos, pos, sz, ws, extra=0):
    return (cpos[0] / sz[0] * ws[0] + pos[0],
            ws[1] - cpos[1] / sz[1] * ws[1] + pos[1] - extra)


def size_to_coordinates(pos, sz, ws, extra=0):
    return (pos[0] * sz[0] / ws[0],
            sz[1] - pos[1] * sz[1] / ws[1] - extra)


class Controllers(BoxLayout):
    pass


def server_init(remote=None):
    remote = remote or ('localhost', 4321)
    client = socket(AF_INET, SOCK_STREAM)
    client.connect(remote)

    return client


class FeedReceiver(Widget):
    __events__ = ('on_send_event', 'on_frame', 'on_send_text')
    cursor_icon = StringProperty('assets/icons/cursor.png')
    cursor_pos = ListProperty((0, 0))
    cursor_size = NumericProperty('20dp')
    host = ListProperty()
    show_cursor = BooleanProperty(True)
    texture = ObjectProperty()
    total_size = ListProperty((0, 0))
    aspect_ratio = NumericProperty(1.)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._bytesio = BytesIO()
        self.bind(host=self.setup_handler)
        self.message = {}

    def setup_handler(self, *largs):
        try:
            self.remote, self.port = self.host
            self.input_ = server_init((self.remote, self.port))
            self.output_ = server_init((self.remote, self.port + 1))
            Thread(target=self.data_exchange, daemon=True).start()
        except Exception:
            Clock.schedule_once(self.setup_handler, 1)

    def data_exchange(self):
        payload_size = calcsize("L")
        data = [b'', b'']

        while True:
            data[0] = pickle.dumps(self.message)
            message_size = struct.pack("L", len(data[0]))
            self.output_.sendall(message_size + data[0])

            while len(data[1]) < payload_size:
                data[1] += self.input_.recv(4096)

            packed_msg_size = data[1][:payload_size]
            data[1] = data[1][payload_size:]
            msg_size = unpack("L", packed_msg_size)[0]
            self.message = {}

            while len(data[1]) < msg_size:
                data[1] += self.input_.recv(4096)

            frame_data = data[1][:msg_size]
            data[1] = data[1][msg_size:]

            if content := loads(frame_data):
                self.dispatch('on_frame', content)

    @mainthread
    def on_frame(self, content):
        image, self.cursor = content
        img = Pimage.fromarray(image)
        img.save(self._bytesio, format='jpeg')
        self._bytesio.seek(0)
        self.texture = CoreImage(self._bytesio, ext='jpeg').texture
        self._bytesio.seek(0)
        self._bytesio.flush()

        self.cursor_pos = coordinates_to_size((self.cursor['x'], self.cursor['y']),
                                              self.pos, self.cursor['total_size'],
                                              self.size, self.cursor_size)

    def on_touch_down(self, touch):
        self.dispatch('on_send_event', touch, 1)

    def on_touch_move(self, touch):
        self.dispatch('on_send_event', touch, 3)

    def on_send_event(self, touch, key):
        if self.collide_point(*touch.pos):
            pos = size_to_coordinates(self.to_local(*touch.pos, relative=True),
                                      self.cursor['total_size'], self.size)
            self.message = {'content': pos, 'input': key, 'click': touch.button}

    def on_send_text(self, message):
        self.message = {'content': [message], 'input': 4}


if __name__ == '__main__':
    from kivy.app import App

    class TestApp(App):
        def build(self):
            self.root = Controllers()

            return self.root

    TestApp().run()
