import json

with open('service_account.json', 'r') as f:
    content = f.read()

# The file contains unescaped newlines in the private_key field
start_key = '"private_key": "'
end_key = '",\n  "client_email"'

start_index = content.find(start_key) + len(start_key)
if start_index < len(start_key): # Not found
    # Try different ending
    end_key = '",\r\n  "client_email"'
    start_index = content.find(start_key) + len(start_key)

end_index = content.find(end_key)

if start_index >= len(start_key) and end_index != -1:
    private_key = content[start_index:end_index]
    escaped_private_key = private_key.replace('\n', '\\n').replace('\r', '')
    new_content = content[:start_index] + escaped_private_key + content[end_index:]
    
    # Try to parse it to verify
    try:
        json_data = json.loads(new_content)
        with open('service_account.json', 'w') as f:
            json.dump(json_data, f, indent=2)
        print("Successfully fixed service_account.json")
    except Exception as e:
        print(f"Error parsing fixed JSON: {e}")
else:
    print("Could not find private_key block")
