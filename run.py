"""
一键运行 — 采集 + 分析 + 生成报告
运行方式: py -3.14 run.py
"""

import sys
import subprocess
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

BASE = Path(__file__).parent
PY = sys.executable

def run_step(label: str, script: Path):
    log.info(f'=== {label} ===')
    result = subprocess.run([PY, str(script)], cwd=str(BASE))
    if result.returncode != 0:
        log.error(f'{label} 失败，退出码 {result.returncode}')
        sys.exit(result.returncode)
    log.info(f'{label} 完成')

if __name__ == '__main__':
    run_step('1/3 浏览器采集', BASE / 'scrapers' / 'main_browser.py')
    run_step('2/3 分析评分',   BASE / 'analyzer' / 'main.py')
    run_step('3/3 生成报告',   BASE / 'analyzer' / 'report_generator.py')
    log.info('')
    log.info('全部完成！查看报告: py -3.14 show_report.py')
    log.info('或用浏览器打开: docs/index.html')
