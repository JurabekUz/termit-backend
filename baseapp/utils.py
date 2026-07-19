from django.db import models


def has_related_objects(instance: models.Model) -> bool:
    """
    Checks whether the given model object has related objects.

    Args:
    instance (models.Model): A Django model object.

    Returns:
    bool: Returns True if there are related objects, False otherwise.
    """
    related_fields = [
        field for field in instance._meta.get_fields()
        if (field.one_to_many or field.one_to_one) and field.auto_created
           and hasattr(instance, field.name)  # Faqat mavjud fieldlarni olish
           and getattr(instance, field.name)  # None bo‘lmaganlarni olish
    ]

    return any(getattr(instance, field.name).exists() for field in related_fields)
