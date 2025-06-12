import json
import requests
import boto3
import re
import base64
from datetime import datetime
import jwt

#Function to fetch secrets from secrets manager
def get_secrets(secret_names, region_name="us-east-1"):
    secrets = {}
    
    #Init boto client
    client = boto3.client(
        service_name='secretsmanager',
        region_name=region_name
    )
    
    #Iterate through each secret to retrieve requested secrets
    for secret_name in secret_names:
        try:
            get_secret_value_response = client.get_secret_value(SecretId=secret_name)
        except Exception as e:
            #If secret retrieval fails, stop execution and raise error
            raise e
        else:
            #Check if secret is stored as string or as binary, handle accordingly
            if 'SecretString' in get_secret_value_response:
                secrets[secret_name] = get_secret_value_response['SecretString']
            else:
                secrets[secret_name] = base64.b64decode(get_secret_value_response['SecretBinary'])

    return secrets

#Helper function to parse JSON strings from secrets
def extract_secret_value(data):
    if isinstance(data, str):
        return json.loads(data)
    return data
    
#Function to get Oauth token for Teams API auth
def get_token(bot_client_id, bot_client_secret):
    response = requests.post(
        "https://login.microsoftonline.com/botframework.com/oauth2/v2.0/token",
        data={
            'grant_type': 'client_credentials',
            'client_id': bot_client_id,
            'client_secret': bot_client_secret,
            'scope': 'https://api.botframework.com/.default'
        }
    )
    
    #Check if the request was successful
    if response.status_code == 200:
        #Extract access token
        return response.json()['access_token']
    else:
        #Log auth error
        print(f"Token error: {response.text}")
        return None

#Function to send messages back to teams using microsoft bot frammework api
def send_to_teams(original_activity, message, bot_client_id, bot_client_secret):
    #Fetch Oauth token
    token = get_token(bot_client_id, bot_client_secret)
    
    #Exit if we can't get the auth token, log error
    if not token:
        print("Failed to get token")
        return
    
    #Build teams api url using conversation details from original message
    url = f"{original_activity['serviceUrl']}v3/conversations/{original_activity['conversation']['id']}/activities"
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    
    #Init headers with auth token
    response = requests.post(url, headers=headers, json={
        'type': 'message',
        'text': message
    })
    
    #Check if the request was successful
    if response.status_code != 201:
        #Log error if request fails
        print(f"Teams API error: {response.text}")
        
        
#In memory storage for user conversations
pending_requests = {}
original_requests = {}

#Function to store user's HubSpot parameters while waiting for confirmation
def store_request(user_id, hubspot_params):
    pending_requests[user_id] = hubspot_params

#Function to retrieve stored HubSpot parameters for a user
def get_request(user_id):
    return pending_requests.get(user_id)
    
#Function to store original user message for clarifications
def store_original_request(user_id, original_message):
    original_requests[user_id] = original_message

#Function to get original user message for combining with clarifications
def get_original_request(user_id):
    return original_requests.get(user_id)

#Function to clear all stored data for a user after completion or cancellation
def clear_request(user_id):
    pending_requests.pop(user_id, None)
    original_requests.pop(user_id, None)
    
