import hashlib
import socket
import subprocess
import sys
import time
from pathlib import Path

from common.protocol import (
    receive_exact,
    receive_message,
    send_message,
)


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


def wait_for_server():
    for _ in range(50):
        sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM
        )

        try:
            sock.connect((HOST, PORT))
            sock.close()
            return

        except ConnectionRefusedError:
            sock.close()
            time.sleep(0.1)

    raise RuntimeError("Server did not start")


def download_file(filename, output_path):
    sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM
    )

    try:
        sock.connect((HOST, PORT))

        send_message(sock, {
            "type": "DOWNLOAD",
            "filename": filename,
        })

        response = receive_message(sock)

        assert response["type"] == "DOWNLOAD_READY"

        file_size = response["size"]
        expected_hash = response["sha256"]

        sha256 = hashlib.sha256()

        remaining = file_size

        with output_path.open("wb") as file:
            while remaining > 0:
                chunk_size = min(
                    BUFFER_SIZE,
                    remaining
                )

                chunk = receive_exact(
                    sock,
                    chunk_size
                )

                file.write(chunk)
                sha256.update(chunk)

                remaining -= len(chunk)

        actual_hash = sha256.hexdigest()

        assert actual_hash == expected_hash

        send_message(sock, {
            "type": "DOWNLOAD_VERIFIED"
        })

        return actual_hash

    finally:
        sock.close()


def test_concurrent_downloads(tmp_path):
    filename = "concurrency-test.bin"

    server_file = Path(
        "received_files",
        filename
    )

    download_1 = tmp_path / "download-1.bin"
    download_2 = tmp_path / "download-2.bin"

    if server_file.exists():
        server_file.unlink()

    server_process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "server.server",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )

    process_1 = None
    process_2 = None

    try:
        wait_for_server()

        data = (
            b"concurrent-download-test-data"
            * 32768
        )

        server_file.write_bytes(data)

        expected_hash = calculate_sha256(
            server_file
        )

        command_1 = [
            sys.executable,
            "-c",
            (
                "from pathlib import Path; "
                "from tests.test_concurrency import "
                "download_file; "
                "download_file("
                f"'{filename}', "
                f"Path(r'{download_1}'))"
            ),
        ]

        command_2 = [
            sys.executable,
            "-c",
            (
                "from pathlib import Path; "
                "from tests.test_concurrency import "
                "download_file; "
                "download_file("
                f"'{filename}', "
                f"Path(r'{download_2}'))"
            ),
        ]

        process_1 = subprocess.Popen(
            command_1
        )

        process_2 = subprocess.Popen(
            command_2
        )

        result_1 = process_1.wait()
        result_2 = process_2.wait()

        if result_1 != 0 or result_2 != 0:
            server_error = ""

            if server_process.stderr is not None:
                server_error = server_process.stderr.read()

            raise AssertionError(
                "One or both download clients failed.\n"
                f"Client 1 exit code: {result_1}\n"
                f"Client 2 exit code: {result_2}\n"
                f"Server stderr:\n{server_error}"
            )

        assert download_1.exists()
        assert download_2.exists()

        assert (
            calculate_sha256(download_1)
            == expected_hash
        )

        assert (
            calculate_sha256(download_2)
            == expected_hash
        )

        assert download_1.read_bytes() == data
        assert download_2.read_bytes() == data

    finally:
        if process_1 is not None:
            process_1.terminate()

        if process_2 is not None:
            process_2.terminate()

        if server_process.poll() is None:
            server_process.terminate()

            try:
                server_process.wait(timeout=5)

            except subprocess.TimeoutExpired:
                server_process.kill()
                server_process.wait()

        if process_1 is not None:
            process_1.wait()

        if process_2 is not None:
            process_2.wait()

        if server_file.exists():
            server_file.unlink()