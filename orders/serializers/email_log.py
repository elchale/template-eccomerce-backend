"""EmailLog serializer (list + detail) for the admin Email Log endpoints."""
from rest_framework import serializers

from orders.models import EmailLog
from orders.email_dispatch import email_log_is_retryable


class EmailLogSerializer(serializers.ModelSerializer):
    email_type_display = serializers.SerializerMethodField()
    status_display = serializers.SerializerMethodField()
    order_number = serializers.SerializerMethodField()
    is_retryable = serializers.SerializerMethodField()

    class Meta:
        model = EmailLog
        fields = [
            'id',
            'email_type',
            'email_type_display',
            'template_name',
            'subject',
            'recipient_email',
            'recipient_user',
            'order',
            'order_number',
            'status',
            'status_display',
            'task_name',
            'error_message',
            'attempts',
            'sent_at',
            'last_attempt_at',
            'is_retryable',
            'created',
        ]
        read_only_fields = fields

    def get_email_type_display(self, obj) -> str:
        return obj.get_email_type_display()

    def get_status_display(self, obj) -> str:
        return obj.get_status_display()

    def get_order_number(self, obj) -> str | None:
        if obj.order_id is not None:
            return getattr(obj.order, 'order_number', None)
        return None

    def get_is_retryable(self, obj) -> bool:
        return email_log_is_retryable(obj)
