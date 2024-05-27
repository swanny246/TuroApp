import discord, json, os
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
default_timeout_duration = config['timeout_duration']
default_auto_unlock_duration = config['auto_unlock_duration']

class UnlockView(View):
    def __init__(self, channel):
        super().__init__(timeout=None)
        self.channel = channel

    @discord.ui.button(label="Unlock", style=discord.ButtonStyle.danger)
    async def unlock_button(self, interaction: discord.Interaction, button: Button):
        await unlock_channel(self.channel)
        await interaction.response.send_message("The channel has been unlocked.", ephemeral=True)
        
        # Update the button to show it has been used
        button.label = "Unlocked"
        button.style = discord.ButtonStyle.success
        button.disabled = True
        await interaction.message.edit(view=self)

async def unlock_channel(channel):
    # Unlock the channel for the Poketwo bot
    bot_member = channel.guild.get_member(poketwo_bot_id)
    if bot_member == None:
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
        return config['server_configs'].get(str(guild_id), {
            'timeout_duration': default_timeout_duration,
            'auto_unlock_duration': default_auto_unlock_duration
        })

    def save_server_config(self, guild_id, timeout_duration, auto_unlock_duration):
        config['server_configs'][str(guild_id)] = {
            'timeout_duration': timeout_duration,
            'auto_unlock_duration': auto_unlock_duration
        }
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=4)

    async def lock_channel(self, channel, timeout_duration):
        # Calculate the Unix timestamp for the lock time
        lock_time = datetime.now() + timedelta(seconds=timeout_duration)
        lock_timestamp = int(lock_time.timestamp())

        # Notify the channel that it will be locked soon with a countdown
        countdown_message = await channel.send(f"The channel will be locked <t:{lock_timestamp}:R>.")
        
        # Wait for the timeout duration to check if there are any new messages
        try:
            await self.bot.wait_for(
            'message', 
            timeout=timeout_duration, 
            check=lambda m: (
                m.channel == channel and 
                m.author.id == poketwo_bot_id and 
                "Congratulations" in m.content and 
                "You caught a Level" in m.content
            )
        )
            await countdown_message.edit(content="Interrupted by a catch, not locking the channel!")
            print("Interrupted by a message containing '@Pokétwo#8236 c', not locking the channel!")
        except asyncio.TimeoutError:
            # Lock the channel for the Poketwo bot
            bot_member = channel.guild.get_member(poketwo_bot_id)  # Ensure bot_member is fetched correctly
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

                # Schedule auto unlock after auto_unlock_duration
                self.locked_channels[channel.id] = countdown_message
                server_config = self.get_server_config(channel.guild.id)
                self.bot.loop.create_task(self.auto_unlock_channel(channel, server_config['auto_unlock_duration']))

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
            if any(keyword in content for keyword in keywords) and "@" in content:
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
                        print(f'Hunt in {message.channel.name} on {message.guild.name}!')  # You might need to adjust this line if `channel` is not defined here
                        server_config = self.get_server_config(message.guild.id)
                        await self.lock_channel(message.channel, server_config['timeout_duration'])

    @commands.hybrid_command(name="lock", description="Locks the current channel you're in, if unlocked")
    async def lock(self, ctx):
        """Locks the current channel until manually unlocked."""
        await ctx.send("Manually locking channel...", ephemeral=True)  # Initial response to prevent timeout
        server_config = self.get_server_config(ctx.guild.id)
        await self.lock_channel(ctx.channel, server_config['timeout_duration'])

    @commands.hybrid_command(name="unlock", description="Unlocks the current channel you're in, if locked")
    async def unlock(self, ctx):
        """Unlocks the current channel"""
        bot_member = ctx.channel.guild.get_member(poketwo_bot_id)
        if bot_member == None:
            await channel.send(":warning: Unable to find Pokétwo bot to let it back in, check that the bot is a member of the server! Otherwise, I may be missing some permissions.")
        else:
            overwrite = ctx.channel.overwrites_for(bot_member)
            if overwrite.send_messages is not False and overwrite.read_messages is not False:
                await ctx.send("This channel is already unlocked.")
            else:
                await ctx.send("The channel has been unlocked.")
                await unlock_channel(ctx.channel)
                if ctx.channel.id in self.locked_channels:
                    del self.locked_channels[ctx.channel.id]

    @commands.hybrid_command(name="set_timeouts", description="Set the timeout and auto unlock durations for this server")
    @commands.has_guild_permissions(manage_guild=True)
    @app_commands.describe(
        timeout_duration="How many seconds before a channel locks.",
        auto_unlock_duration="How many seconds before a channel auto-unlocks (3600 = one hour)"
    )
    
    async def set_timeouts(self, ctx, timeout_duration: int, auto_unlock_duration: int):
        """Sets the timeout durations for this server. Timeout = how long before a channel locks, Auto unlock = how long a channel will stay locked for."""
        self.save_server_config(ctx.guild.id, timeout_duration, auto_unlock_duration)
        await ctx.send(f"Timeout duration set to {timeout_duration} seconds and auto unlock duration set to {auto_unlock_duration} seconds.")
        
    @set_timeouts.error
    async def set_timeouts_error(ctx, error):
        if isinstance(error, MissingPermissions):
            await ctx.reply(':exclamation: You are not the master, you have no control over me!')
        else:
            await ctx.reply('Something went wrong. Vague, I know.')

async def setup(bot):
    await bot.add_cog(ChannelManagement(bot))