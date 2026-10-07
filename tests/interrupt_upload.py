import socket
import sys
from pathlib import Path

from common.protocol import send_message, receive_message


HOST = "127.0.0.1"
PORT = 5050

PARTIAL_SIZE = 10 * 1024 * 1024  # 10 MB


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 tests/interrupt_upload.py <file>")
        sys.exit(1)

    file_path = Path(sys.argv[1])

    if not file_path.is_file():
        print(f"File not found: {file_path}")
        sys.exit(1)

    file_size = file_path.stat().st_size

    if file_size <= PARTIAL_SIZE:
        print(
            f"Test file must be larger than "
            f"{PARTIAL_SIZE / (1024 ** 2):.0f} MB"
        )
        sys.exit(1)

    # Calculate the full file SHA-256.
    import hashlib

    sha256 = hashlib.sha256()

    with file_path.open("rb") as file:
        while True:
            chunk = file.read(64 * 1024)

            if not chunk:
                break

            sha256.update(chunk)

    file_hash = sha256.hexdigest()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        sock.connect((HOST, PORT))

        print(f"Connected to {HOST}:{PORT}")

        send_message(sock, {
            "type": "UPLOAD",
            "filename": file_path.name,
            "size": file_size,
            "sha256": file_hash,
        })

        response = receive_message(sock)

        print(f"Server response: {response}")

        if response.get("type") != "UPLOAD_READY":
            print("Unexpected server response")
            return

        offset = response.get("offset", 0)

        if offset != 0:
            print(f"Unexpected existing offset: {offset}")
            return

        bytes_to_send = PARTIAL_SIZE

        print(
            f"Sending only "
            f"{bytes_to_send / (1024 ** 2):.0f} MB "
            f"then closing the connection..."
        )

        with file_path.open("rb") as file:
            remaining = bytes_to_send

            while remaining > 0:
                chunk = file.read(min(64 * 1024, remaining))

                if not chunk:
                    break

                sock.sendall(chunk)
                remaining -= len(chunk)

        print("Intentional interruption: closing connection")

    finally:
        sock.close()


if __name__ == "__main__":
    main()