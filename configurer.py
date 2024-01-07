#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import yaml

# 配置文件路径
config_file = './config.yaml'

def get_configuration():
    try:
        # 读取 YAML 配置文件
        with open(config_file, 'r') as file:
            config = yaml.safe_load(file)
            return config

    except FileNotFoundError:
        # 如果文件不存在，则打印错误信息
        logging.critical(f"配置文件 {config_file} 不存在，请创建该文件。")
        exit(-1)

    except yaml.YAMLError as exc:
        # 如果文件存在但格式不正确，则打印错误信息
        logging.critical(f"错误：解析 YAML 文件时发生错误。请检查 {config_file} 的格式。", exc_info=exc)
        exit(-1)