#Function to translate natural language into HubSpot API parameters using Claude
def translate_and_explain(user_message):
    #Log entry point
    print(f"Entering translate_and_explain with: '{user_message}'")
    
    #Generate unique timestamp to ensure list names don't conflict
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    try:
        #Create AWS Bedrock client to access Claude
        print("Creating bedrock client...")
        bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
        print("SUCCESS: Bedrock client created")
        
        #Build detailed prompt with HubSpot field mappings and examples
        print("Creating prompt...")
        prompt = f"""User wants to create a HubSpot contact list. They said: "{user_message}"
        
        Create the HubSpot API parameters and explain what list you'll create.
        
        Respond with this EXACT format:
        
        EXPLANATION: [Plain English explanation of what list will be created]
        
        HUBSPOT_JSON:
        {{
      "name": "[Generate appropriate name based on user request]",
      "objectTypeId": "0-1",
      "processingType": "DYNAMIC",
      "filterBranch": {{
        "filterBranchType": "OR",
        "filters": [],
        "filterBranches": [
        {{
        "filterBranchType": "AND",
        "filters": [
        {{
        "filterType": "PROPERTY",
        "property": "primary_location",
        "operation": {{
          "operationType": "ENUMERATION",
          "operator": "IS_ANY_OF",
          "values": ["[STATE_ABBREVIATION]"]
        }}
         }},
         {{
        "filterType": "PROPERTY",
        "property": "record_type",
        "operation": {{
      "operationType": "ENUMERATION",
      "operator": "IS_ANY_OF",
      "values": ["[APPROPRIATE_RECORD_TYPE_VALUES]"]
            }}
          }},
          {{
            "filterType": "PROPERTY",
            "property": "census_range",
            "operation": {{
              "operationType": "ENUMERATION",
              "operator": "IS_ANY_OF",
              "values": ["[APPROPRIATE_SIZE_VALUES]"]
            }}
          }},
          {{
            "filterType": "PROPERTY",
            "property": "job_function",
            "operation": {{
              "operationType": "ENUMERATION",
              "operator": "IS_ANY_OF",
              "values": ["[APPROPRIATE ROLE VALUES]"]
            }}
          }},
          {{
            "filterType": "PROPERTY",
            "property": "hhax_platform_tags",
            "operation": {{
              "operationType": "MULTISTRING",
              "operator": "[APPROPRIATE_OPERATOR_VALUES]",
              "includeObjectsWithNoValueSet": False,
              "values": ["[APPROPRIATE_PLATFORM_TAG_VALUES]"]
                    }}
                  }},
        {{"listId": "[APPROPRIATE EXCLUSION LISTID]", "operator": "[APPROPRIATE OPERATOR]", "filterType": "IN_LIST",
     "filterBranchOperator": "AND",
     "filterBranchType": "AND",
      "filters": [],
      "filterBranchOperator": "OR",
   "filterBranchType": "OR"}}
        ]
              }},
              {{
                "filterBranchType": "AND",
                "filters": [
                  {{
                    "filterType": "PROPERTY",
                    "property": "primary_location",
                    "operation": {{
                      "operationType": "ENUMERATION",
                      "operator": "IS_ANY_OF",
                      "values": ["[STATE_ABBREVIATION]"]
                    }}
                  }},
                  {{
                    "filterType": "PROPERTY",
                    "property": "record_type",
                    "operation": {{
                      "operationType": "ENUMERATION",
                      "operator": "IS_ANY_OF",
                      "values": ["[APPROPRIATE_RECORD_TYPE_VALUES]"]
                    }}
                  }},
                  {{
                    "filterType": "PROPERTY",
                    "property": "census_range",
                    "operation": {{
                      "operationType": "ENUMERATION",
                      "operator": "IS_ANY_OF",
                      "values": ["[APPROPRIATE_SIZE_VALUES]"]
                    }}
                  }},
                  {{
                    "filterType": "PROPERTY",
                    "property": "jobtitle",
                    "operation": {{
                      "operationType": "MULTISTRING",
                      "operator": "CONTAINS",
                      "values": ["[APPROPRIATE TITLE KEYWORDS]"]
                    }}
                  }},
                  {{
                    "filterType": "PROPERTY",
                    "property": "hhax_platform_tags",
                    "operation": {{
                      "operationType": "MULTISTRING",
                      "operator": "[APPROPRIATE_OPERATOR_VALUES]",
                      "includeObjectsWithNoValueSet": False,
                      "values": ["[APPROPRIATE_PLATFORM_TAG_VALUES]"]
                    }}
                  }},
                   {{"listId": "[APPROPRIATE EXCLUSION LISTID]", "operator": "[APPROPRIATE OPERATOR]", "filterType": "IN_LIST",
     "filterBranchOperator": "AND",
     "filterBranchType": "AND",
      "filters": [],
      "filterBranchOperator": "OR",
   "filterBranchType": "OR"}}
                ]
              }}
            ]
          }}
        }}
        
        Field mappings for "{user_message}":
        - location/state → "primary_location" (use 2-letter state code) -- when more than one state included in the request, both states must be included in a single filter group (i.e. any of NY,VA)
        - provider/contacts → always include "record_type" values ["0120Z000001NZwvQAG", "01231000001NZXjAAO"]
        - smb/small medium business, smb segment → "census_range" values: ["0-50","1-25","50-100","26-50","51-125","Small (0-99)","0","1-50","51-100"]
        - mm/mid , midmarket segment → "census_range" values: ["100-250","126-250","101-200","101-149","101-350"]
        - enterprise, ent, enterprise segment contacts → "census_range" values: ["1000+","500+","500-1000","350-500","501-1000","1001+"]
        
    
        - IMPORTANT NOTE TO CLAUDE: WHEN USER ASKS TO FILTER ON TITLE, ROLE, JOB ROLE - BOTH OF THESE FIELDS MUST ALWAYS BE INCLUDED IN THE JSON, COVERING ALL COMBINATIONS (if request
        has two state requests and requires a split into filter groups, all of these fields need to be covered always, its or logic with these two fields. DO NOT INCLUDE THESE FIELDS IF USER DOES NOT MENTION IN REQUEST, THERE IS ALSO NO NEED TO CLARIFY IN RESPONSE TO USER.

            - job role, role, title -- admins, administrator -> job_function value: ["Administrator"] (this is a picklist)
            - job role, role, title -- admin  -> jobtitle value: ["Admin"] (this is a contains, see json above for structure)

            - job role, role, title -- owner, ceo, president -> job_function value: ["Owner/President/CEO","Owner"] (this is a picklist)
            - job role, role, title -- owner  -> jobtitle value: ["Owner"] (this is a contains, see json above for structure)

            - job role, role, title -- billing, finance, biller, accounting -> job_function value: ["Billing/Finance","Billing-Finance"] (this is a picklist)
            - job role, role, title -- billing  -> jobtitle value: ["Finance"] (this is a contains, see json above for structure)
            
            - job role, role, title -- hr, human resources -> job_function value: ["HR"] (this is a picklist)
            - job role, role, title -- hr  -> jobtitle value: ["HR"] (this is a contains, see json above for structure)
            
        - exclude/include caregiver contacts -> appropriate listId value :["974"] -> operator for include ["IN_LIST"] operator for exclude ["NOT_IN_LIST"] - USE THE SPECIFIC LISTID JSON FILTER STRUCTURE
        - exclude/include contacts on marketing exclusion list -> appropriate listId value :["3259"] -> operator for include ["IN_LIST"] operator for exclude ["NOT_IN_LIST"] - USE THE SPECIFIC LISTID JSON FILTER STRUCTURE
        - exclude/include contacts on customer experience, cx exclusion list -> appropriate listId value :["19163"] -> operator for include ["IN_LIST"] operator for exclude ["NOT_IN_LIST"] - USE THE SPECIFIC LISTID JSON FILTER STRUCTURE
        
        - exclude/include paid contacts or providers -> hhax_platform_tags values: ["Enterprise","Enterprise-Core,"Enterprise-EVV Starter"] -> operator for include ["IS_EQUAL_TO"] operator for exclude ["IS_NOT_EQUAL_TO"]
        - exclude/include free, portal, hhax portal, sponsored contacts or providers -> hhax_platform_tags values: ["Enterprise-NY Portal","Portal-Homecare","Portal-Homecare(SCE)","Enterprise-Free"] -> operator for include ["IS_EQUAL_TO"] operator for exclude ["IS_NOT_EQUAL_TO"]
        
        Replace placeholders with actual values based on: "{user_message}"
        Include the timestamp {timestamp} at the end of the name to ensure uniqueness.
        
        NOTE: NOT ALL FIELD MAPPINGS SHOULD BE INCLUDED IN EVERY REQUEST, ASSESS WHAT IS NEEDED BASED ON THE NATURAL LANGUAGE PROCESSED FROM THE USER MESSAGES
        """
        #Log prompt creation success and length
        print(f"SUCCESS: Prompt created (length: {len(prompt)})")
        
        print("Call bedrock.invoke_model...")
        
        #Prepare request payload for Claude
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 10000,
            "messages": [{"role": "user", "content": prompt}]
        }
        print(f"Request body created")
        
        #Convert request to JSON string for API call
        serialized_body = json.dumps(request_body)
        print(f"Body serialized (length: {len(serialized_body)})")
        
        #Call Claude via Bedrock
        print("Making actual Bedrock call...")
        response = bedrock.invoke_model(
            modelId="arn:aws:bedrock:us-east-1:995177893317:inference-profile/us.anthropic.claude-3-5-sonnet-20240620-v1:0",
            contentType="application/json",
            accept="application/json",
            body=serialized_body
        )
        print("SUCCESS: Bedrock call completed")
        
        #Parse Claude's response from bedrock
        print("Reading response...")
        response_body = json.loads(response['body'].read())
        print("SUCCESS: Response parsed")
        
        #Extract token usage information for monitoring
        usage = response_body.get('usage', {})
        print(f"Token usage: input={usage.get('input_tokens', 'unknown')}, output={usage.get('output_tokens', 'unknown')}")
        print(f"Stop reason: {response_body.get('stop_reason', 'unknown')}")
        
        #Check if Claude hit token limits or finished naturally
        if response_body.get('stop_reason') == 'max_tokens':
            print("Hitting max tokens - consider shortening prompt further")
        elif response_body.get('stop_reason') == 'stop_sequence':
            print("Claude finished naturally")
        
        #Validate Claude's response structure
        print("Extracting content...")
        
        if 'content' not in response_body:
            print("No 'content' key in response")
            return None, None
        
        if not response_body['content']:
            print("Content array is empty")
            return None, None
        
        if len(response_body['content']) == 0:
            print("Content array has no items")
            return None, None
        
        #Extract the actual text response from Claude
        claude_output = response_body['content'][0]['text']
        print(f"SUCCESS: Content extracted (length: {len(claude_output)})")
        
        #Use regex to parse explanation and JSON from Claude's response
        print("Extracting explanation and JSON...")
        explanation_match = re.search(r'EXPLANATION:\s*(.+?)(?=HUBSPOT_JSON:)', claude_output, re.DOTALL)
        json_match = re.search(r'HUBSPOT_JSON:\s*({.*})', claude_output, re.DOTALL)
        
        #Check if we successfully found both explanation and JSON
        if explanation_match and json_match:
            #Extract the explanation text
            explanation = explanation_match.group(1).strip()
            
            #Extract and clean the JSON string
            json_str = json_match.group(1).strip()
            print(f"JSON string to parse: {json_str}")
            
            try:
                #Parse JSON string into dictionary
                hubspot_params = json.loads(json_str)
                print(f"Extracted explanation: {explanation}")
                print(f"Extracted JSON: {json.dumps(hubspot_params, indent=2)}")
                #Return both explanation and HubSpot parameters
                return explanation, hubspot_params
            #Log JSON parsing errors
            except json.JSONDecodeError as e:
                print(f"JSON parsing error: {e}")
                return None, None
        else:
            #Log if fail to extract required parts from Claude's response
            print("Failed to extract explanation or JSON from Claude output")
            return None, None
        
    #Log any unexpected errors in the translation process
    except Exception as e:
        print(f"EXCEPTION in translate_and_explain: {e}")
        import traceback
        traceback.print_exc()
        return None, None
        
