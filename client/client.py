import hashlib
import socket
import sys
import time
from pathlib import Path

from common.protocol import send_message, receive_message, receive_exact
from common.validation import (
    validate_filename,
    validate_file_size,
    validate_sha256,
)


HOST = "127.0.0.1"
PORT = 5050

BUFFER_SIZE = 64 * 1024

SOCKET_TIMEOUT = 30

MAX_RETRIES = 3
RETRY_DELAY = 2

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)


def create_connection():
    sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM
    )

    sock.settimeout(SOCKET_TIMEOUT)
    sock.connect((HOST, PORT))

    return sock


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


def validate_download_response(response):
    if not isinstance(response, dict):
        return False, "Response must be a JSON object"

    response_type = response.get("type")

    if response_type is None:
        return False, "Response type is missing"

    if response_type != "DOWNLOAD_READY":
        return False, f"Unexpected response type: {response_type}"

    filename = response.get("filename")

    valid_filename, filename_error = validate_filename(
        filename
    )

    if not valid_filename:
        return False, "Filename must be a non-empty string"

    file_size = response.get("size")

    valid_size, size_error = validate_file_size(
        file_size
    )

    if not valid_size:
        return False, "File size must be a non-negative integer"

    expected_hash = response.get("sha256")

    valid_hash, hash_error = validate_sha256(
        expected_hash
    )

    if not valid_hash:
        return False, hash_error

    return True, None


