# Security action required before deployment

The original public repository contained:

- an Emergent API key inside Docker Compose files; and
- two account-backup ZIP files inside a backend data folder.

Because Git history retains deleted content, simply deleting those files from the original repository is not sufficient.

Recommended action:

1. Revoke the exposed Emergent key.
2. Make the original repository private immediately.
3. Create a new private repository for this cleaned replacement.
4. Upload only the contents of this replacement package.
5. Never add database dumps, backup ZIPs, uploaded invoices, receipts, bank statements or `.env` files to GitHub.

This replacement package deliberately excludes all discovered account backups, generated frontend builds and Emergent configuration files.
