# SEO/AEO/GEO 多租户 SaaS 诊断平台 — 设计文档

## 1. 背景与目的

为不同企业客户提供品牌在传统搜索引擎（SEO）、答案引擎（AEO，如精选摘要/PAA）、生成式AI引擎（GEO，如ChatGPT/文心一言等大模型问答）中的可见度诊断报告，并给出优化建议。以SaaS服务模式运营，支持多客户、多企业档案的批量分析。目标市场：中英文双轨——同时覆盖中国大陆（百度、国产大模型）与海外（Google/Bing、ChatGPT/Claude/Gemini等）市场。

## 2. 开源调研结论（build vs buy）

市面上不存在现成的"SEO+AEO+GEO一体化多租户SaaS"开源平台。关键发现：
- geo-optimizer-skill (Auriti-Labs/geo-optimizer-skill, MIT, Python) — 最成熟的开源GEO/AEO工具，支持 geo audit（网站AI友好度评分）、geo citations（查询ChatGPT/Perplexity/Gemini/Claude的品牌引用情况）。已验证仓库真实、活跃。作为分析引擎核心。
- SerpBear (towfiqi/serpbear, MIT) — 自托管SERP排名追踪，仅支持Google，本次不采用。
- SEOnaut (StJudeWasHere/seonaut, MIT, Go) — 技术SEO站点审计，本次不采用。
- boxyhq/saas-starter-kit (MIT, Next.js) — 多租户SaaS脚手架，可作架构参考。

决策：不做完整开源集成，以 geo-optimizer-skill 为分析引擎核心，自建轻量SaaS层。

## 3. 总体架构（三层）

企业客户信息录入 → 数据采集层（官方API+第三方聚合API，不自建爬虫） → 分析引擎层（基于geo-optimizer-skill扩展，计算SEO/AEO/GEO三项分数） → SaaS应用层（多租户、计费、报告生成Web+PDF）

## 4. 组件设计

### 4.1 数据采集层
- 大模型问答（GEO核心）：OpenRouter/硅基流动聚合（ChatGPT/Claude/Gemini/DeepSeek/Qwen等）+ 百度千帆/字节火山/Moonshot官方API补充聚合平台未覆盖的国产模型
- 搜索引擎排名与精选摘要（SEO/AEO）：DataForSEO（支持Google/Bing/百度SERP，含Featured Snippet/PAA；不支持360/搜狗，MVP暂不覆盖）
- 网站技术面（AI友好度）：自研轻量抓取模块，读取客户自己网站的robots.txt、llms.txt、结构化数据(JSON-LD)、sitemap

### 4.2 分析引擎层（核心）
基于geo-optimizer-skill (Python库)扩展：
- SEO分数：关键词排名分布、收录健康度
- AEO分数：精选摘要/PAA命中率
- GEO分数：品牌在各大模型问答中的提及率、位置、引用来源（扩展geo citations逻辑，新增国产模型适配器）
- 网站AI友好度评分：robots.txt/llms.txt/结构化数据完整性（复用geo audit逻辑）
- 输出：0-100综合分+分项分+优先级排序的优化建议清单

### 4.3 SaaS应用层
- 认证/多租户：邮箱注册登录+Organization隔离，每组织下管理多个客户企业档案
- 计费：订阅制（基础额度）+超额报告按次付费。支付渠道：Stripe（海外）+支付宝/微信支付（国内，需接聚合支付网关）
- 报告生成：异步任务队列生成→Web仪表盘+PDF导出（Playwright或WeasyPrint渲染PDF）
- 定期监测：订阅用户可配置周期性重跑（cron），跟踪分数变化趋势

## 5. 数据流
企业信息录入 → 创建异步分析任务（采集大模型问答+SERP数据+网站技术面） → 分析引擎计算三项分数 → 结果存库 → 通知用户 → 用户查看Web报告/导出PDF

## 6. 错误处理
- 单个数据源失败→该项标记"数据缺失"，不影响其他分数计算，报告中注明数据完整性状态
- 计费失败→触发标准SaaS欠费降级/暂停生成新报告流程

## 7. 测试策略
- 分析引擎评分逻辑：单元测试
- 数据采集层：mock测试
- 关键用户旅程端到端测试：注册→录入企业→生成报告→导出PDF→订阅计费

## 8. 技术栈
- 后端：Python (FastAPI) — 与geo-optimizer-skill原生集成
- 前端：Next.js/React仪表盘
- 任务队列：Celery/RQ（配合Redis）
- 数据库：PostgreSQL（多租户）

## 9. MVP范围（明确排除项）
- 不集成SerpBear/SEOnaut等传统SEO工具
- 不支持360/搜狗（无成熟第三方聚合数据源，留待后续迭代）
- 不自建搜索引擎爬虫或浏览器自动化
- 覆盖：百度+Google+Bing（SEO/AEO）+6-8个主流大模型（国内外各半，GEO）
- Web仪表盘+PDF导出
- 订阅+超额按次计费（含国内支付渠道）
