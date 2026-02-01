"""
backend/dssb_manager.py
Integrated manager that combines server storage, credentials, and dynamic loading.
This is the main interface for the UI to interact with the backend.
"""

from backend.storage.servers import ServerManager
from backend.storage.logins import CredentialManager
from backend.network.dynamic_servers import DynamicServerLoader
from backend.dss_query import query_dss
from typing import Optional, List, Dict, Callable

class DSSBManager:
    """
    Main manager class that coordinates all backend functionality.
    Use this as a single point of access for the UI.
    """
    
    def __init__(self, db_path: Optional[str] = None, cred_storage: str = "keyring",
                 cred_password: Optional[str] = None):
        """
        Initialize the DSSB Manager.
        
        Args:
            db_path: Optional custom path for the database
        """
        self.servers = ServerManager(db_path)
        self.credentials = CredentialManager(cred_storage, cred_password)
        self.dynamic = DynamicServerLoader(self.servers, query_dss)
        
        # UI callback holders
        self._ui_callbacks = {}
    
    def set_ui_callback(self, event: str, callback: Callable):
        """
        Set callbacks for UI updates.
        
        Events:
            - server_list_updated: Called when server list changes
            - server_info_updated: Called with (ip, port, info) when server info updates
            - refresh_progress: Called with progress info during refresh
        """
        self._ui_callbacks[event] = callback
        
        # Also set relevant callbacks on dynamic loader
        if event == "refresh_progress":
            self.dynamic.set_callback("on_fetch_complete", callback)
    
    # ========== Server Management ==========
    
    def add_manual_server(
        self,
        ip: str,
        port: int,
        website: Optional[str] = None,
        validate: bool = True,
        timeout: int = 5
    ) -> bool:
        """
        Add a server manually, optionally validating it first.
        
        Returns:
            True if server was added successfully
        """
        try:
            server_info = None
            if validate:
                server_info = query_dss(ip, port, timeout=timeout)

            self.servers.add_server(ip, port, source="manual", website=website)
            if server_info:
                self.servers.update_server_info(ip, port, server_info)
            
            self._trigger_ui_callback("server_list_updated")
            return True
        except Exception as e:
            print(f"Failed to add server {ip}:{port}: {e}")
            return False
    
    def remove_server(self, ip: str, port: int):
        """Remove a server and its credentials."""
        self.servers.remove_server(ip, port)
        self.credentials.delete_credentials(ip, port)
        self._trigger_ui_callback("server_list_updated")
    
    def get_server_list(self, source_filter: Optional[str] = None) -> List[Dict]:
        """
        Get list of all servers.
        
        Args:
            source_filter: Optional filter ('manual', 'dynamic', 'favorite', or None for all)
        """
        return self.servers.get_all_servers(source_filter)

    def get_server(self, ip: str, port: int) -> Optional[Dict]:
        """Get a single server by IP and port."""
        return self.servers.get_server(ip, port)
    
    def search_servers(self, query: str) -> List[Dict]:
        """Search servers by name, info, or IP."""
        return self.servers.search_servers(query)
    
    def toggle_favorite(self, ip: str, port: int) -> bool:
        """
        Toggle favorite status of a server.
        
        Returns:
            New favorite status (True if now favorite)
        """
        server = self.servers.get_server(ip, port)
        if not server:
            return False
        
        is_favorite = server["source"] == "favorite"
        self.servers.set_favorite(ip, port, not is_favorite)
        self._trigger_ui_callback("server_list_updated")
        return not is_favorite
    
    # ========== Credential Management ==========
    
    def save_credentials(self, ip: str, port: int, username: str, password: str) -> bool:
        """Save credentials for a specific server."""
        success = self.credentials.store_credentials(ip, port, username, password)
        if success:
            print(f"Credentials saved for {ip}:{port}")
        return success
    
    def get_credentials(self, ip: str, port: int) -> Optional[Dict[str, str]]:
        """
        Get credentials for a server.
        Falls back to default credentials if server-specific ones don't exist.
        """
        return self.credentials.get_credentials_with_fallback(ip, port)
    
    def save_default_credentials(self, username: str, password: str) -> bool:
        """Save default credentials to use for all servers."""
        return self.credentials.store_default_credentials(username, password)
    
    def get_default_credentials(self) -> Optional[Dict[str, str]]:
        """Get the default credentials."""
        return self.credentials.get_default_credentials()
    
    def clear_server_credentials(self, ip: str, port: int) -> bool:
        """Clear credentials for a specific server."""
        return self.credentials.delete_credentials(ip, port)
    
    # ========== Dynamic Server Management ==========
    
    def refresh_dynamic_servers(self, progress_callback: Optional[Callable] = None, async_mode: bool = True):
        """
        Refresh the dynamic server list from bsb.seeks.men.
        
        Args:
            progress_callback: Optional callback(total, validated, failed)
            async_mode: Run refresh in a background thread if True
        """
        if progress_callback:
            self.dynamic.set_callback("on_fetch_complete", progress_callback)
        
        def run_refresh():
            self.dynamic.refresh_dynamic_servers()
            self._trigger_ui_callback("server_list_updated")

        if async_mode:
            import threading
            threading.Thread(target=run_refresh, daemon=True).start()
        else:
            run_refresh()
    
    def start_auto_refresh(self, interval_minutes: int = 30):
        """Start automatic background refresh of dynamic servers."""
        self.dynamic.start_auto_refresh(interval_minutes)
    
    def stop_auto_refresh(self):
        """Stop automatic background refresh."""
        self.dynamic.stop_auto_refresh()
    
    def cleanup_dead_servers(self, max_failures: int = 5):
        """Remove servers that have failed validation too many times."""
        removed = self.dynamic.cleanup_failed_servers(max_failures)
        if removed:
            self._trigger_ui_callback("server_list_updated")
        return removed
    
    # ========== Server Queries ==========
    
    def query_server(self, ip: str, port: int, timeout: int = 5) -> Optional[Dict]:
        """
        Query a server for current information.
        
        Returns:
            Server info dict or None if query failed
        """
        try:
            info = query_dss(ip, port, timeout)
            
            # Update database
            server = self.servers.get_server(ip, port)
            if server:
                self.servers.update_server_info(ip, port, info)
                self._trigger_ui_callback("server_info_updated", ip, port, info)
            
            return info
        except Exception as e:
            print(f"Failed to query {ip}:{port}: {e}")
            
            # Mark failure if server exists
            server = self.servers.get_server(ip, port)
            if server:
                self.servers.mark_query_failure(ip, port)
            
            return None
    
    def refresh_all_servers(self):
        """Re-query all servers to update their information."""
        success, failed = self.dynamic.revalidate_all_servers()
        self._trigger_ui_callback("server_list_updated")
        return success, failed
    
    # ========== Utility Methods ==========
    
    def _trigger_ui_callback(self, event: str, *args):
        """Trigger a UI callback if set."""
        if event in self._ui_callbacks and self._ui_callbacks[event]:
            try:
                self._ui_callbacks[event](*args)
            except Exception as e:
                print(f"UI callback error for {event}: {e}")
    
    def get_statistics(self) -> Dict:
        """Get statistics about stored servers."""
        all_servers = self.servers.get_all_servers()
        
        return {
            "total": len(all_servers),
            "manual": len([s for s in all_servers if s["source"] == "manual"]),
            "dynamic": len([s for s in all_servers if s["source"] == "dynamic"]),
            "favorites": len([s for s in all_servers if s["source"] == "favorite"]),
            "trusted": len([s for s in all_servers if s["trusted"]]),
            "important": len([s for s in all_servers if s["important"]]),
            "with_credentials": len([s for s in all_servers 
                                   if self.credentials.has_credentials(s["ip"], s["port"])]),
        }
