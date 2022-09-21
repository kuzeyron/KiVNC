import logging
import pickle
import struct
from os.path import abspath, dirname, join
from pickle import loads
from socket import AF_INET, SO_REUSEADDR, SOCK_STREAM, SOL_SOCKET, socket
from struct import calcsize, unpack
from subprocess import check_output
from threading import Thread

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


class FeedStream:
    active: bool = True
    ipv4_allowed: list = ['192.168.0.']
    scale_percent: int = 100
    screen_info: list = []
    size: tuple = ()

    def __init__(self, **kwargs):
        host, port = kwargs.get('host', ('0.0.0.0', 4321))
        self.output_ = server_init((host, port))
        self.input_ = server_init((host, port + 1))
        self.scale_percent = kwargs.get('scale_percent', 100)
        logging.info("Initialized the socket protocol.")

        if kwargs.get('threaded', False):
            Thread(target=self.listen, daemon=True).start()
        else:
            self.listen()

    def listen(self):
        while self.active:
            in_, address1 = self.output_.accept()
            out_, address2 = self.input_.accept()
            in_.settimeout(60)
            out_.settimeout(60)

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

    def screenshot(self):
        screenshot_ = ImageGrab.grab(all_screens=True)
        screenshot = screenshot_.resize(
            [
                int(x * self.scale_percent / 100)
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
        self.size = screen['total_size'] = screenshot_.size

        return [array(screenshot), screen]

    def transmit_data(self, client1, client2, user):
        logging.info("Feed started and ready for transfer")
        payload_size = calcsize("L")
        data = [b'', b'']

        while self.active:
            # try/except to ignore crashes silently
            try:
                data[0] = pickle.dumps(self.screenshot())
                message_size = struct.pack("L", len(data[0]))
                client1.sendall(message_size + data[0])

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

            except Exception:  # I would like having TimeoutError here instead
                logging.info(f"Disconnecting user: {user}")
                break

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
