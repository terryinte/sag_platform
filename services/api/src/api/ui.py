from __future__ import annotations

from textwrap import dedent


def render_usage_page() -> str:
    return dedent(
        """
        <!doctype html>
        <html lang="zh-CN">
          <head>
            <meta charset="utf-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1" />
            <title>SAG API Console</title>
            <style>
              :root {
                --bg: #f4efe6;
                --bg2: #fff7ef;
                --ink: #172033;
                --muted: rgba(23, 32, 51, 0.72);
                --line: rgba(23, 32, 51, 0.12);
                --card: rgba(255, 255, 255, 0.88);
                --card-solid: #ffffff;
                --accent: #ff6a3d;
                --accent2: #156d7a;
                --good: #0e8f4f;
                --warn: #b45f06;
                --shadow: 0 24px 60px rgba(23, 32, 51, 0.12);
              }

              * { box-sizing: border-box; }
              html, body { min-height: 100%; }
              body {
                margin: 0;
                font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
                color: var(--ink);
                background:
                  radial-gradient(circle at top left, rgba(255, 106, 61, 0.16), transparent 32%),
                  radial-gradient(circle at top right, rgba(21, 109, 122, 0.16), transparent 28%),
                  linear-gradient(180deg, var(--bg), var(--bg2));
              }

              .shell {
                max-width: 1280px;
                margin: 0 auto;
                padding: 32px 20px 40px;
              }

              .hero {
                display: grid;
                grid-template-columns: 1.15fr 0.85fr;
                gap: 20px;
                align-items: stretch;
                margin-bottom: 20px;
              }

              .panel {
                background: var(--card);
                backdrop-filter: blur(12px);
                border: 1px solid var(--line);
                border-radius: 24px;
                box-shadow: var(--shadow);
              }

              .hero-copy {
                padding: 30px;
                overflow: hidden;
                position: relative;
              }

              .hero-copy::after {
                content: "";
                position: absolute;
                inset: auto -20px -30px auto;
                width: 240px;
                height: 240px;
                border-radius: 50%;
                background: radial-gradient(circle, rgba(255, 106, 61, 0.16), transparent 65%);
                pointer-events: none;
              }

              .eyebrow {
                display: inline-flex;
                gap: 8px;
                align-items: center;
                font-size: 12px;
                letter-spacing: 0.18em;
                text-transform: uppercase;
                color: var(--accent2);
                font-weight: 700;
              }

              h1 {
                margin: 12px 0 10px;
                font-size: clamp(34px, 4vw, 58px);
                line-height: 0.98;
                letter-spacing: -0.04em;
              }

              .lede {
                max-width: 62ch;
                font-size: 16px;
                line-height: 1.7;
                color: var(--muted);
                margin: 0;
              }

              .chips {
                display: flex;
                flex-wrap: wrap;
                gap: 10px;
                margin-top: 22px;
              }

              .chip {
                display: inline-flex;
                align-items: center;
                gap: 8px;
                border-radius: 999px;
                padding: 8px 12px;
                background: rgba(255, 255, 255, 0.72);
                border: 1px solid var(--line);
                font-size: 13px;
                color: var(--ink);
              }

              .route-card {
                padding: 22px;
                display: grid;
                gap: 12px;
                align-content: start;
              }

              .route-card h2,
              .section-title {
                margin: 0;
                font-size: 18px;
                letter-spacing: -0.02em;
              }

              .route-row {
                display: flex;
                justify-content: space-between;
                gap: 12px;
                align-items: center;
                padding: 14px 16px;
                border-radius: 16px;
                background: rgba(255, 255, 255, 0.72);
                border: 1px solid var(--line);
              }

              .route-row code {
                font-size: 13px;
                color: var(--accent2);
                background: rgba(21, 109, 122, 0.08);
                padding: 4px 8px;
                border-radius: 999px;
              }

              .route-note {
                font-size: 13px;
                line-height: 1.5;
                color: var(--muted);
                margin: 0;
              }

              .workbench {
                display: grid;
                grid-template-columns: 1.08fr 0.92fr;
                gap: 20px;
              }

              .form-card,
              .result-card {
                padding: 24px;
              }

              .section-subtitle {
                margin: 6px 0 18px;
                color: var(--muted);
                font-size: 14px;
                line-height: 1.6;
              }

              .grid {
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: 14px;
              }

              .field {
                display: grid;
                gap: 8px;
              }

              .field.full {
                grid-column: 1 / -1;
              }

              label {
                font-size: 12px;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.14em;
                color: var(--accent2);
              }

              input, textarea {
                width: 100%;
                border-radius: 16px;
                border: 1px solid var(--line);
                background: rgba(255, 255, 255, 0.88);
                color: var(--ink);
                padding: 14px 15px;
                font: inherit;
                outline: none;
                transition: border-color 0.15s ease, box-shadow 0.15s ease, transform 0.15s ease;
              }

              textarea {
                min-height: 124px;
                resize: vertical;
                line-height: 1.6;
                font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
                font-size: 13px;
              }

              input:focus, textarea:focus {
                border-color: rgba(255, 106, 61, 0.8);
                box-shadow: 0 0 0 4px rgba(255, 106, 61, 0.14);
              }

              .actions {
                display: flex;
                flex-wrap: wrap;
                gap: 10px;
                margin-top: 18px;
              }

              .btn {
                border: 0;
                border-radius: 14px;
                padding: 12px 16px;
                font: inherit;
                font-weight: 700;
                cursor: pointer;
                transition: transform 0.15s ease, box-shadow 0.15s ease, opacity 0.15s ease;
              }

              .btn:hover { transform: translateY(-1px); }
              .btn.primary {
                color: white;
                background: linear-gradient(135deg, var(--accent), #ff8c4f);
                box-shadow: 0 14px 28px rgba(255, 106, 61, 0.24);
              }

              .btn.secondary {
                color: var(--ink);
                background: rgba(255, 255, 255, 0.76);
                border: 1px solid var(--line);
              }

              .meta {
                margin-top: 14px;
                font-size: 12px;
                color: var(--muted);
                line-height: 1.6;
              }

              .result-head {
                display: flex;
                justify-content: space-between;
                gap: 12px;
                align-items: center;
                margin-bottom: 12px;
              }

              .status {
                display: inline-flex;
                align-items: center;
                gap: 8px;
                font-size: 13px;
                font-weight: 700;
                color: var(--warn);
              }

              .status.good { color: var(--good); }
              pre {
                margin: 0;
                min-height: 560px;
                max-height: 760px;
                overflow: auto;
                padding: 18px;
                border-radius: 18px;
                background: #0f1724;
                color: #d7e3ff;
                border: 1px solid rgba(255, 255, 255, 0.08);
                font-size: 13px;
                line-height: 1.6;
                white-space: pre-wrap;
                word-break: break-word;
              }

              .footer {
                margin-top: 18px;
                color: var(--muted);
                font-size: 12px;
              }

              @media (max-width: 1080px) {
                .hero,
                .workbench {
                  grid-template-columns: 1fr;
                }
              }

              @media (max-width: 720px) {
                .shell { padding-inline: 14px; }
                .hero-copy,
                .route-card,
                .form-card,
                .result-card { padding: 18px; }
                .grid { grid-template-columns: 1fr; }
              }
            </style>
          </head>
          <body>
            <main class="shell">
              <section class="hero">
                <div class="panel hero-copy">
                  <div class="eyebrow">SAG API Console</div>
                  <h1>用一个页面直接跑采集和分析。</h1>
                  <p class="lede">
                    这个页面就是你要的前端使用入口。填写域名、品牌、关键词和 GEO 查询后，
                    直接调用 <strong>/collect</strong> 或 <strong>/analyze</strong>。
                    页面会把返回结果原样展示，方便你检查采集错误、分项得分和建议列表。
                  </p>
                  <div class="chips">
                    <span class="chip">同步请求</span>
                    <span class="chip">Collect / Analyze</span>
                    <span class="chip">同站点调用</span>
                    <span class="chip">JSON 输出</span>
                  </div>
                </div>

                <aside class="panel route-card">
                  <h2>接口入口</h2>
                  <div class="route-row">
                    <span>采集数据</span>
                    <code>POST /collect</code>
                  </div>
                  <div class="route-row">
                    <span>采集 + 分析</span>
                    <code>POST /analyze</code>
                  </div>
                  <p class="route-note">
                    页面请求会使用同源相对路径。只要 FastAPI 在本机 8000 端口运行，就能直接点按钮使用。
                  </p>
                </aside>
              </section>

              <section class="workbench">
                <div class="panel form-card">
                  <h2 class="section-title">请求表单</h2>
                  <p class="section-subtitle">
                    这里会把输入包装成 API 请求体。关键词和 GEO 查询默认使用 JSON 数组，保持和后端 DTO 一致。
                  </p>

                  <div class="grid">
                    <div class="field">
                      <label for="domain">Domain</label>
                      <input id="domain" value="example.com" />
                    </div>
                    <div class="field">
                      <label for="url">URL</label>
                      <input id="url" value="https://example.com" />
                    </div>
                    <div class="field full">
                      <label for="brand-name">Brand Name</label>
                      <input id="brand-name" value="Acme" />
                    </div>
                    <div class="field full">
                      <label for="keywords">Keywords JSON</label>
                      <textarea id="keywords">[{"keyword":"best crm","engine":"google"}]</textarea>
                    </div>
                    <div class="field full">
                      <label for="geo-queries">GEO Queries JSON</label>
                      <textarea id="geo-queries">[{"query":"best crm for factories","engine_hint":"global"}]</textarea>
                    </div>
                  </div>

                  <div class="actions">
                    <button class="btn secondary" data-action="collect">Collect</button>
                    <button class="btn primary" data-action="analyze">Analyze</button>
                  </div>
                  <p class="meta">
                    环境变量仍然需要在服务启动时提供：
                    <code>DATAFORSEO_LOGIN</code>,
                    <code>DATAFORSEO_PASSWORD</code>,
                    <code>OPENROUTER_API_KEY</code>,
                    <code>QIANFAN_ACCESS_KEY</code>,
                    <code>QIANFAN_SECRET_KEY</code>.
                  </p>
                </div>

                <div class="panel result-card">
                  <div class="result-head">
                    <h2 class="section-title">响应输出</h2>
                    <span id="status" class="status">Idle</span>
                  </div>
                  <pre id="output">选择 Collect 或 Analyze 开始。</pre>
                </div>
              </section>
            </main>

            <script>
              const output = document.getElementById("output");
              const status = document.getElementById("status");

              function buildPayload() {
                return {
                  domain: document.getElementById("domain").value.trim(),
                  url: document.getElementById("url").value.trim(),
                  brand_name: document.getElementById("brand-name").value.trim(),
                  keywords: JSON.parse(document.getElementById("keywords").value),
                  geo_queries: JSON.parse(document.getElementById("geo-queries").value),
                };
              }

              async function run(action) {
                try {
                  status.textContent = "Running";
                  status.className = "status";
                  const response = await fetch(`/${action}`, {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify(buildPayload()),
                  });
                  const body = await response.json();
                  output.textContent = JSON.stringify(body, null, 2);
                  status.textContent = response.ok ? "OK" : `HTTP ${response.status}`;
                  status.className = response.ok ? "status good" : "status";
                } catch (error) {
                  output.textContent = String(error);
                  status.textContent = "Error";
                  status.className = "status";
                }
              }

              document.querySelectorAll("[data-action]").forEach((button) => {
                button.addEventListener("click", () => run(button.dataset.action));
              });
            </script>
          </body>
        </html>
        """
    ).strip()
