import hashlib
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from common.protocol import receive_message, send_message


HOST = "127.0.0.1"
PORT = 5050

RECEIVED_DIR = Path("received_files")


def wait_for_server():
    for _ in range(50):
        sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM,
        )

        try:
            sock.connect((HOST, PORT))
            sock.close()
            return

        except ConnectionRefusedError:
            sock.close()
            time.sleep(0.1)

    raise RuntimeError("Server did not start")


def start_server():
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "server.server",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    wait_for_server()

    return process


def stop_server(process):
    if process.poll() is None:
        process.terminate()

        try:
            process.wait(timeout=5)

        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def connect_to_server():
    sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM,
    )

    sock.connect((HOST, PORT))

    return sock


def cleanup_files(*paths):
    for path in paths:
        path = Path(path)

        if path.exists():
            path.unlink()


def calculate_sha256(data):
    return hashlib.sha256(data).hexdigest()


def test_invalid_upload_request_is_rejected():
    process = start_server()
    sock = None

    try:
        sock = connect_to_server()

        send_message(
            sock,
            {
                "type": "UPLOAD",
                "filename": "",
                "size": 10,
                "sha256": "a" * 64,
            },
        )

        response = receive_message(sock)

        assert response["type"] == "UPLOAD_FAILED"
        assert response["message"] == (
            "Filename cannot be empty"
        )

    finally:
        if sock is not None:
            sock.close()

        stop_server(process)


def test_upload_checksum_mismatch_is_rejected(tmp_path):
    filename = "server-checksum-test.bin"

    output_path = RECEIVED_DIR / filename
    partial_path = RECEIVED_DIR / f"{filename}.part"
    metadata_path = RECEIVED_DIR / f"{filename}.part.json"

    cleanup_files(
        output_path,
        partial_path,
        metadata_path,
    )

    process = start_server()
    sock = None

    try:
        data = b"server checksum test"

        sock = connect_to_server()

        send_message(
            sock,
            {
                "type": "UPLOAD",
                "filename": filename,
                "size": len(data),
                "sha256": "0" * 64,
            },
        )

        response = receive_message(sock)

        assert response["type"] == "UPLOAD_READY"

        sock.sendall(data)

        response = receive_message(sock)

        assert response["type"] == "TRANSFER_FAILED"
        assert response["message"] == "Checksum mismatch"

        assert not output_path.exists()
        assert partial_path.exists()
        assert partial_path.read_bytes() == data

    finally:
        if sock is not None:
            sock.close()

        stop_server(process)

        cleanup_files(
            output_path,
            partial_path,
            metadata_path,
        )


def test_existing_verified_file_returns_transfer_ok(
    tmp_path,
):
    filename = "existing-verified.bin"

    output_path = RECEIVED_DIR / filename
    partial_path = RECEIVED_DIR / f"{filename}.part"
    metadata_path = RECEIVED_DIR / f"{filename}.part.json"

    cleanup_files(
        output_path,
        partial_path,
        metadata_path,
    )

    data = b"already verified file"

    output_path.write_bytes(data)

    process = start_server()
    sock = None

    try:
        sock = connect_to_server()

        send_message(
            sock,
            {
                "type": "UPLOAD",
                "filename": filename,
                "size": len(data),
                "sha256": calculate_sha256(data),
            },
        )

        response = receive_message(sock)

        assert response["type"] == "TRANSFER_OK"

        assert output_path.read_bytes() == data

    finally:
        if sock is not None:
            sock.close()

        stop_server(process)

        cleanup_files(
            output_path,
            partial_path,
            metadata_path,
        )


