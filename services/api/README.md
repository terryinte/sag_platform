# API

SEO/GEO独立测评MVP的FastAPI服务。

除保留原有同步`/collect`和`/analyze`接口外，还提供：

- SQLite业务数据持久化；
- 客户、项目、合同、SEO、GEO、报告API；
- `/`浏览器工作台；
- `/reports/{project_id}/preview`打印报告；
- `/console`原采集调试台；
- `/docs`OpenAPI文档。

默认数据库位于仓库`data/sag-mvp.db`，可用`SAG_DATABASE_PATH`覆盖。
