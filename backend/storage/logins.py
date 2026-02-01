# backend/storage/logins.py
import keyring
import json
import os
import base64
from typing import Optional, Dict, List

try:
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    from cryptography.fernet import Fernet, InvalidToken
except Exception:
    PBKDF2HMAC = None
    hashes = None
    Fernet = None
    InvalidToken = Exception

class FileCredentialStore:
    def __init__(self, path: str, encrypted: bool = False, password: Optional[str] = None):
        self.path = path
        self.encrypted = encrypted
        self.password = password or ""
        self._data = {"default": None, "servers": {}}
        self._load()

    def _derive_key(self, salt: bytes) -> bytes:
        if not PBKDF2HMAC:
            raise RuntimeError("cryptography is required for encrypted credential storage")
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=200_000,
        )
        return base64.urlsafe_b64encode(kdf.derive(self.password.encode("utf-8")))

    def _load(self):
        if not os.path.exists(self.path):
            return
        with open(self.path, "r", encoding="utf-8") as f:
            raw = f.read().strip()
        if not raw:
            return
        if not self.encrypted:
            try:
                data = json.loads(raw)
                if isinstance(data, dict):
                    self._data = data
                return
            except Exception:
                return
        try:
            wrapper = json.loads(raw)
            salt_b64 = wrapper.get("salt", "")
            token = wrapper.get("data", "")
            if not salt_b64 or not token:
                return
            salt = base64.b64decode(salt_b64)
            fernet = Fernet(self._derive_key(salt))
            payload = fernet.decrypt(token.encode("utf-8"))
            data = json.loads(payload.decode("utf-8"))
            if isinstance(data, dict):
                self._data = data
        except InvalidToken:
            raise ValueError("Invalid password for encrypted credentials")
        except Exception:
            return

    def _save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        if not self.encrypted:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2)
            return
        salt = os.urandom(16)
        fernet = Fernet(self._derive_key(salt))
        payload = json.dumps(self._data).encode("utf-8")
        token = fernet.encrypt(payload).decode("utf-8")
        wrapper = {
            "salt": base64.b64encode(salt).decode("ascii"),
            "data": token,
        }
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(wrapper, f)

    def store_credentials(self, ip: str, port: int, username: str, password: str) -> bool:
        key = f"{ip}:{port}"
        self._data.setdefault("servers", {})[key] = {
            "username": username,
            "password": password,
        }
        self._save()
        return True

    def get_credentials(self, ip: str, port: int) -> Optional[Dict[str, str]]:
        key = f"{ip}:{port}"
        return self._data.get("servers", {}).get(key)

    def delete_credentials(self, ip: str, port: int) -> bool:
        key = f"{ip}:{port}"
        if key in self._data.get("servers", {}):
            del self._data["servers"][key]
            self._save()
            return True
        return False

    def store_default_credentials(self, username: str, password: str) -> bool:
        self._data["default"] = {"username": username, "password": password}
        self._save()
        return True

    def get_default_credentials(self) -> Optional[Dict[str, str]]:
        return self._data.get("default")

    def clear_all(self):
        self._data = {"default": None, "servers": {}}
        self._save()


