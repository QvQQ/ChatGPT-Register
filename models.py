#!/usr/bin/env python
# coding=utf-8

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
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
    access_token = Column(String)
    session_token = Column(String)
    share_token = Column(String)
    created_at = Column(DateTime(), default=func.datetime('now', 'localtime'))

