#!/usr/bin/env python
# coding=utf-8
import time
from typing import List

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

# for Typer Cli
import typer

# for configuration
from configurer import get_configuration
from urllib.parse import urljoin


app = typer.Typer()

# ------------------------------------------------------------------------------------
# 初始化数据库（创建表）
DB_Session = get_session_maker('sqlite:///account.db')

# ------------------------------------------------------------------------------------
# 创建一个Rich的Console对象
console = Console()

# 配置日志，使用RichHandler
logging.basicConfig(
    level="INFO",  # 设置日志级别
    format="%(message)s",  # 设置日志格式
    datefmt="%Y/%m/%d %H:%M:%S",  # 设置时间格式
    handlers=[RichHandler(console=console, rich_tracebacks=True, markup=True, show_path=False)]  # 使用RichHandler
)
log = logging.getLogger(__name__)

# ------------------------------------------------------------------------------------
# 配置信息
config = get_configuration()
pandora_next_base_url = config.get('pandora_next_base_url')
pandora_next_pool_token = config.get('pandora_next_pool_token', '')

# 检查配置
if not pandora_next_base_url:
    log.critical('Please review your environment variable configurations!')
    exit(-1)

# ------------------------------------------------------------------------------------


@retry(tries=6, delay=1, backoff=2, exceptions=(requests.exceptions.HTTPError,))
def get_access_and_session_token(email, password):
    log.info('Fetching [bold white]access token[/bold white] and [bold white]session token[/bold white]...')

    url = urljoin(pandora_next_base_url, "/api/auth/login")

    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    data = {
        'username': email,
        'password': password
    }

    res = requests.post(url, headers=headers, data=data)
    res.raise_for_status()

    json_content = res.json()
    if (
        (session_token := json_content.get('session_token')) and
        (access_token := json_content.get('access_token')) and
        len(session_token) > 0 and
        len(access_token) > 0  # noqa
    ):
        log.info('Got it.')
        return session_token, access_token
    else:
        log.error(f'Fetch failed. json_content:')
        log.error(json_content)

    return None, None


@retry(tries=1, delay=1, backoff=2, exceptions=(requests.exceptions.HTTPError,))
def get_access_and_session_token_ninja(email, password):
    log.info('Fetching [bold white]access token[/bold white] and [bold white]session token[/bold white]...')

    url = "http://localhost:7999/auth/token"

    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    data = {
        'username': email,
        'password': password
    }

    try:
        res = requests.post(url, headers=headers, data=data, verify=False)
        res.raise_for_status()
    except requests.exceptions.HTTPError as http_err:
        log.error(f'HTTP Error. content: {http_err.response.text}')
        raise

    json_content = res.json()
    if (
        (session_token := json_content.get('session_token')) and
        (access_token := json_content.get('accessToken')) and
        len(session_token) > 0 and
        len(access_token) > 0  # noqa
    ):
        log.info('Got it.')
        return session_token, access_token
    else:
        log.error(f'Fetch failed. json_content:')
        log.error(json_content)

    return None, None


@retry(tries=6, delay=1, backoff=2, exceptions=(requests.exceptions.HTTPError,))
def get_share_token(access_token):
    log.info('Fetching corresponding [bold white]share token[/bold white]...')

    url = urljoin(pandora_next_base_url, "/api/token/register")

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

    res = requests.post(url, headers=headers, data=data)
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


@retry(tries=6, delay=1, backoff=2, exceptions=(requests.exceptions.HTTPError,))
def refresh_session_token(session_token):
    log.info('Refreshing current [bold white]session token[/bold white]...')

    url = urljoin(pandora_next_base_url, "/api/auth/session")

    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    data = {
        'session_token': session_token
    }

    res = requests.post(url, headers=headers, data=data)
    res.raise_for_status()

    json_content = res.json()
    if (
        (session_token := json_content.get('session_token')) and
        (access_token := json_content.get('access_token')) and
        len(session_token) > 0 and
        len(access_token) > 0  # noqa
    ):
        log.info('Got it.')
        return session_token, access_token
    else:
        log.error(f'Fetch failed. json_content:')
        log.error(json_content)

    return None, None


@retry(tries=6, delay=1, backoff=2, exceptions=(requests.exceptions.HTTPError,))
def refresh_pool_token(share_tokens):
    log.info(f'Fetching corresponding [bold white]pool token[/bold white] using {len(share_tokens)} share_tokens...')

    if not (0 < len(share_tokens) <= 100):
        log.error(f'The number of share_tokens must be less than 100! Current: {len(share_tokens)}.')
        return None

    url = urljoin(pandora_next_base_url, "/api/pool/update")

    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    data = {
        'share_tokens': '\n'.join(share_tokens),
        'pool_token': pandora_next_pool_token
    }

    res = requests.post(url, headers=headers, data=data)
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


