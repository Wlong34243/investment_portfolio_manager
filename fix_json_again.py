import json

# Read the file content
with open('service_account.json', 'r') as f:
    content = f.read()

# Manually escape the newlines in the private_key
# This is a bit brittle but should work for this specific file
lines = content.splitlines()
in_private_key = False
result_lines = []
for line in lines:
    if '"private_key":' in line:
        in_private_key = True
        line = line.replace('-----BEGIN PRIVATE KEY-----', '-----BEGIN PRIVATE KEY-----
')
    elif '-----END PRIVATE KEY-----' in line:
        line = line.replace('-----END PRIVATE KEY-----', '-----END PRIVATE KEY-----
')
        in_private_key = False
    elif in_private_key:
        line += '
'
    result_lines.append(line)

# The logic is still complex, let's simplify.
# The only part that is multiline is the private key.
# We can find the start and end of the private key string and replace the newlines in between.

start_key = '"private_key": "'
end_key = '",
  "client_email"'

start_index = content.find(start_key) + len(start_key)
end_index = content.find(end_key)

private_key = content[start_index:end_index]
escaped_private_key = private_key.replace('
', '
')

new_content = content[:start_index] + escaped_private_key + content[end_index:]

# Write the corrected content back to the file
with open('service_account.json', 'w') as f:
    f.write(new_content)
