#!/usr/bin/env python
# coding=utf-8

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base  # 导入前面定义的Base

engine = create_engine('sqlite:///account.db')
Session = sessionmaker(bind=engine)

def init_db():
    Base.metadata.create_all(engine)

