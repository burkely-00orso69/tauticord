import asyncio
import sys
from threading import Thread
from typing import Union, List

import discord
from discord import client
from discord.ext import tasks

import modules.statics as statics
from modules.logs import info, debug, error
from modules.tautulli_connector import TautulliConnector, TautulliDataResponse


async def add_emoji_number_reactions(message: discord.Message, count: int):
    """
    Add number reactions to a message for user interaction
    :param message: message to add emojis to
    :param count: how many emojis to add
    :return: None
    """

    if count <= 0:
        return

    # Only add reactions if necessary, and remove unnecessary reactions
    cache_msg = await message.channel.fetch_message(message.id)
    msg_emoji = [str(r.emoji) for r in cache_msg.reactions]

    # thanks twilsonco
    if count <= 0:
        if len(msg_emoji) > 0:
            await message.clear_reactions()
        return

    emoji_to_remove = []

    for i, e in enumerate(msg_emoji):
        if i >= count or i != statics.emoji_numbers.index(e):
            emoji_to_remove.append(e)

    # if all reactions need to be removed, do it all at once
    if len(emoji_to_remove) == len(msg_emoji):
        await message.clear_reactions()
        msg_emoji = []
    else:
        for e in emoji_to_remove:
            await message.clear_reaction(e)
            del (msg_emoji[msg_emoji.index(e)])

    for i in range(0, count):
        if statics.emoji_numbers[i] not in msg_emoji:
            await message.add_reaction(statics.emoji_numbers[i])


async def send_starter_message(tautulli_connector, discord_channel: discord.TextChannel) -> discord.Message:
    if tautulli_connector.use_embeds:
        embed = discord.Embed(title="Welcome to Tauticord!")
        embed.add_field(name="Starting up...",
                        value='This will be replaced once we get data.',
                        inline=False)
        return await discord_channel.send(content=None, embed=embed)
    else:
        return await discord_channel.send(content="Welcome to Tauticord!")


async def send_message(content: TautulliDataResponse, embed: bool = False, message: discord.Message = None,
                       channel: discord.TextChannel = None):
    """
    Send or edit a message.
    :param content: Contents of the message to send
    :param embed: Whether to use embeds
    :param message: Message to edit
    :param channel: Channel to send the message to
    :return: Message sent
    """
    # if neither channel nor message is specified, throw an error
    if not channel and not message:
        raise ValueError("Must specify either a channel or a message")
    if message:  # if message exists, use it to edit the message
        if embed:  # let's send an embed
            if not content.embed:  # oops, no embed to send
                await message.edit(content="Something went wrong.", embed=None)  # erase any existing content and embeds
            else:
                await message.edit(content=None, embed=content.embed)  # erase any existing content and embeds
        else:  # let's send a normal message
            if not content.message:  # oops, no message to send
                await message.edit(content="Something went wrong.", embed=None)  # erase any existing content and embeds
            else:
                await message.edit(content=content.message, embed=None)  # erase any existing content and embeds
        return message
    else:  # otherwise, send a new message in the channel
        if embed:  # let's send an embed
            if not content.embed:  # oops, no embed to send
                return await channel.send(content="Something went wrong.")
            else:
                return await channel.send(content=None, embed=content.embed)
        else:  # let's send a normal message
            if not content.message:  # oops, no message to send
                return await channel.send(content="Something went wrong.")
            else:
                return await channel.send(content=content.message)


async def create_discord_channel(client: discord.Client, guild_id: int, channel_name: str,
                                 channel_type: discord.ChannelType = discord.ChannelType.text) -> \
        Union[discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel]:
    try:
        guild = client.get_guild(guild_id)  # stupid positional-only parameters
        match channel_type:
            case discord.ChannelType.voice:
                return await guild.create_voice_channel(name=channel_name)
            case discord.ChannelType.text:
                return await guild.create_text_channel(name=channel_name)
            case discord.ChannelType.category:
                return await guild.create_category(name=channel_name)
    except:
        raise Exception(f"Could not create channel {channel_name}")


