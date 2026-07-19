from django.db import transaction
from rest_framework.serializers import ModelSerializer, ChoiceField, PrimaryKeyRelatedField
from django.utils.translation import gettext_lazy as _

from account.serializers import UserFullNameSerializer
from baseapp.serializers import IdNameSerializer
from config.utils import CommonException
from info.serializers import MediaSerializer
from notification.services import increment_counter_on_plan_creation
from plan.models import Plan, PlanStatus, PlanItem, PlanRegionStatus, DraftItem
from damaged_object.models import DamagedObject, DamagedStatus, DamagedTypes

"""  PlanRegionStatus """


class PlanRegionStatusSerializer(ModelSerializer):
    region = IdNameSerializer()

    class Meta:
        model = PlanRegionStatus
        fields = ('id', 'read_time', 'status', 'region')


""" PlanItem """


class PlanItemSerializer(ModelSerializer):
    performer = UserFullNameSerializer()
    document = MediaSerializer()
    images = MediaSerializer(many=True)

    class Meta:
        model = PlanItem
        fields = ('id', 'plan', 'item', 'performer', 'date', 'document', 'description', 'images')


class PlanItemUpdateSerializer(ModelSerializer):

    class Meta:
        model = PlanItem
        fields = ('date', 'document', 'description', 'images')
        extra_kwargs = {'date': {'required': True}}


class PlanItemListSerializer(ModelSerializer):
    district = IdNameSerializer()

    class Meta:
        model = DamagedObject
        fields = ('id', 'status', 'district', 'date', 'type')

    def to_representation(self, instance):
        data = super().to_representation(instance)
        related_name = 'mahallainfo' if instance.type == DamagedTypes.mahalla else 'openareainfo'
        related_obj = getattr(instance, related_name)
        data['owner_name'] = related_obj.owner_name
        data['owner_phone'] = related_obj.owner_phone
        data['address'] = related_obj.address
        return data


""" Plan """


class PlanSerializer(ModelSerializer):
    status = ChoiceField(choices=(PlanStatus.new, PlanStatus.draft), default=PlanStatus.draft)
    items = PrimaryKeyRelatedField(
        many=True, write_only=True,
        queryset=DamagedObject.objects.filter(status=DamagedStatus.approved))


    class Meta:
        model = Plan
        fields = ('id', 'name', 'from_date', 'to_date', 'items', 'status')

    def validate_items(self, value):
        if len(value) == 0:
            raise CommonException(_("Plan must have at least one item"))
        for item in value:
            if item.plan_items.filter(is_performed=False).exists():
                raise CommonException(_("This item has not been performed yet"))
        return value

    @transaction.atomic
    def create(self, validated_data):
        items = validated_data.pop('items')
        plan = Plan.objects.create(**validated_data)
        if validated_data['status'] == PlanStatus.draft:
            draft_item_objs = [DraftItem(plan=plan, item=item) for item in items]
            DraftItem.objects.bulk_create(draft_item_objs)
        else:
            item_objs = [PlanItem(plan=plan, item=item) for item in items]
            PlanItem.objects.bulk_create(item_objs)

            # delete draft items
            DraftItem.objects.filter(item__in=items).delete()

            regions = {item.district.region for item in items}
            region_objs = [PlanRegionStatus(plan=plan, region=region, status=PlanStatus.approved) for region in regions]
            PlanRegionStatus.objects.bulk_create(region_objs)
            increment_counter_on_plan_creation()
        return plan

    @transaction.atomic
    def update(self, instance, validated_data):
        items = validated_data.pop('items', None)

        if instance.status != PlanStatus.draft:
            raise CommonException(_("This plan cannot be edited."))

        # Plan modelining maydonlarini yangilash
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Yangi `PlanItem` obyektlarini yaratish
        if validated_data['status'] == PlanStatus.draft:
            # Eski `PlanItem` obyektlarini o‘chirish
            DraftItem.objects.filter(plan=instance).delete()

            draft_item_objs = [DraftItem(plan=instance, item=item) for item in items]
            DraftItem.objects.bulk_create(draft_item_objs)
        else:
            # Eski `PlanItem` obyektlarini o‘chirish
            PlanItem.objects.filter(plan=instance).delete()
            # delete draft items
            DraftItem.objects.filter(item__in=items).delete()

            new_plan_items = [PlanItem(plan=instance, item=item) for item in items]
            PlanItem.objects.bulk_create(new_plan_items)

            # PlanRegionStatus ni yangilash
            PlanRegionStatus.objects.filter(plan=instance).delete()
            regions = {item.district.region for item in items}
            region_objs = [PlanRegionStatus(plan=instance, region=region) for region in regions]
            PlanRegionStatus.objects.bulk_create(region_objs)
            increment_counter_on_plan_creation()
        return instance


class PlanListSerializer(ModelSerializer):

    class Meta:
        model = Plan
        fields = ('id', 'name', 'from_date', 'to_date', 'status', 'unread')

    def to_representation(self, instance):
        user = self.context['request'].user
        data = super().to_representation(instance)
        if user.region_id is not None:
            data['status'] = instance.get_regional_status(user.region_id)
            data['items_count'] = instance.items_count(user.region_id)
            data['percentage_of_cleaned'] = instance.percentage_of_cleaned(user.region_id)
        else:
            data['items_count'] = instance.items_count()
            data['percentage_of_cleaned'] = instance.percentage_of_cleaned()
        return data


class PlanRetrieveSerializer(ModelSerializer):

    class Meta:
        model = Plan
        fields = (
            'id', 'name', 'from_date', 'to_date', 'status', 'director_comment'
        )

    def to_representation(self, instance):
        user = self.context['request'].user
        data = super().to_representation(instance)
        if instance.status == PlanStatus.draft:
            damaged_objects = DamagedObject.objects.filter(
                draft_items__plan=instance).select_related('district').prefetch_related(
                'mahallainfo', 'openareainfo').distinct()
            data['percentage_of_cleaned'] = instance.percentage_of_cleaned()
            data['items_count'] = instance.items_count()
            data['region_statuses'] = []
        else:
            damaged_objects = DamagedObject.objects.filter(
                plan_items__plan=instance).select_related('district').prefetch_related(
                'mahallainfo', 'openareainfo').distinct()
            if user.region_id is not None:
                damaged_objects = damaged_objects.filter(district__region=user.region_id)
                data['status'] = instance.get_regional_status(user.region_id)
                data['percentage_of_cleaned'] = instance.percentage_of_cleaned(user.region_id)
                data['items_count'] = instance.items_count(user.region_id)
            else:
                data['percentage_of_cleaned'] = instance.percentage_of_cleaned()
                data['items_count'] = instance.items_count()
                data['region_statuses'] = PlanRegionStatusSerializer(instance.region_statuses.all(), many=True).data
        data['items'] = PlanItemListSerializer(damaged_objects, many=True).data
        return data


class PlanCheckSerializer(ModelSerializer):
    status = ChoiceField(choices=(PlanStatus.approved, PlanStatus.rejected))

    class Meta:
        model = Plan
        fields = ('status', 'director_comment')

