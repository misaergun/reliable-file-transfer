from pathlib import Path


def validate_filename(filename):
    if not isinstance(filename, str):
        return False, "Filename must be a string"

    filename = filename.strip()

    if not filename:
        return False, "Filename cannot be empty"

    if filename in {".", ".."}:
        return False, "Invalid filename"

    if Path(filename).name != filename:
        return False, "Path separators are not allowed in filename"

    return True, None


def validate_file_size(file_size):
    if not isinstance(file_size, int) or isinstance(file_size, bool):
        return False, "File size must be a non-negative integer"

    if file_size < 0:
        return False, "File size cannot be negative"

    return True, None


def validate_sha256(expected_hash):
    if not isinstance(expected_hash, str):
        return False, "SHA-256 must be a string"

    if len(expected_hash) != 64:
        return False, "SHA-256 must contain exactly 64 characters"

    if any(
        character not in "0123456789abcdefABCDEF"
        for character in expected_hash
    ):
        return False, "SHA-256 contains invalid hexadecimal characters"

    return True, None