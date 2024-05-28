import discord
import json
import os
from discord.ext import commands
from discord.ui import Button, View
from discord import app_commands
import asyncio
from datetime import datetime, timedelta

# Load the configuration file
base_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(base_dir, 'config.json')

with open(config_path) as f:
    config = json.load(f)

pokename = config['pokename']
poketox = config['poketox']
p2assistant = config['p2assistant']
authorized_ids = [pokename, poketox, p2assistant]
poketwo_bot_id = config['poketwo_bot_id']

# Default timeout durations (will be overridden by server-specific settings)
default_lock_delay = config['lock_delay']
default_shiny_lock_duration = config['shiny_lock_duration']
default_rare_lock_duration = config['rare_lock_duration']
default_regional_lock_duration = config['regional_lock_duration']
default_collection_lock_duration = config['collection_lock_duration']

class UnlockView(View):
    def __init__(self, channel):
        super().__init__(timeout=None)
        self.channel = channel

    @discord.ui.button(label="Unlock", style=discord.ButtonStyle.danger, emoji="🔐")
    async def unlock_button(self, interaction: discord.Interaction, button: Button):
        await unlock_channel(self.channel)
        await interaction.response.send_message("The channel has been unlocked.", ephemeral=True)
        
        # Update the button to show it has been used
        button.label = "Unlocked"
        button.emoji = "🔓"
        button.style = discord.ButtonStyle.success
        button.disabled = True
        await interaction.message.edit(view=self)

async def unlock_channel(channel):
    # Unlock the channel for the Poketwo bot
    bot_member = channel.guild.get_member(poketwo_bot_id)
    if bot_member is None:
        await channel.send(":warning: Unable to find Pokétwo bot to let it back in, check that the bot is a member of the server! Otherwise, I may be missing some permissions.")
    else:
        overwrite = channel.overwrites_for(bot_member)
        overwrite.send_messages = True
        overwrite.read_messages = True
        await channel.set_permissions(bot_member, overwrite=overwrite)

