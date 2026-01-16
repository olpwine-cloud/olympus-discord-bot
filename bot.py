import discord
from discord.ext import commands
import os

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"💖 Bot is online as {bot.user}")

@bot.command()
async def ping(ctx):
    await ctx.send("🏓 Pong! บอทตื่นแล้วจ้า~")

@bot.command()
async def hello(ctx):
    await ctx.send("😈 สวัสดีค่ะ รับบริการอะไรดีคะคนสวย")

TOKEN = os.getenv("DISCORD_TOKEN")
bot.run(TOKEN)