def upload_attempt(
    file_path,
    file_size,
    file_hash,
    attempt_number,
    test_interrupt_bytes=None,
):
    sock = create_connection()

    try:
        print(
            f"Connected to {HOST}:{PORT} "
            f"(attempt {attempt_number})"
        )

        message = {
            "type": "UPLOAD",
            "filename": file_path.name,
            "size": file_size,
            "sha256": file_hash,
        }

        send_message(sock, message)

        response = receive_message(sock)

        if response.get("type") == "TRANSFER_OK":
            print(
                "Server reports that the file "
                "is already verified"
            )
            return True

        if response.get("type") != "UPLOAD_READY":
            raise RuntimeError(
                f"Unexpected server response: {response}"
            )

        offset = response.get("offset", 0)

        if offset < 0 or offset > file_size:
            raise RuntimeError(
                f"Invalid resume offset from server: {offset}"
            )

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
            file.seek(offset)

            while True:
                remaining_to_send = file_size - bytes_sent

                if remaining_to_send <= 0:
                    break

                if (
                    test_interrupt_bytes is not None
                    and attempt_number == 1
                ):
                    remaining_before_interrupt = (
                        test_interrupt_bytes - bytes_sent
                    )

                    if remaining_before_interrupt <= 0:
                        print(
                            "\nTest interruption: "
                            "closing connection intentionally"
                        )

                        raise ConnectionError(
                            "Intentional test interruption"
                        )

                    chunk_size = min(
                        BUFFER_SIZE,
                        remaining_to_send,
                        remaining_before_interrupt,
                    )

                else:
                    chunk_size = min(
                        BUFFER_SIZE,
                        remaining_to_send,
                    )

                chunk = file.read(chunk_size)

                if not chunk:
                    break

                sock.sendall(chunk)

                bytes_sent += len(chunk)

                elapsed = time.monotonic() - start_time

                transferred_this_attempt = bytes_sent - offset

                speed = (
                    transferred_this_attempt / elapsed
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

                if (
                    test_interrupt_bytes is not None
                    and attempt_number == 1
                    and bytes_sent >= test_interrupt_bytes
                ):
                    print(
                        "\nTest interruption: "
                        "closing connection intentionally"
                    )

                    raise ConnectionError(
                        "Intentional test interruption"
                    )

        elapsed = time.monotonic() - start_time

        print()
        print(
            f"Upload attempt completed in "
            f"{elapsed:.2f}s"
        )

        if elapsed > 0:
            transferred_this_attempt = bytes_sent - offset
            average_speed = transferred_this_attempt / elapsed

            print(
                f"Attempt average speed: "
                f"{format_bytes(average_speed)}/s"
            )

        response = receive_message(sock)

        if response.get("type") == "TRANSFER_OK":
            print("Server verified the file successfully")
            return True

        if response.get("type") == "TRANSFER_FAILED":
            print("Server rejected the file")
            print(response.get("message"))
            return False

        raise RuntimeError(
            f"Unexpected server response: {response}"
        )

    finally:
        sock.close()


def upload_file(file_path, test_interrupt_mb=None):
    file_path = Path(file_path)

    if not file_path.is_file():
        raise FileNotFoundError(
            f"File not found: {file_path}"
        )

    file_size = file_path.stat().st_size
    file_hash = calculate_sha256(file_path)

    print(f"Preparing upload: {file_path.name}")
    print(f"Size: {format_bytes(file_size)}")
    print(f"SHA-256: {file_hash}")

    test_interrupt_bytes = None

    if test_interrupt_mb is not None:
        test_interrupt_bytes = (
            test_interrupt_mb * 1024 * 1024
        )

        if test_interrupt_bytes >= file_size:
            raise ValueError(
                "Test interruption point must be "
                "smaller than the file size."
            )

        print(
            f"TEST MODE: connection will be "
            f"interrupted after "
            f"{format_bytes(test_interrupt_bytes)}"
        )

    for attempt in range(1, MAX_RETRIES + 1):
        print()
        print(
            f"Upload attempt {attempt}/{MAX_RETRIES}"
        )

        try:
            success = upload_attempt(
                file_path,
                file_size,
                file_hash,
                attempt,
                test_interrupt_bytes,
            )

            if success:
                return

            print("Upload failed.")
            return

        except (
            ConnectionError,
            BrokenPipeError,
            ConnectionResetError,
            socket.timeout,
            OSError,
        ) as error:
            print()
            print(
                f"Connection error during attempt "
                f"{attempt}: {error}"
            )

            if attempt == MAX_RETRIES:
                print(
                    "Maximum retry count reached. "
                    "Upload failed."
                )
                return

            print(
                f"Retrying in {RETRY_DELAY} seconds..."
            )

            time.sleep(RETRY_DELAY)

        except Exception as error:
            print()
            print(f"Upload failed: {error}")
            return


def download_file(filename):
    filename = Path(filename).name

    sock = create_connection()

    try:
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

        valid, error_message = validate_download_response(
            response
        )

        if not valid:
            print(
                "Invalid server response:",
                error_message
            )
            return

        print(f"Downloading: {filename}")

        file_size = response["size"]
        expected_hash = response["sha256"]

        output_path = DOWNLOAD_DIR / filename

        print(f"Size: {format_bytes(file_size)}")
        print(f"SHA-256: {expected_hash}")

        sha256 = hashlib.sha256()

        remaining = file_size
        bytes_received = 0

        start_time = time.monotonic()

        with output_path.open("wb") as file:
            while remaining > 0:
                chunk_size = min(
                    BUFFER_SIZE,
                    remaining,
                )

                chunk = receive_exact(
                    sock,
                    chunk_size,
                )

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
        print(
            f"Download completed in "
            f"{elapsed:.2f}s"
        )

        print(
            f"Actual SHA-256: {actual_hash}"
        )

        if actual_hash == expected_hash:
            print("DOWNLOAD VERIFIED")

            send_message(sock, {
                "type": "DOWNLOAD_VERIFIED"
            })

        else:
            print(
                "DOWNLOAD FAILED: "
                "checksum mismatch"
            )

            send_message(sock, {
                "type": "DOWNLOAD_FAILED",
                "message": "Checksum mismatch",
            })

    finally:
        sock.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            "Usage:\n"
            "  python3 -m client.client upload <file>\n"
            "  python3 -m client.client upload <file> "
            "--test-interrupt <MB>\n"
            "  python3 -m client.client download <file>"
        )
        sys.exit(1)

    command = sys.argv[1]

    if (
        command == "upload"
        and len(sys.argv) == 3
    ):
        upload_file(sys.argv[2])

    elif (
        command == "upload"
        and len(sys.argv) == 5
        and sys.argv[3] == "--test-interrupt"
    ):
        try:
            interrupt_mb = int(sys.argv[4])
        except ValueError:
            print(
                "Error: interrupt size must be "
                "an integer number of MB."
            )
            sys.exit(1)

        upload_file(
            sys.argv[2],
            test_interrupt_mb=interrupt_mb,
        )

    elif (
        command == "download"
        and len(sys.argv) == 3
    ):
        download_file(sys.argv[2])

    else:
        print(
            "Usage:\n"
            "  python3 -m client.client upload <file>\n"
            "  python3 -m client.client upload <file> "
            "--test-interrupt <MB>\n"
            "  python3 -m client.client download <file>"
        )
        sys.exit(1)