import os
import json
import urllib
import requests

AIRTABLE_TABLE = os.getenv('AIRTABLE_TABLE')
AIRTABLE_API_URL = os.getenv('AIRTABLE_API_URL')
AIRTABLE_API_KEY = os.getenv('AIRTABLE_API_KEY')
AIRTABLE_API_HEADERS = {"Content-Type": "application/json", "Authorization": f"Bearer {AIRTABLE_API_KEY}"}
AIRTABLE_FIELDS = ["Site", "Status", "Start Date", "Client Name", "Site Live", "Facebook Tool", "Seller Lead Tool", "FB Managed", "PPC"]
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
    req_url = urllib.parse.urljoin(AIRTABLE_API_URL, AIRTABLE_TABLE)
    params = {'fields[]': AIRTABLE_FIELDS, 'filterByFormula': AIRTABLE_FILTER}
    ses = requests.Session()
    response = record_request(ses, req_url, params)
    results.extend(response.get('records'))
    while response.get('offset') is not None:
        response = record_request(ses, req_url, params, offset=response.get('offset'))
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
    url = urllib.parse.urljoin(AIRTABLE_API_URL, AIRTABLE_TABLE+f"/{record.get('id')}")
    data = {'fields': updates}
    r = requests.patch(url, headers=AIRTABLE_API_HEADERS, data=json.dumps(data))
    if r.status_code != requests.codes.get('ok'):
        raise r.raise_for_status()
    return r.json()


def lambda_handler(event, context):
    """Sample pure Lambda function

    Parameters
    ----------
    event: dict, required
        API Gateway Lambda Proxy Input Format

        {
            "resource": "Resource path",
            "path": "Path parameter",
            "httpMethod": "Incoming request's method name"
            "headers": {Incoming request headers}
            "queryStringParameters": {query string parameters }
            "pathParameters":  {path parameters}
            "stageVariables": {Applicable stage variables}
            "requestContext": {Request context, including authorizer-returned key-value pairs}
            "body": "A JSON string of the request payload."
            "isBase64Encoded": "A boolean flag to indicate if the applicable request payload is Base64-encode"
        }

        https://docs.aws.amazon.com/apigateway/latest/developerguide/set-up-lambda-proxy-integrations.html#api-gateway-simple-proxy-for-lambda-input-format

    context: object, required
        Lambda Context runtime methods and attributes

    Attributes
    ----------

    context.aws_request_id: str
         Lambda request ID
    context.client_context: object
         Additional context when invoked through AWS Mobile SDK
    context.function_name: str
         Lambda function name
    context.function_version: str
         Function version identifier
    context.get_remaining_time_in_millis: function
         Time in milliseconds before function times out
    context.identity:
         Cognito identity provider context when invoked through AWS Mobile SDK
    context.invoked_function_arn: str
         Function ARN
    context.log_group_name: str
         Cloudwatch Log group name
    context.log_stream_name: str
         Cloudwatch Log stream name
    context.memory_limit_in_mb: int
        Function memory

        https://docs.aws.amazon.com/lambda/latest/dg/python-context-object.html

    Returns
    ------
    API Gateway Lambda Proxy Output Format: dict
        'statusCode' and 'body' are required

        {
            "isBase64Encoded": true | false,
            "statusCode": httpStatusCode,
            "headers": {"headerName": "headerValue", ...},
            "body": "..."
        }

        # api-gateway-simple-proxy-for-lambda-output-format
        https: // docs.aws.amazon.com/apigateway/latest/developerguide/set-up-lambda-proxy-integrations.html
    """
    try:
        new_records = get_new_airtable_records()
        if not new_records:
            return {
                "statusCode": 200,
                "body": json.dumps(
                    {"message": "No New Records In AirTable!", "records": []}
                ),
            }
        for record in new_records:
            try:
                print(f"Updating record {record['id']}: {record['fields'].get('Site')}")
                site_info = get_zenchette_info(record['fields'].get('Site'))
                updates = zenchette_to_airtable(site_info)
                print(f"\t\tupdates: {json.dumps(updates)}")
                update_airtable(record, updates)
            except ZenchetteError:
                continue
    except requests.RequestException as e:
        # Send some context about this error to Lambda Logs
        print(e)
        raise e


    return {
        "statusCode": 200,
        "body": json.dumps(
            {"message": "hello world", "records": json.dumps(new_records)}
        ),
    }
