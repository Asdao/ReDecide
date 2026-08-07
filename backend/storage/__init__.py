"""Storage adapters used by the server-side APIs."""

from backend.storage.blob import BlobArtifactStore, blob_storage_enabled

__all__ = ["BlobArtifactStore", "blob_storage_enabled"]
