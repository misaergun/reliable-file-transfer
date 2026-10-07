import hashlib
import socket
import sys
import time
from pathlib import Path

from common.protocol import send_message, receive_message


HOST = "127.0.0.1"
PORT = 5050

BUFFER_SIZE = 64 * 1024


def calculate_sha256(file_path):
    sha256 = hashlib.sha256()

    with file_path.open("rb") as file:
        while True:
            chunk = file.read(BUFFER_SIZE)

            if not chunk:
                break

            sha256.update(chunk)

    return sha256.hexdigest()


def format_bytes(size):
    if size < 1024:
        return f"{size} B"

    if size < 1024 ** 2:
        return f"{size / 1024:.1f} KB"

    if size < 1024 ** 3:
        return f"{size / (1024 ** 2):.1f} MB"

    return f"{size / (1024 ** 3):.1f} GB"


def upload_file(file_path):
    file_path = Path(file_path)

    if not file_path.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")

    file_size = file_path.stat().st_size
    file_hash = calculate_sha256(file_path)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        sock.connect((HOST, PORT))

        print(f"Connected to {HOST}:{PORT}")

        message = {
            "type": "UPLOAD",
            "filename": file_path.name,
            "size": file_size,
            "sha256": file_hash,
        }

        send_message(sock, message)

        print(f"Uploading: {file_path.name}")
        print(f"Size: {format_bytes(file_size)}")
        print(f"SHA-256: {file_hash}")

        bytes_sent = 0
        start_time = time.monotonic()

        with file_path.open("rb") as file:
            while True:
                chunk = file.read(BUFFER_SIZE)

                if not chunk:
                    break

                sock.sendall(chunk)

                bytes_sent += len(chunk)

                elapsed = time.monotonic() - start_time

                if elapsed > 0:
                    speed = bytes_sent / elapsed
                else:
                    speed = 0

                percentage = (bytes_sent / file_size) * 100

                print(
                    f"\rProgress: {percentage:6.2f}% | "
                    f"{format_bytes(bytes_sent)} / {format_bytes(file_size)} | "
                    f"Speed: {format_bytes(speed)}/s",
                    end="",
                    flush=True,
                )

        elapsed = time.monotonic() - start_time

        print()
        print(f"Upload completed in {elapsed:.2f}s")

        if elapsed > 0:
            average_speed = bytes_sent / elapsed
            print(f"Average speed: {format_bytes(average_speed)}/s")

        response = receive_message(sock)

        if response.get("type") == "TRANSFER_OK":
            print("Server verified the file successfully")

        elif response.get("type") == "TRANSFER_FAILED":
            print("Server rejected the file")
            print(response.get("message"))

        else:
            print("Unexpected server response:", response)

    finally:
        sock.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 -m client.client <file>")
        sys.exit(1)

    upload_file(sys.argv[1])