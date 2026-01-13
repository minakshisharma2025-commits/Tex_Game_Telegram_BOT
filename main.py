import re
import asyncio
import requests
from typing import Optional, Dict, List
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)

# =============================================================================
# CONFIG
# =============================================================================

BOT_TOKEN = "8530781378:AAET7A6tm7R9C8ToQYBl8-jjtu0L2KaI13E"
OWNER_IDS = [7899148519]  # Apna Telegram ID daal

API_BASE = "https://gamesleech.com/wp-json/wp/v2"

# Categories
CATEGORIES = {
    "repackers": {
        577: {"name": "DODI", "count": 127},
        487: {"name": "ElAmigos", "count": 235},
        33: {"name": "Epic Games", "count": 494},
        1229: {"name": "CS.RIN.RU", "count": 139},
    },
    "years": {
        26: "2024",
        1165: "2025",
        1844: "2026",
    },
    "genres": {
        27: {"name": "Action", "count": 1309},
        29: {"name": "Adventure", "count": 1001},
        31: {"name": "Casual", "count": 213},
    }
}

# =============================================================================
# USER SESSIONS
# =============================================================================

user_sessions: Dict[int, dict] = {}

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def clean_title(title: str) -> str:
    """Clean game title"""
    if not title:
        return "Unknown"
    
    # Remove HTML entities
    title = re.sub(r'&#\d+;', '', title)
    title = re.sub(r'&[a-z]+;', '', title)
    title = title.replace('&#8211;', '-')
    title = title.replace('&amp;', '&')
    
    # Remove Download prefix
    title = re.sub(r'^Download\s+', '', title, flags=re.IGNORECASE)
    
    return title.strip()


def extract_year(title: str, content: str = "") -> str:
    """Extract year from title or content"""
    
    # Try (2024) pattern
    match = re.search(r'\((\d{4})\)', title)
    if match:
        year = match.group(1)
        if 2000 <= int(year) <= 2030:
            return year
    
    # Try standalone year
    match = re.search(r'\b(20\d{2})\b', title)
    if match:
        return match.group(1)
    
    return "N/A"


def extract_size(content: str) -> str:
    """Extract file size from content"""
    
    match = re.search(r'(\d+\.?\d*)\s*(GB|MB|TB)', content, re.IGNORECASE)
    if match:
        return f"{match.group(1)} {match.group(2).upper()}"
    
    return "N/A"


def extract_repacker(title: str) -> str:
    """Extract repacker name from title"""
    
    repackers = ['FitGirl', 'DODI', 'ElAmigos', 'GOG', 'Elamigos', 'CODEX', 'PLAZA', 'Scene']
    
    for repacker in repackers:
        if repacker.lower() in title.lower():
            return repacker
    
    return "Unknown"


def extract_gdrive_links(content: str) -> List[str]:
    """Extract Google Drive links from content"""
    
    links = []
    
    # Pattern 1: drive.google.com/uc?id=xxx
    pattern1 = re.findall(r'https?://drive\.google\.com/uc\?[^"\'<>\s]+', content)
    links.extend(pattern1)
    
    # Pattern 2: drive.google.com/file/d/xxx
    pattern2 = re.findall(r'https?://drive\.google\.com/file/d/[^"\'<>\s/]+', content)
    links.extend(pattern2)
    
    # Clean links
    clean_links = []
    for link in links:
        link = link.replace('&amp;', '&')
        
        # Extract file ID and create direct link
        id_match = re.search(r'[?&]id=([a-zA-Z0-9_-]+)', link)
        if id_match:
            file_id = id_match.group(1)
            clean_links.append(f"https://drive.google.com/uc?export=download&id={file_id}")
            continue
        
        id_match = re.search(r'/d/([a-zA-Z0-9_-]+)', link)
        if id_match:
            file_id = id_match.group(1)
            clean_links.append(f"https://drive.google.com/uc?export=download&id={file_id}")
            continue
        
        clean_links.append(link)
    
    # Remove duplicates
    return list(dict.fromkeys(clean_links))


