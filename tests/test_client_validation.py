import pytest

from client.client import validate_download_response


def test_valid_download_response():
    response = {
        "type": "DOWNLOAD_READY",
        "filename": "test.bin",
        "size": 100,
        "sha256": "a" * 64,
    }

    valid, error = validate_download_response(response)

    assert valid is True
    assert error is None


@pytest.mark.parametrize(
    "response, expected_error",
    [
        (
            None,
            "Response must be a JSON object",
        ),
        (
            {},
            "Response type is missing",
        ),
        (
            {
                "type": "ERROR",
                "message": "Something went wrong",
            },
            "Unexpected response type: ERROR",
        ),
        (
            {
                "type": "DOWNLOAD_READY",
                "filename": "test.bin",
                "size": -1,
                "sha256": "a" * 64,
            },
            "File size must be a non-negative integer",
        ),
        (
            {
                "type": "DOWNLOAD_READY",
                "filename": "test.bin",
                "size": "100",
                "sha256": "a" * 64,
            },
            "File size must be a non-negative integer",
        ),
        (
            {
                "type": "DOWNLOAD_READY",
                "filename": "test.bin",
                "size": 100,
                "sha256": "abc123",
            },
            "SHA-256 must contain exactly 64 characters",
        ),
        (
            {
                "type": "DOWNLOAD_READY",
                "filename": "test.bin",
                "size": 100,
                "sha256": "z" * 64,
            },
            "SHA-256 contains invalid hexadecimal characters",
        ),
        (
            {
                "type": "DOWNLOAD_READY",
                "filename": "",
                "size": 100,
                "sha256": "a" * 64,
            },
            "Filename must be a non-empty string",
        ),
        (
            {
                "type": "DOWNLOAD_READY",
                "filename": None,
                "size": 100,
                "sha256": "a" * 64,
            },
            "Filename must be a non-empty string",
        ),
    ],
)
def test_invalid_download_responses(
    response,
    expected_error,
):
    valid, error = validate_download_response(response)

    assert valid is False
    assert error == expected_error