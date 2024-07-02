import discord
from discord.ext import commands
from discord.ext.commands import MissingPermissions
import json
import os
import asyncio

# Load the configuration file
base_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(base_dir, 'config.json')

with open(config_path) as f:
    config = json.load(f)

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True  # Enable the message content intent
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    await bot.change_presence(activity=discord.CustomActivity(name='Turov1.2.3' ,emoji='🖥️'))

@bot.hybrid_command()
@commands.has_guild_permissions(manage_guild=True)
async def sync(ctx):
    """Syncs the slash commands."""
    print(f"Running sync command on {ctx.guild.name}")
    await bot.tree.sync()
    await ctx.send(':white_check_mark: My commands have been synced successfully *beep boop*. If you don\'t see any expected changes, try restarting the Discord app.')

@sync.error
async def sync_error(ctx, error):
    if isinstance(error, MissingPermissions):
        await ctx.reply(':exclamation: You are not the master, you have no control over me!')
    else:
        await ctx.reply('Something went wrong. Vague, I know.')

@bot.hybrid_command()
async def restart(ctx):
    """Restarts the bot."""
    if ctx.author.id == config['owner']:
        await bot.reload_extension("channel_management")
        await ctx.send(':white_check_mark: I have restarted successfully *beep boop*.')
    else:
        await ctx.send(":exclamation: You are not my master, you have no control over me!")

async def main():
    async with bot:
        await bot.load_extension("channel_management")
        await bot.start(config['token'])

if __name__ == "__main__":
    asyncio.run(main())