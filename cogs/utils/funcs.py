from __future__ import annotations
from typing import TYPE_CHECKING

from discord.utils import MISSING

if TYPE_CHECKING:
    from typing import Any
    from discord import Embed, File, AllowedMentions, Interaction
    from discord.ui.view import View


async def send(
    interaction: Interaction,
    content: Any = None,
    *,
    embed: Embed = MISSING,
    embeds: list[Embed] = MISSING,
    file: File = MISSING,
    files: list[File] = MISSING,
    allowed_mentions: AllowedMentions = MISSING,
    view: View = MISSING,
    tts: bool = False,
    ephemeral: bool = False,
) -> None:
    if interaction.response._responded:
        sender = interaction.followup.send
    else:
        sender = interaction.response.send_message
    await sender(
        content=content,  # type: ignore
        embed=embed,
        embeds=embeds,
        file=file,
        files=files,
        allowed_mentions=allowed_mentions,
        view=view,
        tts=tts,
        ephemeral=ephemeral,
    )