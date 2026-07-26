This is a bot that will monitor Poketwo channels that utilise PokeName or Poketox for tracking shiny hunts, collection hunts, rare pings and regional pings.

If it sees a hunt, it will go ahead and lock the channel for you so the mon won't flee! Run the main.py file to get going, your bot token goes in a config.json file.

Powered by Discord slash commands, so check the ``/set_`` commands for everything to set it all up.

## Configuration

Before running the bot (either directly or with Docker), create a `config.json` file next to `main.py`. It holds your bot token and the IDs the bot watches for, and the bot also writes runtime state (locked channels and per-server settings) back to it. A minimal example:

```json
{
    "token": "YOUR_BOT_TOKEN",
    "owner": 123456789012345678,
    "poketwo_bot_id": 716390085896962058,
    "pokename": 111111111111111111,
    "poketox": 222222222222222222,
    "p2assistant": 333333333333333333,
    "lock_delay": 0,
    "shiny_lock_duration": 3600,
    "regional_lock_duration": 3600,
    "collection_lock_duration": 3600,
    "server_configs": {},
    "locked_channels": {}
}
```

- `token` — your Discord bot token.
- `owner` — your Discord user ID (used by the `restart` command).
- `poketwo_bot_id`, `pokename`, `poketox`, `p2assistant` — the bot IDs the tracker watches.
- The `*_duration` / `lock_delay` values are in seconds and act as defaults; they can be overridden per-server with the `/set_` slash commands.
- Leave `server_configs` and `locked_channels` as empty objects — the bot fills these in itself.

## Running with Docker

The bot runs on top of the pre-built [`gorialis/discord.py`](https://hub.docker.com/r/gorialis/discord.py) image, which already ships discord.py and its dependencies, so there's nothing extra to install. A `Dockerfile` and `docker-compose.yml` are included.

The one thing to keep in mind: the bot both reads **and writes** `config.json` at runtime (it stores locked channels and per-server settings there). So `config.json` must be mounted from the host — that way your token is supplied and any changes the bot makes survive a container restart.

### Option A — Docker Compose (recommended)

1. Create your `config.json` (see [Configuration](#configuration) above) in the project root.
2. Build and start the bot:

   ```bash
   docker compose up -d --build
   ```

3. View logs / stop:

   ```bash
   docker compose logs -f
   docker compose down
   ```

The included `docker-compose.yml` bind-mounts `./config.json` into the container and sets `restart: unless-stopped` so the bot comes back after a crash or host reboot.

### Option B — Plain Docker

1. Create your `config.json` in the project root.
2. Build the image:

   ```bash
   docker build -t turo .
   ```

3. Run it, bind-mounting your `config.json`:

   ```bash
   docker run -d --name turo --restart unless-stopped \
     -v "$(pwd)/config.json:/app/config.json" \
     turo
   ```

### Option C — No build, straight from the discord.py image

If you'd rather not build a custom image at all, you can mount the whole project into the `gorialis/discord.py` image and run `main.py` directly:

```bash
docker run -d --name turo --restart unless-stopped \
  -v "$(pwd):/app" -w /app \
  gorialis/discord.py python main.py
```

Once the container is up, run the `sync` command in your server to register the slash commands, then use the `/set_` commands to finish setup.
