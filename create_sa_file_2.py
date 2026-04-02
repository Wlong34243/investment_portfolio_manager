import json

# This uses triple-quotes to correctly handle the multi-line private key string
service_account_info = {
  "type": "service_account",
  "project_id": "re-property-manager-487122",
  "private_key_id": "666a1e869872944f5f76bd80765fe5aa20b5a16d",
  "private_key": """-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQCx9dL3lB2HRLuF
HHxhFf6ft2GBgLC5ei/fkRVtDrUEN/j0JFAuevPVN6fYT2ja/3bsGSTcOeqVk2Oe
qC6vsMpLOgorK38eMoYLPOxdkJYwQw/w4gMeF7Yp305jirL3Yy6QjZYZJzI6cCaZ
wZE9oesv/UFVZYR0x6EjNeQcZHLvKtxzgcd8oCfQ4wTdhxa/Wtsg7q0hluRD3mP5
ZChI3wWlFIG9W/HPd7o2URfROrq5gZUjFoc6UrWcBRm+0AiSLo+0eVDfDgIS0+k6
eNfEbosRL9ezNcm7JwpDhle0JdOw9GO7sQYKDYpDihfu7/z1hTVH8Rullvinixuk
OWux49VPAgMBAAECggEAIy342Ad4NOLh/QTuE5UxAirSxDKH/QqKBzSbmzUClMRp
2v2Iuj+FDzvS2uCL1msU+8RWtJBgbtQ1p8oQfJvCyc897l3JYdNUC0muYiqwffbr
4k8TlbHTSYDC8sua6Gu7a0kKCIvmkoXUI6YPy7LEFvcGINcSMbG7CYZgQzqaO+wV
K8XuEeNRWjhFL48L7hivJP/t+vz6/yByQ3QCONNyIwajj4qIeQ6etZ8cByMNRCDs
dVxgexUYmkx0tm+f8NFx9mmIqCRTUzKdMXgZxiqZeAoNkFgJZcjmw8JsLN2ZblDR
EdG0/VXce4wVlzShyQY8XesZOx5v59aM638cVop2cQKBgQDgmL3Cyt4d8HytDtMe
3Rx6DUdSUTvFtosflaWLCrgN57Jx2Kvpm+CJy4L3ZuFxXk8S2gqJGS1iF/pXUI3/
fbc3DZO2IkQy/vJfeCX4UglggxTdd5jK2ydepe1KFi9CSnRAQDhieu5bYiHd1JGI
t7M4oNeZtGeJEIEqR39EdkDSPwKBgQDK18UjS9afqoWYYF5l54HncNcV1WK3o99b
gsCgVB84+lE5ksfhy9lZnKc56SgbH9Cdzim5g4x/x7f8HzszckdfnDoB+EanJHDo
mGWt8+oMmKWZ8dZnQqyKD183lNu33WQpKR2/NlfjTO34LZdLMm2g2E/+IQzqL2YW
lsqJmtgY8QKBgQCqjXK0hGdtptyWckaCDnh8eq7pZMSWHEvDnVkLoAUqkgLhDx9l
E7jMCt4WT2rtMyeq8ibD+3mKHxk8yvA5ztadmNLNoXHWo+Gb+9ohmvKB9qiWkSZX
DVr1Nd1ewD/9ABsNW3c12ZI9lOSQ1sX5Yz5Wx1VR5DwnSoA7gfW0IHSS8wKBgGxq
Lv/ShQAJ0CXFPC8TMadV9F/DEWQ9vh/XHsWSsK1vfQJcpWDV53Gx/N9C8yCsPIBb
tIlm+i1BveCPgMDaj7NWeNqcrIahP4fSDGaRO8NHwxso2wON61JPLQE0GsuHFQW6
6B9PGGJwt7AyDe8vINEbTIXzfEee1d208sPhcybBAoGAZUGTDXoc7mD45mj5TlI3
pRm7hA1A8kOL+nD2YdDsVGac3QUkrbNQlz61pn1X/hfNZwO5dwrqjsg8wvRWG4Lf
KJ3tI6O0WFQq0adxVNHWHFFCdubD96qo9w/3EyRzcABme4fgmE92CMA6GvO/tTai
xAND/ARDDIvn32SFrYQf+aU=
-----END PRIVATE KEY-----""",
  "client_email": "propertymanager@re-property-manager-487122.iam.gserviceaccount.com",
  "client_id": "115662335649907513706",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/propertymanager%40re-property-manager-487122.iam.gserviceaccount.com"
}

with open('service_account.json', 'w') as f:
    json.dump(service_account_info, f, indent=2)
