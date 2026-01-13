import re
import json
import asyncio
import requests
import os
import random
import time
import hashlib
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta
from pathlib import Path
import logging
from collections import defaultdict

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

BOT_TOKEN = "8530781378:AAET7A6tm7R9C8ToQYBl8-jjtu0L2KaI13E"
BOT_NAME = "Team Charnos"
BOT_CREATOR = "@akash8911"
OWNER_IDS = [7899148519]  # Apna Telegram ID daal

# API Configuration
API_BASE = "https://gamesleech.com/wp-json/wp/v2"
BACKUP_API_BASE = "https://gamesleech.net/wp-json/wp/v2"  # Backup API

# Database Paths
DB_PATH = "database.json"
LOGS_PATH = "bot_logs.txt"
PREMIUM_DB = "premium_users.json"
SEARCH_HISTORY_DB = "search_history.json"
USER_STATS_DB = "user_stats.json"

# Limits
FREE_USER_LIMIT = 5
PREMIUM_USER_LIMIT = 999999
DAILY_RESET_HOUR = 0  # Reset at midnight

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

# User Agents for rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
]

# =============================================================================
# LOGGING SETUP
# =============================================================================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler(LOGS_PATH),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# =============================================================================
# DATABASE MANAGER CLASS
# =============================================================================

