# TrueNAS deployment

Use `docker-compose-truenas.yml` in Dockge.

The replacement listens on `192.168.24.10:30053`, uses `/mnt/apps/accounts-2026-use/mongodb` for MongoDB, and stores all user-owned files beneath `/mnt/nextcloud/accounts-2026-saved-data`.

It is configured for both:

- `http://192.168.24.10:30053`
- `https://accounts2026.weddingsbymark.uk`

Follow `TRUENAS-STAGING-AND-MIGRATION.md` before transferring any live data. The existing accounts application remains the working system until Mark approves the replacement.
