import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)


@bot.event
async def on_ready():
    print(f'Sucesso! Bot conectado como: {bot.user.name}')

@bot.command()
async def salve(ctx):
    await ctx.send(f'Salve, {ctx.author.mention}! Tudo tranquilo?')

# Substitua pelo Token que você pegou no Developer Portal
bot.run('SEU_TOKEN_AQUI')