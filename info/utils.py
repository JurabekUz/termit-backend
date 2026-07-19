import os
from datetime import datetime


def media_upload_path(instance, filename):
    today = datetime.today().strftime('%Y/%m/%d')
    filename = os.path.basename(filename)
    return f'{today}/{filename}'


def delete_file_from_storage(file_path):
    """
    Faylni berilgan yo'ldan o'chirish.
    """
    if file_path and os.path.isfile(file_path):
        os.remove(file_path)
