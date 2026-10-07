import hashlib
import socket
from pathlib import Path

from common.protocol import send_message, receive_message, receive_exact


HOST = "127.0.0.1"
PORT = 5050

BUFFER_SIZE = 64 * 1024

RECEIVED_DIR = Path("received_files")
RECEIVED_DIR.mkdir(exist_ok=True)


def calculate_sha256(file_path):
    sha256 = hashlib.sha256()

    with file_path.open("rb") as file:
        while True:
            chunk = file.read(BUFFER_SIZE)

            if not chunk:
                break

            sha256.update(chunk)

    return sha256.hexdigest()


def handle_upload(client_socket, message):
    filename = Path(message["filename"]).name
    file_size = message["size"]
    expected_hash = message["sha256"]

    output_path = RECEIVED_DIR / filename

    print(f"Receiving file: {filename}")
    print(f"File size: {file_size} bytes")
    print(f"Expected SHA-256: {expected_hash}")

    sha256 = hashlib.sha256()

    remaining = file_size

    with output_path.open("wb") as file:
        while remaining > 0:
            chunk_size = min(BUFFER_SIZE, remaining)

            chunk = receive_exact(client_socket, chunk_size)

            file.write(chunk)
            sha256.update(chunk)

            remaining -= len(chunk)

    actual_hash = sha256.hexdigest()

    print(f"Actual SHA-256: {actual_hash}")

    if actual_hash == expected_hash:
        print("TRANSFER VERIFIED")

        send_message(client_socket, {
            "type": "TRANSFER_OK",
            "message": "File received and verified successfully"
        })

    else:
        print("TRANSFER FAILED: checksum mismatch")

        send_message(client_socket, {
            "type": "TRANSFER_FAILED",
            "message": "Checksum mismatch"
        })


def handle_download(client_socket, message):
    filename = Path(message["filename"]).name
    file_path = RECEIVED_DIR / filename

    print(f"Download requested: {filename}")

    if not file_path.is_file():
        print("File not found")

        send_message(client_socket, {
            "type": "DOWNLOAD_FAILED",
            "message": "File not found"
        })

        return

    file_size = file_path.stat().st_size
    file_hash = calculate_sha256(file_path)

    send_message(client_socket, {
        "type": "DOWNLOAD_READY",
        "filename": filename,
        "size": file_size,
        "sha256": file_hash
    })

    print(f"Sending file: {filename}")
    print(f"File size: {file_size} bytes")
    print(f"SHA-256: {file_hash}")

    with file_path.open("rb") as file:
        while True:
            chunk = file.read(BUFFER_SIZE)

            if not chunk:
                break

            client_socket.sendall(chunk)

    print("Download transfer completed")

    response = receive_message(client_socket)

    if response.get("type") == "DOWNLOAD_VERIFIED":
        print("Client verified the file successfully")
    else:
        print("Client reported a verification failure")


def start_server():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    server_socket.bind((HOST, PORT))
    server_socket.listen(1)

    print(f"Server listening on {HOST}:{PORT}")

    client_socket, client_address = server_socket.accept()

    print(f"Client connected: {client_address}")

    try:
        message = receive_message(client_socket)

        print(f"Received message: {message}")

        message_type = message.get("type")

        if message_type == "UPLOAD":
            handle_upload(client_socket, message)

        elif message_type == "DOWNLOAD":
            handle_download(client_socket, message)

        else:
            send_message(client_socket, {
                "type": "ERROR",
                "message": "Unsupported operation"
            })

    finally:
        client_socket.close()
        server_socket.close()


if __name__ == "__main__":
    start_server()