# update_gist.py
import os
import requests
import json
import subprocess
from datetime import datetime

# --- Configuration ---
# Your GitHub username
GITHUB_USER = "YOUR_GITHUB_USERNAME" # <-- IMPORTANT: Change this
# The filename as it will appear in the Gist
GIST_FILENAME = "cardano-committee-votes.md"
# The description for the Gist
GIST_DESCRIPTION = "Cardano Constitutional Committee Votes (Automated)"

def update_gist(token, gist_id, filename, content):
    """Updates an existing Gist."""
    headers = {'Authorization': f'token {token}'}
    payload = {
        "description": f"{GIST_DESCRIPTION} - Last updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "files": {
            filename: {
                "content": content
            }
        }
    }
    url = f"https://api.github.com/gists/{gist_id}"
    response = requests.patch(url, headers=headers, data=json.dumps(payload))
    response.raise_for_status()
    print(f"✅ Successfully updated Gist ID: {gist_id}")

def create_gist(token, filename, content):
    """Creates a new Gist."""
    headers = {'Authorization': f'token {token}'}
    payload = {
        "description": f"{GIST_DESCRIPTION} - Created: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
        "public": True,
        "files": {
            filename: {
                "content": content
            }
        }
    }
    url = "https://api.github.com/gists"
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    response.raise_for_status()
    gist_data = response.json()
    new_gist_id = gist_data['id']
    print(f"✅ Successfully created new Gist with ID: {new_gist_id}")
    print("\nIMPORTANT: Please add this Gist ID as a repository secret named 'COMMITTEE_GIST' for future updates.")
    return new_gist_id

def main():
    """Main function to run the report and update the Gist."""
    # Use the new secret name 'GIST_UPDATE_TOKEN'
    token = os.getenv("GIST_UPDATE_TOKEN")
    gist_id = os.getenv("COMMITTEE_GIST")

    if not token:
        print("❌ Error: GIST_UPDATE_TOKEN environment variable not set.")
        return

    print("🏃 Running committee_votes.py to get the latest data...")
    # Run the committee_votes.py script and capture its output
    result = subprocess.run(['python', 'committee_votes.py'], capture_output=True, text=True)
    
    if result.returncode != 0:
        print("❌ Error running committee_votes.py:")
        print(result.stderr)
        return
        
    report_content = result.stdout
    print("✅ Successfully captured report content.")

    try:
        if gist_id:
            print(f"Found Gist ID: {gist_id}. Attempting to update...")
            update_gist(token, gist_id, GIST_FILENAME, report_content)
        else:
            print("No Gist ID found. Creating a new one...")
            create_gist(token, GIST_FILENAME, report_content)
    except requests.exceptions.RequestException as e:
        print(f"❌ An API error occurred: {e}")
        if e.response is not None:
            print(f"Error Response: {e.response.text}")

if __name__ == "__main__":
    main()