def test_existing_file_with_wrong_hash_is_replaced():
    filename = "replace-existing.bin"

    output_path = RECEIVED_DIR / filename
    partial_path = RECEIVED_DIR / f"{filename}.part"
    metadata_path = RECEIVED_DIR / f"{filename}.part.json"

    cleanup_files(
        output_path,
        partial_path,
        metadata_path,
    )

    old_data = b"old file contents"
    new_data = b"new file contents"

    output_path.write_bytes(old_data)

    process = start_server()
    sock = None

    try:
        sock = connect_to_server()

        send_message(
            sock,
            {
                "type": "UPLOAD",
                "filename": filename,
                "size": len(new_data),
                "sha256": calculate_sha256(new_data),
            },
        )

        response = receive_message(sock)

        assert response["type"] == "UPLOAD_READY"
        assert response["offset"] == 0

        sock.sendall(new_data)

        response = receive_message(sock)

        assert response["type"] == "TRANSFER_OK"
        assert output_path.read_bytes() == new_data

    finally:
        if sock is not None:
            sock.close()

        stop_server(process)

        cleanup_files(
            output_path,
            partial_path,
            metadata_path,
        )


def test_mismatched_partial_metadata_is_discarded():
    filename = "stale-partial.bin"

    output_path = RECEIVED_DIR / filename
    partial_path = RECEIVED_DIR / f"{filename}.part"
    metadata_path = RECEIVED_DIR / f"{filename}.part.json"

    cleanup_files(
        output_path,
        partial_path,
        metadata_path,
    )

    partial_path.write_bytes(b"old partial data")

    metadata_path.write_text(
        json.dumps(
            {
                "filename": filename,
                "size": 999,
                "sha256": "0" * 64,
            }
        ),
        encoding="utf-8",
    )

    process = start_server()
    sock = None

    try:
        new_data = b"new complete data"

        sock = connect_to_server()

        send_message(
            sock,
            {
                "type": "UPLOAD",
                "filename": filename,
                "size": len(new_data),
                "sha256": calculate_sha256(new_data),
            },
        )

        response = receive_message(sock)

        assert response["type"] == "UPLOAD_READY"
        assert response["offset"] == 0

        sock.sendall(new_data)

        response = receive_message(sock)

        assert response["type"] == "TRANSFER_OK"
        assert output_path.read_bytes() == new_data

    finally:
        if sock is not None:
            sock.close()

        stop_server(process)

        cleanup_files(
            output_path,
            partial_path,
            metadata_path,
        )


def test_oversized_partial_file_is_discarded():
    filename = "oversized-partial.bin"

    output_path = RECEIVED_DIR / filename
    partial_path = RECEIVED_DIR / f"{filename}.part"
    metadata_path = RECEIVED_DIR / f"{filename}.part.json"

    cleanup_files(
        output_path,
        partial_path,
        metadata_path,
    )

    partial_path.write_bytes(b"x" * 100)

    metadata_path.write_text(
        json.dumps(
            {
                "filename": filename,
                "size": 10,
                "sha256": "0" * 64,
            }
        ),
        encoding="utf-8",
    )

    process = start_server()
    sock = None

    try:
        data = b"small file"

        sock = connect_to_server()

        send_message(
            sock,
            {
                "type": "UPLOAD",
                "filename": filename,
                "size": len(data),
                "sha256": calculate_sha256(data),
            },
        )

        response = receive_message(sock)

        assert response["type"] == "UPLOAD_READY"
        assert response["offset"] == 0

        sock.sendall(data)

        response = receive_message(sock)

        assert response["type"] == "TRANSFER_OK"
        assert output_path.read_bytes() == data

    finally:
        if sock is not None:
            sock.close()

        stop_server(process)

        cleanup_files(
            output_path,
            partial_path,
            metadata_path,
        )


def test_orphan_partial_metadata_is_removed():
    filename = "orphan-metadata.bin"

    output_path = RECEIVED_DIR / filename
    partial_path = RECEIVED_DIR / f"{filename}.part"
    metadata_path = RECEIVED_DIR / f"{filename}.part.json"

    cleanup_files(
        output_path,
        partial_path,
        metadata_path,
    )

    metadata_path.write_text(
        json.dumps(
            {
                "filename": filename,
                "size": 10,
                "sha256": "0" * 64,
            }
        ),
        encoding="utf-8",
    )

    process = start_server()
    sock = None

    try:
        data = b"fresh data"

        sock = connect_to_server()

        send_message(
            sock,
            {
                "type": "UPLOAD",
                "filename": filename,
                "size": len(data),
                "sha256": calculate_sha256(data),
            },
        )

        response = receive_message(sock)

        assert response["type"] == "UPLOAD_READY"
        assert response["offset"] == 0

        sock.sendall(data)

        response = receive_message(sock)

        assert response["type"] == "TRANSFER_OK"
        assert output_path.read_bytes() == data

    finally:
        if sock is not None:
            sock.close()

        stop_server(process)

        cleanup_files(
            output_path,
            partial_path,
            metadata_path,
        )


