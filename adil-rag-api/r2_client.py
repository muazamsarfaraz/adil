"""Async Cloudflare R2 client for backend reads/deletes.

R2 is S3-compatible — we use aioboto3 pointed at the R2 endpoint. Backend
credentials are scoped to GetObject + DeleteObject only.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import aioboto3


class R2ConfigError(Exception):
    pass


@dataclass(frozen=True)
class R2Config:
    account_id: str
    bucket: str
    endpoint_url: str
    access_key_id: str
    secret_access_key: str

    @classmethod
    def from_env(cls) -> R2Config:
        required = [
            "R2_ACCOUNT_ID",
            "R2_BUCKET",
            "R2_ENDPOINT",
            "R2_BACKEND_ACCESS_KEY_ID",
            "R2_BACKEND_SECRET_ACCESS_KEY",
        ]
        values: dict[str, str] = {}
        missing: list[str] = []
        for name in required:
            v = os.getenv(name)
            if not v:
                missing.append(name)
            else:
                values[name] = v
        if missing:
            raise R2ConfigError(f"Missing R2 env vars: {', '.join(missing)}")
        return cls(
            account_id=values["R2_ACCOUNT_ID"],
            bucket=values["R2_BUCKET"],
            endpoint_url=values["R2_ENDPOINT"],
            access_key_id=values["R2_BACKEND_ACCESS_KEY_ID"],
            secret_access_key=values["R2_BACKEND_SECRET_ACCESS_KEY"],
        )


class R2Client:
    def __init__(self, config: R2Config):
        self.config = config
        self._session = aioboto3.Session()

    @classmethod
    def from_env(cls) -> R2Client:
        return cls(R2Config.from_env())

    def _make_client(self):
        return self._session.client(
            "s3",
            endpoint_url=self.config.endpoint_url,
            aws_access_key_id=self.config.access_key_id,
            aws_secret_access_key=self.config.secret_access_key,
            region_name="auto",
        )

    async def get_object(self, object_key: str) -> bytes:
        """Fetch bytes from R2. Raises on missing object or access error."""
        async with self._make_client() as s3:
            resp = await s3.get_object(Bucket=self.config.bucket, Key=object_key)
            body = resp["Body"]
            return await body.read()

    async def delete_object(self, object_key: str) -> None:
        async with self._make_client() as s3:
            await s3.delete_object(Bucket=self.config.bucket, Key=object_key)
