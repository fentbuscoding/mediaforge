import json
import sys
from functools import lru_cache
import apng

from processing.run_command import run_command
from utils.tempfiles import reserve_tempfile

# Cache magic import based on platform
if sys.platform == "win32":
    from winmagic import magic
else:
    import magic

from processing.common import *
from core.clogs import logger

# Common ffprobe flags
COMMON_PROBE_FLAGS = ["-v", "panic"]
JSON_FORMAT_FLAGS = ["-print_format", "json"]

@lru_cache(maxsize=128)
async def is_apng(filename):
    out = await run_command("ffprobe", filename, *COMMON_PROBE_FLAGS, 
                          "-select_streams", "v:0", *JSON_FORMAT_FLAGS,
                          "-show_entries", "stream=codec_name")
    data = json.loads(out)
    return bool(data["streams"]) and data["streams"][0]["codec_name"] == "apng"

@lru_cache(maxsize=128) 
async def get_frame_rate(filename):
    """Gets the FPS of a file"""
    logger.info("Getting FPS...")
    out = await run_command("ffprobe", filename, *COMMON_PROBE_FLAGS, 
                          "-select_streams", "v:0", *JSON_FORMAT_FLAGS,
                          "-show_entries", "stream=r_frame_rate,codec_name")
    data = json.loads(out)
    
    if data["streams"][0]["codec_name"] == "apng":
        return _get_apng_framerate(filename)
    
    rate = data["streams"][0]["r_frame_rate"].split("/")
    return float(rate[0]) / float(rate[1]) if len(rate) == 2 else float(rate[0])

def _get_apng_framerate(filename):
    """Helper function to calculate APNG framerate"""
    parsedapng = apng.APNG.open(filename)
    total_delay = sum(control.delay / (control.delay_den or 100) 
                     for _, control in parsedapng.frames)
    return len(parsedapng.frames) / total_delay

@lru_cache(maxsize=128)
async def get_duration(filename):
    """Gets the duration of a file"""
    logger.info("Getting duration...")
    out = await run_command("ffprobe", *COMMON_PROBE_FLAGS,
                          "-show_entries", "format=duration", 
                          "-of", "default=noprint_wrappers=1:nokey=1", 
                          filename)
    
    if out == "N/A":
        return _get_apng_duration(filename)
    return float(out)

def _get_apng_duration(filename):
    """Helper function to calculate APNG duration"""
    parsedapng = apng.APNG.open(filename)
    return sum(control.delay / (control.delay_den or 100)
              for _, control in parsedapng.frames)

async def get_resolution(filename):
    """
    gets the resolution of a file
    :param filename: filename
    :return: [width, height]
    """
    out = await run_command("ffprobe", "-v", "panic", "-select_streams", "v:0", "-show_entries",
                            "stream=width,height:stream_tags=rotate",
                            "-print_format", "json", filename)
    out = json.loads(out)
    w = out["streams"][0]["width"]
    h = out["streams"][0]["height"]
    # if rotated in metadata, swap width and height
    if "tags" in out["streams"][0]:
        if "rotate" in out["streams"][0]["tags"]:
            rot = float(out["streams"][0]["tags"]["rotate"])
            if rot % 90 == 0 and not rot % 180 == 0:
                w, h = h, w
    return [w, h]


async def get_vcodec(filename):
    """
    gets the codec of a video
    :param filename: filename
    :return: dict containing "codec_name" and "codec_long_name"
    """
    out = await run_command("ffprobe", "-v", "panic", "-select_streams", "v:0", "-show_entries",
                            "stream=codec_name,codec_long_name",
                            "-print_format", "json", filename)
    out = json.loads(out)
    if out["streams"]:
        return out["streams"][0]
    else:
        # only checks for video codec, audio files return Nothinng
        return None


async def get_acodec(filename):
    """
    gets the codec of audio
    :param filename: filename
    :return: dict containing "codec_name" and "codec_long_name"
    """
    out = await run_command("ffprobe", "-v", "panic", "-select_streams", "a:0", "-show_entries",
                            "stream=codec_name,codec_long_name",
                            "-print_format", "json", filename)
    out = json.loads(out)
    if out["streams"]:
        return out["streams"][0]
    else:
        return None


async def va_codecs(filename):
    out = await run_command('ffprobe', '-v', 'panic', '-show_entries', 'stream=codec_name,codec_type', '-print_format',
                            'json', filename)
    out = json.loads(out)
    acodec = None
    vcodec = None
    if out["streams"]:
        for stream in out["streams"]:
            if stream["codec_type"] == "video" and vcodec is None:
                vcodec = stream["codec_name"]
            elif stream["codec_type"] == "audio" and acodec is None:
                acodec = stream["codec_name"]
        return vcodec, acodec
    else:
        return None


async def ffprobe(file):
    return [await run_command("ffprobe", "-hide_banner", file), magic.from_file(file, mime=False),
            magic.from_file(file, mime=True)]


async def count_frames(video):
    # https://stackoverflow.com/a/28376817/9044183
    return int(await run_command("ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                                 "stream=nb_read_packets", "-of", "csv=p=0", video))


async def frame_n(video, n: int):
    framecount = await count_frames(video)
    if not -1 <= n < framecount:
        raise NonBugError(f"Frame {n} does not exist.")
    if n == -1:
        n = framecount - 1
    frame = reserve_tempfile("mkv")
    await run_command("ffmpeg", "-hide_banner", "-i", video, "-vf", f"select='eq(n,{n})'", "-vframes", "1",
                      "-c:v", "ffv1", frame)
    return frame


async def hasaudio(video):
    return bool(
        await run_command("ffprobe", "-i", video, "-show_streams", "-select_streams", "a", "-loglevel", "panic"))
