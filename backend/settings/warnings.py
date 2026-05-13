import warnings

# NOTE the base register serializer causes these
warnings.filterwarnings("ignore", message="app_settings.USERNAME_REQUIRED is deprecated")
warnings.filterwarnings("ignore", message="app_settings.EMAIL_REQUIRED is deprecated")
warnings.filterwarnings("ignore", message="app_settings.AUTHENTICATION_METHOD is deprecated")
warnings.filterwarnings("ignore", message="Using slow pure-python SequenceMatcher")

