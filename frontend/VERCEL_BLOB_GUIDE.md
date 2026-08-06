# Vercel Blob `.dem` File Upload Strategy & Integration Guide

## Background & Challenge

Counter-Strike 2 / Dota 2 `.dem` replay files typically range in size from **15 MB to 500 MB+**. 

When deploying single-page or full-stack web applications on **Vercel**, Vercel Serverless Functions enforce a strict **4.5 MB HTTP request body size limit**. Any direct POST upload (`POST /api/replay/upload`) containing a `.dem` file exceeding 4.5 MB will fail with `413 Payload Too Large`.

---

## Solution: Vercel Blob Direct Client Upload

**Vercel Blob** is Vercel's object storage solution built to handle large asset uploads up to **500 MB** directly from client browsers.

### Architecture Flow

```text
+------------------+         Direct Client Upload          +-------------------+
|                  | ------------------------------------> |                   |
| Frontend Browser |   (up to 500MB via @vercel/blob)      | Vercel Blob Store |
|                  |                                       |                   |
+------------------+                                       +-------------------+
         |                                                           |
         | 1. Receives Public Blob URL                               |
         |    (https://<store>.public.blob.vercel-storage.com)       |
         v                                                           v
+------------------+   POST /api/replay/import-url                 +-------------------+
| Frontend Adapter | ------------------------------------> | Backend Parser    |
| (importReplayUrl)|   {"url": "<blob_url>", "filename": ...}      | (stream up to 1GB)|
+------------------+                                       +-------------------+
```

---

## Code Implementation Example

### 1. Frontend Client Upload (`@vercel/blob/client`)

Install `@vercel/blob`:
```bash
pnpm add @vercel/blob
```

In your upload component:
```typescript
import { upload } from "@vercel/blob/client";
import { importReplayUrl } from "@/adapters/replay-api";

async function handleLargeReplayUpload(file: File) {
  if (!file.name.endsWith(".dem")) {
    throw new Error("Invalid replay format. Please select a .dem file.");
  }

  // Upload directly from browser to Vercel Blob (bypassing serverless 4.5MB limit)
  const blob = await upload(file.name, file, {
    access: "public",
    handleUploadUrl: "/api/blob/upload", // Optional token provider route
  });

  // Send public Blob URL to backend parser
  const manifest = await importReplayUrl(blob.url, file.name);
  return manifest;
}
```

### 2. Backend Import Endpoint (`POST /api/replay/import-url`)

The FastAPI backend includes built-in support for streaming Vercel Blob URLs when enabled:

Set environment variable:
```bash
REDECIDE_BLOB_IMPORT_ENABLED=true
```

Backend endpoint details:
- **Route**: `POST /api/replay/import-url`
- **Body**: `{"url": "https://<store-id>.public.blob.vercel-storage.com/match.dem", "filename": "match.dem"}`
- **Security**: Validates that source domain matches `.public.blob.vercel-storage.com` and validates file integrity.
- **Output**: Standard `ReplayManifest` matching `/api/replay/upload`.

---

## Conclusion & Recommendation

Using **Vercel Blob client direct upload** completely resolves the 4.5 MB request payload limit for `.dem` files and allows seamless replay ingestion for files up to 500 MB.
