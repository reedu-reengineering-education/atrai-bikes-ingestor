import requests
import json
import logging
import time

PYGEOAPI_URL = "http://localhost:5000"
PROCESS_ID = "traffic_stops_detector"
SECRET_TOKEN = "token"


CAMPAIGN_IDs = [
    "muenster", 
    "wiesbaden", 
    "arnsberg", 
    "saopaulo", 
    "greifswald"
]

DEFAULT_PARAMS = {
    "maxDiameter": 50.0, 
    "minDuration": 2.0, 
    # "startDate": "2024-01-01 00:00:00", 
    # "endDate": "2025-11-30 23:59:59"
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def process_campaigns(campaign_id: str, box_ids: list): 
    """
    Constructs the input payload and sends a synchronous request to the pygeoapi process
    """
    logging.info(f"---Starting Analysis for Campaign: {campaign_id}---")

    payload = {
        "inputs": {
            "campaign": campaign_id, 
            "boxId": box_ids, 
            "token": SECRET_TOKEN
        }
    }

    # Merge default params into payload params
    payload["inputs"].update(DEFAULT_PARAMS)

    ## Remove 'boxId' from payload to filter by campaign!! 

    if campaign_id:
        del payload["inputs"]["boxId"]

    execute_url = f"{PYGEOAPI_URL}/processes/{PROCESS_ID}/execution"
    headers = {"Content-Type": "application/json"}

    # Send the POST request
    try: 
        response = requests.post(execute_url, headers=headers, data=json.dumps(payload))
        print(f"DEBUG: Status Code: {response.status_code}")
        print(f"DEBUG: Response Text: {response.text[:500]}") # DEBUG only first 500 characters
        response.raise_for_status()
        result = response.json()

        if 'message' in result: 
            logging.info(f"Campaign {campaign_id} SUCCESS: {result['message']}")
        else: 
            logging.info(f"Campaign {campaign_id} SUCCESS: Processes returned valid GeoJSON")
        return True
    
    except requests.exceptions.HTTPError as e: 
        error_response = response.json() if response.content else {"error":str(e)}
        logging.error(f"Campaign {campaign_id} FAILED (HTTP Error {response.status_code}): {error_response.get('description', 'Unknown Error')}")

    except requests.exceptions.RequestException as e: 
        logging.error(f"Campaign {campaign_id} FAILED (Connection Error): {e}")
        return False

def main(): 
    """
    Main batch exectuion loop
    """

    # Assume dummy list of box ids, which will be looked up by the load_bike_data function in Atrai Processor 

    dummy_box_ids = ["dummy_id"]

    for campaign_id in CAMPAIGN_IDs: 
        success = process_campaigns(campaign_id, dummy_box_ids)
        if success: 
            time.sleep(1) # Wait before starting next campaign 
        else: 
            logging.warning(f"Skipping rest of the batch due to critical failture in {campaign_id}")
            break

if __name__ == "__main__": 
    main()
