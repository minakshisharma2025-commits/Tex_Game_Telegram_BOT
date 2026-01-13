import re
import json
import asyncio
import requests
import os
import random
import time
from typing import Optional, Dict, List, Any
from datetime import datetime
import logging

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
# BOT CONFIG
# =============================================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8530781378:AAET7A6tm7R9C8ToQYBl8-jjtu0L2KaI13E")
BOT_NAME = "Team Charnos"
BOT_CREATOR = "@akash8911"
OWNER_IDS = [7899148519]

API_BASE = "https://gamesleech.com/wp-json/wp/v2"

DB_PATH = "database.json"
PREMIUM_DB = "premium_users.json"
SEARCH_HISTORY_DB = "search_history.json"

FREE_USER_LIMIT = 5

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0"
]

# Free Proxies (rotating)
PROXIES = [
    None,  # Direct connection first
]

# =============================================================================
# LOGGING
# =============================================================================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# =============================================================================
# DATABASE MANAGER
# =============================================================================

class DatabaseManager:
    def __init__(self):
        self.db_path = DB_PATH
        self.premium_path = PREMIUM_DB
        self.history_path = SEARCH_HISTORY_DB
        self._init_databases()
    
    def _init_databases(self):
        if not os.path.exists(self.db_path):
            self._save_json(self.db_path, {"users": {}, "total_searches": 0, "bot_started": str(datetime.now())})
        if not os.path.exists(self.premium_path):
            self._save_json(self.premium_path, {"premium_users": [], "total_premium": 0})
        if not os.path.exists(self.history_path):
            self._save_json(self.history_path, {})
    
    def _load_json(self, filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    
    def _save_json(self, filepath, data):
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except:
            return False
    
    def add_user(self, user_id: int, user_data: dict):
        db = self._load_json(self.db_path)
        user_id_str = str(user_id)
        
        if user_id_str not in db.get("users", {}):
            if "users" not in db:
                db["users"] = {}
            db["users"][user_id_str] = {
                "user_id": user_id,
                "username": user_data.get("username", ""),
                "first_name": user_data.get("first_name", ""),
                "last_name": user_data.get("last_name", ""),
                "joined": str(datetime.now()),
                "last_active": str(datetime.now()),
                "total_searches": 0,
                "daily_searches": 0,
                "last_reset": str(datetime.now().date()),
                "is_premium": False
            }
        else:
            db["users"][user_id_str]["last_active"] = str(datetime.now())
        
        self._save_json(self.db_path, db)
        return db["users"][user_id_str]
    
    def get_user(self, user_id: int):
        db = self._load_json(self.db_path)
        return db.get("users", {}).get(str(user_id))
    
    def update_user_searches(self, user_id: int):
        db = self._load_json(self.db_path)
        user_id_str = str(user_id)
        
        if user_id_str in db.get("users", {}):
            user = db["users"][user_id_str]
            try:
                last_reset = datetime.fromisoformat(user["last_reset"])
                if last_reset.date() < datetime.now().date():
                    user["daily_searches"] = 0
                    user["last_reset"] = str(datetime.now().date())
            except:
                user["daily_searches"] = 0
                user["last_reset"] = str(datetime.now().date())
            
            user["daily_searches"] += 1
            user["total_searches"] += 1
            db["total_searches"] = db.get("total_searches", 0) + 1
            self._save_json(self.db_path, db)
            return user["daily_searches"]
        return 0
    
    def add_search_history(self, user_id: int, query: str, results: int):
        history = self._load_json(self.history_path)
        user_id_str = str(user_id)
        
        if user_id_str not in history:
            history[user_id_str] = []
        
        history[user_id_str].append({
            "query": query,
            "results": results,
            "timestamp": str(datetime.now())
        })
        
        if len(history[user_id_str]) > 100:
            history[user_id_str] = history[user_id_str][-100:]
        
        self._save_json(self.history_path, history)
    
    def get_user_history(self, user_id: int):
        history = self._load_json(self.history_path)
        return history.get(str(user_id), [])
    
    def is_premium_user(self, user_id: int):
        premium_db = self._load_json(self.premium_path)
        return user_id in premium_db.get("premium_users", [])
    
    def add_premium_user(self, user_id: int):
        premium_db = self._load_json(self.premium_path)
        if "premium_users" not in premium_db:
            premium_db["premium_users"] = []
        if user_id not in premium_db["premium_users"]:
            premium_db["premium_users"].append(user_id)
            premium_db["total_premium"] = len(premium_db["premium_users"])
            self._save_json(self.premium_path, premium_db)
            return True
        return False
    
    def remove_premium_user(self, user_id: int):
        premium_db = self._load_json(self.premium_path)
        if user_id in premium_db.get("premium_users", []):
            premium_db["premium_users"].remove(user_id)
            premium_db["total_premium"] = len(premium_db["premium_users"])
            self._save_json(self.premium_path, premium_db)
            return True
        return False
    
    def get_all_users(self):
        db = self._load_json(self.db_path)
        return db.get("users", {})
    
    def get_stats(self):
        db = self._load_json(self.db_path)
        premium_db = self._load_json(self.premium_path)
        return {
            "total_users": len(db.get("users", {})),
            "premium_users": premium_db.get("total_premium", 0),
            "free_users": len(db.get("users", {})) - premium_db.get("total_premium", 0),
            "total_searches": db.get("total_searches", 0),
            "bot_started": db.get("bot_started", "Unknown")
        }
    
    def export_database(self):
        return {
            "main_database": self._load_json(self.db_path),
            "premium_users": self._load_json(self.premium_path),
            "search_history": self._load_json(self.history_path),
            "export_time": str(datetime.now()),
            "bot_name": BOT_NAME,
            "creator": BOT_CREATOR
        }

# =============================================================================
# INIT
# =============================================================================

db_manager = DatabaseManager()
user_sessions: Dict[int, dict] = {}

# =============================================================================
# HELPERS
# =============================================================================

def clean_title(title: str) -> str:
    if not title:
        return "Unknown"
    title = re.sub(r'&#\d+;', '', title)
    title = re.sub(r'&[a-z]+;', '', title)
    title = title.replace('&#8211;', '-')
    title = title.replace('&amp;', '&')
    title = re.sub(r'^Download\s+', '', title, flags=re.IGNORECASE)
    return title.strip()

def extract_year(title: str, content: str = "") -> str:
    match = re.search(r'\((\d{4})\)', title)
    if match:
        year = match.group(1)
        if 2000 <= int(year) <= 2030:
            return year
    match = re.search(r'\b(20\d{2})\b', title)
    if match:
        return match.group(1)
    return "N/A"

def extract_size(content: str) -> str:
    match = re.search(r'(\d+\.?\d*)\s*(GB|MB|TB)', content, re.IGNORECASE)
    if match:
        return f"{match.group(1)} {match.group(2).upper()}"
    return "N/A"

def extract_repacker(title: str) -> str:
    repackers = ['FitGirl', 'DODI', 'ElAmigos', 'GOG', 'Elamigos', 'CODEX', 'PLAZA', 'Scene']
    for repacker in repackers:
        if repacker.lower() in title.lower():
            return repacker
    return "Unknown"

def extract_gdrive_links(content: str) -> List[str]:
    links = []
    pattern1 = re.findall(r'https?://drive\.google\.com/uc\?[^"\'<>\s]+', content)
    links.extend(pattern1)
    pattern2 = re.findall(r'https?://drive\.google\.com/file/d/[^"\'<>\s/]+', content)
    links.extend(pattern2)
    pattern3 = re.findall(r'https?://drive\.google\.com/open\?[^"\'<>\s]+', content)
    links.extend(pattern3)
    
    clean_links = []
    for link in links:
        link = link.replace('&amp;', '&')
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
    
    return list(dict.fromkeys(clean_links))

def extract_password(content: str) -> str:
    patterns = [r'password[:\s]+([^\s<]+)', r'Password[:\s]+([^\s<]+)', r'PASSWORD[:\s]+([^\s<]+)']
    for pattern in patterns:
        match = re.search(pattern, content)
        if match:
            return match.group(1)
    return "www.gamesleech.com"

def extract_poster(content: str) -> str:
    match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', content)
    if match:
        poster = match.group(1)
        if poster.startswith('//'):
            poster = 'https:' + poster
        return poster
    return ""

def validate_user_limits(user_id: int) -> tuple:
    is_premium = db_manager.is_premium_user(user_id)
    if is_premium:
        return True, "unlimited"
    user = db_manager.get_user(user_id)
    if not user:
        return True, FREE_USER_LIMIT
    try:
        last_reset = datetime.fromisoformat(user["last_reset"])
        if last_reset.date() < datetime.now().date():
            return True, FREE_USER_LIMIT
    except:
        return True, FREE_USER_LIMIT
    remaining = FREE_USER_LIMIT - user.get("daily_searches", 0)
    if remaining <= 0:
        return False, 0
    return True, remaining

# =============================================================================
# API FUNCTIONS WITH RETRY
# =============================================================================

def make_api_request(url: str, params: dict = None, timeout: int = 30):
    """Make API request with multiple retries and user agents"""
    
    for attempt in range(5):
        try:
            headers = {
                'User-Agent': random.choice(USER_AGENTS),
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache',
                'Referer': 'https://gamesleech.com/',
                'Origin': 'https://gamesleech.com'
            }
            
            session = requests.Session()
            session.headers.update(headers)
            
            response = session.get(url, params=params, timeout=timeout)
            
            logger.info(f"API Request: {url} | Status: {response.status_code}")
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 403:
                logger.warning(f"403 Forbidden - Attempt {attempt + 1}")
                time.sleep(2)
            elif response.status_code == 429:
                logger.warning(f"429 Rate Limited - Waiting...")
                time.sleep(5)
            else:
                logger.warning(f"Status {response.status_code} - Attempt {attempt + 1}")
                time.sleep(1)
                
        except requests.exceptions.Timeout:
            logger.error(f"Timeout - Attempt {attempt + 1}")
            time.sleep(2)
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection Error - Attempt {attempt + 1}: {e}")
            time.sleep(3)
        except Exception as e:
            logger.error(f"Request Error - Attempt {attempt + 1}: {e}")
            time.sleep(1)
    
    return None

def search_games(query: str, limit: int = 10) -> List[dict]:
    """Search games"""
    url = f"{API_BASE}/posts"
    params = {'search': query, 'per_page': limit}
    
    posts = make_api_request(url, params)
    
    if not posts:
        # Try alternative search
        clean_query = re.sub(r'[^\w\s]', '', query)
        if clean_query != query:
            params['search'] = clean_query
            posts = make_api_request(url, params)
    
    if not posts:
        return []
    
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

def get_game_details(game_id: int) -> Optional[dict]:
    """Get game details"""
    url = f"{API_BASE}/posts/{game_id}"
    post = make_api_request(url)
    
    if not post:
        return None
    
    content = post.get('content', {}).get('rendered', '')
    title = post['title']['rendered']
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

def get_latest_games(limit: int = 10) -> List[dict]:
    """Get latest games"""
    url = f"{API_BASE}/posts"
    params = {'per_page': limit, 'orderby': 'date', 'order': 'desc'}
    
    posts = make_api_request(url, params)
    
    if not posts:
        return []
    
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

def get_category_games(category_id: int, limit: int = 10) -> List[dict]:
    """Get category games"""
    url = f"{API_BASE}/posts"
    params = {'categories': category_id, 'per_page': limit, 'orderby': 'date', 'order': 'desc'}
    
    posts = make_api_request(url, params)
    
    if not posts:
        return []
    
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

# =============================================================================
# BOT HANDLERS
# =============================================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    logger.info(f"User {user_id} started bot")
    
    user_data = {"username": user.username, "first_name": user.first_name, "last_name": user.last_name}
    db_manager.add_user(user_id, user_data)
    user_sessions.pop(user_id, None)
    
    is_premium = db_manager.is_premium_user(user_id)
    can_search, remaining = validate_user_limits(user_id)
    
    if is_premium:
        status_text = "\nStatus: PREMIUM USER\nUnlimited searches"
    else:
        if remaining > 0:
            status_text = f"\nStatus: FREE USER\nSearches remaining: {remaining}/{FREE_USER_LIMIT}"
        else:
            status_text = f"\nStatus: FREE USER\nDaily limit reached!"
    
    welcome_text = f"""Welcome to {BOT_NAME}!

Hello {user.first_name}!

I can help you download PC Games for FREE!
{status_text}

Features:
- Search any game
- Browse by Repacker
- Google Drive links
- Latest games

Type any game name to search!

Example: GTA 5, FIFA 24, Cyberpunk

Made By {BOT_CREATOR}"""

    keyboard = [
        [InlineKeyboardButton("Latest Games", callback_data="latest"), InlineKeyboardButton("Browse", callback_data="browse")],
        [InlineKeyboardButton("My Stats", callback_data="my_stats"), InlineKeyboardButton("Help", callback_data="help")]
    ]
    
    await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard))

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = f"""HOW TO USE {BOT_NAME}

1. Type game name
2. Select number from results
3. Click Yes to download
4. Get Google Drive links

PASSWORD: www.gamesleech.com

Made By {BOT_CREATOR}"""
    await update.message.reply_text(help_text)