#Function to create HubSpot list by calling HubSpot API directly
def create_hubspot_list(hubspot_params):
    try:
        #Get secrets
        secrets = ['hs_api_key']
        fetch_secrets = get_secrets(secrets)
        extracted_secrets = {key: extract_secret_value(value) for key, value in fetch_secrets.items()}
        access_token = extracted_secrets['hs_api_key']['hs_api_key']
        
        #HubSpot API call
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        url = "https://api.hubapi.com/crm/v3/lists"
        
        response = requests.post(url, headers=headers, json=hubspot_params)
        
        if response.status_code in [200, 201]:
            result = response.json()
            
            #Extract list details from the correct response structure
            list_data = result.get('list', {})
            list_id = list_data.get('listId')
            list_name = list_data.get('name', hubspot_params.get('name', 'Unnamed List'))
            
            #Build HubSpot list URL
            if list_id:
                list_url = f"https://app.hubspot.com/contacts/5138011/objectLists/{list_id}"
            else:
                list_url = "https://app.hubspot.com/contacts/lists"
            
            return True, list_url, list_name
            
        else:
            #Actual error status codes (400, 401, 403, 500, etc.)
            error_detail = response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text
            return False, f"HubSpot API error ({response.status_code}): {error_detail}", None
            
    except Exception as e:
        return False, f"Error calling HubSpot API: {str(e)}", None
        
