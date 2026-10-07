# Reliable File Transfer

A TCP client-server file transfer system written in Python using only the standard library. Every transfer is checked end to end with SHA-256. Interrupted uploads resume where they stopped. The server handles many clients at once and keeps concurrent writers from corrupting each other's data.

The project focuses on how a transfer behaves when things go wrong: dropped connections, stalled peers, stale partial data, malformed messages and concurrent writers.

## Key Features

- **Custom length-prefixed JSON protocol** over raw TCP, with a 1 MB message size limit
- **SHA-256 verification** of every upload and download
- **Resumable uploads** that continue from the last byte the server received
- **Automatic upload retry**: up to 3 attempts, each one resuming instead of starting over
- **Temporary `.part` files**, so a final file only appears after it passes verification
- **Concurrent clients**, with one server thread per connection
- **Per-file upload locking**, so two clients can't write the same file at once
- **Socket timeouts**, so stalled peers can't hold resources indefinitely
- **Input validation**, including protection against path traversal
- **Graceful shutdown** on `Ctrl+C`
- **58 passing tests**, including integration tests against the real server process

## Architecture

| Component | Responsibility | Communication / Storage |
|---|---|---|
| `client/client.py` | CLI client: uploads with retry and resume, downloads with SHA-256 verification | TCP → server |
| `server/server.py` | Accepts connections, handles uploads and downloads, per-file locking, verification | TCP ← clients, one thread per connection |
| `common/protocol.py` | Length-prefixed JSON message framing and the 1 MB message limit | Shared by client and server |
| `common/validation.py` | Shared filename, size and SHA-256 validation | Shared by client and server |
| `received_files/` | Uploaded files, plus `.part` and `.part.json` upload state | Server-side storage |
| `downloads/` | Downloaded files, plus `.part` files for in-progress downloads | Client-side storage |

The client connects to the server over TCP at `127.0.0.1:5050`. Each connection carries exactly one operation, either `UPLOAD` or `DOWNLOAD`. Length-prefixed JSON control messages set up the transfer. Once the handshake completes, the file contents are streamed as raw bytes in 64 KB chunks. The server accepts connections in a loop and hands each one to its own thread, so multiple clients can transfer files at the same time.

## Project Structure

| Path | Contents |
|---|---|
| `client/client.py` | CLI client: upload (retry + resume) and download |
| `server/server.py` | Threaded TCP server, upload/download handlers, locking |
| `common/protocol.py` | Length-prefixed JSON message framing |
| `common/validation.py` | Filename, size and SHA-256 validation |
| `tests/` | Unit and integration tests |
| `requirements.txt` | Test dependencies |
| `pytest.ini` | pytest configuration |

## Protocol

Each control message is a UTF-8 JSON object preceded by a 4-byte big-endian length header:

| Field | Size | Description |
|---|---|---|
| Length header | 4 bytes | Big-endian length of the payload |
| JSON payload | Up to 1 MB | UTF-8 encoded JSON object |

The receiver reads exactly the advertised number of bytes. This handles TCP's stream semantics, where a single read can return a partial message.

**Message limits:** the receiver checks the length header *before* reading the body. Messages that are oversized, empty, not valid UTF-8 or not valid JSON are rejected. A corrupt or malicious header therefore can't make the receiver allocate unbounded memory.

### Upload flow

| Step | Client | Server |
|---|---|---|
| 1 | Calculates file size and SHA-256 | |
| 2 | Sends `UPLOAD` with filename, size and SHA-256 | Validates the request |
| 3 | | Acquires the per-file lock without blocking, or rejects with `UPLOAD_FAILED` |
| 4 | | Checks existing `.part` data against its `.part.json` metadata and discards stale state |
| 5 | Receives `UPLOAD_READY` with the offset | Sends the resume offset (0 for a new upload) |
| 6 | Sends file bytes starting from the offset | Appends to `.part` and hashes the data |
| 7 | | Verifies the SHA-256 of the complete file |
| 8 | Receives `TRANSFER_OK` or `TRANSFER_FAILED` | On success, renames `.part` to the final file |

If the server already has an identical file (same size and hash), it replies `TRANSFER_OK` right away and the client sends no data.

### Download flow

| Step | Client | Server |
|---|---|---|
| 1 | Sends `DOWNLOAD` with the filename | Validates the filename and checks that the file exists |
| 2 | Receives and validates `DOWNLOAD_READY` | Sends the file size and SHA-256 |
| 3 | Writes incoming data to `.part` and hashes it | Streams the file bytes |
| 4 | Compares the calculated SHA-256 with the expected value | |
| 5 | On a match, renames `.part` to the final file | |
| 6 | Sends `DOWNLOAD_VERIFIED` or `DOWNLOAD_FAILED` | Receives and logs the result |

