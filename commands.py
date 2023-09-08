import discord
from discord.ext import commands, tasks
from bottoken import bottoken
import requests
import json
import random


intents = discord.Intents.default()
intents.message_content = True

inventories = {}
trades_in_progress = {}
active_quests = {}

bot = commands.Bot(command_prefix='$', intents=intents)

# Define a structure to hold a quest's details
class Quest:
    def __init__(self, initiator, quest_type="solo", members=None):
        self.initiator = initiator
        self.quest_type = quest_type
        self.members = members if members else []
        self.start_time = discord.utils.utcnow()
        self.quest_content = None  # This will hold the details of the adventure, combat, or puzzle.

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

@tasks.loop(seconds=30)
async def check_party_quests():
    to_remove = []
    for user_id, quest in active_quests.items():
        if quest.quest_type == "party":
            time_elapsed = (discord.utils.utcnow() - quest.start_time).total_seconds()
            if len(quest.members) >= 4 or time_elapsed >= 240:  # 4 minutes
                to_remove.append(user_id)
                # Here you can do something to officially start the quest for the party, e.g. send a message
                # await ctx.send(f"{quest.initiator}'s party quest has started!")
    for user_id in to_remove:
        del active_quests[user_id]

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
            loaded_data = json.load(file)
            inventories = {int(k): v for k, v in loaded_data.items()}
            print('inventories loaded')
    except FileNotFoundError:
        inventories = {}
        print('Failed to load inventories.json')

    # Load trades in progress
    try:
        with open("trades_in_progress.json", "r") as file:
            loaded_data = json.load(file)
            trades_in_progress = {int(k): v for k, v in loaded_data.items()}
            print('trades loaded')
    except FileNotFoundError:
        trades_in_progress = {}
        print('Failed to load trade_in_progress.json')


@bot.event
async def on_ready():
    check_trade_timeouts.start()
    print('bot logged in')
    load_inventories()
    check_party_quests.start()

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

# The questing functions are after this

@bot.command()
async def start_quest(ctx, quest_type="solo"):
    # Check if the user is already in a quest
    if ctx.author.id in active_quests:
        await ctx.send("You're already in a quest!")
        return

    new_quest = Quest(initiator=ctx.author.id, quest_type=quest_type)
    active_quests[ctx.author.id] = new_quest

    if quest_type == "solo":
        await ctx.send(f"{ctx.author.name} has started a solo quest!")
    else:
        await ctx.send(f"{ctx.author.name} has started a party quest! Others can join with $join_quest {ctx.author.name}")

@bot.command()
async def join_quest(ctx, initiator: discord.Member):
    quest = active_quests.get(initiator.id)
    if not quest:
        await ctx.send("That user has not initiated a quest.")
        return

    if quest.quest_type != "party":
        await ctx.send("That's a solo quest, you can't join.")
        return

    if ctx.author.id in quest.members:
        await ctx.send("You've already joined this quest.")
        return

    quest.members.append(ctx.author.id)
    await ctx.send(f"{ctx.author.name} has joined {initiator.name}'s party quest!")

def generate_quest_content():
    quest_type = random.choice(["adventure", "combat", "puzzle"])
    content = {}

    if quest_type == "adventure":
        locations = ["ancient ruins", "a hidden cave", "a mysterious forest", "a deserted village"]
        content["location"] = random.choice(locations)
        content["outcome"] = random.choice(["found a treasure chest!", "discovered an old map.", "encountered a strange creature."])

    elif quest_type == "combat":
        enemies = ["a group of goblins", "a ferocious dragon", "an angry troll", "a cunning thief"]
        content["enemy"] = random.choice(enemies)
        content["outcome"] = random.choice(["defeated the enemy!", "were defeated.", "managed to escape."])

    elif quest_type == "puzzle":
        riddles = [
            {"question": "What comes once in a minute, twice in a moment, but never in a thousand years?", "answer": "m"},
            {"question": "The more you take, the more you leave behind. What am I?", "answer": "steps"},
            # Add more riddles if desired
        ]
        chosen_riddle = random.choice(riddles)
        content["riddle"] = chosen_riddle["question"]
        content["answer"] = chosen_riddle["answer"]

    return quest_type, content

bot.run(bottoken.id)
