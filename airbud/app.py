import os
import json
import logging
import requests

logging.getLogger()
logging.basicConfig(format='[%(levelname)s](%(asctime)s) %(message)s', datefmt='%m/%d/%Y-%I:%M:%S%p')
logging.getLogger().setLevel(logging.INFO)


AIRTABLE_BASE_ID = os.getenv('AIRTABLE_BASE_ID')
AIRTABLE_TABLE = os.getenv('AIRTABLE_TABLE')
AIRTABLE_API_URL = os.getenv('AIRTABLE_API_URL')
AIRTABLE_REQUEST_ENDPOINT = f"{AIRTABLE_API_URL}{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE}"
AIRTABLE_API_KEY = os.getenv('AIRTABLE_API_KEY')
AIRTABLE_API_HEADERS = {"Content-Type": "application/json", "Authorization": f"Bearer {AIRTABLE_API_KEY}"}
AIRTABLE_FIELDS = os.getenv('AIRTABLE_FIELDS').split(',')
AIRTABLE_FILTER = os.getenv('AIRTABLE_FILTER')
ZENCHETTE_API_URL = os.getenv('ZENCHETTE_API_URL')
ZENCHETTE_FIELDS = os.getenv('ZENCHETTE_FIELDS').split(',')

HTTP_SESSION = requests.Session()
def session_request(method, url, **kwargs):
    with HTTP_SESSION.request(method, url, **kwargs) as r:
        r.raise_for_status()
        return r.json()


class ZenchetteError(Exception):
    pass


def bool_to_yn(b):
    return "YES" if b else "NO"


def get_new_airtable_records():
    def record_request(url, params, offset=None):
        if offset:
            params.update({'offset': offset})
        return session_request('GET', url, params=params, headers=AIRTABLE_API_HEADERS) #request_session.get(url, params=params, headers=AIRTABLE_API_HEADERS)
    results = []
    params = {'fields[]': AIRTABLE_FIELDS, 'filterByFormula': AIRTABLE_FILTER}
    response = record_request(AIRTABLE_REQUEST_ENDPOINT, params)
    results.extend(response.get('records'))
    while response.get('offset') is not None:
        response = record_request(AIRTABLE_REQUEST_ENDPOINT, params, offset=response.get('offset'))
        results.extend(response.get('records'))
    return results


def get_zenchette_info(site):
    try:
        return session_request('GET', ZENCHETTE_API_URL, params={'website': site})
    except requests.exceptions.HTTPError as e:
        logging.exception(f"HTTPError: {e.response.text}")
        raise e


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
    try:
        updated_records = []
        failed_records = []
        new_records = get_new_airtable_records()
        logging.info(f"Beginning update of {len(new_records)} records")
        if not new_records:
            return {"statusCode": 200, "body": json.dumps({"message": "No new records!"})}
        for record in new_records:
            logging.info(f"{new_records.index(record)}/{len(new_records)} Getting update info for {record['id']} - {record['fields'].get('Site Name')}")
            try:
                site_info = get_zenchette_info(record['fields'].get('Site Name'))
                updates = zenchette_to_airtable(site_info)
                updated_record = update_airtable(record, updates)
                updated_records.append(updated_record['fields']['Site Name'])
                logging.info(f"Updated in Airtable: {json.dumps(updated_record)}")
            except ZenchetteError as e:
                failed_records.append(record['fields']['Site Name'])
                logging.error(f"ZenchetteError: update failed for {record['fields']['Site Name']}")
                continue
            except requests.exceptions.HTTPError as e:
                failed_records.append(record['fields']['Site Name'])
                logging.exception(e)
                continue
    except requests.RequestException as e:
        logging.exception(f"HTTP Error: {e.response.text}")
        raise e
    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "response_for": f"{attr(context,'aws_request_id')",
                "total_records_processed": len(new_records),
                "total_updated": len(updated_records),
                "updated_records": updated_records,
                "total_failed": len(failed_records),
                "failed_records": failed_records
            }
        ),
    }

if __name__ == "__main__":
    lambda_handler({'test':'test'},{'context': 'context'})