class DatabaseManager:
    """Handle all database operations"""
    
    def __init__(self):
        self.db_path = DB_PATH
        self.premium_path = PREMIUM_DB
        self.history_path = SEARCH_HISTORY_DB
        self.stats_path = USER_STATS_DB
        self._init_databases()
    
    def _init_databases(self):
        """Initialize all databases"""
        # Main database
        if not os.path.exists(self.db_path):
            self._save_json(self.db_path, {
                "users": {},
                "total_searches": 0,
                "bot_started": str(datetime.now()),
                "version": "1.0.0"
            })
        
        # Premium users database
        if not os.path.exists(self.premium_path):
            self._save_json(self.premium_path, {
                "premium_users": [],
                "total_premium": 0
            })
        
        # Search history database
        if not os.path.exists(self.history_path):
            self._save_json(self.history_path, {})
        
        # User stats database
        if not os.path.exists(self.stats_path):
            self._save_json(self.stats_path, {})
    
    def _load_json(self, filepath):
        """Load JSON file"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading {filepath}: {e}")
            return {}
    
    def _save_json(self, filepath, data):
        """Save JSON file"""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"Error saving {filepath}: {e}")
            return False
    
    def add_user(self, user_id: int, user_data: dict):
        """Add or update user in database"""
        db = self._load_json(self.db_path)
        
        user_id_str = str(user_id)
        
        if user_id_str not in db["users"]:
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
                "is_premium": False,
                "is_banned": False,
                "language": "en"
            }
        else:
            db["users"][user_id_str]["last_active"] = str(datetime.now())
        
        self._save_json(self.db_path, db)
        return db["users"][user_id_str]
    
    def get_user(self, user_id: int):
        """Get user from database"""
        db = self._load_json(self.db_path)
        return db.get("users", {}).get(str(user_id))
    
    def update_user_searches(self, user_id: int):
        """Update user search count"""
        db = self._load_json(self.db_path)
        user_id_str = str(user_id)
        
        if user_id_str in db["users"]:
            user = db["users"][user_id_str]
            
            # Check if need to reset daily limit
            last_reset = datetime.fromisoformat(user["last_reset"])
            if last_reset.date() < datetime.now().date():
                user["daily_searches"] = 0
                user["last_reset"] = str(datetime.now().date())
            
            user["daily_searches"] += 1
            user["total_searches"] += 1
            db["total_searches"] = db.get("total_searches", 0) + 1
            
            self._save_json(self.db_path, db)
            return user["daily_searches"]
        
        return 0
    
    def add_search_history(self, user_id: int, query: str, results: int):
        """Add search to user history"""
        history = self._load_json(self.history_path)
        user_id_str = str(user_id)
        
        if user_id_str not in history:
            history[user_id_str] = []
        
        history[user_id_str].append({
            "query": query,
            "results": results,
            "timestamp": str(datetime.now())
        })
        
        # Keep only last 100 searches per user
        if len(history[user_id_str]) > 100:
            history[user_id_str] = history[user_id_str][-100:]
        
        self._save_json(self.history_path, history)
    
    def get_user_history(self, user_id: int):
        """Get user search history"""
        history = self._load_json(self.history_path)
        return history.get(str(user_id), [])
    
    def is_premium_user(self, user_id: int):
        """Check if user is premium"""
        premium_db = self._load_json(self.premium_path)
        return user_id in premium_db.get("premium_users", [])
    
    def add_premium_user(self, user_id: int):
        """Add premium user"""
        premium_db = self._load_json(self.premium_path)
        
        if user_id not in premium_db["premium_users"]:
            premium_db["premium_users"].append(user_id)
            premium_db["total_premium"] = len(premium_db["premium_users"])
            
            # Update main database
            db = self._load_json(self.db_path)
            if str(user_id) in db["users"]:
                db["users"][str(user_id)]["is_premium"] = True
                self._save_json(self.db_path, db)
            
            self._save_json(self.premium_path, premium_db)
            return True
        
        return False
    
    def remove_premium_user(self, user_id: int):
        """Remove premium user"""
        premium_db = self._load_json(self.premium_path)
        
        if user_id in premium_db["premium_users"]:
            premium_db["premium_users"].remove(user_id)
            premium_db["total_premium"] = len(premium_db["premium_users"])
            
            # Update main database
            db = self._load_json(self.db_path)
            if str(user_id) in db["users"]:
                db["users"][str(user_id)]["is_premium"] = False
                self._save_json(self.db_path, db)
            
            self._save_json(self.premium_path, premium_db)
            return True
        
        return False
    
    def get_all_users(self):
        """Get all users"""
        db = self._load_json(self.db_path)
        return db.get("users", {})
    
    def get_stats(self):
        """Get bot statistics"""
        db = self._load_json(self.db_path)
        premium_db = self._load_json(self.premium_path)
        
        stats = {
            "total_users": len(db.get("users", {})),
            "premium_users": premium_db.get("total_premium", 0),
            "free_users": len(db.get("users", {})) - premium_db.get("total_premium", 0),
            "total_searches": db.get("total_searches", 0),
            "bot_started": db.get("bot_started", "Unknown")
        }
        
        return stats
    
    def update_user_stats(self, user_id: int, stat_type: str, value: Any):
        """Update user statistics"""
        stats = self._load_json(self.stats_path)
        user_id_str = str(user_id)
        
        if user_id_str not in stats:
            stats[user_id_str] = {
                "downloads": 0,
                "favorites": [],
                "last_download": None
            }
        
        if stat_type == "download":
            stats[user_id_str]["downloads"] += 1
            stats[user_id_str]["last_download"] = str(datetime.now())
        elif stat_type == "favorite":
            if value not in stats[user_id_str]["favorites"]:
                stats[user_id_str]["favorites"].append(value)
        
        self._save_json(self.stats_path, stats)
    
    def export_database(self):
        """Export complete database"""
        export_data = {
            "main_database": self._load_json(self.db_path),
            "premium_users": self._load_json(self.premium_path),
            "search_history": self._load_json(self.history_path),
            "user_stats": self._load_json(self.stats_path),
            "export_time": str(datetime.now()),
            "bot_name": BOT_NAME,
            "creator": BOT_CREATOR
        }
        
        return export_data

# =============================================================================
# SESSION MANAGER
# =============================================================================

class SessionManager:
    """Manage user sessions"""
    
    def __init__(self):
        self.sessions = {}
        self.cache = {}
    
    def create_session(self, user_id: int):
        """Create new session"""
        self.sessions[user_id] = {
            "created": datetime.now(),
            "last_activity": datetime.now(),
            "state": None,
            "data": {}
        }
    
    def get_session(self, user_id: int):
        """Get user session"""
        if user_id in self.sessions:
            self.sessions[user_id]["last_activity"] = datetime.now()
            return self.sessions[user_id]
        return None
    
    def update_session(self, user_id: int, data: dict):
        """Update session data"""
        if user_id not in self.sessions:
            self.create_session(user_id)
        
        self.sessions[user_id]["data"].update(data)
        self.sessions[user_id]["last_activity"] = datetime.now()
    
    def clear_session(self, user_id: int):
        """Clear user session"""
        if user_id in self.sessions:
            del self.sessions[user_id]
    
    def cleanup_old_sessions(self, max_age_minutes: int = 30):
        """Remove old sessions"""
        current_time = datetime.now()
        to_remove = []
        
        for user_id, session in self.sessions.items():
            age = (current_time - session["last_activity"]).seconds / 60
            if age > max_age_minutes:
                to_remove.append(user_id)
        
        for user_id in to_remove:
            del self.sessions[user_id]
        
        return len(to_remove)

# =============================================================================
# API MANAGER
# =============================================================================

class APIManager:
    """Handle API requests with retry and fallback"""
    
    def __init__(self):
        self.primary_api = API_BASE
        self.backup_api = BACKUP_API_BASE
        self.session = requests.Session()
        self.request_count = 0
        self.last_request_time = None
        
    def _get_headers(self):
        """Get request headers"""
        return {
            'User-Agent': random.choice(USER_AGENTS),
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9',
            'Cache-Control': 'no-cache'
        }
    
    def _make_request(self, url: str, params: dict = None, timeout: int = 15):
        """Make HTTP request with retry"""
        
        # Rate limiting
        if self.last_request_time:
            elapsed = (datetime.now() - self.last_request_time).seconds
            if elapsed < 1:
                time.sleep(1 - elapsed)
        
        self.last_request_time = datetime.now()
        self.request_count += 1
        
        # Try primary API
        try:
            response = self.session.get(
                url,
                params=params,
                headers=self._get_headers(),
                timeout=timeout
            )
            
            if response.status_code == 200:
                return response.json()
                
        except Exception as e:
            logger.error(f"Primary API error: {e}")
        
        # Try backup API
        try:
            backup_url = url.replace(self.primary_api, self.backup_api)
            response = self.session.get(
                backup_url,
                params=params,
                headers=self._get_headers(),
                timeout=timeout
            )
            
            if response.status_code == 200:
                return response.json()
                
        except Exception as e:
            logger.error(f"Backup API error: {e}")
        
        return None
    
    def search_games(self, query: str, limit: int = 10):
        """Search games with fallback"""
        
        # Clean query
        query = query.strip()
        
        # Try exact search
        url = f"{self.primary_api}/posts"
        params = {
            'search': query,
            'per_page': limit
        }
        
        data = self._make_request(url, params)
        
        if data:
            return data
        
        # Try partial search
        if len(query) > 5:
            query_parts = query.split()
            for part in query_parts:
                if len(part) > 3:
                    params['search'] = part
                    data = self._make_request(url, params)
                    if data:
                        return data
        
        # Try without special characters
        clean_query = re.sub(r'[^\w\s]', '', query)
        if clean_query != query:
            params['search'] = clean_query
            data = self._make_request(url, params)
            if data:
                return data
        
        return []
    
    def get_post(self, post_id: int):
        """Get single post"""
        url = f"{self.primary_api}/posts/{post_id}"
        return self._make_request(url)
    
    def get_latest(self, limit: int = 10):
        """Get latest posts"""
        url = f"{self.primary_api}/posts"
        params = {
            'per_page': limit,
            'orderby': 'date',
            'order': 'desc'
        }
        return self._make_request(url, params)
    
    def get_category(self, category_id: int, limit: int = 10):
        """Get posts by category"""
        url = f"{self.primary_api}/posts"
        params = {
            'categories': category_id,
            'per_page': limit,
            'orderby': 'date',
            'order': 'desc'
        }
        return self._make_request(url, params)

# =============================================================================
# INITIALIZE MANAGERS
# =============================================================================

db_manager = DatabaseManager()
session_manager = SessionManager()
api_manager = APIManager()

# =============================================================================
# USER SESSIONS (LEGACY)
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
    
    return "www.gamesleech.com"


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


def validate_user_limits(user_id: int) -> tuple:
    """Check if user can search"""
    
    # Check if premium
    is_premium = db_manager.is_premium_user(user_id)
    
    if is_premium:
        return True, "unlimited"
    
    # Check daily limit for free user
    user = db_manager.get_user(user_id)
    
    if not user:
        return True, FREE_USER_LIMIT
    
    # Reset daily searches if needed
    last_reset = datetime.fromisoformat(user["last_reset"])
    if last_reset.date() < datetime.now().date():
        user["daily_searches"] = 0
        user["last_reset"] = str(datetime.now().date())
    
    remaining = FREE_USER_LIMIT - user.get("daily_searches", 0)
    
    if remaining <= 0:
        return False, 0
    
    return True, remaining


def log_user_action(user_id: int, action: str, details: dict = None):
    """Log user actions"""
    
    log_entry = {
        "user_id": user_id,
        "action": action,
        "timestamp": str(datetime.now()),
        "details": details or {}
    }
    
    logger.info(f"User {user_id}: {action}")

# =============================================================================
# SEARCH FUNCTIONS
# =============================================================================

def search_games(query: str, limit: int = 10) -> List[dict]:
    """Search games on GamesLeech"""
    
    try:
        # Use API manager
        posts = api_manager.search_games(query, limit)
        
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
        
    except Exception as e:
        logger.error(f"Search error: {e}")
        return []


def get_game_details(game_id: int) -> Optional[dict]:
    """Get full game details"""
    
    try:
        post = api_manager.get_post(game_id)
        
        if not post:
            return None
        
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
        logger.error(f"Get game error: {e}")
        return None


def get_latest_games(limit: int = 10) -> List[dict]:
    """Get latest games"""
    
    try:
        posts = api_manager.get_latest(limit)
        
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
        
    except Exception as e:
        logger.error(f"Latest games error: {e}")
        return []


def get_category_games(category_id: int, limit: int = 10) -> List[dict]:
    """Get games by category"""
    
    try:
        posts = api_manager.get_category(category_id, limit)
        
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
        
    except Exception as e:
        logger.error(f"Category games error: {e}")
        return []

# =============================================================================
# BOT HANDLERS
# =============================================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    
    user = update.effective_user
    user_id = user.id
    
    # Log user
    log_user_action(user_id, "start_command")
    
    # Add user to database
    user_data = {
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name
    }
    
    db_user = db_manager.add_user(user_id, user_data)
    
    # Clear session
    user_sessions.pop(user_id, None)
    session_manager.clear_session(user_id)
    
    # Check if premium
    is_premium = db_manager.is_premium_user(user_id)
    
    # Check limits
    can_search, remaining = validate_user_limits(user_id)
    
    status_text = ""
    if is_premium:
        status_text = "\n🌟 Status: PREMIUM USER\n♾️ Unlimited searches"
    else:
        if remaining > 0:
            status_text = f"\n⭐ Status: FREE USER\n🔍 Searches remaining today: {remaining}/{FREE_USER_LIMIT}"
        else:
            status_text = f"\n⭐ Status: FREE USER\n❌ Daily limit reached! Reset at midnight."
    
    welcome_text = f"""🎮 Welcome to {BOT_NAME}!

