import socket

from common.protocol import send_message, receive_message


HOST = "127.0.0.1"
PORT = 5050


TEST_CASES = [
    (
        "Empty filename",
        {
            "type": "UPLOAD",
            "filename": "",
            "size": 100,
            "sha256": "a" * 64,
        },
    ),
    (
        "Negative file size",
        {
            "type": "UPLOAD",
            "filename": "test.bin",
            "size": -1,
            "sha256": "a" * 64,
        },
    ),
    (
        "Invalid SHA-256 length",
        {
            "type": "UPLOAD",
            "filename": "test.bin",
            "size": 100,
            "sha256": "abc123",
        },
    ),
    (
        "Invalid SHA-256 characters",
        {
            "type": "UPLOAD",
            "filename": "test.bin",
            "size": 100,
            "sha256": "z" * 64,
        },
    ),
    (
        "Path traversal",
        {
            "type": "UPLOAD",
            "filename": "../../secret.txt",
            "size": 100,
            "sha256": "a" * 64,
        },
    ),
]


def run_test(name, message):
    print()
    print(f"Test: {name}")

    sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM
    )

    try:
        sock.connect((HOST, PORT))

        send_message(sock, message)

        response = receive_message(sock)

        print(f"Server response: {response}")

        if response.get("type") == "UPLOAD_FAILED":
            print("PASS")

        else:
            print("FAIL")

    finally:
        sock.close()


def main():
    for name, message in TEST_CASES:
        run_test(name, message)

    print()
    print("Malformed upload tests completed.")


if __name__ == "__main__":
    main()