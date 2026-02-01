# backend/storage/servers.py
import sqlite3
import os
from typing import Optional, List, Dict
from datetime import datetime

class ServerManager:
    """Handles server storage and caching via sqlite."""
    
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            # Default to user's app data directory
            app_dir = os.path.join(os.path.expanduser("~"), ".dssb_server_browser")
            os.makedirs(app_dir, exist_ok=True)
            db_path = os.path.join(app_dir, "servers.db")
        
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS servers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ip TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    name TEXT,
                    info TEXT,
                    news TEXT,
                    players INTEGER,
                    max_players INTEGER,
                    icon BLOB,
                    website TEXT,
                    source TEXT NOT NULL,  -- 'manual', 'dynamic', 'favorite'
                    trusted BOOLEAN DEFAULT 0,
                    important BOOLEAN DEFAULT 0,
                    last_seen TIMESTAMP,
                    last_queried TIMESTAMP,
                    query_failures INTEGER DEFAULT 0,
                    added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(ip, port)
                )
            """)
            
            # Index for faster lookups
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_ip_port ON servers(ip, port)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_source ON servers(source)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_last_seen ON servers(last_seen)
            """)
            self._ensure_column(conn, "servers", "website", "TEXT")
            conn.commit()

    def _ensure_column(self, conn, table: str, column: str, col_type: str):
        cursor = conn.execute(f"PRAGMA table_info({table})")
        cols = {row[1] for row in cursor.fetchall()}
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")

    def add_server(self, ip: str, port: int, source: str = "manual",
                   trusted: bool = False, important: bool = False,
                   website: Optional[str] = None) -> int:
        """
        Add a server to the database.
        Returns the server ID.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                INSERT INTO servers (ip, port, source, trusted, important, last_seen, website)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ip, port) DO UPDATE SET
                    source = CASE 
                        WHEN excluded.source = 'favorite' THEN 'favorite'
                        WHEN servers.source = 'favorite' THEN 'favorite'
                        ELSE excluded.source
                    END,
                    trusted = excluded.trusted,
                    important = excluded.important,
                    last_seen = excluded.last_seen,
                    website = COALESCE(excluded.website, servers.website)
                RETURNING id
            """, (ip, port, source, trusted, important, datetime.now(), website))
            result = cursor.fetchone()
            conn.commit()
            return result[0]
    
    def update_server_info(self, ip: str, port: int, server_info: Dict):
        """Update server information from dss_query result."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE servers 
                SET name = ?, info = ?, news = ?, 
                    players = ?, max_players = ?, icon = ?,
                    last_queried = ?, query_failures = 0
                WHERE ip = ? AND port = ?
            """, (
                server_info.get("name"),
                server_info.get("info"),
                server_info.get("news"),
                server_info.get("players"),
                server_info.get("max_players"),
                server_info.get("icon"),
                datetime.now(),
                ip,
                port
            ))
            conn.commit()
    
    def mark_query_failure(self, ip: str, port: int):
        """Increment query failure count for a server."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE servers 
                SET query_failures = query_failures + 1,
                    last_queried = ?
                WHERE ip = ? AND port = ?
            """, (datetime.now(), ip, port))
            conn.commit()
    
    def get_server(self, ip: str, port: int) -> Optional[Dict]:
        """Get a single server by IP and port."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM servers WHERE ip = ? AND port = ?
            """, (ip, port))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_all_servers(self, source_filter: Optional[str] = None) -> List[Dict]:
        """
        Get all servers, optionally filtered by source.
        source_filter can be: 'manual', 'dynamic', 'favorite', or None for all
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            if source_filter:
                cursor = conn.execute("""
                    SELECT * FROM servers 
                    WHERE source = ?
                    ORDER BY important DESC, trusted DESC, players DESC
                """, (source_filter,))
            else:
                cursor = conn.execute("""
                    SELECT * FROM servers 
                    ORDER BY important DESC, trusted DESC, players DESC
                """)
            
            return [dict(row) for row in cursor.fetchall()]
    
    def remove_server(self, ip: str, port: int):
        """Remove a server from the database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM servers WHERE ip = ? AND port = ?", (ip, port))
            conn.commit()
    
    def cleanup_failed_servers(self, max_failures: int = 5):
        """
        Remove dynamic servers that have failed too many times.
        Manual and favorite servers are never auto-removed.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                DELETE FROM servers 
                WHERE source = 'dynamic' 
                AND query_failures >= ?
                RETURNING ip, port
            """, (max_failures,))
            removed = cursor.fetchall()
            conn.commit()
            return removed
    
    def set_favorite(self, ip: str, port: int, is_favorite: bool = True):
        """Mark a server as favorite (prevents auto-removal)."""
        with sqlite3.connect(self.db_path) as conn:
            if is_favorite:
                conn.execute("""
                    UPDATE servers SET source = 'favorite' 
                    WHERE ip = ? AND port = ?
                """, (ip, port))
            else:
                # Revert to previous source if unfavoriting
                conn.execute("""
                    UPDATE servers SET source = 'manual' 
                    WHERE ip = ? AND port = ? AND source = 'favorite'
                """, (ip, port))
            conn.commit()
    
    def search_servers(self, query: str) -> List[Dict]:
        """Search servers by name, info, or IP."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            search_pattern = f"%{query}%"
            cursor = conn.execute("""
                SELECT * FROM servers 
                WHERE name LIKE ? OR info LIKE ? OR ip LIKE ?
                ORDER BY important DESC, trusted DESC, players DESC
            """, (search_pattern, search_pattern, search_pattern))
            return [dict(row) for row in cursor.fetchall()]
