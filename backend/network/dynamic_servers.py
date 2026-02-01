# backend/network/dynamic_servers.py
import requests
import threading
import time
import json
import os
from typing import List, Dict, Callable, Optional

class DynamicServerLoader:
    """
    Handles loading dynamic servers from bsb.seeks.men/list
    and validating them with dss_query.
    """
    
    DEFAULT_API_URL = "https://bsb.seeks.men/list"
    
    def __init__(self, server_manager, query_function):
        """
        Args:
            server_manager: Instance of ServerManager
            query_function: Function to query servers (dss_query.query_dss)
        """
        self.server_manager = server_manager
        self.query_function = query_function
        self._refresh_thread = None
        self._stop_refresh = False
        self._callbacks = {
            "on_fetch_start": None,
            "on_fetch_complete": None,
            "on_server_validated": None,
            "on_server_failed": None,
            "on_error": None,
        }
    
    def set_callback(self, event: str, callback: Callable):
        """
        Set a callback for events.
        
        Events:
            - on_fetch_start: Called when starting to fetch server list
            - on_fetch_complete: Called with (total_servers, new_servers, failed_servers)
            - on_server_validated: Called with (ip, port, server_info)
            - on_server_failed: Called with (ip, port, error)
            - on_error: Called with (error_message)
        """
        if event in self._callbacks:
            self._callbacks[event] = callback
    
    def _trigger_callback(self, event: str, *args):
        """Trigger a callback if it's set."""
        if self._callbacks.get(event):
            try:
                self._callbacks[event](*args)
            except Exception as e:
                print(f"Callback error for {event}: {e}")
    
    def fetch_server_list(self, timeout: int = 5) -> List[Dict]:
        """
        Fetch the server list from the API.
        
        Returns:
            List of server dictionaries with keys: ip, port, trusted, important
        """
        try:
            url = self._get_api_url()
            print(f"Fetching from {url}...")
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            print(f"Fetched {len(data)} servers from API")
            return data
        except requests.RequestException as e:
            error_msg = f"Failed to fetch server list: {e}"
            print(f"ERROR: {error_msg}")
            self._trigger_callback("on_error", error_msg)
            return []

    def _get_api_url(self) -> str:
        settings = self._load_settings()
        return settings.get("list_url") or self.DEFAULT_API_URL

    def _load_settings(self) -> Dict:
        settings_path = os.path.join(
            os.path.expanduser("~"),
            ".dssb_server_browser",
            "settings.json"
        )
        if not os.path.exists(settings_path):
            return {}
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    
    def validate_and_add_server(self, ip: str, port: int, trusted: bool = False,
                                important: bool = False, website: Optional[str] = None,
                                timeout: int = 3) -> bool:
        """
        Validate a server by querying it, then add to database if successful.
        
        Returns:
            True if server was validated and added, False otherwise
        """
        try:
            # Try to query the server
            server_info = self.query_function(ip, int(port), timeout=timeout)
            
            # Add to database as dynamic server
            server_id = self.server_manager.add_server(
                ip, int(port), 
                source="dynamic",
                trusted=trusted,
                important=important,
                website=website
            )
            
            # Update with query results
            self.server_manager.update_server_info(ip, int(port), server_info)
            
            self._trigger_callback("on_server_validated", ip, port, server_info)
            return True
            
        except Exception as e:
            # Mark as failed if it already exists
            existing = self.server_manager.get_server(ip, int(port))
            if existing:
                self.server_manager.mark_query_failure(ip, int(port))
            
            self._trigger_callback("on_server_failed", ip, port, str(e))
            return False
    
    def refresh_dynamic_servers(self, validation_timeout: int = 3, 
                                max_concurrent: int = 10):
        """
        Fetch server list and validate all servers.
        
        Args:
            validation_timeout: Timeout for each server query
            max_concurrent: Maximum number of concurrent validations
        """
        try:
            print("Starting refresh_dynamic_servers...")
            self._trigger_callback("on_fetch_start")
            
            # Fetch the list
            servers = self.fetch_server_list()
            if not servers:
                print("No servers returned from API")
                self._trigger_callback("on_fetch_complete", 0, 0, 0)
                return
            
            total = len(servers)
            new_count = 0
            failed_count = 0
            
            print(f"Validating {total} servers...")
            
            # Process servers in batches for concurrent validation
            from concurrent.futures import ThreadPoolExecutor, as_completed
            
            with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
                futures = {}
                
                for server in servers:
                    future = executor.submit(
                        self.validate_and_add_server,
                        server["ip"],
                        server["port"],
                        server.get("trusted", False),
                        server.get("important", False),
                        server.get("website"),
                        validation_timeout
                    )
                    futures[future] = (server["ip"], server["port"])
                
                for future in as_completed(futures):
                    try:
                        success = future.result()
                        if success:
                            new_count += 1
                        else:
                            failed_count += 1
                    except Exception as e:
                        print(f"Error processing server: {e}")
                        failed_count += 1
            
            print(f"Refresh complete: {new_count} validated, {failed_count} failed")
            self._trigger_callback("on_fetch_complete", total, new_count, failed_count)
            
        except Exception as e:
            print(f"ERROR in refresh_dynamic_servers: {e}")
            import traceback
            traceback.print_exc()
            self._trigger_callback("on_error", str(e))
    
    def start_auto_refresh(self, interval_minutes: int = 30, 
                          validation_timeout: int = 3):
        """
        Start automatic background refresh of dynamic servers.
        
        Args:
            interval_minutes: How often to refresh (in minutes)
            validation_timeout: Timeout for each server query
        """
        if self._refresh_thread and self._refresh_thread.is_alive():
            print("Auto-refresh already running")
            return
        
        self._stop_refresh = False
        
        def refresh_loop():
            while not self._stop_refresh:
                self.refresh_dynamic_servers(validation_timeout=validation_timeout)
                
                # Wait for interval, checking stop flag periodically
                for _ in range(interval_minutes * 60):
                    if self._stop_refresh:
                        break
                    time.sleep(1)
        
        self._refresh_thread = threading.Thread(target=refresh_loop, daemon=True)
        self._refresh_thread.start()
        print(f"Auto-refresh started (every {interval_minutes} minutes)")
    
    def stop_auto_refresh(self):
        """Stop the automatic background refresh."""
        if self._refresh_thread:
            self._stop_refresh = True
            print("Auto-refresh stopped")
    
    def cleanup_failed_servers(self, max_failures: int = 5) -> List[tuple]:
        """
        Remove dynamic servers that have failed too many validation attempts.
        
        Returns:
            List of (ip, port) tuples that were removed
        """
        removed = self.server_manager.cleanup_failed_servers(max_failures)
        print(f"Removed {len(removed)} failed servers")
        return removed
    
    def revalidate_all_servers(self, timeout: int = 3):
        """
        Re-query all existing servers to update their info and check if they're still alive.
        """
        servers = self.server_manager.get_all_servers()
        
        success_count = 0
        failed_count = 0
        
        for server in servers:
            try:
                server_info = self.query_function(
                    server["ip"], 
                    server["port"], 
                    timeout=timeout
                )
                self.server_manager.update_server_info(
                    server["ip"], 
                    server["port"], 
                    server_info
                )
                success_count += 1
            except Exception as e:
                self.server_manager.mark_query_failure(
                    server["ip"], 
                    server["port"]
                )
                failed_count += 1
                print(f"Failed to revalidate {server['ip']}:{server['port']}: {e}")
        
        print(f"Revalidation complete: {success_count} success, {failed_count} failed")
        return success_count, failed_count
