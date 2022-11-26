import pickle
import struct
from functools import partial
from io import BytesIO
from pickle import loads
from socket import AF_INET, SOCK_STREAM, socket
from struct import calcsize, unpack
from threading import Thread

from kivy.clock import Clock
from kivy.core.image import Image as CoreImage
from kivy.lang import Builder
from kivy.properties import (BooleanProperty, ListProperty, NumericProperty,
                             ObjectProperty, StringProperty)
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.widget import Widget
from PIL import Image as Pimage

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

<Container>:
    size_hint: .9, .9
    pos_hint: {'center_x': .5, 'center_y': .5}
    FeedReceiver:
        host: ('192.168.0.8', 6666)

''')


def coordinates_to_size(pos, sz, ws, extra=0):
    return (
        pos[0] / sz[0] * ws[0],
        ws[1] - pos[1] / sz[1] * ws[1] - extra
    )


def size_to_coorinates(pos, sz, ws):
    return (
        pos[0] * sz[0] / ws[0],
        sz[1] - pos[1] * sz[1] / ws[1]
    )


class Container(RelativeLayout):
    pass


def server_init(remote=('localhost', 4321)):
    client = socket(AF_INET, SOCK_STREAM)
    client.connect(remote)

    return client


class FeedReceiver(Widget):
    cursor_icon = StringProperty('assets/icons/cursor.png')
    cursor_pos = ListProperty((0, 0))
    cursor_size = NumericProperty('20dp')
    host = ListProperty()
    show_cursor = BooleanProperty(True)
    texture = ObjectProperty()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._bytesio = BytesIO()
        self.bind(host=self.setup_handler)

    def setup_handler(self, *largs):
        try:
            self.remote, self.port = self.host
            self.input_ = server_init((self.remote, self.port))
            self.output_ = server_init((self.remote, self.port + 1))
            self.message = {}
            Thread(target=self.transmit_data, daemon=True).start()
        except Exception:
            Clock.schedule_once(self.setup_handler, 1)

    def transmit_data(self, *largs):
        payload_size = calcsize("L")
        data = [b'', b'']

        while True:
            data[0] = pickle.dumps(self.message)
            message_size = struct.pack("L", len(data[0]))
            self.output_.sendall(message_size + data[0])
            self.message = {}

            while len(data[1]) < payload_size:
                data[1] += self.input_.recv(4096)

            packed_msg_size = data[1][:payload_size]
            data[1] = data[1][payload_size:]
            msg_size = unpack("L", packed_msg_size)[0]

            while len(data[1]) < msg_size:
                data[1] += self.input_.recv(4096)

            frame_data = data[1][:msg_size]
            data[1] = data[1][msg_size:]
            if content := loads(frame_data):
                Clock.schedule_once(
                    partial(
                        self.draw_frame,
                        content
                    ), 0
                )

    def draw_frame(self, content, *largs):
        image, cursor = content
        img = Pimage.fromarray(image)
        img.save(self._bytesio, format='png')
        self._bytesio.seek(0)

        self.texture = CoreImage(
            self._bytesio,
            ext='png'
        ).texture

        self._bytesio.seek(0)
        self._bytesio.flush()

        self.total_size = tsize = cursor['total_size']
        pos = coordinates_to_size(
            (cursor['x'], cursor['y']), tsize, self.size, self.cursor_size
        )

        self.cursor_pos = pos

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            pos = size_to_coorinates(
                touch.pos, self.total_size, self.size
            )
            self.message = {'pos': pos, 'input': 1}

    def on_touch_move(self, touch):
        if self.collide_point(*touch.pos):
            pos = size_to_coorinates(
                touch.pos, self.total_size, self.size
            )
            self.message = {'pos': pos, 'input': 2}


if __name__ == '__main__':
    from kivy.app import App

    class TestApp(App):
        def build(self):
            self.root = Container()

            return self.root

    TestApp().run()
