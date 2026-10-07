import pytest

from server.server import (
    validate_filename,
    validate_upload_message,
)


def test_valid_filename():
    valid, error = validate_filename("test.bin")

    assert valid is True
    assert error is None


@pytest.mark.parametrize(
    "filename, expected_error",
    [
        (
            "",
            "Filename cannot be empty",
        ),
        (
            "   ",
            "Filename cannot be empty",
        ),
        (
            123,
            "Filename must be a string",
        ),
        (
            ".",
            "Invalid filename",
        ),
        (
            "..",
            "Invalid filename",
        ),
        (
            "../../secret.txt",
            "Path separators are not allowed in filename",
        ),
    ],
)
def test_invalid_filenames(filename, expected_error):
    valid, error = validate_filename(filename)

    assert valid is False
    assert error == expected_error


def test_valid_upload_message():
    message = {
        "type": "UPLOAD",
        "filename": "test.bin",
        "size": 100,
        "sha256": "a" * 64,
    }

    valid, error = validate_upload_message(message)

    assert valid is True
    assert error is None


@pytest.mark.parametrize(
    "message, expected_error",
    [
        (
            {
                "type": "UPLOAD",
                "filename": "",
                "size": 100,
                "sha256": "a" * 64,
            },
            "Filename cannot be empty",
        ),
        (
            {
                "type": "UPLOAD",
                "filename": "test.bin",
                "size": -1,
                "sha256": "a" * 64,
            },
            "File size cannot be negative",
        ),
        (
            {
                "type": "UPLOAD",
                "filename": "test.bin",
                "size": 100,
                "sha256": "abc123",
            },
            "SHA-256 must contain exactly 64 characters",
        ),
        (
            {
                "type": "UPLOAD",
                "filename": "test.bin",
                "size": 100,
                "sha256": "z" * 64,
            },
            "SHA-256 contains invalid hexadecimal characters",
        ),
        (
            {
                "type": "UPLOAD",
                "filename": "../../secret.txt",
                "size": 100,
                "sha256": "a" * 64,
            },
            "Path separators are not allowed in filename",
        ),
    ],
)
def test_invalid_upload_messages(message, expected_error):
    valid, error = validate_upload_message(message)

    assert valid is False
    assert error == expected_error


def test_filename_must_be_string():
    message = {
        "type": "UPLOAD",
        "filename": 123,
        "size": 100,
        "sha256": "a" * 64,
    }

    valid, error = validate_upload_message(message)

    assert valid is False
    assert error == "Filename must be a string"


def test_file_size_must_be_integer():
    message = {
        "type": "UPLOAD",
        "filename": "test.bin",
        "size": "100",
        "sha256": "a" * 64,
    }

    valid, error = validate_upload_message(message)

    assert valid is False
    assert error == "File size must be a non-negative integer"


def test_sha256_must_be_string():
    message = {
        "type": "UPLOAD",
        "filename": "test.bin",
        "size": 100,
        "sha256": 123,
    }

    valid, error = validate_upload_message(message)

    assert valid is False
    assert error == "SHA-256 must be a string"