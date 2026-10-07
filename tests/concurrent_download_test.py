import subprocess
import sys


def main():
    command = [
        sys.executable,
        "-m",
        "client.client",
        "download",
        "test-100mb.bin",
    ]

    client_1 = subprocess.Popen(command)
    client_2 = subprocess.Popen(command)

    client_1.wait()
    client_2.wait()

    print("\nBoth clients finished.")


if __name__ == "__main__":
    main()