import discord
from discord.ext import commands, tasks
from bottoken import bottoken
import requests, json

intents = discord.Intents.default()
intents.message_content = True

inventories = {}
trades_in_progress = {}

bot = commands.Bot(command_prefix='$', intents=intents)


def save_inventories():
    with open("inventories.json", "w") as file:
        json.dump(inventories, file)

    with open("trades_in_progress.json", "w") as file:
        json.dump(trades_in_progress, file)


def load_inventories():
    global inventories
    global trades_in_progress

    # Load inventories
    try:
        with open("inventories.json", "r") as file:
            inventories = json.load(file)
            print('inventories loaded')
    except FileNotFoundError:
        inventories = {}
        print('Failed to load inventories.json')

    # Load trades in progress
    try:
        with open("trades_in_progress.json", "r") as file:
            trades_in_progress = json.load(file)
            print('trades loaded')
    except FileNotFoundError:
        trades_in_progress = {}
        print('Failed to load trade_in_progress.json')


@bot.event
async def on_ready():
    check_trade_timeouts.start()
    print('bot logged in')
    load_inventories()

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

# I used ChatGPT to assist in writing the following code. I am trying to set up the basic inventory and trading system here.

@bot.command()
async def give(ctx, item: str, quantity: int):
    user_id = ctx.author.id
    if user_id not in inventories:
        inventories[user_id] = {}
    inventories[user_id][item] = inventories[user_id].get(item, 0) + quantity
    await ctx.send(f"Gave {quantity} {item}(s) to {ctx.author.name}")
    save_inventories()

@bot.command()
async def inventory(ctx):
    user_id = ctx.author.id
    inventory = inventories.get(user_id, {})
    if not inventory:
        await ctx.send(f"{ctx.author.name}, your inventory is empty!")
        return
    response = f"**{ctx.author.name}'s Inventory**\n"
    for item, quantity in inventory.items():
        response += f"{item}: {quantity}\n"
    await ctx.send(response)


@tasks.loop(seconds=60)
async def check_trade_timeouts():
    to_remove = []
    for user_id, trade in trades_in_progress.items():
        if trade["status"] == "pending" and (discord.utils.utcnow() - trade["started_at"]).total_seconds() > 300:  # 5 minutes timeout
            to_remove.append(user_id)
            trade["status"] = "timeout"

            # Return the escrowed items for the specific trade that timed out
            escrowed_items_for_user = trade["escrow"].get(user_id, {})
            for item, quantity in escrowed_items_for_user.items():
                inventories[user_id].setdefault(item, 0)
                inventories[user_id][item] += quantity

            escrowed_items_for_partner = trade["escrow"].get(partner_id, {})
            for item, quantity in escrowed_items_for_partner.items():
                inventories[partner_id].setdefault(item, 0)
                inventories[partner_id][item] += quantity

    for user_id in to_remove:
        trade = trades_in_progress.pop(user_id)
        partner_id = trade["initiator_id"] if user_id == trade["partner_id"] else trade["partner_id"]
        trades_in_progress.pop(partner_id, None)

    save_inventories()

# Command to initiate a trade with another user
@bot.command()
async def trade(ctx, partner: discord.Member):
    # Create a new trade structure
    new_trade = {
        "initiator_id": ctx.author.id,
        "partner_id": partner.id,
        "escrow": {
            ctx.author.id: {},
            partner.id: {}
        },
        "status": "pending"
    }

    # Save the trade to the trades_in_progress using the user IDs as keys
    trades_in_progress[ctx.author.id] = new_trade
    trades_in_progress[partner.id] = new_trade

    await ctx.send(f"Trade initiated between {ctx.author.name} and {partner.name}!")

# Command to offer items in a trade
@bot.command()
async def offer(ctx, item: str, quantity: int):
    if ctx.author.id not in trades_in_progress:
        await ctx.send("You're not currently in a trade.")
        return

    trade = trades_in_progress[ctx.author.id]

    # Check if user has the item and quantity
    user_inventory = inventories.get(ctx.author.id, {})
    if user_inventory.get(item, 0) < quantity:
        await ctx.send(f"You don't have enough {item}s to offer!")
        return

    # Remove items from user's inventory and place them in escrow
    user_inventory[item] -= quantity
    trade["escrow"][ctx.author.id][item] = trade["escrow"][ctx.author.id].get(item, 0) + quantity

    await ctx.send(f"{quantity} {item}(s) added to the trade offer!")

    save_inventories()

# Command to confirm a trade from both sides
@bot.command()
async def confirm(ctx):
    if ctx.author.id not in trades_in_progress:
        await ctx.send("You're not currently in a trade.")
        return

    trade = trades_in_progress[ctx.author.id]

    # Check if it's the initiator or partner confirming
    if ctx.author.id == trade["initiator_id"]:
        trade["initiator_confirmed"] = True
    else:
        trade["partner_confirmed"] = True

    # If both have confirmed, transfer items and finalize the trade
    if trade.get("initiator_confirmed") and trade.get("partner_confirmed"):
        transfer_items(trade)
        await ctx.send("Trade completed successfully!")

    save_inventories()

# Command to cancel a trade
@bot.command()
async def cancel(ctx):
    if ctx.author.id not in trades_in_progress:
        await ctx.send("You're not currently in a trade.")
        return

    trade = trades_in_progress[ctx.author.id]

    # Return escrowed items to their owners
    for user_id, escrowed_items in trade["escrow"].items():
        for item, quantity in escrowed_items.items():
            inventories[user_id].setdefault(item, 0)
            inventories[user_id][item] += quantity

    del trades_in_progress[ctx.author.id]
    del trades_in_progress[trade["partner_id"]]

    await ctx.send("Trade cancelled and items returned!")

    save_inventories()

def transfer_items(trade):
    # Transfer escrowed items from each user to their trading partner
    for user_id, escrowed_items in trade["escrow"].items():
        receiver_id = trade["partner_id"] if user_id == trade["initiator_id"] else trade["initiator_id"]
        for item, quantity in escrowed_items.items():
            inventories[receiver_id].setdefault(item, 0)
            inventories[receiver_id][item] += quantity

    # Remove the trade from the trades_in_progress
    del trades_in_progress[trade["initiator_id"]]
    del trades_in_progress[trade["partner_id"]]

    save_inventories()

bot.run(bottoken.id)
