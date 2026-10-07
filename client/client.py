import hashlib
import socket
import sys
import time
from pathlib import Path

from common.protocol import send_message, receive_message, receive_exact


HOST = "127.0.0.1"
PORT = 5050

BUFFER_SIZE = 64 * 1024

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)


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

        # Wait for the server to tell us where to start.
        response = receive_message(sock)

        if response.get("type") != "UPLOAD_READY":
            print("Unexpected server response:", response)
            return

        offset = response.get("offset", 0)

        if offset < 0 or offset > file_size:
            print(f"Invalid resume offset received from server: {offset}")
            return

        if offset == 0:
            print("Starting upload from the beginning")
        else:
            print(
                f"Resuming upload from byte {offset} "
                f"({format_bytes(offset)})"
            )

        print(f"Uploading: {file_path.name}")
        print(f"Size: {format_bytes(file_size)}")
        print(f"SHA-256: {file_hash}")

        bytes_sent = offset

        start_time = time.monotonic()

        with file_path.open("rb") as file:
            # Skip the bytes that the server already has.
            file.seek(offset)

            while True:
                chunk = file.read(BUFFER_SIZE)

                if not chunk:
                    break

                sock.sendall(chunk)
                bytes_sent += len(chunk)

                elapsed = time.monotonic() - start_time

                speed = (
                    (bytes_sent - offset) / elapsed
                    if elapsed > 0
                    else 0
                )

                percentage = (
                    (bytes_sent / file_size) * 100
                    if file_size > 0
                    else 100
                )

                print(
                    f"\rProgress: {percentage:6.2f}% | "
                    f"{format_bytes(bytes_sent)} / "
                    f"{format_bytes(file_size)} | "
                    f"Speed: {format_bytes(speed)}/s",
                    end="",
                    flush=True,
                )

        elapsed = time.monotonic() - start_time

        print()
        print(f"Upload completed in {elapsed:.2f}s")

        if elapsed > 0:
            transferred_this_attempt = bytes_sent - offset
            average_speed = transferred_this_attempt / elapsed

            print(
                f"Average speed: "
                f"{format_bytes(average_speed)}/s"
            )

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


def download_file(filename):
    filename = Path(filename).name

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        sock.connect((HOST, PORT))

        print(f"Connected to {HOST}:{PORT}")

        message = {
            "type": "DOWNLOAD",
            "filename": filename,
        }

        send_message(sock, message)

        response = receive_message(sock)

        if response.get("type") == "DOWNLOAD_FAILED":
            print("Download failed")
            print(response.get("message"))
            return

        if response.get("type") != "DOWNLOAD_READY":
            print("Unexpected server response:", response)
            return

        file_size = response["size"]
        expected_hash = response["sha256"]

        output_path = DOWNLOAD_DIR / filename

        print(f"Downloading: {filename}")
        print(f"Size: {format_bytes(file_size)}")
        print(f"SHA-256: {expected_hash}")

        sha256 = hashlib.sha256()

        remaining = file_size
        bytes_received = 0

        start_time = time.monotonic()

        with output_path.open("wb") as file:
            while remaining > 0:
                chunk_size = min(BUFFER_SIZE, remaining)
                chunk = receive_exact(sock, chunk_size)

                file.write(chunk)
                sha256.update(chunk)

                remaining -= len(chunk)
                bytes_received += len(chunk)

                elapsed = time.monotonic() - start_time

                speed = (
                    bytes_received / elapsed
                    if elapsed > 0
                    else 0
                )

                percentage = (
                    (bytes_received / file_size) * 100
                    if file_size > 0
                    else 100
                )

                print(
                    f"\rProgress: {percentage:6.2f}% | "
                    f"{format_bytes(bytes_received)} / "
                    f"{format_bytes(file_size)} | "
                    f"Speed: {format_bytes(speed)}/s",
                    end="",
                    flush=True,
                )

        elapsed = time.monotonic() - start_time
        actual_hash = sha256.hexdigest()

        print()
        print(f"Download completed in {elapsed:.2f}s")
        print(f"Actual SHA-256: {actual_hash}")

        if actual_hash == expected_hash:
            print("DOWNLOAD VERIFIED")

            send_message(sock, {
                "type": "DOWNLOAD_VERIFIED"
            })

        else:
            print("DOWNLOAD FAILED: checksum mismatch")

            send_message(sock, {
                "type": "DOWNLOAD_FAILED",
                "message": "Checksum mismatch"
            })

    finally:
        sock.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            "Usage:\n"
            "  python3 -m client.client upload <file>\n"
            "  python3 -m client.client download <file>"
        )
        sys.exit(1)

    command = sys.argv[1]

    if command == "upload" and len(sys.argv) == 3:
        upload_file(sys.argv[2])

    elif command == "download" and len(sys.argv) == 3:
        download_file(sys.argv[2])

    else:
        print(
            "Usage:\n"
            "  python3 -m client.client upload <file>\n"
            "  python3 -m client.client download <file>"
        )
        sys.exit(1)