async def get_discord_channel_by_starting_name(client: discord.Client, guild_id: int,
                                               starting_channel_name: str,
                                               channel_type: discord.ChannelType = discord.ChannelType.text) -> \
        Union[discord.VoiceChannel, discord.TextChannel]:
    for channel in client.get_all_channels():
        if channel.name.startswith(starting_channel_name):
            return channel
    return await create_discord_channel(client=client,
                                        guild_id=guild_id,
                                        channel_name=starting_channel_name,
                                        channel_type=channel_type)


async def get_discord_channel_by_name(client: discord.Client, guild_id: int,
                                      channel_name: str,
                                      channel_type: discord.ChannelType = discord.ChannelType.text) -> \
        Union[discord.VoiceChannel, discord.TextChannel, discord.CategoryChannel]:
    for channel in client.get_all_channels():
        if channel.name == channel_name:
            return channel
    error(f"Could not load {channel_name} channel. Attempting to create...")
    return await create_discord_channel(client=client,
                                        guild_id=guild_id,
                                        channel_name=channel_name,
                                        channel_type=channel_type)


def valid_reaction(reaction_emoji: discord.PartialEmoji,
                   reaction_user_id: int,
                   reaction_message: discord.Message,
                   reaction_type: str,
                   valid_reaction_type: str = None,
                   valid_message: discord.Message = None,
                   valid_emojis: List[str] = None,
                   valid_user_ids: List[int] = None) -> bool:
    if valid_reaction_type and reaction_type != valid_reaction_type:
        return False
    if valid_message and reaction_message.id != valid_message.id:
        return False
    if valid_emojis and str(reaction_emoji) not in valid_emojis:
        return False
    if valid_user_ids and reaction_user_id not in valid_user_ids:
        return False
    return True


def get_voice_channel_position(stat_type: str) -> int:
    return statics.voice_channel_order.get(stat_type, None)


