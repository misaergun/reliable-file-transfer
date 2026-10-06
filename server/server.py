import hashlib
import socket
from pathlib import Path

from common.protocol import receive_message, receive_exact


HOST = "127.0.0.1"
PORT = 5050

BUFFER_SIZE = 64 * 1024

RECEIVED_DIR = Path("received_files")
RECEIVED_DIR.mkdir(exist_ok=True)


server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

server_socket.bind((HOST, PORT))
server_socket.listen(1)

print(f"Server listening on {HOST}:{PORT}")


client_socket, client_address = server_socket.accept()

print(f"Client connected: {client_address}")


try:
    message = receive_message(client_socket)

    print(f"Received message: {message}")

    if message.get("type") != "UPLOAD":
        raise ValueError("Unsupported message type")

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
    else:
        print("TRANSFER FAILED: checksum mismatch")

finally:
    client_socket.close()
    server_socket.close()