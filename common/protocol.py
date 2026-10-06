import json
import struct


HEADER_SIZE = 4


def send_message(sock, message):
    data = json.dumps(message).encode("utf-8")

    header = struct.pack("!I", len(data))

    sock.sendall(header)
    sock.sendall(data)


def receive_exact(sock, size):
    data = bytearray()

    while len(data) < size:
        chunk = sock.recv(size - len(data))

        if not chunk:
            raise ConnectionError("Connection closed while receiving data")

        data.extend(chunk)

    return bytes(data)


def receive_message(sock):
    header = receive_exact(sock, HEADER_SIZE)

    message_size = struct.unpack("!I", header)[0]

    data = receive_exact(sock, message_size)

    return json.loads(data.decode("utf-8"))