import socket
import time

from common.protocol import send_message, receive_message


HOST = "127.0.0.1"
PORT = 5050

TIMEOUT_WAIT = 35


def main():
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
            "filename": "timeout-test.bin",
            "size": 1024 * 1024,
            "sha256": "a" * 64,
        })

        response = receive_message(sock)

        print(
            f"Server response: {response}"
        )

        if response.get("type") != "UPLOAD_READY":
            print("Server did not allow the test upload.")
            return

        print()
        print(
            f"Upload accepted. Sending no data."
        )

        print(
            f"Waiting {TIMEOUT_WAIT} seconds "
            f"for server timeout..."
        )

        start = time.monotonic()

        try:
            sock.recv(1)

        except socket.timeout:
            elapsed = time.monotonic() - start

            print(
                f"Client-side socket timeout after "
                f"{elapsed:.2f}s"
            )

        time.sleep(2)

        print(
            "Timeout test connection finished."
        )

    finally:
        sock.close()


if __name__ == "__main__":
    main()