import hashlib
import json
import socket
import threading
from pathlib import Path

from common.protocol import send_message, receive_message, receive_exact


HOST = "127.0.0.1"
PORT = 5050

BUFFER_SIZE = 64 * 1024

SOCKET_TIMEOUT = 30

RECEIVED_DIR = Path("received_files")
RECEIVED_DIR.mkdir(exist_ok=True)

# Each filename gets its own lock.
# This prevents two clients from modifying the same
# partial file at the same time.
file_locks = {}
file_locks_guard = threading.Lock()


def get_file_lock(filename):
    with file_locks_guard:
        if filename not in file_locks:
            file_locks[filename] = threading.Lock()

        return file_locks[filename]


def calculate_sha256(file_path):
    sha256 = hashlib.sha256()

    with file_path.open("rb") as file:
        while True:
            chunk = file.read(BUFFER_SIZE)

            if not chunk:
                break

            sha256.update(chunk)

    return sha256.hexdigest()


def validate_upload_message(message):
    if not isinstance(message, dict):
        return False, "Upload request must be a JSON object"

    filename = message.get("filename")
    file_size = message.get("size")
    expected_hash = message.get("sha256")

    if not isinstance(filename, str):
        return False, "Filename must be a string"

    filename = filename.strip()

    if not filename:
        return False, "Filename cannot be empty"

    if filename in {".", ".."}:
        return False, "Invalid filename"

    if Path(filename).name != filename:
        return False, "Path separators are not allowed in filename"

    if not isinstance(file_size, int) or isinstance(file_size, bool):
        return False, "File size must be a non-negative integer"

    if file_size < 0:
        return False, "File size cannot be negative"

    if not isinstance(expected_hash, str):
        return False, "SHA-256 must be a string"

    if len(expected_hash) != 64:
        return False, "SHA-256 must contain exactly 64 characters"

    if any(
        character not in "0123456789abcdefABCDEF"
        for character in expected_hash
    ):
        return False, "SHA-256 contains invalid hexadecimal characters"

    return True, None


def load_partial_metadata(metadata_path):
    if not metadata_path.is_file():
        return None

    try:
        with metadata_path.open(
            "r",
            encoding="utf-8"
        ) as file:
            return json.load(file)

    except (json.JSONDecodeError, OSError):
        return None


def save_partial_metadata(
    metadata_path,
    filename,
    file_size,
    expected_hash
):
    metadata = {
        "filename": filename,
        "size": file_size,
        "sha256": expected_hash,
    }

    with metadata_path.open(
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            metadata,
            file,
            indent=2
        )


def remove_partial_files(
    partial_path,
    metadata_path
):
    if partial_path.exists():
        partial_path.unlink()

    if metadata_path.exists():
        metadata_path.unlink()


def partial_metadata_matches(
    metadata,
    filename,
    file_size,
    expected_hash
):
    if not isinstance(metadata, dict):
        return False

    return (
        metadata.get("filename") == filename
        and metadata.get("size") == file_size
        and metadata.get("sha256") == expected_hash
    )


