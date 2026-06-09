########################SCRAPING FUNCTION########################
#all the extraction of values from eah page happens here
################################################################
import re
from bs4 import BeautifulSoup
import requests
import os
from urllib.parse import urlencode

api_key=os.environ.get("SCRAPOPS_API_KEY")

def extract_data_points(bill_page,url,hash_id,bill_id):
    fields = {}
    fields["content_hash"]=hash_id
    fields["url"]=url
    fields["bill_id"]=bill_id
    fields["bill_name"]=bill_page.find(class_='h1 header-title').text.strip()
    fields["short_des"]=bill_page.find(id="shortTitle-wrapper").text.strip()
    if bill_page.find(class_="col-12 ps-2"):
        fields["memo_name"]=bill_page.find(class_="col-12 ps-2").text.strip()
        fields["memo_link"]=bill_page.find(class_="col-12 ps-2").a['href']
    prime_container = bill_page.find(string="Prime Sponsor").parent.find_next_sibling('div')
    fields["prime_sponsor"]={
        "name": prime_container.strong.text.strip(),
        "party": prime_container.span.text.strip(),
        "district": prime_container.span.next_sibling.strip(),
    }
    if bill_page.find(string="Co-Sponsors"):
        co_sponsors=bill_page.find(string="Co-Sponsors").parent.find_next_sibling('div')
        all_cosp=co_sponsors.find_all(class_=re.compile("^col"))
        fields["cosponsors"]=[]
        for cosp in all_cosp:
            each_cosp= {
            "name": cosp.strong.text.strip(),
            "party": cosp.span.text.strip(),
            "district": cosp.span.next_sibling.strip()
            }
            fields["cosponsors"].append(each_cosp)
    last_action=bill_page.find(string=re.compile("Last Action")).parent.parent.text.strip()
    fields["last_action"]=" ".join(last_action.split())
    timeline=bill_page.find(class_=re.compile("timeline"))
    all_items = timeline.find_all('span')
    time_dict = {}
    for item in all_items:
        item_html = BeautifulSoup(item['title'], "html.parser")
        time_elements = item_html.find_all(string=True)
        time_key = time_elements.pop(0)
        time_dict[time_key] = time_elements
    fields["timeline"] =time_dict
    history_table=bill_page.find(string=re.compile("View Full History")).parent.parent.find_next_sibling('div').table
    actions_list = []
    for row in history_table.find_all('tr'):
        actions_dict = {}
        actions_dict['action']=row.text.strip()
        if row.td.a:
            actions_dict['doc']=row.td.a['aria-label']
            actions_dict['pdf_link']=row.td.a['href']
            actions_dict['text_link']="https://www.palegis.us" + row.td.a['href'].replace("text/PDF/","text/HTM/")
            # actions_dict['text_link']=row.td.a['href']
        actions_list.append(actions_dict)
    fields["actions"]=actions_list
    main_votes=bill_page.find(id="VotesSection").find_next_sibling('div').find_all(class_="card-body")
    fields["votes"] = []
    for vote in main_votes:
        vt={}
        vt['date']=vote.find(class_=re.compile("^h5")).text
        vt['type']=vote.find(class_=re.compile("^h6")).text
        vt['bill']=vote.find(class_=re.compile("^mb-3")).text
        vt['link']=vote.a['href']
        vote_tally=vote.find_all(class_=re.compile("^fa-solid"))
        for item in vote_tally:
            vt[item.find_next_siblings('span')[1].text]=item.find_next_siblings('span')[0].text
        fields["votes"].append(vt)
    if bill_page.find(id="billVotes"):
        add_votes=bill_page.find(id="billVotes").table.find_all('tr')
        for vote in add_votes:
            vt={}
            date_type=vote.find(class_=re.compile("^h6")).text
            vt['date']=date_type.split("-")[0].strip()
            vt['type']=date_type.split("-")[1].strip()
            vt['bill']=vote.a.text
            vt['link']=vote.a['href']
            vt['YES Votes']=vote.find(class_=re.compile("fa-square-check")).parent.text
            vt['NO Votes']=vote.find(class_=re.compile("fa-square-xmark")).parent.text
            fields["votes"].append(vt)
    return fields

def get_bill_text(text_url,head):
    print(text_url)
    proxy_params = {'api_key': api_key,'url': text_url}
    response = requests.get(url='https://proxy.scrapeops.io/v1/',headers=HEAD,params=urlencode(proxy_params),timeout=120)
    bill_html = response.content
    bill_doc = BeautifulSoup(bill_html, "html.parser")
    return bill_doc.find(id="page-container").text
