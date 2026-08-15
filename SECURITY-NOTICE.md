# Security action required for the existing GitHub repository

The repository `valianktni1/march-weddings-by-mark-accounts` has previously been public and its history contains an old Emergent key and account-backup ZIP files.

This clean package can be committed to that same repository as requested, but a normal deletion commit does not erase old Git history.

Before using the repository for Accounts 2026:

1. Make the repository private.
2. Revoke the old Emergent key if that has not already been done.
3. Remove the old backup ZIP files from the current branch when replacing its contents.
4. Do not add `.env`, database archives, invoices, receipts, bank statements or generated application backups.
5. Treat complete Git-history cleanup as a separate controlled job; rewriting history can disrupt clones and must not be done casually.

The supplied release ZIP excludes the discovered backup archives, Emergent folders, generated builds, development caches and local Git metadata.
