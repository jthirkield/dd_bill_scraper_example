########################SCRAPING LOGIC##############################

#########IMPORTS#########
import os
import sys
import json
import hashlib
import time
import datetime
import traceback
import requests
from bs4 import BeautifulSoup
import re

##IMPORTING DATA EXTRACTION FUNCTION
from parse_data import extract_data_points
#########STEP ONE#########
#check for data history

#ABSOLUTE PATH TO GITHUB DIRECTORY
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# MAKING ABSOLUTE PATHS TO DATA FILE & CHANGE/ERROR LOGS
DATA_FILE = os.path.join(BASE_DIR, "data", "pa_senate_bills.json")
CHANGELOG_DIR = os.path.join(BASE_DIR, "data", "changelogs")
ERROR_LOG_DIR = os.path.join(BASE_DIR, "data", "error_logs")

# CHECKING / BUILDING DIRECTORIES
os.makedirs(CHANGELOG_DIR, exist_ok=True)
os.makedirs(ERROR_LOG_DIR, exist_ok=True)
os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
TODAY_STR = datetime.date.today().isoformat()


if os.path.exists(DATA_FILE):
    print("Found existing dataset. Loading history...")
    with open(DATA_FILE, 'r') as f:
        yesterdays_list = json.load(f)
    # Map by URL for instant lookup
    old_data_map = {item['url']: item for item in yesterdays_list}
else:
    print("No existing dataset found. Initializing a baseline run...")
    old_data_map = {} # Empty map forces EVERYTHING to be treated as a new entry


#########STEP TWO#########
#Set up Change Log and Error Log

changelog = {
    "date": TODAY_STR,
    "additions": [],
    "deletions": [],
    "modifications": []
}
error_log = {
    "date": TODAY_STR,
    "errors": []
}


#########STEP THREE#########
#scrap contents page get the current contents

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive"
}

url = "https://www.palegis.us/legislation/bills/bill-index?display=index&sessYr=2025&sessInd=0&billBody=S&filter=bills"
raw_html = requests.get(url,headers=HEADERS, timeout=15).content
contents_doc = BeautifulSoup(raw_html, "html.parser")
bill_container = contents_doc.h3.parent.parent
all_bill_links = bill_container.find_all('a')
all_bill_urls = ["https://www.palegis.us/"+item['href'] for item in all_bill_links]


#####CHECK FOR DELETED ITEMS
for url, old_item in old_data_map.items():
    if url not in all_bill_urls:
        changelog["deletions"].append({
            "bill_id": old_item["bill_id"],
            "url": url,
            "title": old_item.get("title")
        })


#########STEP FOUR#########
#checking/scraping the bill pages

todays_bills = []
for link in all_bill_links[:6]:
    time.sleep(1)
    url = "https://www.palegis.us/"+link['href']
    yesterdays_item = old_data_map.get(url)
    try:
        raw_html = requests.get(url,headers=head).content
        bill_page = BeautifulSoup(raw_html, "html.parser")
        ###setting up hash for change detection
        history_table=bill_page.find(string=re.compile("View Full History")).parent.parent.find_next_sibling('div').table
        last_action=bill_page.find(string=re.compile("Last Action")).parent.parent.text.strip()
        hash_string =" ".join(last_action.split())+" ".join(history_table.text.split())[-50:]
        hash_id=hashlib.md5(hash_string.lower().encode('utf-8')).hexdigest()
        #IF THIS IS A NEW LINK--JUST GET EVERYTHING
        if url not in old_data_map:
            ###SEND THE CONTENT AND KEY DATA POINTS TO THE FUNCTION
            print("new entry: " + url)
            bill_dict=extract_data_points(bill_page,url,hash_id,link.text)
            todays_bills.append(bill_dict)
            changelog["additions"].append({"bill_id": link.text, "url": url, "action": bill_dict["last_action"]})
        else:
            yesterdays_hash = yesterdays_item['content_hash']
            #CHECK HASHES FOR CHANGE
            if yesterdays_hash == hash_id:
                print("no change: "+ url)
                todays_bills.append(yesterdays_item)
            else:
                print("changed entry: "+ url) #there are changes
                bill_dict=extract_data_points(bill_page,url,hash_id,link.text)
                todays_bills.append(bill_dict)
                meaningful_changes = {}
                for key, value in bill_dict.items():
                    if yesterdays_item.get(key) != value:
                        meaningful_changes[key] = {"from": yesterdays_item.get(key), "to": value}
                if meaningful_changes:
                    changelog["modifications"].append({"bill_id": link.text, "changes": meaningful_changes})
    except Exception as e:
        print(f"❌ Error scraping {url}: {str(e)}")
        if yesterdays_item:
            todays_bills.append(yesterdays_item)
        error_log["errors"].append({
            "bill_id": link.text,
            "url": "https://www.palegis.us/"+link['href'],
            "error_type": type(e).__name__,
            "message": str(e),
            "traceback": traceback.format_exc().splitlines()[-3:] # Keeps log clean by grabbing last few lines of trace
        })

#########STEP FIVE#########
#write files
with open(DATA_FILE, 'w') as f:
    # Sorting by 'id' ensures Git diffs stay perfectly clean and predictable
    sorted_data = sorted(todays_bills, key=lambda x: x['bill_id'])
    json.dump(sorted_data, f, indent=2)
if changelog["additions"] or changelog["deletions"] or changelog["modifications"]:
    with open(f"data/changelogs/{TODAY_STR}.json", 'w') as f:
        json.dump(changelog, f, indent=2)

# 3. Write Daily Error Log (Only write if errors occurred)
if error_log["errors"]:
    with open(f"data/error_logs/{TODAY_STR}.json", 'w') as f:
        json.dump(error_log, f, indent=2)
        
print("Scrape done!")
