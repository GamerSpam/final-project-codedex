# Setting up the bot to use my token

import discord
from bottoken import bottoken
import requests
import json
from discord.ext import commands

def get_meme():
  response = requests.get('https://meme-api.com/gimme')
  json_data = json.loads(response.text)
  return json_data['url']

class MyClient(discord.Client):
    async def on_ready(self):
        print('Logged on as {0}!'.format(self.user))

    async def on_message(self, message):
        if message.author == self.user:
            return

        if message.content.startswith('$meme'):
            await message.channel.send(get_meme())


intents = discord.Intents.default()
intents.message_content = True

client = MyClient(intents = intents)
client.run(bottoken.id) # collects my token from the obfuscated file

MyClient = commands.Bot(command_prefix='$', intents=intents)

@MyClient.command()
async def testcom(ctx):
    pass