#!/usr/bin/env python
# coding=utf-8
from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

class Account(Base):
    __tablename__ = 'account_info'  # noqa

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    is_active = Column(Integer, default=1)  # 可用性，通常用布尔值，但这里用整数表示（1表示可用，0表示不可用）

    web_session_token = Column(Text)
    web_access_token = Column(Text)

    pandora_share_token = Column(Text)

    platform_refresh_token = Column(Text)
    platform_access_token = Column(Text)
    platform_sess_key = Column(Text)

    web_refresh_at = Column(DateTime(), default=None)
    web_session_token_expire_at = Column(DateTime(), default=None)
    web_access_token_expire_at = Column(DateTime(), default=None)

    platform_refresh_at = Column(DateTime(), default=None)
    platform_refresh_token_expire_at = Column(DateTime(), default=None)
    platform_access_token_expire_at = Column(DateTime(), default=None)

    created_at = Column(DateTime(), default=datetime.utcnow)

