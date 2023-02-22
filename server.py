import logging
import pickle
import struct
from datetime import datetime, timedelta
from os import makedirs, stat
from os.path import abspath, dirname, join
from pickle import loads
from socket import AF_INET, SO_REUSEADDR, SOCK_STREAM, SOL_SOCKET, socket
from struct import calcsize, unpack
from subprocess import STDOUT, check_output
from threading import Thread
from threading import enumerate as enum
from time import sleep

from numpy import array
from PIL import Image


def xdotool(cmd):
    return check_output(
        ['xdotool'] + cmd,
        encoding='utf8',
        stderr=STDOUT
    )


def server_init(host):
    server = socket(AF_INET, SOCK_STREAM)
    server.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    server.bind(host)
    server.listen(10)

    return server


def screenshot(scale_percent, path):
    co = check_output(path, encoding='utf8', stderr=STDOUT)
    st = bool(stat(path[-1]).st_size)
    
    if co and st:
        screenshot_ = Image.open(path[-1])
        screenshot = screenshot_.resize(
            [int(x * scale_percent / 100)
             for x in screenshot_.size],
            Image.Resampling.LANCZOS)
        screen = dict(
            tuple(float(value) if value.isdigit() else value
                for value in item.split(":"))
            for item in xdotool(['getmouselocation']).split())
        screen['total_size'] = screenshot_.size

        return (array(screenshot), screen)

    return False
    

class FeedStream:
    ipv4_allowed: list = ['192.168.x.']
    scale_percent: int = 100
    screen_info: list = []
    size: tuple = ()
    _data: tuple = ()
    lock: object = None

    def __init__(self, **kwargs):
        self.shot_path = kwargs.get('shot_path', '/tmp/kivnc.jpeg')
        host, port = kwargs.get('host', ('0.0.0.0', 4321))
        self.output_ = server_init((host, port))
        self.input_ = server_init((host, port + 1))
        self.scale_percent = kwargs.get('scale_percent', 100)
        logging.info("Initialized the socket protocol.")
        self._active_sessions = 0

        if kwargs.get('threaded', False):
            Thread(target=self.listen, daemon=True).start()
        else:
            self.listen()

    @property
    def active_sessions(self):
        return self._active_sessions

    @active_sessions.setter
    def active_sessions(self, value):
        running = [x for x in enum() if x.name == 'screenshooter']
        self._active_sessions = max(0, value)

        if not running:
            logging.info("Started capturing screenshots")
            Thread(
                target=self.run_screenshots,
                name='screenshooter',
                daemon=True
            ).start()

    @active_sessions.getter
    def active_sessions(self):
        return self._active_sessions

    def run_screenshots(self):
        while self.active_sessions > 0:
            self._data = screenshot(self.scale_percent,
                                    self.shot_path)

    def listen(self):
        while True:
            in_, address1 = self.output_.accept()
            out_, address2 = self.input_.accept()
            in_.settimeout(5)
            out_.settimeout(5)

            if all([
                address1[0] == address2[0],
                address1[0][:10] in self.ipv4_allowed
            ]):
                logging.info("%s is now connected.", address1[0])
                Thread(
                    target=self.transmit_data,
                    args=(in_, out_, address1),
                    daemon=True
                ).start()

    def transmit_data(self, client1, client2, user):
        logging.info("Feed started and ready for %s", user[0])
        time_start = datetime.now()
        timeout = timedelta(seconds=10)
        self.active_sessions += 1
        payload_size = calcsize("L")
        data = [b'', b'']

        while self.active_sessions > 0:
            try:
                data[0] = pickle.dumps(self._data)
                message_size = struct.pack("L", len(data[0]))
                client1.sendall(message_size + data[0])

                while len(data[1]) < payload_size:
                    now = datetime.now()
                    if (now - time_start) > timeout:
                        break
                    data[1] += client2.recv(4096)
                else:
                    sleep(.2)
                time_start = now

            except Exception:
                break

            try:
                packed_msg_size = data[1][:payload_size]
                data[1] = data[1][payload_size:]
                msg_size = unpack("L", packed_msg_size)[0]

                while len(data[1]) < msg_size:
                    now = datetime.now()
                    if (now - time_start) > timeout:
                        break
                    data[1] += client2.recv(4096)
                time_start = now

                frame_data = data[1][:msg_size]
                data[1] = data[1][msg_size:]

                if content := loads(frame_data):
                    self.mouse_action(content)

            except Exception:
                break

        logging.info("Disconnecting user: %s", user[0])
        self.active_sessions -= 1

    def mouse_action(self, content):
        event = {
            1: "mousemove {0} {1} click {2}",
            2: "mousemove {0} {1}"
        }
        behavior = content.get('behavior', 1)
        pos = content.get('pos', (0, 0))

        xdotool(
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
    path = ['/usr/bin/xfce4-screenshooter',
            '-f', '-s', '/tmp/KiVNC/shot.jpeg']
    makedirs(dirname(path[-1]), exist_ok=True)
    FeedStream(
        host=('0.0.0.0', 6666),
        scale_percent=40,
        threading=False,
        shot_path=path
    )
