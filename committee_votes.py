import requests
import json
import time
import os

# --- Configuration ---
# Base URL for the Koios API
KOIOS_BASE_URL = "https://api.koios.rest/api/v1"
# Standard headers for the HTTP requests
HEADERS = {
    "accept": "application/json"
}
# Gist configuration from the original script
GIST_ID = "7820f9ea2354d0fb8e1c160cae53adf1"
GIST_FILENAME = "committee.json" # The filename within the Gist to update
GITHUB_TOKEN = os.environ.get("GIST_UPDATE_TOKEN")

def get_committee_members():
    """
    Fetches the list of all constitutional committee members from the Koios API.
    
    Returns:
        list: A list of member objects, or None if the request fails.
    """
    endpoint = f"{KOIOS_BASE_URL}/committee_info"
    print("🔍 Step 1: Fetching list of all committee members...")
    try:
        response = requests.get(endpoint, headers=HEADERS, timeout=30)
        response.raise_for_status()  
        data = response.json()
        
        if data and isinstance(data, list) and 'members' in data[0]:
            print("✅ Successfully fetched and parsed committee members.")
            return data[0]['members']
        else:
            print("❌ Unexpected data structure received from API.")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Error fetching committee members: {e}")
        return None
    except (IndexError, KeyError) as e:
        print(f"❌ Error parsing the member data structure: {e}")
        return None

def get_votes_for_member(member_id):
    """
    Fetches the voting history for a specific committee member using their ID.
    
    Args:
        member_id (str): The '_cc_hot_id' of the committee member.
        
    Returns:
        list: A list of vote objects, or None if the request fails.
    """
    endpoint = f"{KOIOS_BASE_URL}/committee_votes"
    params = {"_cc_hot_id": member_id}
    print(f"🔍 Fetching votes for member: {member_id}...")
    try:
        response = requests.get(endpoint, headers=HEADERS, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ Error fetching votes for {member_id}: {e}")
        return None

def update_gist(data_to_upload):
    """
    Updates a GitHub Gist with the provided data.
    """
    if not GITHUB_TOKEN:
        print("❌ GIST_UPDATE_TOKEN is not set. Cannot update Gist.")
        return

    gist_url = f"https://api.github.com/gists/{GIST_ID}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    # The content for the Gist file is the JSON-formatted string of our combined data
    payload = {
        "files": {
            GIST_FILENAME: {
                "content": json.dumps(data_to_upload, indent=2)
            }
        }
    }
    
    print(f"\n🚀 Step 3: Updating Gist file '{GIST_FILENAME}'...")
    try:
        response = requests.patch(gist_url, headers=headers, data=json.dumps(payload), timeout=30)
        response.raise_for_status()
        print("✅ Gist updated successfully!")
    except requests.exceptions.RequestException as e:
        print(f"❌ Error updating Gist: {e}")
        if response:
            print(f"Response content: {response.text}")

def main():
    """
    Main function to orchestrate the process and update the Gist.
    """
    members = get_committee_members()
    
    if not members:
        print("\nCould not retrieve committee members. Exiting.")
        return

    all_votes = []
    print("\n--- 🗳️  Step 2: Processing All Committee Vote Records ---")

    for member in members:
        member_id = member.get("cc_hot_id")

        if not member_id:
            continue
        
        votes = get_votes_for_member(member_id)
        
        if votes:
            print(f"✅ Found {len(votes)} votes for {member_id}.")
            for vote in votes:
                vote['member_id'] = member_id
            all_votes.extend(votes)
        else:
            print(f"No votes found for {member_id}.")
        
        time.sleep(0.25)

    all_votes_sorted = sorted(all_votes, key=lambda x: x.get('block_time', 0), reverse=True)
    
    # Create the single dictionary to hold all the data.
    combined_data = {
        "committee_members": members,
        "committee_votes": all_votes_sorted
    }

    # Update the Gist with the combined data
    update_gist(combined_data)


if __name__ == "__main__":
    main()
