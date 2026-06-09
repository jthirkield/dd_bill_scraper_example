########################SCRAPING LOGIC##############################

#########IMPORTS#########
import os
import sys
import json
import hashlib
import time
from datetime import date, timedelta
import traceback
import requests
from urllib.parse import urlencode
from bs4 import BeautifulSoup
import re

##IMPORTING DATA EXTRACTION FUNCTION
from parse_data import extract_data_points
from parse_data import get_bill_text

#########STEP ONE#########
#check for data history
api_key=os.environ.get("SCRAPOPS_API_KEY")

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
TODAY_STR = date.today().isoformat()

master_list=[]
if os.path.exists(DATA_FILE):
    print("Found existing dataset. Loading history...")
    with open(DATA_FILE, 'r') as f:
        master_list = json.load(f)
    # Map by URL for instant lookup
    old_data_map = {item['url']: item for item in master_list}
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
#scrape contents page get the current contents

yesterday = date.today() #- timedelta(days=1)

# Format without leading zeros using f-strings
formatted_date = f"{yesterday.year}-{yesterday.month}-{yesterday.day}"

#build url with yesterday's date
new_bills = f"https://www.palegis.us/legislation/bills/search-results?sessYr=2025&sessInd=0&actionDate={formatted_date}&actionChamber=S&action=INTRO"
updated_bills = f"https://www.palegis.us/legislation/bills/search-results?sessYr=2025&sessInd=0&actionDate={formatted_date}&actionChamber=S&action=ACTIONS"
contents_links = [new_bills, updated_bills]
todays_bills = []

HEAD = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
}


proxy_params = {
      'api_key': api_key,
      'url': 'https://www.palegis.us/legislation/bills/bill-index?display=index&sessYr=2025&sessInd=0&billBody=S&filter=bills', 
  }

response = requests.get(
    url='https://proxy.scrapeops.io/v1/',
    headers=HEAD,
    params=urlencode(proxy_params),
    timeout=120,
)



all_bill_links=[]
########GET THE UPDATED CONTENTS#########
########LOOPS THROUGH THE UPDATED AND NEW BILLS LINKS ##############
########CHECKS FOR PAGINATION AND LOOPS THROUGH PAGES ###############
for link in contents_links:
    time.sleep(1)
    proxy_params = {'api_key': api_key,'url': link}
    response = requests.get(url='https://proxy.scrapeops.io/v1/',headers=HEAD,params=urlencode(proxy_params),timeout=120)
    raw_html = response.content
    link_doc = BeautifulSoup(raw_html, "html.parser")
    all_docs = link_doc.find_all(class_="resultRow")
    for doc in all_docs:
        if 'SB' in doc.a.text:
            all_bill_links.append(doc.a)
    if link_doc.find('ul', class_="pagination"):
        pg_string=link_doc.find('ul', class_="pagination").text.split("Nav")[0]
        num_pages=re.findall(r'\d+', pg_string)
        for num in range(2,int(num_pages[-1])+1):
            time.sleep(1)
            page_link = link + "&pagenumber="+str(num)
            raw_html = requests.get(page_link,headers=HEAD).content
            link_doc = BeautifulSoup(raw_html, "html.parser")
            all_docs = link_doc.find_all(class_="resultRow")
            for doc in all_docs:
                if 'SB' in doc.a.text:
                    all_bill_links.append(doc.a) 


#########STEP FOUR#########
#checking/scraping the bill pages

for link in all_bill_links[:5]:#EXAMPLE CURRENTLY JUST SCRAPE THE FIRST 3 PAGES
    url = "https://www.palegis.us"+link['href']
    yesterdays_item = old_data_map.get(url)
    time.sleep(1)
    try:
        proxy_params = {'api_key': api_key, 'url': url}
        response = requests.get(url='https://proxy.scrapeops.io/v1/', headers=HEAD, params=urlencode(proxy_params), timeout=120)
        raw_html = response.content
        bill_page = BeautifulSoup(raw_html, "html.parser")
        history_table=bill_page.find(string=re.compile("View Full History")).parent.parent.find_next_sibling('div').table
        last_action=bill_page.find(string=re.compile("Last Action")).parent.parent.text.strip()
        hash_string =" ".join(last_action.split())+" ".join(history_table.text.split())[-50:]
        hash_id=hashlib.md5(hash_string.lower().encode('utf-8')).hexdigest()
        #IF THIS IS A NEW LINK--JUST GET EVERYTHING
        if url not in old_data_map:
            ###SEND THE CONTENT AND KEY DATA POINTS TO THE FUNCTION
            print("new entry: " + url)
            bill_dict=extract_data_points(bill_page,url,hash_id,link.text)
            bill_dict["bill_text"]=get_bill_text(bill_dict["actions"][0]["text_link"],HEAD)
            todays_bills.append(bill_dict)
            changelog["additions"].append({"bill_id": link.text, "url": url, "action": bill_dict["last_action"]})
        else:
            yesterdays_item = old_data_map[url]
            yesterdays_hash = yesterdays_item['content_hash']            
            #CHECK HASHES FOR CHANGE
            if yesterdays_hash == hash_id:
                print("no change: "+ url)
                todays_bills.append(yesterdays_item)
            else:
                print("changed entry: "+ url) #there are changes
                bill_dict=extract_data_points(bill_page,url,hash_id,link.text)
                bill_dict["bill_text"]=get_bill_text(bill_dict["actions"][0]["text_link"],HEAD)
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
            "url": "https://www.palegis.us"+link['href'],
            "error_type": type(e).__name__,
            "message": str(e),
            "traceback": traceback.format_exc().splitlines()[-3:] # Keeps log clean by grabbing last few lines of trace
        })

today = {bill['bill_id']: bill for bill in todays_bills}
old_data_map.update(today)

updated_list = list(old_data_map.values())
#########STEP FIVE#########
#write files
with open(DATA_FILE, 'w') as f:
    # Sorting by 'id' ensures Git diffs stay perfectly clean and predictable
    sorted_data = sorted(updated_list, key=lambda x: x['bill_id'])
    json.dump(sorted_data, f, indent=2)
if changelog["additions"] or changelog["deletions"] or changelog["modifications"]:
    with open(f"data/changelogs/{TODAY_STR}.json", 'w') as f:
        json.dump(changelog, f, indent=2)

# 3. Write Daily Error Log (Only write if errors occurred)
if error_log["errors"]:
    with open(f"data/error_logs/{TODAY_STR}.json", 'w') as f:
        json.dump(error_log, f, indent=2)
        
print("Scrape done!")
