import hashlib
import socket
import time
from pathlib import Path

from common.protocol import send_message, receive_message


HOST = "127.0.0.1"
PORT = 5050

FILE_PATH = Path("resume-test.bin")
HOLD_TIME = 5


def calculate_sha256(file_path):
    sha256 = hashlib.sha256()

    with file_path.open("rb") as file:
        while True:
            chunk = file.read(64 * 1024)

            if not chunk:
                break

            sha256.update(chunk)

    return sha256.hexdigest()


def main():
    if not FILE_PATH.is_file():
        raise FileNotFoundError(
            f"File not found: {FILE_PATH}"
        )

    file_size = FILE_PATH.stat().st_size
    file_hash = calculate_sha256(FILE_PATH)

    sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM
    )

    try:
        print("Connecting to server...")

        sock.connect((HOST, PORT))

        print("Connected.")

        send_message(sock, {
            "type": "UPLOAD",
            "filename": FILE_PATH.name,
            "size": file_size,
            "sha256": file_hash,
        })

        response = receive_message(sock)

        print(f"Server response: {response}")

        if response.get("type") != "UPLOAD_READY":
            print("Server did not allow the upload.")
            return

        offset = response.get("offset", 0)

        print(
            f"Server granted upload lock. "
            f"Offset: {offset}"
        )

        with FILE_PATH.open("rb") as file:
            file.seek(offset)

            chunk = file.read(64 * 1024)

            if chunk:
                sock.sendall(chunk)

                print(
                    f"Sent {len(chunk)} bytes."
                )

        print(
            f"\nHolding the upload connection "
            f"for {HOLD_TIME} seconds..."
        )

        print(
            "During this time, start another "
            "upload of the same file."
        )

        time.sleep(HOLD_TIME)

        print(
            "\nReleasing the test connection."
        )

    finally:
        sock.close()

        print("Test connection closed.")


if __name__ == "__main__":
    main()