👋 Hello {user.first_name}!

🎯 I can help you download PC Games for FREE!
{status_text}

📂 Features:
• Search any game by name
• Browse by Repacker
• Get direct Google Drive links
• Latest games updates

🔍 Simply type any game name to search!

Example: GTA 5, FIFA 24, Cyberpunk

Made By {BOT_CREATOR}"""

    keyboard = [
        [
            InlineKeyboardButton("🆕 Latest Games", callback_data="latest"),
            InlineKeyboardButton("📂 Browse", callback_data="browse")
        ],
        [
            InlineKeyboardButton("📊 My Stats", callback_data="my_stats"),
            InlineKeyboardButton("❓ Help", callback_data="help")
        ]
    ]
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    
    user_id = update.effective_user.id
    log_user_action(user_id, "help_command")
    
    is_premium = db_manager.is_premium_user(user_id)
    
    status = "🌟 PREMIUM" if is_premium else "⭐ FREE"
    
    help_text = f"""❓ HOW TO USE {BOT_NAME}

Status: {status}

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
Default: www.gamesleech.com

📥 DOWNLOAD
• Use IDM or JDownloader
• Download all parts
• Extract Part 1 only

Made By {BOT_CREATOR}"""

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
    
    # Check user limits
    can_search, remaining = validate_user_limits(user_id)
    
    if not can_search:
        await update.message.reply_text(
            f"❌ Daily limit reached!\n\n"
            f"You have used all {FREE_USER_LIMIT} searches today.\n"
            f"Reset at midnight OR upgrade to Premium for unlimited searches.\n\n"
            f"Contact admin: {BOT_CREATOR}"
        )
        return
    
    # Log search
    log_user_action(user_id, "search", {"query": query})
    
    # Update search count
    db_manager.update_user_searches(user_id)
    
    # Send searching message
    msg = await update.message.reply_text(f"🔍 Searching: {query}...")
    
    # Search
    results = search_games(query, limit=8)
    
    # Add to history
    db_manager.add_search_history(user_id, query, len(results))
    
    if not results:
        await msg.edit_text(
            f"❌ No results for: {query}\n\n"
            f"Tips:\n"
            f"• Check spelling\n"
            f"• Try shorter keywords\n"
            f"• Remove special characters\n"
            f"• Try game series name only"
        )
        return
    
    # Save results to session
    user_sessions[user_id] = {
        "results": results,
        "query": query,
        "state": "select"
    }
    
    session_manager.update_session(user_id, {
        "results": results,
        "query": query,
        "state": "select"
    })
    
    # Build results text
    limit_text = ""
    if remaining != "unlimited":
        limit_text = f"\n🔍 Searches remaining: {remaining - 1}/{FREE_USER_LIMIT}"
    
    text = f"""🔍 SEARCH RESULTS

