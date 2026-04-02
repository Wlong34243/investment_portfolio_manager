import json

with open('service_account.json', 'r') as f:
    content = f.read()

# The issue is that the private key has unescaped newlines.
# A simple string replace won't work because of how the tool handles multiline strings.
# A robust way is to load it as a Python dictionary and then dump it back to a file
# with the correct JSON formatting.
# The problem is that the initial file is not valid JSON.

# Let's try to manually fix the string
lines = content.split('
')
in_key = False
new_lines = []
for line in lines:
    if '"private_key":' in line:
        in_key = True
        line = line.replace('-----BEGIN PRIVATE KEY-----', '-----BEGIN PRIVATE KEY-----
')
    elif '-----END PRIVATE KEY-----' in line:
        line = line.replace('-----END PRIVATE KEY-----', '-----END PRIVATE KEY-----
')
        in_key = False
    elif in_key:
        line += '
'
    new_lines.append(line)

# The above logic is flawed because it will add 
 to the last line of the key.
# Let's try a simpler approach.

import re
# The private key is the only value with newlines.
# We can read the whole file, and use a regex to replace the newlines
# within the private key block.
with open('service_account.json', 'r') as f:
    content = f.read()

# This is tricky because the file is not valid JSON, so we can't parse it.
# We have to treat it as a string.
# The problem is that the file contains unescaped newlines in the private_key field.
# Let's do a direct string replacement, but be very careful.

private_key_part = content.split('"private_key": "')[1].split('",
  "client_email"')[0]
escaped_private_key = private_key_part.replace('
', '
')

new_content = content.replace(private_key_part, escaped_private_key)

with open('service_account.json', 'w') as f:
    f.write(new_content)
