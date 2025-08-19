#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import csv
import requests
import json
import logging

# --- Configuration -----------------------------------------------------------
# This script uses dedicated explorer APIs to find direct SPO votes.
CONFIG = {
    "KOIOS_BASE_URL": "https://api.koios.rest/api/v1",
    "CEXPLORER_BASE_URL": "https://api.cexplorer.io/api/v1",
    "HTTP_TIMEOUT": 120,
    "API_SLEEP_INTERVAL": 0.1,
    "KOIOS_POOL_INFO_BATCH_SIZE": 80,
    "OUTPUT_CSV_FILENAME": "spo_governance_votes.csv",
    "GIST_FILENAME": "spo_governance_votes.csv",
    "GIST_UPDATE_RETRIES": 3,
    "GIST_UPDATE_RETRY_DELAY": 5,
}

# --- Logging Setup -----------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)

# --- Helper Functions --------------------------------------------------------
def api_get_request(url):
    """A reusable function for making GET requests with error handling."""
    try:
        response = requests.get(url, timeout=CONFIG["HTTP_TIMEOUT"])
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logging.error(f"API request failed for URL {url}: {e}")
        return None

def parse_meta_json(meta_json):
    """Safely parses metadata that could be a string or dict."""
    if not meta_json: return {}
    try:
        return json.loads(meta_json) if isinstance(meta_json, str) else meta_json
    except (json.JSONDecodeError, AttributeError):
        return {}

def extract_ticker(parsed_meta):
    t = parsed_meta.get("ticker") or parsed_meta.get("pool_ticker")
    return str(t) if t else ""

def extract_homepage(parsed_meta):
    h = parsed_meta.get("homepage") or parsed_meta.get("pool_homepage")
    return str(h) if h else ""

# --- Data Fetching Logic -----------------------------------------------------
def fetch_all_pool_details():
    """
    Fetches a master list of all stake pools and their details from Koios.
    """
    logging.info("Fetching master list of all stake pools from Koios...")
    pool_list_data = api_get_request(f"{CONFIG['KOIOS_BASE_URL']}/pool_list")
    if not pool_list_data:
        logging.error("Could not fetch pool list from Koios. Exiting.")
        return None

    pool_ids = [p.get('pool_id_bech32') for p in pool_list_data if p.get('pool_id_bech32')]
    logging.info(f"Found {len(pool_ids)} pools. Fetching details in batches...")

    all_pools = {}
    batch_size = CONFIG['KOIOS_POOL_INFO_BATCH_SIZE']
    for i in range(0, len(pool_ids), batch_size):
        chunk = pool_ids[i:i + batch_size]
        try:
            logging.info(f"Fetching details for batch {i//batch_size + 1} of {len(pool_ids)//batch_size + 1}...")
            details_data = requests.post(
                f"{CONFIG['KOIOS_BASE_URL']}/pool_info",
                json={"_pool_bech32_ids": chunk},
                timeout=CONFIG['HTTP_TIMEOUT']
            ).json()
            
            for p in details_data:
                meta = parse_meta_json(p.get("meta_json"))
                pool_id = p.get('pool_id_bech32')
                if pool_id:
                    all_pools[pool_id] = {
                        'ticker': extract_ticker(meta),
                        'homepage': extract_homepage(meta)
                    }
            time.sleep(CONFIG['API_SLEEP_INTERVAL'])
        except requests.RequestException as e:
            logging.error(f"Failed to fetch batch details: {e}")

    logging.info(f"Successfully fetched details for {len(all_pools)} pools.")
    return all_pools

def fetch_active_spo_governance_actions():
    """Fetches governance proposals where SPOs can vote from Cexplorer."""
    logging.info("Fetching active governance actions from Cexplorer...")
    data = api_get_request(f"{CONFIG['CEXPLORER_BASE_URL']}/governance/action/proposals")
    if data and 'data' in data:
        active_proposals = [p for p in data['data'] if p.get('status') == 'Voting']
        logging.info(f"Found {len(active_proposals)} active governance actions.")
        return active_proposals
    logging.warning("Could not find any active governance actions.")
    return []

