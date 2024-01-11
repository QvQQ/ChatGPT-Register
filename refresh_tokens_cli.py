#!/usr/bin/env python
# coding=utf-8
# import sys; sys.path.append('.')
import time
from typing import List
from datetime import datetime, timedelta

# from database query
from sqlalchemy import or_, and_
from sqlalchemy.sql.elements import BinaryExpression
from models import Account
from database import get_session_maker

# for log
import logging
from rich.console import Console
from rich.logging import RichHandler

# for api
import requests
from retry import retry
# import subprocess

# for Typer Cli
import typer

# for configuration
from configurer import get_configuration
from urllib.parse import urljoin

# for debugging
# from rich.traceback import install; install(show_locals=True)  # noqa

app = typer.Typer()

# ------------------------------------------------------------------------------------
# 创建一个Rich的Console对象
console = Console()

# 配置日志，使用RichHandler
logging.basicConfig(
    level=logging.INFO,  # 设置日志级别
    format="%(message)s",  # 设置日志格式
    datefmt="%Y/%m/%d %H:%M:%S",  # 设置时间格式
    handlers=[RichHandler(console=console, rich_tracebacks=True, markup=True, show_path=False)]  # 使用RichHandler
)
log = logging.getLogger(__name__)

# ------------------------------------------------------------------------------------
# 初始化数据库（创建表）
DB_Session = get_session_maker('sqlite:///account.db')

# ------------------------------------------------------------------------------------
# 配置信息
config = get_configuration()
ninja_base_url = config.get('ninja_base_url', '')
pandora_next_base_url = config.get('pandora_next_base_url', '')
pandora_next_pool_token = config.get('pandora_next_pool_token', '')

# ------------------------------------------------------------------------------------
# 获取 web 的 access_token 与 session_token
@retry(tries=6, delay=1, backoff=2, exceptions=(requests.exceptions.HTTPError, requests.exceptions.Timeout, requests.exceptions.SSLError, requests.exceptions.ProxyError))
def get_web_access_and_session_token_pandora(email, password):
    # {
    #     'access_token': 'eyJhbGciOiJ...',
    #     'expires_in': 864000,
    #     'session_token': 'eyJhbGciOvZKyxEbl...',
    #     'token_type': 'Bearer'
    # }
    log.info('Fetching [bold white]access token[/bold white] and [bold white]session token[/bold white]...')

    url = urljoin(pandora_next_base_url, "api/auth/login")

    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    data = {
        'username': email,
        'password': password
    }

    res = requests.post(url, headers=headers, data=data, timeout=(20, 20))
    res.raise_for_status()

    json_content = res.json()
    if (
        (session_token := json_content.get('session_token')) and
        (access_token := json_content.get('access_token')) and
        (session_token_expire_at := datetime.utcnow() + timedelta(days=90)) and
        (access_token_expire_at := datetime.utcnow() + timedelta(seconds=json_content.get('expires_in'))) and
        len(session_token) > 0 and
        len(access_token) > 0  # noqa
    ):
        log.info('Got it.')
        return session_token, access_token, session_token_expire_at, access_token_expire_at  # noqa
    else:
        log.error(f'Fetch failed. json_content:')
        log.error(json_content)

    return None, None, None, None

@retry(tries=6, delay=1, backoff=2, exceptions=(requests.exceptions.HTTPError, requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.SSLError, requests.exceptions.ProxyError))
def get_web_access_and_session_token_ninja(email, password):
    # {
    #     "user": {
    #         "id": "user-LbRB6Cm....",
    #         "name": "xxx@xxx",
    #         "email": "xxx@xxx",
    #         "image": "https://s.gravatar.com/avatar/x?s=480&r=pg&d=https%3A%2F%2Fcdn.auth0.com%2Favatars%2Fth.png",
    #         "picture": "https://s.gravatar.com/avatar/x?s=480&r=pg&d=https%3A%2F%2Fcdn.auth0.com%2Favatars%2Fth.png",
    #         "idp": "auth0",
    #         "iat": 1704879831,
    #         "mfa": false,
    #         "groups": [],
    #         "intercom_hash": "1d6488c9xxxxxxxx"
    #     },
    #     "expires": "2024-04-09T09:43:51.862Z",
    #     "accessToken": "eyJhbGciOiJSU...",
    #     "authProvider": "auth0",
    #     "session_token": "eyJhbGciOiJkaXI..."
    # }

    log.info('Fetching [bold white]access token[/bold white] and [bold white]session token[/bold white]...')

    url = urljoin(ninja_base_url, "auth/token")

    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    data = {
        'username': email,
        'password': password
    }

    try:
        res = requests.post(url, headers=headers, data=data, timeout=(20, 20))
        res.raise_for_status()
    except requests.exceptions.HTTPError as http_err:
        log.error(f'HTTP Error. content: {http_err.response.text}')
        raise
    except requests.exceptions.ConnectionError as con_err:
        raise

    json_content = res.json()
    if (
        (session_token := json_content.get('session_token')) and
        (access_token := json_content.get('accessToken')) and
        (session_token_expire_at := datetime.fromisoformat(json_content.get('expires').rstrip('Z')).replace(tzinfo=None)) and
        (access_token_expire_at := datetime.utcnow() + timedelta(days=10)) and
        len(session_token) > 0 and
        len(access_token) > 0  # noqa
    ):
        log.info('Got it.')
        return session_token, access_token, session_token_expire_at, access_token_expire_at  # noqa
    else:
        log.error(f'Fetch failed. json_content:')
        log.error(json_content)

    return None, None, None, None

