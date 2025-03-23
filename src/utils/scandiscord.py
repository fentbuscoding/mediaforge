"""
Miscellaneous helper functions for commands
"""

import json
import asyncio
from typing import Optional, List

import discord
import regex as re
from discord.ext import commands

import config
from core.clogs import logger
from utils.common import fetch
from utils.tempfiles import TenorUrl
from utils.web import contentlength

# Compile regex patterns once
tenor_url_regex = re.compile(r"https?://tenor\.com/view/([^-]+-)*(\d+)/?")
txt_file_regex = re.compile(r".*\.txt$", re.IGNORECASE)

async def handlemessagesave(m: discord.Message, ignoreatts: Optional[List[discord.Attachment]] = None) -> List[str]:
    """
    handles saving of media from discord messages
    :param m: a discord message
    :param ignoreatts: list of discord attachments to ignore
    :return: list of file URLs detected in the message
    """
    detectedfiles = []
    
    # Handle thread starter messages
    if m.type == discord.MessageType.thread_starter_message:
        m = m.reference.resolved

    # Process embeds
    if m.embeds:
        embed_tasks = []
        for embed in m.embeds:
            if embed.type == "gifv":
                if (match := tenor_url_regex.fullmatch(embed.url)):
                    gif_id = match.group(2)
                    tenor_task = asyncio.create_task(fetch(
                        f"https://tenor.googleapis.com/v2/posts?ids={gif_id}&key={config.tenor_key}&limit=1"
                    ))
                    embed_tasks.append(tenor_task)
            elif embed.type in ["image", "video", "audio"]:
                url_check = asyncio.create_task(contentlength(embed.url))
                embed_tasks.append(url_check)
                if embed.type == "image":
                    thumb_check = asyncio.create_task(contentlength(embed.thumbnail.url))
                    embed_tasks.append(thumb_check)
        
        # Wait for all async tasks to complete
        results = await asyncio.gather(*embed_tasks, return_exceptions=True)
        
        # Process results
        for result in results:
            if isinstance(result, str):
                # Handle tenor API response
                tenor_data = json.loads(result)
                if 'results' in tenor_data:
                    detectedfiles.append(TenorUrl(tenor_data['results'][0]['media_formats']['mp4']['url']))
            elif result:  # Handle content length checks
                detectedfiles.append(embed.url)

    # Process attachments
    if m.attachments and (ignoreatts is None or any(att not in ignoreatts for att in m.attachments)):
        detectedfiles.extend(
            att.url for att in m.attachments 
            if not txt_file_regex.match(att.filename)
        )

    # Process stickers
    if m.stickers:
        detectedfiles.extend(
            str(sticker.url) 
            for sticker in m.stickers 
            if sticker.format != discord.StickerFormatType.lottie
        )

    return detectedfiles

async def imagesearch(ctx, nargs=1, ignore: Optional[List[discord.Attachment]] = None):
    """
    searches the channel for nargs media
    :param ctx: command context
    :param nargs: amount of media to return
    :param ignore: attachments to ignore
    :return: False if none or not enough media found, list of file paths if found
    """
    outfiles = []
    seen_messages = set()

    # Check current message
    seen_messages.add(ctx.message.id)
    outfiles.extend(await handlemessagesave(ctx.message, ignoreatts=ignore))
    if len(outfiles) >= nargs:
        return outfiles[:nargs]

    # Check referenced message if exists
    if ctx.message.reference and ctx.message.reference.resolved:
        ref_msg = ctx.message.reference.resolved
        seen_messages.add(ref_msg.id)
        outfiles.extend(await handlemessagesave(ref_msg))
        if len(outfiles) >= nargs:
            return outfiles[:nargs]

    # Check channel history
    async for m in ctx.channel.history(limit=50, before=ctx.message):
        if m.id not in seen_messages:
            seen_messages.add(m.id)
            outfiles.extend(await handlemessagesave(m))
            if len(outfiles) >= nargs:
                return outfiles[:nargs]

    return False if not outfiles else outfiles


async def handletenor(m: discord.Message, ctx: commands.Context, gif=False):
    """
    like handlemessagesave() but only for tenor
    :param m: discord message
    :param ctx: command context
    :param gif: return GIF url if true, mp4 url if false
    :return: raw tenor media url
    """
    if len(m.embeds):
        if m.embeds[0].type == "gifv":
            # https://github.com/esmBot/esmBot/blob/master/utils/imagedetect.js#L34
            tenor = await fetch(
                f"https://tenor.googleapis.com/v2/posts?ids={m.embeds[0].url.split('-').pop()}&key={config.tenor_key}")
            tenor = json.loads(tenor)
            if 'error' in tenor:
                logger.error(tenor['error'])
                await ctx.send(f"{config.emojis['2exclamation']} Tenor Error! `{tenor['error']}`")
                return False
            else:
                if gif:
                    return TenorUrl(tenor['results'][0]['media_formats']['gif']['url'])
                else:
                    return TenorUrl(tenor['results'][0]['media_formats']['mp4']['url'])
    return None


async def tenorsearch(ctx, gif=False):
    # currently only used for 1 command, might have future uses?
    """
    like imagesearch() but for tenor
    :param ctx: discord context
    :param gif: return GIF url if true, mp4 url if false
    :return:
    """
    if ctx.message.reference:
        m = ctx.message.reference.resolved
        hm = await handletenor(m, ctx, gif)
        if hm is None:
            return False
        else:
            return hm
    else:
        async for m in ctx.channel.history(limit=50):
            hm = await handletenor(m, ctx, gif)
            if hm is not None:
                return hm
    return False
