#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import csv
import argparse
import collections
import requests
import json
import logging

# --- Configuration -----------------------------------------------------------
# Centralized configuration for easy management of script parameters.
CONFIG = {
    "KOIOS_BASE_URL": os.getenv("KOIOS_BASE", "https://api.koios.rest/api/v1"),
    "BLOCKFROST_BASE_URL": os.getenv("BLOCKFROST_BASE", "https://cardano-mainnet.blockfrost.io/api/v0"),
    "HTTP_TIMEOUT_GET": 60,
    "HTTP_TIMEOUT_POST": 120,
    "API_SLEEP_INTERVAL": 0.15,
    "KOIOS_POOL_INFO_BATCH_SIZE": 80,
    "GIST_UPDATE_RETRIES": 3,
    "GIST_UPDATE_RETRY_DELAY": 5, # seconds
    "OUTPUT_CSV_FULL": "pools_with_drep_and_voting_power.csv",
    "OUTPUT_CSV_SUMMARY": "voting_power_by_literal.csv",
    "GIST_FILENAME": "drep-delegation-summary.csv"
}

# --- Logging Setup -----------------------------------------------------------
# Use the standard logging module for better output management.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)

# --- Helper Functions --------------------------------------------------------
def ada(lovelace):
    """Converts lovelace to ADA."""
    try:
        return float(int(lovelace)) / 1_000_000.0
    except (ValueError, TypeError):
        return 0.0

def normalize_literal(x):
    """Normalizes a string for consistent grouping."""
    if x is None:
        return None
    s = str(x).strip().lower()
    for ch in ["-", " ", ":", "."]:
        s = s.replace(ch, "_")
    while "__" in s:
        s = s.replace("__", "_")
    return s

def extract_ticker(meta_json):
    """Safely extracts a pool ticker from metadata JSON."""
    if not meta_json:
        return ""
    try:
        if isinstance(meta_json, str):
            meta_json = json.loads(meta_json)
        if isinstance(meta_json, dict):
            t = meta_json.get("ticker") or meta_json.get("pool_ticker")
            return str(t) if t else ""
    except (json.JSONDecodeError, AttributeError):
        pass
    return ""

# --- Data Fetching Logic -----------------------------------------------------
def get_all_pool_ids(blockfrost_key):
    """
    Enumerates all pool IDs, preferring Koios but falling back to Blockfrost
    if Koios results appear capped or incomplete.
    """
    koios_url = f"{CONFIG['KOIOS_BASE_URL']}/pool_list"
    try:
        logging.info("Attempting to fetch all pool IDs from Koios...")
        r = requests.get(koios_url, timeout=CONFIG['HTTP_TIMEOUT_GET'])
        r.raise_for_status()
        koios_ids = [p["pool_id_bech32"] for p in r.json()]
        logging.info(f"Koios returned {len(koios_ids)} pool IDs.")
        # If Koios returns a capped amount (typically 1000), it's unreliable.
        if len(koios_ids) < 1000:
            return koios_ids
    except requests.RequestException as e:
        logging.warning(f"Koios pool list fetch failed: {e}. Falling back to Blockfrost.")

    if not blockfrost_key:
        logging.error("Blockfrost key is required as a fallback but was not provided.")
        sys.exit(1)

    logging.info("Using Blockfrost to enumerate all pools...")
    all_ids, page = [], 1
    sess = requests.Session()
    sess.headers.update({"project_id": blockfrost_key})
    while True:
        try:
            url = f"{CONFIG['BLOCKFROST_BASE_URL']}/pools?page={page}"
            r = sess.get(url, timeout=CONFIG['HTTP_TIMEOUT_GET'])
            if r.status_code == 429: # Rate limit
                time.sleep(2)
                continue
            r.raise_for_status()
            page_ids = r.json()
            if not page_ids:
                break
            all_ids.extend(page_ids)
            logging.info(f"Blockfrost /pools page {page}: Got {len(page_ids)} (total {len(all_ids)})")
            page += 1
            time.sleep(CONFIG['API_SLEEP_INTERVAL'])
        except requests.RequestException as e:
            logging.error(f"Blockfrost request failed on page {page}: {e}")
            break
    return all_ids