# ------------------------------------------------------------------------------------
# 刷新 web 的 access_token 与 session_token
@retry(tries=6, delay=1, backoff=2, exceptions=(requests.exceptions.HTTPError, requests.exceptions.Timeout, requests.exceptions.SSLError, requests.exceptions.ProxyError))
def refresh_web_session_token_pandora(session_token):
    # {
    #     'access_token': 'eyJhbGciOiJ...',
    #     'expires_in': 864000,
    #     'session_token': 'eyJhbGciOvZKyxEbl...',
    #     'token_type': 'Bearer'
    # }

    log.info('Refreshing current [bold white]session token[/bold white]...')

    url = urljoin(pandora_next_base_url, "api/auth/session")

    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    data = {
        'session_token': session_token
    }

    res = requests.post(url, headers=headers, data=data, timeout=(20, 20))
    res.raise_for_status()

    json_content = res.json()
    if (
        (session_token := json_content.get('session_token')) and
        (access_token := json_content.get('access_token')) and
        (session_token_expire_at := datetime.utcnow() + timedelta(days=90)) and
        (access_token_expire_at := datetime.utcnow() + timedelta(seconds=json_content.get('expires_in'))) and
        len(session_token) > 0 and
        len(access_token) > 0  # noqa
    ):
        log.info('Got it.')
        return session_token, access_token, session_token_expire_at, access_token_expire_at  # noqa
    else:
        log.error(f'Fetch failed. json_content:')
        log.error(json_content)

    return None, None, None, None

@retry(tries=6, delay=1, backoff=2, exceptions=(requests.exceptions.HTTPError, requests.exceptions.Timeout, requests.exceptions.SSLError, requests.exceptions.ProxyError))
def refresh_web_session_token_ninja(session_token):
    # {
    #     "user": {
    #         "id": "user-LbRB6Cm....",
    #         "name": "xxx@xxx",
    #         "email": "xxx@xxx",
    #         "image": "https://s.gravatar.com/avatar/x?s=480&r=pg&d=https%3A%2F%2Fcdn.auth0.com%2Favatars%2Fth.png",
    #         "picture": "https://s.gravatar.com/avatar/x?s=480&r=pg&d=https%3A%2F%2Fcdn.auth0.com%2Favatars%2Fth.png",
    #         "idp": "auth0",
    #         "iat": 1704879831,
    #         "mfa": false,
    #         "groups": [],
    #         "intercom_hash": "1d6488c9xxxxxxxx"
    #     },
    #     "expires": "2024-04-09T09:43:51.862Z",
    #     "accessToken": "eyJhbGciOiJSU...",
    #     "authProvider": "auth0",
    #     "session_token": "eyJhbGciOiJkaXI..."
    # }

    log.info('Refreshing current [bold white]session token[/bold white]...')

    url = urljoin(ninja_base_url, "auth/refresh_session")

    headers = {
        'Authorization': f'Bearer {session_token}'
    }

    res = requests.post(url, headers=headers, timeout=(20, 20))
    res.raise_for_status()

    json_content = res.json()
    if (
            (session_token := json_content.get('session_token')) and
            (access_token := json_content.get('accessToken')) and
            (session_token_expire_at := datetime.fromisoformat(json_content.get('expires').rstrip('Z')).replace(tzinfo=None)) and
            (access_token_expire_at := datetime.utcnow() + timedelta(days=10)) and
            len(session_token) > 0 and
            len(access_token) > 0  # noqa
    ):
        log.info('Got it.')
        return session_token, access_token, session_token_expire_at, access_token_expire_at  # noqa
    else:
        log.error(f'Fetch failed. json_content:')
        log.error(json_content)

    return None, None, None, None