## Reliability Design

**SHA-256 verification.** The sender hashes the file before the transfer, and the receiver hashes it incrementally as chunks arrive. The server checks uploads and the client checks downloads. A mismatch never produces a final file.

**Resumable uploads.** The server writes incoming data to `<file>.part` and flushes after every chunk. Next to it, a `<file>.part.json` sidecar records the upload's name, size and hash. When the client reconnects, the server resumes from the current `.part` size, but only if the metadata matches the new request. Partial data that is stale, oversized or has no metadata is discarded, so bytes from a different version of a file are never combined. When it resumes, the server re-hashes the bytes already on disk so the final checksum covers the whole file.

**Downloads are not resumable.** An interrupted download keeps its `.part` file, but the next attempt starts again from byte 0.

**Automatic retry.** Uploads are retried up to 3 times, with a 2-second delay between attempts, and only on connection-level errors such as resets, timeouts and refused connections. Each retry opens a new connection, so it resumes from the server's offset automatically. Checksum mismatches and rejected requests are not retried because retrying would not change the outcome.

**Concurrency and locking.** Each client connection runs in its own thread. Uploads take a per-filename lock in non-blocking mode. A second client that tries to upload the same file is rejected immediately instead of being queued, so two writers can never append to the same `.part` file.

**Timeouts.** Both sides use 30-second socket timeouts. A client that stalls mid-upload is disconnected, which releases its thread and its lock. The partial data stays on disk so the upload can be resumed.

**Safe file replacement.** Neither side writes directly to the final path. Data goes to a `.part` file, which is moved into place with an atomic rename only after verification succeeds. A file on disk is therefore either the previous version or the new verified one, never a half-written copy.

**Validation.** Shared validators reject empty, non-string or path-containing filenames (for example `../../secret.txt`), negative or non-integer sizes, and malformed SHA-256 values. The server validates every request. The client validates the server's download response before trusting it.

**Graceful shutdown.** On `Ctrl+C`, the server logs the shutdown, closes the listening socket and exits cleanly. Transfers still in progress are dropped rather than awaited. Interrupted uploads can be resumed after the server restarts.

## Getting Started

Requires Python 3.9 or newer. The application uses only the standard library. The dependencies in `requirements.txt` are needed only to run the tests.

```bash
git clone <repository-url>
cd network-file-transfer

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run all commands from the project root. The server listens on `127.0.0.1:5050`.

**Start the server.** Received files are stored in `received_files/`:

```bash
python3 -m server.server
```

**Upload and download.** Downloads are saved to `downloads/`:

```bash
python3 -m client.client upload path/to/file.bin
python3 -m client.client download file.bin
```

The client shows live progress and throughput while a transfer runs, then prints the verification result.

**Demonstrate resume and retry.** This command deliberately drops the connection after 30 MB on the first attempt. The automatic retry then resumes from the server's offset:

```bash
python3 -m client.client upload large-file.bin --test-interrupt 30
```

## Testing

```bash
python3 -m pytest
```

The suite contains **58 passing tests**:

- **Unit tests** cover protocol framing, message size limits, malformed input, validation, client-side download verification and retry behaviour.
- **Integration tests** start the real server as a subprocess and test it over TCP. They cover resumable uploads, per-file locking, concurrent downloads, socket timeouts, stale partial-state handling, checksum mismatches and SIGINT shutdown.

The integration tests use port 5050, so stop any running server before you run the suite.

To generate a coverage report:

```bash
python3 -m pytest --cov=client --cov=server --cov=common --cov-report=term-missing
```

The report measures only the test process itself. Server code that runs in the integration-test subprocess is not counted, so the reported server coverage is lower than what the tests actually exercise.

## Technologies

- Python 3: `socket`, `threading`, `hashlib`, `struct`, `json`, `pathlib`, `logging`
- pytest and pytest-cov

## Known Limitations

- Downloads are neither resumable nor retried.
- After an upload fails its checksum, the stale partial data remains on the server and blocks later uploads of the same file until it is removed manually.
- The host, port and timeouts are hard-coded.
- Traffic is not encrypted or authenticated.

## Future Improvements

- Resumable downloads with retry
- Automatic cleanup of partial data after a checksum mismatch, and of abandoned `.part` files
- Configurable host, port, directories and timeouts
- Subprocess-aware coverage measurement and ephemeral ports in integration tests
- TLS and client authentication
