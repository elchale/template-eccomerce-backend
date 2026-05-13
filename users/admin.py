from django.contrib import admin
from django.utils.html import format_html

from .models import Profile, LoginHistory


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'actions_freezed_till', 'is_frozen', 'created', 'updated')
    list_filter = ('actions_freezed_till',)
    search_fields = ('user__email', 'user__username')
    readonly_fields = ('created', 'updated')

    def is_frozen(self, obj: Profile):
        if obj.is_actions_frozen():
            return format_html('<span style="color: red;">Yes</span>')
        return format_html('<span style="color: green;">No</span>')
    is_frozen.short_description = 'Actions Frozen'


@admin.register(LoginHistory)
class LoginHistoryAdmin(admin.ModelAdmin):
    list_display = ('user', 'ip', 'user_agent', 'timestamp')
    list_filter = ('timestamp',)
    search_fields = ('user__email', 'user__username', 'ip')
    readonly_fields = ('user', 'ip', 'user_agent', 'timestamp')
    ordering = ('-timestamp',)

