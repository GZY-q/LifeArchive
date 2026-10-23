"""Create a private local .env without ever overwriting an existing file."""

import os
import secrets
from pathlib import Path


def initialize_env(root: Path) -> None:
    template = (root / ".env.example").read_text(encoding="utf-8")
    placeholder = "replace-with-a-long-random-password"
    if template.count(placeholder) != 1:
        raise ValueError("Expected exactly one password placeholder in .env.example")
    content = template.replace(placeholder, secrets.token_hex(32))
    descriptor = os.open(root / ".env", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        output.write(content)


if __name__ == "__main__":
    try:
        initialize_env(Path(__file__).resolve().parents[1])
    except FileExistsError:
        raise SystemExit(".env already exists; left unchanged.") from None
    print("Created .env with a generated password and mode 0600; keep it private.")