def extract_password(content: str) -> str:
    """Extract password from content"""
    
    patterns = [
        r'password[:\s]+([^\s<]+)',
        r'Password[:\s]+([^\s<]+)',
        r'PASSWORD[:\s]+([^\s<]+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, content)
        if match:
            return match.group(1)
    
    return "N/A"


def extract_poster(content: str, soup=None) -> str:
    """Extract poster/thumbnail from content"""
    
    # Try img src
    match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', content)
    if match:
        poster = match.group(1)
        if poster.startswith('//'):
            poster = 'https:' + poster
        return poster
    
    return ""


# =============================================================================
# API FUNCTIONS
# =============================================================================

def search_games(query: str, limit: int = 10) -> List[dict]:
    """Search games on GamesLeech"""
    
    try:
        url = f"{API_BASE}/posts"
        params = {
            'search': query,
            'per_page': limit
        }
        
        response = requests.get(url, params=params, timeout=15)
        
        if response.status_code != 200:
            return []
        
        posts = response.json()
        
        results = []
        for post in posts:
            content = post.get('content', {}).get('rendered', '')
            
            results.append({
                'id': post['id'],
                'title': post['title']['rendered'],
                'clean_title': clean_title(post['title']['rendered']),
                'url': post['link'],
                'date': post['date'],
                'content': content
            })
        
        return results
        
    except Exception as e:
        print(f"Search error: {e}")
        return []


def get_game_details(game_id: int) -> Optional[dict]:
    """Get full game details"""
    
    try:
        url = f"{API_BASE}/posts/{game_id}"
        response = requests.get(url, timeout=15)
        
        if response.status_code != 200:
            return None
        
        post = response.json()
        content = post.get('content', {}).get('rendered', '')
        title = post['title']['rendered']
        
        # Extract all info
        gdrive_links = extract_gdrive_links(content)
        
        return {
            'id': post['id'],
            'title': title,
            'clean_title': clean_title(title),
            'url': post['link'],
            'date': post['date'],
            'year': extract_year(title, content),
            'repacker': extract_repacker(title),
            'size': extract_size(content),
            'password': extract_password(content),
            'poster': extract_poster(content),
            'gdrive_links': gdrive_links,
            'parts_count': len(gdrive_links)
        }
        
    except Exception as e:
        print(f"Get game error: {e}")
        return None


def get_latest_games(limit: int = 10) -> List[dict]:
    """Get latest games"""
    
    try:
        url = f"{API_BASE}/posts"
        params = {
            'per_page': limit,
            'orderby': 'date',
            'order': 'desc'
        }
        
        response = requests.get(url, params=params, timeout=15)
        
        if response.status_code != 200:
            return []
        
        posts = response.json()
        
        results = []
        for post in posts:
            content = post.get('content', {}).get('rendered', '')
            title = post['title']['rendered']
            
            results.append({
                'id': post['id'],
                'title': title,
                'clean_title': clean_title(title),
                'repacker': extract_repacker(title),
                'size': extract_size(content),
                'date': post['date'][:10]
            })
        
        return results
        
    except Exception as e:
        print(f"Latest games error: {e}")
        return []


def get_category_games(category_id: int, limit: int = 10) -> List[dict]:
    """Get games by category"""
    
    try:
        url = f"{API_BASE}/posts"
        params = {
            'categories': category_id,
            'per_page': limit,
            'orderby': 'date',
            'order': 'desc'
        }
        
        response = requests.get(url, params=params, timeout=15)
        
        if response.status_code != 200:
            return []
        
        posts = response.json()
        
        results = []
        for post in posts:
            content = post.get('content', {}).get('rendered', '')
            title = post['title']['rendered']
            
            results.append({
                'id': post['id'],
                'title': title,
                'clean_title': clean_title(title),
                'repacker': extract_repacker(title),
                'size': extract_size(content)
            })
        
        return results
        
    except Exception as e:
        print(f"Category games error: {e}")
        return []


# =============================================================================
# BOT HANDLERS
# =============================================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    
    user = update.effective_user
    user_id = user.id
    
    # Clear session
    user_sessions.pop(user_id, None)
    
    welcome_text = f"""🎮 Welcome to GamesLeech Bot!

👋 Hello {user.first_name}!

🎯 I can help you download PC Games for FREE!

📂 Features:
• Search any game by name
• Browse by Repacker
• Get direct Google Drive links
• Latest games updates

🔍 Simply type any game name to search!

Example: GTA 5, FIFA 24, Cyberpunk"""

    keyboard = [
        [
            InlineKeyboardButton("🆕 Latest Games", callback_data="latest"),
            InlineKeyboardButton("📂 Browse", callback_data="browse")
        ],
        [
            InlineKeyboardButton("❓ Help", callback_data="help")
        ]
    ]
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    
    help_text = """❓ HOW TO USE

1️⃣ Search
   Type any game name
   Example: Red Dead Redemption 2

2️⃣ Select
   Type the number from results
   Example: 1

3️⃣ Download
   Click Yes to get download links
   All Google Drive parts will be shown

💡 TIPS
• Be specific with game names
• Include year for better results
• Use repacker name if known

🔑 PASSWORDS
Most games password: www.gamesleech.com

📥 DOWNLOAD
• Use IDM or JDownloader
• Download all parts
• Extract Part 1 only"""

    await update.message.reply_text(help_text)


async def search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle game search"""
    
    query = update.message.text.strip()
    user_id = update.effective_user.id
    
    # Check if number (selection)
    if query.isdigit():
        await number_handler(update, context)
        return
    
    # Ignore short queries
    if len(query) < 2:
        await update.message.reply_text("❌ Too short! Type at least 2 characters.")
        return
    
    # Send searching message
    msg = await update.message.reply_text(f"🔍 Searching: {query}...")
    
    # Search
    results = search_games(query, limit=8)
    
    if not results:
        await msg.edit_text(f"❌ No results for: {query}\n\nTry another name!")
        return
    
    # Save results to session
    user_sessions[user_id] = {
        "results": results,
        "query": query,
        "state": "select"
    }
    
    # Build results text
    text = f"""🔍 SEARCH RESULTS

🔎 Query: {query}
📊 Found: {len(results)} results

"""
    
    for i, r in enumerate(results, 1):
        title = r['clean_title'][:50]
        text += f"🎮 {i}. {title}\n\n"
    
    text += f"👇 Type number 1-{len(results)} to select:"
    
    await msg.edit_text(text)


async def number_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle number selection"""
    
    text = update.message.text.strip()
    user_id = update.effective_user.id
    
    if not text.isdigit():
        return
    
    num = int(text)
    
    if user_id not in user_sessions:
        await update.message.reply_text("❌ No active search!\n\nType a game name to search.")
        return
    
    session = user_sessions[user_id]
    
    if "results" not in session:
        await update.message.reply_text("❌ No results found!\n\nType a game name to search.")
        return
    
    results = session["results"]
    
    if num < 1 or num > len(results):
        await update.message.reply_text(f"❌ Invalid! Type 1-{len(results)}")
        return
    
    selected = results[num - 1]
    
    # Show game info
    await show_game_info(update, context, selected['id'])


async def show_game_info(update: Update, context: ContextTypes.DEFAULT_TYPE, game_id: int):
    """Show game info with poster"""
    
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Send loading message
    msg = await update.message.reply_text("⏳ Loading game details...")
    
    # Get game details
    game = get_game_details(game_id)
    
    if not game:
        await msg.edit_text("❌ Failed to load game! Please try again.")
        return
    
    # Save to session
    user_sessions[user_id] = {
        "game": game,
        "state": "confirm"
    }
    
    # Build caption
    caption = f"""🎮 {game['clean_title']}

📊 Game Info:
📅 Year: {game['year']}
🏷️ Repacker: {game['repacker']}
💾 Size: {game['size']}
📦 Parts: {game['parts_count']} files
🔗 Source: Google Drive

👇 Click to continue:"""

    keyboard = [
        [InlineKeyboardButton("✅ Yes, Download", callback_data="confirm_download")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ]
    
    # Delete loading message
    await msg.delete()
    
    # Send with poster if available
    if game['poster']:
        try:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=game['poster'],
                caption=caption,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        except:
            pass
    
    # Send without poster
    await context.bot.send_message(
        chat_id=chat_id,
        text=caption,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_download_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show download links"""
    
    query = update.callback_query
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    
    if user_id not in user_sessions or "game" not in user_sessions[user_id]:
        await query.answer("❌ Session expired! Search again.", show_alert=True)
        return
    
    game = user_sessions[user_id]["game"]
    
    # Delete previous message
    try:
        await query.message.delete()
    except:
        pass
    
    # Send processing message
    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=f"⏳ Fetching download links...\n\n🎮 {game['clean_title']}"
    )
    
    await asyncio.sleep(1)
    
    await msg.edit_text(f"📥 Preparing Google Drive links...\n\n🎮 {game['clean_title']}")
    
    await asyncio.sleep(1)
    
    # Delete processing message
    await msg.delete()
    
    # Check if links available
    if not game['gdrive_links']:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"""❌ No download links found!

🎮 {game['clean_title']}

Try visiting the website directly:
{game['url']}"""
        )
        return
    
    # Build final message
    caption = f"""✅ DOWNLOAD READY!

🎮 {game['clean_title']}

📊 Details:
📅 Year: {game['year']}
🏷️ Repacker: {game['repacker']}
💾 Size: {game['size']}
📦 Parts: {game['parts_count']} files

🔑 Password: {game['password']}

📥 Download Links:"""

    # Create buttons for each part
    keyboard = []
    
    for i, link in enumerate(game['gdrive_links'], 1):
        keyboard.append([
            InlineKeyboardButton(f"📥 Part {i} - Google Drive", url=link)
        ])
    
    # Add footer text
    footer = f"""

🎉 Enjoy your game!

💡 Tips:
• Download all parts
• Extract Part 1 only
• Use WinRAR or 7-Zip

👇 Type another game name to search:"""

    # Send with poster if available
    if game['poster']:
        try:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=game['poster'],
                caption=caption + footer,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            user_sessions.pop(user_id, None)
            return
        except:
            pass
    
    # Send without poster
    await context.bot.send_message(
        chat_id=chat_id,
        text=caption + footer,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    # Clear session
    user_sessions.pop(user_id, None)


async def show_latest_games(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show latest games"""
    
    query = update.callback_query
    user_id = query.from_user.id
    
    await query.answer()
    
    # Get latest games
    games = get_latest_games(limit=10)
    
    if not games:
        await query.edit_message_text("❌ Failed to load latest games!")
        return
    
    # Save to session
    user_sessions[user_id] = {
        "results": games,
        "state": "select"
    }
    
    # Build text
    text = """🆕 LATEST GAMES

"""
    
    for i, game in enumerate(games, 1):
        title = game['clean_title'][:45]
        text += f"🎮 {i}. {title}\n"
        text += f"   💾 {game['size']} | 🏷️ {game['repacker']}\n\n"
    
    text += "👇 Type number 1-10 to select:"
    
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="back_home")]]
    
    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_browse_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show browse menu"""
    
    query = update.callback_query
    await query.answer()
    
    text = """📂 BROWSE GAMES

