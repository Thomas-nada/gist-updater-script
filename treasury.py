import requests
import json
import os
from decimal import Decimal, getcontext

# Set precision for Decimal calculations
getcontext().prec = 28

# --- Helper Functions ---

def lovelace_to_ada(lovelace):
    """Converts a Lovelace value to ADA."""
    return Decimal(lovelace) / Decimal(1_000_000)

# --- Data Gathering Functions ---

def get_current_treasury_balance():
    """Fetches the current total balance of the Cardano treasury and returns it."""
    api_url = "https://api.koios.rest/api/v1/totals?order=epoch_no.desc&limit=1"
    try:
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        data = response.json()
        if not data:
            return None
        lovelace_balance = int(data[0].get('treasury'))
        return lovelace_to_ada(lovelace_balance)
    except Exception as e:
        print(f"An unexpected error occurred while fetching total balance: {e}")
        return None


def get_main_treasury_history():
    """
    Tracks the movements of the main Cardano treasury for all epochs since the start (epoch 208).
    """
    print(f"\n📜 Fetching full treasury history since Shelley era (Epoch 208)...")
    
    # The Shelley era, which introduced the treasury, started at epoch 208.
    start_epoch = 208
    history_data = []
    all_epoch_totals = []
    offset = 0

    try:
        # The Koios API is paginated (1000 results per page). We need to loop to get all pages.
        while True:
            print(f"   Fetching page starting at offset {offset}...", end='\r')
            # We fetch all totals starting from epoch 208, ordered chronologically.
            totals_url = f"https://api.koios.rest/api/v1/totals?epoch_no=gte.{start_epoch}&order=epoch_no.asc&offset={offset}"
            totals_response = requests.get(totals_url, timeout=30)
            totals_response.raise_for_status()
            page_data = totals_response.json()
            
            if not page_data:
                # If a page returns no data, we've reached the end.
                break
            
            all_epoch_totals.extend(page_data)
            
            if len(page_data) < 1000:
                # If we get less than 1000 results, it's the last page.
                break
                
            offset += 1000

        print("\nAll epoch data fetched. Processing history...")
        totals_data = {item['epoch_no']: item for item in all_epoch_totals}

        # Iterate through the epochs we have data for to calculate changes.
        sorted_epochs = sorted(totals_data.keys())
        for i in range(1, len(sorted_epochs)):
            current_epoch_num = sorted_epochs[i]
            previous_epoch_num = sorted_epochs[i-1]

            treasury_current = Decimal(totals_data[current_epoch_num]['treasury'])
            treasury_previous = Decimal(totals_data[previous_epoch_num]['treasury'])
            net_change = treasury_current - treasury_previous

            inflow_ada = lovelace_to_ada(max(Decimal(0), net_change))
            outflow_ada = lovelace_to_ada(-min(Decimal(0), net_change))
            
            history_data.append({
                "epoch": current_epoch_num,
                "inflow_ada": f"{inflow_ada:.2f}",
                "outflow_ada": f"{outflow_ada:.2f}",
                "net_change_ada": f"{lovelace_to_ada(net_change):.2f}",
                "final_balance_ada": f"{lovelace_to_ada(treasury_current):.2f}"
            })
        return history_data
    except Exception as e:
        print(f"An error occurred during treasury history tracking: {e}")
        return []

# --- Gist Update Function ---

def update_gist(gist_id, github_token, filename, content):
    """
    Updates a specific file within a GitHub Gist.
    """
    print(f"Attempting to update Gist file: {filename}")
    api_url = f"https://api.github.com/gists/{gist_id}"
    headers = {
        'Authorization': f'Bearer {github_token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    payload = {
        "files": {
            filename: {
                "content": content
            }
        }
    }
    try:
        response = requests.patch(api_url, headers=headers, data=json.dumps(payload), timeout=20)
        response.raise_for_status()
        print("✅ Gist updated successfully!")
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to update Gist: {e}")
        print(f"Response Body: {e.response.text if e.response else 'No response'}")


if __name__ == "__main__":
    # 1. Retrieve secrets from environment variables using your specified names
    TREASURY_GIST_ID = os.environ.get('TREASURY_GIST')
    GIST_UPDATE_TOKEN = os.environ.get('GIST_UPDATE_TOKEN')
    
    if not TREASURY_GIST_ID or not GIST_UPDATE_TOKEN:
        print("❌ Error: TREASURY_GIST and GIST_UPDATE_TOKEN environment variables must be set.")
    else:
        # 2. Fetch the Cardano data
        print("--- Running Cardano Treasury Tracker ---")
        current_balance = get_current_treasury_balance()
        # The function now fetches all history by default
        history = get_main_treasury_history()
        
        if current_balance is not None and history:
            # 3. Prepare the JSON output
            output_data = {
                "current_balance_ada": f"{current_balance:.2f}",
                "history": history
            }
            
            # Convert the Python dictionary to a JSON formatted string
            json_content = json.dumps(output_data, indent=2)
            
            # 4. Update the Gist
            # The filename comes from your Gist URL
            gist_filename = "treasury.json" 
            update_gist(TREASURY_GIST_ID, GIST_UPDATE_TOKEN, gist_filename, json_content)
        else:
            print("❌ Failed to fetch Cardano data. Gist will not be updated.")

