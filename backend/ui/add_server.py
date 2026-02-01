# add server dialog code.
import os
from backend.ui_manager import HTMLWindow
from PyQt6.QtCore import Qt

def create_add_server_dialog(dssb_manager, on_server_added=None):
    """
    Create the add server dialog window.
    
    Args:
        dssb_manager: Instance of DSSBManager
        on_server_added: Optional callback function to call when server is added
    
    Returns:
        HTMLWindow instance
    """
    # Resolve paths
    current_dir = os.path.dirname(os.path.abspath(__file__))  # backend/ui
    backend_dir = os.path.dirname(current_dir)                 # backend
    project_root = os.path.dirname(backend_dir)                # project root
    html_path = os.path.join(project_root, "frontend", "add_server.html")
    
    if not os.path.exists(html_path):
        raise FileNotFoundError(f"HTML file not found: {html_path}")
    
    # Create dialog window
    callbacks = {
        "close": lambda _: dialog.close(),
        "save": lambda data: handle_save(dssb_manager, dialog, data, on_server_added),
    }

    dialog = HTMLWindow(
        html_path=html_path,
        size=(400, 300),
        enable_drag=False,
        callbacks=callbacks
    )

    callbacks["dragMove"] = dialog._handle_drag_move
    

    dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
    dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
    dialog.activateWindow()
    return dialog


def handle_save(dssb_manager, dialog, data, on_server_added):
    """
    Handle saving the new server.
    
    Args:
        dssb_manager: DSSBManager instance
        dialog: The dialog window
        data: JSON string with ip, port, website
        on_server_added: Callback to execute after server is added
    """
    import json
    
    try:
        server_data = json.loads(data)
        ip = server_data.get("ip", "").strip()
        port_str = server_data.get("port", "").strip()
        website = server_data.get("website", "").strip()
        
        # Validate IP
        if not ip:
            show_error(dialog, "IP address is required")
            return
        
        # Default port to 17017 if not provided
        if not port_str:
            port = 17017
        else:
            try:
                port = int(port_str)
                if port < 1 or port > 65535:
                    show_error(dialog, "Port must be between 1 and 65535")
                    return
            except ValueError:
                show_error(dialog, "Port must be a valid number")
                return
        
        # Default website to IP if not provided
        if not website:
            website = f"http://{ip}"
        
        print(f"Adding server: {ip}:{port} (website: {website})")
        
        # Add server to database
        success = dssb_manager.add_manual_server(ip, port, website=website)
        
        if success:
            print(f"Server {ip}:{port} added successfully")
            
            # Call the callback if provided
            if on_server_added:
                on_server_added()
            
            # Close dialog
            dialog.close()
        else:
            show_error(dialog, "Failed to add server. Check console for details.")
            
    except json.JSONDecodeError:
        show_error(dialog, "Invalid data format")
    except Exception as e:
        print(f"Error adding server: {e}")
        show_error(dialog, f"Error: {str(e)}")


def show_error(dialog, message):
    """Show error message in the dialog."""
    js = f"""
    var errorDiv = document.getElementById('error-message');
    if (!errorDiv) {{
        errorDiv = document.createElement('div');
        errorDiv.id = 'error-message';
        errorDiv.style.color = 'red';
        errorDiv.style.padding = '10px';
        errorDiv.style.textAlign = 'center';
        document.getElementById('content').appendChild(errorDiv);
    }}
    errorDiv.textContent = '{message}';
    setTimeout(() => {{ errorDiv.textContent = ''; }}, 3000);
    """
    dialog.view.page().runJavaScript(js)