def fetch_pool_info_rows(pool_ids):
    """Fetches detailed pool information in batches from Koios."""
    logging.info(f"Fetching detailed info for {len(pool_ids)} pools from Koios...")
    sess = requests.Session()
    rows, i = [], 0
    batch_size = CONFIG['KOIOS_POOL_INFO_BATCH_SIZE']
    while i < len(pool_ids):
        chunk = pool_ids[i:i + batch_size]
        try:
            r = sess.post(
                f"{CONFIG['KOIOS_BASE_URL']}/pool_info",
                json={"_pool_bech32_ids": chunk},
                timeout=CONFIG['HTTP_TIMEOUT_POST']
            )
            if r.status_code == 413: # Payload too large
                batch_size = max(10, batch_size // 2)
                logging.warning(f"413 error: Reducing batch size to {batch_size} and retrying.")
                continue
            r.raise_for_status()
            
            for p in r.json():
                vp = p.get("voting_power", 0)
                rows.append({
                    "pool_id_bech32": p.get("pool_id_bech32"),
                    "ticker": extract_ticker(p.get("meta_json")),
                    "reward_addr": p.get("reward_addr"),
                    "reward_addr_delegated_drep_raw": p.get("reward_addr_delegated_drep"),
                    "reward_addr_delegated_drep_norm": normalize_literal(p.get("reward_addr_delegated_drep")),
                    "voting_power_lovelace": int(vp),
                    "voting_power_ADA": f"{ada(vp):.6f}",
                })
            i += len(chunk)
            time.sleep(CONFIG['API_SLEEP_INTERVAL'])
        except requests.RequestException as e:
            logging.error(f"Koios /pool_info request failed: {e}. Retrying in 5s...")
            time.sleep(5)
    return rows

# --- Data Processing and Output ----------------------------------------------
def write_csv_rows(rows, path, fields):
    """Writes a list of dictionaries to a CSV file."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    logging.info(f"Wrote {len(rows)} rows to {path}")

def summarize_and_write(rows):
    """Summarizes voting power by DRep and writes to CSV."""
    groups = collections.defaultdict(lambda: {"count": 0, "lovelace": 0})
    total_lovelace = sum(int(r["voting_power_lovelace"]) for r in rows)

    for r in rows:
        lit = r["reward_addr_delegated_drep_norm"]
        ll = int(r["voting_power_lovelace"])
        groups[lit]["count"] += 1
        groups[lit]["lovelace"] += ll
    
    summary_path = CONFIG['OUTPUT_CSV_SUMMARY']
    with open(summary_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["normalized_literal", "pools", "total_lovelace", "total_ADA", "share_%"])
        for lit, agg in sorted(groups.items(), key=lambda kv: (-kv[1]["lovelace"], str(kv[0]))):
            share = (agg["lovelace"] / total_lovelace * 100.0) if total_lovelace else 0.0
            writer.writerow([
                lit if lit is not None else "",
                agg["count"],
                agg["lovelace"],
                f"{ada(agg['lovelace']):.6f}",
                f"{share:.4f}"
            ])
    logging.info(f"Wrote summary to {summary_path}")
    
    # Also log the high-level summary to the console
    abstain_total = groups.get('drep_always_abstain', {}).get('lovelace', 0)
    noconf_total = groups.get('drep_always_no_confidence', {}).get('lovelace', 0)
    logging.info("--- Voting Power Summary ---")
    logging.info(f"Always Abstain Total: {ada(abstain_total):,.6f} ADA")
    logging.info(f"Always No-Confidence Total: {ada(noconf_total):,.6f} ADA")
    logging.info(f"Overall Voting Power Seen: {ada(total_lovelace):,.6f} ADA")


# --- Gist Publishing Logic ---------------------------------------------------
def update_github_gist_with_retries():
    """
    Updates a GitHub Gist with the generated summary CSV, with retries on failure.
    """
    logging.info("Preparing to update GitHub Gist...")
    gist_id = os.getenv('GIST_ID')
    github_token = os.getenv('GITHUB_TOKEN')

    if not gist_id or not github_token:
        logging.error("GIST_ID or GITHUB_TOKEN environment variables not found. Skipping Gist update.")
        return

    try:
        with open(CONFIG['OUTPUT_CSV_SUMMARY'], 'r', encoding='utf-8') as f:
            csv_content = f.read()
    except FileNotFoundError:
        logging.error(f"Source file {CONFIG['OUTPUT_CSV_SUMMARY']} not found for Gist update.")
        return

    headers = {
        'Authorization': f'token {github_token}',
        'Accept': 'application/vnd.github.v3+json',
    }
    data = {
        'description': 'Cardano DRep Delegation Summary (Pool Reward Accounts)',
        'files': {
            CONFIG['GIST_FILENAME']: {'content': csv_content}
        }
    }
    url = f'https://api.github.com/gists/{gist_id}'

    for attempt in range(CONFIG['GIST_UPDATE_RETRIES']):
        logging.info(f"Attempting to update Gist (try {attempt + 1}/{CONFIG['GIST_UPDATE_RETRIES']})...")
        try:
            response = requests.patch(url, headers=headers, data=json.dumps(data), timeout=CONFIG['HTTP_TIMEOUT_POST'])
            response.raise_for_status() # Raises HTTPError for bad responses (4xx or 5xx)
            
            logging.info(f"✅ Gist updated successfully! URL: {response.json()['html_url']}")
            return # Success, exit the function
        except requests.RequestException as e:
            logging.warning(f"Gist update attempt {attempt + 1} failed: {e}")
            if attempt < CONFIG['GIST_UPDATE_RETRIES'] - 1:
                logging.info(f"Retrying in {CONFIG['GIST_UPDATE_RETRY_DELAY']} seconds...")
                time.sleep(CONFIG['GIST_UPDATE_RETRY_DELAY'])
            else:
                logging.error("All Gist update attempts failed.")

# --- Main Execution ----------------------------------------------------------
def main():
    """Main script execution flow."""
    parser = argparse.ArgumentParser(description="Fetch Cardano pool DRep delegations and update a GitHub Gist.")
    parser.add_argument(
        "--blockfrost-key",
        default=os.getenv("BLOCKFROST_PROJECT_ID"),
        help="Blockfrost project ID (or set BLOCKFROST_PROJECT_ID env var)"
    )
    args = parser.parse_args()

    # 1. Fetch Data
    pool_ids = get_all_pool_ids(args.blockfrost_key)
    if not pool_ids:
        logging.error("No pool IDs were found. Exiting.")
        return
    
    rows = fetch_pool_info_rows(pool_ids)
    if not rows:
        logging.error("Failed to fetch detailed pool info. Exiting.")
        return

    # 2. Process and Write Local Files
    write_csv_rows(
        rows,
        CONFIG['OUTPUT_CSV_FULL'],
        [
            "pool_id_bech32", "ticker", "reward_addr",
            "reward_addr_delegated_drep_raw", "reward_addr_delegated_drep_norm",
            "voting_power_lovelace", "voting_power_ADA"
        ]
    )
    summarize_and_write(rows)

    # 3. Publish to Gist
    update_github_gist_with_retries()

if __name__ == "__main__":
    main()