🔎 Query: {query}
📊 Found: {len(results)} results{limit_text}

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
    
    # Log selection
    log_user_action(user_id, "select_game", {"game_id": selected['id']})
    
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
    
    session_manager.update_session(user_id, {
        "game": game,
        "state": "confirm"
    })
    
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
    
    # Log download
    log_user_action(user_id, "download", {"game_id": game['id'], "title": game['clean_title']})
    
    # Update stats
    db_manager.update_user_stats(user_id, "download", 1)
    
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
    is_premium = db_manager.is_premium_user(user_id)
    status_text = "🌟 Premium User" if is_premium else "⭐ Free User"
    
    footer = f"""

🎉 Enjoy your game!
Status: {status_text}

💡 Tips:
• Download all parts
• Extract Part 1 only
• Use WinRAR or 7-Zip

Bot: {BOT_NAME}
Made By {BOT_CREATOR}

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
    
    # Check limits
    can_search, remaining = validate_user_limits(user_id)
    
    if not can_search:
        await query.answer(
            "❌ Daily limit reached! Upgrade to Premium.",
            show_alert=True
        )
        return
    
    # Log action
    log_user_action(user_id, "view_latest")
    
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
    
    # Check limits
    can_search, remaining = validate_user_limits(user_id)
    
    if not can_search:
        await query.answer(
            "❌ Daily limit reached! Upgrade to Premium.",
            show_alert=True
        )
        return
    
    # Log action
    log_user_action(user_id, "browse_category", {"category": cat_id})
    
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


async def show_user_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user statistics"""
    
    query = update.callback_query
    user_id = query.from_user.id
    
    await query.answer()
    
    # Get user data
    user = db_manager.get_user(user_id)
    history = db_manager.get_user_history(user_id)
    is_premium = db_manager.is_premium_user(user_id)
    
    if not user:
        await query.edit_message_text("❌ User not found!")
        return
    
    # Calculate stats
    total_searches = user.get("total_searches", 0)
    daily_searches = user.get("daily_searches", 0)
    joined = user.get("joined", "Unknown")
    
    # Recent searches
    recent_searches = ""
    if history:
        recent = history[-5:][::-1]  # Last 5 searches
        for search in recent:
            recent_searches += f"• {search['query']}\n"
    else:
        recent_searches = "No searches yet"
    
    status_emoji = "🌟" if is_premium else "⭐"
    status = "PREMIUM USER" if is_premium else "FREE USER"
    
    text = f"""📊 YOUR STATISTICS

{status_emoji} Status: {status}
🆔 User ID: {user_id}
📅 Joined: {joined[:10]}

📈 Search Stats:
• Total Searches: {total_searches}
• Today's Searches: {daily_searches}
• Daily Limit: {"Unlimited" if is_premium else f"{FREE_USER_LIMIT}"}

🕐 Recent Searches:
{recent_searches}

Bot: {BOT_NAME}
Made By {BOT_CREATOR}"""

    keyboard = [
        [InlineKeyboardButton("🔙 Back", callback_data="back_home")]
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
        session_manager.clear_session(user_id)
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
        session_manager.clear_session(user_id)
        
        is_premium = db_manager.is_premium_user(user_id)
        status_text = "🌟 Premium User" if is_premium else "⭐ Free User"
        
        keyboard = [
            [
                InlineKeyboardButton("🆕 Latest Games", callback_data="latest"),
                InlineKeyboardButton("📂 Browse", callback_data="browse")
            ],
            [
                InlineKeyboardButton("📊 My Stats", callback_data="my_stats"),
                InlineKeyboardButton("❓ Help", callback_data="help")
            ]
        ]
        
        await query.edit_message_text(
            text=f"""🎮 {BOT_NAME}

Status: {status_text}

🔍 Type any game name to search!

Or use buttons below:

Made By {BOT_CREATOR}""",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # Help
    if data == "help":
        await query.answer()
        
        is_premium = db_manager.is_premium_user(user_id)
        status = "🌟 PREMIUM" if is_premium else "⭐ FREE"
        
        help_text = f"""❓ HOW TO USE

Status: {status}

1️⃣ Type any game name
2️⃣ Select from results (type number)
3️⃣ Click Yes to download
4️⃣ Get Google Drive links

🔑 Password: www.gamesleech.com

Bot: {BOT_NAME}
Made By {BOT_CREATOR}"""
        
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="back_home")]]
        
        await query.edit_message_text(
            text=help_text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # My Stats
    if data == "my_stats":
        await show_user_stats(update, context)
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
    
    # Get stats
    stats = db_manager.get_stats()
    
    text = f"""🔧 ADMIN PANEL

👤 Owner: {update.effective_user.first_name}
🆔 ID: {user_id}
🤖 Bot: {BOT_NAME}

📊 Statistics:
• Total Users: {stats['total_users']}
• Premium Users: {stats['premium_users']}
• Free Users: {stats['free_users']}
• Total Searches: {stats['total_searches']}
• Active Sessions: {len(user_sessions)}

⚙️ Commands:
/json - Export database
/add [user_id] - Add premium user
/remove [user_id] - Remove premium user
/stats - View statistics
/broadcast [message] - Send to all users

Made By {BOT_CREATOR}"""

    await update.message.reply_text(text)


async def json_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Export database as JSON"""
    
    user_id = update.effective_user.id
    
    if user_id not in OWNER_IDS:
        await update.message.reply_text("❌ Not authorized!")
        return
    
    # Export database
    export_data = db_manager.export_database()
    
    # Save to temp file
    filename = f"database_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)
    
    # Send file
    await update.message.reply_document(
        document=open(filename, 'rb'),
        caption=f"""📁 Database Export

Bot: {BOT_NAME}
Time: {export_data['export_time']}
Users: {len(export_data['main_database']['users'])}

Made By {BOT_CREATOR}"""
    )
    
    # Delete temp file
    try:
        os.remove(filename)
    except:
        pass


async def add_premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Add premium user"""
    
    user_id = update.effective_user.id
    
    if user_id not in OWNER_IDS:
        await update.message.reply_text("❌ Not authorized!")
        return
    
    # Check args
    if not context.args:
        await update.message.reply_text("Usage: /add [user_id]")
        return
    
    try:
        target_user_id = int(context.args[0])
    except:
        await update.message.reply_text("❌ Invalid user ID!")
        return
    
    # Add premium
    success = db_manager.add_premium_user(target_user_id)
    
    if success:
        await update.message.reply_text(f"✅ User {target_user_id} is now PREMIUM!")
    else:
        await update.message.reply_text(f"❌ User {target_user_id} is already premium!")


async def remove_premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove premium user"""
    
    user_id = update.effective_user.id
    
    if user_id not in OWNER_IDS:
        await update.message.reply_text("❌ Not authorized!")
        return
    
    # Check args
    if not context.args:
        await update.message.reply_text("Usage: /remove [user_id]")
        return
    
    try:
        target_user_id = int(context.args[0])
    except:
        await update.message.reply_text("❌ Invalid user ID!")
        return
    
    # Remove premium
    success = db_manager.remove_premium_user(target_user_id)
    
    if success:
        await update.message.reply_text(f"✅ Removed premium from user {target_user_id}")
    else:
        await update.message.reply_text(f"❌ User {target_user_id} is not premium!")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View detailed statistics"""
    
    user_id = update.effective_user.id
    
    if user_id not in OWNER_IDS:
        await update.message.reply_text("❌ Not authorized!")
        return
    
    # Get all stats
    stats = db_manager.get_stats()
    all_users = db_manager.get_all_users()
    
    # Calculate active users (last 24h)
    active_24h = 0
    now = datetime.now()
    
    for user_data in all_users.values():
        last_active = datetime.fromisoformat(user_data.get("last_active", "2020-01-01"))
        if (now - last_active).days == 0:
            active_24h += 1
    
    text = f"""📊 DETAILED STATISTICS

🤖 Bot: {BOT_NAME}
👤 Admin: {update.effective_user.first_name}

👥 Users:
• Total: {stats['total_users']}
• Premium: {stats['premium_users']}
• Free: {stats['free_users']}
• Active (24h): {active_24h}

🔍 Searches:
• Total: {stats['total_searches']}
• API Requests: {api_manager.request_count}

⏰ Bot Started: {stats['bot_started'][:19]}

Made By {BOT_CREATOR}"""

    await update.message.reply_text(text)


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast message to all users"""
    
    user_id = update.effective_user.id
    
    if user_id not in OWNER_IDS:
        await update.message.reply_text("❌ Not authorized!")
        return
    
    # Check message
    if not context.args:
        await update.message.reply_text("Usage: /broadcast [message]")
        return
    
    message = ' '.join(context.args)
    
    # Get all users
    all_users = db_manager.get_all_users()
    
    sent = 0
    failed = 0
    
    await update.message.reply_text(f"📢 Broadcasting to {len(all_users)} users...")
    
    for user_id_str in all_users:
        try:
            await context.bot.send_message(
                chat_id=int(user_id_str),
                text=f"📢 ANNOUNCEMENT\n\n{message}\n\n- {BOT_NAME} Team"
            )
            sent += 1
            await asyncio.sleep(0.1)  # Avoid flood
        except:
            failed += 1
    
    await update.message.reply_text(
        f"✅ Broadcast complete!\n\nSent: {sent}\nFailed: {failed}"
    )


# =============================================================================
# ERROR HANDLER
# =============================================================================

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    
    logger.error(f"Error: {context.error}")
    
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text("❌ Something went wrong! Try again.")
    except:
        pass


# =============================================================================
# BACKGROUND TASKS
# =============================================================================

async def cleanup_task(context: ContextTypes.DEFAULT_TYPE):
    """Periodic cleanup task"""
    
    # Clean old sessions
    removed = session_manager.cleanup_old_sessions(30)
    
    if removed > 0:
        logger.info(f"Cleaned {removed} old sessions")


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Start the bot"""
    
    print("=" * 50)
    print(f"🎮 {BOT_NAME} Starting...")
    print(f"Created By: {BOT_CREATOR}")
    print("=" * 50)
    
    # Build application
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
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
    
    # Add jobs
    job_queue = app.job_queue
    job_queue.run_repeating(cleanup_task, interval=1800, first=10)  # Every 30 minutes
    
    print(f"✅ {BOT_NAME} is running!")
    print(f"Made By {BOT_CREATOR}")
    print("=" * 50)
    
    # Run
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
