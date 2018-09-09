import os
import json
import logging
import requests

AIRTABLE_BASE_ID = os.getenv('AIRTABLE_BASE_ID')
AIRTABLE_TABLE = os.getenv('AIRTABLE_TABLE')
AIRTABLE_API_URL = os.getenv('AIRTABLE_API_URL')
AIRTABLE_REQUEST_ENDPOINT = f"{AIRTABLE_API_URL}{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE}"
AIRTABLE_API_KEY = os.getenv('AIRTABLE_API_KEY')
AIRTABLE_API_HEADERS = {"Content-Type": "application/json", "Authorization": f"Bearer {AIRTABLE_API_KEY}"}
AIRTABLE_FIELDS = os.getenv('AIRTABLE_FIELDS').split(',')
AIRTABLE_FILTER = os.getenv('AIRTABLE_FILTER')
ZENCHETTE_API_URL = os.getenv('ZENCHETTE_API_URL')

class ZenchetteError(Exception):
    pass

def bool_to_yn(b):
    return "YES" if b else "NO"


def get_new_airtable_records():
    def record_request(session, url, params, offset=None):
        if offset:
            params.update({'offset': offset})
        res = session.get(url, params=params, headers=AIRTABLE_API_HEADERS)
        res.raise_for_status()
        return res.json()

    results = []
    params = {'fields[]': AIRTABLE_FIELDS, 'filterByFormula': AIRTABLE_FILTER}
    ses = requests.Session()
    response = record_request(ses, AIRTABLE_REQUEST_ENDPOINT, params)
    results.extend(response.get('records'))
    while response.get('offset') is not None:
        response = record_request(ses, AIRTABLE_REQUEST_ENDPOINT, params, offset=response.get('offset'))
        results.extend(response.get('records'))
    return results


def get_zenchette_info(site):
    zenchette_info = {}
    try:
        response = requests.get(ZENCHETTE_API_URL, params={'website': site})
        response.raise_for_status()
        zenchette_info = response.json()
    except requests.exceptions.HTTPError:
        pass
    return zenchette_info


def zenchette_to_airtable(site_info):
    if site_info == {} or 'error' in site_info:
        raise ZenchetteError
    return {
        'Seller Lead Tool': bool_to_yn(site_info.get('sellerToolEnabled')),
        "Site Live": bool_to_yn(site_info.get('live')),
        "Facebook Tool": bool_to_yn(site_info.get('fbToolEnabled')),
        "FB Managed": bool_to_yn(site_info.get('fbManagedClient')),
        "PPC": bool_to_yn(site_info.get('realLeadsClient')),
        "Start Date": site_info.get('companyStarted'),
        "CRM - DB Upload": bool_to_yn(not site_info.get('checkLeads'))
    }


def update_airtable(record, updates):
    url = AIRTABLE_REQUEST_ENDPOINT + f"/{record.get('id')}"
    data = {'fields': updates}
    r = requests.patch(url, headers=AIRTABLE_API_HEADERS, data=json.dumps(data))
    if r.status_code != requests.codes.get('ok'):
        raise r.raise_for_status()
    return r.json()


def lambda_handler(event, context):
    """Sample pure Lambda function"""
    new_records = []
    try:
        new_records = get_new_airtable_records()
        logging.info(f"Beginning update of {len(new_records)} records")
        if not new_records:
            return {
                "statusCode": 200,
                "body": json.dumps({"message": "No New Records In AirTable!"}),
            }
        for record in new_records:
            logging.info(f"{new_records.index(record)}/{len(new_records)} Getting update info for {record['id']} - {record['fields'].get('Site Name')}")
            try:
                site_info = get_zenchette_info(record['fields'].get('Site Name'))
                updates = zenchette_to_airtable(site_info)
                updated_record = update_airtable(record, updates)
                logging.info(f"Updated in Airtable: {json.dumps(updated_record)}")
            except ZenchetteError as e:
                logging.error(f"Unable to get zenchette info for {record['fields']['Site Name']} ({record['id']})")
                continue
    except requests.RequestException as e:
        # Send some context about this error to Lambda Logs
        logging.error(f"HTTP Error: {e.response.text}")
        raise e
    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "response_for": f"{context.aws_request_id}",
                "total_records_processed": len(new_records),
                "updated_records": [r['fields']['Site Name'] for r in new_records]
            }
        ),
    }