def handle_upload(client_socket, message):
    valid, error_message = validate_upload_message(message)

    if not valid:
        print(
            f"Invalid upload request: {error_message}"
        )

        send_message(client_socket, {
            "type": "UPLOAD_FAILED",
            "message": error_message
        })

        return

    filename = Path(message["filename"]).name
    file_size = message["size"]
    expected_hash = message["sha256"].lower()

    output_path = RECEIVED_DIR / filename
    partial_path = RECEIVED_DIR / f"{filename}.part"
    metadata_path = RECEIVED_DIR / f"{filename}.part.json"

    file_lock = get_file_lock(filename)

    print(f"Upload requested: {filename}")

    # Only one client can upload this specific filename at a time.
    acquired = file_lock.acquire(blocking=False)

    if not acquired:
        print(
            f"Upload already in progress for: {filename}"
        )

        send_message(client_socket, {
            "type": "UPLOAD_FAILED",
            "message": (
                "Another client is currently "
                "uploading this file"
            )
        })

        return

    try:
        print(f"File size: {file_size} bytes")
        print(f"Expected SHA-256: {expected_hash}")

        # Check whether a partial upload already exists.
        if partial_path.is_file():
            current_size = partial_path.stat().st_size

            metadata = load_partial_metadata(
                metadata_path
            )

            if not partial_metadata_matches(
                metadata,
                filename,
                file_size,
                expected_hash
            ):
                print(
                    "Partial file metadata does not "
                    "match this upload"
                )

                print(
                    "Discarding stale or invalid "
                    "partial file"
                )

                remove_partial_files(
                    partial_path,
                    metadata_path
                )

                offset = 0

            elif current_size < file_size:
                offset = current_size

                print(
                    f"Partial file found: "
                    f"{offset} bytes already received"
                )

                print(
                    f"Resuming from byte {offset}"
                )

            elif current_size == file_size:
                offset = current_size

                print(
                    "Partial file already contains "
                    "the complete file"
                )

            else:
                print(
                    "Partial file is larger than expected"
                )

                print("Discarding partial file")

                remove_partial_files(
                    partial_path,
                    metadata_path
                )

                offset = 0

        else:
            # A metadata file without its corresponding
            # partial file is stale and should not be used.
            if metadata_path.exists():
                print(
                    "Partial metadata exists without "
                    "a partial file"
                )

                print(
                    "Removing stale partial metadata"
                )

                metadata_path.unlink()

            offset = 0

        # If the final file already exists, check whether
        # it is already the requested file.
        if output_path.is_file() and offset == 0:
            existing_size = output_path.stat().st_size

            if existing_size == file_size:
                existing_hash = calculate_sha256(
                    output_path
                )

                if existing_hash == expected_hash:
                    print(
                        "File already exists and "
                        "matches expected SHA-256"
                    )

                    send_message(client_socket, {
                        "type": "TRANSFER_OK",
                        "message": (
                            "File already exists "
                            "and is verified"
                        )
                    })

                    return

                print(
                    "Existing file has a different "
                    "SHA-256"
                )

            print(
                "Existing file will be replaced "
                "after successful verification"
            )

        # If starting a new upload, save metadata before
        # receiving file data.
        if offset == 0:
            save_partial_metadata(
                metadata_path,
                filename,
                file_size,
                expected_hash
            )

        # Tell the client where it should start.
        send_message(client_socket, {
            "type": "UPLOAD_READY",
            "filename": filename,
            "offset": offset
        })

        # Prepare SHA-256.
        sha256 = hashlib.sha256()

        # If resuming, hash the existing partial data first.
        if offset > 0:
            with partial_path.open("rb") as file:
                remaining_partial = offset

                while remaining_partial > 0:
                    chunk_size = min(
                        BUFFER_SIZE,
                        remaining_partial
                    )

                    chunk = file.read(chunk_size)

                    if not chunk:
                        raise ConnectionError(
                            "Unexpected end of partial file"
                        )

                    sha256.update(chunk)
                    remaining_partial -= len(chunk)

        remaining = file_size - offset

        # Append new data to the partial file.
        with partial_path.open("ab") as file:
            while remaining > 0:
                chunk_size = min(
                    BUFFER_SIZE,
                    remaining
                )

                chunk = receive_exact(
                    client_socket,
                    chunk_size
                )

                file.write(chunk)
                sha256.update(chunk)

                remaining -= len(chunk)

        actual_hash = sha256.hexdigest()

        print(f"Actual SHA-256: {actual_hash}")

        if actual_hash == expected_hash:
            print("TRANSFER VERIFIED")

            # Replace the final file only after
            # successful verification.
            partial_path.replace(output_path)

            # Metadata is no longer needed after
            # successful completion.
            if metadata_path.exists():
                metadata_path.unlink()

            send_message(client_socket, {
                "type": "TRANSFER_OK",
                "message": (
                    "File received and verified successfully"
                )
            })

        else:
            print(
                "TRANSFER FAILED: checksum mismatch"
            )

            send_message(client_socket, {
                "type": "TRANSFER_FAILED",
                "message": "Checksum mismatch"
            })

    finally:
        file_lock.release()


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


def handle_client(client_socket, client_address):
    print(f"Client connected: {client_address}")

    # Prevent a client from keeping a connection open
    # indefinitely without sending or receiving data.
    client_socket.settimeout(SOCKET_TIMEOUT)

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

    except socket.timeout:
        print(
            f"Client timed out after "
            f"{SOCKET_TIMEOUT} seconds: "
            f"{client_address}"
        )

    except Exception as error:
        print(
            f"Client error ({client_address}): {error}"
        )

    finally:
        client_socket.close()

        print(
            f"Client disconnected: {client_address}"
        )


def start_server():
    server_socket = socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM
    )

    server_socket.setsockopt(
        socket.SOL_SOCKET,
        socket.SO_REUSEADDR,
        1
    )

    server_socket.bind((HOST, PORT))
    server_socket.listen()

    print(
        f"Server listening on {HOST}:{PORT}"
    )

    try:
        while True:
            client_socket, client_address = (
                server_socket.accept()
            )

            client_thread = threading.Thread(
                target=handle_client,
                args=(
                    client_socket,
                    client_address
                ),
                daemon=True
            )

            client_thread.start()

    except KeyboardInterrupt:
        print("\nServer shutting down...")

    finally:
        server_socket.close()


if __name__ == "__main__":
    start_server()