def fetch_spo_votes_for_action(action_tx_hash):
    """Fetches SPO votes for a specific governance action."""
    logging.info(f"Fetching SPO votes for action tx {action_tx_hash[:12]}...")
    url = f"{CONFIG['CEXPLORER_BASE_URL']}/governance/action/votes/{action_tx_hash}"
    data = api_get_request(url)
    spo_votes = {}
    if data and 'data' in data:
        for vote in data['data']:
            if vote.get('voterType') == 'SPO' and vote.get('poolId'):
                spo_votes[vote['poolId']] = vote['vote'].capitalize()
    return spo_votes

# --- Data Processing and Gist Update -----------------------------------------
def generate_and_publish_report(all_pools, active_actions):
    """Generates the final CSV report and updates the Gist."""
    report_rows = []
    
    if not active_actions:
        logging.warning("No active actions to report on.")
        report_rows.append({
            "pool_id": "N/A", "ticker": "N/A", "homepage": "N/A", 
            "governance_action": "No active SPO proposals found", "vote": "N/A"
        })
    else:
        for action in active_actions:
            action_tx_hash = action['txHash']
            action_title = action.get('title', 'Untitled Action')
            spo_votes_for_action = fetch_spo_votes_for_action(action_tx_hash)
            
            for pool_id, pool_info in all_pools.items():
                vote = spo_votes_for_action.get(pool_id, "Did Not Vote")
                report_rows.append({
                    "pool_id": pool_id,
                    "ticker": pool_info['ticker'],
                    "homepage": pool_info['homepage'],
                    "governance_action": action_title,
                    "vote": vote
                })

    output_path = CONFIG['OUTPUT_CSV_FILENAME']
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        fieldnames = ["pool_id", "ticker", "homepage", "governance_action", "vote"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(report_rows)
    logging.info(f"Wrote {len(report_rows)} rows to {output_path}")
    
    update_github_gist(output_path)

def update_github_gist(file_path):
    """Updates the GitHub Gist with the content of the specified file."""
    logging.info("Preparing to update GitHub Gist...")
    gist_id = os.getenv('GIST_ID')
    github_token = os.getenv('GITHUB_TOKEN')

    if not gist_id or not github_token:
        logging.error("GIST_ID or GITHUB_TOKEN not found. Skipping Gist update.")
        return

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            csv_content = f.read()
    except FileNotFoundError:
        logging.error(f"Source file {file_path} not found.")
        return

    headers = {'Authorization': f'token {github_token}', 'Accept': 'application/vnd.github.v3+json'}
    data = {
        'description': 'Live Cardano SPO Governance Votes',
        'files': {CONFIG['GIST_FILENAME']: {'content': csv_content}}
    }
    url = f'https://api.github.com/gists/{gist_id}'

    for attempt in range(CONFIG['GIST_UPDATE_RETRIES']):
        try:
            response = requests.patch(url, headers=headers, data=json.dumps(data), timeout=CONFIG['HTTP_TIMEOUT'])
            response.raise_for_status()
            logging.info(f"✅ Gist updated successfully! URL: {response.json()['html_url']}")
            return
        except requests.RequestException as e:
            logging.warning(f"Gist update attempt {attempt + 1} failed: {e}")
            if attempt < CONFIG['GIST_UPDATE_RETRIES'] - 1:
                time.sleep(CONFIG['GIST_UPDATE_RETRY_DELAY'])
            else:
                logging.error("All Gist update attempts failed.")

# --- Main Execution ----------------------------------------------------------
def main():
    """Main script execution flow."""
    all_pools = fetch_all_pool_details()
    if not all_pools:
        return
        
    active_actions = fetch_active_spo_governance_actions()
    generate_and_publish_report(all_pools, active_actions)
    
    logging.info("Script finished.")

if __name__ == "__main__":
    main()
