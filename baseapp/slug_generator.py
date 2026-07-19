import random
import string
import uuid

from django.template import defaultfilters
from django.utils.crypto import get_random_string
from django.utils.text import slugify

from unidecode import unidecode
from django.template import defaultfilters


def random_string_generator(size=10, chars=string.ascii_lowercase + string.digits):
    return ''.join(random.choice(chars) for _ in range(size))


def unique_slug_generator(instance, title, new_slug=None):
    title = defaultfilters.slugify(unidecode(title))
    if new_slug is not None:
        slug = new_slug
    else:
        slug = slugify(title, allow_unicode=True)
    Klass = instance.__class__
    max_length = Klass._meta.get_field('slug').max_length
    slug = slug[:max_length]
    qs_exists = Klass.objects.filter(slug=slug).exists()

    if qs_exists:
        new_slug = "{slug}-{randstr}".format(
            slug=slug[:max_length - 5], randstr=random_string_generator(size=4))

        return unique_slug_generator(instance, title, new_slug=new_slug)

    additional_id = str(uuid.uuid4())
    slug += f"-{additional_id[30:]}"

    return slug


def slug_generator(sender, instance, *args, **kwargs):
    if not instance.slug:
        title = ''
        if instance.title_uz is not None and instance.title_uz != '':
            title = instance.title_uz
        else:
            title = get_random_string(8, '0123456789')

        title = title[:40]
        instance.slug = unique_slug_generator(instance, title=title)

