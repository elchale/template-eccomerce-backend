from rest_framework import serializers

from products.models import Category


class AdminCategorySerializer(serializers.ModelSerializer):
    """Admin CRUD serializer that exposes per-language translation columns."""

    parent_name = serializers.CharField(source='parent.name', read_only=True, default=None)

    # Per-language translation fields
    name_es = serializers.CharField(allow_blank=False, required=True)
    name_en = serializers.CharField(allow_blank=True, required=False, allow_null=True, default='')
    name_pt = serializers.CharField(allow_blank=True, required=False, allow_null=True, default='')
    description_es = serializers.CharField(allow_blank=True, required=False, default='')
    description_en = serializers.CharField(allow_blank=True, required=False, allow_null=True, default='')
    description_pt = serializers.CharField(allow_blank=True, required=False, allow_null=True, default='')

    class Meta:
        model = Category
        fields = [
            'id',
            'name',
            'slug',
            'description',
            'name_es',
            'name_en',
            'name_pt',
            'description_es',
            'description_en',
            'description_pt',
            'image_url',
            'parent',
            'parent_name',
            'is_active',
            'sort_order',
            'created',
            'updated',
        ]
        read_only_fields = ['id', 'created', 'updated']


class CategorySerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            'id',
            'name',
            'slug',
            'description',
            'image_url',
            'parent',
            'is_active',
            'sort_order',
            'children',
        ]
        read_only_fields = ['id']

    def get_children(self, obj):
        children = obj.children.filter(is_active=True).order_by('sort_order', 'name')
        return CategorySerializer(children, many=True, context=self.context).data


class CategoryDetailSerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()
    parent_name = serializers.CharField(source='parent.name', read_only=True, default=None)
    product_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            'id',
            'name',
            'slug',
            'description',
            'image_url',
            'parent',
            'parent_name',
            'is_active',
            'sort_order',
            'children',
            'product_count',
            'created',
            'updated',
        ]
        read_only_fields = ['id', 'created', 'updated']

    def get_children(self, obj):
        children = obj.children.filter(is_active=True).order_by('sort_order', 'name')
        return CategorySerializer(children, many=True, context=self.context).data

    def get_product_count(self, obj):
        # Use annotated value when available to avoid per-category COUNT queries.
        if hasattr(obj, 'product_count_annotated'):
            return obj.product_count_annotated
        return obj.products.filter(is_active=True).count()
