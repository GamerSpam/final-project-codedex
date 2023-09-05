import discord
from discord.ext import commands
from bottoken import bottoken
import requests, json

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='$', intents=intents)

def get_meme():
  response = requests.get('https://meme-api.com/gimme')
  json_data = json.loads(response.text)
  return json_data['url']

@bot.command()
async def test(ctx, arg):
    await ctx.send(arg)

@bot.command()
async def meme(ctx):
    await ctx.send(get_meme())

bot.run(bottoken.id)