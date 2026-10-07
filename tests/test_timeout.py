import socket
import subprocess
import sys
import time
from pathlib import Path

from common.protocol import send_message, receive_message


HOST = "127.0.0.1"
PORT = 5050

TEST_TIMEOUT = 1


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


def test_upload_timeout_preserves_partial_file(tmp_path):
    test_filename = "timeout-test.bin"

    partial_path = Path(
        "received_files",
        f"{test_filename}.part"
    )

    metadata_path = Path(
        "received_files",
        f"{test_filename}.part.json"
    )

    output_path = Path(
        "received_files",
        test_filename
    )

    for path in (
        partial_path,
        metadata_path,
        output_path,
    ):
        if path.exists():
            path.unlink()

    server_process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import server.server as server; "
                f"server.SOCKET_TIMEOUT = {TEST_TIMEOUT}; "
                "server.start_server()"
            ),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    sock = None

    try:
        wait_for_server()

        sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM
        )

        sock.connect((HOST, PORT))

        send_message(sock, {
            "type": "UPLOAD",
            "filename": test_filename,
            "size": 1024 * 1024,
            "sha256": "a" * 64,
        })

        response = receive_message(sock)

        assert response["type"] == "UPLOAD_READY"
        assert response["offset"] == 0

        # Do not send file data.
        # The server should timeout after TEST_TIMEOUT seconds.
        start = time.monotonic()

        time.sleep(TEST_TIMEOUT + 0.5)

        elapsed = time.monotonic() - start

        assert elapsed < 3

        assert partial_path.exists()
        assert metadata_path.exists()

        assert partial_path.stat().st_size == 0

    finally:
        if sock is not None:
            sock.close()

        if server_process.poll() is None:
            server_process.terminate()

            try:
                server_process.wait(timeout=5)

            except subprocess.TimeoutExpired:
                server_process.kill()
                server_process.wait()

        for path in (
            partial_path,
            metadata_path,
            output_path,
        ):
            if path.exists():
                path.unlink()