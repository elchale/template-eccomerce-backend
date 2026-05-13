from backend.settings import env
from django import template

register = template.Library()

@register.simple_tag
def get_env_tags(tag, capitalize = True):
    env_tag = env(tag)
    if not env_tag:
        return env_tag
    if capitalize:
        return env_tag[0].upper() + env_tag[1:].lower()
    return env_tag