class CredentialManager:
    """
    Handles secure login storage using system keyring.
    Credentials are stored per-server using keyring's secure storage.
    No master password needed - uses OS-level credential storage.
    """
    
    SERVICE_NAME = "DSSBServerBrowser"
    DEFAULT_CREDS_KEY = "default_credentials"
    
    def __init__(self, storage_mode: str = "keyring", password: Optional[str] = None):
        """Initialize the credential manager."""
        self.storage_mode = storage_mode
        self._file_store = None
        if storage_mode in ("plaintext", "encrypted"):
            app_dir = os.path.join(os.path.expanduser("~"), ".dssb_server_browser")
            fname = "credentials.json" if storage_mode == "plaintext" else "credentials.enc"
            path = os.path.join(app_dir, fname)
            encrypted = storage_mode == "encrypted"
            self._file_store = FileCredentialStore(path, encrypted=encrypted, password=password)
        else:
            # Test keyring availability
            try:
                keyring.get_password(self.SERVICE_NAME, "test")
            except Exception as e:
                print(f"Warning: Keyring might not be available: {e}")
    
    def _make_key(self, ip: str, port: int) -> str:
        """Create a unique key for a server."""
        return f"{ip}:{port}"
    
    def store_credentials(self, ip: str, port: int, username: str, password: str):
        """
        Store credentials for a specific server.
        
        Args:
            ip: Server IP address
            port: Server port
            username: Username for this server
            password: Password for this server
        """
        key = self._make_key(ip, port)
        
        # Store as JSON to keep username and password together
        creds = {
            "username": username,
            "password": password
        }
        
        if self._file_store:
            try:
                return self._file_store.store_credentials(ip, port, username, password)
            except Exception as e:
                print(f"Failed to store credentials: {e}")
                return False
        try:
            keyring.set_password(self.SERVICE_NAME, key, json.dumps(creds))
            return True
        except Exception as e:
            print(f"Failed to store credentials: {e}")
            return False
    
    def get_credentials(self, ip: str, port: int) -> Optional[Dict[str, str]]:
        """
        Retrieve credentials for a specific server.
        
        Returns:
            Dict with 'username' and 'password' keys, or None if not found
        """
        key = self._make_key(ip, port)
        
        if self._file_store:
            try:
                return self._file_store.get_credentials(ip, port)
            except Exception as e:
                print(f"Failed to retrieve credentials: {e}")
                return None
        try:
            stored = keyring.get_password(self.SERVICE_NAME, key)
            if stored:
                return json.loads(stored)
            return None
        except Exception as e:
            print(f"Failed to retrieve credentials: {e}")
            return None
    
    def delete_credentials(self, ip: str, port: int) -> bool:
        """
        Delete credentials for a specific server.
        
        Returns:
            True if deletion was successful
        """
        key = self._make_key(ip, port)
        
        if self._file_store:
            try:
                return self._file_store.delete_credentials(ip, port)
            except Exception as e:
                print(f"Failed to delete credentials: {e}")
                return False
        try:
            keyring.delete_password(self.SERVICE_NAME, key)
            return True
        except keyring.errors.PasswordDeleteError:
            # Credentials didn't exist
            return False
        except Exception as e:
            print(f"Failed to delete credentials: {e}")
            return False
    
    def has_credentials(self, ip: str, port: int) -> bool:
        """Check if credentials exist for a server."""
        return self.get_credentials(ip, port) is not None
    
    def store_default_credentials(self, username: str, password: str):
        """
        Store default credentials to use for servers without specific logins.
        
        Args:
            username: Default username
            password: Default password
        """
        creds = {
            "username": username,
            "password": password
        }
        
        if self._file_store:
            try:
                return self._file_store.store_default_credentials(username, password)
            except Exception as e:
                print(f"Failed to store default credentials: {e}")
                return False
        try:
            keyring.set_password(self.SERVICE_NAME, self.DEFAULT_CREDS_KEY, json.dumps(creds))
            return True
        except Exception as e:
            print(f"Failed to store default credentials: {e}")
            return False
    
    def get_default_credentials(self) -> Optional[Dict[str, str]]:
        """
        Get default credentials.
        
        Returns:
            Dict with 'username' and 'password' keys, or None if not set
        """
        if self._file_store:
            try:
                return self._file_store.get_default_credentials()
            except Exception as e:
                print(f"Failed to retrieve default credentials: {e}")
                return None
        try:
            stored = keyring.get_password(self.SERVICE_NAME, self.DEFAULT_CREDS_KEY)
            if stored:
                return json.loads(stored)
            return None
        except Exception as e:
            print(f"Failed to retrieve default credentials: {e}")
            return None
    
    def get_credentials_with_fallback(self, ip: str, port: int) -> Optional[Dict[str, str]]:
        """
        Get credentials for a server, falling back to default if not found.
        
        Returns:
            Dict with 'username' and 'password' keys, or None if neither exist
        """
        # Try server-specific credentials first
        creds = self.get_credentials(ip, port)
        if creds:
            return creds
        
        # Fall back to default credentials
        return self.get_default_credentials()
    
    def list_servers_with_credentials(self) -> List[str]:
        """
        List all servers that have stored credentials.
        Note: This is limited by keyring's capabilities and may not work on all systems.
        
        Returns:
            List of server keys in "ip:port" format
        """
        # Unfortunately, keyring doesn't provide a standard way to list all keys
        # This would need to be tracked separately in the server database
        # For now, return empty list - servers.py should track this
        return []
    
    def clear_all_credentials(self):
        """
        Clear all stored credentials including defaults.
        WARNING: This cannot be undone!
        """
        if self._file_store:
            try:
                self._file_store.clear_all()
            except Exception:
                pass
            return

        # Delete default credentials
        try:
            keyring.delete_password(self.SERVICE_NAME, self.DEFAULT_CREDS_KEY)
        except Exception:
            pass
        
        # Note: We can't enumerate all stored passwords in keyring
        # The caller should use the server list from servers.py to clear individual ones
        print("Default credentials cleared. Use delete_credentials() for server-specific ones.")
