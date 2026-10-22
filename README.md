# SAG Platform

面向企业市场负责人的 SEO/GEO 独立第三方测评 MVP。平台围绕“服务商承诺 vs 独立测评实际结果”保存证据、执行人工复核、生成报告并持续比较趋势。

仓库包含三个 Python 包：

- `services/analysis-engine`：SEO/AEO/GEO评分与建议内核
- `services/data-collectors`：DataForSEO、OpenRouter、百度千帆采集适配
- `services/api`：FastAPI业务API、SQLite持久化、工作台和打印报告

## MVP功能

- 客户、测评项目、服务商和订阅状态；
- 合同承诺、实际结果、证据与达成判断；
- SEO指标、关键词排名和中英文CSV导入；
- 版本化GEO问题库、检测批次、原始回答与人工复核；
- OpenRouter/百度千帆批量执行，以及其他平台的人工采样；
- SEO/GEO跨期趋势、竞品提及和异常预警；
- A4打印报告和固定报告归档；
- 一键演示数据。

## Requirements

- Python 3.11+

## 一键启动

```bash
./scripts/setup.sh
./scripts/run.sh
```

打开：

- 工作台：`http://127.0.0.1:8000/`
- API文档：`http://127.0.0.1:8000/docs`
- 原采集调试台：`http://127.0.0.1:8000/console`

首次进入可点击“载入演示”，无需任何外部API密钥即可体验完整业务流程。

## 手工安装

Install all local packages in editable mode from the repository root:

```bash
python3 -m pip install -e services/analysis-engine -e services/data-collectors -e services/api
```

For test dependencies, include each package's `dev` extra:

```bash
python3 -m pip install -e "services/analysis-engine[dev]" -e "services/data-collectors[dev]" -e "services/api[dev]"
```

## 测试

```bash
(cd services/analysis-engine && ../../.venv/bin/python -m pytest)
(cd services/data-collectors && ../../.venv/bin/python -m pytest)
(cd services/api && ../../.venv/bin/python -m pytest)
```

## 外部数据源（可选）

The API reads provider credentials from environment variables:

```bash
export DATAFORSEO_LOGIN="..."
export DATAFORSEO_PASSWORD="..."
export OPENROUTER_API_KEY="..."
export QIANFAN_ACCESS_KEY="..."
export QIANFAN_SECRET_KEY="..."
```

不配置密钥时，CSV导入、人工GEO采样和报告仍可使用。配置后可调用原采集接口和GEO批量执行。

## 数据库

默认数据库为仓库下的`data/sag-mvp.db`，可通过环境变量覆盖：

```bash
export SAG_DATABASE_PATH="/absolute/path/sag.db"
```

需求与验收口径见[`docs/SEO-GEO独立测评产品-需求规格说明书.md`](docs/SEO-GEO独立测评产品-需求规格说明书.md)。
