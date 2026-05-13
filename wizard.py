import os
from datetime import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

import django

django.setup()

from django.conf import settings
from django.db.transaction import atomic
from utils.text_output import header, info, section_separator
from django.contrib.sites.models import Site
from django.contrib.auth.models import User
from allauth.account.models import EmailAddress
from django_otp.plugins.otp_totp.models import TOTPDevice
from django.utils.crypto import get_random_string

from backend.settings import env
from users.models import Profile
from utils.text_output import success, warning

def update_site_info():
    """
    Updates or creates the default Django Site with our domain and project name.
    """
    header("Ensuring Site Information Configuration")
    site, created = Site.objects.update_or_create(
        pk=1,
        defaults={
            'domain': settings.DOMAIN,
            'name': settings.PROJECT_NAME,
        }
    )
    if created:
        info(f"Site info created: {site.domain} ({site.name})")
    else:
        info(f"Site info updated: {site.domain} ({site.name})")
    section_separator()


def create_super_admin(log_list: list):
    """
    Creates the Django superuser.
    If the admin user already exists, no attributes (including password) are updated.
    Returns a tuple (admin_user, updated_flag).
    """
    header("Ensuring Super Admin User Configuration")
    admin_email = env('ADMIN_USER', default='admin@exchange.net')
    try:
        admin_user = User.objects.get(username=admin_email)
        created = False
    except User.DoesNotExist:
        admin_user = User(username=admin_email, email=admin_email)
        created = True

    if created:
        admin_random_password = get_random_string(length=12)
        info("Admin user does not exist, creating one now...")
        admin_user.set_password(admin_random_password)
        admin_user.is_superuser = True
        admin_user.is_staff = True
        admin_user.save()
        EmailAddress.objects.create(
            user=admin_user,
            email=admin_email,
            verified=True,
            primary=True,
        )
        Profile.objects.get_or_create(user=admin_user, defaults={'is_auto_orders_enabled': True})
        totp_device, _ = TOTPDevice.objects.get_or_create(
            user=admin_user,
            defaults={'name': admin_user.email}
        )
        totp_config_url = totp_device.config_url
        log_list.append("Admin Info:")
        log_list.append(f"Email: {admin_email} | Password: {admin_random_password}")
        log_list.append(f"Master Pass: {settings.ADMIN_MASTERPASS}")
        log_list.append(f"2FA Token (Scan QR or use URL): {totp_config_url}")
        log_list.append("-" * 30)
        success("Super admin user created successfully.")
        updated = True
    else:
        info("Admin user already exists; not modifying any attributes or password.")
        warning("Existing admin password remains unchanged.")
        updated = False

    section_separator()
    return admin_user, updated

def write_private_info_file(log_list):
    """
    Writes the private info (collected logs) into a file for the user to copy and then delete.
    Ensures each log entry is converted to a string.
    """
    if not log_list:
        return
    filename = f'save_to_self_and_delete_{int(datetime.now().timestamp())}.txt'
    file_path = os.path.join(settings.BASE_DIR, filename)

    with open(file_path, 'a+', encoding='utf-8') as file:
        for line in log_list:
            file.write(str(line) + '\r\n')
    success(
        f"File '{filename}' was created with private info. Please store it safely and remove it from the server afterward!"
    )
    section_separator()

def main():
    private_logs = []

    header("Starting the Setup Script")
    with atomic():
        update_site_info()
        _, admin_updated = create_super_admin(private_logs)

    if admin_updated:
        header("Writing Private Info File")
        write_private_info_file(private_logs)

    success("Setup Script Done")

if __name__ == '__main__':
    main()
