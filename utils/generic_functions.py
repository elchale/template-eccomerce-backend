import re
import string
from random import SystemRandom, randrange

CAMEL_TO_SNAKE_RE = re.compile('((?<=[a-z0-9])[A-Z]|(?!^)[A-Z](?=[a-z]))')

def generate_random_string(length: int, symbols=None):
    symbols = symbols or string.ascii_letters + string.digits

    return ''.join(SystemRandom().choice(symbols) for _ in range(length))

def camel_to_snake_string(value: str) -> str:
    return CAMEL_TO_SNAKE_RE.sub(r'_\1', value).lower()

def get_rand_code(length=16):
    return "{number:0{precision}d}".format(
        number=randrange(10 ** (length - 1), 10 ** length - 1),
        precision=length,
    )