def test_missing_download_file_is_rejected():
    filename = "does-not-exist.bin"

    output_path = RECEIVED_DIR / filename

    cleanup_files(output_path)

    process = start_server()
    sock = None

    try:
        sock = connect_to_server()

        send_message(
            sock,
            {
                "type": "DOWNLOAD",
                "filename": filename,
            },
        )

        response = receive_message(sock)

        assert response["type"] == "DOWNLOAD_FAILED"
        assert response["message"] == "File not found"

    finally:
        if sock is not None:
            sock.close()

        stop_server(process)


def test_invalid_download_filename_is_rejected():
    process = start_server()
    sock = None

    try:
        sock = connect_to_server()

        send_message(
            sock,
            {
                "type": "DOWNLOAD",
                "filename": "",
            },
        )

        response = receive_message(sock)

        assert response["type"] == "DOWNLOAD_FAILED"
        assert response["message"] == (
            "Filename cannot be empty"
        )

    finally:
        if sock is not None:
            sock.close()

        stop_server(process)


def test_download_verification_failure_is_handled():
    filename = "verification-failure.bin"

    output_path = RECEIVED_DIR / filename

    cleanup_files(output_path)

    data = b"download verification test"
    output_path.write_bytes(data)

    process = start_server()
    sock = None

    try:
        sock = connect_to_server()

        send_message(
            sock,
            {
                "type": "DOWNLOAD",
                "filename": filename,
            },
        )

        response = receive_message(sock)

        assert response["type"] == "DOWNLOAD_READY"

        received_data = b""

        while len(received_data) < response["size"]:
            received_data += sock.recv(
                response["size"] - len(received_data)
            )

        assert received_data == data

        send_message(
            sock,
            {
                "type": "DOWNLOAD_FAILED",
                "message": "Checksum mismatch",
            },
        )

        time.sleep(0.1)

    finally:
        if sock is not None:
            sock.close()

        stop_server(process)

        cleanup_files(output_path)


def test_unsupported_operation_returns_error():
    process = start_server()
    sock = None

    try:
        sock = connect_to_server()

        send_message(
            sock,
            {
                "type": "UNKNOWN_OPERATION",
            },
        )

        response = receive_message(sock)

        assert response["type"] == "ERROR"
        assert response["message"] == "Unsupported operation"

    finally:
        if sock is not None:
            sock.close()

        stop_server(process)


def test_non_object_upload_request_is_rejected():
    process = start_server()
    sock = None

    try:
        sock = connect_to_server()

        send_message(
            sock,
            {
                "type": "UPLOAD",
            },
        )

        response = receive_message(sock)

        assert response["type"] == "UPLOAD_FAILED"

    finally:
        if sock is not None:
            sock.close()

        stop_server(process)


def test_non_object_download_request_is_rejected():
    process = start_server()
    sock = None

    try:
        sock = connect_to_server()

        send_message(
            sock,
            {
                "type": "DOWNLOAD",
            },
        )

        response = receive_message(sock)

        assert response["type"] == "DOWNLOAD_FAILED"

    finally:
        if sock is not None:
            sock.close()

        stop_server(process)

def test_server_shuts_down_cleanly_on_sigint():
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "server.server",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        wait_for_server()

        process.send_signal(
            __import__("signal").SIGINT
        )

        stdout, stderr = process.communicate(
            timeout=5
        )

        assert process.returncode == 0

        combined_output = stdout + stderr

        assert "Server shutting down..." in combined_output

    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