# ------------------------------------------------------------------------------------
# 获取 platform 的 access_token 与 refresh_token
@retry(tries=6, delay=1, backoff=2, exceptions=(requests.exceptions.HTTPError, requests.exceptions.Timeout, requests.exceptions.SSLError, requests.exceptions.ProxyError))
def get_platform_access_and_refresh_token_and_sess_key_pandora(email, password):
    # {
    #     "login_info": {
    #         "age_verification": {
    #             "is_required": false
    #         },
    #         "invites": [],
    #         "ip_country": "US",
    #         "object": "login",
    #         "user": {
    #             "amr": [],
    #             "cookie_consent": {
    #                 "is_required": false
    #             },
    #             "created": 1704038708,
    #             "email": "xxx@xxx",
    #             "groups": [],
    #             "id": "user-LbRB6xxx",
    #             "intercom_hash": "1d6488c9xxxxxxxxxx",
    #             "name": "the_one",
    #             "object": "user",
    #             "orgs": {
    #                 "data": [
    #                     {
    #                         "created": 1704038708,
    #                         "description": "Personal org for xxx@xxx",
    #                         "groups": [],
    #                         "id": "org-9xcADZxxx",
    #                         "is_default": true,
    #                         "name": "user-lbrb6cxxx",
    #                         "object": "organization",
    #                         "personal": true,
    #                         "role": "owner",
    #                         "settings": {
    #                             "threads_ui_visibility": "NONE"
    #                         },
    #                         "title": "Personal"
    #                     }
    #                 ],
    #                 "object": "list"
    #             },
    #             "phone_number": null,
    #             "picture": "https://s.gravatar.com/avatar/xxx?s=480&r=pg&d=https%3A%2F%2Fcdn.auth0.com%2Favatars%2Fth.png",
    #             "platform_ui_refresh": true,
    #             "session": {
    #                 "created": 1704038709,
    #                 "last_use": null,
    #                 "name": null,
    #                 "object": "api_key",
    #                 "publishable": false,
    #                 "sensitive_id": "sess-CPBE4X7xxxxx",
    #                 "tracking_id": "key_smtWOxxx"
    #             }
    #         }
    #     },
    #     "token_info": {
    #         "access_token": "eyJhbGciOiJSUzIxxx",
    #         "expires_in": 864000,
    #         "id_token": "eyJhbGciOiJSUzI1NiIsxxx",
    #         "refresh_token": "v1.MbVtfzUljxxx",
    #         "scope": "openid profile email offline_access",
    #         "token_type": "Bearer"
    #     }
    # }
    log.info('Fetching [bold white]access token[/bold white] and [bold white]refresh token[/bold white]...')

    url = urljoin(pandora_next_base_url, "api/auth/platform/login")

    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    data = {
        'username': email,
        'password': password,
        'prompt': 'login'
    }

    try:
        res = requests.post(url, headers=headers, data=data, timeout=(20, 20))
        res.raise_for_status()
    except requests.exceptions.HTTPError as http_err:
        log.error(f'HTTP Error. content: {http_err.response.text}')
        raise
    except requests.exceptions.ConnectionError as con_err:
        raise

    json_content = res.json()
    if (
        (token_info := json_content.get('token_info')) and
        (login_info := json_content.get('login_info')) and
        (refresh_token := token_info.get('refresh_token')) and
        (access_token := token_info.get('access_token')) and
        (refresh_token_expire_at := datetime.utcnow() + timedelta(days=10)) and  # TODO: 不知道 refresh_token 的有效期，暂定为10天
        (access_token_expire_at := datetime.utcnow() + timedelta(seconds=token_info.get('expires_in'))) and
        (sess_key := login_info.get('user', {}).get('session', {}).get('sensitive_id')) and  # noqa
        len(refresh_token) > 0 and  # noqa
        len(access_token) > 0  # noqa
    ):
        log.info('Got it.')
        return refresh_token, access_token, refresh_token_expire_at, access_token_expire_at, sess_key  # noqa
    else:
        log.error(f'Fetch failed. json_content:')
        log.error(json_content)

    return None, None, None, None, None

@retry(tries=6, delay=1, backoff=2, exceptions=(requests.exceptions.HTTPError, requests.exceptions.Timeout, requests.exceptions.SSLError, requests.exceptions.ProxyError))
def get_platform_access_and_refresh_token_ninja(email, password):
    # {
    #     "access_token": "eyJhbGciOiJSU...",
    #     "refresh_token": "v1.MRDL3Axw...",
    #     "id_token": "eyJhbGciOiJSU...",
    #     "expires_in": 864000
    # }
    log.info('Fetching [bold white]access token[/bold white] and [bold white]refresh token[/bold white]...')

    url = urljoin(ninja_base_url, "auth/token")

    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    data = {
        'username': email,
        'password': password,
        'option': 'platform'
    }

    try:
        res = requests.post(url, headers=headers, data=data, timeout=(20, 20))
        res.raise_for_status()
    except requests.exceptions.HTTPError as http_err:
        log.error(f'HTTP Error. content: {http_err.response.text}')
        raise
    except requests.exceptions.ConnectionError as con_err:
        raise

    json_content = res.json()
    if (
        (refresh_token := json_content.get('refresh_token')) and
        (access_token := json_content.get('access_token')) and
        (refresh_token_expire_at := datetime.utcnow() + timedelta(days=10)) and  # TODO: 不知道 refresh_token 的有效期，暂定为10天
        (access_token_expire_at := datetime.utcnow() + timedelta(seconds=json_content.get('expires_in'))) and
        len(refresh_token) > 0 and
        len(access_token) > 0  # noqa
    ):
        log.info('Got it.')
        return refresh_token, access_token, refresh_token_expire_at, access_token_expire_at  # noqa
    else:
        log.error(f'Fetch failed. json_content:')
        log.error(json_content)

    return None, None, None, None

