from client import client


def test_upload_retries_after_connection_error(
    tmp_path,
    monkeypatch,
):
    test_file = tmp_path / "retry-test.bin"
    test_file.write_bytes(b"test data")

    attempts = []

    def fake_upload_attempt(
        file_path,
        file_size,
        file_hash,
        attempt_number,
        test_interrupt_bytes=None,
    ):
        attempts.append(attempt_number)

        if attempt_number == 1:
            raise ConnectionError(
                "Simulated connection failure"
            )

        return True

    monkeypatch.setattr(
        client,
        "upload_attempt",
        fake_upload_attempt,
    )

    monkeypatch.setattr(
        client,
        "RETRY_DELAY",
        0,
    )

    client.upload_file(test_file)

    assert attempts == [1, 2]


def test_upload_stops_after_max_retries(
    tmp_path,
    monkeypatch,
):
    test_file = tmp_path / "retry-fail-test.bin"
    test_file.write_bytes(b"test data")

    attempts = []

    def fake_upload_attempt(
        file_path,
        file_size,
        file_hash,
        attempt_number,
        test_interrupt_bytes=None,
    ):
        attempts.append(attempt_number)

        raise ConnectionError(
            "Simulated connection failure"
        )

    monkeypatch.setattr(
        client,
        "upload_attempt",
        fake_upload_attempt,
    )

    monkeypatch.setattr(
        client,
        "RETRY_DELAY",
        0,
    )

    client.upload_file(test_file)

    assert attempts == [
        1,
        2,
        3,
    ]