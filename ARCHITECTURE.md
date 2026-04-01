# Amazon 选品研究系统 — 架构文档

> **目标**：全自动、每小时运行的亚马逊美国站选品研究系统。国内产品卖给老外。输出Top 10候选产品，GitHub Pages可视化展示，历史快照可横向对比。

---

## 系统概览

```
任务入口（内置规则）
    ↓
采集层（每小时触发 · GitHub Actions）
    ↓
标准化层（字段归一 · 同义词归并）
    ↓
分析引擎（4个Agent协同评分）
    ↓
评分排序（评分卡 · 三层分级）
    ↓
输出层（JSON快照 · GitHub Pages可视化）
```

---

## 第一层：任务入口（内置，无需手动填写）

系统内置一套全局规则，每次运行自动应用，无需人工干预。

### 全局采集范围
- **站点**：Amazon 美国站（amazon.com）
- **类目**：全类目自动扫描，但内置排除规则过滤

### 内置排除规则（硬性过滤）

| 排除类型 | 判断标准 |
|---------|---------|
| 大件重货 | 重量 > 2kg 或 最长边 > 45cm |
| 婴幼儿 | 类目包含 Baby、Infant、Toddler |
| 医疗/健康认证类 | 类目包含 Medical、Health Devices、FDA required |
| 食品 | 类目包含 Grocery、Food、Beverage |
| 危险品 | 含电池锂电（单独运输）、化学品 |
| 超高预算 | 采购成本估算 > ¥500/件（约$70） |

### 利润红线
- 毛利率 ≥ 40%
- FBA配送费后净利润 ≥ $5/件
- 总备货成本 ≤ ¥100,000

---

## 第二层：采集层

### 采集来源（公开页面）

| 来源 | URL | 采集内容 |
|------|-----|---------|
| Amazon BSR | amazon.com/bestsellers | 各类目畅销榜，销量线索 |
| Amazon New Releases | amazon.com/gp/new-releases | 新品热榜，趋势线索 |
| Amazon Movers & Shakers | amazon.com/gp/movers-and-shakers | 短期飙升产品 |
| Amazon 搜索结果页 | amazon.com/s?k={keyword} | Top10竞品、价格、评论量 |
| Amazon 产品详情页 | amazon.com/dp/{ASIN} | 完整产品数据 |
| Amazon 评论页 | amazon.com/product-reviews/{ASIN} | 用户痛点挖掘 |
| Google Trends | trends.google.com | 搜索趋势验证 |

### 采集技术栈
- **HTTP请求**：`httpx` + 随机UA轮换 + 请求限速（每请求间隔3-8秒）
- **HTML解析**：`BeautifulSoup4` + `lxml`
- **反爬处理**：随机UA、随机延迟、代理池（可选）
- **调度**：GitHub Actions（每小时触发）

### Keepa 免费版使用
- Keepa公开价格历史图（无需API）：抓取 `keepa.com/product/{ASIN}` 页面
- 获取：30天/90天价格走势、销售排名历史

### Helium 10 免费版替代
- 免费版核额度有限，系统优先使用公开Amazon数据
- Helium 10 Chrome插件数据可手动导入作为补充

---

## 第三层：标准化层

每条采集记录统一转换为以下结构：

```json
{
  "snapshot_time": "2026-04-01T10:00:00Z",
  "asin": "B0XXXXXXXX",
  "title": "...",
  "brand": "...",
  "price": 29.99,
  "currency": "USD",
  "rating": 4.3,
  "review_count": 1248,
  "bsr": 1523,
  "bsr_category": "Kitchen & Dining",
  "weight_kg": 0.18,
  "dimensions_cm": [12, 8, 3],
  "main_image_url": "...",
  "bullet_points": ["...", "..."],
  "top_complaints": ["线太短", "漏水"],
  "top_praises": ["小巧", "好用"],
  "keyword": "portable blender",
  "source_page": "movers_shakers",
  "platform": "amazon_us",
  "scraped_at": "2026-04-01T10:03:22Z"
}
```

---

## 第四层：分析引擎（四个门）

### 门1：市场集中度
- 抓取该关键词Top 10搜索结果
- 计算各品牌预估销量占比
- **硬规则**：Top10中单一品牌销量占比 > 75% → 直接淘汰

### 门2：进入门槛
- Top 10中，评论数 < 200 的链接数量
- 有无近90天上架的新品出现在前排
- **硬规则**：Top10全部 > 500评论且无新品 → 降级为红海

### 门3：关键词切入口
- 统计该类目下低竞争长尾词（搜索量>500，竞品数<500）
- **硬规则**：找不到任何低竞争入口词 → 再降级

### 门4：评论痛点可改造性
- 从Top5竞品各抓取最近50条差评
- 抽取高频痛点词（质量/尺寸/功能/包装等）
- **硬规则**：无明确可改造痛点 → 不推荐

