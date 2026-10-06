import socket
import sys
from pathlib import Path

from common.protocol import send_message


HOST = "127.0.0.1"
PORT = 5050

BUFFER_SIZE = 64 * 1024


def upload_file(file_path):
    file_path = Path(file_path)

    if not file_path.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")

    file_size = file_path.stat().st_size

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        sock.connect((HOST, PORT))

        print(f"Connected to {HOST}:{PORT}")

        message = {
            "type": "UPLOAD",
            "filename": file_path.name,
            "size": file_size,
        }

        send_message(sock, message)

        print(f"Uploading: {file_path.name}")
        print(f"Size: {file_size} bytes")

        with file_path.open("rb") as file:
            while True:
                chunk = file.read(BUFFER_SIZE)

                if not chunk:
                    break

                sock.sendall(chunk)

        print("Upload completed")

    finally:
        sock.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 client/client.py <file>")
        sys.exit(1)

    upload_file(sys.argv[1])