def refresh_tokens(count: int, conditions: List[BinaryExpression]):

    # 获取可用账号，刷新或获取 session_token、access_token
    # 并获取相应的 share_token
    with DB_Session() as session:

        # 获取统计信息
        matching_field_count = session.query(Account).filter(and_(*conditions, Account.is_active == 1)).count()
        total_field_count = session.query(Account).filter(Account.is_active == 1).count()

        log.info(f'当前数据库账号总数: {total_field_count}，符合条件的账号数: {matching_field_count}')
        log.info(f'刷新{f"{count}个" if count != -1 else "所有"}账号的 [bold white]session/access/share token[/bold white]...')

        # 查询条件：conditions 且 is_active 为 1
        records = session.query(Account).filter(
            and_(
                *conditions,
                # Account.session_token.is_(None),
                # Account.share_token.is_(None),
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

                if record.session_token is not None:
                    # session_token 已存在，进行刷新
                    log.info(f'[bold white]session_token[/bold white] 已存在，进行刷新...')

                    try:
                        # 使用函数处理获取 session token 和 access token
                        session_token, access_token = refresh_session_token(record.session_token)
                    except requests.exceptions.HTTPError as http_err:
                        log.error(f'[bold red]对账号\\[{record.id}]({email})刷新失败！请检查！[/bold red]')
                        log.error('[bold red]Continuing...[/bold red]')
                        continue

                    # 更新记录
                    if session_token and access_token:
                        log.info(f'更新数据库字段...')
                        record.session_token = session_token
                        record.access_token = access_token
                        record.is_active = 1
                        session.commit()
                        log.info(f'更新成功！')
                    else:
                        log.info(f'[bold red]!!! 此处应当按照错误情况进行处理 !!![/bold red]')
                else:
                    # session_token 不存在，进行获取
                    log.info(f'[bold white]session_token[/bold white] 不存在，进行获取...')

                    try:
                        # 使用函数处理获取 session token 和 access token
                        session_token, access_token = get_access_and_session_token(email, password)
                    except requests.exceptions.HTTPError as http_err:
                        log.error(f'[bold red]对账号\\[{record.id}]({email})刷新失败！请检查！[/bold red]')
                        log.error('[bold red]Continuing...[/bold red]')
                        continue

                    # 更新记录
                    if session_token and access_token:
                        log.info(f'更新数据库字段...')
                        record.session_token = session_token
                        record.access_token = access_token
                        record.is_active = 1
                        session.commit()
                        log.info(f'更新成功！')
                    else:
                        log.info(f'[bold red]!!! 此处应当按照错误情况进行处理 !!![/bold red]')

                try:
                    # 不论是首次获取还是刷新，都更新 share token
                    share_token = get_share_token(access_token)
                except requests.exceptions.HTTPError as http_err:
                    log.error(f'[bold red]对账号\\[{record.id}]({email})刷新失败！请检查！[/bold red]')
                    log.error('[bold red]Continuing...[/bold red]')
                    continue

                if share_token:
                    log.info(f'更新数据库字段...')
                    record.share_token = share_token
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
        matching_field_count = session.query(Account).filter(and_(Account.share_token.is_not(None), Account.is_active == 1)).count()
        total_field_count = session.query(Account).filter(Account.is_active == 1).count()

        log.info(f'当前数据库账号总数: {total_field_count}，可组装的账号数: {matching_field_count}')
        log.info(f'根据已存储的 [bold white]share token[/bold white] 组建 [bold white]pool token[/bold white]...')

        # 查询条件：share_token 不为 NULL 且 is_active 为 1
        records = session.query(Account.share_token).filter(
            and_(
                Account.share_token.is_not(None),
                Account.is_active == 1
            )
        ).limit(count).all()

        if records:
            share_tokens = [record[0] for record in records]

            try:
                # 组装 Pool Token
                pool_token = refresh_pool_token(share_tokens)
            except requests.exceptions.HTTPError as http_err:
                log.error(f'[bold red]组装 Pool Token 失败！请检查！[/bold red]')
                log.error('[bold red]Continuing...[/bold red]')
                return

            log.warning('[bold white]Pool token[/bold white] [bold green]已生成完毕。[/bold green]')
            log.warning(pool_token)

        log.warning('[bold green]未找到更多符合条件的记录！已全部处理完毕。[/bold green]')

# ------------------------------------------------------------------------------------

@app.command(help='Obtain new session tokens if not exists.')
def obtain(count: int = typer.Option(10, help='Number of accounts to process')):
    log.info("[bold green]Obtaining session token and refresh all tokens[/bold green]")
    refresh_tokens(count=count, conditions=[
        Account.session_token.is_(None)
    ])


@app.command(help='Refresh tokens.')
def refresh(empty_tokens: bool = typer.Option(False, help='Refresh tokens only if share or access token is empty'),
            count: int = typer.Option(-1, help='Number of accounts to process')):

    log.info(f"[bold green]Refreshing tokens for {count if count != -1 else 'ALL'} accounts.[/bold green]")

    if empty_tokens:
        log.info("[green]Only refreshing if share or access tokens are empty.[/green]")
        refresh_tokens(count=count, conditions=[
            Account.session_token.is_not(None),
            or_(
                Account.access_token.is_(None),
                Account.share_token.is_(None),
            ),
        ])
    else:
        log.info("[green]Refreshing existed session, share and access tokens.[/green]")
        refresh_tokens(count=count, conditions=[
            Account.session_token.is_not(None),
        ])


@app.command(help='Assemble pool token')
def assemble(count: int = typer.Option(100, help='Number of accounts to process')):
    log.info(f"[bold green]Assembling pool tokens for {count} accounts.[/bold green]")
    assemble_pool_token(count=count)


if __name__ == '__main__':
    app()
