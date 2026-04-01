# 🕵️ Amazon Spy — 选品雷达系统

> 每小时自动扫描亚马逊美国站，四门筛选 + 百分制评分，找出蓝海机会产品。

## 功能

- **自动采集**：BSR榜单 / Movers & Shakers / New Releases，覆盖13个类目
- **四门分析**：市场集中度 → 进入门槛 → 关键词切入口 → 评论痛点
- **百分制评分**：每个产品100分评分卡，自动分层 🟢蓝海 / 🟡可打 / 🔴避开
- **GitHub Pages看板**：实时可视化，自动更新

## 看板

📊 **[打开实时看板](https://liujiewen78-lab.github.io/amazon-spy-system/)**

## 本地运行

```bash
pip install -r requirements.txt
playwright install chromium

# 快速测试（2个类目，5个精分）
python run_quick.py

# 完整运行（13个类目）
python scrapers/main_browser.py
python analyzer/main.py
python analyzer/report_generator.py
python show_report.py
```

## 项目结构

```
scrapers/           采集层（Playwright浏览器自动化）
analyzer/           分析层（四门逻辑 + 评分卡）
data/snapshots/     原始数据（不入库）
docs/               GitHub Pages看板
config/rules.json   筛选规则配置
```

## 四个门逻辑

| 门 | 规则 | 触发后果 |
|---|---|---|
| 门1 市场集中度 | Top10头部品牌销量占比 > 75% | 直接淘汰 |
| 门2 进入门槛 | Top10全是高评论老链接 | 降级警告 |
| 门3 关键词切入口 | 无低竞争长尾词 | 降级警告 |
| 门4 评论痛点 | 无可改造痛点 | 不推荐 |

## 自动排除

- 重量 > 2kg 或 最长边 > 45cm
- 婴幼儿 / 医疗 / 食品 / 危险品
- 单件采购估算 > ¥500（约\$70）

---

*由 暴富天团2026 × Vibe Selling Agent 驱动*
