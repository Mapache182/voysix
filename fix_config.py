import json
import os

app_data_dir = os.path.join(os.environ.get("APPDATA", ""), "voysix")
config_file = os.path.join(app_data_dir, "config.json")

if os.path.exists(config_file):
    with open(config_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # 🔹 Move 'tskey-auth' from remote_api_key to tailscale_auth_key
    if "remote_api_key" in data and data["remote_api_key"].startswith("tskey-"):
        print(f"Moving Tailscale Auth Key from 'remote_api_key' to 'tailscale_auth_key'...")
        data["tailscale_auth_key"] = data["remote_api_key"]
        data["remote_api_key"] = ""
    
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
    print("Configuration updated successfully.")
else:
    print(f"Config file not found at {config_file}")
