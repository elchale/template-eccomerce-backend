"""
Constants for the SiteTheme singleton model.
These are the authoritative lists for server-side validation.
Frontend mirrors VALID_THEME_IDS in src/constants/themes.ts.
"""

VALID_THEME_IDS = (
    'classic',
    'dark',
    'elegant',
    'nature',
    'vibrant',
    'pastel',
    'tech',
    'minimal',
)

ALLOWED_CUSTOM_COLOR_KEYS = (
    '--color-primary',
    '--color-primary-hover',
    '--color-bg',
    '--color-bg-subtle',
    '--color-bg-accent',
    '--color-text',
    '--color-text-secondary',
    '--color-text-inverse',
    '--color-border',
    '--color-secondary',
    '--color-success',
    '--color-error',
    '--color-warning',
    '--color-info',
)