# ------------------------------------------------------------------------------------
# 刷新 platform 的 access_token 与 refresh_token
@retry(tries=6, delay=1, backoff=2, exceptions=(requests.exceptions.HTTPError, requests.exceptions.Timeout, requests.exceptions.SSLError, requests.exceptions.ProxyError))
def refresh_platform_refresh_token_pandora(refresh_token):
    # {
    #     "access_token": "eyJhbGciOiJSUzxxxx",
    #     "expires_in": 864000,
    #     "id_token": "eyJhbGciOiJSUzI1xxxx",
    #     "refresh_token": "v1.MrVtfzUljZxxxxx",
    #     "scope": "openid profile email offline_access",
    #     "token_type": "Bearer"
    # }
    log.info('Refreshing current [bold white]refresh token[/bold white]...')

    url = urljoin(pandora_next_base_url, "api/auth/platform/refresh")

    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    data = {
        'refresh_token': refresh_token
    }

    try:
        res = requests.post(url, headers=headers, data=data, timeout=(20, 20))
        res.raise_for_status()
    except requests.exceptions.HTTPError as http_err:
        log.error(f'HTTP Error. content: {http_err.response.text}')
        raise
    except requests.exceptions.ConnectionError as con_err:
        raise

    json_content = res.json()
    if (
        (refresh_token := json_content.get('refresh_token')) and
        (access_token := json_content.get('access_token')) and
        (refresh_token_expire_at := datetime.utcnow() + timedelta(days=10)) and  # TODO: 不知道 refresh_token 的有效期，暂定为10天
        (access_token_expire_at := datetime.utcnow() + timedelta(seconds=json_content.get('expires_in'))) and
        len(refresh_token) > 0 and
        len(access_token) > 0  # noqa
    ):
        log.info('Got it.')
        return refresh_token, access_token, refresh_token_expire_at, access_token_expire_at  # noqa
    else:
        log.error(f'Fetch failed. json_content:')
        log.error(json_content)

    return None, None, None, None

@retry(tries=6, delay=1, backoff=2, exceptions=(requests.exceptions.HTTPError, requests.exceptions.Timeout, requests.exceptions.SSLError, requests.exceptions.ProxyError))
def refresh_platform_refresh_token_ninja(refresh_token):
    # {
    #     "access_token": "eyJhbGciOiJSU...",
    #     "refresh_token": "v1.MRDL3Axw...",
    #     "id_token": "eyJhbGciOiJSU...",
    #     "expires_in": 864000
    # }
    log.info('Refreshing current [bold white]refresh token[/bold white]...')

    url = urljoin(ninja_base_url, "auth/refresh_token")

    headers = {
        'Authorization': f'Bearer {refresh_token}',
    }

    try:
        res = requests.post(url, headers=headers, timeout=(20, 20))
        res.raise_for_status()
    except requests.exceptions.HTTPError as http_err:
        log.error(f'HTTP Error. content: {http_err.response.text}')
        raise
    except requests.exceptions.ConnectionError as con_err:
        raise

    json_content = res.json()
    if (
        (refresh_token := json_content.get('refresh_token')) and
        (access_token := json_content.get('access_token')) and
        (refresh_token_expire_at := datetime.utcnow() + timedelta(days=10)) and  # TODO: 不知道 refresh_token 的有效期，暂定为10天
        (access_token_expire_at := datetime.utcnow() + timedelta(seconds=json_content.get('expires_in'))) and
        len(refresh_token) > 0 and
        len(access_token) > 0  # noqa
    ):
        log.info('Got it.')
        return refresh_token, access_token, refresh_token_expire_at, access_token_expire_at  # noqa
    else:
        log.error(f'Fetch failed. json_content:')
        log.error(json_content)

    return None, None, None, None

# ------------------------------------------------------------------------------------
# 获取 platform 的 sess key
@retry(tries=6, delay=1, backoff=2, exceptions=(requests.exceptions.HTTPError, requests.exceptions.Timeout, requests.exceptions.SSLError, requests.exceptions.ProxyError))
def get_platform_sess_key_pandora_(email, password):

    raise NotImplemented('get_platform_sess_key_pandora')
