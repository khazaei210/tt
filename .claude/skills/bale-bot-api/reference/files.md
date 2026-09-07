# Bale Files

Source: https://docs.bale.ai/

Bale documents three relevant file-sending approaches:

1. Existing `file_id` — reuse a file already known to the platform.
2. URL — send/retrieve media using a URL where the method supports it.
3. Upload — use `multipart/form-data` and `InputFile` for a new upload.

Do not send file uploads as JSON. Follow the exact method's documented parameter name and type.

For repeated files, prefer a stored `file_id` when appropriate instead of uploading the same file repeatedly.
