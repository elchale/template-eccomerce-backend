from rest_framework.serializers import ModelSerializer

from users.models import Profile
from users.serializers.auth import UserSerializer


class UserProfileSerializer(ModelSerializer):
    user = UserSerializer(many=False, read_only=True)

    class Meta:
        model = Profile
        fields = (
            'user',
            'actions_freezed_till',
        )
        read_only_fields = (
            'user',
            'actions_freezed_till',
        )

    # def get_kyc_status(self, obj):
    #     return UserKYC.status_for_user(obj.user)

    # def get_kyt_enabled(self, obj):
    #     return settings.IS_KYT_ENABLED

    # def get_kyc_enabled(self, obj):
    #     return settings.IS_KYC_ENABLED

    # def get_sms_enabled(self, obj):
    #     return settings.IS_SMS_ENABLED

    # def get_is_2fa_on(self, obj):
    #     return TwoFactorSecretTokens.is_enabled_for_user(obj.user)
