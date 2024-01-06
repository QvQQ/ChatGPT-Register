#!/usr/bin/env python
# coding=utf-8
from contextlib import contextmanager
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError, OperationalError
from sqlalchemy.orm import sessionmaker
from sshtunnel import SSHTunnelForwarder, BaseSSHTunnelForwarderError

from models import Base  # 导入前面定义的Base

# for log
import logging
from rich.console import Console
from rich.logging import RichHandler

# ------------------------------------------------------------------------------------
# 创建一个Rich的Console对象
console = Console()

# ------------------------------------------------------------------------------------


class PlainSessionMaker:

    def __init__(self, database_uri: str = None):

        # 配置 logger
        self.logger = logging.getLogger(self.__class__.__name__)

        # 配置数据库信息
        self.database_uri = database_uri
        self._create_engine()

    @contextmanager
    def db_session(self, database_uri: str = None):

        try:
            if database_uri is not None:
                self.database_uri = database_uri
                self._create_engine()
            else:
                if self.database_uri is None:
                    self.logger.error('Neither the initial database_uri nor the current database_uri exists.')
                    raise ValueError('Neither the initial database_uri nor the current database_uri exists.')

            with self.session_maker() as session:
                yield session

        except SQLAlchemyError as e:
            self.logger.error(f'[bold red]SQLAlchemyError occurred![/bold red]', exc_info=e)
            raise e
        except OperationalError as e:
            self.logger.error(f'[bold red]OperationalError occurred![/bold red]', exc_info=e)
            raise e

    def _create_engine(self):

        if self.database_uri is not None:
            self.engine = create_engine(self.database_uri)
            self.session_maker = sessionmaker(bind=self.engine)
            Base.metadata.create_all(self.engine)
        else:
            self.engine = None
            self.session_maker = None


class TunnelledSessionMaker(PlainSessionMaker):

    def __init__(self,
                 *,
                 ssh_host: str,
                 ssh_port: int,
                 ssh_user: str,
                 ssh_password: Optional[str] = None,
                 ssh_private_key: Optional[str] = None,
                 remote_db_host: str,
                 remote_db_port: int,
                 database_user: str,
                 database_password: str,
                 database_name: str):
        super().__init__()
        # ssh 账号信息
        self.ssh_host, self.ssh_port, self.ssh_user = ssh_host, ssh_port, ssh_user

        # ssh 认证信息
        if not any([ssh_password, ssh_private_key]):
            self.logger.error('Neither the ssh_password nor the ssh_private_key exists.')
            raise ValueError('Neither the ssh_password nor the ssh_private_key exists.')

        self.ssh_password, self.ssh_private_key = ssh_password, ssh_private_key

        # 数据库连接信息
        self.remote_db_host, self.remote_db_port = remote_db_host, remote_db_port

        # 数据库认证信息
        self.database_user, self.database_password, self.database_name = database_user, database_password, database_name

    @contextmanager
    def tunnelled_db_session(self):

        try:
            # 建立 SSH 隧道
            with SSHTunnelForwarder(
                    (self.ssh_host, self.ssh_port),
                    ssh_username=self.ssh_user,
                    ssh_pkey=self.ssh_private_key,  # 指定私钥文件
                    ssh_password=self.ssh_password,
                    remote_bind_address=(self.remote_db_host, self.remote_db_port),
            ) as tunnel:

                self.logger.info(f"[bold green]Tunnel established at local port: {tunnel.local_bind_port}[/bold green]")

                # 数据库引擎和会话配置
                self.database_uri = f'mysql+pymysql://{self.database_user}:{self.database_password}@localhost:{tunnel.local_bind_port}/{self.database_name}'

                try:
                    # 获取 session_maker
                    self._create_engine()

                    # 执行数据库操作
                    with self.session_maker() as session:
                        yield session
                except SQLAlchemyError as e:
                    self.logger.error(f'[bold red]SQLAlchemyError occurred![/bold red]', exc_info=e)
                    raise e
                except OperationalError as e:
                    self.logger.error(f'[bold red]OperationalError occurred![/bold red]', exc_info=e)
                    raise e

        except BaseSSHTunnelForwarderError as e:
            self.logger.error(f'[bold red]Tunnel establishment failed![/bold red]', exc_info=e)
            raise e

def get_session_maker(database_uri):
    engine = create_engine(database_uri)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    return Session


if __name__ == '__main__':

    # 配置日志，使用RichHandler
    logging.basicConfig(
        level="INFO",  # 设置日志级别
        format="%(message)s",  # 设置日志格式
        datefmt="%Y/%m/%d %H:%M:%S",  # 设置时间格式
        handlers=[RichHandler(console=console, show_path=False, rich_tracebacks=False, markup=True)]  # 使用RichHandler
    )