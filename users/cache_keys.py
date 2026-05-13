# Cache keys for accounts app

# Used for two purposes:
# 1. Maps verification tokens to user IDs in auth.py with 30-minute timeout (1800 seconds)
#    Format: RESEND_VERIFICATION_TOKEN_CACHE_KEY + token = user_id
# 2. Used as a flag in ResendEmailConfirmationView to prevent sending multiple verification emails
#    Format: RESEND_VERIFICATION_TOKEN_CACHE_KEY + user_id = 1 (with 5-minute timeout/300 seconds)
#    This acts as a rate limiter to prevent multiple email requests within 5 minutes
RESEND_VERIFICATION_TOKEN_CACHE_KEY = 'resend_verification_token_'

# Maps user IDs back to their verification tokens in auth.py
# Used when a user fails email verification to provide them with the same token
# if they try again within 30 minutes (1800 seconds)
# Format: RESEND_VERIFICATION_TOKEN_REVERSED_CACHE_KEY + user_id = token
RESEND_VERIFICATION_TOKEN_REVERSED_CACHE_KEY = 'resend_verification_token_reversed_'

RUC_CACHE_KEY = 'ruc_emails'