@retry(tries=6, delay=1, backoff=2, exceptions=(requests.exceptions.HTTPError, requests.exceptions.Timeout, requests.exceptions.SSLError, requests.exceptions.ProxyError))
def get_platform_sess_key_ninja(access_token):
    # {
    #     "object": "login",
    #     "user": {
    #         "object": "user",
    #         "id": "user-LbRB6C...",
    #         "email": "xxx@xxx",
    #         "name": "the_one",
    #         "picture": "https://s.gravatar.com/avatar/xxx?s=480&r=pg&d=https%3A%2F%2Fcdn.auth0.com%2Favatars%2Fth.png",
    #         "created": 1704038708,
    #         "session": {
    #             "sensitive_id": "sess-CPBE4xxxxxxxxxxxxx",
    #             "object": "api_key",
    #             "name": null,
    #             "created": 1704038709,
    #             "last_use": null,
    #             "publishable": false
    #         }
    #     },
    #     "invites": []
    # }
    log.info('Fetching current [bold white]sess key[/bold white]...')

    url = urljoin(ninja_base_url, "auth/sess_token")

    headers = {
        'Authorization': f'Bearer {access_token}',
    }

    try:
        res = requests.post(url, headers=headers, timeout=(20, 20))
        res.raise_for_status()
    except requests.exceptions.HTTPError as http_err:
        log.error(f'HTTP Error. content: {http_err.response.text}')
        raise
    except requests.exceptions.ConnectionError as con_err:
        raise

    json_content = res.json()
    if (
        (sess_key := json_content.get('user', {}).get('session', {}).get('sensitive_id')) and
        len(sess_key) > 0
    ):
        log.info('Got it.')
        return sess_key
    else:
        log.error(f'Fetch failed. json_content:')
        log.error(json_content)

    return None

# ------------------------------------------------------------------------------------
# 获取 PandoraNext 的 share_token 与 pool_token
@retry(tries=6, delay=1, backoff=2, exceptions=(requests.exceptions.HTTPError, requests.exceptions.Timeout, requests.exceptions.SSLError, requests.exceptions.ProxyError))
def get_pandora_share_token(access_token):
    log.info('Fetching corresponding [bold white]share token[/bold white]...')

    url = urljoin(pandora_next_base_url, "api/token/register")

    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    data = {
        'unique_name': 'demo',
        'access_token': access_token,
        'site_limit': '',
        'expires_in': 0,
        'show_conversations': True,
        'show_userinfo': True
    }

    res = requests.post(url, headers=headers, data=data, timeout=(20, 20))
    res.raise_for_status()

    json_content = res.json()
    if (
        (share_token := json_content.get('token_key')) and
        (expire_at := json_content.get('expire_at')) and
        len(share_token) > 0 and
        expire_at > time.time()  # noqa
    ):
        log.info('Got it.')
        return share_token
    else:
        log.error(f'Fetch failed. json_content:')
        log.error(json_content)

    return None

@retry(tries=6, delay=1, backoff=2, exceptions=(requests.exceptions.HTTPError, requests.exceptions.Timeout, requests.exceptions.SSLError, requests.exceptions.ProxyError))
def refresh_pandora_pool_token(share_tokens):
    log.info(f'Fetching corresponding [bold white]pool token[/bold white] using {len(share_tokens)} share_tokens...')

    if not (0 < len(share_tokens) <= 100):
        log.error(f'The number of share_tokens must be less than 100! Current: {len(share_tokens)}.')
        return None

    url = urljoin(pandora_next_base_url, "api/pool/update")

    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    data = {
        'share_tokens': '\n'.join(share_tokens),
        'pool_token': pandora_next_pool_token
    }

    res = requests.post(url, headers=headers, data=data, timeout=(20, 20))
    res.raise_for_status()

    # {'count': 30, 'pool_token': 'pk-xxxxxxxxxxxxx'}
    json_content = res.json()

    if (
        (pool_token := json_content.get('pool_token')) and
        len(pool_token) > 0  # noqa
    ):
        log.info('Got it.')
        return pool_token
    else:
        log.error(f'Fetch failed. json_content:')
        log.error(json_content)

    return None

