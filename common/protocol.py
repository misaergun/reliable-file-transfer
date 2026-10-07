import json
import struct


HEADER_SIZE = 4
MAX_MESSAGE_SIZE = 1024 * 1024  # 1 MB


def send_message(sock, message):
    data = json.dumps(message).encode("utf-8")

    if len(data) > MAX_MESSAGE_SIZE:
        raise ValueError(
            f"Message exceeds maximum size of "
            f"{MAX_MESSAGE_SIZE} bytes"
        )

    header = struct.pack("!I", len(data))

    sock.sendall(header)
    sock.sendall(data)


def receive_exact(sock, size):
    data = bytearray()

    while len(data) < size:
        chunk = sock.recv(size - len(data))

        if not chunk:
            raise ConnectionError(
                "Connection closed while receiving data"
            )

        data.extend(chunk)

    return bytes(data)


def receive_message(sock):
    header = receive_exact(
        sock,
        HEADER_SIZE,
    )

    message_size = struct.unpack(
        "!I",
        header,
    )[0]

    if message_size > MAX_MESSAGE_SIZE:
        raise ValueError(
            f"Message exceeds maximum size of "
            f"{MAX_MESSAGE_SIZE} bytes"
        )

    if message_size == 0:
        raise ValueError(
            "Message cannot be empty"
        )

    data = receive_exact(
        sock,
        message_size,
    )

    try:
        return json.loads(
            data.decode("utf-8")
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as error:
        raise ValueError(
            "Invalid JSON message"
        ) from error