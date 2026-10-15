# Local Jellyfin test stack

A throwaway Jellyfin server running alongside NextUp for exercising the
`AUTO_CREATE_RECOMMENDATION_LIBRARIES` path end to end. Both containers share the
recommendations directory at the **same** `/recommendations` path, which is the
condition Jellyfin requires: it will only create a library for a path that exists
on its own filesystem.

This stack is isolated from your real deployment. It uses its own named volumes
and `test/jellyfin/data/`, and never reads `config/config.env` or `compose.yaml`.

## Prerequisites

- Docker + Docker Compose
- The containers run as uid/gid `1000:1000`. If your user differs, adjust the
  `user:` lines in `compose.test.yaml` and the ownership of `data/`.

## One-time setup

1. Start Jellyfin:

   ```bash
   docker compose -f test/jellyfin/compose.test.yaml up -d jellyfin
   ```

2. Open http://localhost:8096 and complete the first-boot wizard. Create an admin
   user. You do not need to add any media libraries.

3. In Jellyfin, go to **Dashboard > API Keys** and create a key.

4. Copy the env template and fill it in:

   ```bash
   cp test/jellyfin/config.test.env.sample test/jellyfin/config.test.env
   ```

   Set at minimum:
   - `JELLYFIN_API_KEY` — the key from step 3.
   - `JELLYFIN_URL` — leave as `http://jellyfin:8096` (service name on the compose
     network).
   - `GENERATE_RECOS_FOR` — the admin username you created, so there is a user to
     generate for.
   - `TMDB_API_KEY` — only needed if you want real recommendations generated. The
     library-creation path can be tested with any folders present under
     `data/recommendations`.

## Running NextUp against the test Jellyfin

```bash
docker compose -f test/jellyfin/compose.test.yaml up -d nextup
```

Trigger a run on demand (no cron is configured in the test env):

```bash
curl -X POST http://localhost:8888/recommendations/run
```