#Function to handle user clarifications to existing requests
def handle_clarification(body, user_id, clarification, existing_request, bot_client_id, bot_client_secret):
    print(f"Processing clarification: '{clarification}'")
    
    #Get the original request
    original_request = get_original_request(user_id)
    
    if original_request:
        #Combine original request with clarification
        combined_request = f"{original_request}. Also, {clarification}"
        print(f"🔍 Combined request: '{combined_request}'")
        
        #Re-translate with combined request
        try:
            explanation, hubspot_params = translate_and_explain(combined_request)
            
            if explanation and hubspot_params:
                #Update stored request
                store_request(user_id, hubspot_params)
                
                confirmation_msg = f"Updated request: {explanation}\n\nShould I create this list? (yes/no)\n\n"
                send_to_teams(body, confirmation_msg, bot_client_id, bot_client_secret)
            else:
                send_to_teams(body, "I couldn't understand the clarification. Please try rephrasing.", bot_client_id, bot_client_secret)
                
        except Exception as e:
            print(f"Error processing clarification: {e}")
            send_to_teams(body, "Error processing clarification. Please try again.", bot_client_id, bot_client_secret)
    else:
        #Fallback - treat as new request
        send_to_teams(body, "I couldn't find your original request. Please start over with a new request.", bot_client_id, bot_client_secret)
        