### 三层输出结果

| 等级 | 判断标准 | 颜色标注 |
|------|---------|---------|
| 🔴 直接放弃 | 门1触发（品牌垄断）或门2+门3同时触发 | 红色 |
| 🟡 可切入红海 | 门1未触发，但门2或门3其中一个有警告 | 黄色 |
| 🟢 优先蓝海 | 四个门全部通过，有明确改造空间 | 绿色 |

---

## 第五层：评分卡

| 维度 | 满分 | 评分依据 |
|------|------|---------|
| 需求强度 | 20分 | BSR排名 + 月销估算 + Google Trends趋势 |
| 竞争可打程度 | 20分 | 门1+门2结果 |
| 利润空间 | 20分 | (售价 - 采购估算 - FBA费) / 售价 |
| 供应链复杂度 | 10分 | 重量/尺寸/认证要求 |
| 合规风险 | 10分 | 类目禁限售、认证要求 |
| 评论痛点可改造性 | 10分 | 门4结果 |
| 内容传播潜力 | 10分 | 图片表达力、礼品属性、情感化程度 |
| **总分** | **100分** | |

### 每份报告输出格式（Top 10）

```json
{
  "report_id": "2026-04-01T10:00:00Z",
  "prev_report_id": "2026-04-01T09:00:00Z",
  "top10": [
    {
      "rank": 1,
      "asin": "...",
      "title": "...",
      "tier": "blue_ocean",
      "total_score": 82,
      "score_breakdown": {...},
      "opportunity_summary": "一句话机会判断",
      "top3_evidence": ["...", "...", "..."],
      "top3_risks": ["...", "...", "..."],
      "entry_strategy": "建议切入点",
      "delta_vs_prev": {
        "score_change": +3,
        "rank_change": +2,
        "review_count_change": +47
      }
    }
  ]
}
```

---

## 第六层：输出层

### 数据存储（GitHub仓库）
```
amazon-spy-system/
├── data/
│   ├── snapshots/
│   │   ├── 2026-04-01T10.json   # 每小时快照
│   │   ├── 2026-04-01T11.json
│   │   └── ...
│   └── latest.json              # 最新一份（前端直读）
├── docs/                        # GitHub Pages前端
│   ├── index.html
│   ├── app.js
│   └── style.css
├── scrapers/                    # 采集脚本
│   ├── amazon_scraper.py
│   ├── trends_scraper.py
│   └── review_analyzer.py
├── analyzer/                    # 分析引擎
│   ├── scoring.py
│   ├── filters.py
│   └── report_generator.py
├── config/
│   └── rules.json               # 评分规则配置
├── requirements.txt
└── .github/
    └── workflows/
        └── hourly_scrape.yml    # GitHub Actions调度
```

### GitHub Actions调度（每小时）
- **触发器**：`schedule: cron: '0 * * * *'`（每小时整点）
- **运行步骤**：采集 → 标准化 → 分析 → 生成报告JSON → 提交到data/snapshots/ → 更新latest.json → 触发Pages部署
- **运行环境**：GitHub Actions免费版（2000分钟/月，每次约5分钟，每天24次=120分钟，完全够用）

### GitHub Pages前端功能
- **首页**：最新一份Top 10报告，三层颜色标注
- **历史对比**：下拉选择任意两个时间点的报告，并排对比
- **趋势图**：某产品/关键词的评分走势折线图
- **筛选器**：按等级（蓝/黄/红）、按类目、按评分区间筛选
- **详情弹窗**：点击任意产品查看完整评分卡和证据链

---

## 技术栈汇总

| 层 | 技术 | 理由 |
|---|-----|------|
| 调度 | GitHub Actions | 免费、稳定、无需服务器 |
| 采集 | Python + httpx + BeautifulSoup4 | 轻量、够用 |
| 存储 | GitHub仓库JSON文件 | 零成本、天然版本控制 |
| 分析 | Python + OpenAI API（评论摘要） | 智能抽取痛点 |
| 前端 | HTML/CSS/JS（Vanilla） | 无需构建工具，GitHub Pages直接部署 |
| 可视化 | Chart.js | 轻量图表库，CDN引入 |

---

## 成本估算

| 项目 | 成本 |
|------|------|
| GitHub Actions | 免费（2000分钟/月） |
| GitHub Pages | 免费 |
| GitHub仓库存储 | 免费（JSON文件小） |
| OpenAI API（评论摘要） | ~$0.5-2/天（可选，可先不用） |
| 代理IP（可选） | $10-20/月（初期可不用） |
| **合计** | **$0-22/月** |

---

## 快速启动步骤

1. Fork/创建 GitHub 仓库
2. 开启 GitHub Pages（docs/ 目录）
3. 设置 GitHub Secrets（OpenAI Key等）
4. 启用 GitHub Actions
5. 手动触发第一次运行验证
6. 之后每小时自动运行