# ------------------------------------------------------------------------------------
# 检索数据库进行 web tokens 的获取与刷新
def refresh_web_tokens(use_ninja: bool, count: int, conditions: List[BinaryExpression]):

    # 获取可用账号，刷新或获取 web session_token、access_token
    # 并获取相应的 share_token
    with (DB_Session() as session):

        # 获取统计信息
        matching_field_count = session.query(Account).filter(and_(*conditions, Account.is_active == 1)).count()
        total_field_count = session.query(Account).filter(Account.is_active == 1).count()

        log.info(f'当前数据库账号总数: {total_field_count}，符合条件的账号数: {matching_field_count}')
        log.info(f'刷新{f"{min(count, matching_field_count)}个" if count != -1 else "所有"}账号的 [bold green]WEB[/bold green] [bold white]session/access{"/share token" if not use_ninja else ""}[/bold white]...')

        # 查询条件：conditions 且 is_active 为 1
        records = session.query(Account).filter(
            and_(
                *conditions,
                Account.is_active == 1
            )
        )

        # 是否查询所有的数据
        if count != -1:
            records = records.limit(count)
        records = records.all()

        if records:
            for i, record in enumerate(records):
                # 获取 email 和 password
                email = record.email
                password = record.password

                log.info(f'[bold white]({i + 1}/{len(records)}) Processing...[/bold white]')
                log.info(f'[yellow]Email:[/yellow] [blue]{email}[/blue]')
                log.info(f'[yellow]Password:[/yellow] [blue]{password}[/blue]')

                obtain = record.web_session_token is None

                log.info(f'[bold white]session_token[/bold white] {"不" if obtain else "已"}存在，进行{"获取" if obtain else "刷新"}...')

                try:
                    # 使用函数处理获取 session token 和 access token
                    if use_ninja and obtain:
                        # 使用 ninja 获取 session token 和 access token
                        session_token, access_token, session_token_expire_at, access_token_expire_at = \
                            get_web_access_and_session_token_ninja(email, password)

                    elif use_ninja and not obtain:
                        # 使用 ninja 刷新 session token 和 access token
                        session_token, access_token, session_token_expire_at, access_token_expire_at = \
                            refresh_web_session_token_ninja(record.web_session_token)

                    elif not use_ninja and obtain:
                        # 使用 PandoraNext 获取 session token 和 access token
                        session_token, access_token, session_token_expire_at, access_token_expire_at = \
                            get_web_access_and_session_token_pandora(email, password)

                    else:
                        # 使用 PandoraNext 刷新 session token 和 access token
                        session_token, access_token, session_token_expire_at, access_token_expire_at = \
                            refresh_web_session_token_pandora(record.web_session_token)

                except requests.exceptions.HTTPError as http_err:
                    log.error(f'[bold red]对账号\\[{record.id}]({email}){"获取" if obtain else "刷新"}失败！请检查！[/bold red]')
                    log.error('[bold red]Continuing...[/bold red]')
                    continue

                # 更新记录
                if session_token and access_token:
                    log.info(f'更新数据库字段...')
                    record.web_session_token = session_token
                    record.web_access_token = access_token
                    record.web_refresh_at = datetime.utcnow()
                    record.web_session_token_expire_at = session_token_expire_at
                    record.web_access_token_expire_at = access_token_expire_at
                    record.is_active = 1
                    session.commit()
                    log.info(f'更新成功！')
                else:
                    log.info(f'[bold red]!!! 此处应当按照错误情况进行处理 !!![/bold red]')
                    continue

                # 对 share_token 的处理
                if not use_ninja:
                    try:
                        # 不论是首次获取还是刷新，都更新 share token
                        share_token = get_pandora_share_token(access_token)
                    except requests.exceptions.HTTPError as http_err:
                        log.error(f'[bold red]对账号\\[{record.id}]({email})刷新失败！请检查！[/bold red]')
                        log.error('[bold red]Continuing...[/bold red]')
                        continue

                    if share_token:
                        log.info(f'更新数据库字段...')
                        record.pandora_share_token = share_token
                        session.commit()
                        log.info(f'更新成功！')
                    else:
                        log.info(f'[bold red]!!! 此处应当按照错误情况进行处理 !!![/bold red]')
                else:
                    log.info('`use_ninja` == True, 跳过 pandora_share_token 的获取...')

        log.warning('[bold green]未找到更多符合条件的记录！已全部处理完毕。[/bold green]')