async def search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    user_id = update.effective_user.id
    
    if query.isdigit():
        await number_handler(update, context)
        return
    
    if len(query) < 2:
        await update.message.reply_text("Too short! Type at least 2 characters.")
        return
    
    can_search, remaining = validate_user_limits(user_id)
    
    if not can_search:
        await update.message.reply_text(f"Daily limit reached!\n\nUsed {FREE_USER_LIMIT} searches.\nReset at midnight.\n\nContact: {BOT_CREATOR}")
        return
    
    logger.info(f"User {user_id} searching: {query}")
    
    db_manager.update_user_searches(user_id)
    
    msg = await update.message.reply_text(f"Searching: {query}...")
    
    results = search_games(query, limit=8)
    db_manager.add_search_history(user_id, query, len(results))
    
    if not results:
        await msg.edit_text(f"No results for: {query}\n\nTry:\n- Check spelling\n- Shorter keywords\n- Remove special chars")
        return
    
    user_sessions[user_id] = {"results": results, "query": query, "state": "select"}
    
    limit_text = "" if remaining == "unlimited" else f"\nRemaining: {remaining - 1}/{FREE_USER_LIMIT}"
    
    text = f"SEARCH RESULTS\n\nQuery: {query}\nFound: {len(results)}{limit_text}\n\n"
    
    for i, r in enumerate(results, 1):
        title = r['clean_title'][:50]
        text += f"{i}. {title}\n\n"
    
    text += f"Type 1-{len(results)} to select:"
    
    await msg.edit_text(text)

