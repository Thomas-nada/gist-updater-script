# filename: create_gov_gist.py

import os
import requests
import json
import csv
import io
from datetime import datetime

# --- Blockfrost Configuration ---
BF_API_URL = "https://cardano-mainnet.blockfrost.io/api/v0"
BF_ENDPOINT = "/gov/proposals"

# --- GitHub Gist Configuration ---
GH_API_URL = "https://api.github.com/gists"
GIST_FILENAME = "cardano_governance_proposals.csv"

# ==============================================================================
# PART 1: FETCH DATA FROM BLOCKFROST
# ==============================================================================

def get_blockfrost_project_id():
    """Fetches the Blockfrost Project ID from an environment variable."""
    project_id = os.getenv('BLOCKFROST_PROJECT_ID')
    if not project_id:
        print("Error: The 'BLOCKFROST_PROJECT_ID' environment variable is not set.")
        exit(1)
    return project_id

def fetch_all_governance_actions(project_id):
    """Fetches all governance action proposals from Blockfrost, handling pagination."""
    headers = {'project_id': project_id}
    all_proposals = []
    page = 1
    
    print("Fetching governance action proposals from Cardano mainnet...")
    while True:
        params = {'page': page, 'count': 100}
        try:
            response = requests.get(BF_API_URL + BF_ENDPOINT, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            if not data:
                print("Reached the last page of results.")
                break
            print(f"Fetched {len(data)} proposals from page {page}.")
            all_proposals.extend(data)
            page += 1
        except requests.exceptions.HTTPError as http_err:
            print(f"❌ HTTP error occurred during Blockfrost fetch: {http_err}")
            return None
        except requests.exceptions.RequestException as req_err:
            print(f"❌ An error occurred during Blockfrost request: {req_err}")
            return None
            
    return all_proposals

# ==============================================================================
# PART 2: PROCESS DATA AND UPLOAD TO GIST
# ==============================================================================

def get_github_token():
    """Fetches the GitHub Gist PAT from an environment variable."""
    token = os.getenv('GA_GIST')
    if not token:
        print("Error: The 'GA_GIST' environment variable is not set.")
        print("Please set it with your GitHub Personal Access Token with 'gist' scope.")
        exit(1)
    return token

def convert_proposals_to_csv(proposals):
    """Converts a list of proposal dictionaries to a CSV formatted string."""
    if not proposals:
        return ""
    
    # Use an in-memory string buffer for CSV writing
    output = io.StringIO()
    
    # Define CSV headers, flattening nested JSON objects for clarity
    fieldnames = [
        'proposal_id', 'tx_hash', 'output_index', 'type', 
        'expiry_epoch', 'ratified_epoch', 'enacted_epoch',
        'anchor_url', 'anchor_data_hash', 'committee_votes'
    ]
    
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    
    for proposal in proposals:
        # Create a flattened dictionary for the CSV row
        row = {
            'proposal_id': proposal.get('proposal_id', ''),
            'tx_hash': proposal.get('tx_hash', ''),
            'output_index': proposal.get('output_index', ''),
            'type': proposal.get('type', ''),
            'expiry_epoch': proposal.get('expiry_epoch'),
            'ratified_epoch': proposal.get('ratified_epoch'),
            'enacted_epoch': proposal.get('enacted_epoch'),
            # Safely access nested 'anchor' object
            'anchor_url': proposal.get('anchor', {}).get('url', ''),
            'anchor_data_hash': proposal.get('anchor', {}).get('data_hash', ''),
            # Join the list of committee votes into a single comma-separated string
            'committee_votes': ','.join(proposal.get('committee_votes', []))
        }
        writer.writerow(row)
        
    return output.getvalue()

def create_gist(token, filename, content, description):
    """Creates a new secret GitHub Gist with the provided content."""
    if not content:
        print("No content to upload. Skipping Gist creation.")
        return

    print(f"Uploading content to a new GitHub Gist named '{filename}'...")
    
    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/vnd.github.v3+json',
        'X-GitHub-Api-Version': '2022-11-28' # Recommended practice
    }
    
    payload = {
        'description': description,
        'public': False,  # Creates a secret Gist, only accessible via URL
        'files': {
            filename: {
                'content': content
            }
        }
    }
    
    try:
        response = requests.post(GH_API_URL, headers=headers, data=json.dumps(payload))
        response.raise_for_status() # Raises an exception for 4xx/5xx status codes
        
        gist_data = response.json()
        gist_url = gist_data.get('html_url')
        print(f"✅ Successfully created Gist: {gist_url}")
        
    except requests.exceptions.HTTPError as http_err:
        print(f"❌ Gist creation failed. HTTP error occurred: {http_err}")
        print(f"Response Body: {response.text}")
    except requests.exceptions.RequestException as req_err:
        print(f"❌ An error occurred during the request to GitHub: {req_err}")

# ==============================================================================
# MAIN EXECUTION
# ==============================================================================

def main():
    """Main function to execute the script."""
    # Part 1: Fetch data
    bf_project_id = get_blockfrost_project_id()
    proposals = fetch_all_governance_actions(bf_project_id)
    
    if proposals:
        print(f"\nFetched a total of {len(proposals)} governance proposals.")
        
        # Part 2: Process and upload
        print("Converting data to CSV format...")
        csv_content = convert_proposals_to_csv(proposals)
        
        if csv_content:
            gh_token = get_github_token()
            current_time_utc = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
            gist_description = f"Cardano Governance Proposals - Report from {current_time_utc}"
            
            create_gist(gh_token, GIST_FILENAME, csv_content, gist_description)
    else:
        print("\nNo governance proposals were fetched. Halting script.")

if __name__ == "__main__":
    main()
