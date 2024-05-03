# import ast
# import json
# import re
#
# import requests
#
# url = "https://multidataghana.com/merchintegrate/geosams/ishare_api/"
#
#
# payload = {'type': 'pushData',
#            'apikey': 'fghhg',
#            'ref': 'tiktakkkkklkkkk',
#            'data': '50',
#            'share': '0272266444'}
# files = [
#
# ]
# headers = {}
#
# response = requests.request("POST", url, headers=headers, data=payload, files=files)
# json_match = re.search(r'getBalance(.+)}', response.text)
#
# if json_match:
#     json_part = json_match.group(1) + '}'
#     print("Extracted JSON part:")
#     print(json_part)
#
#     try:
#         # Parse the extracted JSON into a dictionary
#         response_dict = json.loads(json_part)
#
#         # Now you can access the data using keys
#         data = response_dict.get('data')
#         balance = response_dict.get('balance')
#
#         print("Parsed JSON:")
#         print(response_dict)
#         print("Data:", data)
#         print("Balance:", balance)
#     except json.JSONDecodeError as e:
#         print(f"Error decoding JSON: {e}")
# else:
#     print("No valid JSON found in the response.")
#
#
#