# ------------------------------------------------------------------------------------
# 检索数据库进行 platform tokens 的获取与刷新
def refresh_platform_tokens(use_ninja: bool, count: int, conditions: List[BinaryExpression]):

    # 获取可用账号，刷新或获取 platform session_token、refresh_token
    # 并获取相应的 share_token
    with (DB_Session() as session):

        # 获取统计信息
        matching_field_count = session.query(Account).filter(and_(*conditions, Account.is_active == 1)).count()
        total_field_count = session.query(Account).filter(Account.is_active == 1).count()

        log.info(f'当前数据库账号总数: {total_field_count}，符合条件的账号数: {matching_field_count}')
        log.info(f'刷新{f"{min(count, matching_field_count)}个" if count != -1 else "所有"}账号的 [bold green]PLATFORM[/bold green] [bold white]refresh/access token[/bold white]...')

        # 查询条件：conditions 且 is_active 为 1
        records = session.query(Account).filter(
            and_(
                *conditions,
                Account.is_active == 1
            )
        )

        # 是否查询所有的数据
        if count != -1:
            records = records.limit(count)
        records = records.all()

        if records:
            for i, record in enumerate(records):
                # 获取 email 和 password
                email = record.email
                password = record.password

                log.info(f'[bold white]({i + 1}/{len(records)}) Processing...[/bold white]')
                log.info(f'[yellow]Email:[/yellow] [blue]{email}[/blue]')
                log.info(f'[yellow]Password:[/yellow] [blue]{password}[/blue]')

                obtain = record.platform_refresh_token is None

                log.info(f'[bold white]refresh_token[/bold white] {"不" if obtain else "已"}存在，进行{"获取" if obtain else "刷新"}...')

                try:
                    # 使用函数处理获取 refresh token 和 access token
                    if use_ninja and obtain:
                        # 使用 ninja 获取 refresh token 和 access token
                        refresh_token, access_token, refresh_token_expire_at, access_token_expire_at = \
                            get_platform_access_and_refresh_token_ninja(email, password)

                    elif use_ninja and not obtain:
                        # 使用 ninja 刷新 refresh token 和 access token
                        refresh_token, access_token, refresh_token_expire_at, access_token_expire_at = \
                            refresh_platform_refresh_token_ninja(record.platform_refresh_token)

                    elif not use_ninja and obtain:
                        # 使用 PandoraNext 获取 refresh token 和 access token 和 sess key
                        refresh_token, access_token, refresh_token_expire_at, access_token_expire_at, sess_key = \
                            get_platform_access_and_refresh_token_and_sess_key_pandora(email, password)

                    else:
                        # 使用 PandoraNext 刷新 refresh token 和 access token 和 sess key
                        # refresh_token, access_token, refresh_token_expire_at, access_token_expire_at = \
                        #     refresh_platform_refresh_token_pandora(record.platform_refresh_token)
                        # TODO: 使用 PandoraNext 无法从刷新中直接获取 sess key
                        refresh_token, access_token, refresh_token_expire_at, access_token_expire_at, sess_key = \
                            get_platform_access_and_refresh_token_and_sess_key_pandora(email, password)

                except requests.exceptions.HTTPError as http_err:
                    log.error(f'[bold red]对账号\\[{record.id}]({email}){"获取" if obtain else "刷新"}失败！请检查！[/bold red]')
                    log.error('[bold red]Continuing...[/bold red]')
                    continue

                # 更新记录
                if refresh_token and access_token:
                    log.info(f'更新数据库字段...')
                    record.platform_refresh_token = refresh_token
                    record.platform_access_token = access_token
                    record.platform_refresh_at = datetime.utcnow()
                    record.platform_refresh_token_expire_at = refresh_token_expire_at
                    record.platform_access_token_expire_at = access_token_expire_at
                    record.is_active = 1
                    session.commit()
                    log.info(f'更新成功！')
                else:
                    log.info(f'[bold red]!!! 此处应当按照错误情况进行处理 !!![/bold red]')
                    continue

                # 对 sess key 的处理
                # if not (not use_ninja and obtain):  # 如果使用 PandoraNext 且首次获取，那么已经获取过 sess_key 了
                if use_ninja:  # 如果使用 PandoraNext 刷新或获取，那么已经获取过 sess_key 了
                    try:
                        # 不论是首次获取还是刷新，都获取 sess_key
                        # if use_ninja:
                        #     sess_key = get_platform_sess_key_ninja(access_token)
                        # else:
                        #     log.warning(f'[red]使用 PandoraNext 刷新 [bold red]PLATFORM[/bold red] refresh token 与 access token 无法获取 sess_key，跳过...[/red]')
                        #     sess_key = None  # get_platform_sess_key_pandora()
                        sess_key = get_platform_sess_key_ninja(access_token)

                    except requests.exceptions.HTTPError as http_err:
                        log.error(f'[bold red]对账号\\[{record.id}]({email})刷新失败！请检查！[/bold red]')
                        log.error('[bold red]Continuing...[/bold red]')
                        continue
                else:
                    log.info(f'[bold white]sess key[/bold white] 已获取!')

                if sess_key:
                    log.info(f'更新数据库字段...')
                    record.platform_sess_key = sess_key
                    session.commit()
                    log.info(f'更新成功！')
                else:
                    log.info(f'[bold red]!!! 此处应当按照错误情况进行处理 !!![/bold red]')

        log.warning('[bold green]未找到更多符合条件的记录！已全部处理完毕。[/bold green]')

def assemble_pool_token(count: int):

    # 是否过多
    if count > 100:
        log.warning('最多一次组装100个 share token ！')
    count = min(count, 100)

    # 获取可用账号，生成 pool_token
    with DB_Session() as session:

        # 获取统计信息
        matching_field_count = session.query(Account).filter(and_(Account.pandora_share_token.is_not(None), Account.is_active == 1)).count()
        total_field_count = session.query(Account).filter(Account.is_active == 1).count()

        log.info(f'当前数据库账号总数: {total_field_count}，可组装的账号数: {matching_field_count}')
        log.info(f'根据已存储的 [bold white]share token[/bold white] 组建 [bold white]pool token[/bold white]...')

        # 查询条件：share_token 不为 NULL 且 is_active 为 1
        records = session.query(Account.pandora_share_token).filter(
            and_(
                Account.pandora_share_token.is_not(None),
                Account.is_active == 1
            )
        ).limit(count).all()

        if records:
            share_tokens = [record[0] for record in records]

            try:
                # 组装 Pool Token
                pool_token = refresh_pandora_pool_token(share_tokens)
            except requests.exceptions.HTTPError as http_err:
                log.error(f'[bold red]组装 Pool Token 失败！请检查！[/bold red]')
                log.error('[bold red]Continuing...[/bold red]')
                return

            log.warning('[bold white]Pool token[/bold white] [bold green]已生成完毕。[/bold green]')
            log.warning(pool_token)

        log.warning('[bold green]未找到更多符合条件的记录！已全部处理完毕。[/bold green]')

