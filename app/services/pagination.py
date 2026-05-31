from flask import request


DEFAULT_PER_PAGE = 25
MAX_PER_PAGE = 100


def paginer(requete, *, per_page: int = DEFAULT_PER_PAGE):
    page = _int_arg("page", 1)
    per_page = max(1, min(int(per_page), MAX_PER_PAGE))
    return requete.paginate(page=page, per_page=per_page, error_out=False)


def _int_arg(name: str, default: int) -> int:
    try:
        value = int(request.args.get(name, default))
    except (TypeError, ValueError):
        return default
    return max(value, 1)
