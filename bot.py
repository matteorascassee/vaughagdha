import discord
from discord import app_commands
from discord.ext import commands
import json
import os
from dotenv import load_dotenv
import asyncio
from datetime import datetime

def parse_timestamp(timestamp_str):
    try:
        # Si le timestamp est déjà un nombre (timestamp Unix), retourne-le directement
        return int(float(timestamp_str))
    except ValueError:
        # Sinon, parse la chaîne ISO 8601 en datetime, puis en timestamp Unix
        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        return int(dt.timestamp())

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
DATA_DIR = 'data'

class JudicialBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix='!', intents=intents)
        self.data = {}
        self.load_data()

    def load_data(self):
        print("Chargement des données...")
        for filename in os.listdir(DATA_DIR):
            if filename.endswith('.json'):
                filepath = os.path.join(DATA_DIR, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    try:
                        json_data = json.load(f)
                        suspect_name = json_data.get('channel', {}).get('name', 'Inconnu').lower().strip()
                        messages = json_data.get('messages', [])
                        for msg in messages:
                            content = msg.get('content', '')
                            if content:
                                details = {
                                    'id': msg.get('id'),
                                    'timestamp': parse_timestamp(msg.get('timestamp')),  # Parse the timestamp
                                    'author': msg.get('author', {}).get('name'),
                                    'content': content,
                                    'attachments': [att.get('url') for att in msg.get('attachments', [])],
                                    'embeds': msg.get('embeds', []),
                                    'filename': filename
                                }
                                if suspect_name not in self.data:
                                    self.data[suspect_name] = []
                                self.data[suspect_name].append(details)
                    except json.JSONDecodeError:
                        print(f"Erreur de lecture : {filename}")
        print(f"Données chargées : {len(self.data)} suspects uniques.")

bot = JudicialBot()

@bot.event
async def on_ready():
    print(f'Bot connecté en tant que {bot.user}')
    await bot.tree.sync()

# Commande /help
@bot.tree.command(name='help', description='Affiche la liste des commandes disponibles')
async def help(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📚 **Centre d’Aide - JudicialBot**",
        description="Voici les commandes disponibles pour consulter les casiers judiciaires :",
        color=discord.Color.from_str("#2b2d31")
    )
    embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/.../icon_judicial.png")  # Remplace par une URL d'icône
    embed.add_field(
        name="🔍 **/search <nom>**",
        value="Recherche un casier judiciaire par nom (partiel ou complet).\n*Exemple : `/search Dupont`*",
        inline=False
    )
    embed.add_field(
        name="📜 **/list [query]**",
        value="Liste tous les suspects (avec pagination). Filtre par nom si un terme est fourni.\n*Exemple : `/list alex`*",
        inline=False
    )
    embed.add_field(
        name="📄 **/details <id>**",
        value="Affiche les détails complets d’un message via son ID.\n*Exemple : `/details 1339638257243394201`*",
        inline=False
    )
    embed.add_field(
        name="🧬 **/adn <numero>**",
        value="Recherche un suspect par numéro ADN présent dans les rapports.\n*Exemple : `/adn 44915`*",
        inline=False
    )
    embed.add_field(
        name="⚖️ **/faits <mot-clé>**",
        value="Recherche des suspects par faits mentionnés dans les rapports.\n*Exemple : `/faits vol`*",
        inline=False
    )
    embed.set_footer(text="⚠️ Utilisez les commandes avec / dans un salon autorisé.")
    await interaction.response.send_message(embed=embed)

# Commande /search
@bot.tree.command(name='search', description='Recherche un casier judiciaire par nom')
@app_commands.describe(nom='Nom du suspect (partiel ou complet)')
async def search(interaction: discord.Interaction, nom: str):
    await interaction.response.defer()
    nom_lower = nom.lower().strip()
    matching_suspects = [suspect for suspect in bot.data.keys() if nom_lower in suspect]

    if not matching_suspects:
        embed = discord.Embed(
            title="❌ **Aucun résultat**",
            description=f"Aucun casier judiciaire trouvé pour **{nom}**.",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)
        return

    embeds = []
    for suspect in matching_suspects:
        results = bot.data[suspect]
        for idx, res in enumerate(results, 1):
            embed = discord.Embed(
                title=f"🔍 **Casier : {suspect.title()}** ({idx}/{len(results)})",
                color=discord.Color.from_str("#3498db")
            )
            embed.add_field(name="📅 **Date**", value=f"<t:{res['timestamp']}:F>", inline=True)
            embed.add_field(name="👤 **Auteur**", value=res['author'], inline=True)
            embed.add_field(name="\u200b", value="\u200b", inline=False)  # Espacement
            embed.add_field(name="📝 **Rapport**", value=res['content'][:1000] + ("..." if len(res['content']) > 1000 else ""), inline=False)
            if res['attachments']:
                embed.add_field(name="📎 **Pièces jointes**", value='\n'.join(f"[Lien {i+1}]({url})" for i, url in enumerate(res['attachments'][:3])), inline=False)
            embed.set_footer(text=f"ID: {res['id']} | Source: {res['filename']}")
            embeds.append(embed)

    if not embeds:
        embed = discord.Embed(
            title="❌ **Aucun résultat**",
            description=f"Aucun casier trouvé pour **{nom}**.",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)
        return

    current_page = 0
    message = await interaction.followup.send(embed=embeds[current_page])

    if len(embeds) > 1:
        await message.add_reaction('◀️')
        await message.add_reaction('▶️')

        def check(reaction, user):
            return user == interaction.user and str(reaction.emoji) in ['◀️', '▶️'] and reaction.message.id == message.id

        while True:
            try:
                reaction, user = await bot.wait_for('reaction_add', timeout=60.0, check=check)
                if str(reaction.emoji) == '▶️' and current_page < len(embeds) - 1:
                    current_page += 1
                elif str(reaction.emoji) == '◀️' and current_page > 0:
                    current_page -= 1
                await message.edit(embed=embeds[current_page])
                await message.remove_reaction(reaction, user)
            except asyncio.TimeoutError:
                await message.clear_reactions()
                break

# Commande /list
@bot.tree.command(name='list', description='Liste les suspects (avec pagination)')
@app_commands.describe(query='Filtre par nom (optionnel)')
async def list_suspects(interaction: discord.Interaction, query: str = None):
    await interaction.response.defer()
    suspects = sorted(bot.data.keys())

    if not suspects:
        embed = discord.Embed(
            title="❌ **Aucune donnée**",
            description="Aucun suspect enregistré dans la base de données.",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)
        return

    if query:
        query_lower = query.lower().strip()
        filtered_suspects = [s for s in suspects if query_lower in s]
        if not filtered_suspects:
            embed = discord.Embed(
                title="❌ **Aucun résultat**",
                description=f"Aucun suspect trouvé pour **{query}**.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed)
            return
    else:
        filtered_suspects = suspects

    items_per_page = 15
    pages = [filtered_suspects[i:i + items_per_page] for i in range(0, len(filtered_suspects), items_per_page)]

    async def send_page(page_num):
        embed = discord.Embed(
            title=f"📜 **Liste des suspects**{' (filtré)' if query else ''}",
            description="\n".join(f"{i+1}. **{suspect.title()}**" for i, suspect in enumerate(pages[page_num])),
            color=discord.Color.from_str("#2ecc71")
        )
        embed.set_footer(text=f"Page {page_num + 1}/{len(pages)} | Total: {len(filtered_suspects)} suspects")
        return embed

    current_page = 0
    message = await interaction.followup.send(embed=await send_page(current_page))

    if len(pages) > 1:
        await message.add_reaction('🏠')
        await message.add_reaction('◀️')
        await message.add_reaction('▶️')

        def check(reaction, user):
            return user == interaction.user and str(reaction.emoji) in ['🏠', '◀️', '▶️'] and reaction.message.id == message.id

        while True:
            try:
                reaction, user = await bot.wait_for('reaction_add', timeout=60.0, check=check)
                if str(reaction.emoji) == '▶️' and current_page < len(pages) - 1:
                    current_page += 1
                elif str(reaction.emoji) == '◀️' and current_page > 0:
                    current_page -= 1
                elif str(reaction.emoji) == '🏠':
                    current_page = 0
                await message.edit(embed=await send_page(current_page))
                await message.remove_reaction(reaction, user)
            except asyncio.TimeoutError:
                await message.clear_reactions()
                break

# Commande /details
@bot.tree.command(name='details', description='Affiche les détails d’un message par ID')
@app_commands.describe(id='ID du message')
async def details(interaction: discord.Interaction, id: str):
    await interaction.response.defer()
    found = False

    for suspect, results in bot.data.items():
        for res in results:
            if res['id'] == id:
                embed = discord.Embed(
                    title=f"📄 **Détails du rapport** (ID: {id})",
                    description=f"**Suspect** : {suspect.title()}",
                    color=discord.Color.from_str("#e74c3c")
                )
                embed.add_field(name="📅 **Date**", value=f"<t:{res['timestamp']}:F>", inline=True)
                embed.add_field(name="👤 **Auteur**", value=res['author'], inline=True)
                embed.add_field(name="\u200b", value="\u200b", inline=False)
                embed.add_field(name="📝 **Contenu**", value=res['content'][:4000], inline=False)
                if res['attachments']:
                    embed.add_field(name="📎 **Pièces jointes**", value='\n'.join(f"[Lien {i+1}]({url})" for i, url in enumerate(res['attachments'])), inline=False)
                embed.set_footer(text=f"Source: {res['filename']}")
                await interaction.followup.send(embed=embed)
                found = True
                break
        if found:
            break

    if not found:
        embed = discord.Embed(
            title="❌ **ID introuvable**",
            description=f"Aucun message trouvé avec l’ID **{id}**.",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)

# Commande /adn
@bot.tree.command(name='adn', description='Recherche un suspect par numéro ADN')
@app_commands.describe(adn='Numéro ADN à rechercher')
async def adn(interaction: discord.Interaction, adn: str):
    await interaction.response.defer()
    matching_results = []

    for suspect, results in bot.data.items():
        for res in results:
            if adn in res['content']:
                matching_results.append((suspect, res))

    if not matching_results:
        embed = discord.Embed(
            title="❌ **Aucun résultat**",
            description=f"Aucun casier judiciaire trouvé contenant l'ADN **{adn}**.",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)
        return

    embeds = []
    for idx, (suspect, res) in enumerate(matching_results, 1):
        embed = discord.Embed(
            title=f"🧬 **Recherche ADN : {adn}** ({idx}/{len(matching_results)})",
            description=f"**Suspect** : {suspect.title()}",
            color=discord.Color.from_str("#9b59b6")
        )
        embed.add_field(name="📅 **Date**", value=f"<t:{res['timestamp']}:F>", inline=True)
        embed.add_field(name="👤 **Auteur**", value=res['author'], inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=False)  # Espacement
        embed.add_field(name="📝 **Rapport**", value=res['content'][:1000] + ("..." if len(res['content']) > 1000 else ""), inline=False)
        if res['attachments']:
            embed.add_field(name="📎 **Pièces jointes**", value='\n'.join(f"[Lien {i+1}]({url})" for i, url in enumerate(res['attachments'][:3])), inline=False)
        embed.set_footer(text=f"ID: {res['id']} | Source: {res['filename']}")
        embeds.append(embed)

    current_page = 0
    message = await interaction.followup.send(embed=embeds[current_page])

    if len(embeds) > 1:
        await message.add_reaction('◀️')
        await message.add_reaction('▶️')

        def check(reaction, user):
            return user == interaction.user and str(reaction.emoji) in ['◀️', '▶️'] and reaction.message.id == message.id

        while True:
            try:
                reaction, user = await bot.wait_for('reaction_add', timeout=60.0, check=check)
                if str(reaction.emoji) == '▶️' and current_page < len(embeds) - 1:
                    current_page += 1
                elif str(reaction.emoji) == '◀️' and current_page > 0:
                    current_page -= 1
                await message.edit(embed=embeds[current_page])
                await message.remove_reaction(reaction, user)
            except asyncio.TimeoutError:
                await message.clear_reactions()
                break

# Commande /faits
@bot.tree.command(name='faits', description='Recherche des suspects par faits mentionnés dans les rapports')
@app_commands.describe(faits='Mot-clé décrivant les faits (ex: vol, agression)')
async def faits(interaction: discord.Interaction, faits: str):
    await interaction.response.defer()
    faits_lower = faits.lower().strip()
    matching_results = []

    for suspect, results in bot.data.items():
        for res in results:
            if faits_lower in res['content'].lower():
                matching_results.append((suspect, res))

    if not matching_results:
        embed = discord.Embed(
            title="❌ **Aucun résultat**",
            description=f"Aucun casier judiciaire trouvé mentionnant les faits **{faits}**.",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)
        return

    embeds = []
    for idx, (suspect, res) in enumerate(matching_results, 1):
        embed = discord.Embed(
            title=f"⚖️ **Recherche par faits : {faits}** ({idx}/{len(matching_results)})",
            description=f"**Suspect** : {suspect.title()}",
            color=discord.Color.from_str("#f1c40f")
        )
        embed.add_field(name="📅 **Date**", value=f"<t:{res['timestamp']}:F>", inline=True)
        embed.add_field(name="👤 **Auteur**", value=res['author'], inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=False)  # Espacement
        embed.add_field(name="📝 **Rapport**", value=res['content'][:1000] + ("..." if len(res['content']) > 1000 else ""), inline=False)
        if res['attachments']:
            embed.add_field(name="📎 **Pièces jointes**", value='\n'.join(f"[Lien {i+1}]({url})" for i, url in enumerate(res['attachments'][:3])), inline=False)
        embed.set_footer(text=f"ID: {res['id']} | Source: {res['filename']}")
        embeds.append(embed)

    current_page = 0
    message = await interaction.followup.send(embed=embeds[current_page])

    if len(embeds) > 1:
        await message.add_reaction('◀️')
        await message.add_reaction('▶️')

        def check(reaction, user):
            return user == interaction.user and str(reaction.emoji) in ['◀️', '▶️'] and reaction.message.id == message.id

        while True:
            try:
                reaction, user = await bot.wait_for('reaction_add', timeout=60.0, check=check)
                if str(reaction.emoji) == '▶️' and current_page < len(embeds) - 1:
                    current_page += 1
                elif str(reaction.emoji) == '◀️' and current_page > 0:
                    current_page -= 1
                await message.edit(embed=embeds[current_page])
                await message.remove_reaction(reaction, user)
            except asyncio.TimeoutError:
                await message.clear_reactions()
                break

bot.run(TOKEN)
