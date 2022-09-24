import logging
import pickle
import struct
from os.path import abspath, dirname, join
from pickle import loads
from socket import AF_INET, SO_REUSEADDR, SOCK_STREAM, SOL_SOCKET, socket
from struct import calcsize, unpack
from subprocess import check_output
from threading import Lock, Thread
from threading import enumerate as enum
from time import sleep

from numpy import array
from PIL import Image, ImageGrab


def xdotool_events(target=[]):
    return check_output(
        ['xdotool'] + target,
        encoding='utf8'
    )


def server_init(host):
    server = socket(AF_INET, SOCK_STREAM)
    server.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    server.bind(host)
    server.listen(10)

    return server


def screenshot(scale_percent):
    screenshot_ = ImageGrab.grab(all_screens=True)
    screenshot = screenshot_.resize(
        [
            int(x * scale_percent / 100)
            for x in screenshot_.size
        ],
        Image.Resampling.LANCZOS
    )
    screen = dict(
        tuple(
            float(value) if value.isdigit() else value
            for value in item.split(":")
        )
        for item in xdotool_events(
            ['getmouselocation']
        ).split()
    )
    screen['total_size'] = screenshot_.size

    return (array(screenshot), screen)


class FeedStream:
    ipv4_allowed: list = ['192.168.0.']
    scale_percent: int = 100
    screen_info: list = []
    size: tuple = ()
    _content_data: tuple = ()
    lock: object = None
    recording: bool = False

    def __init__(self, **kwargs):
        host, port = kwargs.get('host', ('0.0.0.0', 4321))
        self.output_ = server_init((host, port))
        self.input_ = server_init((host, port + 1))
        self.scale_percent = kwargs.get('scale_percent', 100)
        logging.info("Initialized the socket protocol.")
        self._active_sessions = 0
        self.lock = Lock()

        if kwargs.get('threaded', False):
            Thread(target=self.listen, daemon=True).start()
        else:
            self.listen()

    @property
    def active_sessions(self):
        running = [x for x in enum() if x.name == 'screenshooter']
        if not all([running, self.recording]):
            logging.info("Started capturing screenshots")
            self.recording = True
            Thread(
                target=self.run_screenshots,
                args=(self.lock, ),
                name='screenshooter',
                daemon=True
            ).start()

        if running and self._active_sessions == 0:
            running[0].stop()
            self.recording = False

        return self._active_sessions

    @active_sessions.setter
    def active_sessions(self, value):
        self._active_sessions = value

    def run_screenshots(self, lock):
        while self.recording:
            lock.acquire()
            self._content_data = screenshot(
                self.scale_percent
            )
            lock.release()
            sleep(.05)

    def listen(self):
        while True:
            in_, address1 = self.output_.accept()
            out_, address2 = self.input_.accept()
            in_.settimeout(10)
            out_.settimeout(10)

            if all([
                address1[0] == address2[0],
                address1[0][:10] in self.ipv4_allowed
            ]):
                logging.info(f"{address1[0]} is now connected.")
                Thread(
                    target=self.transmit_data,
                    args=(in_, out_, address1),
                    daemon=True
                ).start()

    def transmit_data(self, client1, client2, user):
        logging.info(f"Feed started and ready for {user[0]}")
        self.active_sessions += 1
        payload_size = calcsize("L")
        data = [b'', b'']

        while self.recording:
            try:
                data[0] = pickle.dumps(self._content_data)
                message_size = struct.pack("L", len(data[0]))
                client1.sendall(message_size + data[0])

            except Exception:
                logging.info(f"Disconnecting user: {user}")
                self.active_sessions -= 1
                break

            while len(data[1]) < payload_size:
                data[1] += client2.recv(4096)

            packed_msg_size = data[1][:payload_size]
            data[1] = data[1][payload_size:]
            msg_size = unpack("L", packed_msg_size)[0]

            while len(data[1]) < msg_size:
                data[1] += client2.recv(4096)

            frame_data = data[1][:msg_size]
            data[1] = data[1][msg_size:]

            if content := loads(frame_data):
                self.mouse_action(content)

            sleep(.1)

    def mouse_action(self, content):
        event = {
            1: "mousemove {0} {1} click {2}",
            2: "mousemove {0} {1}"
        }
        behavior = content.get('behavior', 1)
        pos = content.get('pos', (0, 0))

        xdotool_events(
            event[
                content.get('input', 1)
            ].format(*pos, behavior).split()
        )


if __name__ == '__main__':
    logging.basicConfig(
        filename=join(dirname(abspath(__file__)), 'logs.txt'),
        filemode='a',
        format='%(asctime)s %(levelname)s %(message)s',
        datefmt='%H:%M:%S',
        level=logging.INFO
    )
    logging.getLogger().addHandler(logging.StreamHandler())
    FeedStream(
        host=('0.0.0.0', 6666),
        scale_percent=30,
        threading=False
    )
