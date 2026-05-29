# Public File Cutover Contract

## Bottom Line

Public local-prune is now safe for active `File.file_url` consumers because Ifitwala Drive rewrites public legacy attachments onto a canonical non-`/files/...` URL before deleting the local blob.

What is **not** guaranteed by app code alone is preservation of stale bookmarked or hard-coded old `/files/...` URLs that may still be served statically by the web tier.

## What The App Now Does

For an offloaded public legacy `File`:

1. verify the remote object exists
2. verify the remote size matches the local file size
3. compute a canonical public URL
4. update `File.file_url` to that canonical URL
5. delete the local blob

Canonical public URL resolution order:

1. direct remote public object URL from the active storage backend
2. app-routed public redirect endpoint:
   - `/api/method/ifitwala_drive.api.access.redirect_public_file?file_id=<FILE_ID>`

The redirect endpoint is public by design, but it only resolves files where `File.is_private = 0`.

## What This Guarantees

- DB-backed consumers that read the current `File.file_url` continue to work after prune
- public assets can move off `sites/<site>/public/files`
- the system does not depend on guessed object-storage paths in UI or business code

## What This Does Not Guarantee

- old copied `/files/...` links shared outside the system
- stale HTML or cached markup that still points at the original local path
- web-tier static handlers that never forward missing `/files/...` requests into Python

## Optional Web-Tier Compatibility Layer

If preserving old raw `/files/...` links matters, the web tier must forward **missing** public file requests into Frappe.

Desired behavior:

1. if `/files/...` exists locally, serve it normally
2. if it is missing locally, pass the request to Frappe
3. Frappe resolves the migrated file and redirects to its remote canonical URL

Important:

- do not proxy all `/files/...` traffic through Python by default
- only miss-through should reach the app
- this keeps normal public-file reads cheap while preserving migrated old links

## Recommended Deployment Rule

Use canonical rewritten `File.file_url` values as the default application contract.

Treat web-tier miss routing as a backward-compatibility feature, not as the primary delivery path.
