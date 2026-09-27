# -*- coding: utf-8 -*-
"""工程路径：仓库根、模块根、输出目录。"""

import os

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE_ROOT = os.path.dirname(HERE)
PROJECT_ROOT = os.path.dirname(MODULE_ROOT)
OUTPUT_DIR = os.path.join(MODULE_ROOT, "输出")


def project_root():
    return PROJECT_ROOT


def module_root():
    return MODULE_ROOT


def output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    return OUTPUT_DIR
