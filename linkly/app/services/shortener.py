import secrets
import string
import time

from app.repository import Link, LinkRepository

ALPHABET = string.ascii_letters + string.digits
MAX_GENERATION_ATTEMPTS = 8
RESERVED_CODES = frozenset({"api", "docs", "redoc", "healthz", "openapi.json", "static"})


class AliasUnavailableError(Exception):
    pass


def generate_code(length: int) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


class ShortenerService:
    def __init__(self, links: LinkRepository, code_length: int):
        self.links = links
        self.code_length = code_length

    def shorten(
        self,
        url: str,
        alias: str | None = None,
        expires_in_seconds: int | None = None,
    ) -> Link:
        code = alias if alias is not None else self._unique_code()
        if alias is not None and (alias.lower() in RESERVED_CODES or self.links.code_exists(alias)):
            raise AliasUnavailableError(alias)

        expires_at = time.time() + expires_in_seconds if expires_in_seconds else None
        return self.links.create(code, url, expires_at)

    def _unique_code(self) -> str:
        for _ in range(MAX_GENERATION_ATTEMPTS):
            code = generate_code(self.code_length)
            if not self.links.code_exists(code):
                return code
        raise RuntimeError("could not generate a unique short code")