Select category:"""

    keyboard = [
        [
            InlineKeyboardButton("🏷️ DODI", callback_data="cat_577"),
            InlineKeyboardButton("🏷️ ElAmigos", callback_data="cat_487")
        ],
        [
            InlineKeyboardButton("🏷️ Epic Games", callback_data="cat_33"),
            InlineKeyboardButton("🏷️ CS.RIN.RU", callback_data="cat_1229")
        ],
        [
            InlineKeyboardButton("📅 2024", callback_data="cat_26"),
            InlineKeyboardButton("📅 2025", callback_data="cat_1165")
        ],
        [InlineKeyboardButton("🔙 Back", callback_data="back_home")]
    ]
    
    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_category_games(update: Update, context: ContextTypes.DEFAULT_TYPE, cat_id: int):
    """Show games by category"""
    
    query = update.callback_query
    user_id = query.from_user.id
    
    await query.answer()
    
    # Get category games
    games = get_category_games(cat_id, limit=10)
    
    if not games:
        await query.edit_message_text("❌ No games found in this category!")
        return
    
    # Save to session
    user_sessions[user_id] = {
        "results": games,
        "state": "select"
    }
    
    # Build text
    text = """📂 CATEGORY GAMES

"""
    
    for i, game in enumerate(games, 1):
        title = game['clean_title'][:45]
        text += f"🎮 {i}. {title}\n"
        text += f"   💾 {game['size']}\n\n"
    
    text += "👇 Type number 1-10 to select:"
    
    keyboard = [
        [InlineKeyboardButton("🔙 Back", callback_data="browse")]
    ]
    
    await query.edit_message_text(
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all button callbacks"""
    
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    
    # Cancel
    if data == "cancel":
        user_sessions.pop(user_id, None)
        await query.answer("Cancelled!")
        try:
            await query.message.delete()
        except:
            pass
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="❌ Cancelled!\n\n👇 Type game name to search:"
        )
        return
    
    # Back to home
    if data == "back_home":
        await query.answer()
        user_sessions.pop(user_id, None)
        
        keyboard = [
            [
                InlineKeyboardButton("🆕 Latest Games", callback_data="latest"),
                InlineKeyboardButton("📂 Browse", callback_data="browse")
            ],
            [
                InlineKeyboardButton("❓ Help", callback_data="help")
            ]
        ]
        
        await query.edit_message_text(
            text="🎮 GamesLeech Bot\n\n🔍 Type any game name to search!\n\nOr use buttons below:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # Help
    if data == "help":
        await query.answer()
        help_text = """❓ HOW TO USE

1️⃣ Type any game name
2️⃣ Select from results (type number)
3️⃣ Click Yes to download
4️⃣ Get Google Drive links

🔑 Password: www.gamesleech.com"""
        
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="back_home")]]
        
        await query.edit_message_text(
            text=help_text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # Latest games
    if data == "latest":
        await show_latest_games(update, context)
        return
    
    # Browse menu
    if data == "browse":
        await show_browse_menu(update, context)
        return
    
    # Category selection
    if data.startswith("cat_"):
        cat_id = int(data.replace("cat_", ""))
        await show_category_games(update, context, cat_id)
        return
    
    # Confirm download
    if data == "confirm_download":
        await query.answer()
        await show_download_links(update, context)
        return


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all text messages"""
    
    text = update.message.text.strip()
    
    if text.isdigit():
        await number_handler(update, context)
    else:
        await search_handler(update, context)


# =============================================================================
# ADMIN COMMANDS
# =============================================================================

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin panel"""
    
    user_id = update.effective_user.id
    
    if user_id not in OWNER_IDS:
        await update.message.reply_text("❌ Not authorized!")
        return
    
    text = f"""🔧 ADMIN PANEL

👤 Owner: {update.effective_user.first_name}
🆔 ID: {user_id}

📊 Active Sessions: {len(user_sessions)}

⚙️ Commands:
/stats - View statistics"""

    await update.message.reply_text(text)


# =============================================================================
# ERROR HANDLER
# =============================================================================

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    
    print(f"Error: {context.error}")
    
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text("❌ Something went wrong! Try again.")
    except:
        pass


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Start the bot"""
    
    print("=" * 50)
    print("🎮 GamesLeech Bot Starting...")
    print("=" * 50)
    
    # Build application
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("admin", admin_command))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(CallbackQueryHandler(callback_handler))
    
    app.add_error_handler(error_handler)
    
    print("✅ Bot is running!")
    print("=" * 50)
    
    # Run
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