#Main function to process incoming Teams messages and route them appropriately       
def process_message(body, bot_client_id, bot_client_secret):
    #Log start of message processing
    print("STARTING process_message")
    
    user_message = body.get('text', '').strip()
    user_id = body.get('from', {}).get('id', 'unknown')
    
    print(f"Raw user_message: '{user_message}'")
    print(f"User ID: {user_id}")
    
    #Clean HTML
    if '<p>' in user_message:
        user_message = re.sub(r'<[^>]+>', '', user_message)
        print(f"Cleaned message: '{user_message}'")
    
    print(f"User said: '{user_message}'")
    
    #Handle greeting messages - don't process as list requests
    if user_message.lower() in ['hi', 'hello', 'hey', 'start', 'help']:
        print("Handling greeting - sending help message")
        help_message ="""👋 **Welcome to the HubSpot List Creator!**\n\nI can help you create HubSpot contact lists using natural language. Here's how to use me:\n\n**📋 Examples:**\n\n- "Create a list of SMB providers in Virginia"\n- "Make a list of enterprise provider contacts in California and Texas"\n- "Find mid-market provider contacts in North Carolina"\n\n**🎯 What I understand:**\n\n- **Locations**: State names and abbreviations\n- **Company segments**: SMB, Mid-Market, Enterprise\n- **Types**: Provider contacts\n\n**Ready to get started? Try asking me to create a list!** 🚀"""
        
        send_to_teams(body, help_message, bot_client_id, bot_client_secret)
        return
    
    #Handle positive confirmations from user
    if user_message.lower() in ['yes', 'y', 'proceed', 'create it','yea','yeah','yep','ok']:
        print("Handling YES confirmation")
        handle_yes(body, user_id, bot_client_id, bot_client_secret)
        return
    
    #Handle negative responses or cancellations
    if user_message.lower() in ['no', 'n', 'cancel']:
        print("Handling NO/cancel")
        clear_request(user_id)
        send_to_teams(body, "Request cancelled. Feel free to make a new request!", bot_client_id, bot_client_secret)
        return
    
    #Check if user has a pending request (for clarifications)
    existing_request = get_request(user_id)
    
    #Route to clarification handler if user has pending request
    if existing_request:
        print("User has pending request - treating as clarification")
        handle_clarification(body, user_id, user_message, existing_request, bot_client_id, bot_client_secret)
        return
    
    #Handle new request
    print("Processing new request - ABOUT TO CALL CLAUDE")
    print("Calling translate_and_explain...")
    
    try:
        #Translate natural language to HubSpot parameters using Claude
        explanation, hubspot_params = translate_and_explain(user_message)
        print(f"translate_and_explain returned: explanation={explanation is not None}, params={hubspot_params is not None}")
    #Handle any errors in translation process
    except Exception as e:
        print(f"Exception in translate_and_explain: {e}")
        explanation, hubspot_params = None, None
    
    if explanation and hubspot_params:
        print(f"SUCCESS: Got response from Claude")
        #Store the translated parameters for confirmatio
        store_request(user_id, hubspot_params)
        #Store original message for potential clarifications
        store_original_request(user_id, user_message)
        
        confirmation_msg = f"{explanation}\n\nShould I create this list? (yes/no)\n\n💡 You can also add clarifications like 'also include provider contacts in California'"
        print(f"SENDING: {confirmation_msg}")
        send_to_teams(body, confirmation_msg, bot_client_id, bot_client_secret)
    else:
        print("FAILURE: Claude translation failed or returned None")
        send_to_teams(body, "I couldn't understand that request. Try: 'create a list of SMB providers in Virginia'", bot_client_id, bot_client_secret)

