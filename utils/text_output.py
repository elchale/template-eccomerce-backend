import sys
import json
import colorama
from decimal import Decimal
from colorama import Fore, Back, Style
from contextlib import contextmanager

# Initialize colorama
colorama.init(autoreset=True)


@contextmanager
def redirect_stdout():
    """
    Context manager to temporarily redirect stdout to /dev/null.
    Use this to suppress verbose output during function calls.

    Example:
        with redirect_stdout():
            function_with_verbose_output()
    """
    original_stdout = sys.stdout
    sys.stdout = open('/dev/null', 'w')
    try:
        yield
    finally:
        sys.stdout.close()
        sys.stdout = original_stdout


def header(text):
    """
    Display a section header with cyan background.

    Args:
        text: The header text to display
    """
    print(f"\n{Fore.BLACK}{Back.CYAN}{Style.BRIGHT} {text} {Style.RESET_ALL}")


def info(text):
    """
    Display information text in blue.

    Args:
        text: The information text to display
    """
    print(f"{Fore.BLUE}{text}")


def success(text):
    """
    Display success message in green.

    Args:
        text: The success message to display
    """
    print(f"{Fore.GREEN}{Style.BRIGHT}{text}{Style.RESET_ALL}")


def warning(text):
    """
    Display warning message in yellow.

    Args:
        text: The warning message to display
    """
    print(f"{Fore.YELLOW}{text}")


def error(text):
    """
    Display error message in red.

    Args:
        text: The error message to display
    """
    print(f"{Fore.RED}{Style.BRIGHT}{text}{Style.RESET_ALL}")

def convert_decimals(obj):
    """
    Recursively convert Decimal objects to float.
    This helps ensure that objects like Decimal('0E-8')
    are printed in a more readable format.
    """
    if isinstance(obj, dict):
        return {k: convert_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimals(item) for item in obj]
    elif isinstance(obj, Decimal):
        return float(obj)
    else:
        return obj

def pretty(obj, title=None):
    """
    Pretty print any object (typically a dict) with an optional title.

    Args:
        obj: The object to print.
        title: Optional title to display above the object.
    """
    if title:
        print(f"\n{Fore.CYAN}{Style.BRIGHT}{title}:{Style.RESET_ALL}")

    # Convert Decimal values for nicer printing
    formatted_obj = convert_decimals(obj)

    # Adjusting indent and width to force multiline formatting.
    formatted = json.dumps(formatted_obj, indent=4, default=True)

    print(f"{Fore.RED}{formatted}{Style.RESET_ALL}")


def summary_start(title):
    """
    Start a summary section with a title.

    Args:
        title: The summary title
    """
    print(f"\n{Fore.BLACK}{Back.GREEN}{Style.BRIGHT} {title} {Style.RESET_ALL}")


def summary_error(title):
    """
    Start an error summary section with a title.

    Args:
        title: The error summary title
    """
    print(f"\n{Fore.BLACK}{Back.RED}{Style.BRIGHT} {title} {Style.RESET_ALL}")


def summary_item(text):
    """
    Display a summary item with a bullet point.

    Args:
        text: The summary item text
    """
    print(f"  • {text}")


def section_separator(char="=", length=50):
    """
    Display a section separator line.

    Args:
        char: The character to use for the separator
        length: The length of the separator line
    """
    print(f"\n{char * length}")