class DiscordConnector:
    def __init__(self,
                 token: str,
                 guild_id: int,
                 admin_ids: List[int],
                 refresh_time: int,
                 library_refresh_time: int,
                 tautulli_channel_name: str,
                 tautulli_connector: TautulliConnector,
                 analytics,
                 use_embeds: bool):
        self.token = token
        self.guild_id = guild_id
        self.admin_ids = admin_ids
        self.refresh_time = refresh_time
        self.library_refresh_time = library_refresh_time
        self.tautulli_channel_name = tautulli_channel_name
        self.tautulli_channel: discord.TextChannel = None
        self.tautulli_voice_category: discord.CategoryChannel = None
        self.tautulli = tautulli_connector
        self.analytics = analytics
        self.use_embeds = use_embeds

        intents = discord.Intents.default()
        intents.reactions = True
        self.client = discord.Client(intents=intents)
        self.on_ready = self.client.event(self.on_ready)
        self.on_raw_reaction_add = self.client.event(self.on_raw_reaction_add)

        self.current_message = None

    def connect(self) -> None:
        info('Connecting to Discord...')
        self.client.run(self.token)

    @property
    def voice_category_name(self) -> str:
        return self.tautulli.voice_channel_settings.get("category_name", "Tautulli Stats")

    async def on_ready(self) -> None:
        info('Connected to Discord.')

        info("Loading Tautulli text settings...")
        await self.collect_tautulli_channel()
        await self.collect_old_message_in_tautulli_channel()

        info("Loading Tautulli voice settings...")
        await self.collect_tautulli_voice_category()

        info("Loading Tautulli summary message service...")
        # minimum 5-second sleep time hard-coded, trust me, don't DDoS your server
        asyncio.create_task(self.run_live_summary_message_service(message=self.current_message,
                                                                  refresh_time=max([5, self.refresh_time])))

        info("Starting Tautulli library stats service...")
        # minimum 5-minute sleep time hard-coded, trust me, don't DDoS your server
        asyncio.create_task(self.run_library_stats_service(refresh_time=max([5*60, self.library_refresh_time])))

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        emoji = payload.emoji
        user_id = payload.user_id
        message = await self.tautulli_channel.fetch_message(payload.message_id)
        reaction_type = "REACTION_ADD"

        if valid_reaction(reaction_emoji=emoji,
                          reaction_user_id=user_id,
                          reaction_message=message,
                          reaction_type=reaction_type,
                          valid_message=self.current_message,
                          valid_reaction_type=None,  # We already know it's the right type
                          valid_emojis=statics.emoji_numbers,
                          valid_user_ids=self.admin_ids):
            # message here will be the current message, so we can just use that
            end_notification = await self.stop_tautulli_stream_via_reaction_emoji(emoji=emoji, message=message)
            if end_notification:
                await end_notification.delete(delay=5)  # delete after 5 seconds

    async def run_live_summary_message_service(self, message: discord.Message, refresh_time: int):
        while True:
            message = await self.edit_summary_message(previous_message=message)
            await asyncio.sleep(refresh_time)

    async def run_library_stats_service(self, refresh_time: int):
        while True:
            await self.update_library_stats_voice_channels()
            await asyncio.sleep(refresh_time)

    def is_me(self, message) -> bool:
        return message.author == self.client.user

    async def stop_tautulli_stream_via_reaction_emoji(self, emoji: discord.PartialEmoji, message: discord.Message) -> \
            discord.Message:
        # remember to shift by 1 to convert index to human-readable
        stream_number = statics.emoji_numbers.index(str(emoji)) + 1

        debug(f"Stopping stream {stream_number}...")
        stopped_message = self.tautulli.stop_stream(stream_number=stream_number)
        info(stopped_message)
        end_notification = await self.tautulli_channel.send(content=stopped_message)
        await message.clear_reaction(str(emoji))
        return end_notification

    async def edit_summary_message(self, previous_message) -> discord.Message:
        """
        Collect new summary info, replace old message with new one
        :param previous_message: discord.Message to replace
        :return: new discord.Message
        """
        data_wrapper, count, activity = self.tautulli.refresh_data()

        await self.update_live_voice_channels(activity=activity, category=self.tautulli_voice_category)

        """
        For performance and aesthetics, edit the old message if:
        1) the old message is the newest message in the channel, or
        2) if the only messages that are newer were written by this bot 
        (which would be stream stop messages that have already been deleted)
        """
        use_old_message = False
        async for msg in self.tautulli_channel.history(limit=100):
            if msg.author != self.client.user:
                use_old_message = False
                break
            elif msg.id == previous_message.id:
                use_old_message = True
                break

        if use_old_message:
            # reuse the old message to avoid spamming the channel
            debug('Using old message...')
            await previous_message.clear_reactions()
            if not activity or data_wrapper.error:
                # error when refreshing Tautulli data, new_message is string (i.e. "Connection lost")
                debug("Editing old message with Tautulli error...")
            else:
                debug('Editing old message...')
            # update the message regardless of whether the content has changed
            new_message = await send_message(content=data_wrapper,
                                             embed=self.use_embeds,
                                             message=previous_message)
        else:
            # send a new message each time
            # first, attempt to delete the start-up message if it exists
            try:
                await previous_message.delete()
            except Exception as delete_exception:
                debug(f"Failed to delete old (specified) message: {delete_exception}")
                await self.tautulli_channel.purge(check=self.is_me)
            # send new message
            debug("Using new message...")
            if not activity or data_wrapper.error:
                # error when refreshing Tautulli data, new_message is string (i.e. "Connection lost")
                debug("Sending new message with Tautulli error...")
            else:
                debug('Sending new message...')
            # send a new message, regardless of whether the content has changed
            new_message = await send_message(content=data_wrapper, channel=self.tautulli_channel,
                                             embed=self.use_embeds)

        if data_wrapper.plex_pass:
            await add_emoji_number_reactions(message=new_message, count=count)
            # on_raw_reaction_add will handle the rest

        # Store the message
        self.current_message = new_message
        return self.current_message

    async def collect_tautulli_channel(self) -> None:
        info(f"Getting {self.tautulli_channel_name} channel")
        self.tautulli_channel: discord.TextChannel = \
            await get_discord_channel_by_name(client=self.client, guild_id=self.guild_id,
                                              channel_name=self.tautulli_channel_name)
        if not self.tautulli_channel:
            raise Exception(f"Could not load {self.tautulli_channel_name} channel. Exiting...")
        info(f"{self.tautulli_channel_name} channel collected.")

    async def collect_tautulli_voice_category(self) -> None:
        info(f"Getting {self.voice_category_name} voice category")
        self.tautulli_voice_category: discord.CategoryChannel = \
            await get_discord_channel_by_name(client=self.client, guild_id=self.guild_id,
                                              channel_name=self.voice_category_name,
                                              channel_type=discord.ChannelType.category)
        if not self.tautulli_voice_category:
            raise Exception(f"Could not load {self.voice_category_name} voice category. Exiting...")
        info(f"{self.voice_category_name} voice category collected.")

    async def collect_old_message_in_tautulli_channel(self) -> None:
        """
        Get the last message sent in the Tautulli channel, used to start the bot loop
        :return: discord.Message
        """
        # If the very last message in the channel is from Tauticord, use it
        async for msg in self.tautulli_channel.history(limit=1):
            if msg.author == self.client.user:
                await msg.clear_reactions()

                # Store the message
                self.current_message = msg
                return

        # If the very last message in the channel is not from Tauticord, make a new one.
        info("Couldn't find old message, sending initial message...")
        starter_message = await send_starter_message(tautulli_connector=self.tautulli,
                                                     discord_channel=self.tautulli_channel)
        # Store the message
        self.current_message = starter_message
        return

    async def edit_int_stat_voice_channel(self,
                                          channel_name: str,
                                          number: int,
                                          category: discord.CategoryChannel = None) -> None:
        channel = await get_discord_channel_by_starting_name(client=self.client,
                                                             guild_id=self.guild_id,
                                                             starting_channel_name=f"{channel_name}:",
                                                             channel_type=discord.ChannelType.voice)
        if not channel:
            error(f"Could not load {channel_name} channel")
        else:
            try:
                await channel.edit(name=f"{channel_name}: {number}",
                                   category=category)
            except Exception as voice_channel_edit_error:
                error(f"Error editing {channel_name} voice channel: {voice_channel_edit_error}")

    async def update_live_voice_channels(self, activity, category: discord.CategoryChannel = None) -> None:
        if activity:
            if self.tautulli.voice_channel_settings.get('count', False):
                info(f"Updating Streams voice channel with new stream count")
                await self.edit_int_stat_voice_channel(channel_name="Current Streams",
                                                       number=activity.stream_count,
                                                       category=category)
            if self.tautulli.voice_channel_settings.get('transcodes', False):
                info(f"Updating Transcodes voice channel with new stream count")
                await self.edit_int_stat_voice_channel(channel_name="Current Transcodes",
                                                       number=activity.transcode_count,
                                                       category=category)
            if self.tautulli.voice_channel_settings.get('bandwidth', False):
                info(f"Updating Bandwidth voice channel with new bandwidth")
                await self.edit_int_stat_voice_channel(channel_name="Bandwidth",
                                                       number=activity.total_bandwidth,
                                                       category=category)
            if self.tautulli.voice_channel_settings.get('localBandwidth', False):
                info(f"Updating Local Bandwidth voice channel with new bandwidth")
                await self.edit_int_stat_voice_channel(channel_name="Local Bandwidth",
                                                       number=activity.lan_bandwidth,
                                                       category=category)
            if self.tautulli.voice_channel_settings.get('remoteBandwidth', False):
                info(f"Updating Remote Bandwidth voice channel with new bandwidth")
                await self.edit_int_stat_voice_channel(channel_name="Remote Bandwidth",
                                                       number=activity.wan_bandwidth,
                                                       category=category)

    async def update_library_stats_voice_channels(self) -> None:
        info("Updating library stats...")
        if self.tautulli.voice_channel_settings.get('stats', False):
            for library_name in self.tautulli.voice_channel_settings.get('libraries', []):
                size = self.tautulli.get_library_item_count(library_name=library_name)
                info(f"Updating {library_name} voice channel with new library size")
                await self.edit_int_stat_voice_channel(channel_name=library_name,
                                                       number=size,
                                                       category=self.tautulli_voice_category)
