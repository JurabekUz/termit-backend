import base64
from rest_framework.views import exception_handler
from django.utils.translation import gettext_lazy as _
from rest_framework.status import HTTP_400_BAD_REQUEST
from rest_framework.exceptions import APIException


def make_captcha(obj, image_field):
    if image_field:
        try:
            with open(image_field.path, 'rb') as f:
                binary_data = f.read()
                encoded = base64.b64encode(binary_data).decode('utf-8')

            return {"base64": "data:image/jpg;base64," + encoded}
        except Exception as e:
            print(e)
            return {}
    else:
        return {}


class CommonException(APIException):
    def __init__(self,
                 detail: str = _('A server error occurred.'),
                 status_code=HTTP_400_BAD_REQUEST,
                 code=None):
        self.status_code = status_code
        super().__init__(detail, code)


def extract_first_error(data):
    """
    Response data ichidan birinchi xatolik xabarini topuvchi rekursiv funksiya
    """
    if isinstance(data, dict):
        if 'detail' in data:
            return data['detail']
        for field_name, messages in data.items():
            message = messages[0] if isinstance(messages, list) else messages

            if isinstance(message, (dict, list)):
                return extract_first_error(message)
            elif message.code == 'unique':
                return message

            return f"{field_name} {_('error')}. {message}"

    elif isinstance(data, list):
        for item in data:
            return extract_first_error(item)

    return str(data)


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is not None:
        error_message = extract_first_error(response.data)
        response.data = {"message": error_message}

    return response
