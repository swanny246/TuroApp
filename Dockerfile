# Turo Discord bot
#
# Uses the pre-built discord.py image, which already bundles discord.py and its
# dependencies. See https://hub.docker.com/r/gorialis/discord.py for tags.
FROM gorialis/discord.py

WORKDIR /app

# Copy the bot source into the image. config.json is intentionally NOT copied
# (it is git-ignored and holds your token) — mount it at runtime instead.
COPY main.py channel_management.py ./

CMD ["python", "main.py"]