#Function to handle user confirmation and execute HubSpot list creation
def handle_yes(body, user_id, bot_client_id, bot_client_secret):
    hubspot_params = get_request(user_id)
    
    if hubspot_params:
        print("Sending to HubSpot API:")
        print(json.dumps(hubspot_params, indent=2))
        
        #Call HubSpot API
        success, result, list_name = create_hubspot_list(hubspot_params)
        clear_request(user_id)
        
        if success:
            send_to_teams(body, f"✅ List '{list_name}' created successfully!\n🔗 [View List]({result})", bot_client_id, bot_client_secret)
        else:
            send_to_teams(body, f"❌ {result}", bot_client_id, bot_client_secret)
    else:
        send_to_teams(body, "No pending request found. Please make a new request.", bot_client_id, bot_client_secret)

#Global set to track processed messages and prevent duplicates
processed_messages = set()

#Validate incoming requests
def validate_bot_token(event, bot_app_id):
    try:
        #Fetch token
        auth_header = (event['headers'].get('Authorization') or 
        event['headers'].get('authorization') or 
        event['headers'].get('AUTHORIZATION')
    )
        if not auth_header.startswith('Bearer '):
            raise ValueError('Missing Bearer token')
        
        token = auth_header[7:]
        
        #Fetch msft signing keys
        response = requests.get('https://login.botframework.com/v1/.well-known/keys',timeout=10)
        keys = response.json()
        
        #Fetch token header
        header = jwt.get_unverified_header(token)
        kid = header.get('kid')
        
        #Fetch signing key
        signing_key = None
        for key in keys['keys']:
            if key['kid'] == kid:
                signing_key = jwt.PyJWK(key).key
                print(f"signing_key:{signing_key}")
                break
        
        if not signing_key:
            raise ValueError('Key not found')
        
        #Decode token
        jwt.decode(
            token,
            signing_key,
            algorithms=['RS256'],
            audience=bot_app_id
        )
        
        return True
        
    except Exception as e:
        print(f"Token validation failed: {e}")
        return False


#Main AWS Lambda handler function - entry point for all requests
def lambda_handler(event, context):
    try:
        secrets = ['teams_bot_secret', 'teams_bot_client','hs_teams_bot_app_id']
        fetch_secrets = get_secrets(secrets)
        extracted_secrets = {key: extract_secret_value(value) for key, value in fetch_secrets.items()}
        
        bot_app_id = extracted_secrets['hs_teams_bot_app_id']['hs_teams_bot_app_id']
        
        #Auth
        if not validate_bot_token(event, bot_app_id):
            return {'statusCode': 401, 'body': 'Unauthorized'}

        #Parse message
        body = json.loads(event['body'])
        
        #Handle different activity types
        activity_type = body.get('type')
        
        #Deduplicate messages using message ID
        message_id = body.get('id')
        if message_id in processed_messages:
            print(f"Duplicate message {message_id}, ignoring")
            return {'statusCode': 200}
        
        processed_messages.add(message_id)
        
        #Keep only last 100 message IDs to prevent memory issues
        if len(processed_messages) > 100:
            processed_messages.clear()
        
        if not body.get('text'):
            return {'statusCode': 200}
        
        #Get client id secret and process normally

        bot_client_secret = extracted_secrets['teams_bot_secret']['teams_bot_secret']
        bot_client_id = extracted_secrets['teams_bot_client']['teams_bot_client']
        
        #Process the message
        process_message(body, bot_client_id, bot_client_secret)
        
        return {'statusCode': 200}
        
    except Exception as e:
        print(f"Error: {e}")
        return {'statusCode': 200}