async def number_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.effective_user.id
    
    if not text.isdigit():
        return
    
    num = int(text)
    
    if user_id not in user_sessions:
        await update.message.reply_text("No search active!\n\nType game name to search.")
        return
    
    session = user_sessions[user_id]
    
    if "results" not in session:
        await update.message.reply_text("No results!\n\nType game name to search.")
        return
    
    results = session["results"]
    
    if num < 1 or num > len(results):
        await update.message.reply_text(f"Invalid! Type 1-{len(results)}")
        return
    
    selected = results[num - 1]
    await show_game_info(update, context, selected['id'])

async def show_game_info(update: Update, context: ContextTypes.DEFAULT_TYPE, game_id: int):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    msg = await update.message.reply_text("Loading game...")
    
    game = get_game_details(game_id)
    
    if not game:
        await msg.edit_text("Failed to load! Try again.")
        return
    
    user_sessions[user_id] = {"game": game, "state": "confirm"}
    
    caption = f"""{game['clean_title']}

Year: {game['year']}
Repacker: {game['repacker']}
Size: {game['size']}
Parts: {game['parts_count']} files

Click to continue:"""

    keyboard = [
        [InlineKeyboardButton("Yes Download", callback_data="confirm_download")],
        [InlineKeyboardButton("Cancel", callback_data="cancel")]
    ]
    
    await msg.delete()
    
    if game['poster']:
        try:
            await context.bot.send_photo(chat_id=chat_id, photo=game['poster'], caption=caption, reply_markup=InlineKeyboardMarkup(keyboard))
            return
        except:
            pass
    
    await context.bot.send_message(chat_id=chat_id, text=caption, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_download_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    
    if user_id not in user_sessions or "game" not in user_sessions[user_id]:
        await query.answer("Session expired!", show_alert=True)
        return
    
    game = user_sessions[user_id]["game"]
    
    try:
        await query.message.delete()
    except:
        pass
    
    msg = await context.bot.send_message(chat_id=chat_id, text=f"Getting links...\n\n{game['clean_title']}")
    await asyncio.sleep(1)
    await msg.delete()
    
    if not game['gdrive_links']:
        await context.bot.send_message(chat_id=chat_id, text=f"No links found!\n\n{game['clean_title']}\n\nVisit: {game['url']}")
        return
    
    is_premium = db_manager.is_premium_user(user_id)
    status = "Premium" if is_premium else "Free"
    
    caption = f"""DOWNLOAD READY!

{game['clean_title']}

Year: {game['year']}
Repacker: {game['repacker']}
Size: {game['size']}
Parts: {game['parts_count']}

Password: {game['password']}"""

    keyboard = []
    for i, link in enumerate(game['gdrive_links'], 1):
        keyboard.append([InlineKeyboardButton(f"Part {i} - GDrive", url=link)])
    
    footer = f"""

Status: {status}
Download all parts
Extract Part 1 only

{BOT_NAME} | {BOT_CREATOR}"""

    if game['poster']:
        try:
            await context.bot.send_photo(chat_id=chat_id, photo=game['poster'], caption=caption + footer, reply_markup=InlineKeyboardMarkup(keyboard))
            user_sessions.pop(user_id, None)
            return
        except:
            pass
    
    await context.bot.send_message(chat_id=chat_id, text=caption + footer, reply_markup=InlineKeyboardMarkup(keyboard))
    user_sessions.pop(user_id, None)

async def show_latest_games(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    await query.answer()
    
    can_search, remaining = validate_user_limits(user_id)
    if not can_search:
        await query.answer("Limit reached!", show_alert=True)
        return
    
    games = get_latest_games(limit=10)
    
    if not games:
        await query.edit_message_text("Failed to load!")
        return
    
    user_sessions[user_id] = {"results": games, "state": "select"}
    
    text = "LATEST GAMES\n\n"
    for i, game in enumerate(games, 1):
        title = game['clean_title'][:40]
        text += f"{i}. {title}\n   {game['size']} | {game['repacker']}\n\n"
    
    text += "Type 1-10 to select:"
    
    keyboard = [[InlineKeyboardButton("Back", callback_data="back_home")]]
    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_browse_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    text = "BROWSE GAMES\n\nSelect:"
    
    keyboard = [
        [InlineKeyboardButton("DODI", callback_data="cat_577"), InlineKeyboardButton("ElAmigos", callback_data="cat_487")],
        [InlineKeyboardButton("Epic", callback_data="cat_33"), InlineKeyboardButton("CS.RIN", callback_data="cat_1229")],
        [InlineKeyboardButton("2024", callback_data="cat_26"), InlineKeyboardButton("2025", callback_data="cat_1165")],
        [InlineKeyboardButton("Back", callback_data="back_home")]
    ]
    
    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_category_games(update: Update, context: ContextTypes.DEFAULT_TYPE, cat_id: int):
    query = update.callback_query
    user_id = query.from_user.id
    
    await query.answer()
    
    can_search, remaining = validate_user_limits(user_id)
    if not can_search:
        await query.answer("Limit reached!", show_alert=True)
        return
    
    games = get_category_games(cat_id, limit=10)
    
    if not games:
        await query.edit_message_text("No games!")
        return
    
    user_sessions[user_id] = {"results": games, "state": "select"}
    
    text = "CATEGORY GAMES\n\n"
    for i, game in enumerate(games, 1):
        title = game['clean_title'][:40]
        text += f"{i}. {title}\n   {game['size']}\n\n"
    
    text += "Type 1-10 to select:"
    
    keyboard = [[InlineKeyboardButton("Back", callback_data="browse")]]
    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_user_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    
    await query.answer()
    
    user = db_manager.get_user(user_id)
    history = db_manager.get_user_history(user_id)
    is_premium = db_manager.is_premium_user(user_id)
    
    if not user:
        await query.edit_message_text("User not found!")
        return
    
    total = user.get("total_searches", 0)
    daily = user.get("daily_searches", 0)
    joined = user.get("joined", "Unknown")[:10]
    
    recent = ""
    if history:
        for s in history[-5:][::-1]:
            recent += f"- {s['query']}\n"
    else:
        recent = "None"
    
    status = "PREMIUM" if is_premium else "FREE"
    limit = "Unlimited" if is_premium else str(FREE_USER_LIMIT)
    
    text = f"""YOUR STATS

Status: {status}
ID: {user_id}
Joined: {joined}

Total: {total}
Today: {daily}
Limit: {limit}

Recent:
{recent}

{BOT_NAME} | {BOT_CREATOR}"""

    keyboard = [[InlineKeyboardButton("Back", callback_data="back_home")]]
    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard))

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    
    if data == "cancel":
        user_sessions.pop(user_id, None)
        await query.answer("Cancelled!")
        try:
            await query.message.delete()
        except:
            pass
        await context.bot.send_message(chat_id=query.message.chat_id, text="Cancelled!\n\nType game name:")
        return
    
    if data == "back_home":
        await query.answer()
        user_sessions.pop(user_id, None)
        is_premium = db_manager.is_premium_user(user_id)
        status = "Premium" if is_premium else "Free"
        
        keyboard = [
            [InlineKeyboardButton("Latest", callback_data="latest"), InlineKeyboardButton("Browse", callback_data="browse")],
            [InlineKeyboardButton("Stats", callback_data="my_stats"), InlineKeyboardButton("Help", callback_data="help")]
        ]
        
        await query.edit_message_text(text=f"{BOT_NAME}\n\nStatus: {status}\n\nType game name!\n\n{BOT_CREATOR}", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    if data == "help":
        await query.answer()
        text = f"""HOW TO USE

1. Type game name
2. Type number
3. Click Yes
4. Get links

Pass: www.gamesleech.com

{BOT_CREATOR}"""
        
        keyboard = [[InlineKeyboardButton("Back", callback_data="back_home")]]
        await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    if data == "my_stats":
        await show_user_stats(update, context)
        return
    
    if data == "latest":
        await show_latest_games(update, context)
        return
    
    if data == "browse":
        await show_browse_menu(update, context)
        return
    
    if data.startswith("cat_"):
        cat_id = int(data.replace("cat_", ""))
        await show_category_games(update, context, cat_id)
        return
    
    if data == "confirm_download":
        await query.answer()
        await show_download_links(update, context)
        return

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.isdigit():
        await number_handler(update, context)
    else:
        await search_handler(update, context)

# =============================================================================
# ADMIN COMMANDS
# =============================================================================

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in OWNER_IDS:
        await update.message.reply_text("Not authorized!")
        return
    
    stats = db_manager.get_stats()
    
    text = f"""ADMIN PANEL

Owner: {update.effective_user.first_name}
ID: {user_id}
Bot: {BOT_NAME}

Users: {stats['total_users']}
Premium: {stats['premium_users']}
Free: {stats['free_users']}
Searches: {stats['total_searches']}
Sessions: {len(user_sessions)}

Commands:
/json - Export DB
/add [id] - Add premium
/remove [id] - Remove premium
/stats - Statistics
/broadcast [msg] - Broadcast

{BOT_CREATOR}"""

    await update.message.reply_text(text)

async def json_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in OWNER_IDS:
        await update.message.reply_text("Not authorized!")
        return
    
    export = db_manager.export_database()
    filename = f"db_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(export, f, ensure_ascii=False, indent=2)
    
    await update.message.reply_document(document=open(filename, 'rb'), caption=f"Database\n\nUsers: {len(export['main_database'].get('users', {}))}\n\n{BOT_CREATOR}")
    
    try:
        os.remove(filename)
    except:
        pass

async def add_premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in OWNER_IDS:
        await update.message.reply_text("Not authorized!")
        return
    
    if not context.args:
        await update.message.reply_text("/add [user_id]")
        return
    
    try:
        target = int(context.args[0])
    except:
        await update.message.reply_text("Invalid ID!")
        return
    
    if db_manager.add_premium_user(target):
        await update.message.reply_text(f"User {target} is PREMIUM!")
    else:
        await update.message.reply_text(f"Already premium!")

async def remove_premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in OWNER_IDS:
        await update.message.reply_text("Not authorized!")
        return
    
    if not context.args:
        await update.message.reply_text("/remove [user_id]")
        return
    
    try:
        target = int(context.args[0])
    except:
        await update.message.reply_text("Invalid ID!")
        return
    
    if db_manager.remove_premium_user(target):
        await update.message.reply_text(f"Removed premium from {target}")
    else:
        await update.message.reply_text(f"Not premium!")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in OWNER_IDS:
        await update.message.reply_text("Not authorized!")
        return
    
    stats = db_manager.get_stats()
    all_users = db_manager.get_all_users()
    
    active = 0
    now = datetime.now()
    for u in all_users.values():
        try:
            last = datetime.fromisoformat(u.get("last_active", "2020-01-01"))
            if (now - last).days == 0:
                active += 1
        except:
            pass
    
    text = f"""STATISTICS

Bot: {BOT_NAME}

Total: {stats['total_users']}
Premium: {stats['premium_users']}
Free: {stats['free_users']}
Active 24h: {active}

Searches: {stats['total_searches']}

Started: {stats['bot_started'][:19]}

{BOT_CREATOR}"""

    await update.message.reply_text(text)

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in OWNER_IDS:
        await update.message.reply_text("Not authorized!")
        return
    
    if not context.args:
        await update.message.reply_text("/broadcast [message]")
        return
    
    msg = ' '.join(context.args)
    users = db_manager.get_all_users()
    
    sent = 0
    fail = 0
    
    await update.message.reply_text(f"Broadcasting to {len(users)}...")
    
    for uid in users:
        try:
            await context.bot.send_message(chat_id=int(uid), text=f"ANNOUNCEMENT\n\n{msg}\n\n{BOT_NAME}")
            sent += 1
            await asyncio.sleep(0.1)
        except:
            fail += 1
    
    await update.message.reply_text(f"Done!\nSent: {sent}\nFailed: {fail}")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Error: {context.error}")
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text("Error! Try again.")
    except:
        pass

# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 50)
    print(f"{BOT_NAME} Starting...")
    print(f"Created By: {BOT_CREATOR}")
    print("=" * 50)
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("json", json_command))
    app.add_handler(CommandHandler("add", add_premium_command))
    app.add_handler(CommandHandler("remove", remove_premium_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(CallbackQueryHandler(callback_handler))
    
    app.add_error_handler(error_handler)
    
    print(f"{BOT_NAME} is running!")
    print(f"Made By {BOT_CREATOR}")
    print("=" * 50)
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
