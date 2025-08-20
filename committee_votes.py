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
# Gist configuration
GIST_ID = "7820f9ea2354d0fb8e1c160cae53adf1"
GIST_FILENAME = "committee.json"
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
        
        # The API returns a list with one object, and the members are inside that object.
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
    print(f"\n🔍 Step 2: Fetching votes for member: {member_id}...")
    try:
        response = requests.get(endpoint, headers=HEADERS, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ Error fetching votes for {member_id}: {e}")
        return None

def update_gist(all_votes_data):
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
    
    payload = {
        "files": {
            GIST_FILENAME: {
                "content": json.dumps(all_votes_data, indent=2)
            }
        }
    }
    
    print("\n🚀 Step 3: Updating Gist...")
    try:
        response = requests.patch(gist_url, headers=headers, data=json.dumps(payload), timeout=30)
        response.raise_for_status()
        print("✅ Gist updated successfully!")
    except requests.exceptions.RequestException as e:
        print(f"❌ Error updating Gist: {e}")
        print(f"Response content: {response.text}")


def main():
    """
    Main function to orchestrate the process.
    """
    members = get_committee_members()
    
    if not members:
        print("\nCould not retrieve committee members. Exiting.")
        return

    all_votes = []
    print("\n--- 🗳️  Processing Committee Vote Records ---")

    for member in members:
        status = member.get("status")
        member_id = member.get("cc_hot_id")

        if not member_id:
            continue
        
        print("\n" + "=" * 80)
        print(f"📄 Processing Member: {member_id} (Status: {status.capitalize()})")
        print("=" * 80)

        votes = get_votes_for_member(member_id)
        
        if votes:
            print(f"✅ Found {len(votes)} votes.")
            # Add member info to each vote record for context
            for vote in votes:
                vote['member_id'] = member_id
                vote['member_status'] = status
            all_votes.extend(votes)
        else:
            print("No votes found for this member.")
        
        # A small delay to be polite to the API server
        time.sleep(0.25)

    # Sort all votes globally by block time
    all_votes_sorted = sorted(all_votes, key=lambda x: x.get('block_time', 0), reverse=True)
    
    # Save to local file
    output_filename = 'committee.json'
    with open(output_filename, 'w') as f:
        json.dump(all_votes_sorted, f, indent=2)
    print(f"\n✅ All vote data saved to {output_filename}")

    # Update the Gist
    update_gist(all_votes_sorted)


if __name__ == "__main__":
    main()
