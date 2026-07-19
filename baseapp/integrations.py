import requests
from base64 import b64encode
from django.core.cache import cache
from django.utils.translation import gettext_lazy as _

from config.settings import iip_username, iip_password, ConsumerKey, ConsumerSecret, tin
from config.utils import CommonException

key_secret_bytes = f"{ConsumerKey}:{ConsumerSecret}".encode("ascii")
base64_string = b64encode(key_secret_bytes).decode("ascii")

auth_url = 'https://iskm.egov.uz:9444/oauth2/token'


def iip_auth():
    response = requests.post(
        url=auth_url,
        params={"grant_type": 'password', 'username': iip_username, 'password': iip_password},
        headers={
            "content-type": "application/json",
            "Authorization": f"Basic {base64_string}"
        }
    )
    return response.status_code, response.json()


def get_iip_token():
    iip_token = cache.get('iip_token')
    if not iip_token:
        status, data = iip_auth()
        if status == 200:
            iip_token = data['access_token']
            cache.set('iip_token', iip_token, data['expires_in'])
        else:
            raise CommonException(_("Sorry, there was an error retrieving data."))
    return iip_token


def get_cadastre_info(number):
    token = get_iip_token()
    url = 'https://apimgw.egov.uz:8243/kadastr/cadnum/v3'
    header = {
        'Content-Type': 'application/json',
        'Authorization': f"Bearer {token}"
    }
    payload = {
        'id': 1,
        'purpose': "Fanlar akademiyasi xizmatlari",
        'tin': tin,
        'cad_num': number
    }
    response = requests.post(url, json=payload, headers=header)
    if response.status_code == 204:
        raise CommonException(_("Sorry, the data could not be found."))
    elif response.status_code != 200:
        raise CommonException(_("Sorry, there was an error retrieving data."))
    return response.json()


def get_cadastres_info_by_pin(pinfl):
    token = get_iip_token()
    url = 'https://apimgw.egov.uz:8243/kadastr/cadnum/v3'
    header = {
        'Content-Type': 'application/json',
        'Authorization': f"Bearer {token}"
    }
    payload = {
        'id': 1,
        'purpose': "Fanlar akademiyasi xizmatlari",
        'tin': tin,
        'pinfl': pinfl
    }
    response = requests.post(url, json=payload, headers=header)
    status_code, response_data = response.status_code, response.json()
    if status_code == 204:
        raise CommonException(_("Sorry, the data could not be found."))
    elif status_code != 200:
        raise CommonException(_("Sorry, there was an error retrieving data."))
    elif response_data['code'] == 1:
        try:
            data = {
                "cadastre_count": response_data['cadastr_count'],
                "cadastre_list": response_data['cadastr_list']
            }
        except Exception as e:
            raise CommonException(_("Sorry, an unexpected error occurred while processing the data."))
        return data
    else:
        raise CommonException(response_data.get('message', _("Sorry, there was an error retrieving data.")))

