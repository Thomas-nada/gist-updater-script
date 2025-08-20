# committee_votes.py
import requests
import json
import sys
from io import StringIO
import contextlib
import time

# --- Configuration ---
KOIOS_BASE_URL = "https://api.koios.rest/api/v1"
HEADERS = {"accept": "application/json"}

@contextlib.contextmanager
def capture_stdout():
    """A context manager to capture stdout."""
    old_stdout = sys.stdout
    sys.stdout = captured_output = StringIO()
    try:
        yield captured_output
    finally:
        sys.stdout = old_stdout

def get_committee_members():
    """Fetches the list of all constitutional committee members."""
    endpoint = f"{KOIOS_BASE_URL}/committee_info"
    print("🔍 Step 1: Fetching list of all committee members...")
    try:
        response = requests.get(endpoint, headers=HEADERS, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        # New, more robust parsing for the updated API structure
        if (data and isinstance(data, list) and data[0] and 
            'committee_state' in data[0] and 'members' in data[0]['committee_state']):
            print("✅ Successfully fetched and parsed committee members.")
            # The members are now a dictionary, not a list
            return data[0]['committee_state']['members']
        else:
            print("❌ Unexpected data structure received from API.")
            return None
    except Exception as e:
        print(f"❌ Error fetching or parsing committee members: {e}")
        return None

def get_votes_for_member(member_id):
    """Fetches the voting history for a specific committee member."""
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

def generate_report():
    """Generates the full vote report."""
    members_dict = get_committee_members()
    if not members_dict:
        print("\nCould not retrieve committee members. Exiting.")
        return

    print("\n--- 🗳️ Committee Vote Records ---")
    # Iterate over the dictionary of members
    for member_id, member_details in members_dict.items():
        status = member_details.get("status", "N/A")
        
        print("\n" + "=" * 80)
        print(f"📄 Votes for Member: {member_id} (Status: {status.capitalize()})")
        print("=" * 80)

        votes = get_votes_for_member(member_id)
        if votes:
            print(f"✅ Found {len(votes)} votes.")
            print("-" * 80)
            print(f"{'Proposal ID':<70} {'Vote':<10}")
            print(f"{'Transaction Hash':<70}")
            print("-" * 80)
            for vote in sorted(votes, key=lambda x: x.get('block_time', 0), reverse=True):
                proposal_id = vote.get('proposal_id', 'N/A')
                tx_hash = vote.get('tx_hash', 'N/A')
                vote_cast = vote.get('vote', 'N/A').capitalize()
                print(f"{proposal_id:<70} {vote_cast:<10}")
                print(f"{tx_hash:<70}")
                print("-" * 80)
        else:
            print("No votes found for this member.")
        
        # A small delay to be polite to the API server
        time.sleep(0.25)


def main():
    """Main function to capture and return the report."""
    with capture_stdout() as captured:
        generate_report()
    return captured.getvalue()

if __name__ == "__main__":
    report_content = main()
    # This allows the update_gist.py script to capture the output
    print(report_content)