class ChannelManagement(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.locked_channels = {}

    def get_server_config(self, guild_id):
        default_config = {
            'lock_delay': default_lock_delay,
            'shiny_lock_duration': default_shiny_lock_duration,
            'rare_lock_duration': default_rare_lock_duration,
            'regional_lock_duration': default_regional_lock_duration,
            'collection_lock_duration': default_collection_lock_duration,
        }
        return {**default_config, **config['server_configs'].get(str(guild_id), {})}

    def save_server_config(self, guild_id, lock_delay, shiny_lock_duration, rare_lock_duration, regional_lock_duration, collection_lock_duration):
        config['server_configs'][str(guild_id)] = {
            'lock_delay': lock_delay,
            'shiny_lock_duration': shiny_lock_duration,
            'rare_lock_duration': rare_lock_duration,
            'regional_lock_duration': regional_lock_duration,
            'collection_lock_duration': collection_lock_duration,
        }
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=4)

    async def lock_channel(self, channel, lock_duration):
        # Notify the channel that it will be locked soon with a countdown
        lock_time = datetime.now() + timedelta(seconds=default_lock_delay)
        lock_timestamp = int(lock_time.timestamp())
        countdown_message = await channel.send(f"The channel will be locked <t:{lock_timestamp}:R>.")
        
        # Wait for the lock delay duration
        try:
            await self.bot.wait_for(
                'message', 
                timeout=default_lock_delay, 
                check=lambda m: (
                    m.channel == channel and 
                    m.author.id == poketwo_bot_id and 
                    "Congratulations" in m.content and 
                    "You caught a Level" in m.content
                )
            )
            await countdown_message.edit(content="Interrupted by a catch, not locking the channel!")
            print("Interrupted by a message containing 'Congratulations' and 'You caught a Level', not locking the channel!")
        except asyncio.TimeoutError:
            # Lock the channel for the Poketwo bot
            bot_member = channel.guild.get_member(poketwo_bot_id)
            print(f'Bot member: {bot_member}')
            
            if bot_member is None:
                await channel.send(":warning: Unable to find Pokétwo bot to lock it out, check that the bot is a member of the server! Otherwise, I may be missing some permissions.")
            else:
                overwrite = channel.overwrites_for(bot_member)
                overwrite.send_messages = False
                overwrite.read_messages = False
                print(f'Permissions overwrite: {overwrite}')
                await channel.set_permissions(bot_member, overwrite=overwrite)

                # Create the unlock button view
                view = UnlockView(channel)

                # Edit the countdown message to say the channel has been locked and add the unlock button
                await countdown_message.edit(content="The channel has been locked.", view=view)

                # Register the channel as locked
                self.locked_channels[channel.id] = countdown_message

                # Schedule auto unlock after lock_duration
                self.bot.loop.create_task(self.auto_unlock_channel(channel, lock_duration))

    async def auto_unlock_channel(self, channel, delay):
        await asyncio.sleep(delay)
        if channel.id in self.locked_channels:
            await unlock_channel(channel)
            await channel.send("The channel has been automatically unlocked due to inactivity.")
            del self.locked_channels[channel.id]

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.id in authorized_ids:
            content = message.content.lower()  # Convert message content to lowercase for case-insensitive comparison
            keywords = ["rare ping", "regional ping", "collection pings", "shiny hunt pings"]  # Adjusted the list of keywords

            # Check if any of the keywords are present in the message content
            for keyword in keywords:
                if keyword in content and "@" in content:
                    print(f'Keyword detected in message: {content}')
                    bot_member = message.channel.guild.get_member(poketwo_bot_id)
                    print(f'Bot member: {bot_member}')
                    if bot_member is None:
                        await message.channel.send(":warning: Unable to find Pokétwo bot to lock it out, check that the bot is a member of the server! Otherwise, I may be missing some permissions.")
                    else:
                        overwrite = message.channel.overwrites_for(bot_member)
                        if overwrite.send_messages is False and overwrite.read_messages is False:
                            await message.channel.send("The channel is already locked.")
                            return
                        else:
                            print(f'Hunt in {message.channel.name} on {message.guild.name}!')
                            server_config = self.get_server_config(message.guild.id)
                            if keyword == "rare ping":
                                lock_duration = server_config.get('rare_lock_duration', default_rare_lock_duration)
                            elif keyword == "regional ping":
                                lock_duration = server_config.get('regional_lock_duration', default_regional_lock_duration)
                            elif keyword == "collection pings":
                                lock_duration = server_config.get('collection_lock_duration', default_collection_lock_duration)
                            else:
                                lock_duration = server_config.get('shiny_lock_duration', default_shiny_lock_duration)
                            await self.lock_channel(message.channel, lock_duration)
                    break  # Exit the loop once a keyword is found to avoid redundant checks

    @commands.hybrid_command(name="lock", description="Locks the current channel you're in, if unlocked")
    async def lock(self, ctx):
        """Locks the current channel until manually unlocked."""
        await ctx.send("Manually locking channel...", ephemeral=True)  # Initial response to prevent timeout
        lock_duration = 86400  # Default to 24 hours
        await self.lock_channel(ctx.channel, lock_duration)

    @commands.hybrid_command(name="unlock", description="Unlocks the current channel you're in, if locked")
    async def unlock(self, ctx):
        """Unlocks the current channel"""
        bot_member = ctx.channel.guild.get_member(poketwo_bot_id)
        if bot_member is None:
            await ctx.channel.send(":warning: Unable to find Pokétwo bot to let it back in, check that the bot is a member of the server! Otherwise, I may be missing some permissions.")
        else:
            overwrite = ctx.channel.overwrites_for(bot_member)
            if overwrite.send_messages is not False and overwrite.read_messages is not False:
                await ctx.send("This channel is already unlocked.")
            else:
                await ctx.send("The channel has been unlocked.")
                await unlock_channel(ctx.channel)
                if ctx.channel.id in self.locked_channels:
                    del self.locked_channels[ctx.channel.id]

    @commands.hybrid_command(name="set_timers", description="Set the timeout and auto unlock durations for this server")
    @commands.has_guild_permissions(manage_guild=True)
    @app_commands.describe(
        lock_delay="How many seconds before a channel locks.",
        shiny_lock_duration="How many seconds before a channel auto-unlocks (3600 = one hour)",
        rare_lock_duration="How many seconds before a channel locks after a rare ping",
        regional_lock_duration="How many seconds before a channel locks after a regional ping",
        collection_lock_duration="How many seconds before a channel locks after a collection ping"
    )
    async def set_timers(self, ctx, lock_delay: int = None, shiny_lock_duration: int = None, rare_lock_duration: int = None, regional_lock_duration: int = None, collection_lock_duration: int = None):
        """Sets the timeout durations for this server."""
        server_config = self.get_server_config(ctx.guild.id)

        lock_delay = lock_delay if lock_delay is not None else server_config['lock_delay']
        shiny_lock_duration = shiny_lock_duration if shiny_lock_duration is not None else server_config['shiny_lock_duration']
        rare_lock_duration = rare_lock_duration if rare_lock_duration is not None else server_config['rare_lock_duration']
        regional_lock_duration = regional_lock_duration if regional_lock_duration is not None else server_config['regional_lock_duration']
        collection_lock_duration = collection_lock_duration if collection_lock_duration is not None else server_config['collection_lock_duration']

        self.save_server_config(ctx.guild.id, lock_delay, shiny_lock_duration, rare_lock_duration, regional_lock_duration, collection_lock_duration)
        await ctx.send(f"Lock delay set to {lock_delay} seconds, auto unlock duration set to {shiny_lock_duration} seconds, rare lock duration set to {rare_lock_duration} seconds, regional lock duration set to {regional_lock_duration} seconds, and collection lock duration set to {collection_lock_duration} seconds.")

    @set_timers.error
    async def set_timers_error(ctx, error):
        if isinstance(error, MissingPermissions):
            await ctx.reply(':exclamation: You are not the master, you have no control over me!')
        else:
            await ctx.reply('Something went wrong. Vague, I know.')

async def setup(bot):
    await bot.add_cog(ChannelManagement(bot))