# ------------------------------------------------------------------------------------

@app.command(help='Obtain new session tokens if not exists.')
def obtain(ninja: bool = typer.Option(False, help='Use ninja as backend. Default to PandoraNext.'),
           type: str = typer.Option('web', help='Obtain tokens of web or platform.'),  # noqa
           count: int = typer.Option(10, help='Number of accounts to process.')):

    if ninja:
        if not ninja_base_url:
            log.error(f'[bold red]Please set ninja_base_url in your configuration file![/bold red]')
            exit(-1)
    else:
        if not pandora_next_base_url:
            log.error(f'[bold red]Please set pandora_next_base_url in your configuration file![/bold red]')
            exit(-1)

    if type == 'web':
        log.info("[green]Obtaining [bold green]WEB[/bold green] session token and refresh all tokens...[/green]")

        refresh_web_tokens(
            use_ninja=ninja,
            count=count,
            conditions=[
                # session token 为空或 已过期
                or_(
                    Account.web_session_token.is_(None),
                    Account.web_session_token_expire_at.is_(None),
                    Account.web_session_token_expire_at < datetime.utcnow()
                )
            ]
        )
    elif type == 'platform':
        log.info("[green]Obtaining [bold green]PLATFORM[/bold green] refresh/access tokens and sess key...[/green]")

        refresh_platform_tokens(
            use_ninja=ninja,
            count=count,
            conditions=[
                # refresh token 为空或 已过期
                or_(
                    Account.platform_refresh_token.is_(None),
                    Account.platform_refresh_token_expire_at.is_(None),
                    Account.platform_refresh_token_expire_at < datetime.utcnow(),
                )
            ]
        )
    else:
        log.error("[red]Wrong [bold red]type[/bold red]! Choose one from web/platform![/red]")


@app.command(help='Refresh tokens.')
def refresh(ninja: bool = typer.Option(False, help='Use ninja as backend. Default to PandoraNext.'),
            type: str = typer.Option('web', help='Obtain tokens of web or platform.'),  # noqa
            empty_only: bool = typer.Option(False, help='Refresh account only if its [web](share token) or [platform](sess key) is empty.'),
            count: int = typer.Option(-1, help='Number of accounts to process.'),
            remaining: int = typer.Option(5, help='Number of days remaining until expiration.')):

    if ninja:
        if not ninja_base_url:
            log.error(f'[bold red]Please set ninja_base_url in your configuration file![/bold red]')
            exit(-1)
    else:
        if not pandora_next_base_url:
            log.error(f'[bold red]Please set pandora_next_base_url in your configuration file![/bold red]')
            exit(-1)

    log.info(f"[bold green]Refreshing tokens for {count if count != -1 else 'ALL'} accounts that [bold red]expire within {remaining} days[/bold red].[/bold green]")

    # 计算当前 UTC 时间后 N 天的时间
    N_days_after = datetime.utcnow() + timedelta(days=remaining)

    if type == 'web':
        log.info("[green]Refreshing existed [bold green]WEB[/bold green] session, share and access tokens.[/green]")

        refresh_web_tokens(
            use_ninja=ninja,
            count=count,
            conditions=[
                # session token 有效
                Account.web_session_token.is_not(None),
                Account.web_session_token_expire_at > datetime.utcnow(),
                # access token 临近过期
                or_(
                    Account.web_access_token_expire_at <= N_days_after,
                    Account.web_access_token_expire_at.is_(None)
                ),
                # 是否只刷新空的 share token
                Account.pandora_share_token.is_(None) if empty_only else True,
            ]
        )
    elif type == 'platform':
        log.info("[green]Refreshing existed [bold green]PLATFORM[/bold green] refresh/access tokens.[/green]")

        refresh_platform_tokens(
            use_ninja=ninja,
            count=count,
            conditions=[
                # refresh token 有效
                Account.platform_refresh_token.is_not(None),
                Account.platform_refresh_token_expire_at > datetime.utcnow(),
                # access token 临近过期
                or_(
                    Account.platform_access_token_expire_at <= N_days_after,
                    Account.platform_access_token_expire_at.is_(None)
                ),
                # 是否只刷新空的 sess key
                Account.platform_sess_key.is_(None) if empty_only else True,
            ]
        )
    else:
        log.error("[bold red]Wrong type! Choose one from web/platform![/bold red]")


@app.command(help='Assemble pool token')
def assemble(count: int = typer.Option(100, help='Number of accounts to process')):

    if not pandora_next_base_url:
        log.error(f'[bold red]Please set pandora_next_base_url in your configuration file![/bold red]')
        exit(-1)

    log.info(f"[bold green]Assembling pool tokens for {count} accounts.[/bold green]")
    assemble_pool_token(count=count)


if __name__ == '__main__':
    app()
