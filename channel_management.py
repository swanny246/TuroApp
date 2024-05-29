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

    def save_server_config(self, guild_id, config_type, value, permanent_lock=False):
        server_config = config['server_configs'].get(str(guild_id), {})
        if permanent_lock:
            server_config[config_type] = {'permanent_lock': True}
        else:
            server_config[config_type] = {'value': value, 'permanent_lock': False}
        config['server_configs'][str(guild_id)] = server_config
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
                if lock_duration and not server_config.get('permanent_lock', False):  # Check for permanent lock
                    self.bot.loop.create_task(self.auto_unlock_channel(channel, lock_duration))

    async def lock_channel_immediately(self, channel, lock_duration):
        # Lock the channel for the Poketwo bot immediately
        bot_member = channel.guild.get_member(poketwo_bot_id)
        if bot_member is None:
            await channel.send(":warning: Unable to find Pokétwo bot to lock it out, check that the bot is a member of the server! Otherwise, I may be missing some permissions.")
        else:
            overwrite = channel.overwrites_for(bot_member)
            overwrite.send_messages = False
            overwrite.read_messages = False
            await channel.set_permissions(bot_member, overwrite=overwrite)

            # Create the unlock button view
            view = UnlockView(channel)

            # Notify the channel that it has been locked and add the unlock button
            countdown_message = await channel.send("The channel has been locked.", view=view)

            # Register the channel as locked
            self.locked_channels[channel.id] = countdown_message

            # Schedule auto unlock after lock_duration
            if lock_duration and not self.get_server_config(channel.guild.id).get('permanent_lock', False):  # Check for permanent lock
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
        await self.lock_channel_immediately(ctx.channel, lock_duration)

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

    @commands.hybrid_command(name="set_shiny_lock_timer", description="Set the auto-unlock duration for shiny locks or make it permanent.")
    @commands.has_guild_permissions(manage_guild=True)
    @app_commands.describe(
        lock_duration="How many seconds before a channel auto-unlocks (3600 = one hour)",
        permanent_lock="Whether to make the lock permanent (True/False)"
    )
    async def set_shiny_lock_timer(self, ctx, lock_duration: int = None, permanent_lock: bool = False):
        """Sets the shiny lock duration for this server."""
        if lock_duration is not None and permanent_lock:
            await ctx.send("You cannot set both a lock duration and permanent lock. Please choose one.", ephemeral=True)
            return
        
        server_config = self.get_server_config(ctx.guild.id)
        self.save_server_config(ctx.guild.id, 'shiny_lock', lock_duration, permanent_lock)

        embed = discord.Embed(
            title="Shiny lock timer settings updated",
            color=discord.Color.blue()
        )
        embed.add_field(name="Lock duration", value=f"{lock_duration} seconds" if lock_duration else "Not Set", inline=False)
        embed.add_field(name="Permanent lock", value=str(permanent_lock), inline=False)

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="set_rare_lock_timer", description="Set the auto-unlock duration for rare locks or make it permanent.")
    @commands.has_guild_permissions(manage_guild=True)
    @app_commands.describe(
        lock_duration="How many seconds before a channel auto-unlocks (3600 = one hour)",
        permanent_lock="Whether to make the lock permanent (True/False)"
    )
    async def set_rare_lock_timer(self, ctx, lock_duration: int = None, permanent_lock: bool = False):
        """Sets the rare lock duration for this server."""
        if lock_duration is not None and permanent_lock:
            await ctx.send("You cannot set both a lock duration and permanent lock. Please choose one.", ephemeral=True)
            return
        
        server_config = self.get_server_config(ctx.guild.id)
        self.save_server_config(ctx.guild.id, 'rare_lock', lock_duration, permanent_lock)

        embed = discord.Embed(
            title="Rare lock timer settings updated",
            color=discord.Color.blue()
        )
        embed.add_field(name="Lock duration", value=f"{lock_duration} seconds" if lock_duration else "Not Set", inline=False)
        embed.add_field(name="Permanent lock", value=str(permanent_lock), inline=False)

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="set_regional_lock_timer", description="Set the auto-unlock duration for regional locks or make it permanent.")
    @commands.has_guild_permissions(manage_guild=True)
    @app_commands.describe(
        lock_duration="How many seconds before a channel auto-unlocks (3600 = one hour)",
        permanent_lock="Whether to make the lock permanent (True/False)"
    )
    async def set_regional_lock_timer(self, ctx, lock_duration: int = None, permanent_lock: bool = False):
        """Sets the regional lock duration for this server."""
        if lock_duration is not None and permanent_lock:
            await ctx.send("You cannot set both a lock duration and permanent lock. Please choose one.", ephemeral=True)
            return
        
        server_config = self.get_server_config(ctx.guild.id)
        self.save_server_config(ctx.guild.id, 'regional_lock', lock_duration, permanent_lock)

        embed = discord.Embed(
            title="Regional lock timer settings updated",
            color=discord.Color.blue()
        )
        embed.add_field(name="Lock duration", value=f"{lock_duration} seconds" if lock_duration else "Not Set", inline=False)
        embed.add_field(name="Permanent lock", value=str(permanent_lock), inline=False)

        await ctx.send(embed=embed)

    @commands.hybrid_command(name="set_collection_lock_timer", description="Set the auto-unlock duration for collection locks or make it permanent.")
    @commands.has_guild_permissions(manage_guild=True)
    @app_commands.describe(
        lock_duration="How many seconds before a channel auto-unlocks (3600 = one hour)",
        permanent_lock="Whether to make the lock permanent (True/False)"
    )
    async def set_collection_lock_timer(self, ctx, lock_duration: int = None, permanent_lock: bool = False):
        """Sets the collection lock duration for this server."""
        if lock_duration is not None and permanent_lock:
            await ctx.send("You cannot set both a lock duration and permanent lock. Please choose one.", ephemeral=True)
            return
        
        server_config = self.get_server_config(ctx.guild.id)
        self.save_server_config(ctx.guild.id, 'collection_lock', lock_duration, permanent_lock)

        embed = discord.Embed(
            title="Collection lock timer settings updated",
            color=discord.Color.blue()
        )
        embed.add_field(name="Lock duration", value=f"{lock_duration} seconds" if lock_duration else "Not Set", inline=False)
        embed.add_field(name="Permanent lock", value=str(permanent_lock), inline=False)
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name="set_lock_delay", description="Set the lock delay for channel locks.")
    @commands.has_guild_permissions(manage_guild=True)
    @app_commands.describe(
        lock_delay="How many seconds before a channel locks after a ping."
    )
    async def set_lock_delay(self, ctx, lock_delay: int):
        """Sets the lock delay for this server."""
        try:
            # Update the lock delay in the server config
            self.save_server_config(ctx.guild.id, 'lock_delay', lock_delay)
            
            await ctx.send(f"Lock delay set to {lock_delay} seconds.")
        except Exception as e:
            print(e)

    @set_shiny_lock_timer.error
    @set_rare_lock_timer.error
    @set_regional_lock_timer.error
    @set_collection_lock_timer.error
    @set_lock_delay.error
    async def set_timers_error(ctx, error):
        if isinstance(error, MissingPermissions):
            await ctx.reply(':exclamation: You are not the master, you have no control over me!')
        else:
            await ctx.reply('Something went wrong. Vague, I know.')

    @commands.hybrid_command(name="view_timers", description="View all your timers and lock settings.")
    async def view_timers(self, ctx):
        """Displays all the current timer and lock settings for the server."""
        server_config = self.get_server_config(ctx.guild.id)

        embed = discord.Embed(
            title="Current timer and lock Settings",
            color=discord.Color.blue()
        )

        embed.add_field(name="Lock Delay", value=f"{server_config.get('lock_delay', default_lock_delay)} seconds", inline=False)

        shiny_lock = server_config.get('shiny_lock', {})
        if shiny_lock.get('permanent_lock', False):
            embed.add_field(name="Shiny Lock", value="Permanent", inline=False)
        else:
            embed.add_field(name="Shiny Lock Duration", value=f"{server_config.get('shiny_lock_duration', default_shiny_lock_duration)} seconds", inline=False)

        rare_lock = server_config.get('rare_lock', {})
        if rare_lock.get('permanent_lock', False):
            embed.add_field(name="Rare Lock", value="Permanent", inline=False)
        else:
            embed.add_field(name="Rare Lock Duration", value=f"{server_config.get('rare_lock_duration', default_rare_lock_duration)} seconds", inline=False)

        regional_lock = server_config.get('regional_lock', {})
        if regional_lock.get('permanent_lock', False):
            embed.add_field(name="Regional Lock", value="Permanent", inline=False)
        else:
            embed.add_field(name="Regional Lock Duration", value=f"{server_config.get('regional_lock_duration', default_regional_lock_duration)} seconds", inline=False)

        collection_lock = server_config.get('collection_lock', {})
        if collection_lock.get('permanent_lock', False):
            embed.add_field(name="Collection Lock", value="Permanent", inline=False)
        else:
            embed.add_field(name="Collection Lock Duration", value=f"{server_config.get('collection_lock_duration', default_collection_lock_duration)} seconds", inline=False)

        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(ChannelManagement(bot))